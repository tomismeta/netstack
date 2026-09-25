"""RFV presentation boundaries: missing evidence, exact units and finalization."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analytics
import netstack_core as core
import netstack_output as output
from cli_fixture import Fixture


def document(metrics, status="completed"):
    return core.serialize_result({
        "schema_version": 1, "command": "rfv", "status": status,
        "stopping_reason": "completed_requested_collection" if status == "completed" else "deadline_exhausted",
        "snapshot": {"chain_id": 4663, "block_number": 10, "block_hash": "0x" + "bb" * 32,
                     "block_timestamp": 100, "recheck_status": "confirmed"},
        "metrics": metrics, "coverage": {"requested_scope": {"scope": "reports", "collection_complete": status == "completed",
                                                               "all_assets_exhaustive": False}},
        "errors": [], "not_proven": ["Known-universe accounting is not exhaustive ownership."],
    })


class SummaryAccounting(unittest.TestCase):
    def test_unknown_methodology_cannot_turn_null_total_or_unclassified_exposure_into_zero(self):
        full = document({
            "reports_methodology": {"status": "unsupported", "profile_id": None,
                "v4_principal_included": None, "fetched_this_run": True,
                "sources": [{"sha256": "ab" * 32, "retrieved_at": "2026-01-01T00:00:00Z"}],
                "evidence": [{"id": "calculation", "source_sha256": "ab" * 32, "excerpt": "unrecognized source"}],
                "headline_comparison": {"status": "unavailable", "website_value_usd": None},
                "limits": {"current_source_not_pinned_chain_fact": True}},
            "reports_true_rfv": {"value_wad": None, "unit": "USDG", "methodology_valid": False,
                                 "required_missing": {"methodology": ["Unsupported current calculation"]}},
            "reports_historical_rfv": {"value_wad": "123", "unit": "USDG wad", "recipe_date": "2026-09-25"},
            "component_summary": {"wallet": {"status": "partial", "observed": {"rows": [
                {"quantity_raw": "7", "included_in_reports": None, "reports_value_wad": None}]},
                "publisher": {"contribution_wad": None, "unclassified_row_indices": [0]},
                "economic": {"known_rows_value_wad": None, "required_missing": ["Missing mark"]},
                "missing": ["Missing mark"]}},
        }, "partial")
        summary = json.loads(output.summarize_rfv(full))
        metrics = summary["metrics"]
        self.assertIsNone(metrics["reports_true_rfv"]["value_wad"])
        self.assertFalse(metrics["reports_true_rfv"]["methodology_valid"])
        self.assertEqual(metrics["reports_true_rfv"]["required_missing"]["methodology"], ["Unsupported current calculation"])
        self.assertEqual(metrics["reports_historical_rfv"]["value_wad"], "123")
        wallet = metrics["component_summary"]["wallet"]
        self.assertIsNone(wallet["observed"]["rows"][0]["included_in_reports"])
        self.assertEqual(wallet["economic"]["required_missing"], ["Missing mark"])
        methodology = metrics["reports_methodology"]
        self.assertEqual(methodology["sources"][0]["sha256"], "ab" * 32)
        self.assertIsNone(methodology["headline_comparison"]["website_value_usd"])
        self.assertTrue(methodology["limits"]["current_source_not_pinned_chain_fact"])
        self.assertNotIn("excerpt", methodology["evidence"][0])
        self.assertEqual(summary["status"], "partial")
        self.assertFalse(summary["coverage"]["requested_scope"]["all_assets_exhaustive"])

    def test_precise_amounts_and_economic_selection_survive_duplicate_ledger_removal(self):
        raw = str(2**255 + 123)
        rows = [{"quantity_raw": raw, "decimals": 18, "unit": "USDG raw", "sign": -1,
                 "reports_value_wad": raw, "economic_value_wad": "-" + raw,
                 "exact_value_wad": {"numerator": raw, "denominator": "3"},
                 "included_in_reports": False, "own_net_exposure": False},
                {"quantity_raw": "0", "economic_value_wad": "0", "unit": "USDG raw"},
                {"quantity_raw": None, "economic_value_wad": None, "unit": "USDG raw"}]
        economic_rows = [{"quantity_raw": raw, "sign": -1, "economic_value_wad": "-" + raw,
                          "indicative_reports_basis_wad": raw}]
        full = document({"sleeve": {"components": {"credit": {"rows": rows}}},
            "component_summary": {"credit": {"observed": {"rows": rows},
                "publisher": {"excluded_row_indices": [0], "contribution_wad": None},
                "economic": {"external_rows": economic_rows, "required_missing": ["Unpriced collateral"]}}},
            "adjusted_net_assets": {"value_wad": None, "unit": "USDG", "all_assets_exhaustive": False,
                "external_asset_ledger": {"credit": {"rows": economic_rows}}}})
        metrics = json.loads(output.summarize_rfv(full))["metrics"]
        retained = metrics["component_summary"]["credit"]["observed"]["rows"]
        self.assertEqual(retained[0]["quantity_raw"], raw)
        self.assertEqual(retained[0]["exact_value_wad"], {"numerator": raw, "denominator": "3"})
        self.assertEqual(retained[0]["economic_value_wad"], "-" + raw)
        self.assertEqual(retained[0]["unit"], "USDG raw")
        self.assertEqual(retained[1]["economic_value_wad"], "0")
        self.assertIsNone(retained[2]["economic_value_wad"])
        selected = metrics["component_summary"]["credit"]["economic"]["external_rows"]
        self.assertEqual(selected["indices"], [0])
        self.assertEqual(selected["summary_reference"], "/metrics/component_summary/credit/observed/rows")
        self.assertEqual(selected["field_aliases"]["indicative_reports_basis_wad"], "reports_value_wad")
        self.assertEqual(metrics["component_summary"]["credit"]["economic"]["required_missing"], ["Unpriced collateral"])
        self.assertIsNone(metrics["adjusted_net_assets"]["value_wad"])

    def test_interrupted_unpublished_amount_and_newer_rows_are_not_erased(self):
        observed = {"contract": "0x" + "11" * 20, "getter": "balanceOf", "status": "observed", "raw": "19", "unit": "USDG raw"}
        full = document({"core_rfv": {"reads": {"cash": observed}, "components": {}},
            "sleeve": {"components": {"wallet": {"rows": [{"quantity_raw": "19"}], "missing": ["No decimals yet"]}}},
            "component_summary": {"wallet": {"observed": {"rows": []}, "missing": ["Not started"]}}}, "partial")
        summary = json.loads(output.summarize_rfv(full))
        self.assertEqual(summary["metrics"]["core_rfv"]["reads"]["cash"]["raw"], "19")
        self.assertEqual(summary["metrics"]["sleeve"]["components"]["wallet"]["rows"][0]["quantity_raw"], "19")
        self.assertEqual(summary["metrics"]["sleeve"]["components"]["wallet"]["missing"], ["No decimals yet"])
        self.assertEqual(summary["output_detail"]["full_evidence"]["checkpoint_status"], "not_requested")

    def test_completed_requested_scope_still_discloses_supplemental_read_failure(self):
        full = document({"sleeve": {"reads": [
            {"contract": "token", "getter": "balanceOf", "result": "0"},
            {"contract": "claim", "getter": "convertToAssets", "result": None, "error": "Pruned"},
            {"contract": "token", "method": "eth_getCode", "has_code": False}],
            "components": {"credit": {"collection_complete": False, "missing": ["Unresolved debt"],
                                       "markets": {"unpriced": {"debt_raw": "7"}}}}}})
        summary = json.loads(output.summarize_rfv(full))
        sleeve = summary["metrics"]["sleeve"]
        self.assertEqual(sleeve["reads"]["unavailable_entries"][0]["error"], "Pruned")
        self.assertFalse(sleeve["reads"]["unavailable_entries"][1]["has_code"])
        self.assertEqual(sleeve["components"]["credit"]["markets"]["unpriced"]["debt_raw"], "7")
        self.assertEqual(sleeve["components"]["credit"]["missing"], ["Unresolved debt"])


class InterruptedProjection(unittest.TestCase):
    def test_projection_stop_keeps_actual_checkpoint_failure_document_not_pruned_tree(self):
        encode = output._encode

        def stop_at_summary_encoding(value):
            if "metrics" in value:
                raise core.StopRun("deadline_exhausted")
            return encode(value)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "evidence.json"
            fixture = Fixture("checkpoint-failure", path)
            stdout = io.StringIO()
            with patch.object(core, "_FixedHTTPSConnection", fixture.connection), \
                    patch.object(analytics, "_PROCESS_STARTED", time.monotonic()), \
                    patch.object(output, "_encode", side_effect=stop_at_summary_encoding), \
                    redirect_stdout(stdout):
                status = analytics.main(["rfv", "--detail", "summary", "--deadline", "8", "--output", str(path)])
            result = json.loads(stdout.getvalue())
            self.assertEqual(status, 2)
            self.assertEqual(result["stopping_reason"], "checkpoint_failure")
            self.assertEqual(result["status"], "partial")
            self.assertTrue(any(error.get("kind") == "output" for error in result["errors"]))
            self.assertEqual(result["metrics"]["core_rfv"]["assembled"]["rfv_wad"], str(298 * 10**18))
            self.assertIn("vault.convertToAssets", result["metrics"]["core_rfv"]["reads"])
            self.assertEqual(result["output_detail"]["mode"], "full")
            self.assertEqual(result["output_detail"]["projection_stopping_reason"], "deadline_exhausted")
            self.assertEqual(result["output_detail"]["full_evidence"]["checkpoint_status"], "not_confirmed")
            self.assertNotIn("output_detail", json.loads(Path(str(path) + ".before-failure").read_text()))


if __name__ == "__main__":
    unittest.main()

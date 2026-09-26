"""Presentation boundaries: missing evidence, exact units and finalization."""
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


class AdvanceSummary(unittest.TestCase):
    def full(self, metrics, status="completed", complete=True):
        value = json.loads(document(metrics, status))
        value["command"] = "advance"
        value["coverage"] = {"collection_complete": complete,
                             "requested_scope": {"scope": metrics.get("scope", {}).get("view", "capacity"),
                                                 "collection_complete": complete}}
        return core.serialize_result(value)

    def test_exact_token_units_preserve_large_integers_without_float_rounding(self):
        huge = "123456789012345678901234567890123456789"
        full = self.full({
            "tokens": {"usdg": {"decimals": 6}, "wsnet": {"decimals": 18},
                       "net": {"decimals": 9}, "snet": {"decimals": 3}},
            "capacity": {"capacity": 5538443, "maxAdvance": huge, "inventory": huge,
                         "inventoryNet": huge, "escrowed": 0, "treasuryOwed": 1, "halted": False},
            "params": {"MIN_LOCK_NET": 1, "MAX_ADVANCE_PER_POSITION": 5538443, "TERM": 2592000},
            "balances": [{"token_role": "snet", "raw": huge}]})
        summary = json.loads(output.summarize_advance(full))
        capacity = summary["metrics"]["capacity"]
        self.assertEqual(capacity["amounts"]["capacity"]["formatted"], "5.538443")
        self.assertEqual(capacity["amounts"]["maxAdvance"]["formatted"],
                         "123456789012345678901234567890123.456789")
        self.assertEqual(capacity["amounts"]["inventory"]["formatted"],
                         "123456789012345678901.234567890123456789")
        self.assertEqual(capacity["amounts"]["inventoryNet"]["formatted"],
                         "123456789012345678901234567890.123456789")
        self.assertEqual(capacity["amounts"]["escrowed"]["formatted"], "0.000000")
        self.assertEqual(capacity["amounts"]["treasuryOwed"]["formatted"], "0.000001")
        self.assertEqual(capacity["maxAdvance"], huge)
        self.assertFalse(capacity["halted"])
        self.assertIsNone(capacity["zap_halted"])
        self.assertEqual(summary["metrics"]["balances"][0]["formatted"],
                         "123456789012345678901234567890123456.789")
        self.assertEqual(summary["metrics"]["params"]["amounts"]["MIN_LOCK_NET"]["formatted"], "0.000000001")
        self.assertEqual(json.loads(full)["metrics"]["capacity"]["maxAdvance"], huge)
        self.assertNotIn("amounts", json.loads(full)["metrics"]["capacity"])

    def test_missing_decimals_never_borrow_another_token_scale_or_balance_default(self):
        summary = json.loads(output.summarize_advance(self.full({
            "tokens": {"usdg": {"decimals": None}, "net": {"decimals": 0}},
            "capacity": {"capacity": 5538443, "inventory": 1, "inventoryNet": 17,
                         "maxAdvance": None},
            "balances": [{"token_role": "snet", "raw": 1, "decimals": 18}]})))
        amounts = summary["metrics"]["capacity"]["amounts"]
        for name in ("capacity", "inventory", "maxAdvance"):
            self.assertIsNone(amounts[name]["formatted"])
        self.assertEqual(amounts["inventoryNet"]["formatted"], "17")
        self.assertIsNone(summary["metrics"]["balances"][0]["formatted"])

    def test_live_verification_requires_pinned_getter_not_code_or_runtime_metadata(self):
        code = {"contract": "desk", "getter": "eth_getCode", "status": "observed",
                "block": 10, "code_present": True}
        getter = {"contract": "desk", "getter": "halted", "status": "observed",
                  "context_reference": "/metrics/read_context", "value": False}
        for rows, context, observed in (
            ([code], {"block": 10}, False),
            ([getter], {"block": 11}, False),
            ([{**getter, "status": "unavailable", "value": None}], {"block": 10}, False),
            ([getter], {"block": 10}, True),
        ):
            with self.subTest(rows=rows, context=context):
                result = json.loads(output.summarize_advance(self.full({
                    "read_context": context, "read_provenance": rows})))
                self.assertIs(result["verification"]["live_state_observed"], observed)
                self.assertEqual(result["verification"]["analyzed_runtime_match"], "not_checked")
                self.assertEqual(result["verification"]["zap_halted"]["status"], "unknown")

    def test_partial_and_failed_reads_survive_even_when_requested_collection_completes(self):
        observed = {"contract": "desk", "getter": "capacity", "status": "observed",
                    "value": 31, "context_reference": "/metrics/read_context"}
        unpublished = {**observed, "getter": "treasuryOwed", "value": 7}
        failed = {**observed, "getter": "inventory", "status": "unavailable",
                  "value": None, "error_kind": "rpc"}
        for status, complete in (("partial", False), ("completed", False), ("completed", True)):
            with self.subTest(status=status, complete=complete):
                value = json.loads(self.full({
                    "scope": {"desk": "desk"}, "read_context": {"block": 10},
                    "capacity": {"capacity": 31, "inventory": None},
                    "supplemental_missing": [{"scope": "inventory", "reason": "RPC failed"}],
                    "read_provenance": [observed, unpublished, failed]}, status, complete))
                value["errors"] = [{"scope": "inventory", "error": "RPC failed", "required": False}]
                summary = json.loads(output.summarize_advance(core.serialize_result(value)))
                retained = summary["metrics"]["read_provenance"]
                self.assertIn(unpublished, retained)
                self.assertIn(failed, retained)
                self.assertEqual(observed in retained, not (status == "completed" and complete))
                self.assertEqual(summary["errors"], value["errors"])
                self.assertEqual(summary["coverage"], value["coverage"])
                self.assertEqual(summary["metrics"]["supplemental_missing"],
                                 value["metrics"]["supplemental_missing"])

    def test_noncapacity_scope_preserves_owner_destination_and_partial_subtotals(self):
        metrics = {
            "scope": {"view": "holders"},
            "positions": [{"owner": "owner", "destination": "different-destination",
                           "raw_position": {"closed": True, "owed": 1151, "paid": 1151},
                           "original_advance_usdg_raw": 1001, "repaid_usdg_raw": None,
                           "observed_repaid_event_subtotal_usdg_raw": 51,
                           "realized_profit_usdg_raw": None, "history_complete": False}],
            "holders": [{"owner": "owner", "ownership_scope": "Not necessarily destination",
                         "inventory_complete": False, "totals": {"paid_raw": None},
                         "observed_subtotals": {"paid_raw": 1151}}],
            "totals": {"inventory_complete": False, "totals": {"paid_raw": None}},
            "event_history": {"complete": False, "events": [{"event": "Repaid", "raw": {"usdg": 51}}]}}
        summary = json.loads(output.summarize_advance(self.full(metrics, "partial", False)))
        for key in ("positions", "holders", "totals", "event_history"):
            self.assertEqual(summary["metrics"][key], metrics[key])

    def test_offline_summary_output_checkpoint_retains_full_runtime_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "advance.json"
            stdout = io.StringIO()
            with patch.object(analytics, "_PROCESS_STARTED", time.monotonic()), redirect_stdout(stdout):
                status = analytics.main(["advance", "provenance", "--detail", "summary",
                                         "--output", str(path)])
            saved = json.loads(path.read_text())
            summary = json.loads(stdout.getvalue())
            self.assertEqual(status, 0)
            self.assertIn("method", saved["provenance"]["analysis"]["runtime_evidence"])
            self.assertNotIn("method", summary["provenance"]["analysis"]["runtime_evidence"])
            for role in ("desk", "zap"):
                for key in ("source_id", "source_url", "runtime_keccak256"):
                    self.assertEqual(summary["provenance"]["analysis"]["runtime_evidence"][role][key],
                                     saved["provenance"]["analysis"]["runtime_evidence"][role][key])
            self.assertFalse(summary["verification"]["live_state_observed"])
            self.assertNotIn("output_detail", saved)
            self.assertEqual(summary["output_detail"]["full_evidence"]["checkpoint_status"], "saved")


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

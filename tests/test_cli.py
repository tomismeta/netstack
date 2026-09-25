"""Real CLI lifecycle over synthetic raw JSON-RPC; no DNS or live network."""
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
FIXTURE = Path(__file__).resolve().with_name("cli_fixture.py")
BLOCK_HASH = "0x" + "bb" * 32


class AnalyticsCLI(unittest.TestCase):
    def invoke(self, scenario="success", *options, command="rfv"):
        args = (["predict", "--series", "2"] if command == "predict"
                else ["rfv", "--scope", "core"])
        process = subprocess.run(
            [sys.executable, "-I", "-B", str(FIXTURE), scenario,
             *args, "--deadline", "8", *options],
            capture_output=True, timeout=15,
        )
        self.assertEqual(process.stderr, b"", process.stderr.decode("utf-8", "replace"))
        return process, json.loads(process.stdout)

    def assert_confirmed(self, report):
        snapshot = report["snapshot"]
        self.assertEqual(snapshot["chain_id"], 4663)
        self.assertEqual(snapshot["requested_block"], "latest-2")
        self.assertEqual(snapshot["block_number"], 10)
        self.assertEqual(snapshot["block_hash"], BLOCK_HASH)
        self.assertEqual(snapshot["timestamp"], 25)
        self.assertEqual(snapshot["recheck_status"], "confirmed")

    def assert_independent_core(self, report):
        core = report["metrics"]["core_rfv"]
        # Expected results are not produced by the fixture or production math:
        # 100 cash + 98 haircut vault + 100 geometric half-owned POL = 298;
        # 10 NET total supply yields 29.8. External-asset basis excludes LP NET.
        self.assertEqual(core["assembled"]["rfv_wad"], "298000000000000000000")
        self.assertEqual(core["assembled"]["nav_wad"], "29800000000000000000")
        self.assertEqual(core["components"]["liquid_usdg"]["value_wad"], "100000000000000000000")
        self.assertEqual(core["components"]["morpho"]["value_wad"], "98000000000000000000")
        self.assertEqual(core["components"]["pol"]["value_wad"], "100000000000000000000")
        self.assertEqual(core["components"]["pol"]["look_through_memo"]["usdg"]["raw"], "50000000")
        self.assertFalse(core["components"]["pol"]["look_through_memo"]["additive"])
        self.assertEqual(core["external_asset_basis"]["value_wad"], "250000000000000000000")
        self.assertEqual(core["external_asset_basis"]["excluded_own_net_pol_raw"], "50000000000")
        self.assertEqual(core["denominator"]["raw"], "10000000000")

    def assert_missing_vault_keeps_evidence(self, report):
        core = report["metrics"]["core_rfv"]
        self.assertEqual(core["status"], "partial")
        self.assertIsNone(core["assembled"]["rfv_wad"])
        self.assertIsNone(core["assembled"]["nav_wad"])
        self.assertIsNone(core["components"]["morpho"]["assets_raw"])
        self.assertIsNone(core["components"]["morpho"]["value_wad"])
        self.assertIsNone(core["external_asset_basis"]["value_wad"])
        self.assertEqual(core["reported"]["rfv"]["raw"], "298000000000000000000")
        self.assertEqual(core["components"]["liquid_usdg"]["value_wad"], "100000000000000000000")
        self.assertEqual(core["components"]["pol"]["value_wad"], "100000000000000000000")
        self.assertEqual(core["reconciliation"]["rfv"]["status"], "unavailable")
        self.assertIsNone(core["reconciliation"]["rfv"]["delta_raw"])
        self.assertFalse(report["coverage"]["collection_complete"])
        self.assertTrue(any(row.get("scope") == "core_rfv:vault.convertToAssets"
                            for row in report["errors"]))

    def test_core_default_and_explicit_full_stdout_equal_atomic_output(self):
        for detail in ((), ("--detail", "full")):
            with self.subTest(detail=detail), tempfile.TemporaryDirectory() as directory:
                output = Path(directory).resolve() / "result.json"
                process, report = self.invoke("success", *detail, "--output", str(output))
                self.assertEqual(process.returncode, 0)
                self.assertEqual(output.read_bytes(), process.stdout)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
                self.assertEqual(list(output.parent.iterdir()), [output])
                self.assertEqual(report["status"], "completed")
                self.assertEqual(report["stopping_reason"], "completed_requested_collection")
                self.assert_confirmed(report)
                self.assert_independent_core(report)
                core = report["metrics"]["core_rfv"]
                self.assertEqual(core["status"], "reconciled")
                self.assertTrue(report["coverage"]["collection_complete"])
                self.assertEqual(report["errors"], [])
                self.assertEqual(core["reads"]["vault.convertToAssets"]["raw"], "100000000")
                self.assertEqual(core["reconciliation"]["rfv"]["delta_raw"], "0")

    def test_required_read_failure_retains_partial_values_and_confirms_header(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "partial.json"
            process, report = self.invoke("read-failure", "--output", str(output))
            self.assertEqual(process.returncode, 2)
            self.assertEqual(output.read_bytes(), process.stdout)
            self.assertEqual(report["status"], "partial")
            self.assertEqual(report["stopping_reason"], "incomplete_collection")
            self.assert_confirmed(report)
            self.assert_missing_vault_keeps_evidence(report)
            read = report["metrics"]["core_rfv"]["reads"]["vault.convertToAssets"]
            self.assertEqual(read["status"], "unavailable")
            self.assertIsNone(read["raw"])

    def test_reconciliation_mismatch_never_overwrites_independent_total(self):
        process, report = self.invoke("reconciliation-mismatch")
        self.assertEqual(process.returncode, 2)
        self.assert_confirmed(report)
        self.assert_independent_core(report)
        core = report["metrics"]["core_rfv"]
        self.assertEqual(core["reported"]["rfv"]["raw"], "297999999999999999999")
        self.assertEqual(core["reconciliation"]["rfv"]["delta_raw"], "-1")
        self.assertEqual(core["reconciliation"]["rfv"]["status"], "mismatch")
        self.assertEqual(core["status"], "partial")
        self.assertFalse(report["coverage"]["collection_complete"])

    def test_final_header_mismatch_or_unavailability_cannot_report_success(self):
        for scenario, recheck, confirmation, kind in (
                ("header-mismatch", "mismatch", "invalid", "integrity"),
                ("header-unavailable", "unconfirmed", "unconfirmed", "unavailable")):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                output = Path(directory).resolve() / "result.json"
                process, report = self.invoke(scenario, "--output", str(output))
                self.assertEqual(process.returncode, 2)
                self.assertEqual(output.read_bytes(), process.stdout)
                self.assertEqual(report["status"], "partial")
                self.assert_independent_core(report)
                self.assertEqual(report["snapshot"]["block_hash"], BLOCK_HASH)
                self.assertEqual(report["snapshot"]["recheck_status"], recheck)
                self.assertEqual(report["snapshot"]["confirmation"], confirmation)
                self.assertTrue(any(error.get("kind") == kind for error in report["errors"]))
                if scenario == "header-mismatch":
                    self.assertFalse(report["coverage"]["collection_complete"])
                    self.assertFalse(report["coverage"]["core_rfv"]["collection_complete"])

    def test_signal_and_real_deadline_stop_after_progress_without_more_retrieval(self):
        for scenario, reason in (("stop", "interrupted_by_SIGTERM"),
                                 ("deadline", "deadline_exhausted")):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                output = Path(directory).resolve() / "partial.json"
                process, report = self.invoke(scenario, "--output", str(output))
                self.assertEqual(process.returncode, 2)
                self.assertEqual(output.read_bytes(), process.stdout)
                self.assertEqual(report["status"], "partial")
                self.assertEqual(report["stopping_reason"], reason)
                self.assertEqual(report["snapshot"]["recheck_status"], "not_performed")
                self.assertEqual(report["snapshot"]["confirmation"], "unconfirmed")
                core = report["metrics"]["core_rfv"]
                self.assertEqual(core["reported"]["rfv"]["raw"], "298000000000000000000")
                self.assertEqual(core["components"]["liquid_usdg"]["value_wad"], "100000000000000000000")
                self.assertNotIn("pol", core["components"])
                self.assertFalse(report["coverage"]["collection_complete"])
                self.assertEqual(report["errors"], [])

    def test_checkpoint_failure_retains_stdout_and_last_successful_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "result.json"
            process, report = self.invoke("checkpoint-failure", "--output", str(output))
            self.assertEqual(process.returncode, 2)
            self.assertEqual(report["status"], "partial")
            self.assertEqual(report["stopping_reason"], "checkpoint_failure")
            self.assert_confirmed(report)
            self.assert_independent_core(report)
            self.assertTrue(any(error.get("kind") == "output" for error in report["errors"]))
            backup = output.with_name(output.name + ".before-failure")
            saved = json.loads(backup.read_bytes())
            self.assert_independent_core(saved)
            self.assertEqual(saved["snapshot"]["recheck_status"], "not_performed")
            self.assertEqual(saved["status"], "partial")
            self.assertTrue(output.is_dir())
            self.assertEqual(set(output.parent.iterdir()), {output, backup})

    def test_invalid_arguments_preserve_exit_one_and_sanitized_json(self):
        process, report = self.invoke("success", "--block", "private-secret")
        self.assertEqual(process.returncode, 1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["stopping_reason"], "invalid_arguments")
        self.assertEqual(report["metrics"], {})
        self.assertNotIn(b"private-secret", process.stdout)

    def test_selected_predict_uses_real_dispatch_and_only_requested_snapshot(self):
        process, report = self.invoke("predict", command="predict")
        self.assertEqual(process.returncode, 0)
        self.assert_confirmed(report)
        self.assertEqual(report["command"], "predict")
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["errors"], [])
        self.assertTrue(report["coverage"]["collection_complete"])
        self.assertEqual(report["coverage"]["history"]["status"], "not_requested")
        self.assertEqual(report["coverage"]["series_discovery"]["inspected_ids"], [2])
        self.assertEqual(set(report["metrics"]["series"]), {"2"})
        series = report["metrics"]["series"]["2"]
        self.assertIsNone(series["onchain_question_title"])
        self.assertEqual(series["raw"]["lastMarkWad"], "400000000000000000")
        self.assertEqual(report["metrics"]["desk_snapshot"]["markPrice"], "600000000000000000")
        self.assertEqual(series["state"]["publisher_interpretation"]["clock_state"], "last_call")
        self.assertFalse(series["state"]["observations"]["halted"])
        self.assertEqual(series["outcome_tokens"]["HIGHER"]["totalSupply"], "12000000000000000000")
        self.assertEqual(series["outcome_tokens"]["LOWER"]["symbol"], "LOWER")
        self.assertNotIn("activity", report["metrics"])

    def assert_summary_companion(self, summary, full):
        self.assertEqual(summary["output_detail"]["mode"], "summary")
        self.assertEqual(summary["output_detail"]["projection_version"], 1)
        for key in ("snapshot", "coverage", "not_proven", "errors", "status", "stopping_reason"):
            self.assertEqual(summary[key], full[key], key)
        self.assertNotIn("output_detail", full)
        self.assertEqual(summary["output_detail"]["full_evidence"]["checkpoint_status"], "saved")
        reads = summary["metrics"]["core_rfv"]["reads"]
        if full["status"] == "completed":
            self.assertEqual(reads["summary_omitted"], "successful_raw_reads")
            self.assertNotIn("treasury.rfv", reads)
            self.assertEqual(full["metrics"]["core_rfv"]["reads"]["treasury.rfv"]["raw"],
                             "298000000000000000000")
        else:
            self.assertEqual(reads, full["metrics"]["core_rfv"]["reads"])
        for key in ("assembled", "reported", "components", "reconciliation", "external_asset_basis"):
            if key in full["metrics"]["core_rfv"]:
                self.assertEqual(summary["metrics"]["core_rfv"][key], full["metrics"]["core_rfv"][key])

    def test_summary_stdout_keeps_same_collection_full_output(self):
        for scenario in ("success", "read-failure", "reconciliation-mismatch",
                         "header-mismatch", "header-unavailable", "stop", "deadline"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                output = Path(directory).resolve() / "evidence.json"
                process, summary = self.invoke(scenario, "--detail", "summary",
                                               "--output", str(output))
                self.assertEqual(process.returncode, 0 if scenario == "success" else 2)
                full = json.loads(output.read_bytes())
                self.assert_summary_companion(summary, full)
                if scenario == "success":
                    self.assert_independent_core(summary)
                    self.assert_confirmed(summary)
                elif scenario == "read-failure":
                    self.assert_missing_vault_keeps_evidence(summary)
                elif scenario in ("stop", "deadline"):
                    reason = "interrupted_by_SIGTERM" if scenario == "stop" else "deadline_exhausted"
                    self.assertEqual(summary["stopping_reason"], reason)
                    self.assertEqual(summary["metrics"]["core_rfv"]["components"]["liquid_usdg"]["value_wad"],
                                     "100000000000000000000")

    def test_summary_checkpoint_failure_preserves_accounting_and_error(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "evidence.json"
            process, report = self.invoke("checkpoint-failure", "--detail", "summary", "--output", str(output))
            self.assertEqual(process.returncode, 2)
            self.assertEqual(report["output_detail"]["mode"], "summary")
            self.assertEqual(report["stopping_reason"], "checkpoint_failure")
            self.assert_independent_core(report)
            self.assertTrue(any(error.get("kind") == "output" for error in report["errors"]))
            self.assertEqual(report["output_detail"]["full_evidence"]["checkpoint_status"], "not_confirmed")
            saved = json.loads(output.with_name(output.name + ".before-failure").read_bytes())
            self.assert_independent_core(saved)
            self.assertEqual(report["metrics"]["core_rfv"]["reads"], saved["metrics"]["core_rfv"]["reads"])


if __name__ == "__main__":
    unittest.main()

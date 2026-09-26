"""Synthetic Advance boundaries; no real holders, position IDs or balances."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import netstack_advance as advance
from netstack_core import RpcError, serialize_result


def address(number):
    return "0x" + format(number, "040x")


def event(name, identifier, values, index):
    return {"event": name, "values": {"id": identifier, **values},
            "blockNumber": 15, "blockHash": "0x" + "ab" * 32,
            "transactionHash": "0x" + format(index + 1, "064x"),
            "transactionIndex": index, "logIndex": index}


class SyntheticContext:
    def __init__(self):
        self.block, self.timestamp = 20, 500
        self.result = {"metrics": {}, "coverage": {}, "errors": [], "not_proven": []}
        self.routes = {role: {"address": address(number)} for number, role in enumerate(
            ("desk", "zap", "usdg", "wsnet", "snet", "net", "sleeve", "treasury"), 1)}
        self.routes["_route"] = {"interface": "assets/analytics/advance-interface.json",
                                  "scope": "Synthetic selected deployment"}
        self.values = {}
        self.position_reads = []
        self.scans = 0
        self.history_complete = True
        self.log_error = None
        self.positions = {
            7: {"owner": address(101), "destination": address(201), "openedAt": 100,
                "closed": True, "wsLocked": 0, "principalNet": 9001,
                "owed": 1151, "paid": 1151},
            900000: {"owner": address(102), "destination": address(202), "openedAt": 200,
                     "closed": False, "wsLocked": 2**100 + 3, "principalNet": 10001,
                     "owed": 2301, "paid": 3},
        }
        desk, zap = self.routes["desk"]["address"], self.routes["zap"]["address"]
        for target, bindings in ((desk, {"usdg": "usdg", "wsNet": "wsnet", "sNet": "snet",
                                        "house": "sleeve", "zap": "zap", "treasury": "treasury"}),
                                 (zap, {"desk": "desk", "house": "sleeve", "usdg": "usdg",
                                        "wsNet": "wsnet", "sNet": "snet", "net": "net"})):
            for method, role in bindings.items():
                self.values[(target, method, ())] = self.routes[role]["address"]
        for role, decimals in (("usdg", 6), ("wsnet", 18), ("snet", 9), ("net", 9)):
            for method, value in (("decimals", decimals), ("symbol", role), ("name", "Synthetic " + role)):
                self.values[(self.routes[role]["address"], method, ())] = value
        self.values[(self.routes["snet"]["address"], "index", ())] = 12345678901
        for method, value in (("ADVANCE_BPS", 4000), ("FEE_BPS", 1000), ("TREASURY_BPS", 500),
                              ("TERM", 400), ("MAX_ADVANCE_PER_POSITION", 9000), ("MIN_LOCK_NET", 1),
                              ("capacity", 401), ("maxAdvance", 399), ("halted", False),
                              ("unallocated", 700), ("escrowed", 15), ("inventory", 4),
                              ("inventoryNet", 8), ("lockedTotal", 2**100 + 3), ("treasuryOwed", 2),
                              ("positionCount", 2)):
            self.values[(desk, method, ())] = value
        self.values[(zap, "ZAP_CAP_USDG", ())] = 321
        for holder, usdg, wsnet in ((desk, 711, 2**100 + 7), (zap, 0, 0)):
            self.values[(self.routes["usdg"]["address"], "balanceOf", (holder,))] = usdg
            self.values[(self.routes["wsnet"]["address"], "balanceOf", (holder,))] = wsnet
        self.events = []
        for identifier, original in ((7, 1001), (900000, 2001)):
            position = self.positions[identifier]
            self.events.append(event("Opened", identifier, {
                "owner": position["owner"], "destination": position["destination"],
                "wsLocked": 99 if identifier == 7 else position["wsLocked"],
                "principalNet": position["principalNet"], "advance": original,
                "owed": position["owed"],
            }, len(self.events)))
            self.values[(desk, "advanceOf", (identifier,))] = original
            self.values[(desk, "unlockAt", (identifier,))] = position["openedAt"] + 400
        self.events.extend([
            event("Repaid", 7, {"payer": address(301), "usdg": 51}, 2),
            event("Closed", 7, {"wsTaken": 50, "usdgCovered": 1100, "wsReturned": 49}, 3),
            event("Repaid", 900000, {"payer": address(302), "usdg": 3}, 4),
        ])

    def check(self):
        pass

    def checkpoint(self):
        pass

    def code(self, target):
        return "0x6000"

    def deployment(self, record):
        return 10

    def call(self, target, abi, method, args=()):
        if method == "position":
            self.position_reads.append(args[0])
            value = self.positions[args[0]]
        else:
            value = self.values[(target, method, args)]
        if isinstance(value, RpcError):
            raise value
        return deepcopy(value)

    def logs(self, key, target, abi, names, start, end):
        self.scans += 1
        if self.log_error:
            raise self.log_error
        self.result["coverage"][key] = {"event_coverage_complete": self.history_complete,
                                        "requested_range": [start, end]}
        yield deepcopy(self.events)

    def run(self, view="totals"):
        with patch.object(advance, "resolve_routes", return_value=self.routes):
            advance.run(self, SimpleNamespace(view=view))
        return self.result["metrics"]


class AdvanceAccounting(unittest.TestCase):
    def test_full_checkpoint_formats_exact_units_without_filling_missing_decimals(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.routes["desk"]["address"], "capacity", ())] = 123456789012345678901
        ctx.values[(ctx.routes["wsnet"]["address"], "decimals", ())] = RpcError("Missing precision")
        ctx.run("capacity")
        ctx.result.update(command="advance", snapshot={"block_number": ctx.block})
        full = json.loads(serialize_result(ctx.result))
        amounts = full["metrics"]["capacity"]["amounts"]
        self.assertEqual(amounts["capacity"]["raw"], "123456789012345678901")
        self.assertEqual(amounts["capacity"]["formatted"], "123456789012345.678901")
        self.assertEqual(amounts["capacity"]["display"], "123456789012345.678901 USDG")
        self.assertEqual(amounts["lockedTotal"]["raw"], str(2**100 + 3))
        self.assertIsNone(amounts["lockedTotal"]["formatted"])
        self.assertIsNone(amounts["lockedTotal"]["display"])
        self.assertFalse(full["coverage"]["collection_complete"])

    def test_full_checkpoint_requires_getters_at_the_selected_block_for_observed_state(self):
        result = {"command": "advance", "snapshot": {"block_number": 20}, "metrics": {
            "read_context": {"block": 19}, "read_provenance": [
                {"contract": address(1), "getter": "capacity", "value": 100,
                 "status": "observed", "context_reference": "/metrics/read_context"}]}}
        self.assertFalse(json.loads(serialize_result(result))["verification"]["live_state_observed"])
        result["metrics"]["read_context"]["block"] = 20
        full = json.loads(serialize_result(result))
        self.assertTrue(full["verification"]["live_state_observed"])
        self.assertEqual(full["verification"]["analyzed_runtime_match"], "not_checked")
        self.assertIsNone(full["verification"]["zap_halted"]["value"])

    def test_required_dependency_gap_retains_rows_but_withholds_full_aggregates(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.routes["desk"]["address"], "house", ())] = RpcError("pruned dependency")
        result = ctx.run()
        self.assertEqual([row["position_id"] for row in result["positions"]], [7, 900000])
        self.assertTrue(all(value is None for value in result["totals"]["totals"].values()))
        self.assertFalse(ctx.result["coverage"]["requested_scope"]["collection_complete"])

    def test_sparse_ids_discovered_once_and_original_advance_not_owed_division(self):
        ctx = SyntheticContext()
        result = ctx.run()
        self.assertEqual(ctx.position_reads, [7, 900000])
        self.assertEqual(ctx.scans, 1)
        self.assertTrue(ctx.result["coverage"]["requested_scope"]["collection_complete"])
        total = result["totals"]["totals"]
        self.assertEqual(total["original_advance_usdg_raw"], 3002)
        self.assertEqual(total["ws_locked_raw"], 2**100 + 3)
        self.assertEqual(total["paid_raw"], 1154)
        self.assertEqual(total["repaid_event_usdg_raw"], 54)
        self.assertIsNone(result["totals"]["realized_profit_usdg_raw"])
        closed = result["positions"][0]
        self.assertEqual(closed["repaid_usdg_raw"], 51)
        self.assertEqual(closed["raw_position"]["paid"], 1151)
        self.assertEqual(closed["opening_ws_locked_raw"], 99)
        self.assertEqual(closed["raw_position"]["wsLocked"], 0)
        self.assertIsNone(closed["realized_profit_usdg_raw"])
        self.assertEqual(result["holders"][0]["owner"], address(101))
        self.assertNotEqual(result["holders"][0]["owner"], closed["destination"])

    def test_incomplete_history_preserves_observed_values_without_full_totals(self):
        ctx = SyntheticContext()
        ctx.history_complete = False
        result = ctx.run("holders")
        self.assertFalse(ctx.result["coverage"]["requested_scope"]["collection_complete"])
        self.assertIsNone(result["totals"]["totals"]["position_count"])
        self.assertEqual(result["totals"]["observed_subtotals"]["paid_raw"], 1154)
        self.assertIsNone(result["positions"][0]["repaid_usdg_raw"])
        self.assertEqual(result["positions"][0]["observed_repaid_event_subtotal_usdg_raw"], 51)
        self.assertIsNone(result["holders"][0]["totals"]["position_count"])

    def test_missing_history_is_unknown_not_empty_inventory(self):
        ctx = SyntheticContext()
        ctx.log_error = RpcError("History unavailable", kind="pruned")
        result = ctx.run()
        self.assertIsNone(result["totals"]["totals"]["position_count"])
        self.assertFalse(ctx.result["coverage"]["advance_positions"]["collection_complete"])

    def test_counter_mismatch_cannot_be_cured_by_empty_positions(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.routes["desk"]["address"], "positionCount", ())] = 3
        result = ctx.run()
        self.assertEqual(ctx.position_reads, [7, 900000])
        self.assertFalse(ctx.result["coverage"]["advance_positions"]["count_reconciled"])
        self.assertIsNone(result["totals"]["totals"]["original_advance_usdg_raw"])

    def test_failed_position_read_does_not_discard_other_positions(self):
        ctx = SyntheticContext()
        ctx.positions[7] = RpcError("Missing pinned state", kind="pruned")
        result = ctx.run()
        self.assertEqual([row["position_id"] for row in result["positions"]], [900000])
        self.assertEqual(result["totals"]["observed_subtotals"]["original_advance_usdg_raw"], 2001)
        self.assertIsNone(result["totals"]["totals"]["position_count"])

    def test_conflicting_advance_evidence_is_unknown_not_zero(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.routes["desk"]["address"], "advanceOf", (7,))] = 999
        result = ctx.run()
        self.assertIsNone(result["positions"][0]["original_advance_usdg_raw"])
        self.assertIsNone(result["totals"]["totals"]["original_advance_usdg_raw"])
        self.assertFalse(ctx.result["coverage"]["requested_scope"]["collection_complete"])

    def test_maturity_uses_live_term_and_distinguishes_observed_unlock(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.routes["desk"]["address"], "TERM", ())] = 401
        result = ctx.run("positions")
        row = result["positions"][0]
        self.assertEqual(row["estimated_unlock_at"], 501)
        self.assertFalse(row["estimated_term_elapsed"])
        self.assertEqual(row["unlock_at_getter"], 500)

    def test_missing_term_is_null_not_dated_default(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.routes["desk"]["address"], "TERM", ())] = RpcError("Unavailable", kind="revert")
        result = ctx.run("positions")
        self.assertIsNone(result["positions"][0]["estimated_unlock_at"])
        self.assertIsNone(result["positions"][0]["estimated_term_elapsed"])
        self.assertFalse(ctx.result["coverage"]["requested_scope"]["collection_complete"])

    def test_params_capacity_do_not_require_position_history(self):
        for view in ("params", "capacity"):
            with self.subTest(view=view):
                ctx = SyntheticContext()
                ctx.log_error = AssertionError("History not required for snapshot views")
                result = ctx.run(view)
                self.assertEqual(ctx.scans, 0)
                self.assertEqual(ctx.position_reads, [])
                self.assertTrue(ctx.result["coverage"]["requested_scope"]["collection_complete"])
                if view == "capacity":
                    self.assertEqual(result["capacity"]["capacity"], 401)
                    self.assertEqual(result["capacity"]["unallocated"], 700)
                    self.assertEqual(result["capacity"]["ZAP_CAP_USDG"], 321)
                    self.assertIsNone(result["capacity"]["zap_halted"])

    def test_identity_mismatch_is_fatal_and_unexpected_address_is_not_followed(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.routes["desk"]["address"], "usdg", ())] = address(999)
        with self.assertRaises(RpcError) as failure:
            ctx.run()
        self.assertEqual(failure.exception.kind, "integrity")
        self.assertEqual(ctx.position_reads, [])
        self.assertEqual(ctx.scans, 0)

    def test_supplemental_metadata_failure_does_not_erase_complete_capacity(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.routes["net"]["address"], "name", ())] = RpcError("Name unavailable", kind="revert")
        result = ctx.run("capacity")
        self.assertIsNone(result["tokens"]["net"]["name"])
        self.assertTrue(ctx.result["coverage"]["requested_scope"]["collection_complete"])
        self.assertTrue(result["supplemental_missing"])

    def test_missing_decimals_never_becomes_hardcoded_token_scale(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.routes["usdg"]["address"], "decimals", ())] = RpcError("Decimals unavailable", kind="revert")
        result = ctx.run("capacity")
        self.assertIsNone(result["tokens"]["usdg"]["decimals"])
        self.assertFalse(ctx.result["coverage"]["requested_scope"]["collection_complete"])
        self.assertEqual(result["capacity"]["capacity"], 401)

    def test_local_position_limit_does_not_claim_provider_complete_inventory(self):
        ctx = SyntheticContext()
        with patch.object(advance, "POSITION_LIMIT", 1):
            result = ctx.run()
        self.assertFalse(result["event_history"]["complete"])
        self.assertFalse(ctx.result["coverage"]["requested_scope"]["collection_complete"])
        self.assertIsNone(result["totals"]["totals"]["position_count"])

    def test_empty_inventory_requires_complete_history_and_zero_counter(self):
        ctx = SyntheticContext()
        ctx.events = []
        ctx.positions = {}
        ctx.values[(ctx.routes["desk"]["address"], "positionCount", ())] = 0
        result = ctx.run()
        self.assertTrue(ctx.result["coverage"]["requested_scope"]["collection_complete"])
        self.assertEqual(result["totals"]["totals"]["position_count"], 0)
        self.assertEqual(result["totals"]["totals"]["original_advance_usdg_raw"], 0)

    def test_duplicate_opened_events_do_not_establish_unique_original_advance(self):
        ctx = SyntheticContext()
        duplicate = deepcopy(ctx.events[0])
        duplicate["logIndex"] = 99
        ctx.events.append(duplicate)
        result = ctx.run()
        self.assertFalse(ctx.result["coverage"]["requested_scope"]["collection_complete"])
        self.assertEqual([row["position_id"] for row in result["positions"]], [900000])
        self.assertIsNone(result["totals"]["totals"]["original_advance_usdg_raw"])



if __name__ == "__main__":
    unittest.main()

"""Synthetic consumer boundaries only; no packaged live positions or RPC probes."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analytics
import netstack_netlong as netlong
from netstack_core import Context, RpcError, StopRun, ZERO, load_json, serialize_result


def address(number):
    return "0x" + format(number, "040x")


class SyntheticContext:
    def __init__(self):
        self.block, self.timestamp = 200, 1000
        self.result = {"command": "netlong", "snapshot": {"block_number": 200},
                       "metrics": {}, "coverage": {}, "errors": [], "not_proven": []}
        self.source = deepcopy(load_json("assets/analytics/netlong-interface.json"))
        self.source["models"] = [{"id": family, "family": family, "runtime_bytes": 2,
                                   "normalized_sha256": hashlib.sha256(bytes.fromhex("6000")).hexdigest(),
                                   "immutable_ranges": [], "source_id": "synthetic"}
                                  for family in ("oracle", "vault", "futures", "margin", "pot", "twap")]
        self.source["margin_libraries"] = []
        self.routes = {role: {"address": address(number)} for number, role in enumerate(
            ("oracle", "vault", "margin", "pot", "twap", "usdg", "known_future"), 1)}
        self.routes["_route"] = {"interface": "assets/analytics/netlong-interface.json",
                                    "futures_labels": [{"route": "known_future", "symbol": "NET"}]}
        self.future = self.routes["known_future"]["address"]
        self.token = address(100)
        self.trader = address(200)
        self.code_values = {}
        self.values = {}
        self.requests = []
        self.event_complete = True
        self.event_error = None
        self.position_error = None
        self.checkpoints = []
        vault, desk, pot = (self.routes[role]["address"] for role in ("vault", "margin", "pot"))
        for method, value in (("deskCount", 1), ("deskAt", self.future)):
            self.values[(vault, method, (0,) if method == "deskAt" else ())] = value
        self.values[(vault, "totalOiUsdWad", ())] = 12 * netlong.WAD
        self.values[(vault, "desks", (self.future,))] = {
            "registered": True, "skewShareBps": 1000, "oiUsdWad": 12 * netlong.WAD,
            "skewUsdWad": 8 * netlong.WAD, "lockedWs": 1}
        for method, value in (("vault", vault), ("oracle", self.routes["oracle"]["address"]),
                              ("oiLongUsdWad", 10 * netlong.WAD), ("oiShortUsdWad", 2 * netlong.WAD),
                              ("lastMark", {"priceWad": 3 * netlong.WAD, "observedAt": 990, "rung": 1})):
            self.values[(self.future, method, ())] = value
        self.values[(self.future, "positions", (self.trader,))] = {
            "sizeUsdWad": 10 * netlong.WAD, "entryPriceWad": 2 * netlong.WAD, "isLong": True}
        self.values[(self.future, "positions", (address(201),))] = {
            "sizeUsdWad": 2 * netlong.WAD, "entryPriceWad": 4 * netlong.WAD, "isLong": False}
        for method, role in (("pot", "pot"), ("marginOracle", "oracle"), ("twapSource", "twap"), ("usdg", "usdg")):
            self.values[(desk, method, ())] = self.routes[role]["address"]
        for method, role in (("desk", "margin"), ("usdg", "usdg")):
            self.values[(pot, method, ())] = self.routes[role]["address"]
        self.values[(self.routes["usdg"]["address"], "decimals", ())] = 6
        self.values[(desk, "tokenCount", ())] = 1
        self.values[(desk, "tokenAt", (0,))] = self.token
        self.values[(desk, "nextPositionId", ())] = 3
        self.values[(self.token, "symbol", ())] = "NET"
        self.values[(self.token, "decimals", ())] = 9
        self.values[(self.token, "balanceOf", (desk,))] = 11 * 10**9
        self.values[(desk, "listings", (self.token,))] = {
            "tokenDecimals": 9, "listed": False, "allowed": False, "probeOk": False,
            "measuredAt": 1, "notionalUsdWad": 18 * netlong.WAD,
            "capUsedWad": 30 * netlong.WAD, "totalShares": 500}
        self.values[(desk, "opensAllowed", (self.token,))] = {"ok": False, "reason": 1}
        self.values[(desk, "marks", (self.token,))] = {
            "twapPriceWad": 3 * netlong.WAD, "spotPriceWad": 2 * netlong.WAD, "twapLive": True}
        self.values[(desk, "positions", (1,))] = {
            "trader": self.trader, "token": self.token, "state": 2,
            "shares": 500, "notionalUsdWad": 18 * netlong.WAD}
        self.values[(desk, "positions", (2,))] = {"trader": ZERO, "token": ZERO}
        self.values[(desk, "unitsOf", (1,))] = 10 * 10**9
        self.values[(desk, "debtUsdg", (1,))] = 21 * 10**6
        self.values[(pot, "totalPrincipalUsdg", ())] = 20 * 10**6
        self.values[(pot, "totalDebtUsdg", ())] = 21 * 10**6

    def check(self):
        pass

    def checkpoint(self):
        self.checkpoints.append(deepcopy(self.result))

    def code(self, target, block=None):
        value = self.code_values.get(target, "0x6000")
        if isinstance(value, Exception):
            raise value
        return value

    def creation_block(self, target, record=None):
        return 100

    def call(self, target, abi, method, args=()):
        self.requests.append((target, method, args))
        value = self.values[(target, method, args)]
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)

    def logs(self, key, target, abi, names, start, end):
        if self.event_error:
            raise self.event_error
        self.result["coverage"][key] = {"event_coverage_complete": self.event_complete}
        yield [{"values": {"trader": self.trader}}, {"values": {"trader": address(201)}}]

    def run(self, product="all", market=None):
        with patch.object(netlong, "resolve_routes", return_value=self.routes), patch.object(netlong, "load_json", return_value=self.source):
            netlong.run(self, SimpleNamespace(product=product, market=market))
        return self.result


class NetLongBoundaries(unittest.TestCase):
    def test_empty_futures_history_uses_real_log_coverage_contract(self):
        ctx = Context("netlong", deadline=30)
        ctx.block = 200
        abi = load_json("assets/analytics/netlong-interface.json")["futures_abi"]
        try:
            with patch.object(ctx, "creation_block", return_value=100), patch.object(ctx, "_rpc", return_value=[]):
                identifiers, complete = netlong._discover_ids(
                    ctx, address(1), abi, "Filled", "trader", None, "fills")
            self.assertEqual(identifiers, [])
            self.assertTrue(complete)
            self.assertEqual(ctx.result["coverage"]["fills"]["covered_ranges"], [[100, 200]])
            self.assertEqual(ctx.result["coverage"]["fills"]["missing_ranges"], [])
            self.assertEqual(ctx.result["errors"], [])
        finally:
            ctx.close()

    def test_disjoint_accounting_uses_actual_units_debt_and_mark(self):
        result = SyntheticContext().run()
        self.assertTrue(result["coverage"]["collection_complete"])
        futures, margin = result["metrics"]["markets"]
        self.assertEqual(futures["entry_notional"]["gross"]["raw"], str(12 * netlong.WAD))
        self.assertEqual(futures["entry_notional"]["net"]["raw"], str(8 * netlong.WAD))
        self.assertEqual(futures["mark_notional"]["gross"]["raw"], str(165 * netlong.WAD // 10))
        self.assertEqual(futures["mark_notional"]["net"]["raw"], str(135 * netlong.WAD // 10))
        self.assertEqual(margin["entry_notional"]["raw"], str(18 * netlong.WAD))
        self.assertEqual(margin["debt"]["formatted"], "21.000000")
        self.assertEqual(margin["marked_token_exposure"]["raw"], str(20 * netlong.WAD))
        self.assertNotEqual(margin["token_units"]["raw"], margin["desk_token_custody"]["raw"])
        self.assertFalse(margin["opens_allowed"]["ok"])
        self.assertEqual(set(result["metrics"]["aggregates"]), {"futures", "margin"})
        self.assertNotIn("total_oi", result["metrics"])

    def test_symbol_ambiguity_and_address_selection(self):
        with self.assertRaisesRegex(RpcError, "ambiguous"):
            SyntheticContext().run(market="NET")
        ctx = SyntheticContext()
        result = ctx.run(market=ctx.token)
        self.assertEqual([row["address"] for row in result["metrics"]["markets"]], [ctx.token])
        self.assertEqual(len(result["metrics"]["discovered_markets"]), 2)

    def test_future_inventory_gap_never_becomes_mark_total(self):
        ctx = SyntheticContext()
        ctx.event_complete = False
        row = ctx.run("futures")["metrics"]["markets"][0]
        self.assertIsNone(row["mark_notional"])
        self.assertIsNotNone(row["entry_notional"])
        self.assertFalse(row["positions_complete"])
        self.assertFalse(ctx.result["coverage"]["collection_complete"])

    def test_stale_margin_price_retains_debt_without_inventing_exposure(self):
        ctx = SyntheticContext()
        desk = ctx.routes["margin"]["address"]
        ctx.values[(desk, "marks", (ctx.token,))]["twapLive"] = False
        row = ctx.run("margin")["metrics"]["markets"][0]
        self.assertEqual(row["debt"]["raw"], "21000000")
        self.assertIsNone(row["marked_token_exposure"]["raw"])
        self.assertFalse(row["collection_complete"])
        self.assertIsNone(row["observed_position_mark_subtotal"]["raw"])
        self.assertIsNone(ctx.result["metrics"]["aggregates"]["margin"]["marked_token_exposure"]["observed_subtotal"])

    def test_futures_vault_mismatches_revoke_complete_totals(self):
        for scope in ("desk", "vault"):
            with self.subTest(scope=scope):
                ctx = SyntheticContext()
                vault = ctx.routes["vault"]["address"]
                if scope == "desk":
                    ctx.values[(vault, "desks", (ctx.future,))]["oiUsdWad"] = 13 * netlong.WAD
                else:
                    ctx.values[(vault, "totalOiUsdWad", ())] = 13 * netlong.WAD
                result = ctx.run("futures")
                aggregate = result["metrics"]["aggregates"]["futures"]
                self.assertFalse(aggregate["collection_complete"])
                self.assertFalse(aggregate["entry_notional"]["collection_complete"])
                self.assertIsNone(aggregate["entry_notional"]["total"])
                self.assertEqual(aggregate["entry_notional"]["observed_subtotal"]["gross"]["raw"],
                                 str(12 * netlong.WAD))
                if scope == "vault":
                    self.assertFalse(result["metrics"]["vault_entry_reconciliation"]["matches"])

    def test_missing_futures_mark_never_becomes_observed_zero(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.future, "lastMark", ())] = RpcError("Unavailable mark", kind="unavailable")
        result = ctx.run("futures")
        aggregate = result["metrics"]["aggregates"]["futures"]
        self.assertIsNone(aggregate["mark_notional"]["total"])
        self.assertIsNone(aggregate["mark_notional"]["observed_subtotal"])
        self.assertEqual(aggregate["entry_notional"]["total"]["gross"]["raw"], str(12 * netlong.WAD))

    def test_runtime_mismatch_refuses_oi_getters(self):
        ctx = SyntheticContext()
        ctx.code_values[ctx.future] = "0x6001"
        row = ctx.run("futures")["metrics"]["markets"][0]
        self.assertEqual(row["status"], "unsupported")
        self.assertFalse(any(target == ctx.future for target, method, args in ctx.requests))
        self.assertIsNone(ctx.result["metrics"]["aggregates"]["futures"]["entry_notional"]["total"])
        self.assertIsNone(ctx.result["metrics"]["aggregates"]["futures"]["entry_notional"]["observed_subtotal"])

    def test_permission_denial_is_terminal_not_a_per_market_fallback(self):
        ctx = SyntheticContext()
        ctx.code_values[ctx.routes["oracle"]["address"]] = RpcError("Denied", kind="permission")
        with self.assertRaises(RpcError):
            ctx.run()
        self.assertEqual(ctx.requests, [])

    def test_position_bound_preserves_subtotals_but_not_totals(self):
        ctx = SyntheticContext()
        with patch.object(netlong, "POSITION_LIMIT", 1):
            row = ctx.run("margin")["metrics"]["markets"][0]
        self.assertEqual(row["observed_position_debt_subtotal"]["raw"], "21000000")
        self.assertIsNone(row["debt"]["raw"])
        self.assertEqual(ctx.result["coverage"]["margin_positions"]["missing_id_range"], [2, 2])

    def test_market_bound_and_duplicate_entries_are_partial(self):
        ctx = SyntheticContext()
        vault = ctx.routes["vault"]["address"]
        ctx.values[(vault, "deskCount", ())] = 2
        ctx.values[(vault, "deskAt", (1,))] = ctx.future
        result = ctx.run("futures")
        self.assertFalse(result["coverage"]["futures_discovery"]["collection_complete"])
        self.assertIsNone(result["metrics"]["aggregates"]["futures"]["entry_notional"]["total"])

    def test_new_token_uses_registry_not_a_symbol_allowlist(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.token, "symbol", ())] = "UNSEEN"
        result = ctx.run("margin", "UNSEEN")
        self.assertTrue(result["coverage"]["collection_complete"])
        self.assertEqual(result["metrics"]["markets"][0]["symbol"], "UNSEEN")

    def test_same_model_unknown_future_is_address_queryable(self):
        ctx = SyntheticContext()
        ctx.routes["_route"]["futures_labels"] = []
        result = ctx.run("futures", ctx.future)
        self.assertTrue(result["coverage"]["collection_complete"])
        self.assertIsNone(result["metrics"]["markets"][0]["symbol"])

    def test_zero_entry_price_is_missing_not_zero_exposure(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.future, "positions", (ctx.trader,))]["entryPriceWad"] = 0
        row = ctx.run("futures")["metrics"]["markets"][0]
        self.assertIsNone(row["mark_notional"])
        self.assertFalse(row["collection_complete"])

    def test_summary_projects_saved_document_and_exact_large_values(self):
        ctx = SyntheticContext()
        result = ctx.run("margin")
        result.update(status="partial", stopping_reason="deadline_exhausted")
        result["metrics"]["markets"][0]["debt"] = netlong.quantity(2**100 + 1, 6, "USDG")
        summary = json.loads(netlong.summarize(serialize_result(result), "saved"))
        self.assertEqual(summary["status"], "partial")
        self.assertNotIn("reads", summary["metrics"])
        self.assertEqual(summary["metrics"]["markets"][0]["debt"]["raw"], str(2**100 + 1))
        self.assertEqual(summary["presentation"]["full_checkpoint"], "saved")

    def test_template_rejects_inconsistent_embedded_dependency_words(self):
        ctx = SyntheticContext()
        ctx.result["metrics"]["implementation_checks"] = []
        word = bytes.fromhex("00" * 31 + "01")
        raw = b"\x7f" + word + b"\x7f" + word
        normalized = b"\x7f" + bytes(32) + b"\x7f" + bytes(32)
        model = {"id": "synthetic-template", "family": "futures", "runtime_bytes": len(raw),
                 "source_id": "synthetic", "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
                 "immutable_ranges": [[1, 32], [34, 32]],
                 "immutable_groups": [{"name": "vault", "offsets": [1, 34]}]}
        ctx.code_values[ctx.future] = "0x" + raw.hex()
        self.assertEqual(netlong._identity(ctx, ctx.future, [model], "futures")["id"], model["id"])
        ctx.code_values[ctx.future] = "0x" + (raw[:-1] + b"\x02").hex()
        with self.assertRaisesRegex(RpcError, "not a reviewed"):
            netlong._identity(ctx, ctx.future, [model], "futures")

    def test_pending_buy_is_not_counted_as_funded_debt_or_token_exposure(self):
        ctx = SyntheticContext()
        desk = ctx.routes["margin"]["address"]
        ctx.values[(desk, "positions", (1,))].update(state=1, shares=0, notionalUsdWad=0)
        ctx.values[(desk, "listings", (ctx.token,))].update(totalShares=0, notionalUsdWad=0)
        ctx.values[(desk, "unitsOf", (1,))] = 0
        ctx.values[(desk, "debtUsdg", (1,))] = 0
        row = ctx.run("margin")["metrics"]["markets"][0]
        self.assertEqual(row["debt"]["raw"], "0")
        self.assertEqual(row["marked_token_exposure"]["raw"], "0")

    def test_unknown_allocated_token_or_state_is_not_silently_ignored(self):
        for changed in ({"token": address(999)}, {"state": 4}):
            ctx = SyntheticContext()
            desk = ctx.routes["margin"]["address"]
            ctx.values[(desk, "positions", (1,))].update(changed)
            row = ctx.run("margin")["metrics"]["markets"][0]
            self.assertFalse(row["collection_complete"])
            self.assertIsNone(row["debt"]["raw"])

    def test_deadline_preserves_snapshot_without_promoting_incomplete_positions(self):
        ctx = SyntheticContext()
        desk = ctx.routes["margin"]["address"]
        ctx.values[(desk, "unitsOf", (1,))] = StopRun("deadline_exhausted")
        with self.assertRaises(StopRun):
            ctx.run("margin")
        row = ctx.result["metrics"]["markets"][0]
        self.assertEqual(row["entry_notional"]["raw"], str(18 * netlong.WAD))
        self.assertFalse(row["collection_complete"])
        self.assertFalse(ctx.result["coverage"]["collection_complete"])
        self.assertNotIn("debt", row)
        self.assertTrue(any(checkpoint["metrics"].get("markets", [{}])[0].get("entry_notional")
                            for checkpoint in ctx.checkpoints if checkpoint["metrics"].get("markets")))

    def test_failed_discovery_does_not_publish_an_empty_complete_aggregate(self):
        ctx = SyntheticContext()
        vault = ctx.routes["vault"]["address"]
        ctx.values[(vault, "totalOiUsdWad", ())] = RpcError("Unavailable", kind="unavailable")
        result = ctx.run("futures")
        self.assertFalse(result["coverage"]["futures_discovery"]["collection_complete"])
        self.assertIsNone(result["metrics"]["aggregates"]["futures"]["entry_notional"]["total"])

    def test_cli_and_exact_read_allowlist(self):
        args = analytics.parser().parse_args(["netlong", "--product", "margin", "--market", "NEW", "--detail", "summary"])
        self.assertEqual((args.command, args.product, args.market, args.detail), ("netlong", "margin", "NEW", "summary"))
        ctx = Context.__new__(Context)
        ctx.command, ctx._allowed = "netlong", None
        allowed = ctx._functions()
        self.assertIn("nextPositionId()", allowed)
        self.assertIn("positions(uint256)", allowed)
        self.assertIn("positions(address)", allowed)
        self.assertNotIn("open(address,uint256,uint256,uint256,uint64)", allowed)
        self.assertTrue(all(item["stateMutability"] in ("view", "pure") for item in allowed.values()))


if __name__ == "__main__":
    unittest.main()

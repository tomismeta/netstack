"""Consumer-visible accounting boundaries, independent of live balances."""
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

from unittest.mock import patch
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from netstack_core import RpcError, keccak256
from netstack_sleeve import (Collector, FAMILIES, WAD, Q128, MOD256, accrued_owed, accrued_market,
                            book_exposure, book_claim, debt_assets, feed_valid, predict_claims, settled)

A = "0x" + "11" * 20
B = "0x" + "22" * 20
C = "0x" + "33" * 20
D = "0x" + "44" * 20


class AccountingBoundaries(unittest.TestCase):
    def test_borrow_share_conversion_uses_virtual_shares_and_rounds_up(self):
        self.assertEqual(debt_assets(0, 100, 10**6), 0)
        self.assertEqual(debt_assets(1, 0, 0), 1)
        self.assertEqual(debt_assets(10**6, 100, 10**6), 51)

    def test_fee_accrual_uses_lower_inclusive_upper_exclusive_and_wraps(self):
        self.assertEqual(accrued_owed(1, 0, 0, 10, 100*Q128, 20*Q128, 30*Q128, 0, 7), (57, 50))
        self.assertEqual(accrued_owed(1, 10, 0, 10, 100*Q128, 20*Q128, 30*Q128, 0, 7), (17, 10))
        self.assertEqual(accrued_owed(1, 5, 0, 10, 5*Q128, 0, 0, MOD256-3*Q128, 0), (8, 8))

    def test_zero_liquidity_retains_owed_and_overflow_is_not_a_huge_fee(self):
        self.assertEqual(accrued_owed(0, 5, 0, 10, 0, 0, 0, 99, 123), (123, 0))
        with self.assertRaises(RpcError):
            accrued_owed(1, 5, 0, 10, Q128, 0, 0, 0, Q128-1)

    def test_feed_age_future_round_and_missing_are_not_current_zero(self):
        rd = {"roundId": 9, "answeredInRound": 9, "answer": 200000000, "updatedAt": 100}
        self.assertTrue(feed_valid(rd, 14500))
        self.assertFalse(feed_valid(rd, 14501))
        self.assertFalse(feed_valid(rd, 99))
        self.assertFalse(feed_valid(dict(rd, answer=0), 100))
        self.assertFalse(feed_valid(dict(rd, answeredInRound=8), 100))
        self.assertFalse(feed_valid(None, 100))

    def test_queue_maturity_uses_posted_state_not_notice_presence(self):
        self.assertFalse(settled(0, 3, False))
        self.assertFalse(settled(3, 3, True))
        self.assertTrue(settled(3, 3, False))
        self.assertTrue(settled(2, 3, True))
        self.assertIsNone(settled(3, None, False))

    def test_documented_heartbeat_boundary_does_not_extend_market_hours(self):
        rd = {"roundId": 1, "answeredInRound": 1, "answer": 100000000, "updatedAt": 100}
        self.assertTrue(feed_valid(rd, 86500, 86400))
        self.assertFalse(feed_valid(rd, 86501, 86400))
        self.assertFalse(feed_valid(rd, 200000, 86400))

    def test_morpho_accrual_compounds_before_debt_round_up_and_fee_dilution(self):
        market = {"totalSupplyAssets": 2000, "totalSupplyShares": 2_000_000_000,
                  "totalBorrowAssets": 1000, "totalBorrowShares": 1_000_000_000,
                  "lastUpdate": 100, "fee": WAD // 10}
        current, interest, fee_shares = accrued_market(market, WAD // 100, 110)
        self.assertEqual(interest, 105)
        self.assertEqual(current["totalBorrowAssets"], 1105)
        self.assertEqual(current["totalSupplyAssets"], 2105)
        self.assertEqual(fee_shares, 9_546_755)
        self.assertEqual(current["totalSupplyShares"], 2_009_546_755)
        self.assertEqual(debt_assets(1_000_000, 1105, 1_000_000_000), 2)
        self.assertEqual(debt_assets(1_000_000, 1000, 1_000_000_000), 1)
        self.assertEqual(accrued_market(market, 0, 110)[1:], (0, 0))
        with self.assertRaises(RpcError):
            accrued_market(market, 1, 99)

    def test_book_alternative_risk_and_open_grade_settle_void_claims(self):
        market = {"state": 1, "result": 0, "owedFav": 130, "owedDog": 80,
                  "wagersFav": 100, "wagersDog": 70, "indexAtGrade": 4}
        bet = {"settled": False, "riskOff": False, "amount": 10,
               "reserve": 0, "side": 0, "feeBps": 300, "index0": 3}
        self.assertEqual(book_exposure(market), 60)
        self.assertIsNone(book_claim(bet, market)["payable"])
        graded = dict(market, state=2)
        self.assertEqual(book_claim(bet, graded)["payable"], 20)
        self.assertEqual(book_claim(dict(bet, side=1), graded)["payable"], 0)
        self.assertEqual(book_claim(dict(bet, settled=True, payout=20), graded)["payable"], 0)
        self.assertEqual(book_claim(bet, dict(graded, result=2))["payable"], 10)
        self.assertEqual(book_claim(bet, dict(graded, state=3, result=2))["payable"], 10)
        risk_off = dict(bet, riskOff=True, amount=101, reserve=30, feeBps=500)
        self.assertEqual(book_claim(risk_off, graded)["payable"], 125)
        self.assertEqual(book_claim(dict(risk_off, side=1), graded)["payable"], 76)
        self.assertEqual(book_claim(risk_off, dict(graded, result=2))["payable"], 101)

    def test_predict_queue_conversion_and_notice_maturity_are_not_double_counted(self):
        pending, notice = {"series": 2, "usdg": 7}, {"series": 3, "shares": 2*WAD}
        active = predict_claims(30, 3*WAD, 10, pending, notice, 2, True, 1, None)
        self.assertEqual(active["unconverted_pending"], 7)
        self.assertEqual(active["matured_notice"], 0)
        converted = predict_claims(30, 3*WAD, 10, pending, notice, 2, False, 1, None)
        self.assertEqual(converted["unconverted_pending"], 0)
        matured = predict_claims(10, WAD, 10, pending, notice, 3, False, 1, 12)
        self.assertEqual(matured["matured_notice"], 24)
        self.assertEqual(matured["active_share_assets"] + matured["matured_notice"], 34)
        old_generation = predict_claims(0, 0, 10, pending, notice, 4, True, 4, 12)
        self.assertEqual(old_generation["matured_notice"], 24)
        with self.assertRaises(RpcError):
            predict_claims(31, 3*WAD, 10, pending, notice, 2, True, 1, None)


class SleeveLedger(unittest.TestCase):
    def collector(self):
        ctx = SimpleNamespace(block=1000, timestamp=1000,
                              result={"metrics": {}, "errors": [], "coverage": {}},
                              checkpoint=lambda: None)
        core = {"sleeve": A, "usdg": B, "net": C, "pair": D,
                "usdg_decimals": 6, "net_decimals": 9, "rfv_wad": 100*WAD,
                "external_assets_wad": 100*WAD, "core_complete": True}
        c = Collector(ctx, core)
        c.register(B, "test", symbol="USDG")["decimals"] = 6
        c.methodology.update(status="verified", v4_principal_included=False, fetched_this_run=True)
        c.methodology["selection_policy"] = {
            "v3": {"selection": "owner_enumeration", "fee": 500, "usdg": B,
                   "position_manager": c.address("position_manager"),
                   "assets": [{"token": D, "pool": D}]},
            "wallet": {"fixed_stock_tokens": []},
            "credit": {"market_ids": ["selected-market"], "vault": c.address("credit_vault")}}
        # Synthetic required claims start as observed zero balances; tests add exposure.
        c.families["credit"]["vault_claim_complete"] = True
        c.families["credit"]["stored_position_valuation_complete"] = {"selected-market": True}
        return c

    def test_missing_quantity_prevents_total_but_does_not_erase_cash(self):
        c = self.collector()
        cash = c.quantity("wallet", B, 7_000_000, "cash")
        c.quantity("wallet", C, None, "unavailable NET")
        c.finish("wallet", True)
        c.publish()
        self.assertEqual(cash["reports_value_wad"], str(7*WAD))
        self.assertIsNone(c.families["wallet"]["historical_reports_value_wad"])
        self.assertIsNone(c.ctx.result["metrics"]["reports_true_rfv"]["value_wad"])

    def test_native_zero_does_not_require_a_fabricated_price(self):
        c = self.collector()
        c.register(D, "unpriced")["decimals"] = 18
        zero = c.quantity("wallet", D, 0, "zero unpriced token")
        nonzero = c.quantity("wallet", D, 1, "positive unpriced token")
        self.assertEqual(zero["reports_value_wad"], "0")
        self.assertEqual(nonzero["quantity_raw"], "1")
        self.assertIsNone(nonzero["reports_value_wad"])

    def test_supplemental_fees_excluded_from_reports_but_in_external_ledger(self):
        c = self.collector()
        c.quantity("v3", B, 10_000_000, "principal", extra={"pool": D})
        c.quantity("v3", B, 2_000_000, "mixed owed", reports=False)
        for name in FAMILIES:
            c.finish(name, True)
        c.publish()
        result = c.ctx.result["metrics"]
        self.assertEqual(result["reports_true_rfv"]["value_wad"], str(110*WAD))
        self.assertEqual(result["adjusted_net_assets"]["external_asset_ledger"]["v3"]["known_rows_value_wad"], str(12*WAD))
        self.assertEqual(result["adjusted_net_assets"]["value_wad"], str(112*WAD))

    def test_stock_multiplier_is_applied_once_only_in_lp_turbo_convention(self):
        c = self.collector()
        c.register(D, "stock", feed=A)["decimals"] = 18
        c.tokens[D]["direct_token_feed"] = True
        def call(address, abi, name, args=()):
            return {"latestRoundData": {"roundId": 1, "answer": 200000000,
                    "startedAt": 900, "updatedAt": 900, "answeredInRound": 1},
                    "decimals": 8, "uiMultiplier": 15*10**17}[name]
        c.ctx.call = call
        c.ctx.calls = lambda specs: [call(address, abi, name, args) for address, abi, name, args in specs]
        self.assertEqual(c.mark(D), Fraction(2))
        self.assertEqual(c.mark(D, "lp"), Fraction(3))
        self.assertEqual(c.mark(D, "turbo"), Fraction(3))
        self.assertEqual(c.mark(D), Fraction(2))
        c.usdg_usd = Fraction(4, 5)
        row = c.quantity("v3", D, WAD, "one stock token", basis="lp")
        self.assertEqual(row["reports_value_wad"], str(3*WAD))
        self.assertEqual(row["economic_value_wad"], str(5*WAD//2))

    def test_supplemental_unknown_liability_blocks_net_not_reports(self):
        c = self.collector()
        c.quantity("turbo", B, 10_000_000, "put pot", extra={"asset_token": D})
        c.quantity("turbo", B, None, "unresolved liability", sign=-1, reports=False,
                   extra={"liability_basis": "unknown"})
        for name in FAMILIES:
            c.finish(name, True)
        c.publish()
        self.assertEqual(c.ctx.result["metrics"]["reports_true_rfv"]["value_wad"], str(110*WAD))
        self.assertIsNone(c.ctx.result["metrics"]["adjusted_net_assets"]["value_wad"])
        self.assertTrue(c.ctx.result["coverage"]["collection_complete"])
        c.scope = "net-assets"
        c.publish()
        self.assertFalse(c.ctx.result["coverage"]["collection_complete"])

    def test_own_net_is_not_external_backing_and_core_failure_blocks_both(self):
        c = self.collector()
        c.net_mark = Fraction(5)
        c.register(C, "NET")["decimals"] = 9
        c.quantity("wallet", C, 2*10**9, "own NET")
        c.quantity("wallet", B, 3*10**6, "cash")
        for name in FAMILIES:
            c.finish(name, True)
        c.publish()
        self.assertEqual(c.ctx.result["metrics"]["reports_true_rfv"]["value_wad"], str(113*WAD))
        self.assertEqual(c.ctx.result["metrics"]["adjusted_net_assets"]["value_wad"], str(103*WAD))
        c.core["core_complete"] = False
        c.publish()
        self.assertIsNone(c.ctx.result["metrics"]["reports_true_rfv"]["value_wad"])
        self.assertIsNone(c.ctx.result["metrics"]["adjusted_net_assets"]["value_wad"])

    def test_net_assets_uses_external_core_not_geometric_own_net_pol(self):
        c = self.collector()
        c.core["external_assets_wad"] = 80*WAD
        for name in FAMILIES:
            c.finish(name, True)
        c.publish()
        self.assertEqual(c.ctx.result["metrics"]["reports_true_rfv"]["value_wad"], str(100*WAD))
        self.assertEqual(c.ctx.result["metrics"]["adjusted_net_assets"]["value_wad"], str(80*WAD))
        c.core["external_assets_wad"] = None
        c.publish()
        self.assertIsNone(c.ctx.result["metrics"]["adjusted_net_assets"]["value_wad"])

    def test_stored_debt_is_not_added_again_to_accrued_debt(self):
        c = self.collector()
        c.quantity("credit", B, 2_000_000, "stored", sign=-1,
                   extra={"included_in_economic": False, "market_id": "selected-market"})
        c.quantity("credit", B, 3_000_000, "accrued", sign=-1, reports=False)
        c.quantity("predict", B, 5_000_000, "active shares")
        c.quantity("predict", B, 7_000_000, "pending", reports=False,
                   extra={"included_in_economic": True})
        for name in FAMILIES:
            c.finish(name, True)
        c.publish()
        self.assertEqual(c.ctx.result["metrics"]["reports_true_rfv"]["value_wad"], str(103*WAD))
        self.assertEqual(c.ctx.result["metrics"]["adjusted_net_assets"]["value_wad"], str(109*WAD))

    def valued_v4(self, c, extra_position=False, missing_fees=False, missing_mark=False):
        c.net_mark, c.index = None if missing_mark else Fraction(5), 2 * 10**9
        c.register(c.snet, "sNET")["decimals"] = 9
        c.register(c.wsnet, "wsNET")["decimals"] = 18
        positions = [{"position_id": 7, "pool_id": "0x" + "55" * 32,
                      "currency0": B, "currency1": c.wsnet,
                      "amount0_raw": 10_000_000, "amount1_raw": 2*WAD,
                      "fees0_raw": 1_000_000, "fees1_raw": WAD//2,
                      "read_provenance": []}]
        if missing_fees:
            positions[0].update(fees0_raw=None, fees1_raw=None)
        if extra_position:
            positions.append(dict(positions[0], position_id=8, amount0_raw=7_000_000,
                                  amount1_raw=0, fees0_raw=0, fees1_raw=0))
        inventory = {"position_manager": D, "owner": A, "expected_owned_count": len(positions),
                     "ownership_complete": True, "collection_complete": True, "missing": [],
                     "positions": positions,
                     "candidates": [{"position_id": p["position_id"], "owner": A} for p in positions],
                     "read_provenance": [{"contract": D, "getter": "ownerOf", "arguments": [7],
                                          "block": 1000, "value": A}]}
        c.methodology["v4_position_scope"] = {
            "selection": "publisher_registry_allowlist", "position_manager": D,
            "owner": A, "token_ids": ["7"]}
        with patch("netstack_sleeve.collect_v4", return_value=inventory):
            c.v4()
        for name in FAMILIES:
            c.finish(name, True)

    def test_v4_principal_inclusion_exclusion_and_unknown_keep_owned_exposure_visible(self):
        for inclusion, status, expected in ((True, "verified", 130),
                                            (False, "verified", 100),
                                            (None, "unsupported", None)):
            with self.subTest(inclusion=inclusion, status=status):
                c = self.collector()
                self.valued_v4(c)
                c.methodology.update(v4_principal_included=inclusion, status=status)
                c.publish()
                metrics = c.ctx.result["metrics"]
                self.assertEqual(metrics["reports_true_rfv"]["value_wad"],
                                 None if expected is None else str(expected*WAD))
                self.assertEqual(metrics["reports_historical_rfv"]["value_wad"], str(100*WAD))
                summary = metrics["component_summary"]["v4"]["details"]
                self.assertEqual(summary["principal"]["reports_value_wad"], str(30*WAD))
                self.assertEqual(summary["fees"]["reports_value_wad"], str(6*WAD))
                self.assertEqual(summary["principal"]["own_net_known_reports_mark_wad"], str(20*WAD))
                self.assertEqual(summary["ownership"]["expected_owned_count"], 1)
                self.assertEqual(summary["publisher_total_impact_wad"],
                                 None if inclusion is None else str(30*WAD if inclusion else 0))
                self.assertEqual(metrics["adjusted_net_assets"]["value_wad"], str(111*WAD))
                self.assertEqual(metrics["reports_true_rfv"]["publisher_headline_comparison"]["status"], "unavailable")
                c.publish()
                self.assertEqual(metrics["adjusted_net_assets"]["value_wad"], str(111*WAD))

    def test_publisher_registry_selects_principal_without_hiding_extra_owned_v4(self):
        c = self.collector()
        self.valued_v4(c, extra_position=True)
        c.methodology["v4_principal_included"] = True
        c.publish()
        metrics = c.ctx.result["metrics"]
        self.assertEqual(metrics["reports_true_rfv"]["value_wad"], str(130*WAD))
        self.assertEqual(metrics["component_summary"]["v4"]["details"]["principal"]["reports_value_wad"], str(37*WAD))
        self.assertEqual(metrics["component_summary"]["v4"]["details"]["owned_positions_outside_publisher_scope"], ["8"])
        self.assertEqual(metrics["adjusted_net_assets"]["value_wad"], str(118*WAD))
        self.assertEqual([r["included_in_reports"] for r in c.families["v4"]["rows"]],
                         [True, False, True, False, False, False, False, False])

    def test_stale_methodology_withholds_current_total_without_blocking_economic_scope(self):
        c = self.collector()
        self.valued_v4(c)
        c.methodology.update(v4_principal_included=True, fetched_this_run=False)
        c.publish()
        metrics = c.ctx.result["metrics"]
        self.assertIsNone(metrics["reports_true_rfv"]["value_wad"])
        self.assertFalse(metrics["reports_true_rfv"]["methodology_valid"])
        self.assertTrue(metrics["reports_true_rfv"]["pinned_collection_complete"])
        self.assertEqual(metrics["reports_historical_rfv"]["value_wad"], str(100*WAD))
        self.assertFalse(c.ctx.result["coverage"]["requested_scope"]["collection_complete"])
        c.scope = "net-assets"
        c.publish()
        self.assertEqual(metrics["adjusted_net_assets"]["value_wad"], str(111*WAD))
        self.assertTrue(c.ctx.result["coverage"]["requested_scope"]["collection_complete"])

    def test_missing_other_family_does_not_bury_valued_v4(self):
        c = self.collector()
        self.valued_v4(c)
        c.methodology["v4_principal_included"] = True
        c.quantity("credit", B, None, "Posted collateral", extra={"market_id": "selected-market"})
        c.finish("credit", False)
        c.publish()
        metrics = c.ctx.result["metrics"]
        self.assertIsNone(metrics["reports_true_rfv"]["value_wad"])
        self.assertEqual(metrics["component_summary"]["v4"]["publisher"]["contribution_wad"], str(30*WAD))
        self.assertEqual(metrics["component_summary"]["v4"]["details"]["fees"]["economic_external_value_wad"], str(WAD))

    def test_unpriced_v4_leg_retains_cash_and_withholds_only_current_publisher_total(self):
        c = self.collector()
        self.valued_v4(c, missing_mark=True)
        c.methodology["v4_principal_included"] = True
        c.publish()
        metrics = c.ctx.result["metrics"]
        self.assertIsNone(metrics["reports_true_rfv"]["value_wad"])
        self.assertEqual(metrics["reports_historical_rfv"]["value_wad"], str(100*WAD))
        self.assertIsNone(metrics["component_summary"]["v4"]["details"]["principal"]["reports_value_wad"])
        self.assertEqual(metrics["component_summary"]["v4"]["details"]["principal"]["known_priced_subtotal_wad"], str(10*WAD))
        self.assertEqual(metrics["adjusted_net_assets"]["value_wad"], str(111*WAD))

    def test_v4_fee_failure_does_not_invalidate_selected_principal_only_report(self):
        c = self.collector()
        self.valued_v4(c, missing_fees=True)
        c.methodology["v4_principal_included"] = True
        c.publish()
        metrics = c.ctx.result["metrics"]
        self.assertEqual(metrics["reports_true_rfv"]["value_wad"], str(130*WAD))
        self.assertIsNone(metrics["component_summary"]["v4"]["details"]["fees"]["reports_value_wad"])
        self.assertFalse(metrics["component_summary"]["v4"]["details"]["fees"]["quantity_collection_complete"])
        self.assertIsNone(metrics["adjusted_net_assets"]["value_wad"])

    def test_current_scope_excludes_other_v3_pools_and_discovered_credit_positions(self):
        c = self.collector()
        c.quantity("v3", B, 10_000_000, "selected principal", extra={"pool": D})
        extra_lp = c.quantity("v3", B, 7_000_000, "other pool", extra={"pool": A})
        c.quantity("credit", B, 3_000_000, "selected collateral", extra={"market_id": "selected-market"})
        extra_credit = c.quantity("credit", B, 5_000_000, "other collateral", extra={"market_id": "other-market"})
        for name in FAMILIES:
            c.finish(name, True)
        c.publish()
        metrics = c.ctx.result["metrics"]
        self.assertEqual(metrics["reports_true_rfv"]["value_wad"], str(113*WAD))
        self.assertEqual(metrics["reports_historical_rfv"]["value_wad"], str(125*WAD))
        self.assertEqual(metrics["adjusted_net_assets"]["value_wad"], str(125*WAD))
        self.assertFalse(extra_lp["included_in_reports"])
        self.assertFalse(extra_credit["included_in_reports"])

    def test_broader_credit_discovery_gap_does_not_invalidate_fixed_publisher_claims(self):
        c = self.collector()
        c.quantity("credit", B, 3_000_000, "selected collateral",
                   extra={"market_id": "selected-market"})
        for name in FAMILIES:
            c.finish(name, True)
        c.missing("credit", "Incoming position history unavailable after provider rate limit")
        c.finish("credit", False)
        c.publish()
        metrics = c.ctx.result["metrics"]
        self.assertEqual(metrics["reports_true_rfv"]["value_wad"], str(103*WAD))
        self.assertTrue(metrics["component_summary"]["credit"]["publisher"]["collection_complete"])
        self.assertFalse(metrics["component_summary"]["credit"]["observed"]["discovery_complete"])
        self.assertIsNone(metrics["adjusted_net_assets"]["value_wad"])
        self.assertIsNone(metrics["reports_historical_rfv"]["value_wad"])

    def test_current_publisher_requires_every_selected_credit_claim(self):
        for missing in ("vault", "selected-market", "new-required-market"):
            with self.subTest(missing=missing):
                c = self.collector()
                for name in FAMILIES:
                    c.finish(name, True)
                if missing == "vault":
                    c.families["credit"]["vault_claim_complete"] = False
                elif missing == "selected-market":
                    c.families["credit"]["stored_position_valuation_complete"][missing] = False
                else:
                    c.methodology["selection_policy"]["credit"]["market_ids"].append(missing)
                c.publish()
                self.assertIsNone(c.ctx.result["metrics"]["reports_true_rfv"]["value_wad"])
                self.assertFalse(c.ctx.result["metrics"]["component_summary"]["credit"]["publisher"]["collection_complete"])

    def test_component_summary_exposes_non_lp_contributions_exclusions_and_missing_marks(self):
        c = self.collector()
        c.net_mark = Fraction(5)
        c.register(C, "NET")["decimals"] = 9
        c.quantity("wallet", B, 7_000_000, "cash")
        c.quantity("wallet", C, 2*10**9, "own NET")
        c.quantity("credit", B, 3_000_000, "selected collateral",
                   extra={"market_id": "selected-market"})
        c.quantity("credit", B, 5_000_000, "other collateral",
                   extra={"market_id": "other-market"})
        c.quantity("predict", B, None, "unavailable active claim")
        for name in FAMILIES:
            c.finish(name, True)
        c.publish()
        metrics = c.ctx.result["metrics"]
        summaries = metrics["component_summary"]
        self.assertEqual(summaries["wallet"]["publisher"]["contribution_wad"], str(17*WAD))
        self.assertEqual(summaries["wallet"]["economic"]["known_rows_value_wad"], str(7*WAD))
        self.assertEqual(summaries["wallet"]["economic"]["excluded_own_net_rows"][0]["quantity_raw"], str(2*10**9))
        self.assertEqual(summaries["credit"]["publisher"]["contribution_wad"], str(3*WAD))
        excluded = summaries["credit"]["publisher"]["excluded_row_indices"]
        self.assertEqual([summaries["credit"]["observed"]["rows"][i]["quantity_raw"] for i in excluded],
                         ["5000000"])
        self.assertEqual(summaries["credit"]["economic"]["known_rows_value_wad"], str(8*WAD))
        self.assertIsNone(summaries["predict"]["publisher"]["contribution_wad"])
        self.assertFalse(summaries["predict"]["valuation"]["reports_basis_complete"])
        self.assertIsNone(summaries["predict"]["economic"]["known_rows_value_wad"])
        self.assertFalse(summaries["predict"]["economic"]["collection_complete"])
        self.assertEqual(summaries["core"]["publisher"]["contribution_wad"], str(100*WAD))
        self.assertEqual(summaries["core"]["economic"]["known_rows_value_wad"], str(100*WAD))
        self.assertIsNone(metrics["reports_true_rfv"]["value_wad"])
        self.assertIsNone(metrics["adjusted_net_assets"]["value_wad"])

    def test_methodology_error_retains_rpc_valuation_and_does_not_block_net_assets(self):
        c = self.collector()
        self.valued_v4(c)
        c.scope = "net-assets"
        c.methodology["v4_principal_included"] = True
        with patch("netstack_methodology.collect_reports_methodology", side_effect=RuntimeError("module failed")):
            c.check_methodology()
        c.publish()
        metrics = c.ctx.result["metrics"]
        self.assertEqual(metrics["reports_methodology"]["status"], "unavailable")
        self.assertIsNone(metrics["reports_true_rfv"]["value_wad"])
        self.assertEqual(metrics["component_summary"]["v4"]["details"]["principal"]["reports_value_wad"], str(30*WAD))
        self.assertEqual(metrics["adjusted_net_assets"]["value_wad"], str(111*WAD))
        self.assertTrue(c.ctx.result["coverage"]["requested_scope"]["collection_complete"])

    def test_methodology_permission_and_integrity_failures_remain_terminal(self):
        for kind in ("permission", "integrity"):
            c = self.collector()
            with patch("netstack_methodology.collect_reports_methodology",
                       side_effect=RpcError("Denied or invalid source", kind=kind)):
                with self.assertRaises(RpcError) as failure:
                    c.check_methodology()
            self.assertEqual(failure.exception.kind, kind)

    def test_morpho_pending_fee_shares_belong_only_to_fee_recipient(self):
        for recipient, expected in ((A, "1057"), (D, "1047"), (None, None)):
            c = self.collector()
            params = {"loanToken": B, "collateralToken": C, "oracle": D,
                      "irm": c.source["morpho_accrual_source"]["supported_irm"], "lltv": WAD // 2}
            encoded = b"".join(bytes.fromhex(params[n][2:]).rjust(32, b"\0")
                               for n in ("loanToken", "collateralToken", "oracle", "irm")) + params["lltv"].to_bytes(32, "big")
            mid = "0x" + keccak256(encoded).hex()
            market = {"totalSupplyAssets": 2000, "totalSupplyShares": 2_000_000_000,
                      "totalBorrowAssets": 1000, "totalBorrowShares": 1_000_000_000,
                      "lastUpdate": 900, "fee": WAD // 10}
            c.families["credit"]["markets"] = {}
            values = {"idToMarketParams": params, "market": market,
                      "position": {"supplyShares": 1_000_000_000, "borrowShares": 1_000_000, "collateral": 0},
                      "MORPHO": c.address("morpho"), "borrowRateView": WAD // 1000,
                      "feeRecipient": recipient, "decimals": 9}
            c.read = lambda address, abi, name, args=(): values[name]
            c.many = lambda specs: [c.read(*spec) for spec in specs]
            c.credit_ids([mid])
            rows = c.families["credit"]["rows"]
            self.assertEqual(next(r for r in rows if r["label"] == "Accrued direct Morpho supply claim")["quantity_raw"], expected)
            self.assertEqual(next(r for r in rows if r["label"] == "Accrued Morpho debt")["quantity_raw"], "2")

    def test_book_omitted_bets_require_full_nonnegative_stock_reconciliation(self):
        market = {"state": 2, "result": 0, "owedFav": 10, "owedDog": 4,
                  "wagersFav": 10, "wagersDog": 4, "indexAtGrade": 4}
        winning = {"marketId": 1, "settled": False, "riskOff": False, "amount": 10,
                   "reserve": 0, "side": 0, "feeBps": 300, "index0": 3}
        for omitted_principal in (0, 1):
            c = self.collector()
            f = c.families["book"]
            f.update(raw={"betCount": "129", "potsOf": {"0": "104", "1": "10", "2": "10", "3": str(omitted_principal)}},
                     markets={}, player_total_raw="100", accounting_code_matches=True)
            c.read = lambda address, abi, name, args=(): (
                market if name == "marketOf" else winning if args[0] == 129 else dict(winning, settled=True))
            c.book_markets(1)
            self.assertFalse(f["bet_history_exhaustive"])
            self.assertEqual(f["uninspected_bet_id_ranges"], [[1, 1]])
            self.assertEqual(f["obligations"]["collection_complete"], omitted_principal == 0)
            if omitted_principal:
                self.assertIsNone(f["obligations"]["decided_unsettled_payouts_raw"])
            else:
                self.assertEqual(f["obligations"]["decided_unsettled_payouts_raw"], "20")
                self.assertEqual(f["obligations"]["house_after_decided_settlement_raw"], "94")

    def test_permission_denial_is_terminal_not_optional_missing_balance(self):
        c = self.collector()
        def denied(*args):
            raise RpcError("Denied", kind="permission")
        c.ctx.call = denied
        with self.assertRaises(RpcError) as result:
            c.read(B, "token_abi", "balanceOf", (A,))
        self.assertEqual(result.exception.kind, "permission")


if __name__ == "__main__":
    unittest.main()

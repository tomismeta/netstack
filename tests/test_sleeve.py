"""Consumer-visible accounting boundaries, independent of live balances."""
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

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
        return c

    def test_missing_quantity_prevents_total_but_does_not_erase_cash(self):
        c = self.collector()
        cash = c.quantity("wallet", B, 7_000_000, "cash")
        c.quantity("wallet", C, None, "unavailable NET")
        c.finish("wallet", True)
        c.publish()
        self.assertEqual(cash["reports_value_wad"], str(7*WAD))
        self.assertIsNone(c.families["wallet"]["reports_value_wad"])
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
        c.quantity("v3", B, 10_000_000, "principal")
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
        c.quantity("turbo", B, 10_000_000, "put pot")
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
                   extra={"included_in_economic": False})
        c.quantity("credit", B, 3_000_000, "accrued", sign=-1, reports=False)
        c.quantity("predict", B, 5_000_000, "active shares")
        c.quantity("predict", B, 7_000_000, "pending", reports=False,
                   extra={"included_in_economic": True})
        for name in FAMILIES:
            c.finish(name, True)
        c.publish()
        self.assertEqual(c.ctx.result["metrics"]["reports_true_rfv"]["value_wad"], str(103*WAD))
        self.assertEqual(c.ctx.result["metrics"]["adjusted_net_assets"]["value_wad"], str(109*WAD))

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

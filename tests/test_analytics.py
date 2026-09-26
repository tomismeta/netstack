"""Accounting/security edge regressions; no network or installed-host dependency."""
import json
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from netstack_core import ZERO, RpcError, decode_event, load_json, topic, _decode_outputs, _encode_value
from netstack_lp import _Ledger
from netstack_markets import _Evidence, _classification, _discover, _settled

A = "0x" + "11" * 20
B = "0x" + "22" * 20
C = "0x" + "33" * 20
TOKEN = "0x" + "44" * 20
TX = "0x" + "aa" * 32
BLOCK_HASH = "0x" + "bb" * 32


def event(name, values, address=A, index=0, tx=TX):
    return {"event": name, "values": values, "address": address,
            "blockNumber": 10, "transactionIndex": 0, "logIndex": index,
            "transactionHash": tx, "blockHash": BLOCK_HASH}


def transfer(sender, recipient, quantity, index=0):
    return event("Transfer", {"from": sender, "to": recipient, "value": quantity}, index=index)


class LiquidityConservation(unittest.TestCase):
    def test_lock_zero_transfer_and_internal_burn_are_distinct(self):
        ledger = _Ledger()
        ledger.apply(transfer(ZERO, ZERO, 1000), "mint", 1000)
        ledger.apply(transfer(ZERO, A, 500, 1), "mint", 1000)
        ledger.apply(transfer(A, ZERO, 10, 2), "transfer", 1000)
        self.assertEqual(ledger.supply, 1500)
        self.assertEqual(ledger.balances[ZERO], 1010)
        ledger.apply(transfer(A, B, 20, 3), "transfer", 1000)
        ledger.apply(transfer(B, ZERO, 20, 4), "burn", 1000)
        self.assertEqual(ledger.supply, 1480)
        self.assertEqual(ledger.balances[ZERO], 1010)
        self.assertEqual(ledger.balances[A], 470)
        self.assertEqual(sum(ledger.balances.values()), ledger.supply)
        self.assertTrue(ledger.valid)

    def test_overspend_and_ambiguous_burn_invalidate_attribution(self):
        for kind in ("transfer", "ambiguous"):
            with self.subTest(kind=kind):
                ledger = _Ledger()
                ledger.apply(transfer(ZERO, A, 10), "mint", 1000)
                ledger.apply(transfer(A, B, 11, 1), kind, 1000)
                self.assertFalse(ledger.valid)


class MarketBoundaries(unittest.TestCase):
    def test_clock_boundaries_do_not_assert_trade_acceptance(self):
        raw = {"status": 1, "openTime": 10, "lastCallTime": 20,
               "closeTime": 30, "printTime": 40}
        for timestamp, expected in ((9, "scheduled"), (10, "trading_window"),
                                    (19, "trading_window"), (20, "last_call"),
                                    (29, "last_call"), (30, "closed_awaiting_settlement"),
                                    (40, "closed_awaiting_settlement"), (41, "closed_awaiting_settlement")):
            for halted in (False, True, None):
                with self.subTest(timestamp=timestamp, halted=halted):
                    state = _classification(raw, timestamp, halted)
                    observed, interpreted = state["observations"], state["publisher_interpretation"]
                    self.assertEqual(observed["raw_status"], 1)
                    self.assertIs(observed["halted"], halted)
                    self.assertEqual(observed["at_or_after_close_time"], timestamp >= 30)
                    self.assertEqual(observed["after_print_time"], timestamp > 40)
                    self.assertEqual(interpreted["clock_state"], expected)
                    self.assertEqual(interpreted["buy_acceptance"]["status"], "unverified")
                    self.assertEqual(interpreted["sell_acceptance"]["status"], "unverified")

    def test_unknown_enum_inconsistent_times_and_settlement_stay_distinct(self):
        raw = {"status": 255, "openTime": 10, "lastCallTime": 20,
               "closeTime": 30, "printTime": 40}
        unknown = _classification(raw, 15, False)
        self.assertEqual(unknown["observations"]["raw_status"], 255)
        self.assertEqual(unknown["publisher_interpretation"]["clock_state"], "unknown_enum")
        raw.update(status=1, lastCallTime=5)
        self.assertEqual(_classification(raw, 15, False)["publisher_interpretation"]["clock_state"], "contradictory_timestamps")
        self.assertEqual(_classification(raw, 30, False)["publisher_interpretation"]["clock_state"], "closed_awaiting_settlement")
        raw.update(lastCallTime=20)
        for status, label in ((0, "none"), (2, "resolved"), (3, "voided")):
            raw["status"] = status
            state = _classification(raw, 41, False)
            self.assertEqual(state["publisher_interpretation"]["clock_state"], label)
            self.assertEqual(state["observations"]["raw_status"], status)

    def test_selected_series_does_not_expand_into_unrelated_rows(self):
        raw = {"status": 1, "openTime": 10, "lastCallTime": 20,
               "closeTime": 30, "printTime": 40}
        def unavailable_older_series(address, abi, method, args, block=None):
            if args[0] != 2:
                raise RpcError("unrelated series unavailable")
            return dict(raw)
        ctx = SimpleNamespace(
            result={"metrics": {}, "coverage": {}, "errors": []}, timestamp=25,
            call=unavailable_older_series, checkpoint=lambda: None)
        rows = _discover(ctx, A, [], {"seriesCount": 100, "vault": B, "halted": False}, selected_id=2)
        self.assertEqual(set(rows), {2})
        self.assertEqual(set(ctx.result["metrics"]["series"]), {"2"})
        coverage = ctx.result["coverage"]["series_discovery"]
        self.assertTrue(coverage["discovery_complete"])
        self.assertEqual(coverage["missing_id_ranges"], [])
        self.assertEqual(ctx.result["errors"], [])
        with self.assertRaises(RpcError):
            _discover(ctx, A, [], {"seriesCount": 1}, selected_id=2)

    def test_queue_maturity_uses_accounting_state_not_wall_clock(self):
        live = {"seriesCount": 3, "live": True}
        self.assertTrue(_settled(2, live))
        self.assertFalse(_settled(3, live))
        self.assertFalse(_settled(4, live))
        self.assertTrue(_settled(3, {"seriesCount": 3, "live": False}))
        self.assertIsNone(_settled(3, {"seriesCount": 3}))


class CashReconciliation(unittest.TestCase):
    def ledger(self):
        ctx = SimpleNamespace(result={"metrics": {}, "coverage": {}})
        return _Evidence(ctx, A, B, TOKEN)

    def test_two_same_transaction_buys_cannot_reuse_one_transfer(self):
        ledger = self.ledger()
        ledger.extend([event("Bought", {"account": C, "usdgIn": 10}, index=1),
                       event("Bought", {"account": C, "usdgIn": 10}, index=2)])
        cash = event("Transfer", {"from": C, "to": A, "value": 10}, address=TOKEN, index=0)
        ledger.add_transfers([cash, cash])
        matching = ledger.matching()
        self.assertEqual(len(matching[3]), 1)
        self.assertEqual(matching[3][0]["event_amount_raw"], "20")
        self.assertEqual(matching[3][0]["transfer_amount_raw"], "10")
        ledger.add_transfers([event("Transfer", {"from": C, "to": A, "value": 10}, address=TOKEN, index=3)])
        matching = ledger.matching()
        self.assertEqual(matching[3], [])
        self.assertEqual(len(matching[2]), 1)

    def test_donation_is_not_forced_into_wager_receipts(self):
        ledger = self.ledger()
        ledger.extend([event("Bought", {"account": C, "usdgIn": 10}, index=1)])
        ledger.add_transfers([event("Transfer", {"from": C, "to": A, "value": 11}, address=TOKEN)])
        matching = ledger.matching()
        self.assertEqual(len(matching[3]), 1)
        self.assertEqual(matching[5][0]["value_raw"], "11")

    def test_unrelated_transaction_cannot_satisfy_matching_amount(self):
        ledger = self.ledger()
        ledger.extend([event("Bought", {"account": C, "usdgIn": 10})])
        ledger.add_transfers([event("Transfer", {"from": C, "to": A, "value": 10}, address=TOKEN, tx="0x" + "cc" * 32)])
        self.assertEqual(len(ledger.matching()[3]), 1)

    def reportable_ledger(self):
        ledger = self.ledger()
        ledger.ctx.block = 10
        ledger.ctx.result["metrics"] = {
            "desk_snapshot": {"usdg_balance_raw": "0"},
            "house_snapshot": {"usdg_balance_raw": "0"},
        }
        ledger.ctx.result["coverage"] = {
            "cash": {"event_coverage_complete": True},
            "events": {"event_coverage_complete": True},
            "series_discovery": {"discovery_complete": True},
        }
        ledger.cash_keys = ["cash"]
        ledger.event_keys = ["events"]
        ledger.starts = {"desk": 0, "house": 0}
        ledger.balances_before = {"desk": 0, "house": 0}
        return ledger

    def test_unmapped_series_outcome_never_gets_complete_grade(self):
        ledger = self.reportable_ledger()
        ledger.extend([event("Bought", {"account": C, "usdgIn": 10,
                                       "series": 2, "long": True, "tokensOut": 9})])
        ledger.publish(outcomes={})
        report = ledger.ctx.result["metrics"]["cash_reconciliation"]
        self.assertFalse(report["outcome_transfer_history_complete"])
        self.assertFalse(report["outcome_event_legs_matched"])
        self.assertEqual(report["unmapped_outcome_events"][0]["series"], 2)

    def test_zero_outcome_identity_without_trades_cannot_claim_complete_history(self):
        ledger = self.reportable_ledger()
        ledger.ctx.result["coverage"]["series_discovery"]["inspected_ids"] = [1]
        ledger.publish(outcomes={(1, True): ZERO, (1, False): ZERO})
        report = ledger.ctx.result["metrics"]["cash_reconciliation"]
        self.assertFalse(report["outcome_transfer_history_complete"])
        self.assertFalse(report["outcome_event_legs_matched"])
        self.assertEqual(
            {(row["series"], row["side"]) for row in report["unmapped_outcome_identities"]},
            {(1, "HIGHER"), (1, "LOWER")},
        )

    def test_unmatched_net_routing_blocks_desk_and_overall_cash_grade(self):
        ledger = self.reportable_ledger()
        ledger.extend([event("NetBought", {"usdgSpent": 10})])
        ledger.publish()
        report = ledger.ctx.result["metrics"]["cash_reconciliation"]
        self.assertFalse(report["event_cash_legs_matched"])
        self.assertFalse(report["accounts"]["desk"]["event_cash_legs_matched"])
        self.assertTrue(report["accounts"]["house"]["event_cash_legs_matched"])

    def test_calculated_nonzero_balance_residual_is_not_reconciled(self):
        ledger = self.reportable_ledger()
        ledger.ctx.result["metrics"]["desk_snapshot"]["usdg_balance_raw"] = "1"
        ledger.publish()
        report = ledger.ctx.result["metrics"]["cash_reconciliation"]["accounts"]["desk"]
        self.assertTrue(report["balance_comparison_performed"])
        self.assertEqual(report["balance_delta_residual_raw"], "1")
        self.assertFalse(report["balance_reconciliation_complete"])


class StrictEventDecoding(unittest.TestCase):
    def setUp(self):
        self.abi = load_json("assets/analytics/v2-interface.json")["pair_abi"]
        self.transfer_abi = next(item for item in self.abi if item.get("name") == "Transfer")

    def raw_log(self):
        return {"address": A, "topics": [topic(self.transfer_abi), "0x" + "00" * 32, "0x" + "00" * 12 + C[2:]],
                "data": "0x" + (2**255 + 123).to_bytes(32, "big").hex(),
                "blockNumber": "0xa", "transactionIndex": "0x0", "logIndex": "0x1",
                "transactionHash": TX, "blockHash": BLOCK_HASH, "removed": False}

    def test_ethereum_topic_and_uint256_precision(self):
        self.assertEqual(topic(self.transfer_abi), "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef")
        self.assertEqual(decode_event(self.raw_log(), self.abi)["values"]["value"], 2**255 + 123)

    def test_invalid_address_padding_and_truncated_word_rejected(self):
        for field in ("padding", "truncation"):
            with self.subTest(field=field):
                raw = self.raw_log()
                if field == "padding":
                    raw["topics"][2] = "0x01" + raw["topics"][2][4:]
                else:
                    raw["data"] = raw["data"][:-2]
                with self.assertRaises((RpcError, ValueError)):
                    decode_event(raw, self.abi)

    def test_false_boolean_encoding_is_not_coerced_to_true(self):
        abi = load_json("assets/analytics/predict-interface.json")["abi"]
        bought = next(item for item in abi if item.get("name") == "Bought")
        raw = self.raw_log()
        raw["topics"] = [topic(bought), "0x" + (1).to_bytes(32, "big").hex(), "0x" + "00" * 12 + C[2:]]
        raw["data"] = "0x" + "".join(n.to_bytes(32, "big").hex() for n in (2, 10, 1, 9, 0))
        with self.assertRaises((RpcError, ValueError)):
            decode_event(raw, abi)


class BoundedAssetMenus(unittest.TestCase):
    def decode(self, field, words):
        raw = "0x" + "".join(value.to_bytes(32, "big").hex() for value in words)
        return _decode_outputs({"outputs": [field]}, raw)

    def test_tuple_menu_preserves_address_and_signed_units(self):
        field = {"type": "tuple[]", "components": [
            {"name": "token", "type": "address"}, {"name": "adjustment", "type": "int24"}]}
        entries = self.decode(field, [32, 2, int(A, 16), (1 << 256) - 7, int(B, 16), 19])
        self.assertEqual(entries, [{"token": A, "adjustment": -7}, {"token": B, "adjustment": 19}])

    def test_empty_menu_differs_from_truncated_or_oversized_response(self):
        self.assertEqual(self.decode({"type": "address[]"}, [32, 0]), [])
        for words in ([32, 1], [32, 129], [64, 0], [32, 0, 0]):
            with self.subTest(words=words), self.assertRaises(RpcError):
                self.decode({"type": "address[]"}, words)

    def test_menu_rejects_noncanonical_token_address(self):
        with self.assertRaises(RpcError):
            self.decode({"type": "address[]"}, [32, 1, (1 << 160) + 1])

    def test_market_identifier_encoding_retains_leading_zeroes_and_exact_width(self):
        identifier = "0x" + "00" * 31 + "01"
        self.assertEqual(_encode_value({"type": "bytes32"}, identifier), bytes.fromhex(identifier[2:]))
        for invalid in ("0x01", identifier + "00"):
            with self.subTest(invalid=invalid), self.assertRaises(RpcError):
                _encode_value({"type": "bytes32"}, invalid)


class CollectorCLI(unittest.TestCase):
    def invoke(self, *args):
        script = Path(__file__).resolve().parents[1] / "scripts" / "analytics.py"
        return subprocess.run([sys.executable, "-I", "-B", str(script), *args],
                              capture_output=True, text=True, timeout=3)

    def test_expired_collection_returns_json_without_network_or_hanging(self):
        for command in ("lp", "predict", "house", "rfv", "advance"):
            with self.subTest(command=command):
                result = self.invoke(command, "--deadline", "0.01", "--json")
                self.assertEqual(result.returncode, 2, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["status"], "partial")
                self.assertEqual(report["stopping_reason"], "deadline_exhausted")
                self.assertEqual(report["metrics"], {})

    def test_custom_endpoint_and_inline_credentials_are_rejected_without_echo(self):
        private_url = "https://private-user:private-secret@127.0.0.1/"
        result = self.invoke("lp", "--rpc", private_url)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["stopping_reason"], "invalid_arguments")
        self.assertNotIn("private-secret", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

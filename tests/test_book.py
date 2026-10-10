"""Synthetic transport exercises the real Book CLI, Context and receipt decoder."""

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analytics
import netstack_book as book
from netstack_core import Context, RpcError, ZERO, TRANSFER_TOPIC, load_json, resolve_routes, serialize_result, topic


def word(value):
    return format(int(value) % (1 << 256), "064x")


def hash_value(value):
    return "0x" + word(value)


def encode(field, value):
    if field["type"] == "tuple":
        return "".join(encode(component, value[component["name"]]) for component in field["components"])
    if field["type"].startswith("bytes") or field["type"] == "address":
        return value[2:].rjust(64, "0")
    return word(value)


class Fixture:
    def __init__(self):
        self.routes = resolve_routes("book")
        self.source = load_json("assets/analytics/book-interface.json")
        self.evidence = deepcopy(load_json("assets/contracts/book-source-evidence.json"))
        for value in self.evidence["contracts"].values():
            value.update(runtime_bytes=2, runtime_sha256=hashlib.sha256(bytes.fromhex("6000")).hexdigest())
        self.selectors = {topic(item)[:10]: item for key in ("abi", "zap_abi", "token_abi")
                          for item in self.source[key] if item["type"] == "function"}
        self.market = {"favourite": hash_value(1), "underdog": hash_value(2), "spreadTenths": -35,
                       "openAt": 100, "closeAt": 1000, "state": 2, "result": 2,
                       "favScore": 0, "dogScore": 0, "owedFav": 10, "owedDog": 0,
                       "wagersFav": 10, "wagersDog": 0, "feesPot": 0, "feesSleeve": 0,
                       "indexAtGrade": 1100000000}
        self.bet = {"player": "0x" + "ab"*20, "marketId": 1, "side": 0, "riskOff": False,
                    "settled": False, "feeBps": 300, "placedAt": 500, "amount": 10,
                    "reserve": 2, "index0": 1000000000, "wager": 0, "payout": 0}
        self.state = {"marketCount": 1, "betCount": 1, "halted": False, "potsOf": [100, 20, 10, 30],
                      "freePot": 80, "playerTotal": 40, "manager": self.routes["sleeve"]["address"],
                      "grader": self.routes["sleeve"]["address"], "minBetWs": 1,
                      "maxBetBps": 500, "reserveRateBps": 90, "ZAP_CAP_USDG": 2500000000,
                      "exposureOf": 20}
        self.baseline = {"marketCount": 1, "betCount": 1}
        self.custody = 180
        self.logs, self.receipts, self.requests = [], {}, []
        self.fail_method = None
        self.fail_kind = "permission"
        self.runtime = "0x6000"

    def raw_log(self, address, index, topics, data, block=180):
        return {"address": address, "blockNumber": hex(block), "blockHash": hash_value(block+1000),
                "transactionHash": hash_value(900), "transactionIndex": "0x0", "logIndex": hex(index),
                "topics": topics, "data": data, "removed": False}

    def event(self, name, values, index):
        item = next(item for item in self.source["abi"] if item.get("name") == name)
        topics = [topic(item)] + ["0x"+encode(field, values[field["name"]]) for field in item["inputs"] if field["indexed"]]
        data = "0x" + "".join(encode(field, values[field["name"]]) for field in item["inputs"] if not field["indexed"])
        return self.raw_log(self.routes["desk"]["address"], index, topics, data)

    def add_fee_receipt(self):
        desk, sleeve = self.routes["desk"]["address"], self.routes["sleeve"]["address"]
        transfer = self.raw_log(self.routes["wsnet"]["address"], 0,
                               [TRANSFER_TOPIC, "0x"+desk[2:].rjust(64,"0"), "0x"+sleeve[2:].rjust(64,"0")], "0x"+word(3))
        event = self.event("FeeSplit", {"marketId": 1, "betId": 1, "potHalf": 2, "sleeveHalf": 3}, 1)
        self.logs = [event]
        self.receipts[event["transactionHash"]] = {"transactionHash": event["transactionHash"], "blockNumber": hex(180),
            "blockHash": hash_value(1180), "transactionIndex": "0x0", "status": "0x1", "from": self.bet["player"],
            "to": desk, "contractAddress": None, "logs": [transfer, event]}
        return event

    def exchange(self, ctx, requests):
        responses = []
        for method, params in requests:
            ctx._validate_payload(method, params)
            ctx._members += 1
            self.requests.append((method, params))
            if method == self.fail_method:
                responses.append(RpcError("Synthetic provider failure", kind=self.fail_kind))
                continue
            if method == "eth_chainId":
                value = hex(4663)
            elif method == "eth_getBlockByNumber":
                number = 202 if params[0] == "latest" else int(params[0], 16)
                value = {"number": hex(number), "hash": hash_value(number+1000), "timestamp": hex(number*100)}
            elif method == "eth_getCode":
                value = self.runtime
            elif method == "eth_call":
                item = self.selectors[params[0]["data"][:10]]
                name = item["name"]
                role = "desk" if params[0]["to"] == self.routes["desk"]["address"] else "zap"
                bindings = {(owner, getter): target for owner, getter, target in book.BINDINGS}
                if (role, name) in bindings:
                    output = self.routes[bindings[role, name]]["address"]
                elif name == "decimals":
                    output = 18
                elif name == "balanceOf":
                    output = self.custody
                elif name == "marketOf":
                    output = self.market
                elif name == "betOf":
                    output = self.bet
                elif name in self.baseline and int(params[1], 16) < 200:
                    output = self.baseline[name]
                else:
                    output = self.state[name]
                outputs = item["outputs"]
                values = [output] if len(outputs) == 1 else output
                value = "0x" + "".join(encode(field, entry) for field, entry in zip(outputs, values))
            elif method == "eth_getLogs":
                value = deepcopy(self.logs)
            elif method == "eth_getTransactionReceipt":
                value = deepcopy(self.receipts[params[0]])
            else:
                raise AssertionError("Unexpected synthetic method " + method)
            responses.append(value)
        return responses

    def patches(self):
        stack = ExitStack()
        original_load = book.load_json
        stack.enter_context(patch.object(book, "load_json", side_effect=lambda path:
            self.evidence if path == "assets/contracts/book-source-evidence.json" else original_load(path)))
        fixture = self
        stack.enter_context(patch.object(Context, "_exchange_once", lambda ctx, requests: fixture.exchange(ctx, requests)))
        return stack

    def run(self, **options):
        args = SimpleNamespace(market_ids=[], bet_ids=[], max_markets=8, max_bets=32, from_block=None)
        vars(args).update(options)
        with self.patches():
            ctx = Context("book", deadline=30)
            try:
                ctx.pin("200")
                book.run(ctx, args)
                ctx.recheck()
                return json.loads(serialize_result(ctx.result))
            finally:
                ctx.close()


def smoke(args=None, denial=False, scenario="snapshot"):
    fixture = Fixture()
    if scenario == "receipts":
        fixture.add_fee_receipt()
    elif scenario == "empty_inconsistent":
        fixture.baseline["betCount"] = 0
    if denial:
        fixture.fail_method = "eth_call"
    command = args or ["book", "--detail", "summary", "--deadline", "30"]
    if args is None and scenario != "snapshot":
        command += ["--from-block", "150"]
    with fixture.patches(), patch.object(analytics, "_PROCESS_STARTED", time.monotonic()):
        return analytics.main(command)


class BookTests(unittest.TestCase):
    def test_snapshot_distinguishes_custody_reserved_cover_and_claim(self):
        fixture = Fixture()
        result = fixture.run()
        accounting = result["metrics"]["state_accounting"]
        self.assertEqual(accounting["custody_minus_accounted_components"]["raw"], "0")
        self.assertEqual(accounting["reserved_cover"]["raw"], "20")
        self.assertEqual(result["metrics"]["bets"][0]["status"], "decided_unsettled")
        self.assertEqual(result["metrics"]["bets"][0]["publisher_unsettled_credit_model"]["raw"], "10")
        self.assertIsNone(result["metrics"]["bets"][0]["stored_settled_payout"])
        self.assertFalse(any(method == "eth_getLogs" for method, _ in fixture.requests))
        self.assertTrue(result["coverage"]["collection_complete"])

    def test_risk_off_principal_not_realized_wager_or_verified_liability(self):
        fixture = Fixture()
        fixture.bet["riskOff"] = True
        fixture.market["result"] = 0
        row = fixture.run()["metrics"]["bets"][0]
        self.assertEqual(row["amount_basis"], "risk_off_principal")
        self.assertIsNone(row["publisher_unsettled_credit_model"])
        self.assertIsNone(row["claimable_verified"])

    def test_settled_payout_is_internal_credit_not_new_cash(self):
        fixture = Fixture()
        fixture.bet.update(settled=True, wager=10, payout=20)
        row = fixture.run()["metrics"]["bets"][0]
        self.assertEqual(row["stored_settled_payout"]["raw"], "20")
        self.assertIsNone(row["publisher_unsettled_credit_model"])

    def test_empty_history_crosschecks_boundary_counters(self):
        fixture = Fixture()
        fixture.baseline["betCount"] = 0
        result = fixture.run(from_block=150)
        self.assertFalse(result["coverage"]["history_counter_reconciliation"]["complete"])
        self.assertIsNone(result["metrics"]["event_reported"]["requested_window_total"])
        self.assertFalse(result["coverage"]["collection_complete"])

    def test_empty_window_does_not_erase_existing_bets(self):
        result = Fixture().run(from_block=150)
        self.assertEqual(result["metrics"]["state"]["betCount"], 1)
        self.assertEqual(result["metrics"]["event_reported"]["requested_window_total"]["placements"], 0)
        self.assertIsNone(result["metrics"]["event_reported"]["lifetime_total"])
        self.assertIsNone(result["metrics"]["receipt_confirmed"]["all_book_outflows"])

    def test_receipts_preserve_odd_fee_split_and_recipient_scope(self):
        fixture = Fixture()
        fixture.add_fee_receipt()
        result = fixture.run(from_block=150)
        self.assertEqual(result["metrics"]["event_reported"]["observed_subtotal"]["house_fee_allocation"]["raw"], "2")
        self.assertEqual(result["metrics"]["receipt_confirmed"]["requested_event_transaction_total"]["sleeve"]["raw"], "3")
        self.assertEqual(result["metrics"]["receipt_confirmed"]["observed_subtotal"]["treasury"]["raw"], "0")
        self.assertTrue(result["metrics"]["receipts"][0]["sleeve_outflow_matches_allocations_plus_withdrawals"])

    def test_fee_allocation_without_transfer_is_not_confirmed_receipt(self):
        fixture = Fixture()
        event = fixture.add_fee_receipt()
        fixture.receipts[event["transactionHash"]]["logs"].pop(0)
        result = fixture.run(from_block=150)
        self.assertEqual(result["metrics"]["event_reported"]["observed_subtotal"]["sleeve_fee_allocation"]["raw"], "3")
        self.assertEqual(result["metrics"]["receipt_confirmed"]["observed_subtotal"]["sleeve"]["raw"], "0")
        self.assertIsNone(result["metrics"]["receipt_confirmed"]["requested_event_transaction_total"])
        self.assertFalse(result["coverage"]["collection_complete"])

    def test_receipt_missing_event_is_integrity_failure(self):
        fixture = Fixture()
        event = fixture.add_fee_receipt()
        fixture.receipts[event["transactionHash"]]["logs"].pop()
        with self.assertRaises(RpcError):
            fixture.run(from_block=150)

    def test_permission_stop_never_attempts_history_or_another_read(self):
        fixture = Fixture()
        fixture.fail_method = "eth_call"
        with self.assertRaises(RpcError):
            fixture.run(from_block=150)
        self.assertEqual(sum(method == "eth_call" for method, _ in fixture.requests), 1)
        self.assertFalse(any(method == "eth_getLogs" for method, _ in fixture.requests))

    def test_unknown_runtime_stops_before_semantic_reads(self):
        fixture = Fixture()
        fixture.runtime = "0x6001"
        with self.assertRaises(RpcError):
            fixture.run()
        self.assertFalse(any(method == "eth_call" for method, _ in fixture.requests))

    def test_bounded_selection_has_explicit_non_global_scope(self):
        fixture = Fixture()
        fixture.state["betCount"] = 100
        result = fixture.run(max_bets=2)
        self.assertEqual(result["coverage"]["id_discovery"]["selected_bet_ids"], [99, 100])
        self.assertFalse(result["coverage"]["id_discovery"]["all_bet_ids_selected"])
        self.assertIsNone(result["metrics"]["selected_bet_observations"]["all_unsettled_payout_liability"])

    def test_recheck_loss_withholds_totals_and_summary_retains_observations(self):
        fixture = Fixture()
        fixture.add_fee_receipt()
        result = fixture.run(from_block=150)
        result["snapshot"]["recheck_status"] = "unconfirmed"
        book.prepare_result(result)
        self.assertIsNone(result["metrics"]["receipt_confirmed"]["requested_event_transaction_total"])
        summary = json.loads(book.summarize(serialize_result(result), "partial"))
        self.assertEqual(summary["metrics"]["receipt_confirmed"]["observed_subtotal"]["sleeve"]["raw"], "3")
        self.assertNotIn("events", summary["metrics"])
    def test_large_raw_payout_survives_full_json_repreparation(self):
        fixture = Fixture()
        fixture.bet.update(settled=True, wager=10**18, payout=2*10**18)
        result = fixture.run()
        reparsed = json.loads(serialize_result(result))
        self.assertEqual(reparsed["metrics"]["selected_bet_observations"]["stored_settled_payout_subtotal"]["raw"], str(2*10**18))

    def test_receipt_reveals_omitted_scanned_event(self):
        fixture = Fixture()
        event = fixture.add_fee_receipt()
        omitted = fixture.event("HouseWithdrawn", {"to": fixture.routes["sleeve"]["address"], "amount": 1}, 2)
        fixture.receipts[event["transactionHash"]]["logs"].append(omitted)
        result = fixture.run(from_block=150)
        self.assertEqual(result["metrics"]["receipts"][0]["missing_scanned_event_log_indices"], [2])
        self.assertIsNone(result["metrics"]["event_reported"]["requested_window_total"])
        self.assertIsNone(result["metrics"]["receipt_confirmed"]["requested_event_transaction_total"])

    def test_missing_history_preserves_snapshot_without_zero_total(self):
        fixture = Fixture()
        fixture.fail_method, fixture.fail_kind = "eth_getLogs", "pruned"
        with fixture.patches():
            ctx = Context("book", deadline=30)
            try:
                ctx.pin("200")
                args = SimpleNamespace(market_ids=[], bet_ids=[], max_markets=8, max_bets=32, from_block=150)
                with self.assertRaises(RpcError):
                    book.run(ctx, args)
                result = json.loads(serialize_result(ctx.result))
                self.assertEqual(result["metrics"]["custody"]["raw"], "180")
                self.assertIsNone(result["metrics"]["event_reported"]["requested_window_total"])
                self.assertEqual(result["coverage"][book.EVENT_COVERAGE]["missing_ranges"], [[150, 200]])
            finally:
                ctx.close()

    def test_real_cli_summary_and_permission_failure(self):
        for scenario, denial, expected in (("snapshot", False, 0), ("receipts", False, 0),
                                          ("empty_inconsistent", False, 2), ("snapshot", True, 2)):
            output = io.StringIO()
            with redirect_stdout(output):
                status = smoke(denial=denial, scenario=scenario)
            result = json.loads(output.getvalue())
            self.assertEqual(status, expected)
            self.assertEqual(result["command"], "book")
            if not denial:
                self.assertEqual(result["snapshot"]["recheck_status"], "confirmed")


if __name__ == "__main__":
    unittest.main()

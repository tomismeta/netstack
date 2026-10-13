"""Synthetic PremiumSeller accounting; no live RPC, cached history or bytecode archive."""

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
import netstack_premiumseller as seller
from netstack_core import (Context, RpcError, StopRun, ZERO, TRANSFER_TOPIC,
                           decode_event, load_json, resolve_routes, serialize_result, topic)


def hash_value(value):
    return "0x" + format(value, "064x")


def word(value):
    return format(value, "064x")


class Fixture:
    """Transport-level synthetic responses exercise real Context logs/receipts."""
    def __init__(self):
        self.routes = deepcopy(resolve_routes("premiumseller"))
        self.source = deepcopy(load_json("assets/analytics/premiumseller-interface.json"))
        self.source["runtime_evidence"].update(runtime_bytes=2, runtime_sha256=hashlib.sha256(bytes.fromhex("6000")).hexdigest())
        self.creation_tx = hash_value(999)
        self.routes["seller"]["deployment_transaction_hash"] = self.creation_tx
        self.logs = []
        self.receipts = {}
        self.last_execute = 0
        self.fail_method = None
        self.failure = None
        self.requests = []
        self.runtime = "0x6000"
        self.sale_topic = next(topic(item) for item in self.source["abi"] if item.get("name") == "PremiumSold")
        self.values = {getter: self.routes[role]["address"] for getter, role in seller.BINDINGS}
        self.selectors = {topic(item)[:10]: item for key in ("abi", "token_abi") for item in self.source[key]
                          if item.get("type") == "function"}

    def raw_log(self, address, block, tx, index, topics, data):
        return {"address": address, "blockNumber": hex(block), "blockHash": hash_value(block + 1000),
                "transactionHash": tx, "transactionIndex": "0x0", "logIndex": hex(index),
                "topics": topics, "data": data, "removed": False}

    def transfer(self, token, source, target, value, block, tx, index):
        return self.raw_log(self.routes[token]["address"], block, tx, index,
                            [TRANSFER_TOPIC, "0x" + source[2:].rjust(64, "0"), "0x" + target[2:].rjust(64, "0")],
                            "0x" + word(value))

    def add_sale(self, block=180, net=10**9, usdg=2*10**6, *, tx=None, offset=0, tax=0,
                 remittance=None, unrelated=False, duplicate=False):
        tx = tx or hash_value(block)
        sale_address, treasury, pair = (self.routes[key]["address"] for key in ("seller", "treasury", "pair"))
        rows = []
        index = offset
        if unrelated:
            # Pre-existing cash donation to seller and unrelated Treasury flow.
            rows.append(self.transfer("usdg", ZERO, sale_address, 99*10**6, block, tx, index))
            rows.append(self.transfer("usdg", ZERO, treasury, 100*10**6, block, tx, index+1))
            index += 2
        rows.extend([self.transfer("net", ZERO, sale_address, net, block, tx, index),
                     self.transfer("net", sale_address, pair, net-tax, block, tx, index+1),
                     self.transfer("usdg", pair, sale_address, usdg, block, tx, index+2),
                     self.transfer("usdg", sale_address, treasury, usdg if remittance is None else remittance,
                                   block, tx, index+3)])
        event = self.raw_log(sale_address, block, tx, index+4, [self.sale_topic], "0x" + word(net) + word(usdg))
        rows.append(event)
        self.logs.append(event)
        if duplicate:
            self.logs.append(deepcopy(event))
        if tx in self.receipts:
            self.receipts[tx]["logs"].extend(rows)
        else:
            self.receipts[tx] = {"transactionHash": tx, "blockNumber": hex(block),
                                 "blockHash": hash_value(block+1000), "transactionIndex": "0x0",
                                 "status": "0x1", "from": ZERO, "to": sale_address,
                                 "contractAddress": None, "logs": rows}
        self.last_execute = max(self.last_execute, block*100)
        return event

    def exchange(self, ctx, requests):
        result = []
        for method, params in requests:
            ctx._validate_payload(method, params)
            ctx._members += 1
            self.requests.append((method, params))
            if method == self.fail_method:
                result.append(self.failure)
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
                if name == "decimals":
                    output = 9 if params[0]["to"] == self.routes["net"]["address"] else 6
                elif name == "lastExecuteAt":
                    output = self.last_execute
                else:
                    output = int(self.values[name], 16)
                value = "0x" + word(output)
            elif method == "eth_getLogs":
                query = params[0]
                value = [deepcopy(row) for row in self.logs if int(query["fromBlock"], 16) <= int(row["blockNumber"], 16) <= int(query["toBlock"], 16)]
            elif method == "eth_getTransactionReceipt":
                if params[0] == self.creation_tx:
                    value = {"transactionHash": self.creation_tx, "blockNumber": hex(100),
                             "blockHash": hash_value(1100), "transactionIndex": "0x0", "status": "0x1",
                             "from": ZERO, "to": None, "contractAddress": self.routes["seller"]["address"], "logs": []}
                else:
                    value = deepcopy(self.receipts[params[0]])
            else:
                raise AssertionError("Unexpected synthetic RPC method: " + method)
            result.append(value)
        return result

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(seller, "resolve_routes", return_value=self.routes))
        stack.enter_context(patch.object(seller, "load_json", return_value=self.source))
        fixture = self
        stack.enter_context(patch.object(Context, "_exchange_once", lambda ctx, requests: fixture.exchange(ctx, requests)))
        return stack

    def run(self, since_days=None, block=200, row_limit=None):
        with self.patches():
            ctx = Context("premiumseller", deadline=30)
            try:
                if row_limit is not None:
                    ctx._row_limit = row_limit
                ctx.pin(str(block))
                seller.run(ctx, SimpleNamespace(since_days=since_days))
                ctx.recheck()
                return json.loads(serialize_result(ctx.result))
            finally:
                ctx.close()


def smoke(args=None, denial=False, scenario="sale"):
    """Isolated real analytics.main entrypoint with in-memory transport only."""
    fixture = Fixture()
    if scenario == "sale":
        fixture.add_sale(unrelated=True, tax=50_000_000)
    elif scenario == "empty_inconsistent":
        fixture.last_execute = 18000
    elif scenario != "empty":
        raise ValueError("Unknown synthetic scenario")
    if denial:
        fixture.fail_method = "eth_getLogs"
        fixture.failure = RpcError("Synthetic permission denial", kind="permission")
    with fixture.patches(), patch.object(analytics, "_PROCESS_STARTED", time.monotonic()):
        return analytics.main(args or ["premiumseller", "--detail", "summary", "--deadline", "30"])


class PremiumSellerTests(unittest.TestCase):
    def test_receipt_logs_do_not_consume_scanned_sale_budget(self):
        fixture = Fixture()
        for block in (101, 102):
            event = fixture.add_sale(block=block, tx=hash_value(block + 10000))
            # Real receipts also contain router/pair/approval and other logs.
            # Validate them all without charging them as additional sales.
            fixture.receipts[event["transactionHash"]]["logs"].extend(
                fixture.raw_log(fixture.routes["router"]["address"], block,
                                event["transactionHash"], index, [], "0x")
                for index in range(5, 10))
        # Exercise the exact scan boundary without a timing-sensitive history benchmark.
        result = fixture.run(row_limit=2)
        self.assertEqual(result["resources"]["event_rows_accepted"], 2)
        self.assertEqual(result["resources"]["receipt_log_rows_validated"], 20)
        self.assertEqual(result["metrics"]["receipt_confirmed"]["lifetime_total"]["sale_count"], 2)
        self.assertEqual(result["coverage"][seller.SALE_COVERAGE]["missing_ranges"], [])

    def test_history_does_not_request_historical_contract_state(self):
        fixture = Fixture()
        fixture.add_sale()
        original = fixture.exchange
        def exchange(ctx, requests):
            for method, params in requests:
                if method in ("eth_call", "eth_getCode"):
                    self.assertEqual(params[-1], hex(200))
            return original(ctx, requests)
        with patch.object(fixture, "exchange", side_effect=exchange):
            result = fixture.run()
        self.assertTrue(result["coverage"]["collection_complete"])

    def test_last_execute_selector_matches_reviewed_uint64_getter(self):
        interface = load_json("assets/analytics/premiumseller-interface.json")
        getter = next(item for item in interface["abi"] if item.get("name") == "lastExecuteAt")
        self.assertEqual(topic(getter)[:10], "0x44120c56")
        self.assertEqual(getter["outputs"][0]["type"], "uint64")
        self.assertNotEqual(topic(getter)[:10], "0x65d962ca")

    def test_real_cli_row_stop_confirms_endpoint_but_keeps_partial_history(self):
        fixture = Fixture()
        fixture.add_sale()
        original = fixture.exchange
        def exchange(ctx, requests):
            if requests[0][0] == "eth_getLogs":
                ctx._row_limit = 0
            return original(ctx, requests)
        stream = io.StringIO()
        with patch.object(fixture, "exchange", side_effect=exchange), fixture.patches(), \
                redirect_stdout(stream), patch.object(analytics, "_PROCESS_STARTED", time.monotonic()):
            code = analytics.main(["premiumseller", "--detail", "summary", "--deadline", "30"])
        result = json.loads(stream.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["stopping_reason"], "event_row_limit")
        self.assertEqual(result["snapshot"]["recheck_status"], "confirmed")
        self.assertEqual(result["coverage"][seller.SALE_COVERAGE]["status"], "partial")
        self.assertEqual(result["coverage"][seller.SALE_COVERAGE]["missing_ranges"], [[100, 200]])
        self.assertIsNone(result["metrics"]["event_reported"]["lifetime_total"])

    def test_units_vwap_tax_and_unrelated_cash_are_disjoint(self):
        fixture = Fixture()
        fixture.add_sale(block=120, net=10**9, usdg=2*10**6, unrelated=True, tax=50_000_000, duplicate=True)
        fixture.add_sale(block=180, net=3*10**9, usdg=12*10**6)
        result = fixture.run()
        totals = result["metrics"]["event_reported"]["lifetime_total"]
        self.assertEqual(totals["sale_count"], 2)
        self.assertEqual(totals["gross_net_sold"]["formatted"], "4.000000000")
        self.assertEqual(totals["event_proceeds"]["formatted"], "14.000000")
        self.assertEqual(totals["weighted_realized_price_usdg_per_gross_net"], {"numerator": "7", "denominator": "2"})
        self.assertEqual(totals["realized_price_range_usdg_per_gross_net"],
                         {"min": {"numerator": "2", "denominator": "1"}, "max": {"numerator": "4", "denominator": "1"}})
        self.assertEqual(result["metrics"]["receipt_confirmed"]["lifetime_total"]["usdg_to_treasury"]["formatted"], "14.000000")
        first = result["metrics"]["sales"][0]
        self.assertEqual(first["pool_net_transfer"]["formatted"], "0.950000000")
        self.assertTrue(first["pair_output_matches_event"])
        self.assertEqual(sum(method == "eth_getTransactionReceipt" for method, _ in fixture.requests), 3)

    def test_multiple_sales_one_tx_partition_without_double_counting_but_reject_invariant(self):
        fixture = Fixture()
        first = fixture.add_sale(usdg=2_000_000)
        fixture.add_sale(usdg=5_000_000, tx=first["transactionHash"], offset=5)
        result = fixture.run()
        self.assertEqual(result["metrics"]["event_reported"]["observed_subtotal"]["event_proceeds"]["raw"], "7000000")
        self.assertIsNone(result["metrics"]["event_reported"]["lifetime_total"])
        self.assertIsNone(result["metrics"]["receipt_confirmed"]["lifetime_total"])
        self.assertEqual([row["remittance_candidates"][0]["amount"]["raw"] for row in result["metrics"]["sales"]], ["2000000", "5000000"])
        self.assertTrue(all(row["receipt_status"] == "impossible_multiple_sales" for row in result["metrics"]["sales"]))
        self.assertEqual(len(result["metrics"]["receipts"]), 1)

    def test_mismatch_and_ambiguous_segment_do_not_confirm_delivery(self):
        for ambiguous in (False, True):
            with self.subTest(ambiguous=ambiguous):
                fixture = Fixture()
                event = fixture.add_sale(remittance=1 if not ambiguous else None, offset=1)
                if ambiguous:
                    fixture.receipts[event["transactionHash"]]["logs"].insert(0, fixture.transfer(
                        "usdg", fixture.routes["seller"]["address"], fixture.routes["treasury"]["address"],
                        123, 180, event["transactionHash"], 0))
                result = fixture.run()
                self.assertIsNone(result["metrics"]["receipt_confirmed"]["lifetime_total"])
                self.assertEqual(result["metrics"]["receipt_confirmed"]["observed_subtotal"]["usdg_to_treasury"]["raw"], "0")
                self.assertEqual(result["metrics"]["sales"][0]["receipt_status"],
                                 "ambiguous_remittance_segment" if ambiguous else "mismatched_remittance")

    def test_receipt_exposes_missing_scanned_event(self):
        fixture = Fixture()
        event = fixture.add_sale()
        fixture.add_sale(tx=event["transactionHash"], offset=5)
        fixture.logs.pop()
        result = fixture.run()
        self.assertEqual(result["metrics"]["receipts"][0]["missing_scanned_sale_log_indices"], [9])
        self.assertIsNone(result["metrics"]["event_reported"]["lifetime_total"])

    def test_real_context_empty_proven_history_is_zero_not_inactive(self):
        result = Fixture().run()
        scan = result["coverage"][seller.SALE_COVERAGE]
        self.assertEqual(scan["requested_range"], [100, 200])
        self.assertEqual(scan["covered_ranges"], [[100, 200]])
        self.assertEqual(scan["missing_ranges"], [])
        self.assertIn("silently omit", scan["provider_completeness_assumption"])
        self.assertTrue(result["coverage"]["collection_complete"])
        self.assertEqual(result["metrics"]["event_reported"]["lifetime_total"]["sale_count"], 0)
        self.assertNotIn("active", result["metrics"])

    def test_empty_or_nonempty_history_omitting_latest_conflicts_with_state(self):
        for older_sale in (False, True):
            fixture = Fixture()
            if older_sale:
                fixture.add_sale(block=120)
            fixture.last_execute = 18000
            result = fixture.run()
            self.assertFalse(result["coverage"]["last_execution_reconciliation"]["collection_complete"])
            self.assertIsNone(result["metrics"]["event_reported"]["requested_window_total"])
            self.assertIsNone(result["metrics"]["receipt_confirmed"]["lifetime_total"])
            self.assertEqual(result["metrics"]["event_reported"]["observed_subtotal"]["sale_count"], int(older_sale))

    def test_last_execution_before_since_window_allows_scoped_zero_only(self):
        fixture = Fixture()
        fixture.add_sale(block=120)
        result = fixture.run(since_days=0.01)
        self.assertEqual(result["coverage"]["history"]["requested_range"], [192, 200])
        self.assertEqual(result["coverage"]["last_execution_reconciliation"]["status"], "last_execution_before_requested_window")
        self.assertEqual(result["metrics"]["event_reported"]["requested_window_total"]["sale_count"], 0)
        self.assertIsNone(result["metrics"]["event_reported"]["lifetime_total"])

    def test_since_window_includes_all_blocks_at_cutoff_second(self):
        fixture = Fixture()
        fixture.add_sale(block=191)
        fixture.last_execute = 19136
        original = fixture.exchange

        def exchange(ctx, requests):
            responses = original(ctx, requests)
            for index, (method, params) in enumerate(requests):
                if method == "eth_getBlockByNumber" and params[0] in ("0xbf", "0xc0"):
                    responses[index]["timestamp"] = hex(19136)
            return responses

        with patch.object(fixture, "exchange", side_effect=exchange):
            result = fixture.run(since_days=0.01)
        self.assertEqual(result["coverage"]["history"]["requested_range"], [191, 200])
        self.assertEqual(result["metrics"]["event_reported"]["requested_window_total"]["sale_count"], 1)
        self.assertIsNone(result["metrics"]["event_reported"]["lifetime_total"])

    def test_creation_receipt_must_match_canonical_header(self):
        fixture = Fixture()
        original = fixture.exchange

        def exchange(ctx, requests):
            responses = original(ctx, requests)
            for index, (method, params) in enumerate(requests):
                if method == "eth_getTransactionReceipt" and params[0] == fixture.creation_tx:
                    responses[index]["blockHash"] = hash_value(999999)
            return responses

        with patch.object(fixture, "exchange", side_effect=exchange), self.assertRaises(RpcError):
            fixture.run()
        self.assertFalse(any(method == "eth_getLogs" for method, _ in fixture.requests))

    def test_missing_receipt_or_log_scan_never_produces_complete_zero(self):
        fixture = Fixture()
        fixture.fail_method, fixture.failure = "eth_getLogs", RpcError("Synthetic unavailable history", kind="pruned")
        with fixture.patches():
            ctx = Context("premiumseller", deadline=30)
            try:
                ctx.pin("200")
                with self.assertRaises(RpcError):
                    seller.run(ctx, SimpleNamespace(since_days=None))
                result = json.loads(serialize_result(ctx.result))
                self.assertIsNone(result["metrics"]["event_reported"]["lifetime_total"])
                self.assertEqual(result["coverage"][seller.SALE_COVERAGE]["missing_ranges"], [[100, 200]])
            finally:
                ctx.close()

    def test_receipt_gap_retains_events_without_confirmed_total(self):
        fixture = Fixture()
        event = fixture.add_sale()
        with fixture.patches():
            ctx = Context("premiumseller", deadline=30)
            try:
                ctx.pin("200")
                original = ctx.receipt

                def receipt(tx):
                    if tx == event["transactionHash"]:
                        raise RpcError("Synthetic receipt unavailable", kind="unavailable")
                    return original(tx)

                with patch.object(ctx, "receipt", side_effect=receipt):
                    seller.run(ctx, SimpleNamespace(since_days=None))
                ctx.recheck()
                result = json.loads(serialize_result(ctx.result))
                self.assertEqual(result["metrics"]["event_reported"]["lifetime_total"]["sale_count"], 1)
                self.assertIsNone(result["metrics"]["receipt_confirmed"]["lifetime_total"])
            finally:
                ctx.close()

    def test_budget_stop_retains_newest_observed_subtotal_and_gap(self):
        fixture = Fixture()
        fixture.add_sale(block=180000)
        original = fixture.exchange
        scans = 0

        def exchange(ctx, requests):
            nonlocal scans
            if requests[0][0] == "eth_getLogs":
                scans += 1
                if scans == 2:
                    raise StopRun("rpc_member_limit")
            return original(ctx, requests)

        with patch.object(fixture, "exchange", side_effect=exchange), fixture.patches():
            ctx = Context("premiumseller", deadline=30)
            try:
                ctx.pin("200000")
                with self.assertRaises(StopRun):
                    seller.run(ctx, SimpleNamespace(since_days=None))
                result = json.loads(serialize_result(ctx.result))
                self.assertEqual(result["metrics"]["event_reported"]["observed_subtotal"]["sale_count"], 1)
                self.assertIsNone(result["metrics"]["event_reported"]["lifetime_total"])
                self.assertIsNone(result["metrics"]["receipt_confirmed"]["lifetime_total"])
                self.assertEqual(result["coverage"][seller.SALE_COVERAGE]["missing_ranges"], [[100, 100000]])
            finally:
                ctx.close()

    def test_unknown_runtime_never_starts_history_or_claims_zero(self):
        fixture = Fixture()
        fixture.runtime = "0x6001"
        with fixture.patches():
            ctx = Context("premiumseller", deadline=30)
            try:
                ctx.pin("200")
                with self.assertRaisesRegex(RpcError, "reviewed implementation"):
                    seller.run(ctx, SimpleNamespace(since_days=None))
                self.assertIsNone(ctx.result["metrics"]["event_reported"]["lifetime_total"])
                self.assertFalse(any(method == "eth_getLogs" for method, _ in fixture.requests))
            finally:
                ctx.close()

    def test_missing_remittance_and_conflicting_receipt_hash(self):
        fixture = Fixture()
        event = fixture.add_sale()
        receipt = fixture.receipts[event["transactionHash"]]
        receipt["logs"] = [row for row in receipt["logs"] if int(row["logIndex"], 16) != 3]
        result = fixture.run()
        self.assertEqual(result["metrics"]["sales"][0]["receipt_status"], "missing_remittance")
        self.assertIsNone(result["metrics"]["receipt_confirmed"]["lifetime_total"])
        fixture = Fixture()
        event = fixture.add_sale()
        fixture.receipts[event["transactionHash"]]["blockHash"] = hash_value(987654)
        with self.assertRaises(RpcError):
            fixture.run()

    def test_failed_receipt_and_wrong_emitter_reject_identity(self):
        for failed in (False, True):
            fixture = Fixture()
            event = fixture.add_sale()
            if failed:
                fixture.receipts[event["transactionHash"]]["status"] = "0x0"
            else:
                fixture.logs[0]["address"] = fixture.routes["net"]["address"]
            with self.assertRaises(RpcError):
                fixture.run()

    def test_recheck_invalidation_removes_totals(self):
        fixture = Fixture()
        fixture.add_sale()
        result = fixture.run()
        result["snapshot"]["recheck_status"] = "mismatch"
        serialized = json.loads(serialize_result(result))
        self.assertIsNone(serialized["metrics"]["event_reported"]["lifetime_total"])
        self.assertIsNone(serialized["metrics"]["receipt_confirmed"]["lifetime_total"])

    def test_cli_summary_and_permission_denial(self):
        for denial in (False, True):
            stream = io.StringIO()
            with redirect_stdout(stream):
                exit_code = smoke(denial=denial)
            result = json.loads(stream.getvalue())
            self.assertEqual(exit_code, 2 if denial else 0)
            self.assertNotIn("sales", result["metrics"])
            if denial:
                self.assertIsNone(result["metrics"]["event_reported"]["lifetime_total"])
                self.assertEqual(result["snapshot"]["recheck_status"], "not_performed")
            else:
                self.assertEqual(result["metrics"]["event_reported"]["lifetime_total"]["sale_count"], 1)
                self.assertEqual(result["snapshot"]["recheck_status"], "confirmed")

    def test_real_cli_empty_history_consistency(self):
        for scenario, expected in (("empty", 0), ("empty_inconsistent", 2)):
            stream = io.StringIO()
            with redirect_stdout(stream):
                exit_code = smoke(scenario=scenario)
            result = json.loads(stream.getvalue())
            self.assertEqual(exit_code, expected)
            total = result["metrics"]["event_reported"]["lifetime_total"]
            if expected:
                self.assertIsNone(total)
            else:
                self.assertEqual(total["sale_count"], 0)
            self.assertEqual(result["coverage"][seller.SALE_COVERAGE]["covered_ranges"], [[100, 200]])

    def test_unrelated_anonymous_receipt_log_does_not_hide_sale(self):
        fixture = Fixture()
        event = fixture.add_sale(offset=1)
        fixture.receipts[event["transactionHash"]]["logs"].insert(0, fixture.raw_log(
            fixture.routes["router"]["address"], 180, event["transactionHash"], 0, [], "0x"))
        result = fixture.run()
        self.assertEqual(result["metrics"]["receipt_confirmed"]["lifetime_total"]["usdg_to_treasury"]["raw"], "2000000")

    def test_unconfirmed_snapshot_withholds_totals_but_preserves_observations(self):
        fixture = Fixture()
        fixture.add_sale()
        original = fixture.exchange
        snapshot_reads = 0

        def exchange(ctx, requests):
            nonlocal snapshot_reads
            if requests[0] == ("eth_getBlockByNumber", ["0xc8", False]):
                snapshot_reads += 1
                if snapshot_reads > 1:
                    return [RpcError("Synthetic recheck unavailable", kind="unavailable")]
            return original(ctx, requests)

        stream = io.StringIO()
        with patch.object(fixture, "exchange", side_effect=exchange), fixture.patches(), redirect_stdout(stream), patch.object(analytics, "_PROCESS_STARTED", time.monotonic()):
            exit_code = analytics.main(["premiumseller", "--detail", "summary", "--deadline", "30"])
        result = json.loads(stream.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(result["snapshot"]["recheck_status"], "unconfirmed")
        self.assertIsNone(result["metrics"]["event_reported"]["lifetime_total"])
        self.assertIsNone(result["metrics"]["receipt_confirmed"]["lifetime_total"])
        self.assertEqual(result["metrics"]["receipt_confirmed"]["observed_subtotal"]["usdg_to_treasury"]["raw"], "2000000")

    def test_receipt_integrity_failure_does_not_start_final_recheck(self):
        fixture = Fixture()
        event = fixture.add_sale()
        fixture.receipts[event["transactionHash"]]["status"] = "0x0"
        stream = io.StringIO()
        with fixture.patches(), redirect_stdout(stream), patch.object(analytics, "_PROCESS_STARTED", time.monotonic()):
            exit_code = analytics.main(["premiumseller", "--detail", "summary", "--deadline", "30"])
        result = json.loads(stream.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(result["snapshot"]["recheck_status"], "not_performed")
        self.assertEqual(fixture.requests[-1], ("eth_getTransactionReceipt", [event["transactionHash"]]))
        self.assertIsNone(result["metrics"]["receipt_confirmed"]["lifetime_total"])

    def test_command_rejects_write_rpc_and_execution_call(self):
        ctx = Context("premiumseller", deadline=30)
        ctx.block = 200
        try:
            with self.assertRaises(RpcError):
                ctx._validate_payload("eth_sendTransaction", [{}])
            execute = {"type": "function", "name": "execute", "inputs": [{"type": "uint256"}]}
            with self.assertRaises(RpcError):
                ctx._validate_payload("eth_call", [{
                    "to": resolve_routes("premiumseller")["seller"]["address"],
                    "data": topic(execute)[:10] + word(0)}, "0xc8"])
        finally:
            ctx.close()


if __name__ == "__main__":
    unittest.main()

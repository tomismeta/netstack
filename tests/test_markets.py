"""Synthetic transport regressions for real Predict/House Context and CLI paths."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
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
import netstack_markets as markets
from netstack_core import Context, RpcError, ZERO, decode_event, keccak256, load_json, resolve_routes, serialize_result, topic


def hash_value(n):
    return "0x" + format(n, "064x")


def word(n):
    return format(int(n, 16) if isinstance(n, str) else int(n), "064x")


class Fixture:
    """Only the transport and static runtime evidence are synthetic, not Context."""
    def __init__(self, count=0, house_shares=0):
        self.routes = deepcopy(resolve_routes("predict"))
        self.da = load_json("assets/analytics/predict-interface.json")["abi"]
        self.ha = load_json("assets/analytics/house-interface.json")["abi"]
        self.ta = load_json("assets/analytics/predict-interface.json")["token_abi"]
        self.selectors = {topic(item)[:10]: item for abi in (self.da, self.ha, self.ta) for item in abi if item["type"] == "function"}
        self.logs, self.receipts, self.requests = [], {}, []
        self.count, self.house_shares = count, house_shares
        self.fail_method = self.failure = None
        self.runtime = "0x6000"
        self.higher, self.lower = "0x" + "11" * 20, "0x" + "22" * 20
        for index, name in enumerate(("desk", "house")):
            self.routes[name]["deployment_transaction_hash"] = hash_value(900 + index)
        a = {name: row["address"] for name, row in self.routes.items() if name != "_route"}
        self.desk_values = {"seriesCount": count, "halted": False, "minTicket": 1,
                            "vault": a["house"], "usdg": a["usdg"], "sleeve": a["sleeve"],
                            "treasury": a["treasury"], "reservedUsdg": 0, "pendingNetUsdg": 0,
                            "prizeCarry": 0, "net": a["sleeve"], "owner": a["treasury"],
                            "grader": a["treasury"], "markPrice": 10**18 // 2, "feesPaid": 0}
        self.house_values = {"seriesCount": count, "live": bool(count), "desk": a["desk"],
                             "usdg": a["usdg"], "wired": True, "generation": 0, "generationStartSeries": 0,
                             "totalShares": house_shares, "totalPending": 0, "totalClaimable": 0,
                             "activeAssets": house_shares // 10**12, "sharePriceWad": 10**6,
                             "sharesOf": 0, "assetsOf": 0, "pendingOf": [0, 0], "noticeOf": [0, 0]}
        self.series = [1, 100, 200, 30000, 40000, 0, 10**18, 10**18,
                       self.higher, self.lower, 0, 0, 100, 10, 110, 7, 1, 0, 1,
                       10**18 // 2, 0, 0, 0, False, ZERO, 0]

    def source(self, path):
        value = load_json(path)
        if path == "assets/contracts/predict-source-evidence.json":
            for row in value["runtime"].values():
                row.update(runtime_bytes=2, runtime_keccak256="0x" + keccak256(bytes.fromhex("6000")).hex())
        return value

    def event(self, address, abi, name, values, index, tx=None, block=150):
        item = next(item for item in abi if item.get("name") == name and item["type"] == "event")
        indexed = ["0x" + word(values[field["name"]]) for field in item["inputs"] if field.get("indexed")]
        data = "0x" + "".join(word(values[field["name"]]) for field in item["inputs"] if not field.get("indexed"))
        return {"address": address, "topics": [topic(item), *indexed], "data": data,
                "blockNumber": hex(block), "blockHash": hash_value(block + 1000), "transactionHash": tx or hash_value(block),
                "transactionIndex": "0x0", "logIndex": hex(index), "removed": False}

    def receipt(self, rows):
        first = rows[0]
        receipt = {key: first[key] for key in ("blockNumber", "blockHash", "transactionHash", "transactionIndex")}
        receipt.update(status="0x1", logs=deepcopy(rows), **{"from": ZERO, "to": self.routes["desk"]["address"], "contractAddress": None})
        self.receipts[first["transactionHash"]] = receipt

    def exchange(self, ctx, requests):
        replies = []
        for method, params in requests:
            ctx._validate_payload(method, params)
            ctx._members += 1
            self.requests.append((method, params))
            if method == self.fail_method:
                replies.append(self.failure)
                continue
            if method == "eth_chainId":
                value = hex(4663)
            elif method == "eth_getBlockByNumber":
                n = 202 if params[0] == "latest" else int(params[0], 16)
                value = {"number": hex(n), "hash": hash_value(n + 1000), "timestamp": hex(n * 100)}
            elif method == "eth_getCode":
                value = "0x" if int(params[1], 16) < 100 else self.runtime
            elif method == "eth_call":
                item = self.selectors[params[0]["data"][:10]]
                name, address = item["name"], params[0]["to"]
                if name == "series":
                    output = self.series
                elif name == "decimals":
                    output = 6 if address == self.routes["usdg"]["address"] else 18
                elif name in ("balanceOf", "totalSupply"):
                    output = 0
                elif name in ("name", "symbol"):
                    text = b"Synthetic"
                    replies.append("0x" + word(32) + word(len(text)) + text.hex() + "00" * (-len(text) % 32))
                    continue
                else:
                    values = self.desk_values if address == self.routes["desk"]["address"] else self.house_values
                    output = values[name]
                output = output if isinstance(output, list) else [output]
                value = "0x" + "".join(word(n) for n in output)
            elif method == "eth_getLogs":
                query = params[0]
                def matches(row):
                    if row["address"] != query["address"] or not int(query["fromBlock"], 16) <= int(row["blockNumber"], 16) <= int(query["toBlock"], 16):
                        return False
                    return all(wanted is None or row["topics"][i] in (wanted if isinstance(wanted, list) else [wanted]) for i, wanted in enumerate(query["topics"]))
                value = [deepcopy(row) for row in self.logs if matches(row)]
            elif method == "eth_getTransactionReceipt":
                creation = next((name for name in ("desk", "house") if params[0] == self.routes[name]["deployment_transaction_hash"]), None)
                if creation:
                    value = {"transactionHash": params[0], "blockNumber": "0x64", "blockHash": hash_value(1100),
                             "transactionIndex": "0x0" if creation == "desk" else "0x1", "status": "0x1", "from": ZERO, "to": None,
                             "contractAddress": self.routes[creation]["address"], "logs": []}
                else:
                    value = deepcopy(self.receipts[params[0]])
            else:
                raise AssertionError(method)
            replies.append(value)
        return replies

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(markets, "resolve_routes", return_value=self.routes))
        stack.enter_context(patch.object(markets, "load_json", side_effect=self.source))
        stack.enter_context(patch.object(Context, "_exchange_once", lambda ctx, requests: self.exchange(ctx, requests)))
        return stack

    def run(self, command="predict", series=None):
        with self.patches():
            ctx = Context(command, deadline=30)
            try:
                ctx.pin("200")
                (markets.run_predict if command == "predict" else markets.run_house)(ctx, SimpleNamespace(series=series))
                ctx.recheck()
                return json.loads(serialize_result(ctx.result))
            finally:
                ctx.close()


def smoke(command="predict", scenario="empty_inconsistent"):
    """Real analytics.main, bounded synthetic RPC transport; never live-chain proof."""
    fixture = Fixture(count=1 if scenario == "empty_inconsistent" else 0)
    if scenario == "permission":
        fixture.fail_method = "eth_getLogs"
        fixture.failure = RpcError("Synthetic permission denial", kind="permission")
    with fixture.patches(), patch.object(analytics, "_PROCESS_STARTED", time.monotonic()):
        return analytics.main([command, "--block", "200", "--deadline", "30", "--json"])


class MarketDepthTests(unittest.TestCase):
    def test_empty_history_does_not_override_nonzero_series_or_capital(self):
        for command, fixture in (("predict", Fixture(count=1)), ("house", Fixture(count=1)),
                                 ("house", Fixture(house_shares=10**18))):
            with self.subTest(command=command, count=fixture.count):
                result = fixture.run(command)
                self.assertFalse(result["coverage"]["collection_complete"])
                self.assertFalse(result["metrics"]["state_history_consistency"]["consistent"])
                self.assertIsNone(result["metrics"]["receipt_reconciliation"]["confirmed_totals"])
                if command == "predict":
                    self.assertIsNone(result["metrics"]["activity"]["selected_deployment_totals"])
                    self.assertIsNone(result["metrics"]["funding"]["series"]["1"]["funded_event_usdg_raw"])

    def test_zero_requires_independent_zero_state_and_confirmed_snapshot(self):
        result = Fixture().run()
        self.assertTrue(result["coverage"]["collection_complete"])
        self.assertEqual(result["metrics"]["activity"]["selected_deployment_totals"], {})
        result["snapshot"]["recheck_status"] = "unconfirmed"
        markets.prepare_result(result)
        self.assertFalse(result["coverage"]["collection_complete"])
        self.assertIsNone(result["metrics"]["activity"]["selected_deployment_totals"])
        self.assertEqual(result["metrics"]["activity"]["series"], {})

    def test_selected_snapshot_never_fetches_history(self):
        fixture = Fixture(count=2)
        result = fixture.run(series=2)
        self.assertTrue(result["coverage"]["collection_complete"])
        self.assertEqual(result["coverage"]["series_discovery"]["inspected_ids"], [2])
        self.assertFalse(any(method in ("eth_getLogs", "eth_getTransactionReceipt") for method, params in fixture.requests))

    def test_unknown_runtime_cannot_use_reviewed_accounting(self):
        fixture = Fixture()
        fixture.runtime = "0x6001"
        with self.assertRaises(RpcError):
            fixture.run()
        self.assertFalse(any(method == "eth_call" for method, params in fixture.requests))

    def receipt_case(self, *, missing=False, lazy=False, failure=None, omitted=False, conflicting_values=False):
        fixture = Fixture()
        desk, house, usdg = (fixture.routes[name]["address"] for name in ("desk", "house", "usdg"))
        account = fixture.higher
        if lazy:
            event = fixture.event(house, fixture.ha, "Deposited", {"account": account, "usdg": 10, "shares": 10**18}, 0)
            rows = [event]
        else:
            cash = fixture.event(usdg, fixture.ta, "Transfer", {"from": desk, "to": account, "value": 7}, 0)
            burn = fixture.event(fixture.lower, fixture.ta, "Transfer", {"from": account, "to": ZERO, "value": 10**18}, 1)
            event = fixture.event(desk, fixture.da, "Redeemed", {"series": 1, "account": account, "long": False, "tokens": 10**18, "usdgOut": 7}, 2)
            rows = [burn, event] if missing else [cash, burn, event]
        if omitted:
            extra = deepcopy(event)
            extra["logIndex"] = "0x3"
            rows.append(extra)
        fixture.receipt(rows)
        if conflicting_values:
            stored = fixture.receipts[event["transactionHash"]]["logs"]
            stored[0]["data"] = "0x" + word(8)
            stored[-1]["data"] = stored[-1]["data"][:-64] + word(8)
        if failure:
            fixture.fail_method = "eth_getTransactionReceipt"
            fixture.failure = RpcError("Synthetic denied receipt", kind=failure)
        with fixture.patches():
            ctx = Context("house" if lazy else "predict", deadline=30)
            try:
                ctx.pin("200")
                ledger = markets._Evidence(ctx, desk, house, usdg)
                ledger.event_keys = ["house_events" if lazy else "desk_events"]
                ledger.extend([decode_event(event, fixture.ha if lazy else fixture.da)])
                markets._receipts(ctx, ledger, fixture.da, fixture.ha, fixture.ta, None if lazy else {(1, False): fixture.lower})
                return ctx.result["metrics"]["receipt_reconciliation"], ledger
            finally:
                ctx.close()

    def test_redemption_cash_and_privileged_burn_are_separate_receipt_legs(self):
        report, ledger = self.receipt_case()
        self.assertTrue(report["all_groups_matched"])
        self.assertEqual(report["observed_matched_subtotals"]["Redeemed.usdg_raw"], "7")
        self.assertEqual(report["observed_matched_subtotals"]["Redeemed:outcome.outcome_raw"], str(10**18))
        report, ledger = self.receipt_case(missing=True)
        self.assertFalse(report["all_groups_matched"])
        self.assertNotIn("Redeemed.usdg_raw", report["observed_matched_subtotals"])

    def test_lazy_queued_join_is_not_a_second_deposit_cashflow(self):
        report, ledger = self.receipt_case(lazy=True)
        self.assertTrue(report["all_groups_matched"])
        self.assertEqual(report["observed_matched_subtotals"], {})
        self.assertEqual(len(ledger.non_cash_deposits), 1)
        self.assertEqual(ledger.expected()[0], {})

    def test_receipt_exposes_event_omitted_from_served_scan(self):
        report, ledger = self.receipt_case(omitted=True)
        self.assertFalse(report["all_groups_matched"])
        transaction = next(iter(report["transactions"].values()))
        self.assertEqual(transaction["missing_scan_events"][0]["log_index"], 3)

    def test_matching_receipt_cash_cannot_override_conflicting_scanned_event(self):
        with self.assertRaises(RpcError) as caught:
            self.receipt_case(conflicting_values=True)
        self.assertEqual(caught.exception.kind, "integrity")

    def test_matured_claim_survives_later_generation_reset(self):
        fixture = Fixture(count=2)
        fixture.house_values.update(live=False, generation=1, generationStartSeries=2,
                                    noticeOf=[10**18, 1], exitPriceWad=600000)
        report = fixture.run("house")
        account = report["metrics"]["accounts"][fixture.routes["sleeve"]["address"]]
        self.assertTrue(account["notice"]["matured"])
        self.assertFalse(account["notice"]["generation_compatible"])
        self.assertEqual(account["notice"]["frontend_claim_usdg_raw"], "600000")
        self.assertEqual(report["metrics"]["ownership"]["matured_claim_observed_usdg_raw"], "1200000")

    def test_receipt_terminal_denial_is_not_demoted_to_optional_gap(self):
        for kind in ("permission", "integrity"):
            with self.subTest(kind=kind), self.assertRaises(RpcError) as caught:
                self.receipt_case(failure=kind)
            self.assertEqual(caught.exception.kind, kind)

    def test_real_cli_preserves_empty_history_failure_and_denial(self):
        for command in ("predict", "house"):
            for scenario in ("empty_inconsistent", "permission"):
                with self.subTest(command=command, scenario=scenario):
                    output = io.StringIO()
                    with redirect_stdout(output):
                        status = smoke(command, scenario)
                    result = json.loads(output.getvalue())
                    self.assertEqual(status, 2)
                    self.assertFalse(result["coverage"]["collection_complete"])
                    if scenario == "permission":
                        self.assertEqual(result["snapshot"]["recheck_status"], "not_performed")
                    else:
                        self.assertEqual(result["snapshot"]["recheck_status"], "confirmed")


if __name__ == "__main__":
    unittest.main()

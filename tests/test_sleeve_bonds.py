"""Synthetic transport exercises real Context/CLI; no packaged financial history."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
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
import netstack_sleeve_bonds as sleeve
from netstack_core import (Context, RpcError, ZERO, TRANSFER_TOPIC, decode_event,
                           load_json, resolve_routes, serialize_result, topic)


def word(value):
    return format(value, "064x")


def hash_value(value):
    return "0x" + word(value)


class Fixture:
    def __init__(self):
        self.routes = deepcopy(resolve_routes("sleeve-bonds"))
        self.source = deepcopy(load_json("assets/analytics/sleeve-bonds-interface.json"))
        self.source["runtime_evidence"].update(runtime_bytes=2, runtime_sha256=hashlib.sha256(bytes.fromhex("6000")).hexdigest())
        self.account = "0x" + "11" * 20
        self.equity = "0x" + "22" * 20
        self.router = "0x" + "33" * 20
        self.creation_tx = hash_value(999)
        self.creation_hash = hash_value(1100)
        self.routes["desk"]["deployment_transaction_hash"] = self.creation_tx
        self.logs, self.receipts, self.requests = [], {}, []
        self.fail_method = None
        self.notes = [{"payout": 2_000_000_000, "claimed": 0, "start": 18000, "end": 22000}]
        self.values = {name: self.routes[role]["address"] for name, role in sleeve.BINDINGS}
        self.values.update(inventory=3_000_000_000, owedNet=2_000_000_000,
                           inventoryMax=150_000_000_000, bHwm=10**18, deskDiscountBps=650,
                           halted=False, VEST=172800, INVENTORY_HARD_CAP=300_000_000_000,
                           MAX_DISCOUNT_BPS=750, MAX_ORACLE_DEV_BPS=500, MIN_PREMIUM_WAD=12*10**17,
                           balanceOf=5_000_000_000, menuLength=0)
        self.selectors = {topic(item)[:10]: item for key in ("abi", "token_abi")
                          for item in self.source[key] if item.get("type") == "function"}

    def raw_log(self, address, index, topics, data):
        return {"address": address, "blockNumber": hex(180), "blockHash": hash_value(1180),
                "transactionHash": hash_value(180), "transactionIndex": "0x0", "logIndex": hex(index),
                "topics": topics, "data": data, "removed": False}

    def transfer(self, token, sender, receiver, value, index):
        return self.raw_log(token, index, [TRANSFER_TOPIC, "0x" + sender[2:].rjust(64, "0"),
                                          "0x" + receiver[2:].rjust(64, "0")], "0x" + word(value))

    def add_subscription(self, residual=100000, router_refund=False):
        desk, custody, usdg = (self.routes[key]["address"] for key in ("desk", "sleeve", "usdg"))
        event_abi = next(item for item in self.source["abi"] if item.get("name") == "DeskBond")
        event = self.raw_log(desk, 5 if router_refund else 4, [topic(event_abi), "0x" + self.account[2:].rjust(64, "0"),
                                      "0x" + self.equity[2:].rjust(64, "0")],
                             "0x" + "".join(word(v) for v in (4_000_000, 2_000_000_000, 2*10**18, 0, 10**18)))
        self.logs.append(event)
        rows = [self.transfer(usdg, self.account, desk, 4_000_000, 0),
                self.transfer(usdg, desk, self.router, 4_000_000 if router_refund else 4_000_000-residual, 1)]
        if router_refund:
            rows.append(self.transfer(usdg, self.router, desk, residual, 2))
        rows.extend([self.transfer(self.equity, desk, custody, 10**18, len(rows)),
                     self.transfer(usdg, desk, custody, residual, len(rows)+1), event])
        self.receipts[hash_value(180)] = {"transactionHash": hash_value(180), "blockNumber": hex(180),
            "blockHash": hash_value(1180), "transactionIndex": "0x0", "status": "0x1", "from": self.account,
            "to": desk, "contractAddress": None, "logs": rows}

    def exchange(self, ctx, requests):
        output = []
        for method, params in requests:
            ctx._validate_payload(method, params)
            ctx._members += 1
            self.requests.append((method, params))
            if method == self.fail_method:
                output.append(RpcError("Synthetic permission denial", kind="permission"))
                continue
            if method == "eth_chainId":
                value = hex(4663)
            elif method == "eth_getBlockByNumber":
                number = 202 if params[0] == "latest" else int(params[0], 16)
                value = {"number": hex(number), "hash": hash_value(number+1000), "timestamp": hex(number*100)}
            elif method == "eth_getCode":
                value = "0x6000"
            elif method == "eth_call":
                item = self.selectors[params[0]["data"][:10]]
                name = item["name"]
                if name == "menu":
                    value = "0x" + word(32) + word(0)
                elif name == "noteAt":
                    index = int(params[0]["data"][-64:], 16)
                    value = "0x" + "".join(word(self.notes[index][key]) for key in ("payout", "claimed", "start", "end"))
                elif name == "pendingFor":
                    pending = sum(note["payout"]-note["claimed"] for note in self.notes)
                    claimable = sum(note["payout"]*(20000-note["start"])//(note["end"]-note["start"])-note["claimed"] for note in self.notes)
                    value = "0x" + word(pending) + word(claimable)
                else:
                    if name == "decimals":
                        raw = 9 if params[0]["to"] == self.routes["net"]["address"] else 6
                    elif name == "noteCount":
                        raw = len(self.notes)
                    else:
                        raw = self.values[name]
                    value = "0x" + word(int(raw, 16) if isinstance(raw, str) else raw)
            elif method == "eth_getLogs":
                value = deepcopy(self.logs)
            elif method == "eth_getTransactionReceipt":
                if params[0] == self.creation_tx:
                    value = {"transactionHash": self.creation_tx, "blockNumber": hex(100), "blockHash": self.creation_hash,
                             "transactionIndex": "0x0", "status": "0x1", "from": ZERO, "to": None,
                             "contractAddress": self.routes["desk"]["address"], "logs": []}
                else:
                    value = deepcopy(self.receipts[params[0]])
            else:
                raise AssertionError(method)
            output.append(value)
        return output

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(sleeve, "resolve_routes", return_value=self.routes))
        stack.enter_context(patch.object(sleeve, "load_json", return_value=self.source))
        fixture = self
        stack.enter_context(patch.object(Context, "_exchange_once", lambda ctx, requests: fixture.exchange(ctx, requests)))
        return stack

    def run(self, history=False, account=False, max_notes=128, recheck=True):
        with self.patches():
            ctx = Context("sleeve-bonds", deadline=30)
            try:
                ctx.pin("200")
                sleeve.run(ctx, SimpleNamespace(history=history, account=self.account if account else None, max_notes=max_notes))
                if recheck:
                    ctx.recheck()
                sleeve.prepare_result(ctx.result)
                return json.loads(serialize_result(ctx.result))
            finally:
                ctx.close()


def smoke(args=None, scenario="snapshot"):
    fixture = Fixture()
    if scenario == "subscription":
        fixture.add_subscription()
    elif scenario == "denial":
        fixture.fail_method = "eth_call"
    elif scenario not in ("snapshot", "empty"):
        raise ValueError("Unknown synthetic scenario")
    with fixture.patches(), patch.object(analytics, "_PROCESS_STARTED", time.monotonic()):
        return analytics.main(args or ["sleeve-bonds", "--block", "200", "--detail", "summary", "--deadline", "30"])


class SleeveBondTests(unittest.TestCase):
    def test_snapshot_reports_global_gross_claims_without_history(self):
        fixture = Fixture()
        result = fixture.run()
        self.assertEqual(result["metrics"]["current"]["gross_outstanding_claims"]["raw"], "2000000000")
        self.assertTrue(result["coverage"]["collection_complete"])
        self.assertFalse(any(method == "eth_getLogs" for method, _ in fixture.requests))

    def test_account_notes_reconcile_linear_vesting(self):
        result = Fixture().run(account=True)
        report = result["metrics"]["account"]
        self.assertEqual(report["notes"][0]["claimable_now"]["raw"], "1000000000")
        self.assertTrue(report["collection_complete"])
        self.assertEqual(report["scope"], "selected_account_only")

    def test_capped_account_never_claims_complete_discovery(self):
        fixture = Fixture()
        fixture.notes.append(deepcopy(fixture.notes[0]))
        result = fixture.run(account=True, max_notes=1)
        self.assertFalse(result["coverage"]["collection_complete"])
        self.assertFalse(result["metrics"]["account"]["enumeration_complete"])
        self.assertEqual(result["metrics"]["account"]["pending_for"]["outstanding"]["raw"], "4000000000")

    def test_subscription_residual_is_sleeve_not_treasury(self):
        fixture = Fixture()
        fixture.add_subscription()
        result = fixture.run(history=True)
        history = result["metrics"]["history"]
        self.assertEqual(history["lifetime_event_total"]["subscriber_capital"]["raw"], "4000000")
        self.assertIsNone(history["treasury_remittance"])
        receipt = result["metrics"]["events"][0]["receipt"]
        self.assertEqual(receipt["residual_usdg_to_sleeve"]["raw"], "100000")
        self.assertTrue(history["receipt_collection_complete"])
        summary = json.loads(sleeve.summarize(json.dumps(result), "complete"))
        self.assertEqual(summary["metrics"]["history"], history)
        self.assertTrue(summary["coverage"]["collection_complete"])

    def test_router_return_is_not_additional_subscriber_capital(self):
        fixture = Fixture()
        fixture.add_subscription(router_refund=True)
        result = fixture.run(history=True)
        history = result["metrics"]["history"]
        receipt = result["metrics"]["events"][0]["receipt"]
        self.assertEqual(history["lifetime_event_total"]["subscriber_capital"]["raw"], "4000000")
        self.assertEqual(receipt["residual_usdg_to_sleeve"]["raw"], "100000")
        self.assertEqual(receipt["usdg_returns_to_desk"][0]["amount"]["raw"], "100000")
        self.assertTrue(result["coverage"]["collection_complete"])

    def test_unfunded_return_withholds_receipt_totals_even_when_cash_balances(self):
        fixture = Fixture()
        fixture.add_subscription(router_refund=True)
        fixture.receipts[hash_value(180)]["logs"][2]["topics"][1] = "0x" + ("44" * 20).rjust(64, "0")
        result = fixture.run(history=True)
        self.assertIsNone(result["metrics"]["history"]["receipt_routing"]["lifetime_total"])
        self.assertEqual(result["metrics"]["history"]["lifetime_event_total"]["subscriber_capital"]["raw"], "4000000")
        self.assertFalse(result["metrics"]["events"][0]["receipt"]["return_legs_match_prior_outflows"])
        self.assertFalse(result["coverage"]["collection_complete"])

    def test_creation_receipt_must_match_creation_header(self):
        fixture = Fixture()
        fixture.creation_hash = hash_value(9999)
        with self.assertRaises(RpcError) as caught:
            fixture.run(history=True)
        self.assertEqual(caught.exception.kind, "integrity")
        self.assertFalse(any(method == "eth_getLogs" for method, _ in fixture.requests))

    def test_empty_history_never_becomes_zero_lifetime(self):
        fixture = Fixture()
        fixture.values["owedNet"] = 0
        result = fixture.run(history=True)
        self.assertIsNone(result["metrics"]["history"]["lifetime_event_total"])
        self.assertFalse(result["coverage"]["collection_complete"])

    def test_missing_subscription_detected_by_note_count(self):
        fixture = Fixture()
        fixture.add_subscription()
        fixture.notes.append(deepcopy(fixture.notes[0]))
        result = fixture.run(history=True)
        self.assertFalse(result["coverage"]["history_reconciliation"]["discovered_note_counts_match"])
        self.assertIsNone(result["metrics"]["history"]["lifetime_event_total"])

    def test_no_final_total_before_block_recheck(self):
        fixture = Fixture()
        fixture.add_subscription()
        result = fixture.run(history=True, recheck=False)
        self.assertIsNone(result["metrics"]["history"]["lifetime_event_total"])
        self.assertFalse(result["coverage"]["collection_complete"])

    def test_permission_failure_is_terminal(self):
        fixture = Fixture()
        fixture.fail_method = "eth_call"
        with self.assertRaises(RpcError) as caught:
            fixture.run()
        self.assertEqual(caught.exception.kind, "permission")
        self.assertFalse(any(method == "eth_getLogs" for method, _ in fixture.requests))

    def test_rounding_and_invalid_claim_state(self):
        row = sleeve.note_row({"payout": 11, "claimed": 1, "start": 0, "end": 3}, 0, 1)
        self.assertEqual(row["claimable_now"]["raw"], "2")
        with self.assertRaises(RpcError):
            sleeve.note_row({"payout": 11, "claimed": 4, "start": 0, "end": 3}, 0, 1)


if __name__ == "__main__":
    unittest.main()

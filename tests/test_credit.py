"""Synthetic transport only: fresh Credit arithmetic and actual Context/CLI boundaries."""
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
import netstack_credit as credit
from netstack_core import Context, RpcError, ZERO, _encode_value, load_json, resolve_routes, serialize_result, topic


def word(value):
    return int(value).to_bytes(32, "big")


def encode(outputs, outputs_values):
    heads, tails = [], b""
    offset = sum(32 if field["type"] in ("bytes", "bytes32[]") else 32 for field in outputs)
    for field, value in zip(outputs, outputs_values):
        if field["type"] == "bytes":
            raw = bytes.fromhex(value[2:])
            part = word(len(raw)) + raw + b"\0" * (-len(raw) % 32)
        elif field["type"] == "bytes32[]":
            part = word(len(value)) + b"".join(bytes.fromhex(v[2:]) for v in value)
        else:
            heads.append(_encode_value(field, value))
            continue
        heads.append(word(offset + len(tails)))
        tails += part
    return "0x" + (b"".join(heads) + tails).hex()


class Fixture:
    def __init__(self):
        self.routes = resolve_routes("credit")
        self.interface = load_json("assets/analytics/credit-interface.json")
        self.evidence = deepcopy(load_json(self.interface["source_evidence"]))
        for row in self.evidence["contracts"].values():
            row.update(runtime_bytes=2, runtime_sha256=hashlib.sha256(bytes.fromhex("6000")).hexdigest())
        self.addresses = {key: row["address"] for key, row in self.routes.items() if key != "_route"}
        self.params = {"loanToken": self.addresses["usdg"], "collateralToken": "0x" + "aa" * 20,
                       "oracle": self.addresses["oracle"], "irm": self.addresses["irm"], "lltv": 625000000000000000}
        self.mid = credit.market_id(self.params)
        self.selectors = {topic(item)[:10]: item for key, abi in self.interface.items() if key.endswith("_abi") for item in abi}
        self.requests = []
        self.denial = False
        self.unknown_adapter = False
        self.revert_oracle = False
        self.state = {
            "asset": self.addresses["usdg"], "parentVault": self.addresses["vault"], "morpho": self.addresses["morpho"],
            "MORPHO": self.addresses["morpho"], "adapter": self.addresses["adapter"], "adaptiveCurveIrm": self.addresses["irm"],
            "irm": self.addresses["irm"], "oracle": self.addresses["oracle"],
            "totalAssets": 1100000, "totalSupply": 10**18, "virtualShares": 10**12, "_totalAssets": 1000000,
            "lastUpdate": 100, "maxRate": 10**15, "performanceFee": 10**17, "managementFee": 0,
            "performanceFeeRecipient": "0x" + "bb" * 20, "managementFeeRecipient": ZERO,
            "owner": "0x" + "cc" * 20, "curator": "0x" + "dd" * 20,
            "liquidityAdapter": self.addresses["adapter"], "liquidityData": "0x", "adapterRegistry": ZERO,
            "receiveSharesGate": ZERO, "sendSharesGate": ZERO, "receiveAssetsGate": ZERO, "sendAssetsGate": ZERO,
            "adaptersLength": 1, "adapters": self.addresses["adapter"], "realAssets": 1000000,
            "marketIdsLength": 1, "marketIds": self.mid, "listedMarkets": [self.mid], "marketId": self.mid,
            "feeRecipient": "0x" + "ee" * 20, "borrowRateView": 10**12,
            "expectedSupplyAssets": 1000000, "ids": [], "price": 10**36,
            "canSendShares": True, "canReceiveAssets": True, "maxWithdraw": 0, "convertToAssets": 100000,
        }

    def exchange(self, ctx, requests):
        results = []
        for method, params in requests:
            ctx._validate_payload(method, params)
            ctx._members += 1
            self.requests.append((method, params))
            if self.denial:
                results.append(RpcError("Synthetic permission denial", kind="permission"))
                continue
            if method == "eth_chainId":
                result = hex(4663)
            elif method == "eth_getBlockByNumber":
                number = 200 if params[0] == "latest" else int(params[0], 16)
                result = {"number": hex(number), "hash": "0x" + format(number, "064x"), "timestamp": hex(200)}
            elif method == "eth_getCode":
                result = "0x6000"
            elif method == "eth_call":
                item = self.selectors[params[0]["data"][:10]]
                name = item["name"]
                if name == "price" and self.revert_oracle:
                    results.append(RpcError("Synthetic oracle revert", kind="revert"))
                    continue
                if name == "decimals":
                    out = [6 if params[0]["to"] == self.addresses["usdg"] else 18]
                elif name == "accrueInterestView":
                    out = [1100000, 10**15, 0]
                elif name == "idToMarketParams":
                    out = list(self.params.values())
                elif name == "market":
                    out = [2000000, 2 * 10**12, 1000000, 10**12, 100, 10**17]
                elif name == "position":
                    out = [0, 10**11, 400000]
                elif name == "balanceOf":
                    out = [100000 if params[0]["to"] == self.addresses["usdg"] else 10**17]
                elif name == "adapters" and self.unknown_adapter:
                    out = ["0x" + "ab" * 20]
                else:
                    out = [self.state[name]]
                result = encode(item["outputs"], out)
            else:
                raise AssertionError("Unexpected method: " + method)
            results.append(result)
        return results

    def patches(self):
        stack = ExitStack()
        original = credit.load_json
        stack.enter_context(patch.object(credit, "load_json", side_effect=lambda path: self.evidence if path == self.interface["source_evidence"] else original(path)))
        fixture = self
        stack.enter_context(patch.object(Context, "_exchange_once", lambda ctx, requests: fixture.exchange(ctx, requests)))
        return stack

    def run(self, account=None):
        with self.patches():
            ctx = Context("credit", deadline=30)
            try:
                ctx.pin("200")
                credit.run(ctx, SimpleNamespace(account=account, max_adapters=16, max_markets=32))
                ctx.recheck()
                credit.prepare_result(ctx.result)
                return json.loads(serialize_result(ctx.result))
            finally:
                ctx.close()


def smoke(args=None, denial=False):
    fixture = Fixture()
    fixture.denial = denial
    with fixture.patches(), patch.object(analytics, "_PROCESS_STARTED", time.monotonic()):
        return analytics.main(args or ["credit", "--detail", "summary", "--deadline", "30"])


class CreditTests(unittest.TestCase):
    def test_virtual_offsets_and_rounding(self):
        self.assertEqual(credit.assets_for_shares(1, 0, 0), 0)
        self.assertEqual(credit.assets_for_shares(1, 0, 0, up=True), 1)
        self.assertEqual(credit.assets_for_shares(0, 0, 0, up=True), 0)

    def test_accrual_fees_are_shares_not_cash(self):
        state = dict(zip(credit.MARKET_FIELDS, [1000000, 10**12, 500000, 10**12, 100, 10**17]))
        result = credit.accrue_market(state, 110, 10**15)
        first = 10**16
        compounded = first + first * first // (2 * 10**18) + (first * first // (2 * 10**18)) * first // (3 * 10**18)
        interest = 500000 * compounded // 10**18
        self.assertEqual(result["pending_interest_assets"], interest)
        self.assertEqual(result["available_liquidity_assets"], 500000)
        self.assertGreater(result["pending_fee_shares"], 0)
        self.assertEqual(state["totalBorrowAssets"], 500000)

    def test_future_state_is_integrity_error(self):
        with self.assertRaises(RpcError) as caught:
            credit.accrue_market(dict(zip(credit.MARKET_FIELDS, [1, 1, 0, 0, 201, 0])), 200, 0)
        self.assertEqual(caught.exception.kind, "integrity")

    def test_unknown_health_is_not_zero_debt(self):
        market = {"totalBorrowAssets": 100, "totalBorrowShares": 10**6, "totalSupplyAssets": 200, "totalSupplyShares": 10**6}
        position = credit.account_position([0, 10**6, 0], market, None, 625000000000000000,
                                           is_fee_recipient=False)
        self.assertGreater(position["accrued_debt_assets"], 0)
        self.assertIsNone(position["healthy_at_reported_oracle"])
        self.assertIsNone(position["income"])

    def test_snapshot_needs_confirmation_without_erasing_observations(self):
        result = {"metrics": {"credit_scope": {}, "snapshot_reads_complete": True, "vault": {"totalAssets": 4}}, "snapshot": {}, "errors": []}
        credit.prepare_result(result)
        self.assertIsNone(result["metrics"]["confirmed_vault_accounting"])
        result["snapshot"]["recheck_status"] = "confirmed"
        credit.prepare_result(result)
        self.assertEqual(result["metrics"]["confirmed_vault_accounting"]["totalAssets"], 4)
        credit.prepare_result({"metrics": {}})

    def test_actual_context_nonzero_claim_with_zero_max_withdraw(self):
        fixture = Fixture()
        result = fixture.run("0x" + "12" * 20)
        self.assertTrue(result["coverage"]["collection_complete"])
        vault = result["metrics"]["vault"]
        self.assertEqual(int(vault["account"]["max_withdraw_reported"]), 0)
        self.assertGreater(int(vault["account"]["claim_assets"]), 0)
        self.assertIsNone(result["metrics"]["cash_fee_receipts"])
        self.assertFalse(any(method == "eth_getLogs" for method, _ in fixture.requests))

    def test_new_adapter_is_not_ignored(self):
        fixture = Fixture()
        fixture.unknown_adapter = True
        result = fixture.run()
        self.assertFalse(result["coverage"]["collection_complete"])
        self.assertIsNone(result["metrics"]["confirmed_vault_accounting"])
        self.assertTrue(result["metrics"]["unsupported"])

    def test_oracle_revert_preserves_debt_but_not_health(self):
        fixture = Fixture()
        fixture.revert_oracle = True
        result = fixture.run("0x" + "12" * 20)
        self.assertFalse(result["coverage"]["collection_complete"])
        position = result["metrics"]["markets"][0]["account"]
        self.assertGreater(int(position["accrued_debt_assets"]), 0)
        self.assertIsNone(position["healthy_at_reported_oracle"])

    def test_fee_recipient_receives_pending_morpho_shares(self):
        fixture = Fixture()
        recipient = fixture.run(fixture.state["feeRecipient"])["metrics"]["markets"][0]["account"]
        ordinary = fixture.run("0x" + "12" * 20)["metrics"]["markets"][0]["account"]
        self.assertEqual(recipient["supply_shares"], 0)
        self.assertEqual(recipient["pending_fee_shares"], 9999550)
        self.assertEqual(recipient["accrued_supply_shares"], 9999550)
        self.assertEqual(recipient["supply_claim_assets"], 9)
        self.assertEqual(ordinary["pending_fee_shares"], 0)
        self.assertEqual(ordinary["supply_claim_assets"], 0)

    def test_summary_emits_confirmed_or_denied_accounting(self):
        for denied in (False, True):
            with self.subTest(denied=denied), redirect_stdout(io.StringIO()) as output:
                code = smoke(denial=denied)
            result = json.loads(output.getvalue())
            self.assertEqual(code, 2 if denied else 0)
            if denied:
                self.assertEqual(result["errors"][0]["kind"], "permission")
                self.assertIsNone(result["metrics"].get("confirmed_vault_accounting"))
            else:
                self.assertEqual(result["metrics"]["confirmed_vault_accounting"]["totalAssets"], 1100000)

    def test_permission_denial_is_terminal(self):
        fixture = Fixture()
        fixture.denial = True
        with self.assertRaises(RpcError):
            fixture.run()
        self.assertEqual(len(fixture.requests), 1)


if __name__ == "__main__":
    unittest.main()

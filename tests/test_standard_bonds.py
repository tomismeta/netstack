"""Synthetic transport exercises epoch selection, canonical receipts and fail-closed totals."""

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analytics
import netstack_standard_bonds as bonds
from netstack_core import Context, RpcError, StopRun, ZERO, TRANSFER_TOPIC, decode_event, load_json, resolve_routes, serialize_result, topic

UNIT = bonds.NET_UNIT
USER = "0x" + "ab"*20


def word(value):
    return format(int(value), "064x")


def hash_value(value):
    return "0x" + word(value)


def encode(field, value):
    return value[2:].rjust(64, "0") if field["type"] == "address" else word(value)


class Fixture:
    def __init__(self):
        self.routes = resolve_routes("standard-bonds")
        self.source = load_json("assets/analytics/standard-bonds-interface.json")
        self.evidence = deepcopy(load_json("assets/contracts/bond-depository-source-evidence.json"))
        for value in self.evidence["contracts"].values():
            value.update(runtime_bytes=2, runtime_sha256=hashlib.sha256(bytes.fromhex("6000")).hexdigest())
        self.selectors = {topic(item)[:10]: item for key in ("abi", "token_abi", "pair_abi", "treasury_abi")
                          for item in self.source[key] if item["type"] == "function"}
        self.start, self.snapshot = 1000, 3600
        self.initial_supply = 1000*UNIT
        self.raw_logs, self.receipts, self.requests = [], {}, []
        self.omit = set()
        self.runtime = "0x6000"
        self.fail_method = None
        self.fail_kind = "permission"
        self.archive_unavailable = False
        self.reorg = False
        self.header_reads = {}

    def raw(self, address, block, tx, index, topics, data, tx_index=0):
        return {"address": address, "blockNumber": hex(block), "blockHash": hash_value(block+10000),
                "transactionHash": hash_value(tx), "transactionIndex": hex(tx_index), "logIndex": hex(index),
                "topics": topics, "data": data, "removed": False}

    def transfer(self, role, sender, recipient, value, block, tx, index):
        return self.raw(self.routes[role]["address"], block, tx, index,
                        [TRANSFER_TOPIC, "0x"+sender[2:].rjust(64,"0"), "0x"+recipient[2:].rjust(64,"0")], "0x"+word(value))

    def sale(self, market=0, payout=UNIT, quote=3000000, block=2891, tx=900):
        event = next(item for item in self.source["abi"] if item.get("name") == "BondCreated")
        values = {"depositor": USER, "marketId": market, "amountIn": quote, "payout": payout, "priceWad": 3*10**18}
        topics = [topic(event)] + ["0x"+encode(field,values[field["name"]]) for field in event["inputs"] if field["indexed"]]
        data = "0x"+"".join(encode(field,values[field["name"]]) for field in event["inputs"] if not field["indexed"])
        logs = [self.transfer("usdg" if market == 0 else "pair", USER, self.routes["treasury"]["address"], quote, block, tx, 0),
                self.transfer("net", ZERO, self.routes["bond"]["address"], payout, block, tx, 1),
                self.raw(self.routes["bond"]["address"], block, tx, 2, topics, data)]
        self.add(logs)
        return logs

    def add(self, logs):
        self.raw_logs.extend(deepcopy(logs))
        row = logs[0]
        self.receipts[row["transactionHash"]] = {"transactionHash": row["transactionHash"], "blockNumber": row["blockNumber"],
            "blockHash": row["blockHash"], "transactionIndex": row["transactionIndex"], "status": "0x1",
            "from": USER, "to": self.routes["bond"]["address"], "contractAddress": None, "logs": deepcopy(logs)}

    def decoded(self, raw):
        return decode_event(raw, self.source["abi"] if raw["address"] == self.routes["bond"]["address"] else self.source["token_abi"])

    def state(self, block, epoch=None):
        supply, used = self.initial_supply, 0
        for raw in self.raw_logs:
            if int(raw["blockNumber"],16) > block:
                continue
            row = self.decoded(raw)
            values = row["values"]
            if raw["address"] == self.routes["net"]["address"]:
                supply += values["value"] if values["from"] == ZERO else 0
                supply -= values["value"] if values["to"] == ZERO else 0
            elif row["event"] == "BondCreated" and (row["blockNumber"]*100-self.start)//bonds.EPOCH_SECONDS == epoch:
                used += values["payout"]
        return supply, used

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
                block = self.snapshot+2 if params[0] == "latest" else int(params[0],16)
                self.header_reads[block] = self.header_reads.get(block,0)+1
                changed = self.reorg and self.header_reads[block] > 1
                value = {"number": hex(block), "hash": hash_value(block+10000+int(changed)), "timestamp": hex(block*100)}
            elif method == "eth_getCode":
                value = self.runtime
            elif method == "eth_call":
                block = int(params[1],16)
                if self.archive_unavailable and block < self.snapshot:
                    responses.append(RpcError("Historical state unavailable", kind="unavailable"))
                    continue
                item = self.selectors[params[0]["data"][:10]]
                name = item["name"]
                address = params[0]["to"]
                arg = int(params[0]["data"][10:] or "0",16)
                bound = dict(bonds.BINDINGS)
                if name in bound:
                    output = self.routes[bound[name]]["address"]
                elif name == "decimals":
                    output = 9 if address == self.routes["net"]["address"] else 6 if address == self.routes["usdg"]["address"] else 18
                elif name == "totalSupply":
                    output = self.state(block)[0]
                elif name == "payoutInEpoch":
                    output = self.state(block,arg)[1]
                elif name == "marketCount":
                    output = 2
                elif name == "quoteToken":
                    output = self.routes["usdg" if arg == 0 else "pair"]["address"]
                elif name == "enabled":
                    output = True
                elif name == "startTime":
                    output = self.start
                elif name == "token0":
                    output = self.routes["net"]["address"]
                elif name == "token1":
                    output = self.routes["usdg"]["address"]
                elif name == "backingPerToken":
                    output = 2*10**18+block
                elif name == "getReserves":
                    output = [100*UNIT, 350*10**6, block*100]
                else:
                    raise AssertionError(name)
                outputs = [output] if len(item["outputs"]) == 1 else output
                value = "0x"+"".join(encode(field,entry) for field,entry in zip(item["outputs"],outputs))
            elif method == "eth_getLogs":
                query = params[0]
                value = []
                for row in self.raw_logs:
                    if (row["transactionHash"], int(row["logIndex"],16)) in self.omit:
                        continue
                    if row["address"] != query["address"] or not int(query["fromBlock"],16) <= int(row["blockNumber"],16) <= int(query["toBlock"],16):
                        continue
                    if all(wanted is None or row["topics"][i] in (wanted if isinstance(wanted,list) else [wanted])
                           for i,wanted in enumerate(query["topics"])):
                        value.append(deepcopy(row))
            elif method == "eth_getTransactionReceipt":
                value = deepcopy(self.receipts.get(params[0]))
            else:
                raise AssertionError(method)
            responses.append(value)
        return responses

    def patches(self):
        stack = ExitStack()
        original = bonds.load_json
        stack.enter_context(patch.object(bonds,"load_json",side_effect=lambda path:
            self.evidence if path == "assets/contracts/bond-depository-source-evidence.json" else original(path)))
        fixture = self
        stack.enter_context(patch.object(Context,"_exchange_once",lambda ctx,requests: fixture.exchange(ctx,requests)))
        return stack

    def run(self, confirm=True, **options):
        args = SimpleNamespace(epochs=10, chunk_blocks=100000, discovery=None)
        vars(args).update(options)
        with self.patches():
            ctx = Context("standard-bonds",deadline=60)
            try:
                ctx.pin(str(self.snapshot))
                bonds.run(ctx,args)
                if confirm:
                    ctx.recheck()
                return json.loads(serialize_result(ctx.result))
            finally:
                ctx.close()


def smoke(args=None):
    fixture = Fixture()
    fixture.sale(payout=2*UNIT)
    with fixture.patches(), patch.object(analytics,"_PROCESS_STARTED",time.monotonic()):
        return analytics.main(args or ["standard-bonds","--detail","summary","--deadline","60"])


class StandardBondTests(unittest.TestCase):
    def test_default_ten_completed_keeps_inactive_epochs_and_excludes_ongoing(self):
        fixture = Fixture()
        fixture.sale()
        fixture.sale(block=3500,tx=901)
        result = fixture.run()
        self.assertEqual(result["metrics"]["window"]["selected_epochs"],list(range(2,12)))
        self.assertEqual(result["metrics"]["window"]["ongoing_epoch_excluded"]["epoch"],12)
        self.assertEqual(result["metrics"]["totals"]["purchases"],1)
        self.assertEqual(len(result["metrics"]["epochs"]),10)
        self.assertTrue(result["coverage"]["collection_complete"])
        self.assertEqual(result["metrics"]["epochs"][0]["totals"]["purchases"],0)

    def test_opening_nav_and_spot_use_strict_prior_block(self):
        result = Fixture().run()
        row = next(row for row in result["metrics"]["epochs"] if row["epoch"] == 10)
        self.assertEqual(row["opening_header"]["number"],2889)
        self.assertLess(row["opening_header"]["timestamp"],row["start_timestamp"])
        self.assertEqual(row["opening_prices"]["nav"]["raw"],str(2*10**18+2889))
        self.assertEqual(row["opening_prices"]["market_spot"]["numerator"],"7")
        self.assertEqual(row["opening_prices"]["market_spot"]["denominator"],"2")

    def test_usdg_and_lp_receipts_are_distinct_with_full_window_totals(self):
        fixture = Fixture()
        fixture.sale(payout=UNIT)
        fixture.sale(market=1,payout=UNIT,quote=10**18,block=2892,tx=901)
        totals = fixture.run()["metrics"]["totals"]
        self.assertEqual(totals["net_sold"]["raw"],str(2*UNIT))
        self.assertEqual(totals["direct_usdg_received"]["raw"],"3000000")
        self.assertEqual(totals["lp_received"]["raw"],str(10**18))
        self.assertEqual(totals["market_0_purchases"],1)
        self.assertEqual(totals["market_1_purchases"],1)

    def test_burn_between_purchases_can_be_first_crossing_and_mint_reopens(self):
        fixture = Fixture()
        fixture.sale(payout=1250000000)
        fixture.add([fixture.transfer("net",USER,ZERO,200*UNIT,2892,901,0)])
        fixture.add([fixture.transfer("net",ZERO,USER,400*UNIT,2893,902,0)])
        row = next(row for row in fixture.run()["metrics"]["epochs"] if row["epoch"] == 10)
        self.assertEqual(row["sellout"]["first_crossing"]["transaction_hash"],hash_value(901))
        self.assertEqual(row["sellout"]["seconds_to_sellout"],200)
        self.assertGreater(int(row["reconstruction"]["transactions"][-1]["available_net"]["raw"]),UNIT)

    def test_exact_one_net_is_not_below_and_transient_intra_transaction_is_ignored(self):
        fixture = Fixture()
        rows = [fixture.transfer("net",USER,ZERO,600*UNIT,2891,900,0),
                fixture.transfer("net",ZERO,USER,600*UNIT,2891,900,1)]
        model = bonds.reconstruct_epoch([fixture.decoded(row) for row in rows],1000*UNIT,0,289000,{2891:289100})
        self.assertIsNone(model["first_below_one_net"])
        model = bonds.reconstruct_epoch([fixture.decoded(rows[0])],1000*UNIT,0,289000,{2891:289100})
        self.assertEqual(model["transactions"][0]["available_net"]["raw"],str(UNIT))
        self.assertIsNone(model["first_below_one_net"])
        self.assertIsNone(bonds.reconstruct_epoch([],0,0,289000,{})["first_below_one_net"])

    def test_post_deposit_mint_changes_cap_before_threshold(self):
        fixture = Fixture()
        fixture.sale(payout=1500000001)
        row = next(row for row in fixture.run()["metrics"]["epochs"] if row["epoch"] == 10)
        self.assertEqual(row["sellout"]["status"],"not_reached")
        self.assertGreater(int(row["reconstruction"]["transactions"][0]["available_net"]["raw"]),UNIT)

    def test_missing_receipt_never_becomes_zero_cash_total(self):
        fixture = Fixture()
        logs = fixture.sale()
        del fixture.receipts[logs[0]["transactionHash"]]
        result = fixture.run()
        self.assertIsNone(result["metrics"]["totals"])
        self.assertFalse(result["coverage"]["collection_complete"])

    def test_silent_empty_sales_are_detected_by_receipt_and_epoch_counter(self):
        fixture = Fixture()
        logs = fixture.sale()
        fixture.omit.add((logs[-1]["transactionHash"],2))
        result = fixture.run()
        self.assertIsNone(result["metrics"]["totals"])
        self.assertFalse(result["coverage"]["receipt_reconciliation"]["collection_complete"])

    def test_empty_all_logs_cannot_override_nonzero_payout(self):
        fixture = Fixture()
        logs = fixture.sale()
        fixture.omit.update((row["transactionHash"],int(row["logIndex"],16)) for row in logs)
        self.assertIsNone(fixture.run()["metrics"]["totals"])

    def test_unconfirmed_snapshot_and_missing_archives_suppress_results(self):
        fixture = Fixture()
        self.assertIsNone(fixture.run(confirm=False)["metrics"]["totals"])
        fixture = Fixture()
        fixture.archive_unavailable = True
        result = fixture.run()
        self.assertIsNone(result["metrics"]["totals"])
        self.assertTrue(all(row["sellout"]["status"] == "unknown" for row in result["metrics"]["epochs"]))

    def test_permission_reorg_and_wrong_runtime_fail_closed(self):
        for failure in ("permission","reorg","runtime"):
            with self.subTest(failure=failure):
                fixture = Fixture()
                if failure == "permission":
                    fixture.fail_method = "eth_getLogs"
                elif failure == "reorg":
                    fixture.reorg = True
                else:
                    fixture.runtime = "0x6001"
                with self.assertRaises(RpcError):
                    fixture.run()

    def test_quote_leg_ambiguity_is_unknown_not_event_cash(self):
        fixture = Fixture()
        logs = fixture.sale()
        receipt = fixture.receipts[logs[0]["transactionHash"]]
        receipt["logs"][1]["logIndex"] = "0x3"
        receipt["logs"][2]["logIndex"] = "0x4"
        duplicate = deepcopy(logs[0])
        duplicate["logIndex"] = "0x1"
        receipt["logs"].insert(1,duplicate)
        relevant = [fixture.decoded(row) for row in receipt["logs"] if row["address"] in (fixture.routes["net"]["address"],fixture.routes["bond"]["address"])]
        checked = bonds.reconcile_receipt(receipt,relevant,fixture.routes,fixture.source)
        self.assertFalse(checked["matched"])
        self.assertEqual(checked["direct_usdg_received"]["raw"],"0")
        self.assertIsNone(checked["sales"][0]["quote_receipt"])

    def test_beneficiary_is_not_mistaken_for_payer(self):
        fixture = Fixture()
        logs = fixture.sale()
        receipt = fixture.receipts[logs[0]["transactionHash"]]
        receipt["logs"][0]["topics"][1] = "0x"+("cd"*20).rjust(64,"0")
        relevant = [fixture.decoded(row) for row in logs[1:]]
        checked = bonds.reconcile_receipt(receipt,relevant,fixture.routes,fixture.source)
        self.assertTrue(checked["matched"])
        self.assertNotEqual(checked["sales"][0]["payer"],checked["sales"][0]["beneficiary"])

    def test_cli_summary_keeps_complete_totals_without_full_event_rows(self):
        out = io.StringIO()
        with redirect_stdout(out):
            status = smoke()
        result = json.loads(out.getvalue())
        self.assertEqual(status,0)
        self.assertEqual(result["metrics"]["totals"]["purchases"],1)
        self.assertNotIn("events",result["metrics"])
        self.assertTrue(result["coverage"]["collection_complete"])

    def handoff(self, fixture, **overrides):
        current = (fixture.snapshot*100-fixture.start)//bonds.EPOCH_SECONDS
        first = (fixture.start+(current-10)*bonds.EPOCH_SECONDS-1)//100+1
        last = (fixture.start+current*bonds.EPOCH_SECONDS-1)//100
        document = {"schema_version": 1,
                    "snapshot": {"block_number": fixture.snapshot, "block_hash": hash_value(fixture.snapshot+10000)},
                    "block_range": [first,last], "complete": True,
                    "source": {"url": "https://robinhoodchain.blockscout.com/api?apikey=not-retained",
                               "method": "blockscout_v1_logs", "coverage_basis": "paginated_exact_window_all_three_filters"},
                    "transaction_hashes": list(fixture.receipts)}
        document.update(overrides)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name).resolve()/"discovery.json"
        path.write_text(json.dumps(document))
        return str(path)

    def test_supplied_discovery_reconciles_without_rpc_logs_and_redacts_url(self):
        fixture = Fixture()
        fixture.sale()
        result = fixture.run(discovery=self.handoff(fixture))
        self.assertEqual(result["metrics"]["totals"]["purchases"],1)
        self.assertEqual(result["resources"]["event_rows_accepted"], 2)
        self.assertFalse(any(method == "eth_getLogs" for method,_ in fixture.requests))
        self.assertEqual(result["coverage"]["supplied_discovery"]["source_origin"],"https://robinhoodchain.blockscout.com")
        self.assertNotIn("not-retained",json.dumps(result))
        self.assertIn("Supplied index",result["coverage"]["completeness_basis"])

    def test_supplied_discovery_stops_before_admitting_over_budget_events(self):
        fixture = Fixture()
        fixture.sale()
        args = SimpleNamespace(epochs=10, chunk_blocks=100000, discovery=self.handoff(fixture))
        with fixture.patches():
            ctx = Context("standard-bonds", deadline=60)
            try:
                ctx.pin(str(fixture.snapshot))
                ctx._row_limit = 1
                with self.assertRaises(StopRun) as stopped:
                    bonds.run(ctx, args)
                self.assertEqual(stopped.exception.reason, "event_row_limit")
                self.assertEqual(ctx._rows, 0)
                self.assertEqual(ctx.result["metrics"]["events"], [])
                self.assertIsNone(ctx.result["metrics"]["totals"])
            finally:
                ctx.close()

    def test_wrong_pin_window_and_incomplete_handoff_are_rejected(self):
        for override in ({"snapshot":{"block_number":3601,"block_hash":hash_value(13600)}},
                         {"block_range":[0,1]}, {"source":{}}):
            with self.subTest(override=override):
                fixture = Fixture()
                fixture.sale()
                with self.assertRaises(RpcError):
                    fixture.run(discovery=self.handoff(fixture,**override))
                self.assertFalse(any(method == "eth_getTransactionReceipt" for method,_ in fixture.requests))

    def test_false_source_complete_suppresses_epoch_totals_and_counts(self):
        fixture = Fixture()
        fixture.sale()
        result = fixture.run(discovery=self.handoff(fixture,complete=False))
        self.assertIsNone(result["metrics"]["totals"])
        self.assertEqual(result["metrics"]["observed_subtotal"]["purchases"],1)
        self.assertTrue(all(row["totals"] is None and row["sellout"]["status"] == "unknown" for row in result["metrics"]["epochs"]))

    def test_omitted_external_mint_handoff_fails_archive_reconciliation(self):
        fixture = Fixture()
        fixture.sale()
        fixture.add([fixture.transfer("net",ZERO,USER,200*UNIT,2892,901,0)])
        result = fixture.run(discovery=self.handoff(fixture,transaction_hashes=[hash_value(900)]))
        self.assertIsNone(result["metrics"]["totals"])
        self.assertFalse(result["coverage"]["collection_complete"])

    def test_handoff_rejects_symlink_duplicate_hashes_and_credentials(self):
        fixture = Fixture()
        fixture.sale()
        path = self.handoff(fixture)
        link = Path(path).with_name("linked.json")
        link.symlink_to(path)
        with self.assertRaises(RpcError):
            fixture.run(discovery=str(link))
        with self.assertRaises(RpcError):
            fixture.run(discovery=self.handoff(fixture,transaction_hashes=[hash_value(900)]*2))
        source = {"url":"https://secret@provider.example/api","method":"authorized_index",
                  "coverage_basis":"paginated_exact_window_all_three_filters"}
        with self.assertRaises(RpcError):
            fixture.run(discovery=self.handoff(fixture,source=source))

    def test_other_authorized_index_origin_is_provenance_not_fetch_authority(self):
        fixture = Fixture()
        fixture.sale()
        source = {"url":"https://provider.example/key/private?token=secret","method":"authorized_index",
                  "coverage_basis":"paginated_exact_window_all_three_filters"}
        result = fixture.run(discovery=self.handoff(fixture,source=source))
        self.assertEqual(result["coverage"]["supplied_discovery"]["source_origin"],"https://provider.example")
        self.assertNotIn("secret",json.dumps(result))

    def test_catalog_has_source_body_proof_and_read_only_family(self):
        interface = load_json("assets/analytics/standard-bonds-interface.json")
        evidence = load_json("assets/contracts/bond-depository-source-evidence.json")
        self.assertTrue(any("_checkEpochCap" in row["text"] for row in evidence["contracts"]["bond"]["excerpts"]))
        self.assertTrue(any("totalSupply -= amount" in row["text"] for row in evidence["contracts"]["net"]["excerpts"]))
        self.assertEqual(evidence["constants"]["vesting_seconds"],172800)
        self.assertTrue(all(row.get("stateMutability") in ("view","pure") for values in (interface[key] for key in ("abi","token_abi","pair_abi","treasury_abi")) for row in values if row["type"] == "function"))


if __name__ == "__main__":
    unittest.main()

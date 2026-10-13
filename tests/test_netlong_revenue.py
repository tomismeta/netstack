"""Synthetic revenue evidence over the real CLI, Context and guarded HTTPS I/O."""
from collections import Counter, defaultdict
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analytics
import netstack_core as core
import netstack_netlong as netlong
import netstack_netlong_revenue as revenue
from test_receipts import Fixture as HTTPSFixture, ProviderFailure, SECRET, URL, block_hash


OPENING, START, END = 9, 10, 20
TRADER = "0x" + "71" * 20
DYNAMIC_DESK = "0x" + "72" * 20
DYNAMIC_TOKEN = "0x" + "73" * 20
OTHER_ACCOUNT = "0x" + "74" * 20
FUTURES_FEE = 10**18 + 7
MARGIN_BUY_FEE, MARGIN_SELL_FEE = 13, 17


def word(value):
    integer = int(value, 16) if isinstance(value, str) else int(value)
    return format(integer % (1 << 256), "064x")


def words(*values):
    return "0x" + "".join(word(value) for value in values)


def transaction(number):
    return "0x" + word(5000 + number)


def encode_output(field, value):
    if field["type"] == "tuple":
        return "".join(encode_output(child, value[child["name"]]) for child in field["components"])
    return word(value)


def matches_log(row, query):
    if not int(query["fromBlock"], 16) <= int(row["blockNumber"], 16) <= int(query["toBlock"], 16):
        return False
    addresses = query["address"]
    if row["address"] not in (addresses if isinstance(addresses, list) else [addresses]):
        return False
    for index, requested in enumerate(query.get("topics", [])):
        if requested is None:
            continue
        accepted = requested if isinstance(requested, list) else [requested]
        if index >= len(row["topics"]) or row["topics"][index] not in accepted:
            return False
    return True


class RevenueFixture(HTTPSFixture):
    """Only provider I/O and reviewed toy runtime identities are substituted."""

    def __init__(self):
        super().__init__()
        self.routes = core.resolve_routes("netlong-revenue")
        self.addresses = {key: row["address"] for key, row in self.routes.items() if key != "_route"}
        self.source = deepcopy(core.load_json("assets/analytics/netlong-interface.json"))
        for model in self.source["models"]:
            model.update(runtime_bytes=2,
                         normalized_sha256=hashlib.sha256(bytes.fromhex("6000")).hexdigest(),
                         immutable_ranges=[], immutable_groups=[])
        self.calls = {}
        self.code_values = {}
        self.documents = []
        self.catalogs = {
            family: core.load_json("assets/contracts/" + filename)
            for family, filename in (
                ("vault", "netlong-futures-vault.json"),
                ("futures", "netlong-futures-net.json"),
                ("margin", "netlong-margin-desk.json"),
            )
        }
        self.revenue_source = deepcopy(core.load_json("assets/analytics/netlong-revenue-interface.json"))
        for model in self.revenue_source["models"]:
            model.update(runtime_bytes=2,
                         normalized_sha256=hashlib.sha256(bytes.fromhex("6000")).hexdigest(),
                         immutable_ranges=[], immutable_groups=[])
        self.functions = {}
        for filename in ("netlong-interface.json", "netlong-revenue-interface.json"):
            source = core.load_json("assets/analytics/" + filename)
            for key, abi in source.items():
                if key.endswith("_abi"):
                    for item in abi:
                        if item.get("type") == "function":
                            self.functions[core.topic(item)[:10]] = item
        self.configure()

    def set_call(self, address, name, value, args=(), block=None):
        for number in (OPENING, END) if block is None else (block,):
            self.calls[(number, address, name, tuple(args))] = value

    def set_state(self, role, values, block=None):
        for name, value in values.items():
            self.set_call(self.addresses[role], name, value, block=block)

    def configure(self):
        a = self.addresses
        self.known_desk = core.resolve_routes("netlong")["net"]["address"]
        self.desks = [self.known_desk, DYNAMIC_DESK]
        self.set_state("vault", {
            "deskCount": 2, "balanceWs": 100 * 10**18, "totalFreeWs": 20 * 10**18,
            "totalLockedWs": 10 * 10**18, "clearingReserveWs": 0, "totalOwedWs": 0,
            "equityWs": 70 * 10**18, "subscribedWs": 70 * 10**18, "totalShares": 70 * 10**18,
            "sharePriceWad": 10**18, "pendingRedeemWs": 0, "adlEpoch": 1, "adlUnpaidWs": 0,
        })
        for index, desk in enumerate(self.desks):
            self.set_call(a["vault"], "deskAt", desk, (index,))
            self.set_call(a["vault"], "desks", {
                "registered": True, "skewShareBps": 1000, "skewUsdWad": -23,
                "oiUsdWad": 100, "lockedWs": 10,
            }, (desk,))
            for name, value in (("vault", a["vault"]), ("oracle", a["oracle"]),
                                ("carryLongWad", -31), ("carryShortWad", 29), ("lastCarryAt", 1000)):
                self.set_call(desk, name, value)
        self.set_state("margin", {
            "pot": a["pot"], "marginOracle": a["oracle"], "twapSource": a["twap"],
            "usdg": a["usdg"], "feeRouter": a["margin_router"], "tokenCount": 1,
        })
        self.set_call(a["margin"], "tokenAt", DYNAMIC_TOKEN, (0,))
        self.set_call(a["margin"], "listings", {
            "allowed": True, "measuredAt": 1000, "tokenDecimals": 9, "listed": True, "probeOk": True,
            "ownerRisk": False, "pool": OTHER_ACCOUNT, "quoteIsWeth": False,
            "depthUsdWad": 100 * 10**18, "sigmaHBps": 100, "maxLeverageWad": 2 * 10**18,
            "safeCapUsdWad": 50 * 10**18, "safeMaxLeverageWad": 2 * 10**18,
            "capUsedWad": 10 * 10**18, "notionalUsdWad": 10 * 10**18, "totalShares": 100,
        }, (DYNAMIC_TOKEN,))
        self.set_state("pot", {
            "desk": a["margin"], "usdg": a["usdg"], "feeRouter": a["margin_router"], "cashUsdg": 100 * 10**6,
            "idleUsdg": 100 * 10**6, "insuranceUsdg": 0, "heldWs": 0, "insuranceWs": 0,
            "heldWsValueUsdg": 0, "totalPrincipalUsdg": 20 * 10**6, "totalDebtUsdg": 20 * 10**6,
            "owedUsdg": 0, "equityUsdg": 120 * 10**6, "totalShares": 120 * 10**6,
            "sharePriceWad": 10**18, "borrowRateWad": 10**15, "wsCreditPerWsWad": 10**18,
        })
        self.set_state("futures_router", {
            "wsNet": a["wsnet"], "sNet": a["snet"], "net": a["net"],
            "usdg": a["usdg"], "treasury": a["treasury"],
        })
        for asset, decimals in (("wsnet", 18), ("usdg", 6), ("net", 9)):
            self.set_call(a[asset], "decimals", decimals)
            for endpoint in ("vault", "pot", "futures_router", "margin_router", "treasury"):
                balance = 100 * 10**18 if (asset, endpoint) == ("wsnet", "vault") else (
                    100 * 10**6 if (asset, endpoint) == ("usdg", "pot") else 0)
                self.set_call(a[asset], "balanceOf", balance, (a[endpoint],))
        self.set_call(DYNAMIC_TOKEN, "decimals", 9)

    def activity(self):
        a = self.addresses
        settlement = self.add_event("vault", "Settled", {
            "desk": DYNAMIC_DESK, "trader": TRADER, "pnlWs": -23, "feeWs": FUTURES_FEE,
            "penaltyWs": 0, "paidWs": 0, "deferredWs": 0, "adlClaimWs": 0,
        }, block=START)
        self.add_transfer("wsnet", a["vault"], a["futures_router"], FUTURES_FEE,
                          block=START, index=1)
        self.add_event("futures", "Filled", {
            "commitId": 1, "trader": TRADER, "isLong": True, "sizeUsdWad": 101,
            "priceWad": 10**18, "rung": 1, "marginWs": 103, "feeWs": 11,
        }, address=DYNAMIC_DESK, block=END)
        self.add_transfer("wsnet", a["vault"], a["futures_router"], 11, block=END, index=1)
        self.add_event("margin", "Bought", {
            "id": 1, "trader": TRADER, "token": DYNAMIC_TOKEN, "spendUsdg": 107, "units": 109,
            "fillPriceWad": 10**18, "feeUsdg": MARGIN_BUY_FEE, "by": OTHER_ACCOUNT,
        }, block=11)
        self.add_transfer("usdg", a["margin"], a["margin_router"], MARGIN_BUY_FEE, block=11, index=1)
        self.add_event("margin", "Sold", {
            "id": 2, "trader": TRADER, "token": DYNAMIC_TOKEN, "reason": 0, "units": 113,
            "proceedsUsdg": 127, "feeUsdg": MARGIN_SELL_FEE, "penaltyUsdg": 0,
            "debtRepaidUsdg": 131, "seizedWs": 0, "shortfallUsdg": 0, "returnedUsdg": 137,
            "by": OTHER_ACCOUNT,
        }, block=12)
        self.add_transfer("usdg", a["margin"], a["margin_router"], MARGIN_SELL_FEE, block=12, index=1)
        self.add_transfer("net", OTHER_ACCOUNT, a["treasury"], 19, block=13)
        self.set_state("vault", {
            "balanceWs": 100 * 10**18 - FUTURES_FEE - 11,
            "totalFreeWs": 20 * 10**18 - FUTURES_FEE - 11 - 23,
            "equityWs": 70 * 10**18 + 23,
        }, block=END)
        self.set_state("pot", {"totalDebtUsdg": 20 * 10**6 + 4, "equityUsdg": 120 * 10**6 + 3}, block=END)
        for asset, endpoint, value in (
            ("wsnet", "vault", 100 * 10**18 - FUTURES_FEE - 11),
            ("wsnet", "futures_router", FUTURES_FEE + 11),
            ("usdg", "margin_router", MARGIN_BUY_FEE + MARGIN_SELL_FEE), ("net", "treasury", 19),
        ):
            self.set_call(a[asset], "balanceOf", value, (a[endpoint],), block=END)
        return settlement

    def add_event(self, family, name, values, *, block=START, tx=None, index=0, address=None):
        event = next(item for item in self.catalogs[family]["events"] if item["name"] == name)
        indexed, data = [], []
        for field in event["inputs"]:
            (indexed if field["indexed"] else data).append(values[field["name"]])
        row = self.raw_log(address or self.addresses[family], block, tx or transaction(block), index,
                           [event["topic0"], *["0x" + word(value) for value in indexed]], words(*data))
        self.add_log(row)
        return row

    def raw_log(self, address, block, tx, index, topics, data):
        return {"address": address, "blockNumber": hex(block), "blockHash": block_hash(block),
                "transactionHash": tx, "transactionIndex": "0x0", "logIndex": hex(index),
                "topics": topics, "data": data, "removed": False}

    def add_transfer(self, asset, sender, receiver, amount, *, block=START, tx=None, index=0):
        row = self.raw_log(self.addresses[asset], block, tx or transaction(block), index,
                           [core.TRANSFER_TOPIC, "0x" + word(sender), "0x" + word(receiver)], words(amount))
        self.add_log(row)
        return row

    def add_log(self, row, *, scanned=True):
        if scanned:
            self.logs.append(deepcopy(row))
        tx = row["transactionHash"]
        if tx not in self.receipts:
            self.receipts[tx] = {
                "transactionHash": tx, "blockNumber": row["blockNumber"], "blockHash": row["blockHash"],
                "transactionIndex": "0x0", "status": "0x1", "from": TRADER,
                "to": self.addresses["vault"], "contractAddress": None, "logs": [],
            }
        self.receipts[tx]["logs"].append(deepcopy(row))

    def answer(self, method, params):
        if self.override is not None:
            handled, value = self.override(method, params)
            if handled:
                return value
        if method == "eth_call":
            request, tag = params
            if set(request) != {"to", "data"} or int(tag, 16) not in (OPENING, END):
                raise AssertionError("Unpinned or extended contract call")
            data = request["data"]
            item = self.functions[data[:10]]
            arguments = tuple(
                "0x" + data[10 + 64 * index + 24:10 + 64 * (index + 1)] if field["type"] == "address"
                else int(data[10 + 64 * index:10 + 64 * (index + 1)], 16)
                for index, field in enumerate(item["inputs"])
            )
            value = self.calls[(int(tag, 16), request["to"], item["name"], arguments)]
            if isinstance(value, ProviderFailure):
                return value
            fields = item["outputs"]
            if len(fields) == 1:
                return "0x" + encode_output(fields[0], value)
            return "0x" + "".join(encode_output(field, value[field["name"]]) for field in fields)
        if method == "eth_getCode":
            number = int(params[1], 16)
            if number not in (OPENING, END):
                raise AssertionError("Code identity outside requested boundaries")
            return self.code_values.get((number, params[0]), "0x6000")
        if method == "eth_getLogs":
            return deepcopy([row for row in self.logs if matches_log(row, params[0])])
        # Avoid invoking the override twice through the shared HTTPS fixture.
        override, self.override = self.override, None
        try:
            return super().answer(method, params)
        finally:
            self.override = override

    def patches(self):
        stack = super().patches()
        original_load = core.load_json

        def load(path):
            if path == "assets/analytics/netlong-interface.json":
                return deepcopy(self.source)
            if path == "assets/analytics/netlong-revenue-interface.json":
                return deepcopy(self.revenue_source)
            return original_load(path)

        stack.enter_context(patch.object(netlong, "load_json", side_effect=load))
        stack.enter_context(patch.object(revenue, "load_json", side_effect=load))
        original_output = core.Context._atomic_output

        def capture(ctx, text):
            self.documents.append(json.loads(text))
            original_output(ctx, text)

        stack.enter_context(patch.object(core.Context, "_atomic_output", capture))
        return stack

    def run_cli(self, *extra, detail="summary", interval=None):
        with tempfile.TemporaryDirectory(prefix="netlong-revenue-") as directory:
            checkpoint = Path(directory).resolve() / "evidence.json"
            with self.patches(), patch.object(analytics, "_PROCESS_STARTED", time.monotonic()), \
                    redirect_stdout(io.StringIO()) as output:
                status = analytics.main([
                    "netlong-revenue", *(interval or ("--from-block", str(START))), "--block", str(END),
                    "--chunk-blocks", "10", "--deadline", "30", "--detail", detail,
                    "--output", str(checkpoint), *extra,
                ])
            saved = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
        return status, saved, json.loads(output.getvalue())


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from dictionaries(child)
    elif isinstance(value, list):
        for child in value:
            yield from dictionaries(child)


class NetLongRevenueTests(unittest.TestCase):
    def test_projection_preserves_evidence_and_qualifies_boundaries_independently(self):
        fixture = RevenueFixture()
        fixture.activity()
        status, full, _ = fixture.run_cli()
        self.assertEqual(status, 0, full)
        for checkpoint in fixture.documents:
            before = deepcopy(checkpoint)
            projected = revenue.prepare_result(checkpoint)
            self.assertEqual(checkpoint, before)
            self.assertEqual(projected, revenue.prepare_result(checkpoint))
            self.assertEqual(projected, revenue.prepare_result(projected))

        baseline = deepcopy(full)
        observed = [
            row["observed_subtotal"]
            for row in dictionaries(full["metrics"]["observations"])
            if "observed_subtotal" in row]
        for side in revenue.SIDES:
            for state in ("absent", "unconfirmed", "mismatch"):
                with self.subTest(side=side, state=state):
                    source = deepcopy(full)
                    if state == "absent":
                        del source["metrics"]["boundaries"][side]
                    else:
                        source["metrics"]["boundaries"][side]["recheck_status"] = state
                    before = deepcopy(source)
                    projected = revenue.prepare_result(source)
                    self.assertEqual(source, before)
                    self.assert_incomplete(projected)
                    scope = projected["coverage"]["requested_scope"]
                    self.assertTrue(scope["raw_acquisition_complete"])
                    self.assertFalse(scope["boundaries_confirmed"])
                    self.assertEqual(scope["snapshot_confirmation"],
                                     "invalid" if state == "mismatch" else "unconfirmed")
                    self.assertEqual(observed, [
                        row["observed_subtotal"]
                        for row in dictionaries(projected["metrics"]["observations"])
                        if "observed_subtotal" in row])
                    self.assertEqual(projected, revenue.prepare_result(projected))
                    other = next(boundary for boundary in revenue.SIDES if boundary != side)
                    self.assertEqual(projected["metrics"]["boundaries"][other]["recheck_status"], "confirmed")
                    self.assertEqual(projected["metrics"]["events"], full["metrics"]["events"])
                    # Retained raw discovery facts permit fresh qualification;
                    # previously demoted flags are not failed acquisition.
                    recovered = deepcopy(projected)
                    recovered["metrics"]["boundaries"][side] = deepcopy(full["metrics"]["boundaries"][side])
                    restored = revenue.prepare_result(recovered)
                    self.assertTrue(restored["coverage"]["requested_scope"]["collection_complete"])
                    self.assertEqual(restored["metrics"]["observations"], full["metrics"]["observations"])
                    self.assertEqual(projected["metrics"]["transfers"], full["metrics"]["transfers"])

        for kind in ("permission", "integrity"):
            source = deepcopy(full)
            source["errors"].append({"kind": kind})
            projected = revenue.prepare_result(source)
            self.assert_incomplete(projected)
            self.assertEqual(projected["coverage"]["requested_scope"]["snapshot_confirmation"], "invalid")
            self.assertTrue(projected["coverage"]["requested_scope"]["raw_acquisition_complete"])

        # Boundary confirmation cannot compensate for unfinished acquisition,
        # even when all observations from a prior checkpoint remain available.
        source = deepcopy(full)
        source["metrics"]["acquisition_finished"] = False
        projected = revenue.prepare_result(source)
        self.assert_incomplete(projected)
        self.assertTrue(projected["coverage"]["requested_scope"]["boundaries_confirmed"])
        self.assertFalse(projected["coverage"]["requested_scope"]["raw_acquisition_complete"])
        self.assertEqual(observed, [
            row["observed_subtotal"]
            for row in dictionaries(projected["metrics"]["observations"])
            if "observed_subtotal" in row])
        self.assertEqual(full, baseline)

    def assert_incomplete(self, document):
        self.assertFalse(document["coverage"].get("requested_scope", {}).get("collection_complete", False))
        for row in dictionaries(document["metrics"].get("observations", {})):
            if "requested_window_total" in row:
                self.assertIsNone(row["requested_window_total"])
                self.assertFalse(row["collection_complete"])


    def test_pin_denial_reports_uncollected_events_and_unmeasured_router_disposition(self):
        for detail in ("full", "summary"):
            for denied_method in ("eth_chainId", "eth_getBlockByNumber"):
                for interval in (("--from-block", "10"), ("--recent-blocks", "11")):
                    with self.subTest(detail=detail, denied_method=denied_method, interval=interval):
                        fixture = RevenueFixture()
                        fixture.override = lambda method, params: (
                            (True, ProviderFailure("denied " + URL, status=403))
                            if method == denied_method else (False, None))
                        status, full, stdout = fixture.run_cli(detail=detail, interval=interval)
                        self.assertEqual(status, 2, stdout)
                        self.assertEqual(fixture.requests[-1][0], denied_method)
                        self.assertEqual(fixture.contexts[0]._recoveries, 0)
                        self.assertFalse(any(method in ("eth_call", "eth_getLogs", "eth_getCode")
                                             for method, _ in fixture.requests))
                        self.assertTrue(all(response.closed for response in fixture.responses))
                        for document in (full, stdout):
                            self.assert_incomplete(document)
                            scope = document["coverage"]["requested_scope"]
                            self.assertEqual(scope["status"], "not_collected")
                            self.assertFalse(scope["raw_acquisition_complete"])
                            self.assertFalse(scope["boundaries_confirmed"])
                            self.assertEqual(scope["from_block"], 10 if interval[0] == "--from-block" else None)
                            self.assertEqual(scope["recent_blocks"], 11 if interval[0] == "--recent-blocks" else None)
                            self.assertTrue(document["not_proven"])
                            self.assertEqual(document["errors"][0]["kind"], "permission")
                            self.assertNotIn(SECRET, json.dumps(document))
                            self.assertNotIn("block_number", document["snapshot"])
                            self.assertTrue(document["metrics"]["event_coverage"])
                            for row in document["metrics"]["event_coverage"]:
                                self.assertEqual(row["scan_status"], "not_collected")
                                self.assertIsNone(row["address"])
                                self.assertIsNone(row["selected_events"])
                                self.assertIsNone(row["observed_named_event_count"])
                                self.assertFalse(row["selected_scan_complete"])
                            observations = document["metrics"]["observations"]
                            self.assertEqual(observations["status"], "not_collected")
                            self.assertIsNone(observations["requested_window_total"])
                            disposition = observations["router_disposition"]
                            self.assertEqual(disposition["status"], "not_measured")
                            for key in ("addresses", "processing", "unwrap", "unstake", "net_burn"):
                                self.assertIsNone(disposition[key])
                        if detail == "full":
                            self.assertEqual(stdout, full)
                        else:
                            self.assertEqual(stdout["presentation"]["full_checkpoint"], "saved")
                            self.assertEqual(stdout["metrics"]["event_coverage"], full["metrics"]["event_coverage"])
                            self.assertEqual(stdout["metrics"]["observations"]["router_disposition"],
                                             full["metrics"]["observations"]["router_disposition"])

    def test_recent_interval_uses_guarded_pin_and_exact_inclusive_boundaries(self):
        fixture = RevenueFixture()
        fixture.activity()
        status, full, _ = fixture.run_cli("--block", "latest-2", interval=("--recent-blocks", "11"))
        self.assertEqual(status, 0, full)
        scope = full["metrics"]["scope"]
        self.assertEqual((scope["opening_block"], scope["from_block"], scope["to_block"]),
                         (OPENING, START, END))
        self.assertTrue(all(row["recheck_status"] == "confirmed"
                            for row in full["metrics"]["boundaries"].values()))
        log_ranges = [(int(params[0]["fromBlock"], 16), int(params[0]["toBlock"], 16))
                      for method, params in fixture.requests if method == "eth_getLogs"]
        self.assertEqual(set(log_ranges), {(START, END - 1), (END, END)})
        self.assertEqual(sum(params[0] == "latest" for method, params in fixture.requests
                             if method == "eth_getBlockByNumber"), 1)
        self.assertTrue(full["coverage"]["requested_scope"]["collection_complete"])

    def test_recent_interval_rejects_invalid_or_conflicting_counts_before_network(self):
        for interval in (("--recent-blocks", "0"), ("--recent-blocks", "-1"),
                         ("--recent-blocks", "1", "--from-block", "10")):
            with self.subTest(interval=interval):
                fixture = RevenueFixture()
                status, _, result = fixture.run_cli(interval=interval)
                self.assertEqual(status, 1, result)
                self.assertEqual(fixture.requests, [])
                self.assertEqual(fixture.connections, [])

    def test_recent_interval_does_not_silently_clip_at_genesis(self):
        fixture = RevenueFixture()
        status, _, result = fixture.run_cli(interval=("--recent-blocks", str(END + 1)))
        self.assertNotEqual(status, 0, result)
        self.assertTrue(result["errors"])
        self.assertTrue(all(method in ("eth_chainId", "eth_getBlockByNumber")
                            for method, _ in fixture.requests))

    def test_both_products_dynamic_registry_and_exact_signed_evidence(self):
        fixture = RevenueFixture()
        fixture.activity()
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 0, full)
        self.assertTrue(full["coverage"]["requested_scope"]["collection_complete"])
        self.assertEqual(len(fixture.contexts), 1)
        self.assertEqual(fixture.header_reads[OPENING], 2)
        self.assertEqual(fixture.header_reads[END], 2)
        self.assertEqual(full["metrics"]["scope"]["opening_block"], OPENING)
        for side in ("opening", "closing"):
            roster = full["metrics"]["discovery"][side]
            self.assertEqual(set(roster["futures"]["addresses"]), set(fixture.desks))
            self.assertEqual(roster["margin"]["addresses"], [DYNAMIC_TOKEN])
            self.assertTrue(roster["futures"]["collection_complete"])
            self.assertTrue(roster["margin"]["collection_complete"])
            self.assertEqual(full["metrics"]["boundaries"][side]["recheck_status"], "confirmed")
        events = full["metrics"]["events"]
        settlement = next(row for row in events if row["event"] == "Settled")
        self.assertEqual(settlement["values"]["pnlWs"], -23)
        self.assertEqual(settlement["values"]["feeWs"], str(FUTURES_FEE))
        self.assertTrue(all(row["receipt_verified"] for row in events))
        self.assertTrue(any(row["address"] == DYNAMIC_DESK and row["event"] == "Filled" for row in events))
        self.assertTrue(any(row["event"] == "Bought" for row in events))
        self.assertTrue(any(row["event"] == "Sold" for row in events))
        for row in dictionaries(full["metrics"]["observations"]):
            if "raw" in row:
                self.assertTrue(row["raw"] is None or isinstance(row["raw"], str))
        self.assertFalse(any(isinstance(value, float)
                             for row in dictionaries(full["metrics"]["observations"]) for value in row.values()))

    def test_each_event_and_transfer_scope_splits_eleven_blocks_ten_plus_one(self):
        fixture = RevenueFixture()
        fixture.activity()
        status, full, _ = fixture.run_cli()
        self.assertEqual(status, 0, full)
        scopes = defaultdict(list)
        for method, params in fixture.requests:
            if method != "eth_getLogs":
                continue
            query = params[0]
            key = json.dumps({key: value for key, value in query.items()
                              if key not in ("fromBlock", "toBlock")}, sort_keys=True)
            scopes[key].append((int(query["fromBlock"], 16), int(query["toBlock"], 16)))
        self.assertGreater(len(scopes), 4)
        for key, ranges in scopes.items():
            with self.subTest(scope=key):
                self.assertEqual(ranges, [(10, 19), (20, 20)])
        receipt_requests = [params[0] for method, params in fixture.requests
                            if method == "eth_getTransactionReceipt"]
        self.assertEqual(Counter(receipt_requests), Counter({tx: 1 for tx in fixture.receipts}))
        self.assertLessEqual(len(fixture.requests), 750)

    def test_endpoint_roster_union_retains_removed_and_new_entities(self):
        fixture = RevenueFixture()
        vault, margin = fixture.addresses["vault"], fixture.addresses["margin"]
        fixture.set_call(vault, "deskCount", 1, block=OPENING)
        fixture.set_call(vault, "deskAt", fixture.known_desk, (0,), block=OPENING)
        fixture.set_call(vault, "deskCount", 1, block=END)
        fixture.set_call(vault, "deskAt", DYNAMIC_DESK, (0,), block=END)
        fixture.set_call(margin, "tokenCount", 0, block=OPENING)
        fixture.activity()
        _, full, _ = fixture.run_cli()
        discovery = full["metrics"]["discovery"]
        self.assertEqual(discovery["opening"]["futures"]["addresses"], [fixture.known_desk])
        self.assertEqual(discovery["closing"]["futures"]["addresses"], [DYNAMIC_DESK])
        self.assertEqual(discovery["opening"]["margin"]["addresses"], [])
        self.assertEqual(discovery["closing"]["margin"]["addresses"], [DYNAMIC_TOKEN])
        scopes = {row["address"] for row in full["metrics"]["event_scopes"]}
        self.assertTrue(set(fixture.desks).issubset(scopes))
        caveats = json.dumps(full).lower()
        self.assertIn("roster", caveats)
        self.assertIn("intermediate", caveats)

    def test_unknown_or_absent_endpoint_runtime_keeps_gap_not_zero_total(self):
        for code in ("0x6001", "0x"):
            with self.subTest(runtime=code):
                fixture = RevenueFixture()
                fixture.activity()
                fixture.code_values[(OPENING, DYNAMIC_DESK)] = code
                status, full, summary = fixture.run_cli()
                self.assertEqual(status, 2, full)
                self.assertTrue(any(row["address"] == DYNAMIC_DESK and row["status"] != "matched"
                                    for row in full["metrics"]["implementation_checks"]))
                for document in (full, summary):
                    self.assert_incomplete(document)
                self.assertTrue(full["metrics"]["events"])

    def test_missing_registry_entry_is_explicit_even_with_stable_boundaries(self):
        fixture = RevenueFixture()
        fixture.activity()
        fixture.set_call(fixture.addresses["vault"], "deskAt",
                         ProviderFailure("historical state unavailable", status=200), (1,), block=OPENING)
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 2, full)
        self.assertFalse(full["metrics"]["discovery"]["opening"]["futures"]["collection_complete"])
        self.assertTrue(full["errors"])
        for document in (full, summary):
            self.assert_incomplete(document)
        self.assertTrue(all(row["recheck_status"] == "confirmed"
                            for row in full["metrics"]["boundaries"].values()))

    def test_changed_live_binding_is_not_assumed_canonical(self):
        fixture = RevenueFixture()
        fixture.activity()
        fixture.set_call(fixture.addresses["futures_router"], "treasury", OTHER_ACCOUNT, block=END)
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 2, full)
        mismatch = [row for row in full["metrics"]["bindings"]
                    if row["function"] == "treasury" and row["side"] == "closing"]
        self.assertEqual(len(mismatch), 1)
        self.assertFalse(mismatch[0]["matches"])
        self.assertEqual(mismatch[0]["observed"], OTHER_ACCOUNT)
        for document in (full, summary):
            self.assert_incomplete(document)

    def test_receipt_failures_cannot_confirm_assessed_fees(self):
        for failure in ("missing", "failed", "wrong_transaction", "wrong_block", "missing_event", "malformed", "changed_event"):
            with self.subTest(failure=failure):
                fixture = RevenueFixture()
                selected = fixture.activity()
                tx = selected["transactionHash"]
                receipt = fixture.receipts[tx]
                if failure == "missing":
                    fixture.receipts[tx] = None
                elif failure == "failed":
                    receipt["status"] = "0x0"
                elif failure == "wrong_transaction":
                    receipt["transactionHash"] = transaction(999)
                elif failure == "wrong_block":
                    receipt["blockHash"] = block_hash(999)
                elif failure == "missing_event":
                    receipt["logs"] = receipt["logs"][1:]
                elif failure == "malformed":
                    receipt["logs"][0]["data"] = "0x0"
                else:
                    receipt["logs"][0]["data"] = words(-23, FUTURES_FEE + 1, 0, 0, 0, 0)
                status, full, summary = fixture.run_cli()
                self.assertEqual(status, 2, full)
                self.assertTrue(full["errors"])
                for document in (full, summary):
                    self.assert_incomplete(document)
                bad_events = [row for row in full["metrics"]["events"] if row["transactionHash"] == tx]
                self.assertTrue(all(not row["receipt_verified"] for row in bad_events))

    def test_receipt_local_transfer_is_not_global_scan_coverage(self):
        fixture = RevenueFixture()
        selected = fixture.activity()
        extra = fixture.raw_log(fixture.addresses["usdg"], START, selected["transactionHash"], 2,
                                [core.TRANSFER_TOPIC, "0x" + word(TRADER), "0x" + word(OTHER_ACCOUNT)],
                                words(999))
        fixture.add_log(extra, scanned=False)
        status, full, _ = fixture.run_cli()
        self.assertEqual(status, 0, full)
        scanned = {(row["transactionHash"], row["logIndex"]) for row in full["metrics"]["transfers"]}
        self.assertNotIn((selected["transactionHash"], 2), scanned)
        self.assertTrue(any(row["values"]["to"] == OTHER_ACCOUNT
                            for transaction_row in full["metrics"]["transactions"]
                            for row in transaction_row["transfers"]))

    def test_transfer_identity_conflict_between_scoped_directions_is_terminal(self):
        fixture = RevenueFixture()
        fixture.activity()
        transfer = next(row for row in fixture.logs if row["topics"][0] == core.TRANSFER_TOPIC)
        seen = 0

        def conflict(method, params):
            nonlocal seen
            if method == "eth_getLogs" and matches_log(transfer, params[0]):
                seen += 1
                if seen == 2:
                    rows = [deepcopy(row) for row in fixture.logs if matches_log(row, params[0])]
                    for row in rows:
                        if (row["transactionHash"], row["logIndex"]) == (
                                transfer["transactionHash"], transfer["logIndex"]):
                            row["data"] = words(FUTURES_FEE + 1)
                    return True, rows
            return False, None

        fixture.override = conflict
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 2, full)
        self.assertEqual(seen, 2)
        self.assertTrue(any(row["kind"] == "integrity" for row in full["errors"]))
        for document in (full, summary):
            self.assert_incomplete(document)

    def test_http403_is_terminal_redacted_and_does_not_recover(self):
        fixture = RevenueFixture()
        fixture.activity()

        def deny(method, params):
            return (True, ProviderFailure("denied " + URL, status=403)) if method == "eth_getLogs" else (False, None)

        fixture.override = deny
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 2, full)
        self.assertEqual(len(fixture.ranges()), 1)
        self.assertEqual(fixture.requests[-1][0], "eth_getLogs")
        self.assertEqual(fixture.contexts[0]._recoveries, 0)
        self.assertTrue(any(row["kind"] == "permission" for row in full["errors"]))
        self.assertTrue(all(response.closed for response in fixture.responses))
        for document in (full, summary):
            self.assert_incomplete(document)
            self.assertNotIn(SECRET, json.dumps(document))

    def test_classified_provider_limit_splits_only_the_affected_range(self):
        fixture = RevenueFixture()
        fixture.activity()

        def first_range_limit(method, params):
            if method == "eth_getLogs" and len(fixture.ranges()) == 1:
                return True, ProviderFailure(
                    "Under the Free tier plan, you can make eth_getLogs requests with up to a 10 block range. " + URL)
            return False, None

        fixture.override = first_range_limit
        status, full, _ = fixture.run_cli()
        self.assertEqual(status, 0, full)
        self.assertEqual(fixture.ranges()[:4], [(10, 19), (10, 14), (15, 19), (20, 20)])
        self.assertEqual(fixture.contexts[0]._recoveries, 0)
        self.assertEqual(fixture.contexts[0]._range_splits, 1)
        self.assertTrue(full["coverage"]["requested_scope"]["collection_complete"])
        self.assertNotIn(SECRET, json.dumps(full))

    def test_interrupt_or_deadline_preserves_observations_but_no_confirmed_total(self):
        for reason in ("interrupted_by_SIGTERM", "deadline_exhausted"):
            with self.subTest(reason=reason):
                fixture = RevenueFixture()
                fixture.activity()

                def stop_second_page(method, params):
                    if method == "eth_getLogs" and len(fixture.ranges()) == 2:
                        ctx = fixture.contexts[0]
                        if reason == "interrupted_by_SIGTERM":
                            ctx._signal(signal.SIGTERM, None)
                        else:
                            ctx._collect_end = 0
                            ctx.check()
                    return False, None

                fixture.override = stop_second_page
                status, full, summary = fixture.run_cli()
                self.assertEqual(status, 2, full)
                for document in (full, summary):
                    self.assertEqual(document["status"], "partial")
                    self.assertEqual(document["stopping_reason"], reason)
                    self.assert_incomplete(document)
                    self.assertTrue(document["metrics"]["observations"])
                    self.assertTrue(any(row.get("covered_ranges") == [[10, 19]]
                                        and row.get("missing_ranges") == [[20, 20]]
                                        for row in document["coverage"].values() if isinstance(row, dict)))
                self.assertTrue(full["metrics"]["events"])
                self.assertEqual(fixture.requests[-1][0], "eth_getLogs")

    def test_each_boundary_recheck_can_revoke_completion_independently(self):
        for boundary in (OPENING, END):
            for failure in ("mismatch", "missing"):
                with self.subTest(boundary=boundary, failure=failure):
                    fixture = RevenueFixture()
                    fixture.activity()

                    def recheck_failure(method, params):
                        if (method == "eth_getBlockByNumber" and params[0] == hex(boundary)
                                and fixture.header_reads[boundary]):
                            if failure == "missing":
                                return True, None
                            return True, {"number": hex(boundary), "timestamp": hex(1000 + boundary),
                                          "hash": block_hash(999)}
                        return False, None

                    fixture.override = recheck_failure
                    status, full, summary = fixture.run_cli()
                    self.assertEqual(status, 2, full)
                    for document in (full, summary):
                        self.assert_incomplete(document)
                        self.assertFalse(document["coverage"]["requested_scope"]["boundaries_confirmed"])
                        self.assertTrue(document["coverage"]["requested_scope"]["raw_acquisition_complete"])
                    self.assertTrue(full["metrics"]["events"])
                    if failure == "mismatch":
                        self.assertTrue(any(row["kind"] == "integrity" for row in full["errors"]))
                    if boundary == OPENING and failure == "missing":
                        self.assertEqual(full["metrics"]["boundaries"]["closing"]["recheck_status"], "confirmed")

    def test_interim_checkpoints_cannot_publish_complete_scoped_totals(self):
        fixture = RevenueFixture()
        fixture.activity()
        status, full, _ = fixture.run_cli()
        self.assertEqual(status, 0, full)
        unconfirmed = [document for document in fixture.documents
                       if not document["coverage"].get("requested_scope", {}).get("boundaries_confirmed")]
        self.assertTrue(unconfirmed)
        self.assertTrue(any(document["coverage"].get("requested_scope", {}).get("raw_acquisition_complete")
                            for document in unconfirmed))
        for document in unconfirmed:
            self.assert_incomplete(document)
        self.assertTrue(full["coverage"]["requested_scope"]["boundaries_confirmed"])

    def test_router_transfer_receipts_do_not_establish_router_event_activity(self):
        fixture = RevenueFixture()
        fixture.activity()
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 0, full)
        for document in (full, summary):
            rows = document["metrics"]["event_coverage"]
            vault = next(row for row in rows if row["role"] == "vault")
            self.assertEqual(vault["scan_status"], "completed")
            self.assertEqual(vault["observed_named_event_count"], 1)
            self.assertTrue(vault["selected_scan_complete"])
            for role in ("pot", "futures_router", "margin_router", "treasury"):
                row = next(row for row in rows if row["role"] == role)
                self.assertEqual(row["scan_status"], "not_collected")
                self.assertIsNone(row["observed_named_event_count"])
                self.assertFalse(row["selected_scan_complete"])
            router = next(row for row in document["metrics"]["observations"]["router_receipts"]
                          if (row["endpoint"], row["asset"]) == ("futures_router", "wsnet"))
            self.assertEqual(router["observed_subtotal"]["raw"], str(FUTURES_FEE + 11))

    def test_router_transfer_to_zero_is_not_a_measured_processing_or_burn_operation(self):
        fixture = RevenueFixture()
        fixture.activity()
        router = fixture.addresses["futures_router"]
        fixture.set_call(fixture.addresses["net"], "balanceOf", 31, (router,), block=OPENING)
        fixture.set_call(fixture.addresses["net"], "balanceOf", 0, (router,), block=END)
        fixture.add_transfer("net", router, core.ZERO, 31, block=START + 5)
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 0, full)
        for document in (full, summary):
            observations = document["metrics"]["observations"]
            bridge = next(row for row in observations["asset_bridges"]
                          if (row["asset"], row["endpoint"]) == ("net", "futures_router"))
            self.assertEqual(bridge["observed_outgoing"]["raw"], "31")
            self.assertEqual(bridge["residual"]["raw"], "0")
            disposition = observations["router_disposition"]
            self.assertEqual(disposition["status"], "not_measured")
            for operation in ("processing", "unwrap", "unstake", "net_burn"):
                self.assertIsNone(disposition[operation])

    def test_empty_selected_logs_is_scoped_zero_not_zero_protocol_revenue(self):
        fixture = RevenueFixture()
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 0, full)
        self.assertEqual(full["metrics"]["events"], [])
        self.assertTrue(full["coverage"]["requested_scope"]["collection_complete"])
        for document in (full, summary):
            caveats = json.dumps(document.get("not_proven", [])).lower()
            self.assertIn("revenue", caveats)
            self.assertIn("native", caveats)
            self.assertIn("internal", caveats)
            self.assertNotIn("total_revenue", document["metrics"]["observations"])
            for fee in document["metrics"]["observations"]["assessed_fees"]:
                self.assertEqual(fee["requested_window_total"]["raw"], "0")
            self.assertIsNone(document["metrics"]["observations"]["vault_equity_delta"]["economic_result"])
            self.assertIsNone(document["metrics"]["observations"]["pot_state_deltas"]["cash_interest_received"])

    def test_native_fee_amounts_and_receipts_remain_separate_by_basis_and_product(self):
        fixture = RevenueFixture()
        fixture.activity()
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 0, full)
        expected = {("futures", "Settled"): FUTURES_FEE, ("futures", "Filled"): 11,
                    ("margin", "Bought"): MARGIN_BUY_FEE, ("margin", "Sold"): MARGIN_SELL_FEE}
        for document in (full, summary):
            observations = document["metrics"]["observations"]
            fees = {(row["product"], row["assessment_basis"]): row
                    for row in observations["assessed_fees"]}
            self.assertEqual(set(fees), set(expected))
            for key, raw in expected.items():
                quantity = fees[key]["requested_window_total"]
                self.assertEqual(quantity["raw"], str(raw))
                self.assertEqual(quantity["decimals"], 18 if key[0] == "futures" else 6)
                self.assertEqual(fees[key]["event_count"], 1)
                self.assertEqual(fees[key]["receipt_verified_count"], 1)
            self.assertEqual(fees[("futures", "Settled")]["observed_subtotal"]["formatted"],
                             "1.000000000000000007")
            reconciliations = observations["fee_receipt_reconciliation"]
            self.assertEqual(len(reconciliations), 4)
            for row in reconciliations:
                self.assertEqual(row["assessed"]["raw"], str(expected[(row["product"], row["assessment_basis"])]))
                self.assertEqual(row["assessed"], row["router_receipts"])
                self.assertEqual(row["residual"]["raw"], "0")
                self.assertTrue(row["equality"])
            routers = {(row["asset"], row["endpoint"]): row for row in observations["router_receipts"]}
            self.assertEqual(routers[("wsnet", "futures_router")]["observed_subtotal"]["raw"],
                             str(FUTURES_FEE + 11))
            self.assertEqual(routers[("usdg", "margin_router")]["observed_subtotal"]["raw"], "30")
            self.assertEqual(observations["vault_equity_delta"]["observed_subtotal"]["raw"], "23")
            self.assertIsNone(observations["vault_equity_delta"]["economic_result"])

    def test_router_receipt_mismatch_is_exposed_not_fabricated_fee_equality(self):
        fixture = RevenueFixture()
        selected = fixture.activity()
        tx = selected["transactionHash"]
        for rows in (fixture.logs, fixture.receipts[tx]["logs"]):
            for row in rows:
                if row["transactionHash"] == tx and row["topics"][0] == core.TRANSFER_TOPIC:
                    row["data"] = words(FUTURES_FEE - 1)
        _, full, summary = fixture.run_cli()
        for document in (full, summary):
            row = next(row for row in document["metrics"]["observations"]["fee_receipt_reconciliation"]
                       if row["assessment_basis"] == "Settled")
            self.assertEqual(row["assessed"]["raw"], str(FUTURES_FEE))
            self.assertEqual(row["router_receipts"]["raw"], str(FUTURES_FEE - 1))
            self.assertEqual(row["residual"]["raw"], "-1")
            self.assertFalse(row["equality"])
            bridge = next(row for row in document["metrics"]["observations"]["asset_bridges"]
                          if (row["asset"], row["endpoint"]) == ("wsnet", "futures_router"))
            self.assertEqual(bridge["residual"]["raw"], "1")
            self.assertFalse(bridge["reconciled"])

    def test_capital_subscription_and_trader_deposit_are_not_earned_revenue(self):
        fixture = RevenueFixture()
        a = fixture.addresses
        subscribed, deposited = 31 * 10**18, 29 * 10**18
        fixture.add_event("vault", "Subscribed", {"account": TRADER, "ws": subscribed, "shares": subscribed})
        fixture.add_transfer("wsnet", TRADER, a["vault"], subscribed, index=1)
        fixture.add_event("vault", "Deposited", {
            "trader": TRADER, "from": TRADER, "asset": 0, "amountIn": deposited, "ws": deposited,
        }, block=11)
        fixture.add_transfer("wsnet", TRADER, a["vault"], deposited, block=11, index=1)
        fixture.set_state("vault", {
            "balanceWs": 160 * 10**18, "totalFreeWs": 49 * 10**18, "equityWs": 101 * 10**18,
            "subscribedWs": 101 * 10**18, "totalShares": 101 * 10**18,
        }, block=END)
        fixture.set_call(a["wsnet"], "balanceOf", 160 * 10**18, (a["vault"],), block=END)
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 0, full)
        for document in (full, summary):
            observations = document["metrics"]["observations"]
            equity = observations["vault_equity_delta"]
            self.assertEqual(equity["observed_subtotal"]["raw"], str(subscribed))
            self.assertEqual(equity["capital_and_claim_events"]["Subscribed"]["raw"], str(subscribed))
            self.assertEqual(equity["capital_and_claim_events"]["Deposited"]["raw"], str(deposited))
            self.assertIsNone(equity["economic_result"])
            self.assertTrue(all(row["observed_subtotal"]["raw"] == "0" for row in observations["assessed_fees"]))
            bridge = next(row for row in observations["asset_bridges"]
                          if (row["asset"], row["endpoint"]) == ("wsnet", "vault"))
            self.assertEqual(bridge["observed_incoming"]["raw"], str(subscribed + deposited))
            self.assertEqual(bridge["balance_delta"]["raw"], str(subscribed + deposited))
            self.assertEqual(bridge["residual"]["raw"], "0")
            self.assertTrue(bridge["reconciled"])

    def test_pot_indexed_accrual_is_not_cash_interest_or_new_financing(self):
        fixture = RevenueFixture()
        fixture.activity()
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 0, full)
        for document in (full, summary):
            pot = document["metrics"]["observations"]["pot_state_deltas"]
            self.assertEqual(pot["totalDebtUsdg"]["observed_subtotal"]["raw"], "4")
            self.assertEqual(pot["equityUsdg"]["observed_subtotal"]["raw"], "3")
            self.assertEqual(pot["totalPrincipalUsdg"]["observed_subtotal"]["raw"], "0")
            self.assertEqual(pot["cashUsdg"]["observed_subtotal"]["raw"], "0")
            self.assertEqual(pot["outstanding_indexed_interest"]["closing"]["raw"], "4")
            self.assertEqual(pot["totalDebtUsdg"]["observed_subtotal"]["formatted"], "0.000004")
            self.assertIsNone(pot["cash_interest_received"])

    def test_scoped_treasury_receipts_exclude_unrelated_incoming_tokens(self):
        fixture = RevenueFixture()
        a = fixture.addresses
        fixture.set_call(a["net"], "balanceOf", 100, (a["futures_router"],), block=OPENING)
        fixture.set_call(a["net"], "balanceOf", 81, (a["futures_router"],), block=END)
        fixture.set_call(a["net"], "balanceOf", 42, (a["treasury"],), block=END)
        fixture.add_transfer("net", a["futures_router"], a["treasury"], 19, block=START)
        fixture.add_transfer("net", OTHER_ACCOUNT, a["treasury"], 23, block=END)
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 0, full)
        for document in (full, summary):
            observations = document["metrics"]["observations"]
            scoped = next(row for row in observations["treasury_receipts"] if row["asset"] == "net")
            self.assertEqual(scoped["requested_window_total"]["raw"], "19")
            self.assertEqual(scoped["transfer_count"], 1)
            bridge = next(row for row in observations["asset_bridges"]
                          if (row["asset"], row["endpoint"]) == ("net", "treasury"))
            self.assertEqual(bridge["observed_incoming"]["raw"], "42")
            self.assertEqual(bridge["balance_delta"]["raw"], "42")
            self.assertTrue(bridge["reconciled"])
        transfers = full["metrics"]["transfers"]
        self.assertEqual(len(transfers), 2)
        self.assertTrue(all(row["address"] == a["net"] for row in transfers))
        self.assertTrue(all(row["values"]["to"] == a["treasury"] for row in transfers))

    def test_balance_delta_residual_is_unreconciled_not_automatic_profit(self):
        fixture = RevenueFixture()
        fixture.set_call(fixture.addresses["usdg"], "balanceOf", 37,
                         (fixture.addresses["treasury"],), block=END)
        _, full, summary = fixture.run_cli()
        for document in (full, summary):
            observations = document["metrics"]["observations"]
            bridge = next(row for row in observations["asset_bridges"]
                          if (row["asset"], row["endpoint"]) == ("usdg", "treasury"))
            self.assertEqual(bridge["balance_delta"]["raw"], "37")
            self.assertEqual(bridge["observed_net_transfers"]["raw"], "0")
            self.assertEqual(bridge["residual"]["raw"], "37")
            self.assertFalse(bridge["reconciled"])
            receipts = next(row for row in observations["treasury_receipts"] if row["asset"] == "usdg")
            self.assertEqual(receipts["observed_subtotal"]["raw"], "0")

    def test_signed_vault_equity_survives_raw_integer_serialization(self):
        fixture = RevenueFixture()
        fixture.set_state("vault", {"equityWs": -5 * 10**18, "totalOwedWs": 75 * 10**18}, block=OPENING)
        fixture.set_state("vault", {"equityWs": -8 * 10**18, "totalOwedWs": 78 * 10**18}, block=END)
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 0, full)
        for document in (full, summary):
            equity = document["metrics"]["observations"]["vault_equity_delta"]
            self.assertEqual(equity["opening"]["raw"], str(-5 * 10**18))
            self.assertEqual(equity["closing"]["raw"], str(-8 * 10**18))
            self.assertEqual(equity["requested_window_total"]["raw"], str(-3 * 10**18))
            self.assertEqual(equity["observed_subtotal"]["formatted"], "-3.000000000000000000")

    def test_failed_accounting_getter_is_unknown_not_invented_zero(self):
        fixture = RevenueFixture()
        fixture.set_call(fixture.addresses["vault"], "equityWs",
                         ProviderFailure("historical state unavailable", status=200), block=OPENING)
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 2, full)
        for document in (full, summary):
            self.assert_incomplete(document)
            equity = document["metrics"]["observations"]["vault_equity_delta"]
            self.assertIsNone(equity["opening"]["raw"])
            self.assertIsNone(equity["observed_subtotal"]["raw"])
            self.assertIsNone(equity["requested_window_total"])

    def test_changed_or_unsupported_precision_withholds_formatted_money_and_completion(self):
        for opening_precision in (6, 18):
            with self.subTest(opening_precision=opening_precision):
                fixture = RevenueFixture()
                fixture.activity()
                fixture.set_call(fixture.addresses["usdg"], "decimals", opening_precision, block=OPENING)
                fixture.set_call(fixture.addresses["usdg"], "decimals", 18, block=END)
                status, full, summary = fixture.run_cli()
                self.assertEqual(status, 2, full)
                for document in (full, summary):
                    self.assert_incomplete(document)
                    margin = next(row for row in document["metrics"]["observations"]["assessed_fees"]
                                  if row["assessment_basis"] == "Bought")
                    self.assertEqual(margin["observed_subtotal"]["raw"], str(MARGIN_BUY_FEE))
                    self.assertIsNone(margin["observed_subtotal"]["decimals"])
                    self.assertIsNone(margin["observed_subtotal"]["formatted"])

    def test_guarded_context_rejects_writes_and_unreviewed_selectors(self):
        fixture = RevenueFixture()
        with fixture.patches():
            ctx = core.Context("netlong-revenue", deadline=30)
            try:
                for method, params in (
                    ("eth_sendRawTransaction", ["0xdeadbeef"]),
                    ("eth_call", [{"to": fixture.addresses["vault"], "data": "0xdeadbeef"}, hex(END)]),
                    ("eth_getLogs", [{"address": fixture.addresses["vault"], "fromBlock": hex(START),
                                      "toBlock": hex(END), "topics": [], "rpc_url": "https://other.example/"}]),
                ):
                    with self.subTest(method=method):
                        with self.assertRaises(core.RpcError) as caught:
                            ctx._rpc(method, params)
                        self.assertEqual(caught.exception.kind, "permission")
            finally:
                ctx.close()
        self.assertEqual(fixture.connections, [])


if __name__ == "__main__":
    unittest.main()

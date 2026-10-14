"""Synthetic consumer boundaries only; no packaged live positions or RPC probes."""

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
import netstack_netlong as netlong
from netstack_core import Context, RpcError, StopRun, ZERO, load_json, serialize_result, topic


def address(number):
    return "0x" + format(number, "040x")


class SyntheticContext:
    def __init__(self):
        self.block, self.timestamp = 200, 1000
        self.result = {"command": "netlong", "snapshot": {"block_number": 200},
                       "metrics": {}, "coverage": {}, "errors": [], "not_proven": []}
        self.source = deepcopy(load_json("assets/analytics/netlong-interface.json"))
        self.source["models"] = [{"id": family, "family": family, "runtime_bytes": 2,
                                   "normalized_sha256": hashlib.sha256(bytes.fromhex("6000")).hexdigest(),
                                   "immutable_ranges": [], "source_id": "synthetic"}
                                  for family in ("oracle", "vault", "futures", "margin", "pot", "twap")]
        self.source["margin_libraries"] = []
        self.routes = {role: {"address": address(number)} for number, role in enumerate(
            ("oracle", "vault", "margin", "pot", "twap", "usdg", "known_future"), 1)}
        self.routes["_route"] = {"interface": "assets/analytics/netlong-interface.json",
                                    "futures_labels": [{"route": "known_future", "symbol": "NET"}]}
        self.future = self.routes["known_future"]["address"]
        self.token = address(100)
        self.trader = address(200)
        self.code_values = {}
        self.values = {}
        self.requests = []
        self.event_complete = True
        self.event_error = None
        self.position_error = None
        self.checkpoints = []
        vault, desk, pot = (self.routes[role]["address"] for role in ("vault", "margin", "pot"))
        for method, value in (("deskCount", 1), ("deskAt", self.future)):
            self.values[(vault, method, (0,) if method == "deskAt" else ())] = value
        self.values[(vault, "totalOiUsdWad", ())] = 12 * netlong.WAD
        self.values[(vault, "desks", (self.future,))] = {
            "registered": True, "skewShareBps": 1000, "oiUsdWad": 12 * netlong.WAD,
            "skewUsdWad": 8 * netlong.WAD, "lockedWs": 1}
        for method, value in (("vault", vault), ("oracle", self.routes["oracle"]["address"]),
                              ("oiLongUsdWad", 10 * netlong.WAD), ("oiShortUsdWad", 2 * netlong.WAD),
                              ("lastMark", {"priceWad": 3 * netlong.WAD, "observedAt": 990, "rung": 1})):
            self.values[(self.future, method, ())] = value
        self.values[(self.future, "positions", (self.trader,))] = {
            "sizeUsdWad": 10 * netlong.WAD, "entryPriceWad": 2 * netlong.WAD, "isLong": True}
        self.values[(self.future, "positions", (address(201),))] = {
            "sizeUsdWad": 2 * netlong.WAD, "entryPriceWad": 4 * netlong.WAD, "isLong": False}
        for method, role in (("pot", "pot"), ("marginOracle", "oracle"), ("twapSource", "twap"), ("usdg", "usdg")):
            self.values[(desk, method, ())] = self.routes[role]["address"]
        for method, role in (("desk", "margin"), ("usdg", "usdg")):
            self.values[(pot, method, ())] = self.routes[role]["address"]
        self.values[(self.routes["usdg"]["address"], "decimals", ())] = 6
        self.values[(desk, "tokenCount", ())] = 1
        self.values[(desk, "tokenAt", (0,))] = self.token
        self.values[(desk, "nextPositionId", ())] = 3
        self.values[(self.token, "symbol", ())] = "NET"
        self.values[(self.token, "decimals", ())] = 9
        self.values[(self.token, "balanceOf", (desk,))] = 11 * 10**9
        self.values[(desk, "listings", (self.token,))] = {
            "tokenDecimals": 9, "listed": False, "allowed": False, "probeOk": False,
            "measuredAt": 1, "notionalUsdWad": 18 * netlong.WAD,
            "capUsedWad": 30 * netlong.WAD, "totalShares": 500}
        self.values[(desk, "opensAllowed", (self.token,))] = {"ok": False, "reason": 1}
        self.values[(desk, "marks", (self.token,))] = {
            "twapPriceWad": 3 * netlong.WAD, "spotPriceWad": 2 * netlong.WAD, "twapLive": True}
        self.values[(desk, "positions", (1,))] = {
            "trader": self.trader, "token": self.token, "state": 2,
            "shares": 500, "notionalUsdWad": 18 * netlong.WAD}
        self.values[(desk, "positions", (2,))] = {"trader": ZERO, "token": ZERO}
        self.values[(desk, "unitsOf", (1,))] = 10 * 10**9
        self.values[(desk, "debtUsdg", (1,))] = 21 * 10**6
        self.values[(pot, "totalPrincipalUsdg", ())] = 20 * 10**6
        self.values[(pot, "totalDebtUsdg", ())] = 21 * 10**6

    def check(self):
        pass

    def checkpoint(self):
        self.checkpoints.append(deepcopy(self.result))

    def code(self, target, block=None):
        value = self.code_values.get(target, "0x6000")
        if isinstance(value, Exception):
            raise value
        return value

    def creation_block(self, target, record=None):
        return 100

    def call(self, target, abi, method, args=()):
        self.requests.append((target, method, args))
        value = self.values[(target, method, args)]
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)

    def logs(self, key, target, abi, names, start, end):
        if self.event_error:
            raise self.event_error
        self.result["coverage"][key] = {"event_coverage_complete": self.event_complete}
        yield [{"values": {"trader": self.trader}}, {"values": {"trader": address(201)}}]

    def run(self, product="all", market=None):
        with patch.object(netlong, "resolve_routes", return_value=self.routes), patch.object(netlong, "load_json", return_value=self.source):
            netlong.run(self, SimpleNamespace(product=product, market=market))
        return self.result


def word(value):
    return format((int(value, 16) if isinstance(value, str) else int(value)) % (1 << 256), "064x")


def encode_value(field, value):
    if field["type"] == "tuple":
        return "".join(encode_value(child, value.get(child["name"], 0)) for child in field["components"])
    return word(value)


class TransportFixture(SyntheticContext):
    """Reuse synthetic accounting inputs through the real Context and CLI."""
    def __init__(self):
        super().__init__()
        self.selectors = {topic(item)[:10]: item for name, abi in self.source.items()
                          if name.endswith("_abi") for item in abi if item["type"] == "function"}
        self.recheck_error = None
        self.header_reads = 0
        self.documents = []
        self.traders = [self.trader, address(201)]
        self.pruned_history = False
        self.receipts = {}

    def exchange(self, ctx, requests):
        replies = []
        for method, params in requests:
            ctx._validate_payload(method, params)
            ctx._members += 1
            self.requests.append((method, params))
            if method == "eth_chainId":
                value = hex(4663)
            elif method == "eth_getBlockByNumber":
                number = int(params[0], 16)
                self.header_reads += number == 200
                recheck = number == 200 and self.header_reads > 1
                if recheck and isinstance(self.recheck_error, StopRun):
                    ctx._stop(self.recheck_error.reason)
                if recheck and isinstance(self.recheck_error, RpcError):
                    replies.append(self.recheck_error)
                    continue
                conflict = recheck and self.recheck_error == "mismatch"
                value = {"number": hex(number), "hash": "0x" + word(number + 1000 + int(conflict)),
                         "timestamp": hex(number * 5)}
            elif method == "eth_getCode":
                if self.pruned_history and int(params[1], 16) != 200:
                    replies.append(RpcError("Historical state pruned", kind="pruned"))
                    continue
                value = self.code_values.get(params[0], "0x6000") if int(params[1], 16) >= 100 else "0x"
            elif method == "eth_getTransactionReceipt":
                value = deepcopy(self.receipts.get(params[0]))
            elif method == "eth_call":
                data = params[0]["data"]
                item = self.selectors[data[:10]]
                args = tuple("0x" + data[10 + i * 64 + 24:10 + (i + 1) * 64] if field["type"] == "address"
                             else int(data[10 + i * 64:10 + (i + 1) * 64], 16)
                             for i, field in enumerate(item["inputs"]))
                raw = self.values[(params[0]["to"], item["name"], args)]
                if isinstance(raw, RpcError):
                    replies.append(raw)
                    continue
                fields = item["outputs"]
                if len(fields) == 1 and fields[0]["type"] == "string":
                    text = raw.encode()
                    value = "0x" + word(32) + word(len(text)) + text.hex() + "00" * (-len(text) % 32)
                elif len(fields) == 1:
                    value = "0x" + encode_value(fields[0], raw)
                else:
                    value = "0x" + "".join(encode_value(field, raw[field["name"]]) for field in fields)
            elif method == "eth_getLogs":
                if self.event_error:
                    replies.append(self.event_error)
                    continue
                event = next(item for item in self.source["futures_abi"] if item.get("name") == "Filled")
                value = [{"address": self.future, "blockNumber": hex(150), "blockHash": "0x" + word(1150),
                          "transactionHash": "0x" + word(150), "transactionIndex": "0x0", "logIndex": hex(index),
                          "topics": [topic(event), "0x" + word(index), "0x" + word(trader)],
                          "data": "0x" + word(0) * 6, "removed": False}
                         for index, trader in enumerate(self.traders)]
            else:
                raise AssertionError(method)
            replies.append(value)
        return replies

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(netlong, "resolve_routes", return_value=self.routes))
        stack.enter_context(patch.object(netlong, "load_json", return_value=self.source))
        stack.enter_context(patch.object(Context, "_exchange_once", lambda ctx, requests: self.exchange(ctx, requests)))
        original = Context._atomic_output

        def capture(ctx, text):
            self.documents.append(json.loads(text))
            original(ctx, text)

        stack.enter_context(patch.object(Context, "_atomic_output", capture))
        return stack

    def run_cli(self, product="all", detail="summary"):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory(prefix="netlong-confirmation-") as directory:
            checkpoint = Path(directory).resolve() / "checkpoint.json"
            with self.patches(), patch.object(analytics, "_PROCESS_STARTED", time.monotonic()), redirect_stdout(stdout):
                status = analytics.main(["netlong", "--product", product, "--block", "200", "--deadline", "30",
                                         "--detail", detail, "--output", str(checkpoint)])
            full = json.loads(checkpoint.read_text())
        return status, full, json.loads(stdout.getvalue())


class NetLongConfirmationTests(unittest.TestCase):
    def test_projection_is_deterministic_idempotent_and_does_not_demote_acquisition(self):
        subtotal = netlong.quantity(17, 18, "synthetic")
        raw = {
            "snapshot": {"recheck_status": "unconfirmed"}, "errors": [],
            "coverage": {"collection_complete": True,
                         "positions": {"event_coverage_complete": True}},
            "metrics": {
                "aggregates": {"futures": {
                    "collection_complete": True,
                    "entry_notional": {"collection_complete": True,
                                       "observed_subtotal": subtotal, "total": subtotal}}},
                "markets": [{"collection_complete": True, "positions_complete": True}]}}
        original = deepcopy(raw)
        interim = netlong.prepare_result(raw)
        self.assertEqual(raw, original)
        self.assertEqual(interim, netlong.prepare_result(raw))
        self.assertEqual(interim, netlong.prepare_result(interim))
        self.assert_unconfirmed(interim, "unconfirmed")
        raw["snapshot"]["recheck_status"] = "confirmed"
        confirmed = netlong.prepare_result(raw)
        self.assertTrue(confirmed["coverage"]["collection_complete"])
        field = confirmed["metrics"]["aggregates"]["futures"]["entry_notional"]
        self.assertEqual(field["total"], subtotal)
        self.assertEqual(confirmed, netlong.prepare_result(confirmed))
        self.assertEqual(interim["metrics"]["aggregates"]["futures"]["entry_notional"]["total"], None)
        # A previously publishable projection must be revocable without losing
        # its measured subtotal or mutating the previously returned checkpoint.
        for signal in ("snapshot", "integrity"):
            revoked = deepcopy(confirmed)
            if signal == "snapshot":
                revoked["snapshot"]["confirmation"] = "invalid"
            else:
                revoked["errors"].append({"kind": "integrity"})
            before = deepcopy(revoked)
            invalid = netlong.prepare_result(revoked)
            self.assert_unconfirmed(invalid, "invalid")
            self.assertEqual(invalid["metrics"]["aggregates"]["futures"]["entry_notional"]["observed_subtotal"],
                             subtotal)
            self.assertEqual(revoked, before)
            self.assertEqual(invalid, netlong.prepare_result(invalid))
        self.assertEqual(field["total"], subtotal)
        # Confirmation is not evidence of successful acquisition.
        raw["metrics"]["aggregates"]["futures"]["entry_notional"]["collection_complete"] = False
        incomplete = netlong.prepare_result(raw)
        self.assertIsNone(incomplete["metrics"]["aggregates"]["futures"]["entry_notional"]["total"])
        self.assertEqual(incomplete["metrics"]["aggregates"]["futures"]["entry_notional"]["observed_subtotal"],
                         subtotal)

    def assert_unconfirmed(self, document, confirmation):
        self.assertFalse(document["coverage"]["collection_complete"])
        self.assertFalse(document["coverage"]["snapshot_valid"])
        self.assertEqual(document["coverage"]["snapshot_confirmation"], confirmation)
        for aggregate in document["metrics"]["aggregates"].values():
            self.assertFalse(aggregate["collection_complete"])
            self.assertFalse(aggregate["snapshot_valid"])
            self.assertEqual(aggregate["snapshot_confirmation"], confirmation)
            for field in aggregate.values():
                if isinstance(field, dict) and "total" in field:
                    self.assertIsNone(field["total"])
                    self.assertFalse(field["collection_complete"])
                    self.assertFalse(field["snapshot_valid"])
                    self.assertEqual(field["snapshot_confirmation"], confirmation)
        for row in document["metrics"]["markets"]:
            self.assertFalse(row["collection_complete"])
            self.assertFalse(row.get("positions_complete", False))
            self.assertFalse(row["snapshot_valid"])
            self.assertEqual(row["snapshot_confirmation"], confirmation)

    def test_conflicting_recheck_revokes_full_checkpoint_and_summary_totals(self):
        fixture = TransportFixture()
        fixture.recheck_error = "mismatch"
        status, full, summary = fixture.run_cli()
        self.assertEqual(status, 2)
        self.assertEqual(full["snapshot"]["confirmation"], "invalid")
        self.assertTrue(any(error["kind"] == "integrity" for error in full["errors"]))
        self.assert_unconfirmed(fixture.documents[-2], "unconfirmed")
        for document in (full, summary):
            self.assert_unconfirmed(document, "invalid")
            aggregates = document["metrics"]["aggregates"]
            self.assertEqual(aggregates["futures"]["entry_notional"]["observed_subtotal"]["gross"]["raw"],
                             str(12 * netlong.WAD))
            self.assertEqual(aggregates["margin"]["debt"]["observed_subtotal"]["raw"], "21000000")
            self.assertEqual(aggregates["margin"]["marked_token_exposure"]["observed_subtotal"]["raw"],
                             str(20 * netlong.WAD))
            self.assertFalse(document["coverage"]["futures_discovery"]["collection_complete"])
            self.assertFalse(document["coverage"]["margin_positions"]["collection_complete"])
        self.assertEqual(full["metrics"]["aggregates"], summary["metrics"]["aggregates"])
        self.assertEqual(summary["presentation"]["full_checkpoint"], "saved")
        self.assertNotIn("reads", summary["metrics"])
        self.assertNotIn("positions", summary["metrics"]["markets"][0])

    def test_unconfirmed_and_terminal_rechecks_withhold_totals(self):
        failures = (RpcError("Synthetic permission denial", kind="permission"),
                    RpcError("Synthetic unavailable header", kind="unavailable"),
                    StopRun("deadline_exhausted"))
        for failure in failures:
            with self.subTest(failure=str(failure)):
                fixture = TransportFixture()
                fixture.recheck_error = failure
                status, full, summary = fixture.run_cli()
                self.assertEqual(status, 2)
                self.assertEqual(fixture.header_reads, 2)
                self.assertEqual(full["snapshot"]["confirmation"], "unconfirmed")
                for document in (fixture.documents[-2], full, summary):
                    self.assert_unconfirmed(document, "unconfirmed")
                    self.assertEqual(document["metrics"]["aggregates"]["margin"]["debt"]["observed_subtotal"]["raw"],
                                     "21000000")
                self.assertFalse(full["coverage"]["futures_positions:" + fixture.future]["event_coverage_complete"])
                if isinstance(failure, StopRun):
                    self.assertEqual(full["stopping_reason"], "deadline_exhausted")

    def test_confirmed_collection_and_zeros_promote_after_interim_checkpoints(self):
        for scenario in ("positions", "empty_positions", "empty_registries"):
            for detail in ("full", "summary"):
                with self.subTest(scenario=scenario, detail=detail):
                    fixture = TransportFixture()
                    vault = fixture.routes["vault"]["address"]
                    margin = fixture.routes["margin"]["address"]
                    if scenario != "positions":
                        fixture.values[(vault, "totalOiUsdWad", ())] = 0
                    if scenario == "empty_registries":
                        fixture.values[(vault, "deskCount", ())] = 0
                        fixture.values[(margin, "tokenCount", ())] = 0
                    elif scenario == "empty_positions":
                        fixture.traders = []
                        fixture.values[(fixture.future, "oiLongUsdWad", ())] = 0
                        fixture.values[(fixture.future, "oiShortUsdWad", ())] = 0
                        fixture.values[(fixture.future, "lastMark", ())]["priceWad"] = 0
                        fixture.values[(vault, "desks", (fixture.future,))].update(oiUsdWad=0, skewUsdWad=0)
                        fixture.values[(margin, "nextPositionId", ())] = 1
                        fixture.values[(margin, "listings", (fixture.token,))].update(totalShares=0, notionalUsdWad=0)
                        fixture.values[(margin, "marks", (fixture.token,))]["twapLive"] = False
                    status, full, printed = fixture.run_cli(detail=detail)
                    self.assertEqual(status, 0)
                    interim = fixture.documents[-2]
                    self.assert_unconfirmed(interim, "unconfirmed")
                    for document in (full, printed):
                        self.assertEqual(document["status"], "completed")
                        self.assertEqual(document["snapshot"]["recheck_status"], "confirmed")
                        self.assertTrue(document["coverage"]["collection_complete"])
                        self.assertTrue(document["coverage"]["snapshot_valid"])
                        for product, aggregate in document["metrics"]["aggregates"].items():
                            self.assertTrue(aggregate["collection_complete"])
                            self.assertTrue(aggregate["snapshot_valid"])
                            for name, field in aggregate.items():
                                if not isinstance(field, dict) or "total" not in field:
                                    continue
                                self.assertTrue(field["collection_complete"])
                                self.assertTrue(field["snapshot_valid"])
                                self.assertIsNotNone(field["total"])
                                self.assertEqual(field["total"], field["observed_subtotal"])
                                self.assertEqual(field["observed_subtotal"],
                                                 interim["metrics"]["aggregates"][product][name]["observed_subtotal"])
                                if scenario != "positions":
                                    quantity = field["total"].get("gross", field["total"])
                                    self.assertEqual(quantity["raw"], "0")
                        for row in document["metrics"]["markets"]:
                            self.assertTrue(row["positions_complete"])
                            self.assertTrue(row["collection_complete"])
                            self.assertTrue(row["snapshot_valid"])

    def test_confirmation_never_rebuilds_unsupported_or_partial_totals(self):
        for scenario in ("partial_registry", "failed_registry", "unsupported", "desk_reconciliation",
                         "vault_reconciliation", "position_history", "margin_position_bound"):
            with self.subTest(scenario=scenario):
                fixture = TransportFixture()
                vault = fixture.routes["vault"]["address"]
                product, field = "futures", "entry_notional"
                subtotal = str(12 * netlong.WAD)
                if scenario == "partial_registry":
                    fixture.values[(vault, "deskCount", ())] = 2
                    fixture.values[(vault, "deskAt", (1,))] = fixture.future
                elif scenario == "failed_registry":
                    fixture.values[(vault, "totalOiUsdWad", ())] = RpcError("Unavailable", kind="unavailable")
                    subtotal = None
                elif scenario == "unsupported":
                    fixture.code_values[fixture.future] = "0x6001"
                    subtotal = None
                elif scenario == "desk_reconciliation":
                    fixture.values[(vault, "desks", (fixture.future,))]["oiUsdWad"] = 13 * netlong.WAD
                elif scenario == "vault_reconciliation":
                    fixture.values[(vault, "totalOiUsdWad", ())] = 13 * netlong.WAD
                elif scenario == "position_history":
                    fixture.event_error = RpcError("Unavailable history", kind="unavailable")
                    field, subtotal = "mark_notional", None
                else:
                    product, field, subtotal = "margin", "debt", "21000000"
                with patch.object(netlong, "POSITION_LIMIT", 1 if scenario == "margin_position_bound" else 128):
                    status, full, summary = fixture.run_cli(product=product)
                self.assertEqual(status, 2)
                for document in (full, summary):
                    self.assertEqual(document["snapshot"]["recheck_status"], "confirmed")
                    self.assertFalse(document["coverage"]["collection_complete"])
                    aggregate = document["metrics"]["aggregates"][product]
                    self.assertFalse(aggregate["collection_complete"])
                    self.assertTrue(aggregate["snapshot_valid"])
                    metric = aggregate[field]
                    self.assertFalse(metric["collection_complete"])
                    self.assertIsNone(metric["total"])
                    if subtotal is None:
                        self.assertIsNone(metric["observed_subtotal"])
                    else:
                        observed = metric["observed_subtotal"]
                        self.assertEqual(observed.get("gross", observed)["raw"], subtotal)
                    if scenario == "vault_reconciliation":
                        self.assertFalse(document["metrics"]["vault_entry_reconciliation"]["matches"])
                        self.assertIsNone(aggregate["mark_notional"]["total"])


class NetLongCreationBoundaryTests(unittest.TestCase):
    def fixture(self):
        fixture = TransportFixture()
        fixture.pruned_history = True
        tx_hash = "0x" + word(900)
        fixture.routes["known_future"]["deployment_transaction_hash"] = tx_hash
        fixture.receipts[tx_hash] = {
            "transactionHash": tx_hash, "transactionIndex": "0x0",
            "blockNumber": hex(100), "blockHash": "0x" + word(1100),
            "status": "0x1", "from": address(300), "to": None,
            "contractAddress": fixture.future, "logs": []}
        return fixture, tx_hash

    def assert_incomplete_inventory(self, fixture, full, summary):
        for document in (full, summary):
            self.assertEqual(document["snapshot"]["recheck_status"], "confirmed")
            self.assertTrue(document["coverage"]["futures_discovery"]["collection_complete"])
            self.assertFalse(document["coverage"]["collection_complete"])
            self.assertEqual([row["address"] for row in document["metrics"]["discovered_markets"]],
                             [fixture.future])
            self.assertEqual(len(document["metrics"]["markets"]), 1)
            row = document["metrics"]["markets"][0]
            self.assertEqual(row["status"], "partial")
            self.assertFalse(row["collection_complete"])
            self.assertFalse(row.get("positions_complete", False))
            self.assertEqual(row["entry_notional"]["gross"]["raw"], str(12 * netlong.WAD))
            aggregate = document["metrics"]["aggregates"]["futures"]
            self.assertEqual(aggregate["market_count"], 1)
            self.assertFalse(aggregate["collection_complete"])
            # Current desk OI remains observed; unavailable position history is
            # neither a zero marked inventory nor grounds to drop the desk.
            self.assertEqual(aggregate["entry_notional"]["total"]["gross"]["raw"],
                             str(12 * netlong.WAD))
            self.assertIsNone(aggregate["mark_notional"]["total"])
            self.assertIsNone(aggregate["mark_notional"]["observed_subtotal"])
            self.assertEqual(document["coverage"]["missing_markets"],
                             [{"product": "futures", "address": fixture.future, "status": "partial"}])
        self.assertFalse(any(method == "eth_getLogs" for method, _ in fixture.requests))

    def test_creation_receipt_enumerates_and_reconciles_with_pruned_state(self):
        fixture, tx_hash = self.fixture()
        status, full, summary = fixture.run_cli(product="futures")
        self.assertEqual(status, 0)
        self.assertIn(("eth_getTransactionReceipt", [tx_hash]), fixture.requests)
        code_blocks = [params[1] for method, params in fixture.requests if method == "eth_getCode"]
        self.assertTrue(code_blocks)
        self.assertEqual(set(code_blocks), {hex(200)})
        boundary = full["coverage"]["deployment_boundaries"][fixture.future]
        self.assertEqual(boundary, {"block": 100, "provenance": "canonical_creation_receipt"})
        coverage = full["coverage"]["futures_positions:" + fixture.future]
        self.assertEqual(coverage["requested_range"], [100, 200])
        self.assertEqual(coverage["covered_ranges"], [[100, 200]])
        self.assertTrue(coverage["event_coverage_complete"])
        self.assertEqual(coverage["identifiers_discovered"], 2)
        row = full["metrics"]["markets"][0]
        self.assertEqual({position["trader"] for position in row["positions"]}, set(fixture.traders))
        self.assertEqual(row["position_entry_reconciliation"],
                         {"matches": True, "long_residual_wad": "0", "short_residual_wad": "0"})
        self.assertEqual(summary["metrics"]["markets"][0]["observed_position_count"], 2)
        for document in (full, summary):
            self.assertTrue(document["coverage"]["collection_complete"])
            self.assertTrue(document["metrics"]["markets"][0]["positions_complete"])
            aggregate = document["metrics"]["aggregates"]["futures"]
            self.assertEqual(aggregate["market_count"], 1)
            self.assertTrue(aggregate["collection_complete"])
            self.assertEqual(aggregate["entry_notional"]["total"]["gross"]["raw"],
                             str(12 * netlong.WAD))
            self.assertEqual(aggregate["mark_notional"]["total"]["long"]["raw"],
                             str(15 * netlong.WAD))
            self.assertEqual(aggregate["mark_notional"]["total"]["short"]["raw"],
                             str(3 * netlong.WAD // 2))

    def test_missing_creation_provenance_keeps_known_and_new_desks_incomplete(self):
        for known in (True, False):
            with self.subTest(known=known):
                fixture, _ = self.fixture()
                if known:
                    del fixture.routes["known_future"]["deployment_transaction_hash"]
                else:
                    del fixture.routes["known_future"]
                    fixture.routes["_route"]["futures_labels"] = []
                status, full, summary = fixture.run_cli(product="futures")
                self.assertEqual(status, 2)
                self.assert_incomplete_inventory(fixture, full, summary)
                if not known:
                    self.assertIsNone(full["metrics"]["markets"][0]["symbol"])
                self.assertTrue(any(method == "eth_getCode" and params[1] != hex(200)
                                    for method, params in fixture.requests))
                self.assertTrue(any(error["kind"] == "pruned" for error in full["errors"]))

    def test_mismatched_creation_receipt_never_falls_back_to_guessed_boundary(self):
        for field, value in (("contractAddress", address(999)),
                             ("transactionHash", "0x" + word(901)), ("status", "0x0")):
            with self.subTest(field=field):
                fixture, tx_hash = self.fixture()
                fixture.receipts[tx_hash][field] = value
                # A locator must not rescue an invalid canonical receipt either.
                fixture.routes["known_future"]["provenance"] = [{"locator": "block_number=100"}]
                status, full, summary = fixture.run_cli(product="futures")
                self.assertEqual(status, 2)
                for document in (full, summary):
                    self.assertNotEqual(document["snapshot"]["recheck_status"], "confirmed")
                    self.assertFalse(document["coverage"]["collection_complete"])
                    row = document["metrics"]["markets"][0]
                    self.assertEqual(row["address"], fixture.future)
                    self.assertFalse(row.get("positions_complete", False))
                    self.assertNotIn("futures", document["metrics"]["aggregates"])
                self.assertFalse(any(method == "eth_getLogs" for method, _ in fixture.requests))
                self.assertTrue(any(error["kind"] == "integrity" for error in full["errors"]))
                self.assertNotIn(fixture.future, full["coverage"].get("deployment_boundaries", {}))
                self.assertFalse(any(method == "eth_getCode" and params[1] != hex(200)
                                     for method, params in fixture.requests))


class NetLongBoundaries(unittest.TestCase):
    def test_empty_futures_history_uses_real_log_coverage_contract(self):
        ctx = Context("netlong", deadline=30)
        ctx.block = 200
        abi = load_json("assets/analytics/netlong-interface.json")["futures_abi"]
        try:
            with patch.object(ctx, "creation_block", return_value=100), patch.object(ctx, "_rpc", return_value=[]):
                identifiers, complete = netlong._discover_ids(
                    ctx, address(1), abi, "Filled", "trader", None, "fills")
            self.assertEqual(identifiers, [])
            self.assertTrue(complete)
            self.assertEqual(ctx.result["coverage"]["fills"]["covered_ranges"], [[100, 200]])
            self.assertEqual(ctx.result["coverage"]["fills"]["missing_ranges"], [])
            self.assertEqual(ctx.result["errors"], [])
        finally:
            ctx.close()

    def test_disjoint_accounting_uses_actual_units_debt_and_mark(self):
        result = SyntheticContext().run()
        self.assertTrue(result["coverage"]["collection_complete"])
        futures, margin = result["metrics"]["markets"]
        self.assertEqual(futures["entry_notional"]["gross"]["raw"], str(12 * netlong.WAD))
        self.assertEqual(futures["entry_notional"]["net"]["raw"], str(8 * netlong.WAD))
        self.assertEqual(futures["mark_notional"]["gross"]["raw"], str(165 * netlong.WAD // 10))
        self.assertEqual(futures["mark_notional"]["net"]["raw"], str(135 * netlong.WAD // 10))
        self.assertEqual(margin["entry_notional"]["raw"], str(18 * netlong.WAD))
        self.assertEqual(margin["debt"]["formatted"], "21.000000")
        self.assertEqual(margin["marked_token_exposure"]["raw"], str(20 * netlong.WAD))
        self.assertNotEqual(margin["token_units"]["raw"], margin["desk_token_custody"]["raw"])
        self.assertFalse(margin["opens_allowed"]["ok"])
        self.assertEqual(set(result["metrics"]["aggregates"]), {"futures", "margin"})
        self.assertNotIn("total_oi", result["metrics"])

    def test_symbol_ambiguity_and_address_selection(self):
        with self.assertRaisesRegex(RpcError, "ambiguous"):
            SyntheticContext().run(market="NET")
        ctx = SyntheticContext()
        result = ctx.run(market=ctx.token)
        self.assertEqual([row["address"] for row in result["metrics"]["markets"]], [ctx.token])
        self.assertEqual(len(result["metrics"]["discovered_markets"]), 2)

    def test_future_inventory_gap_never_becomes_mark_total(self):
        ctx = SyntheticContext()
        ctx.event_complete = False
        row = ctx.run("futures")["metrics"]["markets"][0]
        self.assertIsNone(row["mark_notional"])
        self.assertIsNotNone(row["entry_notional"])
        self.assertFalse(row["positions_complete"])
        self.assertFalse(ctx.result["coverage"]["collection_complete"])

    def test_stale_margin_price_retains_debt_without_inventing_exposure(self):
        ctx = SyntheticContext()
        desk = ctx.routes["margin"]["address"]
        ctx.values[(desk, "marks", (ctx.token,))]["twapLive"] = False
        row = ctx.run("margin")["metrics"]["markets"][0]
        self.assertEqual(row["debt"]["raw"], "21000000")
        self.assertIsNone(row["marked_token_exposure"]["raw"])
        self.assertFalse(row["collection_complete"])
        self.assertIsNone(row["observed_position_mark_subtotal"]["raw"])
        self.assertIsNone(ctx.result["metrics"]["aggregates"]["margin"]["marked_token_exposure"]["observed_subtotal"])

    def test_futures_vault_mismatches_revoke_complete_totals(self):
        for scope in ("desk", "vault"):
            with self.subTest(scope=scope):
                ctx = SyntheticContext()
                vault = ctx.routes["vault"]["address"]
                if scope == "desk":
                    ctx.values[(vault, "desks", (ctx.future,))]["oiUsdWad"] = 13 * netlong.WAD
                else:
                    ctx.values[(vault, "totalOiUsdWad", ())] = 13 * netlong.WAD
                result = ctx.run("futures")
                aggregate = result["metrics"]["aggregates"]["futures"]
                self.assertFalse(aggregate["collection_complete"])
                self.assertFalse(aggregate["entry_notional"]["collection_complete"])
                self.assertIsNone(aggregate["entry_notional"]["total"])
                self.assertEqual(aggregate["entry_notional"]["observed_subtotal"]["gross"]["raw"],
                                 str(12 * netlong.WAD))
                if scope == "vault":
                    self.assertFalse(result["metrics"]["vault_entry_reconciliation"]["matches"])

    def test_missing_futures_mark_never_becomes_observed_zero(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.future, "lastMark", ())] = RpcError("Unavailable mark", kind="unavailable")
        result = ctx.run("futures")
        aggregate = result["metrics"]["aggregates"]["futures"]
        self.assertIsNone(aggregate["mark_notional"]["total"])
        self.assertIsNone(aggregate["mark_notional"]["observed_subtotal"])
        self.assertEqual(aggregate["entry_notional"]["total"]["gross"]["raw"], str(12 * netlong.WAD))

    def test_runtime_mismatch_refuses_oi_getters(self):
        ctx = SyntheticContext()
        ctx.code_values[ctx.future] = "0x6001"
        row = ctx.run("futures")["metrics"]["markets"][0]
        self.assertEqual(row["status"], "unsupported")
        self.assertFalse(any(target == ctx.future for target, method, args in ctx.requests))
        self.assertIsNone(ctx.result["metrics"]["aggregates"]["futures"]["entry_notional"]["total"])
        self.assertIsNone(ctx.result["metrics"]["aggregates"]["futures"]["entry_notional"]["observed_subtotal"])

    def test_permission_denial_is_terminal_not_a_per_market_fallback(self):
        ctx = SyntheticContext()
        ctx.code_values[ctx.routes["oracle"]["address"]] = RpcError("Denied", kind="permission")
        with self.assertRaises(RpcError):
            ctx.run()
        self.assertEqual(ctx.requests, [])

    def test_position_bound_preserves_subtotals_but_not_totals(self):
        ctx = SyntheticContext()
        with patch.object(netlong, "POSITION_LIMIT", 1):
            row = ctx.run("margin")["metrics"]["markets"][0]
        self.assertEqual(row["observed_position_debt_subtotal"]["raw"], "21000000")
        self.assertIsNone(row["debt"]["raw"])
        self.assertEqual(ctx.result["coverage"]["margin_positions"]["missing_id_range"], [2, 2])

    def test_market_bound_and_duplicate_entries_are_partial(self):
        ctx = SyntheticContext()
        vault = ctx.routes["vault"]["address"]
        ctx.values[(vault, "deskCount", ())] = 2
        ctx.values[(vault, "deskAt", (1,))] = ctx.future
        result = ctx.run("futures")
        self.assertFalse(result["coverage"]["futures_discovery"]["collection_complete"])
        self.assertIsNone(result["metrics"]["aggregates"]["futures"]["entry_notional"]["total"])

    def test_new_token_uses_registry_not_a_symbol_allowlist(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.token, "symbol", ())] = "UNSEEN"
        result = ctx.run("margin", "UNSEEN")
        self.assertTrue(result["coverage"]["collection_complete"])
        self.assertEqual(result["metrics"]["markets"][0]["symbol"], "UNSEEN")

    def test_same_model_unknown_future_is_address_queryable(self):
        ctx = SyntheticContext()
        ctx.routes["_route"]["futures_labels"] = []
        result = ctx.run("futures", ctx.future)
        self.assertTrue(result["coverage"]["collection_complete"])
        self.assertIsNone(result["metrics"]["markets"][0]["symbol"])

    def test_zero_entry_price_is_missing_not_zero_exposure(self):
        ctx = SyntheticContext()
        ctx.values[(ctx.future, "positions", (ctx.trader,))]["entryPriceWad"] = 0
        row = ctx.run("futures")["metrics"]["markets"][0]
        self.assertIsNone(row["mark_notional"])
        self.assertFalse(row["collection_complete"])

    def test_summary_projects_saved_document_and_exact_large_values(self):
        ctx = SyntheticContext()
        result = ctx.run("margin")
        result.update(status="partial", stopping_reason="deadline_exhausted")
        result["metrics"]["markets"][0]["debt"] = netlong.quantity(2**100 + 1, 6, "USDG")
        summary = json.loads(netlong.summarize(serialize_result(result), "saved"))
        self.assertEqual(summary["status"], "partial")
        self.assertNotIn("reads", summary["metrics"])
        self.assertEqual(summary["metrics"]["markets"][0]["debt"]["raw"], str(2**100 + 1))
        self.assertEqual(summary["presentation"]["full_checkpoint"], "saved")

    def test_template_rejects_inconsistent_embedded_dependency_words(self):
        ctx = SyntheticContext()
        ctx.result["metrics"]["implementation_checks"] = []
        word = bytes.fromhex("00" * 31 + "01")
        raw = b"\x7f" + word + b"\x7f" + word
        normalized = b"\x7f" + bytes(32) + b"\x7f" + bytes(32)
        model = {"id": "synthetic-template", "family": "futures", "runtime_bytes": len(raw),
                 "source_id": "synthetic", "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
                 "immutable_ranges": [[1, 32], [34, 32]],
                 "immutable_groups": [{"name": "vault", "offsets": [1, 34]}]}
        ctx.code_values[ctx.future] = "0x" + raw.hex()
        self.assertEqual(netlong._identity(ctx, ctx.future, [model], "futures")["id"], model["id"])
        ctx.code_values[ctx.future] = "0x" + (raw[:-1] + b"\x02").hex()
        with self.assertRaisesRegex(RpcError, "not a reviewed"):
            netlong._identity(ctx, ctx.future, [model], "futures")

    def test_pending_buy_is_not_counted_as_funded_debt_or_token_exposure(self):
        ctx = SyntheticContext()
        desk = ctx.routes["margin"]["address"]
        ctx.values[(desk, "positions", (1,))].update(state=1, shares=0, notionalUsdWad=0)
        ctx.values[(desk, "listings", (ctx.token,))].update(totalShares=0, notionalUsdWad=0)
        ctx.values[(desk, "unitsOf", (1,))] = 0
        ctx.values[(desk, "debtUsdg", (1,))] = 0
        row = ctx.run("margin")["metrics"]["markets"][0]
        self.assertEqual(row["debt"]["raw"], "0")
        self.assertEqual(row["marked_token_exposure"]["raw"], "0")

    def test_unknown_allocated_token_or_state_is_not_silently_ignored(self):
        for changed in ({"token": address(999)}, {"state": 4}):
            ctx = SyntheticContext()
            desk = ctx.routes["margin"]["address"]
            ctx.values[(desk, "positions", (1,))].update(changed)
            row = ctx.run("margin")["metrics"]["markets"][0]
            self.assertFalse(row["collection_complete"])
            self.assertIsNone(row["debt"]["raw"])

    def test_deadline_preserves_snapshot_without_promoting_incomplete_positions(self):
        ctx = SyntheticContext()
        desk = ctx.routes["margin"]["address"]
        ctx.values[(desk, "unitsOf", (1,))] = StopRun("deadline_exhausted")
        with self.assertRaises(StopRun):
            ctx.run("margin")
        row = ctx.result["metrics"]["markets"][0]
        self.assertEqual(row["entry_notional"]["raw"], str(18 * netlong.WAD))
        self.assertFalse(row["collection_complete"])
        self.assertFalse(ctx.result["coverage"]["collection_complete"])
        self.assertNotIn("debt", row)
        self.assertTrue(any(checkpoint["metrics"].get("markets", [{}])[0].get("entry_notional")
                            for checkpoint in ctx.checkpoints if checkpoint["metrics"].get("markets")))

    def test_failed_discovery_does_not_publish_an_empty_complete_aggregate(self):
        ctx = SyntheticContext()
        vault = ctx.routes["vault"]["address"]
        ctx.values[(vault, "totalOiUsdWad", ())] = RpcError("Unavailable", kind="unavailable")
        result = ctx.run("futures")
        self.assertFalse(result["coverage"]["futures_discovery"]["collection_complete"])
        self.assertIsNone(result["metrics"]["aggregates"]["futures"]["entry_notional"]["total"])

    def test_cli_and_exact_read_allowlist(self):
        args = analytics.parser().parse_args(["netlong", "--product", "margin", "--market", "NEW", "--detail", "summary"])
        self.assertEqual((args.command, args.product, args.market, args.detail), ("netlong", "margin", "NEW", "summary"))
        ctx = Context.__new__(Context)
        ctx.command, ctx._allowed = "netlong", None
        allowed = ctx._functions()
        self.assertIn("nextPositionId()", allowed)
        self.assertIn("positions(uint256)", allowed)
        self.assertIn("positions(address)", allowed)
        self.assertNotIn("open(address,uint256,uint256,uint256,uint64)", allowed)
        self.assertTrue(all(item["stateMutability"] in ("view", "pure") for item in allowed.values()))


if __name__ == "__main__":
    unittest.main()

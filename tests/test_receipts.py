"""Receipt research regressions over the real collector, CLI and guarded RPC transport."""
from collections import Counter
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import signal
import ssl
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analytics
import netstack_core as core
import netstack_receipts as receipts

ADDRESS = "0x" + "11" * 20
ACCOUNT = "0x" + "22" * 20
TX = "0x" + "aa" * 32
OTHER_TX = "0x" + "ab" * 32
SECRET = "receipt-provider-secret"
URL = "https://" + SECRET + ".example:8443/v2/" + SECRET + "?key=" + SECRET
EVENT = {"type": "event", "name": "Settlement", "anonymous": False, "inputs": [
    {"name": "account", "type": "address", "indexed": True},
    {"name": "delta", "type": "int256", "indexed": False},
    {"name": "amount", "type": "uint256", "indexed": False},
]}


def block_hash(number):
    return "0x" + format(number + 1000, "064x")


def raw_log(block=10, index=0, tx=TX, delta=-7, amount=13):
    return {"address": ADDRESS,
            "topics": [core.topic(EVENT), "0x" + ACCOUNT[2:].rjust(64, "0")],
            "data": "0x" + (delta % (1 << 256)).to_bytes(32, "big").hex()
                    + amount.to_bytes(32, "big").hex(),
            "blockNumber": hex(block), "blockHash": block_hash(block),
            "transactionHash": tx, "transactionIndex": "0x0",
            "logIndex": hex(index), "removed": False}


def raw_receipt(logs, tx=TX, block=10, status=1):
    return {"transactionHash": tx, "blockNumber": hex(block),
            "blockHash": block_hash(block), "transactionIndex": "0x0",
            "status": hex(status), "from": ACCOUNT, "to": ADDRESS,
            "contractAddress": None, "logs": deepcopy(logs)}


class Response:
    """Only replace HTTPS I/O; Context still validates, classifies and decodes."""
    def __init__(self, fixture):
        self.fixture = fixture
        self.status = 200
        self.body = b""
        self.closed = False

    def request(self, method, target, body, headers):
        self.fixture.targets.append(target)
        self.fixture.http_methods.append(method)
        request = json.loads(body)

        def member(entry):
            method, params = entry["method"], entry["params"]
            self.fixture.requests.append((method, deepcopy(params)))
            result = self.fixture.answer(method, params)
            envelope = {"jsonrpc": "2.0", "id": entry["id"]}
            if isinstance(result, ProviderFailure):
                self.status = result.status
                envelope["error"] = {"code": result.code, "message": result.message, "data": URL}
            else:
                envelope["result"] = result
            return envelope

        envelope = [member(entry) for entry in request] if isinstance(request, list) else member(request)
        self.body = json.dumps(envelope).encode()

    def getresponse(self):
        return self

    def getheader(self, name, default=None):
        return default

    def read(self, size):
        self.fixture.reads += 1
        result, self.body = self.body[:size], self.body[size:]
        return result

    def close(self):
        self.closed = True


class ProviderFailure:
    def __init__(self, message, status=400, code=-32600):
        self.message, self.status, self.code = message, status, code


class Fixture:
    def __init__(self, logs=()):
        self.logs = deepcopy(list(logs))
        self.receipts = {}
        for log in self.logs:
            tx = log["transactionHash"]
            if tx not in self.receipts:
                self.receipts[tx] = raw_receipt([], tx=tx, block=int(log["blockNumber"], 16))
            if log not in self.receipts[tx]["logs"]:
                self.receipts[tx]["logs"].append(deepcopy(log))
        self.requests, self.targets, self.http_methods = [], [], []
        self.connections, self.responses, self.contexts = [], [], []
        self.reads = 0
        self.header_reads = Counter()
        self.override = None

    def answer(self, method, params):
        if self.override is not None:
            handled, result = self.override(method, params)
            if handled:
                return result
        if method == "eth_chainId":
            return hex(4663)
        if method == "eth_getBlockByNumber":
            number = 22 if params[0] == "latest" else int(params[0], 16)
            self.header_reads[number] += 1
            return {"number": hex(number), "hash": block_hash(number), "timestamp": hex(1000 + number)}
        if method == "eth_getCode":
            return "0x6000"
        if method == "eth_getLogs":
            query = params[0]
            first, last = int(query["fromBlock"], 16), int(query["toBlock"], 16)
            return deepcopy([log for log in self.logs if first <= int(log["blockNumber"], 16) <= last])
        if method == "eth_getTransactionReceipt":
            return deepcopy(self.receipts.get(params[0]))
        raise AssertionError("Unexpected RPC method: " + method)

    def connect(self, host, port, *, timeout, context, network_policy):
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise AssertionError("Collector weakened TLS verification")
        if not 0 < timeout <= 15:
            raise AssertionError("Unbounded transport timeout")
        self.connections.append((host, port))
        response = Response(self)
        self.responses.append(response)
        return response

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.dict(os.environ, {"NETSTACK_RPC_URL": URL}, clear=True))
        stack.enter_context(patch.object(core.socket, "getaddrinfo", side_effect=AssertionError("Real DNS forbidden")))
        stack.enter_context(patch.object(core, "_FixedHTTPSConnection", side_effect=self.connect))
        original_init = core.Context.__init__

        def capture(ctx, *args, **kwargs):
            original_init(ctx, *args, **kwargs)
            self.contexts.append(ctx)

        stack.enter_context(patch.object(core.Context, "__init__", capture))
        return stack

    def ranges(self):
        return [(int(params[0]["fromBlock"], 16), int(params[0]["toBlock"], 16))
                for method, params in self.requests if method == "eth_getLogs"]


def catalog_document():
    event = deepcopy(EVENT)
    event.pop("type")
    event.update(signature="Settlement(address,int256,uint256)", topic0=core.topic(EVENT))
    return {"contract_id": "robinhood-" + ADDRESS, "chain_id": 4663,
            "address": ADDRESS, "events": [event]}


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "assets" / "contracts").mkdir(parents=True)
        self.catalog_path = "assets/contracts/fixture.json"
        self.write_catalog(catalog_document())
        root_patch = patch.object(receipts, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def write_catalog(self, document):
        (self.root / self.catalog_path).write_text(json.dumps(document))

    def run_cli(self, fixture, *extra):
        argv = ["receipts", "--catalog", self.catalog_path, "--from-block", "10",
                "--block", "20", "--chunk-blocks", "10", "--deadline", "30", *extra]
        with fixture.patches(), patch.object(analytics, "_PROCESS_STARTED", time.monotonic()), \
                redirect_stdout(io.StringIO()) as output:
            code = analytics.main(argv)
        return code, json.loads(output.getvalue())

    def assert_incomplete(self, result):
        self.assertFalse(result["coverage"]["requested_scope"]["collection_complete"])
        self.assertFalse(result["coverage"]["receipt_scan"]["event_coverage_complete"])

    def test_inclusive_eleven_blocks_chunked_ten_plus_one_without_gaps_or_duplicates(self):
        fixture = Fixture([raw_log(block=10), raw_log(block=20, tx=OTHER_TX)])
        code, result = self.run_cli(fixture)
        self.assertEqual(code, 0, result)
        self.assertEqual(fixture.ranges(), [(10, 19), (20, 20)])
        visited = [block for start, end in fixture.ranges() for block in range(start, end + 1)]
        self.assertEqual(visited, list(range(10, 21)))
        scan = result["coverage"]["receipt_scan"]
        self.assertEqual(scan["missing_ranges"], [])
        self.assertTrue(scan["event_coverage_complete"])
        self.assertTrue(result["coverage"]["requested_scope"]["collection_complete"])
        events = result["metrics"]["receipts"]["events"]
        self.assertEqual(len(events), 2)
        self.assertEqual({event["transactionHash"] for event in events}, {TX, OTHER_TX})
        self.assertTrue(all(event["receipt_verified"] for event in events))

    def test_descriptive_catalog_projects_standard_abi_and_decodes_signed_value(self):
        projected = receipts.load_catalog(self.catalog_path)
        self.assertEqual(projected["abi"], [EVENT])
        fixture = Fixture([raw_log(delta=-7, amount=13)])
        code, result = self.run_cli(fixture)
        self.assertEqual(code, 0, result)
        event = result["metrics"]["receipts"]["events"][0]
        self.assertEqual(event["values"], {"account": ACCOUNT, "delta": -7, "amount": 13})
        self.assertEqual(event["signature"], "Settlement(address,int256,uint256)")
        self.assertEqual(event["topic0"], core.topic(EVENT))

    def test_same_topic0_with_wrong_indexed_layout_is_not_validated(self):
        document = catalog_document()
        document["events"][0]["inputs"][0]["indexed"] = False
        # Indexing is absent from the event signature, so this topic remains identical.
        self.assertEqual(core.topic(dict(document["events"][0], type="event")), core.topic(EVENT))
        self.write_catalog(document)
        fixture = Fixture([raw_log()])
        code, result = self.run_cli(fixture)
        self.assertEqual(code, 2, result)
        self.assert_incomplete(result)
        self.assertTrue(result["errors"])
        self.assertFalse(result["metrics"]["receipts"]["events"])

    def test_matching_topic0_rejects_noncanonical_signed_word(self):
        document = catalog_document()
        event = document["events"][0]
        event["inputs"][1]["type"] = "int8"
        event["signature"] = "Settlement(address,int8,uint256)"
        event["topic0"] = core.topic(dict(event, type="event"))
        self.write_catalog(document)
        malformed = raw_log()
        malformed["topics"][0] = event["topic0"]
        # Low byte encodes -7, but the required signed extension is absent.
        malformed["data"] = "0x" + (249).to_bytes(32, "big").hex() + (13).to_bytes(32, "big").hex()
        code, result = self.run_cli(Fixture([malformed]))
        self.assertEqual(code, 2, result)
        self.assert_incomplete(result)
        self.assertFalse(result["metrics"]["receipts"]["events"])

    def test_multiple_events_in_one_receipt_and_duplicate_scan_rows_are_not_double_counted(self):
        first, second = raw_log(index=0), raw_log(index=1, delta=4, amount=29)
        fixture = Fixture([first, first, second])
        code, result = self.run_cli(fixture, "--tx", TX, "--tx", TX)
        self.assertEqual(code, 0, result)
        events = result["metrics"]["receipts"]["events"]
        transactions = result["metrics"]["receipts"]["transactions"]
        self.assertEqual(len(events), 2)
        self.assertEqual({event["logIndex"] for event in events}, {0, 1})
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0]["selected_event_count"], 2)
        self.assertTrue(all(event["receipt_verified"] for event in events))
        self.assertTrue(all({"scan", "witness"}.issubset(event["evidence_sources"]) for event in events))
        self.assertEqual([params[0] for method, params in fixture.requests
                          if method == "eth_getTransactionReceipt"], [TX])

    def test_failed_missing_and_mismatched_receipts_never_complete_scan(self):
        for failure in ("failed", "missing", "wrong_transaction", "wrong_block", "missing_event", "changed_event"):
            with self.subTest(failure=failure):
                fixture = Fixture([raw_log()])
                receipt = fixture.receipts[TX]
                if failure == "failed":
                    receipt["status"] = "0x0"
                elif failure == "missing":
                    fixture.receipts[TX] = None
                elif failure == "wrong_transaction":
                    receipt["transactionHash"] = OTHER_TX
                elif failure == "wrong_block":
                    receipt["blockHash"] = block_hash(11)
                elif failure == "missing_event":
                    receipt["logs"] = []
                else:
                    receipt["logs"] = [raw_log(amount=99)]
                code, result = self.run_cli(fixture)
                self.assertEqual(code, 2, result)
                self.assert_incomplete(result)
                self.assertTrue(result["errors"])
                self.assertFalse(result["coverage"]["requested_scope"]["receipts_complete"])
                self.assertTrue(all(not event["receipt_verified"]
                                    for event in result["metrics"]["receipts"]["events"]))

    def test_outside_interval_witness_is_excluded_not_counted_as_scanned_event(self):
        for block in (9, 21):
            with self.subTest(block=block):
                fixture = Fixture()
                fixture.receipts[TX] = raw_receipt([raw_log(block=block)], block=block)
                code, result = self.run_cli(fixture, "--tx", TX)
                self.assertEqual(code, 0, result)
                data = result["metrics"]["receipts"]
                self.assertEqual(data["events"], [])
                self.assertEqual(data["transactions"], [])
                self.assertEqual(data["witnesses"][0]["status"], "excluded_outside_interval")
                self.assertEqual(fixture.ranges(), [(10, 19), (20, 20)])
                self.assertTrue(result["coverage"]["receipt_scan"]["event_coverage_complete"])

    def test_http403_is_terminal_and_never_discloses_configured_endpoint(self):
        fixture = Fixture()
        fixture.override = lambda method, params: (True, ProviderFailure("denied " + URL, status=403))
        code, result = self.run_cli(fixture)
        self.assertEqual(code, 2, result)
        self.assertEqual(result["errors"][0]["kind"], "permission")
        self.assertEqual(len(fixture.requests), 1)
        self.assertEqual(len(fixture.connections), 1)
        self.assertEqual(fixture.reads, 0)
        self.assertEqual(fixture.contexts[0]._recoveries, 0)
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertIsNone(result["snapshot"]["rpc_origin"])
        self.assertTrue(all(response.closed for response in fixture.responses))

    def test_classified_range_error_splits_but_unknown_error_never_retries(self):
        for classified in (True, False):
            with self.subTest(classified=classified):
                fixture = Fixture()

                def fail_first(method, params):
                    if method == "eth_getLogs" and len(fixture.ranges()) == 1:
                        message = ("Under the Free tier plan, you can make eth_getLogs requests "
                                   "with up to a 10 block range." if classified
                                   else "Unrecognized provider request failure")
                        return True, ProviderFailure(message + " " + URL)
                    return False, None

                fixture.override = fail_first
                code, result = self.run_cli(fixture)
                self.assertNotIn(SECRET, json.dumps(result))
                if classified:
                    self.assertEqual(code, 0, result)
                    self.assertEqual(fixture.ranges(), [(10, 19), (10, 14), (15, 19), (20, 20)])
                    self.assertEqual(fixture.contexts[0]._recoveries, 1)
                    self.assertTrue(result["coverage"]["receipt_scan"]["event_coverage_complete"])
                else:
                    self.assertEqual(code, 2, result)
                    self.assertEqual(fixture.ranges(), [(10, 19)])
                    self.assertEqual(fixture.contexts[0]._recoveries, 0)
                    self.assert_incomplete(result)
                    self.assertEqual(result["coverage"]["receipt_scan"]["missing_ranges"], [[10, 20]])

    def test_opening_hash_change_invalidates_interval_even_when_closing_is_stable(self):
        fixture = Fixture([raw_log()])

        def reorg_opening(method, params):
            if method == "eth_getBlockByNumber" and params[0] == "0x9" and fixture.header_reads[9]:
                return True, {"number": "0x9", "hash": block_hash(999), "timestamp": hex(1009)}
            return False, None

        fixture.override = reorg_opening
        code, result = self.run_cli(fixture)
        self.assertEqual(code, 2, result)
        self.assert_incomplete(result)
        self.assertFalse(result["coverage"]["requested_scope"]["boundaries_confirmed"])
        self.assertTrue(any(error["kind"] == "integrity" for error in result["errors"]))
        self.assertEqual(len(result["metrics"]["receipts"]["events"]), 1)
        self.assertEqual(result["metrics"]["receipts"]["boundaries"]["closing"]["block_hash"], block_hash(20))

    def test_interrupt_and_deadline_keep_acquired_data_in_json_and_checkpoint(self):
        for reason in ("interrupted_by_SIGTERM", "deadline_exhausted"):
            with self.subTest(reason=reason):
                fixture = Fixture([raw_log()])
                output_path = self.root / (reason + ".json")

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
                code, result = self.run_cli(fixture, "--output", str(output_path))
                self.assertEqual(code, 2, result)
                self.assertEqual(result["stopping_reason"], reason)
                self.assertEqual(result["status"], "partial")
                saved = json.loads(output_path.read_text())
                for document in (result, saved):
                    self.assert_incomplete(document)
                    self.assertEqual(document["coverage"]["receipt_scan"]["covered_ranges"], [[10, 19]])
                    self.assertEqual(document["coverage"]["receipt_scan"]["missing_ranges"], [[20, 20]])
                    event = document["metrics"]["receipts"]["events"][0]
                    self.assertEqual(event["values"]["delta"], -7)
                    self.assertEqual(event["transactionHash"], TX)
                self.assertEqual(fixture.requests[-1][0], "eth_getLogs")

    def test_readonly_collector_uses_only_guarded_configured_transport(self):
        fixture = Fixture([raw_log()])
        code, result = self.run_cli(fixture)
        self.assertEqual(code, 0, result)
        self.assertEqual(set(method for method, _ in fixture.requests),
                         {"eth_chainId", "eth_getBlockByNumber", "eth_getCode",
                          "eth_getLogs", "eth_getTransactionReceipt"})
        self.assertEqual(set(fixture.connections), {(SECRET + ".example", 8443)})
        self.assertEqual(set(fixture.targets), {"/v2/" + SECRET + "?key=" + SECRET})
        self.assertEqual(set(fixture.http_methods), {"POST"})
        self.assertNotIn(SECRET, json.dumps(result))

    def test_receipts_context_rejects_writes_arbitrary_calls_and_endpoint_override_payloads(self):
        cases = [
            ("eth_sendRawTransaction", ["0xdeadbeef"]),
            ("eth_sendTransaction", [{"from": ACCOUNT, "to": ADDRESS}]),
            ("personal_sign", ["0x00", ACCOUNT]),
            ("eth_call", [{"to": ADDRESS, "data": "0xdeadbeef"}, "0x14"]),
            ("eth_call", [{"to": ADDRESS, "data": "0x70a08231" + ACCOUNT[2:].rjust(64, "0")}, "0x14"]),
            ("eth_getLogs", [{"address": ADDRESS, "fromBlock": "0xa", "toBlock": "0x14",
                              "topics": [[core.topic(EVENT)]], "rpc_url": "https://other.example/"}]),
        ]
        for method, params in cases:
            with self.subTest(method=method):
                fixture = Fixture()
                with fixture.patches():
                    ctx = core.Context("receipts", deadline=30)
                    try:
                        with self.assertRaises(core.RpcError) as failure:
                            ctx._rpc(method, params)
                        self.assertEqual(failure.exception.kind, "permission")
                    finally:
                        ctx.close()
                self.assertEqual(fixture.connections, [])

    def test_witness_only_observation_cannot_establish_complete_scan(self):
        fixture = Fixture()
        fixture.receipts[TX] = raw_receipt([raw_log()])

        def unavailable_logs(method, params):
            if method == "eth_getLogs":
                return True, ProviderFailure("historical state unavailable " + URL, status=200)
            return False, None

        fixture.override = unavailable_logs
        code, result = self.run_cli(fixture, "--tx", TX)
        self.assertEqual(code, 2, result)
        self.assert_incomplete(result)
        self.assertFalse(result["coverage"]["requested_scope"]["scan_complete"])
        self.assertEqual(result["coverage"]["receipt_scan"]["covered_ranges"], [])
        self.assertEqual(result["coverage"]["receipt_scan"]["missing_ranges"], [[10, 20]])
        events = result["metrics"]["receipts"]["events"]
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["receipt_verified"])
        self.assertIn("witness", events[0]["evidence_sources"])
        self.assertNotIn("scan", events[0]["evidence_sources"])
        self.assertTrue(any(error["kind"] == "pruned" for error in result["errors"]))
        self.assertNotIn(SECRET, json.dumps(result))

    def test_receipt_proven_event_omitted_from_successful_scan_is_integrity_failure(self):
        fixture = Fixture()
        fixture.receipts[TX] = raw_receipt([raw_log()])
        code, result = self.run_cli(fixture, "--tx", TX)
        self.assertEqual(code, 2, result)
        self.assert_incomplete(result)
        self.assertTrue(any(error["kind"] == "integrity" for error in result["errors"]))
        self.assertEqual(len(result["metrics"]["receipts"]["events"]), 1)
        self.assertNotIn("scan", result["metrics"]["receipts"]["events"][0]["evidence_sources"])

    def test_zero_scoped_events_does_not_claim_zero_economic_total(self):
        code, result = self.run_cli(Fixture())
        self.assertEqual(code, 0, result)
        self.assertTrue(result["coverage"]["requested_scope"]["collection_complete"])
        self.assertTrue(result["coverage"]["receipt_scan"]["event_coverage_complete"])
        self.assertEqual(result["metrics"]["receipts"]["events"], [])
        self.assertEqual(result["metrics"]["receipts"]["transactions"], [])
        self.assertEqual(result["coverage"]["receipt_scan"]["rows"], 0)
        self.assertIsNone(result["metrics"]["receipts"].get("economic_total"))
        limitations = " ".join(str(item) for item in result["not_proven"]).lower()
        self.assertIn("economic", limitations)
        self.assertIn("revenue", limitations)

    def test_cli_cannot_override_provider_with_new_endpoint_flag(self):
        fixture = Fixture()
        code, result = self.run_cli(fixture, "--rpc-url", "https://other.example/")
        self.assertEqual(code, 1, result)
        self.assertEqual(fixture.requests, [])
        self.assertNotIn("other.example", json.dumps(result))


    def test_permission_after_acquired_page_stops_before_any_further_rpc(self):
        fixture = Fixture([raw_log()])

        def deny_second_page(method, params):
            if method == "eth_getLogs" and len(fixture.ranges()) == 2:
                return True, ProviderFailure("Permission denied " + URL, status=403)
            return False, None

        fixture.override = deny_second_page
        code, result = self.run_cli(fixture)
        self.assertEqual(code, 2, result)
        self.assert_incomplete(result)
        self.assertEqual(fixture.ranges(), [(10, 19), (20, 20)])
        self.assertEqual(fixture.requests[-1][0], "eth_getLogs")
        self.assertEqual(fixture.contexts[0]._recoveries, 0)
        self.assertEqual(result["errors"][-1]["kind"], "permission")
        self.assertEqual(result["coverage"]["receipt_scan"]["covered_ranges"], [[10, 19]])
        self.assertEqual(len(result["metrics"]["receipts"]["events"]), 1)
        self.assertNotIn(SECRET, json.dumps(result))


    def test_unavailable_opening_header_retains_code_evidence_without_claiming_confirmation(self):
        fixture = Fixture([raw_log()])

        def unavailable_opening(method, params):
            if method == "eth_getBlockByNumber" and params[0] == "0x9":
                return True, ProviderFailure("historical state unavailable " + URL, status=200)
            return False, None

        fixture.override = unavailable_opening
        code, result = self.run_cli(fixture)
        self.assertEqual(code, 2, result)
        self.assertEqual(result["status"], "partial")
        self.assert_incomplete(result)
        self.assertTrue(any(error["kind"] == "pruned" for error in result["errors"]))
        self.assertFalse(any(error["kind"] == "fatal" for error in result["errors"]))
        scope = result["coverage"]["requested_scope"]
        for field in ("scan_complete", "receipts_complete", "boundaries_confirmed", "code_identities_complete"):
            self.assertFalse(scope[field])
        self.assertTrue(scope["scan_retrieval_complete"])
        self.assertTrue(scope["receipts_reconciliation_complete"])
        self.assertTrue(scope["code_identities_observed"])
        opening = result["metrics"]["receipts"]["boundaries"]["opening"]
        self.assertEqual(opening["code"]["byte_count"], 2)
        self.assertNotEqual(opening["recheck_status"], "confirmed")
        event = result["metrics"]["receipts"]["events"][0]
        self.assertEqual(event["values"], {"account": ACCOUNT, "delta": -7, "amount": 13})
        self.assertTrue(event["receipt_verified"])
        self.assertNotIn(SECRET, json.dumps(result))

    def test_catalog_requires_explicit_boolean_indexed_layout_before_retrieval(self):
        for invalid in (None, 0, "false"):
            with self.subTest(indexed=invalid):
                document = catalog_document()
                field = document["events"][0]["inputs"][0]
                if invalid is None:
                    del field["indexed"]
                else:
                    field["indexed"] = invalid
                self.write_catalog(document)
                with self.assertRaises(core.RpcError) as caught:
                    receipts.load_catalog(self.catalog_path)
                self.assertEqual(caught.exception.kind, "abi")


if __name__ == "__main__":
    unittest.main()

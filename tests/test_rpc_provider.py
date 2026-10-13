"""Configured-provider transport regressions; every network boundary is synthetic."""
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analytics
import netstack_core as core
import netstack_methodology as methodology

SECRET = "provider-secret-do-not-print"
URL = "https://" + SECRET + ".example:8443/v2/" + SECRET + "?key=" + SECRET
HASH = "0x" + "bb" * 32
ALCHEMY_RANGE_ERROR = {
    "code": -32600,
    "message": ("Under the Free tier plan, you can make eth_getLogs requests with up to a 10 block range. "
                "Based on your parameters, this block range should work: [0x5293ea4, 0x5293ead]. "
                "Upgrade to PAYG for expanded block range."),
    "data": URL,
}
LOG_ADDRESS = "0x" + "11" * 20


class Response:
    def __init__(self, owner, status=200, error=None, chain_id=4663, headers=None, transform=None):
        self.owner, self.status, self.error = owner, status, error
        self.chain_id, self.headers = chain_id, headers or {}
        self.transform = transform
        self.body = b""
        self.closed = False

    def request(self, method, path, body, headers):
        request = json.loads(body)
        self.owner.requests.append((method, path, request, headers))
        def member(entry):
            result = (hex(self.chain_id) if entry["method"] == "eth_chainId" else
                      [] if entry["method"] == "eth_getLogs" else
                      {"number": "0xa", "timestamp": "0x64", "hash": HASH})
            envelope = {"jsonrpc": "2.0", "id": entry["id"], "ignored_provider_field": SECRET}
            envelope.update(error=self.error) if self.error is not None else envelope.update(result=result)
            return envelope
        envelope = [member(entry) for entry in request] if isinstance(request, list) else member(request)
        if self.transform is not None:
            envelope = self.transform(envelope)
        self.body = envelope if isinstance(envelope, bytes) else json.dumps(envelope).encode()

    def getresponse(self):
        return self

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, size):
        self.owner.reads += 1
        result, self.body = self.body[:size], self.body[size:]
        return result

    def close(self):
        self.closed = True


class ProviderSelection(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        dns = patch.object(core.socket, "getaddrinfo", side_effect=AssertionError("Real DNS forbidden"))
        dns.start()
        self.addCleanup(dns.stop)
        self.requests, self.connections, self.reads = [], [], 0

    def context(self, **kwargs):
        ctx = core.Context("advance", deadline=30, **kwargs)
        self.addCleanup(ctx.close)
        return ctx

    def connection(self, host, port, *, timeout, context, network_policy):
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 15)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.connections.append((host, port))
        return Response(self)

    def test_unconfigured_defaults_to_public_and_does_not_reread_environment(self):
        ctx = self.context()
        os.environ["NETSTACK_RPC_URL"] = URL
        with patch.object(core, "_FixedHTTPSConnection", side_effect=self.connection):
            self.assertEqual(ctx._rpc("eth_chainId", []), hex(4663))
        self.assertEqual(self.connections, [(core.RPC_HOST, 443)])
        self.assertEqual(self.requests[0][1], "/")
        self.assertEqual(ctx.rpc_provenance["rpc_provider"], "public")
        self.assertEqual(ctx.rpc_provenance["rpc_origin"], "https://" + core.RPC_HOST)

    def test_configured_selection_is_fixed_through_pin_reads_and_fresh_recheck(self):
        os.environ["NETSTACK_RPC_URL"] = URL
        ctx = self.context()
        os.environ["NETSTACK_RPC_URL"] = "https://different.example/other"
        with patch.object(core, "_FixedHTTPSConnection", side_effect=self.connection):
            ctx.pin("10")
            ctx.header(10)  # Cached inside this run only.
            ctx.recheck()
        self.assertEqual(self.connections, [(SECRET + ".example", 8443)] * 3)
        self.assertEqual([row[1] for row in self.requests], ["/v2/" + SECRET + "?key=" + SECRET] * 3)
        self.assertEqual([row[2]["method"] for row in self.requests],
                         ["eth_chainId", "eth_getBlockByNumber", "eth_getBlockByNumber"])
        self.assertEqual([row[2]["params"] for row in self.requests[1:]], [["0xa", False]] * 2)
        self.assertEqual(ctx.result["snapshot"]["recheck_status"], "confirmed")
        self.assertEqual(ctx.result["snapshot"]["rpc_provider"], "configured")
        self.assertIsNone(ctx.result["snapshot"]["rpc_origin"])
        self.assertRegex(ctx.rpc_provenance["rpc_run_id"], r"^[0-9a-f]{32}$")
        self.assertEqual(ctx.result["snapshot"]["rpc_run_id"], ctx.rpc_provenance["rpc_run_id"])
        self.assertNotIn(SECRET, core.serialize_result(ctx.result))
        self.assertNotIn(SECRET, repr(ctx._rpc_endpoint))
        self.assertNotIn("Authorization", self.requests[0][3])

    def test_run_attribution_is_not_a_stable_endpoint_fingerprint(self):
        os.environ["NETSTACK_RPC_URL"] = URL
        first = self.context()
        first_id = first.rpc_provenance["rpc_run_id"]
        with patch.object(core, "_FixedHTTPSConnection", side_effect=self.connection):
            first.pin("10")
        first.close()
        second = self.context()
        self.assertNotEqual(first_id, second.rpc_provenance["rpc_run_id"])
        with patch.object(core, "_FixedHTTPSConnection", side_effect=self.connection):
            second.pin("10")
        self.assertEqual(len(self.connections), 4)  # No financial state survives a new run.

    def test_valid_uri_targets_are_preserved_without_decoding_secrets(self):
        cases = [("https://RPC.example", "rpc.example", 443, "/"),
                 ("https://rpc.example?key=a%2Fb%2Bc", "rpc.example", 443, "/?key=a%2Fb%2Bc"),
                 ("https://rpc.example/v2/a%2Fb?x=1&x=2", "rpc.example", 443, "/v2/a%2Fb?x=1&x=2"),
                 ("https://[2606:4700:4700::1111]:8443/rpc", "2606:4700:4700::1111", 8443, "/rpc"),
                 ("https://8.8.8.8/", "8.8.8.8", 443, "/")]
        for url, host, port, target in cases:
            with self.subTest(url=url):
                os.environ["NETSTACK_RPC_URL"] = url
                endpoint = core._rpc_endpoint()
                self.assertEqual((endpoint.host, endpoint.port, endpoint.target), (host, port, target))
                self.assertTrue(endpoint.configured)

    def test_malformed_configuration_is_rejected_before_any_transport(self):
        cases = ["", "http://rpc.example/", "https:///rpc", "https://user:pass@rpc.example/",
                 "https://@rpc.example/", "https://rpc.example/#", "https://rpc.example/#fragment",
                 " https://rpc.example/", "https://rpc.example/\n", "https://rpc.example/\tkey",
                 "https://rpc.example/\\path", "https://rpc.example:0/", "https://rpc.example:65536/",
                 "https://rpc.example:/", "https://rpc.example:bad/", "https://rpc..example/",
                 "https://rpc.example../", "https://rpc_example/", "https://-rpc.example/",
                 "https://rpc.example/%xx", "https://rpc.example/%", "https://rpc.example/caf" + chr(233),
                 "https://[::1]/", "https://127.0.0.1/", "https://[fe80::1%25eth0]/",
                 "https://[2606:4700:4700::1111]suffix/", "https://10.0.0.1/",
                 "https://rpc.example/" + "a" * 8192]
        with patch.object(core, "_FixedHTTPSConnection", side_effect=AssertionError("Transport forbidden")):
            for url in cases:
                with self.subTest(url=url[:80]):
                    os.environ["NETSTACK_RPC_URL"] = url
                    with self.assertRaises(core.RpcError) as failure:
                        self.context()
                    self.assertEqual(failure.exception.kind, "input")
                    if url:
                        self.assertNotIn(url, str(failure.exception))
                    self.assertTrue(failure.exception.__suppress_context__)

    def test_http_denial_and_redirect_are_terminal_without_body_or_header_disclosure(self):
        os.environ["NETSTACK_RPC_URL"] = URL
        for status in (401, 403, 407, 301, 302, 307, 308):
            with self.subTest(status=status):
                ctx = self.context()
                response = Response(self, status, error=ALCHEMY_RANGE_ERROR,
                                    headers={"Location": URL, "WWW-Authenticate": SECRET})
                with patch.object(core, "_FixedHTTPSConnection", return_value=response) as transport:
                    for _ in range(2):
                        with self.assertRaises(core.RpcError) as failure:
                            ctx._rpc("eth_chainId", [])
                        self.assertEqual(failure.exception.kind, "permission")
                        self.assertNotIn(SECRET, str(failure.exception))
                    self.assertEqual(transport.call_count, 1)
                self.assertEqual(self.reads, 0)
                self.assertEqual(ctx._recoveries, 0)
                self.assertTrue(response.closed)
                self.assertEqual(ctx.result["snapshot"]["rpc_provider"], "configured")
                ctx.close()

    def test_provider_error_messages_and_codes_are_never_echoed(self):
        os.environ["NETSTACK_RPC_URL"] = URL
        for message, kind in (("access denied " + URL, "permission"),
                              ("historical state unavailable " + SECRET, "pruned"),
                              (SECRET, "remote")):
            with self.subTest(kind=kind):
                ctx = self.context()
                response = Response(self, error={"code": 123456789, "message": message, "data": URL})
                with patch.object(core, "_FixedHTTPSConnection", return_value=response):
                    with self.assertRaises(core.RpcError) as failure:
                        ctx._rpc("eth_chainId", [])
                self.assertEqual(failure.exception.kind, kind)
                self.assertNotIn(SECRET, str(failure.exception))
                self.assertNotIn("123456789", str(failure.exception))
                if kind == "permission":
                    self.assertIs(ctx._terminal_error, failure.exception)
                ctx.close()

    def log_request(self, start=0, end=31):
        return ("eth_getLogs", [{"address": LOG_ADDRESS, "fromBlock": hex(start),
                                 "toBlock": hex(end), "topics": [[core.TRANSFER_TOPIC]]}])

    def test_http400_range_error_reaches_bounded_adaptive_log_scan(self):
        os.environ["NETSTACK_RPC_URL"] = URL
        ctx = self.context()
        ctx.block = 31
        responses = []
        def connect(*args, **kwargs):
            response = self.connection(*args, **kwargs)
            if len(self.connections) in (1, 2, 5):
                response.status, response.error = 400, ALCHEMY_RANGE_ERROR
            responses.append(response)
            return response
        abi = core.load_json("assets/analytics/v2-interface.json")["pair_abi"]
        with patch.object(core, "_FixedHTTPSConnection", side_effect=connect):
            self.assertEqual(list(ctx.logs("range", LOG_ADDRESS, abi, ["Transfer"], 0, 31)), [[], [], [], []])
        queries = [row[2]["params"][0] for row in self.requests]
        self.assertEqual([(int(query["fromBlock"], 16), int(query["toBlock"], 16)) for query in queries],
                         [(0, 31), (0, 15), (0, 7), (8, 15), (16, 31), (16, 23), (24, 31)])
        self.assertEqual(self.connections, [(SECRET + ".example", 8443)] * 7)
        self.assertEqual((ctx._members, ctx._recoveries), (7, 3))
        self.assertTrue(ctx.result["coverage"]["range"]["event_coverage_complete"])
        self.assertTrue(all(response.closed for response in responses))
        self.assertNotIn(SECRET, core.serialize_result(ctx.result))

    def test_http400_range_error_stops_at_recovery_budget_with_honest_coverage(self):
        ctx = self.context()
        ctx.block = 31
        ctx._recoveries = 10
        response = Response(self, status=400, error=ALCHEMY_RANGE_ERROR)
        abi = core.load_json("assets/analytics/v2-interface.json")["pair_abi"]
        with patch.object(core, "_FixedHTTPSConnection", return_value=response) as transport:
            with self.assertRaises(core.RpcError) as failure:
                list(ctx.logs("range", LOG_ADDRESS, abi, ["Transfer"], 0, 31))
        self.assertEqual(failure.exception.kind, "range")
        self.assertFalse(failure.exception.retryable)
        self.assertEqual((transport.call_count, ctx._recoveries), (1, 10))
        coverage = ctx.result["coverage"]["range"]
        self.assertEqual(coverage["covered_ranges"], [])
        self.assertEqual(coverage["missing_ranges"], [[0, 31]])
        self.assertEqual(coverage["failure_kind"], "range")
        self.assertFalse(coverage["event_coverage_complete"])
        self.assertNotIn(SECRET, core.serialize_result(ctx.result))

    def test_http400_permission_errors_are_terminal_before_range_classification(self):
        os.environ["NETSTACK_RPC_URL"] = URL
        messages = ["Access denied " + URL,
                    ALCHEMY_RANGE_ERROR["message"] + " Permission denied " + URL]
        for message in messages:
            for batched in (False, True):
                with self.subTest(message=message, batched=batched):
                    ctx = self.context()
                    error = {"code": -32600, "message": message, "data": URL}
                    def transform(values):
                        if isinstance(values, list):
                            values[0]["error"] = ALCHEMY_RANGE_ERROR
                        return values
                    response = Response(self, status=400, error=error, transform=transform)
                    requests = [self.log_request(), ("eth_chainId", [])] if batched else [self.log_request()]
                    with patch.object(core, "_FixedHTTPSConnection", return_value=response) as transport:
                        with self.assertRaises(core.RpcError) as failure:
                            ctx._exchange(requests)
                        self.assertEqual(failure.exception.kind, "permission")
                        self.assertIs(ctx._terminal_error, failure.exception)
                        self.assertFalse(failure.exception.retryable)
                        self.assertFalse(failure.exception.splittable)
                        self.assertNotIn(SECRET, "".join(traceback.format_exception(failure.exception)))
                        for followup in (lambda: ctx._rpc("eth_chainId", []), ctx.recheck):
                            with self.assertRaises(core.RpcError) as subsequent:
                                followup()
                            self.assertIs(subsequent.exception, failure.exception)
                        self.assertEqual(transport.call_count, 1)
                        self.assertEqual(transport.call_args.args, (SECRET + ".example", 8443))
                    self.assertEqual(ctx._recoveries, 0)
                    self.assertTrue(response.closed)
                    ctx.close()

    def test_http400_unrecognized_errors_remain_nonretryable_http_failures(self):
        cases = [
            (self.log_request(), {"code": -32600, "message": "Invalid range " + URL}),
            (self.log_request(), {"code": -32005, "message": ALCHEMY_RANGE_ERROR["message"]}),
            (self.log_request(), {"code": "-32600", "message": ALCHEMY_RANGE_ERROR["message"]}),
            (self.log_request(), {"code": -32600, "message": "rate limit exceeded " + SECRET}),
            (self.log_request(), {"code": -32600, "message": "temporarily busy " + SECRET}),
            (self.log_request(), {"code": -32600, "message": SECRET}),
            (self.log_request(), {"code": -32600}),
            (self.log_request(), {"code": "-32600", "message": "Access denied " + URL}),
            (self.log_request(), {"code": True, "message": "Permission denied " + URL}),
            (self.log_request(), SECRET),
            (("eth_chainId", []), ALCHEMY_RANGE_ERROR),
        ]
        for request, error in cases:
            with self.subTest(method=request[0], error=error):
                ctx = self.context()
                response = Response(self, status=400, error=error)
                with patch.object(core, "_FixedHTTPSConnection", return_value=response) as transport:
                    with self.assertRaises(core.RpcError) as failure:
                        ctx._rpc(*request)
                self.assertEqual(failure.exception.kind, "http")
                self.assertFalse(failure.exception.retryable)
                self.assertFalse(failure.exception.splittable)
                self.assertNotIn(SECRET, "".join(traceback.format_exception(failure.exception)))
                self.assertEqual((transport.call_count, ctx._recoveries), (1, 0))
                self.assertTrue(response.closed)
                ctx.close()

    def test_http400_requires_matching_unambiguous_error_envelope(self):
        transforms = [
            lambda value: dict(value, id=value["id"] + 1),
            lambda value: dict(value, id=True),
            lambda value: dict(value, id=None),
            lambda value: dict(value, jsonrpc="1.0"),
            lambda value: dict(value, result=[]),
            lambda value: {"jsonrpc": "2.0", "id": value["id"], "result": []},
            lambda value: {"jsonrpc": "2.0", "id": value["id"]},
            lambda value: [value],
            lambda value: ("<html>" + SECRET + "</html>").encode(),
            lambda value: b'{"jsonrpc":"2.0","id":1,"id":1,"error":'
                          + json.dumps(ALCHEMY_RANGE_ERROR).encode() + b"}",
        ]
        for transform in transforms:
            with self.subTest(transform=transform):
                ctx = self.context()
                response = Response(self, status=400, error=ALCHEMY_RANGE_ERROR, transform=transform)
                with patch.object(core, "_FixedHTTPSConnection", return_value=response) as transport:
                    with self.assertRaises(core.RpcError) as failure:
                        ctx._rpc(*self.log_request())
                self.assertEqual(failure.exception.kind, "http")
                self.assertFalse(failure.exception.splittable)
                self.assertFalse(failure.exception.retryable)
                self.assertNotIn(SECRET, "".join(traceback.format_exception(failure.exception)))
                self.assertEqual(transport.call_count, 1)
                self.assertTrue(response.closed)
                ctx.close()

    def test_http400_batch_checks_all_ids_and_never_commits_success_results(self):
        cases = [
            (lambda values: list(reversed(values)), True),
            (lambda values: [values[0], values[0]], False),
            (lambda values: values[:1], False),
            (lambda values: values[0], False),
            (lambda values: [values[0], dict(values[1], id=9999)], False),
            (lambda values: [values[0], {"jsonrpc": "2.0", "id": values[1]["id"], "result": []}], False),
        ]
        for transform, valid in cases:
            with self.subTest(valid=valid, transform=transform):
                ctx = self.context()
                accepted = Mock()
                response = Response(self, status=400, error=ALCHEMY_RANGE_ERROR, transform=transform)
                with patch.object(core, "_FixedHTTPSConnection", return_value=response) as transport:
                    if valid:
                        values = ctx._exchange([self.log_request(), ("eth_chainId", [])], accept=accepted)
                        self.assertEqual([value.kind for value in values], ["range", "http"])
                        self.assertTrue(values[0].splittable)
                        self.assertFalse(values[1].splittable)
                    else:
                        with self.assertRaises(core.RpcError) as failure:
                            ctx._exchange([self.log_request(), self.log_request()], accept=accepted)
                        self.assertEqual(failure.exception.kind, "http")
                        accepted.assert_not_called()
                self.assertEqual(transport.call_count, 1)
                self.assertTrue(response.closed)
                ctx.close()

    def test_http400_body_uses_existing_byte_encoding_and_deadline_bounds(self):
        cases = [
            ({"Content-Encoding": "gzip"}, None, None, "http", False),
            ({"Content-Length": "99999999"}, None, None, "http", False),
            ({"Content-Length": SECRET}, None, None, "http", False),
            ({}, 16, None, "http", True),
            ({}, None, 16, "response_byte_limit", True),
        ]
        for headers, raw_limit, total_limit, kind, reads in cases:
            with self.subTest(kind=kind, headers=headers):
                ctx = self.context()
                response = Response(self, status=400, error=ALCHEMY_RANGE_ERROR, headers=headers)
                self.reads = 0
                with patch.object(core, "_FixedHTTPSConnection", return_value=response), \
                     patch.object(core, "MAX_RESPONSE_BYTES", raw_limit or core.MAX_RESPONSE_BYTES), \
                     patch.object(core, "MAX_TOTAL_BYTES", total_limit or core.MAX_TOTAL_BYTES):
                    with self.assertRaises((core.RpcError, core.StopRun)) as failure:
                        ctx._rpc(*self.log_request())
                if isinstance(failure.exception, core.StopRun):
                    self.assertEqual(failure.exception.reason, kind)
                else:
                    self.assertEqual(failure.exception.kind, kind)
                    self.assertFalse(failure.exception.splittable)
                    self.assertFalse(failure.exception.retryable)
                self.assertEqual(self.reads > 0, reads)
                self.assertEqual(ctx._raw_bytes > 0, reads)
                self.assertTrue(response.closed)
                self.assertIsNone(ctx._attempt_end)
                ctx.close()

        ctx = self.context()
        response = Response(self, status=400, error=ALCHEMY_RANGE_ERROR)
        def expire(size):
            self.assertIsNotNone(ctx._attempt_end)
            ctx._stop("deadline_exhausted")
        with patch.object(core, "_FixedHTTPSConnection", return_value=response), \
             patch.object(response, "read", side_effect=expire):
            with self.assertRaises(core.StopRun) as failure:
                ctx._rpc(*self.log_request())
        self.assertEqual(failure.exception.reason, "deadline_exhausted")
        self.assertTrue(response.closed)
        self.assertIsNone(ctx._attempt_end)

    def test_rate_limit_recovers_only_on_selected_provider_with_existing_budget(self):
        os.environ["NETSTACK_RPC_URL"] = URL
        clock = [0.0]
        with patch.object(core.time, "monotonic", side_effect=lambda: clock[0]):
            ctx = self.context()
        waits = []
        def sleep(seconds):
            waits.append(seconds)
            clock[0] += seconds
        def connect(*args, **kwargs):
            response = self.connection(*args, **kwargs)
            if len(self.connections) == 1:
                response.status = 429
                response.headers = {"Retry-After": "3", "X-Provider-Diagnostic": SECRET}
            return response
        with patch.object(core, "_FixedHTTPSConnection", side_effect=connect), \
             patch.object(core.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(core.time, "sleep", side_effect=sleep):
            self.assertEqual(ctx._rpc("eth_chainId", []), hex(4663))
        self.assertEqual(self.connections, [(SECRET + ".example", 8443)] * 2)
        self.assertEqual(waits, [3.0])
        self.assertEqual((ctx._members, ctx._recoveries), (2, 1))

    def test_dns_tls_and_http_errors_have_distinct_sanitized_diagnostics(self):
        os.environ["NETSTACK_RPC_URL"] = URL
        for error, kind in ((socket.gaierror(socket.EAI_NONAME, URL), "dns"),
                            (ssl.SSLCertVerificationError(1, URL), "permission"),
                            (ssl.SSLError(1, URL), "tls"),
                            (PermissionError(URL), "permission")):
            with self.subTest(kind=kind):
                ctx = self.context()
                with patch.object(core, "_FixedHTTPSConnection", side_effect=error) as transport:
                    with self.assertRaises(core.RpcError) as failure:
                        ctx._rpc("eth_chainId", [])
                self.assertEqual(failure.exception.kind, kind)
                rendered = "".join(traceback.format_exception(failure.exception))
                self.assertNotIn(SECRET, rendered)
                self.assertNotIn("Cloudflare", rendered)
                self.assertEqual(transport.call_count, 1)
                ctx.close()

    def test_configured_provider_still_requires_chain_4663(self):
        os.environ["NETSTACK_RPC_URL"] = URL
        ctx = self.context()
        with patch.object(core, "_FixedHTTPSConnection", return_value=Response(self, chain_id=1)) as transport:
            with self.assertRaises(core.RpcError) as failure:
                ctx.pin("10")
        self.assertEqual(failure.exception.kind, "integrity")
        self.assertEqual(transport.call_count, 1)
        self.assertIsNone(ctx.block)

    def test_configured_provider_does_not_relax_readonly_or_resource_limits(self):
        os.environ["NETSTACK_RPC_URL"] = URL
        ctx = self.context()
        with patch.object(core, "_FixedHTTPSConnection", side_effect=AssertionError("Transport forbidden")):
            with self.assertRaises(core.RpcError):
                ctx._exchange_once([("eth_sendRawTransaction", ["0x00"])])
            with self.assertRaises(core.RpcError):
                ctx._exchange_once([("eth_call", [{"to": "0x" + "11" * 20, "data": "0xdeadbeef"}, "latest"])])
            ctx._members = ctx._member_limit
            with self.assertRaises(core.StopRun) as failure:
                ctx._rpc("eth_chainId", [])
            self.assertEqual(failure.exception.reason, "rpc_member_limit")

    def test_offline_cli_ignores_invalid_config_and_has_no_rpc_capability(self):
        os.environ["NETSTACK_RPC_URL"] = "http://user:" + SECRET + "@localhost/#fragment"
        os.environ.update(NETSTACK_NETWORK_MODE="invalid", NETSTACK_MANAGED_EGRESS_CIDRS=SECRET)
        with patch.object(core, "_FixedHTTPSConnection", side_effect=AssertionError("Transport forbidden")), \
             patch.object(analytics, "_PROCESS_STARTED", time.monotonic()), \
             patch.object(analytics, "_emit", return_value=True) as emit:
            self.assertEqual(analytics.main(["advance", "provenance"]), 0)
        text = emit.call_args.args[0]
        self.assertNotIn(SECRET, text)
        self.assertEqual(json.loads(text)["snapshot"], {})
        ctx = self.context(offline=True)
        with self.assertRaises(core.RpcError) as failure:
            ctx._rpc("eth_chainId", [])
        self.assertEqual(failure.exception.kind, "permission")

    def test_configured_cli_denial_redacts_stdout_and_saved_checkpoint(self):
        os.environ["NETSTACK_RPC_URL"] = URL
        response = Response(self, status=403, headers={"WWW-Authenticate": SECRET, "Location": URL})
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(core, "_FixedHTTPSConnection", return_value=response) as transport, \
             patch.object(analytics, "_PROCESS_STARTED", time.monotonic()), \
             patch.object(analytics, "_emit", return_value=True) as emit:
            output = Path(directory).resolve() / "denied.json"
            self.assertEqual(analytics.main(["advance", "--view", "capacity", "--output", str(output)]), 2)
            text = emit.call_args.args[0]
            self.assertEqual(output.read_text(), text)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(self.reads, 0)
        self.assertNotIn(SECRET, text)
        report = json.loads(text)
        self.assertEqual(report["snapshot"]["rpc_provider"], "configured")
        self.assertIsNone(report["snapshot"]["rpc_origin"])
        self.assertNotIn("block_number", report["snapshot"])
        self.assertEqual(report["errors"][-1]["kind"], "permission")
        self.assertIn("403", report["errors"][-1]["message"])

    def test_invalid_config_cli_is_sanitized_without_network_or_fallback(self):
        os.environ["NETSTACK_RPC_URL"] = "https://user:" + SECRET + "@rpc.example/"
        with patch.object(core, "_FixedHTTPSConnection", side_effect=AssertionError("Transport forbidden")), \
             patch.object(analytics, "_PROCESS_STARTED", time.monotonic()), \
             patch.object(analytics, "_emit", return_value=True) as emit:
            self.assertEqual(analytics.main(["advance", "--view", "capacity"]), 1)
        text = emit.call_args.args[0]
        self.assertNotIn(SECRET, text)
        self.assertEqual(json.loads(text)["errors"][-1]["kind"], "input")


    def test_managed_policy_is_captured_before_pin_and_never_discloses_ranges(self):
        os.environ.update(NETSTACK_RPC_URL=URL, NETSTACK_NETWORK_MODE="managed-egress",
                          NETSTACK_MANAGED_EGRESS_CIDRS="198.18.0.1/32")
        ctx = self.context()
        os.environ.update(NETSTACK_NETWORK_MODE="public", NETSTACK_MANAGED_EGRESS_CIDRS="invalid")
        policies = []
        def connect(*args, **kwargs):
            policies.append(kwargs["network_policy"])
            return self.connection(*args, **kwargs)
        with patch.object(core, "_FixedHTTPSConnection", side_effect=connect):
            ctx.pin("10")
            ctx.recheck()
        self.assertEqual(ctx.result["snapshot"]["recheck_status"], "confirmed")
        self.assertEqual(ctx.result["snapshot"]["network_mode"], "managed-egress")
        self.assertTrue(all(policy is ctx._network_policy for policy in policies))
        self.assertNotIn("198.18.0.1", core.serialize_result(ctx.result) + repr(ctx._network_policy))
        self.assertNotIn(SECRET, core.serialize_result(ctx.result))

    def test_invalid_managed_configuration_fails_before_transport(self):
        cases = [("unexpected", None), ("managed-egress", None), ("managed-egress", ""),
                 ("public", "198.18.0.1/32"), ("managed-egress", "0.0.0.0/0"),
                 ("managed-egress", "198.18.0.1"), ("managed-egress", "198.18.0.1/15"),
                 ("managed-egress", "198.18.0.1/032"), ("managed-egress", "198.18.0.1/255.255.255.255"),
                 ("managed-egress", "198.18.0.1/32,"), ("managed-egress", " 198.18.0.1/32"),
                 ("managed-egress", "198.18.0.1/32,198.18.0.1/32"),
                 ("managed-egress", "198.18.0.0/15,198.18.0.1/32"),
                 ("managed-egress", "::ffff:198.18.0.1/128"),
                 ("managed-egress", ",".join("198.18.0.%d/32" % i for i in range(17))),
                 ("managed-egress", SECRET * 100)]
        for mode, cidrs in cases:
            with self.subTest(mode=mode, cidrs=cidrs), patch.dict(os.environ, {}, clear=True), \
                    patch.object(core, "_FixedHTTPSConnection", side_effect=AssertionError("Transport forbidden")):
                os.environ["NETSTACK_NETWORK_MODE"] = mode
                if cidrs is not None:
                    os.environ["NETSTACK_MANAGED_EGRESS_CIDRS"] = cidrs
                with self.assertRaises(core.RpcError) as failure:
                    self.context()
                self.assertEqual(failure.exception.kind, "input")
                self.assertNotIn(SECRET, "".join(traceback.format_exception(failure.exception)))

    def test_managed_mode_does_not_retry_denial_redirect_or_wrong_chain(self):
        os.environ.update(NETSTACK_NETWORK_MODE="managed-egress", NETSTACK_MANAGED_EGRESS_CIDRS="198.18.0.1/32")
        for status, chain_id, kind in ((403, 4663, "permission"), (302, 4663, "permission"), (200, 1, "integrity")):
            with self.subTest(status=status, chain_id=chain_id):
                ctx = self.context()
                with patch.object(core, "_FixedHTTPSConnection",
                                  return_value=Response(self, status=status, chain_id=chain_id)) as transport:
                    with self.assertRaises(core.RpcError) as failure:
                        ctx.pin("10")
                self.assertEqual(failure.exception.kind, kind)
                self.assertEqual(transport.call_count, 1)
                self.assertIsNone(ctx.block)
                ctx.close()

class ConnectionSafety(unittest.TestCase):
    def answer(self, address, port=8443):
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        destination = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
        return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", destination)

    def managed_policy(self, cidr="198.18.0.1/32"):
        return core._NetworkPolicy("managed-egress", (core.ipaddress.IPv4Network(cidr),))

    def test_managed_rpc_and_publisher_connect_only_to_operator_pinned_dns(self):
        for cls, host, port in ((core._FixedHTTPSConnection, "rpc.example", 8443),
                                (methodology._PublisherHTTPSConnection, methodology.HOST, 443)):
            with self.subTest(host=host):
                context, sock, wrapped = ssl.create_default_context(), Mock(), Mock()
                with patch.object(core.socket, "getaddrinfo", return_value=[self.answer("198.18.0.1", port)]) as lookup, \
                        patch.object(core.socket, "socket", return_value=sock), \
                        patch.object(context, "wrap_socket", return_value=wrapped) as tls:
                    connection = cls(host, port, timeout=5, context=context, network_policy=self.managed_policy())
                    connection.connect()
                    lookup.assert_called_once_with(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
                    sock.connect.assert_called_once_with(("198.18.0.1", port))
                    tls.assert_called_once_with(sock, server_hostname=host)
                    self.assertIs(connection.sock, wrapped)
                    connection.close()

    def test_managed_cidr_is_not_a_general_private_or_literal_ip_permission(self):
        for host, address in (("rpc.example", "198.18.0.2"), ("rpc.example", "127.0.0.1"),
                              ("rpc.example", "169.254.169.254"), ("rpc.example", "10.0.0.1"),
                              ("rpc.example", "::ffff:198.18.0.1"), ("198.18.0.1", "198.18.0.1"),
                              ("198.18.0.1.", "198.18.0.1"), ("198.18.1", "198.18.0.1"),
                              ("0xc6120001", "198.18.0.1"), ("3323068417", "198.18.0.1")):
            with self.subTest(host=host, address=address), \
                    patch.object(core.socket, "getaddrinfo", return_value=[self.answer(address)]), \
                    patch.object(core.socket, "socket", side_effect=AssertionError("TCP forbidden")):
                with self.assertRaises(core.RpcError) as failure:
                    core._FixedHTTPSConnection(host, 8443, network_policy=self.managed_policy()).connect()
                self.assertEqual(failure.exception.kind, "permission")
        with patch.object(core.socket, "getaddrinfo", return_value=[self.answer("198.18.0.1")]), \
                patch.object(core.socket, "socket", side_effect=AssertionError("TCP forbidden")):
            with self.assertRaises(core.RpcError):
                core._FixedHTTPSConnection("rpc.example", 8443).connect()

    def test_mixed_or_malformed_dns_answers_are_rejected_before_any_connect(self):
        invalid = [self.answer("198.18.0.2"), self.answer("198.18.0.1", 443), None, (),
                   (socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP, "", ("198.18.0.1", 8443)),
                   (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (b"198.18.0.1", 8443)),
                   (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("198.18.0.1", 8443, 0, 0)),
                   (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("198.18.0.1", 8443, 0, 0)),
                   (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("2606:4700::1111%lo0", 8443, 0, 0))]
        for answer in invalid:
            with self.subTest(answer=answer), \
                    patch.object(core.socket, "getaddrinfo", return_value=[self.answer("198.18.0.1"), answer]), \
                    patch.object(core.socket, "socket", side_effect=AssertionError("TCP forbidden")):
                with self.assertRaises(core.RpcError) as failure:
                    core._FixedHTTPSConnection("rpc.example", 8443, network_policy=self.managed_policy()).connect()
                self.assertEqual(failure.exception.kind, "permission")

    def test_managed_route_still_requires_tls_identity_and_fixed_publisher(self):
        for cls, host, port in ((core._FixedHTTPSConnection, "rpc.example", 8443),
                                (methodology._PublisherHTTPSConnection, methodology.HOST, 443)):
            for mutation in ("tls", "host", "tunnel"):
                with self.subTest(host=host, mutation=mutation):
                    context = ssl.create_default_context()
                    connection = cls(host, port, context=context, network_policy=self.managed_policy())
                    if mutation == "tls":
                        context.check_hostname = False
                    elif mutation == "host":
                        connection.host = "other.example"
                    else:
                        connection.set_tunnel("other.example", 443)
                    with patch.object(core.socket, "getaddrinfo", side_effect=AssertionError("DNS forbidden")):
                        with self.assertRaises(core.RpcError) as failure:
                            connection.connect()
                    self.assertEqual(failure.exception.kind, "permission")

    def test_all_dns_answers_must_be_public_before_socket_creation(self):
        addresses = ("127.0.0.1", "10.0.0.1", "169.254.169.254", "0.0.0.0", "224.0.0.1",
                     "::1", "fe80::1", "fc00::1", "::ffff:8.8.8.8", "192.0.2.1")
        for address in addresses:
            with self.subTest(address=address), \
                 patch.object(core.socket, "getaddrinfo", return_value=[self.answer("8.8.8.8"), self.answer(address)]), \
                 patch.object(core.socket, "socket", side_effect=AssertionError("TCP forbidden")):
                with self.assertRaises(core.RpcError) as failure:
                    core._FixedHTTPSConnection("rpc.example", 8443).connect()
                self.assertEqual(failure.exception.kind, "permission")

    def test_single_dns_resolution_numeric_connect_and_matching_tls_sni(self):
        context = ssl.create_default_context()
        sock, wrapped = Mock(), Mock()
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:8080"}), \
             patch.object(core.socket, "getaddrinfo", return_value=[self.answer("8.8.8.8")]) as lookup, \
             patch.object(core.socket, "socket", return_value=sock), \
             patch.object(context, "wrap_socket", return_value=wrapped) as tls:
            connection = core._FixedHTTPSConnection("rpc.example", 8443, timeout=5, context=context)
            connection.connect()
            lookup.assert_called_once_with("rpc.example", 8443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
            sock.connect.assert_called_once_with(("8.8.8.8", 8443))
            sock.settimeout.assert_called_once_with(5)
            tls.assert_called_once_with(sock, server_hostname="rpc.example")
            self.assertIs(connection.sock, wrapped)
            connection.close()

    def test_tunnel_destination_mutation_and_disabled_tls_are_refused(self):
        for mode in ("tunnel", "host", "port", "tls"):
            with self.subTest(mode=mode):
                context = ssl.create_default_context()
                connection = core._FixedHTTPSConnection("rpc.example", 8443, context=context)
                if mode == "tunnel":
                    connection.set_tunnel("other.example", 443)
                elif mode == "host":
                    connection.host = "other.example"
                elif mode == "port":
                    connection.port = 443
                else:
                    context.check_hostname = False
                with patch.object(core.socket, "getaddrinfo", side_effect=AssertionError("DNS forbidden")):
                    with self.assertRaises(core.RpcError) as failure:
                        connection.connect()
                self.assertEqual(failure.exception.kind, "permission")


if __name__ == "__main__":
    unittest.main()

"""Publisher source recognition and hostile-input boundaries; no live network."""
from copy import deepcopy
import io
from pathlib import Path
import socket
import ssl
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from netstack_core import RpcError, StopRun, load_json
import netstack_methodology as methodology

HTML = b'<html><script type="module" crossorigin src="/assets/current.js"></script></html>'
# Synthetic reviewed source exercises the trust boundary, not JS execution.
REGISTRY = b'{alpha:{tokenId:"41",status:"HUMAN-VERIFIED",source:"synthetic"}}'
SELECTOR = (b';function uM(){return Object.values(lM).filter(t=>t.status==="HUMAN-VERIFIED")'
            b'.map(t=>BigInt(t.tokenId))}')
BUNDLE = (b'const unrelated={tokenId:"999"},lM=' + REGISTRY + SELECTOR
          + b'function positions(){return uM()}function principal(p){return p.amount*p.mark}'
          b'function report(core,v4){return core+v4};')


def registry_entry(key, token_id, status="HUMAN-VERIFIED"):
    return ('%s:{tokenId:"%s",status:"%s",source:"synthetic"}' % (key, token_id, status)).encode()


class Response:
    def __init__(self, body, content_type, status=200, headers=None):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body)), **(headers or {})}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, size):
        return self.body.read(size)


class PublisherBoundaries(unittest.TestCase):
    def context(self):
        def stop(reason):
            raise StopRun(reason)
        return SimpleNamespace(result={"metrics": {}}, _collect_end=time.monotonic()+30,
                               _attempt_end=None, _raw_bytes=0, _arm=lambda: None,
                               check=lambda: None, _stop=stop)

    def profile(self):
        profile = deepcopy(load_json("assets/analytics/reports-methodology.json"))
        profile["entry_shell_sha256"] = methodology._digest(HTML.replace(b"/assets/current.js", b"<ENTRY_BUNDLE>"))
        digest = methodology._digest(BUNDLE)
        registry = {"registry_binding": "lM", "selector_binding": "uM"}
        profile["reviewed_bundles"] = [{"bundle_sha256": digest,
                                       "executable_sha256": methodology._registry_observation(BUNDLE, registry)[1],
                                       "registry_extraction": registry,
                                       "evidence": [{"id": "test_review", "source_sha256": digest,
                                                     "excerpt": "function report(core,v4){return core+v4}"}]}]
        return profile

    def collect(self, bundle=BUNDLE, html=HTML, first_response=None, profile=None, bundle_response=None):
        responses = [first_response or Response(html, "text/html"),
                     bundle_response or Response(bundle, "application/javascript")]
        ctx = self.context()
        with patch.object(methodology, "load_json", return_value=profile or self.profile()), \
                patch.object(methodology, "_PublisherHTTPSConnection") as connection:
            connection.return_value.getresponse.side_effect = responses
            try:
                result = methodology.collect_reports_methodology(ctx)
            except RpcError as exc:
                self.assertIn(exc.kind, ("permission", "integrity"))
                result = ctx.result["metrics"]["reports_methodology"]
            return result, connection.call_count

    def test_supported_current_observation_has_provenance_but_no_headline(self):
        result, calls = self.collect()
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["fetched_this_run"])
        self.assertTrue(result["v4_principal_included"])
        self.assertFalse(result["v4_fees_included"])
        self.assertEqual(result["v4_position_scope"]["token_ids"], ["41"])
        provenance = result["v4_position_scope"]["selection_provenance"]
        self.assertEqual(provenance["source_sha256"], methodology._digest(BUNDLE))
        self.assertEqual(provenance["registry_sha256"], methodology._digest(REGISTRY))
        self.assertEqual((provenance["entry_count"], provenance["selected_count"]), (1, 1))
        self.assertEqual([row["sha256"] for row in result["sources"]],
                         [methodology._digest(HTML), methodology._digest(BUNDLE)])
        self.assertEqual(result["headline_comparison"]["status"], "unavailable")
        self.assertIsNone(result["headline_comparison"]["website_value_usd"])
        self.assertEqual(calls, 2)

    def test_later_runs_never_reuse_an_earlier_verified_observation(self):
        first, _ = self.collect()
        self.assertEqual(first["status"], "verified")
        changed, _ = self.collect(bundle=BUNDLE.replace(b"return core+v4", b"return core-v4"))
        self.assertEqual(changed["status"], "unsupported")
        self.assertIsNone(changed["v4_principal_included"])
        unavailable, _ = self.collect(first_response=Response(b"", "text/html", status=503))
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertFalse(unavailable["fetched_this_run"])
        self.assertEqual(unavailable["sources"], [])
        self.assertIsNone(unavailable["v4_principal_included"])
        failed_bundle, _ = self.collect(bundle_response=Response(b"", "application/javascript", status=503))
        self.assertEqual(failed_bundle["status"], "unavailable")
        self.assertIsNone(failed_bundle["v4_position_scope"])
        self.assertEqual([row["role"] for row in failed_bundle["sources"]], ["entry_html"])

    def test_changed_aggregate_principal_selector_or_reader_is_not_certified(self):
        for bundle in (BUNDLE.replace(b"return core+v4", b"return core-v4"),
                       BUNDLE.replace(b"p.amount*p.mark", b"p.fees*p.mark"),
                       BUNDLE.replace(b'Object.values(lM)', b'Object.values(unrelated)'),
                       BUNDLE.replace(b'return uM()', b'return [999n]'),
                       BUNDLE.replace(b'status==="HUMAN-VERIFIED"', b'status!=="HUMAN-VERIFIED"'),
                       b'const visible="True RFV V4 principal";',
                       BUNDLE+b';import("./unreviewed.js");'):
            with self.subTest(bundle=bundle):
                result, _ = self.collect(bundle=bundle)
                self.assertEqual(result["status"], "unsupported")
                self.assertIsNone(result["v4_principal_included"])
                self.assertEqual(result["evidence"], [])

    def test_registry_replacement_growth_shrink_and_empty_are_fresh_data(self):
        for entries, expected in (
                ([registry_entry("replacement", "72")], ["72"]),
                ([registry_entry("second", "73"), registry_entry("first", "41")], ["73", "41"]),
                ([registry_entry("one", "0"), registry_entry("two", str((1 << 256) - 1))],
                 ["0", str((1 << 256) - 1)]),
                ([registry_entry("unreviewed", "84", "PLACEHOLDER")], []),
                ([], [])):
            literal = b"{" + b",".join(entries) + b"}"
            changed = BUNDLE.replace(REGISTRY, literal)
            with self.subTest(expected=expected):
                result, _ = self.collect(bundle=changed)
                self.assertEqual(result["status"], "verified")
                scope = result["v4_position_scope"]
                self.assertEqual(scope["token_ids"], expected)
                self.assertEqual(scope["selection_provenance"]["entry_count"], len(entries))
                self.assertEqual(scope["selection_provenance"]["empty_selection_proved"], not expected)
                self.assertEqual(scope["selection_provenance"]["source_sha256"], methodology._digest(changed))
                self.assertEqual(result["recognition"], "reviewed_registry_data_fingerprint")

    def test_malformed_duplicate_or_executable_registry_fails_closed(self):
        invalid = [
            b"{"+registry_entry("one", value)+b"}"
            for value in ("", "-1", "+1", "01", "1.0", "1e2", "0x10", str(1 << 256))
        ]
        invalid.extend([
            b"{"+registry_entry("one", "41")+b","+registry_entry("two", "41")+b"}",
            b"{"+registry_entry("one", "41")+b","+registry_entry("one", "42")+b"}",
            b"{"+registry_entry("__proto__", "41")+b"}",
            REGISTRY.replace(b'"41"', b"41n"),
            REGISTRY.replace(b'"41"', b'getPositionId()'),
            REGISTRY.replace(b'"synthetic"', b'fetchSource()'),
            REGISTRY.replace(b'"synthetic"', b'"synthetic",extra:run()'),
            REGISTRY.replace(b'"synthetic"', b'"unterminated'),
            REGISTRY[:-1]+b",}",
            b"Object.assign({}, "+REGISTRY+b")",
        ])
        for literal in invalid:
            with self.subTest(literal=literal):
                result, _ = self.collect(bundle=BUNDLE.replace(REGISTRY, literal))
                self.assertEqual(result["status"], "unsupported")
                self.assertIsNone(result["v4_position_scope"])

    def test_registry_ambiguity_and_limits_do_not_imply_empty_selection(self):
        too_many = b"{" + b",".join(registry_entry("item"+str(i), str(i))
                                     for i in range(methodology.MAX_REGISTRY_ENTRIES+1)) + b"}"
        for changed in (
                BUNDLE.replace(REGISTRY, too_many),
                BUNDLE.replace(REGISTRY, b"{"+b" "*methodology.MAX_REGISTRY_BYTES+b"}"),
                BUNDLE.replace(b'"synthetic"', b'"'+b"x"*8193+b'"'),
                BUNDLE+b",lM={}",
                BUNDLE+SELECTOR,
                BUNDLE.replace(b",lM=", b",other="),
                BUNDLE.replace(REGISTRY, b"null")):
            result, _ = self.collect(bundle=changed)
            self.assertEqual(result["status"], "unsupported")
            self.assertIsNone(result["v4_position_scope"])

    def test_dated_bundle_evidence_is_not_current_recognition(self):
        historical = BUNDLE.replace(b"return core+v4", b"return core")
        profile = self.profile()
        profile["historical_reviewed_bundles"] = [{
            "bundle_sha256": methodology._digest(historical),
            "executable_sha256": methodology._registry_observation(
                historical, profile["reviewed_bundles"][0]["registry_extraction"])[1],
        }]
        result, _ = self.collect(bundle=historical, profile=profile)
        self.assertEqual(result["status"], "unsupported")
        self.assertIsNone(result["v4_position_scope"])

    def test_packaged_id_list_cannot_override_fresh_selection(self):
        profile = self.profile()
        profile["v4_position_scope"]["token_ids"] = ["72"]
        result, calls = self.collect(profile=profile)
        self.assertEqual(result["status"], "unsupported")
        self.assertIsNone(result["v4_position_scope"])
        self.assertEqual(calls, 0)

    def test_extra_inline_scripts_and_unreviewed_entry_envelope_fail_closed(self):
        for addition in (b'<script>changeAccounting()</script>',
                         b'<script type="module" src="/assets/another.js"></script>',
                         b'<base href="https://example.com/">',
                         b'<img src="x" onerror="changeAccounting()">'):
            result, calls = self.collect(html=HTML.replace(b"</html>", addition+b"</html>"))
            self.assertEqual(result["status"], "unsupported")
            self.assertIsNone(result["v4_principal_included"])
            self.assertEqual(calls, 1)

    def test_hostile_script_destinations_never_receive_a_request(self):
        for src in (b'https://evil.example/assets/current.js', b'//127.0.0.1/a.js',
                    b'https://app.netnet.capital@evil.example/a.js', b'/assets/%2e%2e/a.js',
                    b'/assets/current.js?credential=secret', b'data:text/javascript,run()',
                    b'/assets/current.js#fragment'):
            result, calls = self.collect(html=HTML.replace(b'/assets/current.js', src))
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["error"]["kind"], "permission")
            self.assertEqual(calls, 1)
            self.assertNotIn("credential", str(result))

    def test_redirect_access_denial_compression_and_size_do_not_certify(self):
        cases = [Response(b"", "text/html", status=302, headers={"Location": "http://127.0.0.1/"}),
                 Response(b"", "text/html", status=403),
                 Response(HTML, "text/html", headers={"Content-Encoding": "gzip"}),
                 Response(HTML, "text/html", headers={"Content-Length": str(methodology.MAX_HTML_BYTES+1)}),
                 Response(HTML, "application/json")]
        for response in cases:
            result, calls = self.collect(first_response=response)
            self.assertEqual(result["status"], "unavailable")
            self.assertFalse(result["fetched_this_run"])
            self.assertIsNone(result["v4_principal_included"])
            self.assertEqual(calls, 1)

    def test_dns_rejects_any_nonpublic_answer_before_socket_creation(self):
        for address in ("127.0.0.1", "169.254.169.254", "10.0.0.1", "224.0.0.1", "::1", "::ffff:8.8.8.8"):
            answers = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443)),
                       (socket.AF_INET6 if ":" in address else socket.AF_INET,
                        socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]
            connection = methodology._PublisherHTTPSConnection(methodology.HOST, 443,
                                                                context=ssl.create_default_context())
            with patch.object(methodology.socket, "getaddrinfo", return_value=answers), \
                    patch.object(methodology.socket, "socket") as create_socket:
                with self.assertRaises(RpcError) as error:
                    connection.connect()
                self.assertEqual(error.exception.kind, "permission")
                create_socket.assert_not_called()

    def test_tls_failure_never_retries_or_disables_verification(self):
        ctx = self.context()
        with patch.object(methodology, "_PublisherHTTPSConnection") as connection:
            connection.return_value.request.side_effect = ssl.SSLCertVerificationError("untrusted")
            with self.assertRaises(RpcError) as error:
                methodology.collect_reports_methodology(ctx)
            self.assertEqual(error.exception.kind, "permission")
            result = ctx.result["metrics"]["reports_methodology"]
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["error"]["kind"], "permission")
            self.assertEqual(connection.call_count, 1)
            self.assertEqual(connection.call_args.kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(connection.call_args.kwargs["context"].check_hostname)

    def test_integrity_failure_propagates_with_unavailable_evidence(self):
        ctx = self.context()
        with patch.object(ctx, "check", side_effect=RpcError("Chain conflict", kind="integrity")), \
                patch.object(methodology, "_PublisherHTTPSConnection") as connection:
            with self.assertRaises(RpcError) as error:
                methodology.collect_reports_methodology(ctx)
        self.assertEqual(error.exception.kind, "integrity")
        self.assertEqual(ctx.result["metrics"]["reports_methodology"]["status"], "unavailable")
        self.assertIsNone(ctx.result["metrics"]["reports_methodology"]["v4_principal_included"])
        connection.assert_not_called()

    def test_interruption_retains_entry_evidence_without_certifying(self):
        ctx = self.context()
        with patch.object(methodology, "load_json", return_value=self.profile()), \
                patch.object(methodology, "_PublisherHTTPSConnection") as connection:
            connection.return_value.getresponse.side_effect = [Response(HTML, "text/html"), StopRun("deadline_exhausted")]
            with self.assertRaises(StopRun):
                methodology.collect_reports_methodology(ctx)
        result = ctx.result["metrics"]["reports_methodology"]
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["sources"][0]["sha256"], methodology._digest(HTML))
        self.assertIsNone(result["v4_principal_included"])
        self.assertIsNone(ctx._attempt_end)

    def test_malformed_trusted_evidence_cannot_spoof_inclusion(self):
        for key, value in (("v4_principal_included", "true"), ("v4_fees_included", 0)):
            profile = self.profile()
            profile[key] = value
            result, calls = self.collect(profile=profile)
            self.assertEqual(result["status"], "unsupported")
            self.assertIsNone(result["v4_principal_included"])
            self.assertEqual(calls, 0)
        profile = self.profile()
        profile["reviewed_bundles"][0]["evidence"][0]["source_sha256"] = "0"*64
        result, calls = self.collect(profile=profile)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()

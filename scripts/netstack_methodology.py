"""Read-only recognition of reviewed publisher accounting; never execute fetched code."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import http.client
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit

from netstack_core import MAX_TOTAL_BYTES, RpcError, StopRun, load_json

HOST = "app.netnet.capital"
ENTRY_URL = "https://" + HOST + "/"
PROFILE_ID = "reports-20260926-dynamic-v4-registry"
MAX_HTML_BYTES = 128 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_REQUESTS = 2
MAX_SECONDS = 15.0
_ASSET_PATH = re.compile(r"/assets/[A-Za-z0-9_-]+\.js\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_REGISTRY_BYTES = 64 * 1024
MAX_REGISTRY_ENTRIES = 128
_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]{0,63}\Z")
# This is the reviewed registry's literal object grammar, not a JS evaluator.
# Only these data fields can vary; the selector and every byte outside the
# object stay bound to the reviewed complete-bundle fingerprint.
_REGISTRY_ENTRY = re.compile(
    rb'([A-Za-z_$][A-Za-z0-9_$]{0,127}):\{tokenId:"(0|[1-9][0-9]{0,77})",'
    rb'status:"([A-Z][A-Z0-9_-]{0,63})",source:"'
    rb'(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9A-Fa-f]{4})){0,8192}"\}')


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _registry_observation(raw, descriptor):
    """Extract only the literal registry consumed by the reviewed Reports path.

    A matching whole-bundle fingerprint proves this binding is still the one
    consumed by Reports. Parsing alone is never sufficient for recognition.
    """
    binding = descriptor["registry_binding"].encode("ascii")
    selector = descriptor["selector_binding"].encode("ascii")
    prefix = b"," + binding + b"="
    suffix = (b";function " + selector + b"(){return Object.values(" + binding
              + b').filter(t=>t.status==="HUMAN-VERIFIED").map(t=>BigInt(t.tokenId))}')
    if len(raw) > MAX_BUNDLE_BYTES or raw.count(prefix) != 1 or raw.count(suffix) != 1:
        raise RpcError("Publisher V4 registry binding is ambiguous or unsupported", kind="unsupported")
    start = raw.index(prefix) + len(prefix)
    end = raw.index(suffix)
    literal = raw[start:end]
    if (not 2 <= len(literal) <= MAX_REGISTRY_BYTES
            or not literal.startswith(b"{") or not literal.endswith(b"}")):
        raise RpcError("Publisher V4 registry literal is unsupported", kind="unsupported")
    try:
        literal.decode("utf-8")
    except UnicodeError as exc:
        raise RpcError("Publisher V4 registry is not UTF-8", kind="unsupported") from exc
    rows = literal[1:-1]
    position, count = 0, 0
    keys, ids, selected = set(), set(), []
    while position < len(rows):
        match = _REGISTRY_ENTRY.match(rows, position)
        if match is None or count >= MAX_REGISTRY_ENTRIES:
            raise RpcError("Publisher V4 registry entries are unsupported or exceed limits", kind="unsupported")
        key, token_id, status = match.groups()
        if key == b"__proto__" or key in keys or token_id in ids or int(token_id) >= 1 << 256:
            raise RpcError("Publisher V4 registry contains duplicate or invalid identities", kind="unsupported")
        keys.add(key)
        ids.add(token_id)
        count += 1
        if status == b"HUMAN-VERIFIED":
            selected.append(token_id.decode("ascii"))
        position = match.end()
        if position < len(rows):
            if rows[position:position + 1] != b"," or position + 1 == len(rows):
                raise RpcError("Publisher V4 registry separator is unsupported", kind="unsupported")
            position += 1
    fingerprint = _digest(raw[:start] + b"<REPORTS_V4_REGISTRY>" + raw[end:])
    provenance = {"method": "reviewed_reports_v4_registry_v1",
                  "registry_binding": descriptor["registry_binding"],
                  "selector_binding": descriptor["selector_binding"],
                  "source_sha256": _digest(raw), "registry_sha256": _digest(literal),
                  "byte_offset": start, "byte_length": len(literal),
                  "entry_count": count, "selected_count": len(selected),
                  "empty_selection_proved": not selected}
    return selected, fingerprint, provenance


def _destination(url):
    try:
        parts = urlsplit(url)
        allowed = (parts.scheme == "https" and parts.netloc == HOST
                   and parts.hostname == HOST and parts.port is None
                   and not parts.query and not parts.fragment
                   and (parts.path == "/" or _ASSET_PATH.fullmatch(parts.path)))
    except (ValueError, TypeError):
        allowed = False
    if not allowed:
        raise RpcError("Publisher destination is not allowlisted", kind="permission")
    return parts.path


class _PublisherHTTPSConnection(http.client.HTTPSConnection):
    """The core RPC transport's resolve-once/public-IP/TLS policy, fixed to publisher."""
    def connect(self):
        if self.host != HOST or self.port != 443 or self._tunnel_host:
            raise RpcError("Publisher destination or tunnel refused", kind="permission")
        answers = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        if not answers or len(answers) > 16:
            raise RpcError("Publisher DNS answer count is invalid", kind="permission")
        for family, socktype, protocol, canonical, destination in answers:
            try:
                address = ipaddress.ip_address(destination[0])
            except ValueError as exc:
                raise RpcError("Publisher DNS returned a malformed address", kind="permission") from exc
            if (family not in (socket.AF_INET, socket.AF_INET6) or not address.is_global
                    or address.is_multicast or address.is_reserved or address.is_unspecified
                    or address.is_loopback or address.is_link_local or address.is_private
                    or getattr(address, "ipv4_mapped", None) is not None):
                raise RpcError("Publisher DNS resolved to a nonpublic destination", kind="permission")
        family, socktype, protocol, canonical, destination = answers[0]
        sock = socket.socket(family, socktype, protocol)
        try:
            sock.settimeout(self.timeout)
            sock.connect(destination)
            self.sock = self._context.wrap_socket(sock, server_hostname=HOST)
        except BaseException:
            sock.close()
            raise


def _fetch(ctx, url, cap, role, result, end):
    path = _destination(url)
    ctx.check()
    usage = result["usage"]
    if usage["requests"] >= MAX_REQUESTS:
        raise RpcError("Publisher request cap reached", kind="limit")
    remaining = min(end, ctx._collect_end) - time.monotonic()
    if remaining <= 0:
        raise RpcError("Publisher collection time cap reached", kind="timeout")
    usage["requests"] += 1
    previous_attempt = ctx._attempt_end
    ctx._attempt_end = min(end, ctx._collect_end)
    ctx._arm()
    connection = None
    try:
        connection = _PublisherHTTPSConnection(HOST, 443, timeout=remaining, context=ssl.create_default_context())
        connection.request("GET", path, headers={"Accept-Encoding": "identity", "Cache-Control": "no-cache",
                                                "User-Agent": "netstack-analytics/1"})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise RpcError("Publisher redirect refused", kind="permission")
        if response.status in (401, 403, 407):
            raise RpcError("Publisher access denied; no alternate source attempted", kind="permission")
        if response.status != 200:
            raise RpcError("Publisher HTTP status " + str(response.status), kind="http")
        if response.getheader("Content-Encoding", "identity").lower() not in ("", "identity"):
            raise RpcError("Compressed publisher responses are not accepted", kind="protocol")
        expected = ("text/html",) if role == "entry_html" else ("application/javascript", "text/javascript")
        if response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() not in expected:
            raise RpcError("Unexpected publisher source content type", kind="protocol")
        length = response.getheader("Content-Length")
        if length is not None and (not length.isdigit() or len(length) > 10 or int(length) > cap):
            raise RpcError("Publisher response exceeds source byte cap", kind="size")
        chunks, size = [], 0
        while True:
            ctx.check()
            chunk = response.read(min(65536, cap + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            usage["bytes_received"] += len(chunk)
            ctx._raw_bytes += len(chunk)
            if ctx._raw_bytes > MAX_TOTAL_BYTES:
                ctx._stop("response_byte_limit")
            if size > cap:
                raise RpcError("Publisher response exceeds source byte cap", kind="size")
            chunks.append(chunk)
        if length is not None and size != int(length):
            raise RpcError("Publisher source body is incomplete", kind="protocol")
        raw = b"".join(chunks)
        result["sources"].append({"role": role, "url": url, "sha256": _digest(raw),
                                  "bytes": size, "fetched_at": _now()})
        return raw
    except (PermissionError, ssl.SSLCertVerificationError) as exc:
        raise RpcError("Publisher transport permission or TLS verification denied", kind="permission") from exc
    except (socket.timeout, TimeoutError) as exc:
        raise RpcError("Publisher transport timeout", kind="timeout") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise RpcError("Publisher transport unavailable", kind="transport") from exc
    finally:
        if connection is not None:
            connection.close()
        ctx._attempt_end = previous_attempt
        ctx._arm()


class _EntryScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts = []
        self.has_base = False

    def handle_starttag(self, tag, attrs):
        if tag == "base":
            self.has_base = True
        if tag == "script":
            self.scripts.append(attrs)


def _entry_bundle(raw, expected_shell):
    try:
        parser = _EntryScripts()
        parser.feed(raw.decode("utf-8"))
        parser.close()
    except (UnicodeError, ValueError) as exc:
        raise RpcError("Publisher entry is not supported UTF-8 HTML", kind="unsupported") from exc
    if parser.has_base or len(parser.scripts) != 1:
        raise RpcError("Publisher executable entry structure changed", kind="unsupported")
    attrs = parser.scripts[0]
    fields = dict(attrs)
    if (len(fields) != len(attrs) or fields.get("type") != "module"
            or not isinstance(fields.get("src"), str)):
        raise RpcError("Publisher module entry is unsupported", kind="unsupported")
    src = fields["src"]
    # Check raw spelling too: urljoin must not silently accept whitespace,
    # credentials, fragments, escaped paths or a foreign origin.
    if not _ASSET_PATH.fullmatch(src):
        raise RpcError("Publisher script destination is not allowlisted", kind="permission")
    url = urljoin(ENTRY_URL, src)
    _destination(url)
    encoded_src = src.encode("ascii")
    if raw.count(encoded_src) != 1 or _digest(raw.replace(encoded_src, b"<ENTRY_BUNDLE>")) != expected_shell:
        raise RpcError("Publisher HTML execution envelope is unreviewed", kind="unsupported")
    return url


def _reviewed_profile():
    profile = load_json("assets/analytics/reports-methodology.json")
    if (profile.get("schema_version") != 2 or profile.get("profile_id") != PROFILE_ID
            or profile.get("source_id") != "netnet-reports-methodology-20260926-current"
            or profile.get("entry_url") != ENTRY_URL or profile.get("v4_principal_included") is not True
            or profile.get("v4_fees_included") is not False
            or profile.get("normalization") != "reviewed_reports_v4_registry_v1"):
        raise RpcError("Packaged publisher methodology profile is invalid", kind="package")
    digest = profile.get("entry_shell_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise RpcError("Packaged publisher HTML fingerprint is invalid", kind="package")
    bundles = profile.get("reviewed_bundles")
    if not isinstance(bundles, list) or not 1 <= len(bundles) <= 8:
        raise RpcError("Packaged publisher bundle profiles are invalid", kind="package")
    for bundle in bundles:
        if not isinstance(bundle, dict):
            raise RpcError("Packaged publisher bundle profile is invalid", kind="package")
        for name in ("bundle_sha256", "executable_sha256"):
            if not isinstance(bundle.get(name), str) or not _SHA256.fullmatch(bundle[name]):
                raise RpcError("Packaged publisher fingerprint is invalid", kind="package")
        registry = bundle.get("registry_extraction")
        if (not isinstance(registry, dict)
                or any(not isinstance(registry.get(name), str)
                       or not _IDENTIFIER.fullmatch(registry[name])
                       for name in ("registry_binding", "selector_binding"))):
            raise RpcError("Packaged publisher registry extraction is invalid", kind="package")
        evidence = bundle.get("evidence")
        if (not isinstance(evidence, list) or not evidence
                or any(not isinstance(row, dict) or row.get("source_sha256") != bundle["bundle_sha256"]
                       or not isinstance(row.get("excerpt"), str) for row in evidence)):
            raise RpcError("Packaged publisher formula evidence is invalid", kind="package")
    if (not isinstance(profile.get("reviewed_at"), str)
            or not isinstance(profile.get("selection_policy"), dict)
            or not isinstance(profile.get("valuation_conventions"), dict)
            or not isinstance(profile.get("accounting_caveats"), list)):
        raise RpcError("Packaged publisher accounting metadata is invalid", kind="package")
    scope = profile.get("v4_position_scope")
    if (not isinstance(scope, dict) or scope.get("selection") != "publisher_registry_allowlist"
            or "token_ids" in scope or scope.get("hooks") != "zero_only"
            or scope.get("currencies") != ["wsNET", "hOHM", "USDG"]
            or scope.get("position_manager") != "0x58daec3116aae6d93017baaea7749052e8a04fa7"
            or scope.get("owner") != "0x498752d5fa0600cbd613074c151abe15b3fec7cb"):
        raise RpcError("Packaged publisher position scope is invalid", kind="package")
    return profile


def collect_reports_methodology(ctx):
    """Fetch this run's entry and bundle; attest only a fully supported calculation.

    This is a current HTTP-source observation, not a pinned-chain fact or a
    rendered-headline comparison. StopRun propagates with partial evidence left
    in metrics so callers can retain already collected RPC results.
    """
    result = {"status": "unavailable", "fetched_this_run": False, "checked_at": _now(),
              "reviewed_at": None, "profile_id": None, "recognition": None,
              "v4_principal_included": None, "v4_fees_included": None, "v4_position_scope": None,
              "sources": [], "evidence": [], "limits": {
                  "max_requests": MAX_REQUESTS, "max_html_bytes": MAX_HTML_BYTES,
                  "max_bundle_bytes": MAX_BUNDLE_BYTES, "max_seconds": MAX_SECONDS,
                  "max_registry_bytes": MAX_REGISTRY_BYTES, "max_registry_entries": MAX_REGISTRY_ENTRIES,
                  "redirects": False, "browser_or_javascript_execution": False,
                  "numerical_website_inputs": False,
                  "recognition_scope": "reviewed complete bundle with bounded Reports registry data extraction",
                  "current_source_not_pinned_chain_fact": True,
                  "not_independent_contract_audit": True},
              "usage": {"requests": 0, "bytes_received": 0},
              "headline_comparison": {"status": "unavailable", "website_value_usd": None,
                                      "reason": "client_rendered_no_reviewed_static_headline"}}
    ctx.result["metrics"]["reports_methodology"] = result
    end = time.monotonic() + MAX_SECONDS
    try:
        ctx.check()
        profile = _reviewed_profile()
        html = _fetch(ctx, ENTRY_URL, MAX_HTML_BYTES, "entry_html", result, end)
        bundle_url = _entry_bundle(html, profile["entry_shell_sha256"])
        bundle = _fetch(ctx, bundle_url, MAX_BUNDLE_BYTES, "entry_bundle", result, end)
        result["fetched_this_run"] = True
        actual = _digest(bundle)
        matched = None
        for reviewed in profile["reviewed_bundles"]:
            try:
                token_ids, fingerprint, selection_provenance = _registry_observation(
                    bundle, reviewed["registry_extraction"])
            except RpcError:
                continue
            if actual == reviewed["bundle_sha256"] or fingerprint == reviewed["executable_sha256"]:
                matched = reviewed
                break
        if matched is None:
            raise RpcError("Current publisher calculation or V4 registry is not recognized; static review is required",
                           kind="unsupported")
        recognition = ("reviewed_bundle_sha256" if actual == matched["bundle_sha256"]
                       else "reviewed_registry_data_fingerprint")
        selection_provenance["source_url"] = bundle_url
        scope = {**profile["v4_position_scope"], "token_ids": token_ids,
                 "selection_provenance": selection_provenance}
        ctx.check()
        result.update(status="verified", reviewed_at=profile["reviewed_at"], profile_id=PROFILE_ID,
                      recognition=recognition, v4_principal_included=True, v4_fees_included=False,
                      v4_position_scope=scope, evidence=matched["evidence"],
                      source_id=profile["source_id"], selection_policy=profile["selection_policy"],
                      valuation_conventions=profile["valuation_conventions"],
                      accounting_caveats=profile["accounting_caveats"])
    except StopRun as exc:
        result["error"] = {"kind": "stopped", "message": exc.reason}
        raise
    except RpcError as exc:
        result["status"] = "unsupported" if exc.kind in ("unsupported", "package") else "unavailable"
        result["error"] = {"kind": exc.kind, "message": str(exc)}
        if exc.kind in ("permission", "integrity"):
            raise
    return result

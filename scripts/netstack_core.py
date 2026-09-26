"""Bounded, read-only analytics primitives. Python 3.10+, POSIX, stdlib only."""
from __future__ import annotations

import errno
import ipaddress
import http.client
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import ssl
import stat
import secrets
import time
from fractions import Fraction
from email.utils import parsedate_to_datetime

ROOT = Path(__file__).resolve().parents[1]
ZERO = "0x" + "0" * 40
RPC_HOST = "rpc.mainnet.chain.robinhood.com"
CHAIN_ID = 4663
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_ABI_BYTES = 65536
MAX_PAGE_ROWS = 2000
SERIALIZATION_RESERVE = 2.0
MAX_LOG_BLOCKS = 100000
MAX_RECOVERY_WAIT = 30.0
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
_HEX = re.compile(r"0x(?:[0-9a-fA-F]{2})*\Z")
_QUANTITY = re.compile(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)\Z")
_MASK64 = (1 << 64) - 1
_ROTATIONS = (0, 1, 62, 28, 27, 36, 44, 6, 55, 20, 3, 10, 43, 25, 39, 41, 45, 15, 21, 8, 18, 2, 61, 56, 14)
_ROUND_CONSTANTS = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)


class StopRun(Exception):
    def __init__(self, reason):
        self.reason = str(reason)
        super().__init__(self.reason)


class RpcError(Exception):
    """A sanitized failure; provider messages and credential-bearing URLs are excluded."""
    def __init__(self, message, *, kind="protocol", retryable=False, splittable=False, retry_after=None):
        self.kind = kind
        self.retryable = retryable
        self.splittable = splittable
        self.retry_after = retry_after
        super().__init__(message)


def _hex(value, size=None):
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise RpcError("Malformed hexadecimal data", kind="decode")
    if size is not None and len(value) != 2 + 2 * size:
        raise RpcError("Incorrect hexadecimal data length", kind="decode")
    return value.lower()


def _address(value):
    return _hex(value, 20)


def _quantity(value):
    if not isinstance(value, str) or len(value) > 66 or not _QUANTITY.fullmatch(value):
        raise RpcError("Malformed RPC quantity", kind="decode")
    return int(value, 16)


def _integer(value, label="integer"):
    if type(value) is not int or value < 0 or value >= 1 << 256:
        raise RpcError("Invalid " + label, kind="input")
    return value


def _json_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _invalid_constant(value):
    raise ValueError("nonfinite JSON number")


def _parse_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_json_pairs, parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RpcError("Invalid or ambiguous JSON response", kind="decode") from exc


def load_json(relative_path):
    if not isinstance(relative_path, (str, Path)):
        raise RpcError("Invalid package JSON path", kind="input")
    relative = Path(relative_path)
    if relative.is_absolute():
        raise RpcError("Package JSON path must be relative", kind="input")
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise RpcError("Package JSON path escapes root", kind="input")
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_RESPONSE_BYTES + 1)
    except OSError as exc:
        raise RpcError("Required package JSON is unavailable", kind="package") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RpcError("Package JSON exceeds size limit", kind="package")
    obj = _parse_json(raw)
    if not isinstance(obj, dict):
        raise RpcError("Package JSON must be an object", kind="package")
    return obj


def resolve_routes(workflow):
    if workflow not in ("liquidity", "predict", "reserves", "sleeve", "v4", "advance"):
        raise RpcError("Unknown canonical route set", kind="input")
    route = load_json("assets/analytics/" + workflow + "-routes.json")
    resolved = {"_route": route}
    documents = {}
    for key, pointer in route.items():
        if not isinstance(pointer, dict) or "file" not in pointer or "id" not in pointer:
            continue
        filename = pointer["file"]
        if filename not in documents:
            documents[filename] = load_json(filename)
        matches = [record for record in documents[filename].get("contracts", [])
                   if isinstance(record, dict) and record.get("id") == pointer["id"]]
        if len(matches) != 1 or matches[0].get("chain_id") != CHAIN_ID:
            raise RpcError("Canonical route is missing, ambiguous or on another chain", kind="package")
        resolved[key] = dict(matches[0], address=_address(matches[0].get("address")))
    return resolved


def amount(raw, decimals):
    if type(raw) is not int or type(decimals) is not int or not 0 <= decimals <= 255:
        raise RpcError("Invalid amount or decimal precision", kind="input")
    sign = "-" if raw < 0 else ""
    digits = str(abs(raw))
    if decimals == 0:
        return sign + digits
    digits = digits.rjust(decimals + 1, "0")
    return sign + digits[:-decimals] + "." + digits[-decimals:]


def ratio(value):
    if not isinstance(value, Fraction):
        raise RpcError("Ratio must be an exact Fraction", kind="input")
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def keccak256(data):
    """Ethereum Keccak-256 (legacy 0x01 suffix, not FIPS SHA3)."""
    if not isinstance(data, bytes) or len(data) > MAX_ABI_BYTES:
        raise RpcError("Keccak input exceeds limit", kind="input")
    rate = 136
    padded = bytearray(data)
    padded.append(1)
    padded.extend(b"\0" * ((-len(padded)) % rate))
    padded[-1] |= 0x80
    state = [0] * 25
    for offset in range(0, len(padded), rate):
        for lane in range(rate // 8):
            start = offset + lane * 8
            state[lane] ^= int.from_bytes(padded[start:start + 8], "little")
        for constant in _ROUND_CONSTANTS:
            columns = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
            delta = [columns[(x - 1) % 5] ^ ((columns[(x + 1) % 5] << 1 | columns[(x + 1) % 5] >> 63) & _MASK64) for x in range(5)]
            permuted = [0] * 25
            for y in range(5):
                for x in range(5):
                    index = x + 5 * y
                    value = state[index] ^ delta[x]
                    shift = _ROTATIONS[index]
                    permuted[y + 5 * ((2 * x + 3 * y) % 5)] = ((value << shift) | (value >> ((64 - shift) % 64))) & _MASK64
            for y in range(5):
                for x in range(5):
                    index = x + 5 * y
                    state[index] = permuted[index] ^ ((~permuted[(x + 1) % 5 + 5 * y]) & permuted[(x + 2) % 5 + 5 * y])
            state[0] ^= constant
    return b"".join(word.to_bytes(8, "little") for word in state[:4])


def _canonical_type(item, depth=0):
    if depth > 8 or not isinstance(item, dict) or not isinstance(item.get("type"), str):
        raise RpcError("Malformed ABI type", kind="abi")
    kind = item["type"]
    if kind.endswith("[]"):
        element = dict(item, type=kind[:-2])
        return _canonical_type(element, depth + 1) + "[]"
    if kind == "tuple":
        components = item.get("components")
        if not isinstance(components, list) or len(components) > 128:
            raise RpcError("Malformed ABI tuple", kind="abi")
        return "(" + ",".join(_canonical_type(part, depth + 1) for part in components) + ")"
    if kind in ("address", "bool", "string", "bytes") or re.fullmatch(r"bytes(?:[1-9]|[12][0-9]|3[0-2])", kind):
        return kind
    match = re.fullmatch(r"(uint|int)([0-9]*)", kind)
    if match and (not match[2] or int(match[2]) in range(8, 257, 8)):
        return match[1] + (match[2] or "256")
    raise RpcError("Unsupported ABI type", kind="abi")


def signature(item):
    if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item["name"]):
        raise RpcError("Malformed ABI name", kind="abi")
    inputs = item.get("inputs", [])
    if not isinstance(inputs, list) or len(inputs) > 128:
        raise RpcError("Malformed ABI inputs", kind="abi")
    return item["name"] + "(" + ",".join(_canonical_type(part) for part in inputs) + ")"


_TOPIC_CACHE = {}


def topic(item):
    sig = signature(item)
    if sig not in _TOPIC_CACHE:
        if len(_TOPIC_CACHE) >= 1024:
            raise RpcError("ABI topic cache limit reached", kind="abi")
        _TOPIC_CACHE[sig] = "0x" + keccak256(sig.encode("ascii")).hex()
    return _TOPIC_CACHE[sig]


def _dynamic(item):
    kind = _canonical_type(item)
    return kind.endswith("[]") or kind in ("string", "bytes") or (
        item["type"] == "tuple" and any(_dynamic(c) for c in item["components"]))


def _static_size(item):
    if _dynamic(item):
        return 32
    if item["type"] == "tuple":
        return sum(_static_size(c) for c in item["components"])
    return 32


def _named(items, values):
    names = [item.get("name") or str(index) for index, item in enumerate(items)]
    if len(set(names)) != len(names):
        raise RpcError("Ambiguous ABI field names", kind="abi")
    return dict(zip(names, values))


def _decode_static(item, data, offset):
    kind = _canonical_type(item)
    if item["type"] == "tuple":
        values, end = _decode_sequence(item["components"], data, offset)
        return _named(item["components"], values), end
    if offset + 32 > len(data):
        raise RpcError("Truncated ABI word", kind="decode")
    word = data[offset:offset + 32]
    value = int.from_bytes(word, "big")
    if kind.startswith("uint"):
        if value >= 1 << int(kind[4:]):
            raise RpcError("Noncanonical ABI unsigned integer", kind="decode")
        decoded = value
    elif kind.startswith("int"):
        width = int(kind[3:])
        decoded = value - (1 << 256) if value >> 255 else value
        if not -(1 << (width - 1)) <= decoded < 1 << (width - 1):
            raise RpcError("Noncanonical ABI signed integer", kind="decode")
    elif kind == "address":
        if value >= 1 << 160:
            raise RpcError("Noncanonical ABI address", kind="decode")
        decoded = "0x" + word[-20:].hex()
    elif kind == "bool":
        if value not in (0, 1):
            raise RpcError("Noncanonical ABI boolean", kind="decode")
        decoded = bool(value)
    elif kind.startswith("bytes") and kind != "bytes":
        length = int(kind[5:])
        if any(word[length:]):
            raise RpcError("Noncanonical ABI bytes padding", kind="decode")
        decoded = "0x" + word[:length].hex()
    else:
        raise RpcError("Unsupported static ABI value", kind="abi")
    return decoded, offset + 32


def _decode_dynamic(item, data, offset):
    if item["type"] == "tuple":
        values, end = _decode_sequence(item["components"], data, offset)
        return _named(item["components"], values), end
    if offset + 32 > len(data):
        raise RpcError("Truncated ABI length", kind="decode")
    length = int.from_bytes(data[offset:offset + 32], "big")
    if item["type"].endswith("[]"):
        if length > 128:
            raise RpcError("ABI array count exceeds limit", kind="decode")
        element = dict(item, type=item["type"][:-2])
        return _decode_sequence([element] * length, data, offset + 32)
    if length > 4096:
        raise RpcError("ABI metadata exceeds size limit", kind="decode")
    start = offset + 32
    end = start + ((length + 31) // 32) * 32
    if end > len(data) or any(data[start + length:end]):
        raise RpcError("Invalid ABI dynamic padding or length", kind="decode")
    raw = data[start:start + length]
    if item["type"] == "string":
        try:
            value = raw.decode("utf-8")
        except UnicodeError as exc:
            raise RpcError("Invalid ABI metadata UTF-8", kind="decode") from exc
    elif item["type"] == "bytes":
        value = "0x" + raw.hex()
    else:
        raise RpcError("Unsupported dynamic ABI value", kind="abi")
    return value, end


def _decode_sequence(items, data, start=0):
    if not isinstance(items, list) or len(items) > 128:
        raise RpcError("ABI field count exceeds limit", kind="abi")
    head_end = start + sum(_static_size(item) for item in items)
    if head_end > len(data):
        raise RpcError("Truncated ABI head", kind="decode")
    cursor, tail, values = start, head_end, []
    for item in items:
        if _dynamic(item):
            relative = int.from_bytes(data[cursor:cursor + 32], "big")
            if relative % 32 or start + relative != tail:
                raise RpcError("Noncanonical ABI dynamic offset", kind="decode")
            value, tail = _decode_dynamic(item, data, tail)
            cursor += 32
        else:
            value, cursor = _decode_static(item, data, cursor)
        values.append(value)
    return values, tail


def _decode_outputs(item, raw):
    raw = _hex(raw)
    if len(raw) > 2 + MAX_ABI_BYTES * 2:
        raise RpcError("ABI response exceeds limit", kind="decode")
    data = bytes.fromhex(raw[2:])
    outputs = item.get("outputs", [])
    values, end = _decode_sequence(outputs, data)
    if end != len(data):
        raise RpcError("Trailing ABI response bytes", kind="decode")
    if len(values) == 1:
        return values[0]
    return _named(outputs, values)


def _encode_value(item, value):
    kind = _canonical_type(item)
    if kind.endswith("[]"):
        raise RpcError("Array arguments are not supported", kind="input")
    if kind.startswith("bytes") and kind != "bytes":
        length = int(kind[5:])
        return bytes.fromhex(_hex(value, length)[2:]).ljust(32, b"\0")
    if kind.startswith("uint"):
        _integer(value, "ABI argument")
        if value >= 1 << int(kind[4:]):
            raise RpcError("ABI unsigned argument out of range", kind="input")
        return value.to_bytes(32, "big")
    if kind.startswith("int"):
        bits = int(kind[3:])
        if type(value) is not int or not -(1 << (bits - 1)) <= value < 1 << (bits - 1):
            raise RpcError("ABI signed argument out of range", kind="input")
        return (value % (1 << 256)).to_bytes(32, "big")
    if kind == "address":
        return bytes.fromhex(_address(value)[2:]).rjust(32, b"\0")
    if kind == "bool" and type(value) is bool:
        return int(value).to_bytes(32, "big")
    if item["type"] == "tuple" and not _dynamic(item):
        components = item["components"]
        if isinstance(value, dict):
            values = [value[c.get("name") or str(i)] for i, c in enumerate(components)]
        else:
            values = value
        if not isinstance(values, (list, tuple)) or len(values) != len(components):
            raise RpcError("Invalid tuple argument", kind="input")
        return b"".join(_encode_value(c, v) for c, v in zip(components, values))
    raise RpcError("Unsupported ABI argument", kind="input")


def _validated_log(log):
    if not isinstance(log, dict) or log.get("removed", False) is not False:
        raise RpcError("Removed or malformed event log", kind="integrity")
    topics = log.get("topics")
    if not isinstance(topics, list) or not 1 <= len(topics) <= 4:
        raise RpcError("Malformed event topics", kind="integrity")
    data = _hex(log.get("data"))
    if len(data) > 2 + MAX_ABI_BYTES * 2:
        raise RpcError("Event data exceeds ABI limit", kind="integrity")
    return {"address": _address(log.get("address")), "topics": [_hex(t, 32) for t in topics],
            "data": data, "blockNumber": _quantity(log.get("blockNumber")),
            "transactionIndex": _quantity(log.get("transactionIndex")), "logIndex": _quantity(log.get("logIndex")),
            "transactionHash": _hex(log.get("transactionHash"), 32), "blockHash": _hex(log.get("blockHash"), 32)}


def decode_event(log, abi):
    normalized = _validated_log(log)
    candidates = [item for item in abi if item.get("type") == "event" and not item.get("anonymous", False)
                  and topic(item) == normalized["topics"][0]]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise RpcError("Ambiguous event ABI", kind="abi")
    item = candidates[0]
    indexed = [part for part in item["inputs"] if part.get("indexed", False)]
    plain = [part for part in item["inputs"] if not part.get("indexed", False)]
    if len(normalized["topics"]) != len(indexed) + 1:
        raise RpcError("Incorrect indexed event field count", kind="integrity")
    indexed_values = []
    for field, raw in zip(indexed, normalized["topics"][1:]):
        if _dynamic(field) or field["type"] == "tuple":
            indexed_values.append(raw)
        else:
            indexed_values.append(_decode_static(field, bytes.fromhex(raw[2:]), 0)[0])
    data = bytes.fromhex(normalized["data"][2:])
    plain_values, end = _decode_sequence(plain, data)
    if end != len(data):
        raise RpcError("Trailing event data", kind="integrity")
    indexed_iter, plain_iter = iter(indexed_values), iter(plain_values)
    values = _named(item["inputs"], [next(indexed_iter) if field.get("indexed", False) else next(plain_iter) for field in item["inputs"]])
    return {"event": item["name"], "values": values,
            **{key: normalized[key] for key in ("blockNumber", "transactionIndex", "logIndex", "transactionHash", "blockHash", "address")}}


def json_safe(value):
    """Preserve JSON interoperability without narrowing integer arithmetic."""
    if type(value) is int:
        return str(value) if abs(value) > (1 << 53) - 1 else value
    if isinstance(value, Fraction):
        return ratio(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise RpcError("Nonfinite result cannot be serialized", kind="serialization")
    return value


def serialize_result(result):
    if result.get("command") == "advance":
        # Lazy import avoids a module cycle; every saved/printed body shares this contract.
        from netstack_advance import prepare_result
        prepare_result(result)
    return json.dumps(json_safe(result), ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"


def _merge_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _missing_ranges(start, end, covered):
    missing, cursor = [], start
    for left, right in covered:
        if left > cursor:
            missing.append([cursor, left - 1])
        cursor = max(cursor, right + 1)
    if cursor <= end:
        missing.append([cursor, end])
    return missing


class _FixedHTTPSConnection(http.client.HTTPSConnection):
    """Resolve once, reject nonpublic addresses, and retain fixed TLS SNI."""
    def connect(self):
        if self.host != RPC_HOST or self.port != 443 or self._tunnel_host:
            raise RpcError("Unapproved HTTPS destination or tunnel", kind="permission")
        answers = socket.getaddrinfo(RPC_HOST, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        if not answers or len(answers) > 16:
            raise RpcError("RPC DNS answer count is invalid", kind="permission")
        for family, socktype, protocol, canonical, destination in answers:
            address = ipaddress.ip_address(destination[0])
            if (family not in (socket.AF_INET, socket.AF_INET6) or not address.is_global
                    or address.is_multicast or address.is_reserved or address.is_unspecified
                    or address.is_loopback or address.is_link_local or address.is_private
                    or getattr(address, "ipv4_mapped", None) is not None):
                raise RpcError("RPC DNS resolved to a nonpublic destination", kind="permission")
        # A single validated numeric destination prevents both proxy use and
        # a second hostname lookup between policy enforcement and connection.
        family, socktype, protocol, canonical, destination = answers[0]
        sock = socket.socket(family, socktype, protocol)
        try:
            sock.settimeout(self.timeout)
            sock.connect(destination)
            self.sock = self._context.wrap_socket(sock, server_hostname=RPC_HOST)
        except BaseException:
            sock.close()
            raise


class Context:
    def __init__(self, command, deadline=120, output=None):
        if command not in ("lp", "predict", "house", "rfv", "advance"):
            raise RpcError("Unknown analytics command", kind="input")
        if not isinstance(deadline, (int, float)) or not math.isfinite(deadline) or not 0 < deadline <= 600:
            raise RpcError("Deadline must be positive and at most 600 seconds", kind="input")
        self.result = {"schema_version": 1, "command": command, "snapshot": {}, "metrics": {},
                       "coverage": {}, "not_proven": [], "errors": []}
        self.command, self.output = command, output
        self.block = self.timestamp = None
        self._started = time.monotonic()
        self._deadline = deadline
        self._hard_end = self._started + deadline
        self._collect_end = self._hard_end - SERIALIZATION_RESERVE
        self._attempt_end = None
        self._stopped = "deadline_exhausted" if deadline <= SERIALIZATION_RESERVE else None
        self._finalizing = False
        self._emitting = False
        self._closed = False
        self._old_handlers = {}
        self._cache = {}
        self._headers = {}
        self._observed_blocks = {}
        self._observed_transactions = {}
        self._observed_positions = {}
        self._observed_logs = {}
        self._integrity_invalid = False
        self._output_fd = None
        self._output_name = None
        self._receipts = {}
        self._next_id = 1
        self._members = self._rows = self._raw_bytes = self._recoveries = 0
        self._retry_not_before = 0.0
        self._retry_wait_seconds = 0.0
        self._member_limit = 750 if command in ("rfv", "advance") else 250
        self._row_limit = 50000 if command == "lp" else 10000
        self._allowed = None
        self._last_body = serialize_result(self.result)
        self._last_json = self.partial_json("collection_in_progress")
        if not hasattr(signal, "setitimer"):
            raise RpcError("POSIX interval timers are required", kind="platform")
        try:
            for sig in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM):
                self._old_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, self._signal)
        except (ValueError, OSError) as exc:
            self.close()
            raise RpcError("Analytics must run in the main POSIX thread", kind="platform") from exc
        self._arm()

    def _signal(self, signum, frame):
        if signum in (signal.SIGTERM, signal.SIGINT):
            self._stopped = "interrupted_by_" + signal.Signals(signum).name
            self._attempt_end = None
            self._arm()
            if self._emitting:
                # Once JSON starts, finish that document rather than knowingly
                # truncate it. SIGALRM still enforces the unchanged hard end.
                return
            raise StopRun(self._stopped)
        now = time.monotonic()
        if self._finalizing or now >= self._collect_end:
            self._stopped = self._stopped or "deadline_exhausted"
            self._attempt_end = None
            if not self._finalizing:
                self._arm()
            raise StopRun(self._stopped)
        self._attempt_end = None
        self._arm()
        raise RpcError("RPC attempt exceeded its walltime limit", kind="timeout", retryable=True, splittable=True)

    def _arm(self):
        if self._closed:
            return
        end = self._hard_end if self._finalizing or self._stopped else self._collect_end
        if self._attempt_end is not None:
            end = min(end, self._attempt_end)
        signal.setitimer(signal.ITIMER_REAL, max(0.000001, end - time.monotonic()))

    def check(self):
        if self._stopped:
            raise StopRun(self._stopped)
        if self._integrity_invalid:
            raise RpcError("Previously observed chain identities conflict; retrieval is invalid", kind="integrity")
        if time.monotonic() >= self._collect_end:
            self._stopped = "deadline_exhausted"
            raise StopRun(self._stopped)

    def _stop(self, reason):
        self._stopped = reason
        self._attempt_end = None
        self._arm()
        raise StopRun(reason)

    def begin_finalization(self):
        self._finalizing = True
        self._attempt_end = None
        self._arm()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
            for sig, handler in self._old_handlers.items():
                signal.signal(sig, handler)
        finally:
            if self._output_fd is not None:
                os.close(self._output_fd)
                self._output_fd = None

    def _open_output_parent(self):
        path = Path(self.output)
        if not path.name or path.name in (".", ".."):
            raise RpcError("Output must name a regular checkpoint file", kind="output")
        if not path.is_absolute():
            path = Path.cwd() / path
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptor = None
        try:
            descriptor = os.open(path.anchor, flags)
            for component in path.parent.parts[1:]:
                following = os.open(component, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = following
            # Check the opened directory's real ancestry, not a path that could
            # resolve somewhere else between validation and atomic replacement.
            package = ROOT.stat()
            cursor = os.dup(descriptor)
            try:
                for depth in range(256):
                    current = os.fstat(cursor)
                    if (current.st_dev, current.st_ino) == (package.st_dev, package.st_ino):
                        raise RpcError("Output must be outside the installed package", kind="output")
                    parent = os.open("..", flags, dir_fd=cursor)
                    parent_stat = os.fstat(parent)
                    os.close(cursor)
                    cursor = parent
                    if (current.st_dev, current.st_ino) == (parent_stat.st_dev, parent_stat.st_ino):
                        break
                else:
                    raise RpcError("Output directory ancestry exceeds limit", kind="output")
            finally:
                os.close(cursor)
            self._validate_output_target(descriptor, path.name)
            self._output_fd, self._output_name = descriptor, path.name
            descriptor = None
        except OSError as exc:
            raise RpcError("Cannot open checkpoint parent without following symlinks", kind="output") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

    @staticmethod
    def _validate_output_target(directory_fd, name):
        try:
            target = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(target.st_mode):
            raise RpcError("Output target must be a regular file, never a symlink", kind="output")

    def _atomic_output(self, text):
        if self.output is None:
            return
        if self._closed:
            raise RpcError("Checkpoint directory is closed", kind="output")
        if self._output_fd is None:
            self._open_output_parent()
        directory_fd, name = self._output_fd, self._output_name
        temporary = None
        descriptor = None
        try:
            self._validate_output_target(directory_fd, name)
            for attempt in range(8):
                candidate = ".netstack-checkpoint-" + secrets.token_hex(16)
                try:
                    descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                         os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory_fd)
                except FileExistsError:
                    continue
                temporary = candidate
                break
            if descriptor is None:
                raise RpcError("Cannot allocate an exclusive checkpoint file", kind="output")
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = None
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            self._validate_output_target(directory_fd, name)
            os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            temporary = None
        except OSError as exc:
            raise RpcError("Cannot write atomic output checkpoint", kind="output") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary is not None:
                try:
                    os.unlink(temporary, dir_fd=directory_fd)
                except OSError:
                    pass

    def checkpoint(self):
        self.result["resources"] = {"rpc_members_used": self._members, "rpc_member_limit": self._member_limit,
                                    "event_rows_accepted": self._rows, "event_row_limit": self._row_limit,
                                    "response_bytes": self._raw_bytes, "recovery_attempts": self._recoveries,
                                    "recovery_limit": 10, "recovery_wait_seconds": self._retry_wait_seconds,
                                    "initial_log_block_limit": MAX_LOG_BLOCKS}
        self.result["elapsed_seconds"] = max(0.0, time.monotonic() - self._started)
        self.result["collector_deadline_seconds"] = self._deadline
        self._last_body = serialize_result({key: value for key, value in self.result.items()
                                           if key not in ("status", "stopping_reason", "elapsed_seconds", "collector_deadline_seconds")})
        envelope = {"status": self.result.get("status", "partial"),
                    "stopping_reason": self.result.get("stopping_reason", "collection_in_progress"),
                    "elapsed_seconds": self.result["elapsed_seconds"],
                    "collector_deadline_seconds": self._deadline}
        text = serialize_result(envelope)[:-2] + "," + self._last_body[1:]
        self._last_json = text
        self._atomic_output(text)

    def partial_json(self, reason):
        envelope = serialize_result({"status": "partial", "stopping_reason": reason,
                                     "elapsed_seconds": max(0.0, time.monotonic() - self._started),
                                     "collector_deadline_seconds": self._deadline})
        return envelope[:-2] + "," + self._last_body[1:]

    def _functions(self):
        if self._allowed is None:
            allowed = {}
            if self.command == "advance":
                filenames = ("advance-interface.json",)
            else:
                filenames = ("v2-interface.json", "predict-interface.json", "house-interface.json")
                if self.command == "rfv":
                    filenames += ("reserves-interface.json", "sleeve-interface.json", "book-interface.json", "v4-interface.json", "advance-interface.json")
            for filename in filenames:
                document = load_json("assets/analytics/" + filename)
                for key, items in document.items():
                    if key != "abi" and not key.endswith("_abi"):
                        continue
                    for item in items:
                        if item.get("type") == "function" and item.get("stateMutability") in ("view", "pure"):
                            allowed[signature(item)] = item
            self._allowed = allowed
        return self._allowed

    def _function(self, abi, name, args):
        candidates = [item for item in abi if item.get("type") == "function" and
                      (item.get("name") == name or signature(item) == name) and len(item.get("inputs", [])) == len(args)]
        if len(candidates) != 1:
            raise RpcError("Read function is missing or ambiguous", kind="abi")
        item = candidates[0]
        approved = self._functions().get(signature(item))
        if approved is None or item.get("stateMutability") not in ("view", "pure"):
            raise RpcError("Function is not in the packaged read-only allowlist", kind="permission")
        if [_canonical_type(o) for o in item.get("outputs", [])] != [_canonical_type(o) for o in approved.get("outputs", [])]:
            raise RpcError("ABI output shape differs from the packaged interface", kind="abi")
        return item

    def _block_tag(self, block):
        if block is None:
            if self.block is None:
                raise RpcError("Snapshot has not been pinned", kind="input")
            block = self.block
        return hex(_integer(block, "block number"))

    def _validate_payload(self, method, params):
        if not isinstance(params, list):
            raise RpcError("RPC params must be a list", kind="permission")
        if method == "eth_chainId" and params == []:
            return
        if method == "eth_getBlockByNumber" and len(params) == 2 and params[1] is False:
            if params[0] != "latest":
                _quantity(params[0])
            return
        if method == "eth_getTransactionReceipt" and len(params) == 1:
            _hex(params[0], 32)
            return
        if method == "eth_getCode" and len(params) == 2:
            _address(params[0])
            _quantity(params[1])
            return
        if method == "eth_call" and len(params) == 2 and isinstance(params[0], dict) and set(params[0]) == {"to", "data"}:
            _address(params[0]["to"])
            _quantity(params[1])
            data = _hex(params[0]["data"])
            matches = [item for item in self._functions().values() if topic(item)[:10] == data[:10]]
            if len(matches) != 1:
                raise RpcError("Unapproved or ambiguous call selector", kind="permission")
            _decode_outputs({"outputs": matches[0].get("inputs", [])}, "0x" + data[10:])
            return
        if method == "eth_getLogs" and len(params) == 1 and isinstance(params[0], dict):
            query = params[0]
            if set(query) == {"fromBlock", "toBlock", "topics"}:
                topics = query["topics"]
                if (not isinstance(topics, list) or len(topics) != 3
                        or topics[0] != [TRANSFER_TOPIC] or topics[1] is not None
                        or not isinstance(topics[2], str) or len(topics[2]) != 66
                        or topics[2][2:26] != "0" * 24):
                    raise RpcError("Unscoped owner transfer filter", kind="permission")
                self._discovery_owner("0x" + topics[2][26:])
                if _quantity(query["toBlock"]) - _quantity(query["fromBlock"]) >= MAX_LOG_BLOCKS:
                    raise RpcError("Owner transfer range exceeds bounded limit", kind="permission")
                if self.block is None or _quantity(query["toBlock"]) > self.block:
                    raise RpcError("Owner transfers require a pinned historical range", kind="permission")
            elif set(query) == {"address", "fromBlock", "toBlock", "topics"}:
                _address(query["address"])
            else:
                raise RpcError("Unapproved log filter fields", kind="permission")
            if _quantity(query["fromBlock"]) > _quantity(query["toBlock"]):
                raise RpcError("Inverted log range", kind="input")
            topics = query["topics"]
            if not isinstance(topics, list) or not 1 <= len(topics) <= 4 or topics[0] is None:
                raise RpcError("Log topic filter is required", kind="permission")
            for entry in topics:
                if isinstance(entry, list):
                    if not 1 <= len(entry) <= 64:
                        raise RpcError("Log topic alternatives exceed limit", kind="permission")
                    for value in entry:
                        _hex(value, 32)
                elif entry is not None:
                    _hex(entry, 32)
            return
        raise RpcError("RPC method or payload is not read-only allowlisted", kind="permission")

    @staticmethod
    def _remote_error(error):
        if not isinstance(error, dict) or type(error.get("code")) is not int or not isinstance(error.get("message"), str):
            return RpcError("Malformed RPC error object", kind="protocol")
        code = error["code"]
        message = error["message"].lower()
        if any(term in message for term in ("permission", "unauthor", "forbidden", "access denied", "not allowed")):
            return RpcError("RPC permission denied; no alternate provider attempted", kind="permission")
        if any(term in message for term in ("pruned", "missing trie", "historical state", "archive", "state unavailable")):
            return RpcError("Historical RPC state unavailable or pruned", kind="pruned")
        if any(term in message for term in ("rate limit", "too many requests", "request quota")):
            return RpcError("RPC rate limit; bounded cooldown required", kind="rate_limit", retryable=True)
        if "revert" in message:
            return RpcError("Read-only contract call reverted", kind="revert")
        if any(term in message for term in ("too many result", "more than", "range", "response size", "limit exceeded")):
            return RpcError("Provider log range or response limit", kind="range", splittable=True)
        if any(term in message for term in ("timeout", "timed out", "temporarily", "busy")):
            return RpcError("Transient RPC service failure", kind="transient", retryable=True, splittable=True)
        return RpcError("RPC returned error code " + str(code), kind="remote")

    @staticmethod
    def _retry_after(value):
        if value is None:
            return None
        try:
            value = value.strip()
            if value.isdigit():
                return float(value)
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            return max(0.0, date.timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            return None

    def _recover(self, error):
        self.check()
        if self._recoveries >= 10:
            self._stop("recovery_limit")
        delay = min(8.0, 2.0 ** min(self._recoveries, 3))
        if error.retry_after is not None:
            delay = max(delay, error.retry_after)
        delay = max(delay, self._retry_not_before - time.monotonic())
        # Never shorten Retry-After to fit our budget, or let another request
        # bypass a cooldown that could not be honored.
        if delay > MAX_RECOVERY_WAIT or time.monotonic() + delay >= self._collect_end:
            self._stop("provider_backoff_exceeds_budget")
        self._recoveries += 1
        self._retry_wait_seconds += delay
        time.sleep(delay)
        self.check()

    def _exchange_once(self, requests):
        self.check()
        if self._members + len(requests) > self._member_limit:
            self._stop("rpc_member_limit")
        if time.monotonic() < self._retry_not_before:
            self._recover(RpcError("Provider cooldown", kind="rate_limit"))
        for method, params in requests:
            self._validate_payload(method, params)
        entries = []
        for method, params in requests:
            entries.append({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params})
            self._next_id += 1
        body = json.dumps(entries[0] if len(entries) == 1 else entries, separators=(",", ":")).encode("ascii")
        if len(body) > 128 * 1024:
            raise RpcError("RPC request payload exceeds size limit", kind="input")
        self._members += len(entries)
        self._attempt_end = min(self._collect_end, time.monotonic() + 15.0)
        self._arm()
        connection = None
        try:
            timeout = max(0.001, self._attempt_end - time.monotonic())
            connection = _FixedHTTPSConnection(RPC_HOST, 443, timeout=timeout, context=ssl.create_default_context())
            connection.request("POST", "/", body=body, headers={"Content-Type": "application/json", "Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": "netstack-analytics/1"})
            response = connection.getresponse()
            if response.status in (401, 403, 407):
                raise RpcError("RPC permission denied; no alternate provider attempted", kind="permission")
            if 300 <= response.status < 400:
                raise RpcError("RPC redirect refused", kind="permission")
            if response.status != 200:
                transient = response.status in (408, 429, 500, 502, 503, 504)
                retry_after = self._retry_after(response.getheader("Retry-After")) if transient else None
                if response.status == 429 or retry_after is not None:
                    self._retry_not_before = max(self._retry_not_before,
                                                time.monotonic() + max(1.0, retry_after or 0.0))
                raise RpcError("RPC HTTP status " + str(response.status),
                               kind="rate_limit" if response.status == 429 else "http",
                               retryable=transient, retry_after=retry_after)
            if response.getheader("Content-Encoding", "identity").lower() not in ("", "identity"):
                raise RpcError("Compressed RPC responses are not accepted", kind="protocol")
            length = response.getheader("Content-Length")
            if length is not None and (not length.isdigit() or int(length) > MAX_RESPONSE_BYTES):
                raise RpcError("RPC response exceeds raw size limit", kind="size", splittable=True)
            chunks, size = [], 0
            while True:
                self.check()
                chunk = response.read(min(65536, MAX_RESPONSE_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                self._raw_bytes += len(chunk)
                if self._raw_bytes > MAX_TOTAL_BYTES:
                    self._stop("response_byte_limit")
                if size > MAX_RESPONSE_BYTES:
                    raise RpcError("RPC response exceeds raw size limit", kind="size", splittable=True)
            decoded = _parse_json(b"".join(chunks))
            values = [decoded] if len(entries) == 1 else decoded
            if not isinstance(values, list) or len(values) != len(entries):
                raise RpcError("RPC response member count mismatch", kind="protocol")
            expected = {entry["id"] for entry in entries}
            indexed = {}
            for value in values:
                if not isinstance(value, dict) or value.get("jsonrpc") != "2.0" or type(value.get("id")) is not int or value["id"] not in expected or value["id"] in indexed:
                    raise RpcError("RPC response IDs or protocol do not match", kind="protocol")
                if ("result" in value) == ("error" in value):
                    raise RpcError("RPC response must contain one result or error", kind="protocol")
                indexed[value["id"]] = self._remote_error(value["error"]) if "error" in value else value["result"]
                if isinstance(indexed[value["id"]], RpcError) and indexed[value["id"]].kind == "rate_limit":
                    self._retry_not_before = max(self._retry_not_before, time.monotonic() + 1.0)
            return [indexed[entry["id"]] for entry in entries]
        except StopRun:
            raise
        except (PermissionError, ssl.SSLCertVerificationError) as exc:
            raise RpcError("RPC transport permission or certificate verification denied", kind="permission") from exc
        except (socket.timeout, TimeoutError) as exc:
            raise RpcError("RPC transport timeout", kind="timeout", retryable=True, splittable=True) from exc
        except OSError as exc:
            if exc.errno in (errno.EPERM, errno.EACCES):
                raise RpcError("RPC transport permission denied; no alternate provider attempted", kind="permission") from exc
            raise RpcError("RPC transport unavailable", kind="transport", retryable=True) from exc
        except http.client.HTTPException as exc:
            raise RpcError("Invalid or interrupted HTTPS response", kind="transport", retryable=True) from exc
        finally:
            if connection is not None:
                connection.close()
            self._attempt_end = None
            self._arm()

    def _exchange(self, requests, accept=None):
        if not 1 <= len(requests) <= 20:
            raise RpcError("RPC batch size must be 1..20", kind="input")
        for attempt in range(2):
            try:
                results = self._exchange_once(requests)
                break
            except RpcError as exc:
                if attempt or not exc.retryable or self._recoveries >= 10:
                    raise
                self._recover(exc)
        if accept is not None:
            accept(results)
        # Retry only failed transient members, never successful members.
        retry_indices = [i for i, value in enumerate(results) if isinstance(value, RpcError) and value.retryable]
        fatal = any(isinstance(value, RpcError) and value.kind in ("permission", "integrity") for value in results)
        if retry_indices and not fatal and attempt == 0 and self._recoveries < 10:
            self._recover(max((results[i] for i in retry_indices), key=lambda error: error.retry_after or 0.0))
            try:
                retried = self._exchange_once([requests[i] for i in retry_indices])
                for index, value in zip(retry_indices, retried):
                    results[index] = value
            except RpcError as exc:
                for index in retry_indices:
                    results[index] = exc
            if accept is not None:
                accept(results)
        return results

    def _rpc(self, method, params):
        result = self._exchange([(method, params)])[0]
        if isinstance(result, RpcError):
            raise result
        return result

    def call(self, address, abi, name, args=(), block=None):
        return self.calls([(address, abi, name, args)], block=block)[0]

    def calls(self, specs, block=None):
        tag = self._block_tag(block)
        prepared = []
        for address, abi, name, args in specs:
            self.check()
            address = _address(address)
            item = self._function(abi, name, args)
            encoded = topic(item)[:10] + b"".join(_encode_value(field, value) for field, value in zip(item.get("inputs", []), args)).hex()
            prepared.append(((address, encoded, tag), item))
        pending, seen = [], set()
        for key, item in prepared:
            if key not in self._cache and key not in seen:
                pending.append((key, item))
                seen.add(key)
        for start in range(0, len(pending), 20):
            batch = pending[start:start + 20]

            def accept(values):
                # Commit successful members before any transient-member retry.
                # A deadline or SIGTERM in that retry must not erase them.
                for index, ((key, item), raw) in enumerate(zip(batch, values)):
                    if isinstance(raw, RpcError) or key in self._cache:
                        continue
                    try:
                        self._cache[key] = _decode_outputs(item, raw)
                    except RpcError as exc:
                        values[index] = exc

            values = self._exchange(
                [("eth_call", [{"to": key[0], "data": key[1]}, key[2]]) for key, item in batch],
                accept=accept)
            failures = [value for value in values if isinstance(value, RpcError)]
            if failures:
                raise failures[0]
        return [self._cache[key] for key, item in prepared]

    def _invalidate_identity(self, message):
        self._integrity_invalid = True
        self.result["snapshot"]["recheck_status"] = "mismatch"
        self.result["snapshot"]["confirmation"] = "invalid"
        self.result["coverage"]["collection_complete"] = False

        def invalidate(value):
            if isinstance(value, dict):
                if "event_coverage_complete" in value:
                    value["event_coverage_complete"] = False
                    value["snapshot_valid"] = False
                if "collection_complete" in value:
                    value["collection_complete"] = False
                if "snapshot_valid" in value:
                    value["snapshot_valid"] = False
                for child in value.values():
                    invalidate(child)
            elif isinstance(value, list):
                for child in value:
                    invalidate(child)

        invalidate(self.result["coverage"])
        raise RpcError(message, kind="integrity")

    def _observe_identity(self, number, block_hash, tx_hash=None, tx_index=None):
        known_hash = self._observed_blocks.get(number)
        if known_hash is not None and known_hash != block_hash:
            self._invalidate_identity("Observed block height has conflicting hashes")
        if tx_hash is not None:
            identity = (number, block_hash, tx_index)
            known_identity = self._observed_transactions.get(tx_hash)
            if known_identity is not None and known_identity != identity:
                self._invalidate_identity("Observed transaction hash has conflicting block or position")
            position = (number, tx_index)
            known_transaction = self._observed_positions.get(position)
            if known_transaction is not None and known_transaction != tx_hash:
                self._invalidate_identity("Observed transaction position has conflicting hashes")
            self._observed_transactions[tx_hash] = identity
            self._observed_positions[position] = tx_hash
        self._observed_blocks[number] = block_hash

    def _observe_log(self, log):
        self._observe_identity(log["blockNumber"], log["blockHash"],
                               log["transactionHash"], log["transactionIndex"])
        identity = (log["blockHash"], log["logIndex"])
        fingerprint = (log["blockNumber"], log["transactionHash"], log["transactionIndex"],
                       log["address"], tuple(log["topics"]), log["data"])
        previous = self._observed_logs.get(identity)
        if previous is not None:
            if previous != fingerprint:
                self._invalidate_identity("Observed event identity has conflicting emitter, topics or data")
        else:
            if len(self._observed_logs) >= self._row_limit:
                self._stop("event_row_limit")
            self._observed_logs[identity] = fingerprint


    def header(self, number, *, fresh=False):
        self.check()
        tag = "latest" if number == "latest" else hex(_integer(number, "block number"))
        if not fresh and tag != "latest" and number in self._headers:
            return self._headers[number]
        raw = self._rpc("eth_getBlockByNumber", [tag, False])
        if not isinstance(raw, dict):
            raise RpcError("Requested block header is unavailable", kind="unavailable")
        value = {"number": _quantity(raw.get("number")), "hash": _hex(raw.get("hash"), 32), "timestamp": _quantity(raw.get("timestamp"))}
        if tag != "latest" and value["number"] != number:
            self._invalidate_identity("RPC returned the wrong block header")
        existing = self._headers.get(value["number"])
        if existing is not None and existing != value:
            self._invalidate_identity("Conflicting block headers")
        self._observe_identity(value["number"], value["hash"])
        self._headers[value["number"]] = value
        return value

    def pin(self, block_spec):
        self.check()
        if _quantity(self._rpc("eth_chainId", [])) != CHAIN_ID:
            raise RpcError("RPC chain ID does not match Robinhood 4663", kind="integrity")
        if block_spec == "latest-2":
            latest = self.header("latest")
            if latest["number"] < 2:
                raise RpcError("Chain has insufficient blocks for latest-2", kind="input")
            number = latest["number"] - 2
        elif isinstance(block_spec, str) and re.fullmatch(r"0|[1-9][0-9]*", block_spec):
            number = int(block_spec)
        elif type(block_spec) is int:
            number = block_spec
        else:
            raise RpcError("Block must be latest-2 or a nonnegative integer", kind="input")
        header = self.header(number)
        self.block, self.timestamp = header["number"], header["timestamp"]
        self.result["snapshot"] = {"chain_id": CHAIN_ID, "rpc_origin": "https://" + RPC_HOST,
                                   "block_number": self.block, "block_hash": header["hash"],
                                   "timestamp": self.timestamp, "requested_block": block_spec,
                                   "recheck_status": "not_performed"}
        self.checkpoint()

    def recheck(self):
        self.check()
        if self.block is None:
            raise RpcError("Snapshot has not been pinned", kind="input")
        snapshot = self.result["snapshot"]
        snapshot["recheck_status"] = "unconfirmed"
        value = self.header(self.block, fresh=True)
        if value["hash"] != snapshot["block_hash"] or value["timestamp"] != self.timestamp:
            self._invalidate_identity("Pinned snapshot changed; coverage is invalid")
        snapshot["recheck_status"] = "confirmed"
        for coverage in self.result["coverage"].values():
            if isinstance(coverage, dict) and "snapshot_valid" in coverage:
                coverage["snapshot_valid"] = True

    def code(self, address, block=None):
        self.check()
        address, tag = _address(address), self._block_tag(block)
        key = ("code", address, tag)
        if key not in self._cache:
            self._cache[key] = _hex(self._rpc("eth_getCode", [address, tag]))
        return self._cache[key]

    def find_block(self, timestamp):
        self.check()
        _integer(timestamp, "timestamp")
        if self.block is None:
            raise RpcError("Snapshot has not been pinned", kind="input")
        if timestamp >= self.timestamp:
            return self.block
        genesis = self.header(0)
        if timestamp < genesis["timestamp"]:
            raise RpcError("No chain block exists at the requested timestamp", kind="unavailable")
        low, high = 0, self.block
        while low < high:
            self.check()
            middle = (low + high + 1) // 2
            if self.header(middle)["timestamp"] <= timestamp:
                low = middle
            else:
                high = middle - 1
        return low

    def receipt(self, tx_hash):
        self.check()
        tx_hash = _hex(tx_hash, 32)
        if tx_hash in self._receipts:
            return self._receipts[tx_hash]
        raw = self._rpc("eth_getTransactionReceipt", [tx_hash])
        if not isinstance(raw, dict) or _hex(raw.get("transactionHash"), 32) != tx_hash:
            raise RpcError("Transaction receipt missing or identity mismatch", kind="integrity")
        block, tx_index = _quantity(raw.get("blockNumber")), _quantity(raw.get("transactionIndex"))
        block_hash = _hex(raw.get("blockHash"), 32)
        if self.block is not None and block > self.block:
            raise RpcError("Receipt is newer than the pinned snapshot", kind="integrity")
        self._observe_identity(block, block_hash, tx_hash, tx_index)
        status_value = _quantity(raw.get("status"))
        if status_value not in (0, 1):
            raise RpcError("Invalid receipt status", kind="integrity")
        _address(raw.get("from"))
        if raw.get("to") is not None:
            _address(raw["to"])
        if raw.get("contractAddress") is not None:
            _address(raw["contractAddress"])
        rows = raw.get("logs")
        if not isinstance(rows, list) or len(rows) >= MAX_PAGE_ROWS:
            raise RpcError("Receipt log list missing or reaches suspected cap", kind="integrity")
        if self._rows + len(rows) > self._row_limit:
            self._stop("event_row_limit")
        seen = {}
        for log in rows:
            normalized = _validated_log(log)
            if (normalized["blockNumber"], normalized["transactionIndex"], normalized["transactionHash"], normalized["blockHash"]) != (block, tx_index, tx_hash, block_hash):
                raise RpcError("Receipt log identity mismatch", kind="integrity")
            self._observe_log(normalized)
            key = normalized["logIndex"]
            if key in seen:
                raise RpcError("Duplicate receipt log index", kind="integrity")
            seen[key] = normalized
        self._rows += len(rows)
        self._receipts[tx_hash] = raw
        return raw

    def deployment(self, record):
        if not isinstance(record, dict):
            raise RpcError("Canonical deployment record required", kind="input")
        address = _address(record.get("address"))
        tx_hash = record.get("deployment_transaction_hash")
        provenance = None
        if tx_hash:
            receipt = self.receipt(tx_hash)
            if _quantity(receipt["status"]) != 1 or _address(receipt.get("contractAddress")) != address:
                raise RpcError("Creation receipt does not establish canonical deployment", kind="integrity")
            block = _quantity(receipt["blockNumber"])
            provenance = "canonical_creation_receipt"
        else:
            blocks = set()
            for entry in record.get("provenance", []):
                if not isinstance(entry, dict):
                    continue
                locator = entry.get("locator", "")
                if not isinstance(locator, str):
                    continue
                for match in re.finditer(r"(?:^|[;\s])block_number=(0|[1-9][0-9]*)(?=$|[;\s])", locator):
                    blocks.add(int(match[1]))
            if len(blocks) != 1:
                raise RpcError("Canonical deployment block is unavailable or ambiguous", kind="unavailable")
            block = blocks.pop()
            provenance = "publisher_recorded_block_number_locator"
        if self.block is None or block > self.block:
            raise RpcError("Deployment occurs after the requested snapshot", kind="unavailable")
        self.result["coverage"].setdefault("deployment_boundaries", {})[address] = {"block": block, "provenance": provenance}
        return block

    def creation_block(self, address, record=None):
        address = _address(address)
        if record is not None and _address(record.get("address")) != address:
            raise RpcError("Creation record address mismatch", kind="integrity")
        if record is not None and (record.get("deployment_transaction_hash") or any("block_number=" in str(p.get("locator", "")) for p in record.get("provenance", []) if isinstance(p, dict))):
            return self.deployment(record)
        if self.command != "lp":
            raise RpcError("A canonical recorded deployment boundary is required", kind="unavailable")
        if self.code(address) == "0x":
            raise RpcError("Contract has no code at pinned block", kind="integrity")
        low, high = 0, self.block
        while low < high:
            self.check()
            middle = (low + high) // 2
            if self.code(address, middle) == "0x":
                low = middle + 1
            else:
                high = middle
        self.result["coverage"].setdefault("deployment_boundaries", {})[address] = {
            "block": low, "provenance": "binary_historical_code_search",
            "assumption": "Code existence is monotonic; redeployments or historical provider omissions are not disproved."}
        return low

    def _discovery_owner(self, owner):
        owner = _address(owner)
        routes = resolve_routes("reserves")
        if self.command != "rfv" or owner not in (routes["treasury"]["address"], routes["sleeve"]["address"]):
            raise RpcError("Owner discovery is limited to canonical RFV custody", kind="permission")
        return owner

    def owner_transfers(self, key, owner, start, end):
        owner = self._discovery_owner(owner)
        abi = load_json("assets/analytics/v2-interface.json")["pair_abi"]
        return self.logs(key, None, abi, ["Transfer"], start, end,
                         indexed_topics=[None, "0x" + owner[2:].rjust(64, "0")], owner=owner, newest_first=True)

    def logs(self, key, address, abi, event_names, start, end, chunk=100000, *, indexed_topics=None, owner=None, newest_first=False):
        self.check()
        if address is None:
            owner = self._discovery_owner(owner)
            if event_names != ["Transfer"] or indexed_topics != [None, "0x" + owner[2:].rjust(64, "0")]:
                raise RpcError("Owner discovery requires an exact incoming Transfer filter", kind="permission")
        else:
            address = _address(address)
        _integer(start, "log start")
        _integer(end, "log end")
        if (self.block is None or end > self.block or start > end or type(chunk) is not int
                or chunk <= 0 or type(newest_first) is not bool):
            raise RpcError("Invalid pinned log scan range", kind="input")
        events = [item for item in abi if item.get("type") == "event" and not item.get("anonymous", False)
                  and (not event_names or item.get("name") in event_names)]
        if not events or (event_names and set(event_names) != {event["name"] for event in events}):
            raise RpcError("Requested events are not present in ABI", kind="abi")
        selectors = sorted(set(topic(event) for event in events))
        if address is None and selectors != [TRANSFER_TOPIC]:
            raise RpcError("Owner discovery requires the standard Transfer signature", kind="permission")
        topics = [selectors]
        if indexed_topics is not None:
            if not isinstance(indexed_topics, (tuple, list)) or len(indexed_topics) > 3:
                raise RpcError("Invalid indexed event filter", kind="input")
            for entry in indexed_topics:
                if isinstance(entry, (tuple, list)):
                    if not 1 <= len(entry) <= 20:
                        raise RpcError("Indexed event alternatives exceed limit", kind="input")
                    topics.append([_hex(value, 32) for value in entry])
                else:
                    topics.append(None if entry is None else _hex(entry, 32))
        coverage = {"requested_range": [start, end], "covered_ranges": [], "missing_ranges": [[start, end]],
                    "event_coverage_complete": False, "unknown_topics": {}, "rows": 0,
                    "filter": {"address": address, "topics": topics, "owner": owner},
                    "initial_chunk_blocks": min(chunk, MAX_LOG_BLOCKS),
                    "scan_order": "newest_first" if newest_first else "oldest_first",
                    "provider_completeness_assumption": "Served ranges are complete only assuming the RPC provider did not silently omit logs.",
                    "snapshot_valid": None, "status": "in_progress"}
        if key in self.result["coverage"]:
            existing = self.result["coverage"][key]
            planned = {"requested_range": [start, end], "covered_ranges": [],
                       "missing_ranges": [[start, end]], "event_coverage_complete": False,
                       "status": "not_started"}
            if (not isinstance(existing, dict) or existing != planned
                    or existing.get("event_coverage_complete") is not False):
                raise RpcError("Log coverage key already contains evidence or a different plan", kind="input")
            existing.update(coverage)
            coverage = existing
        else:
            self.result["coverage"][key] = coverage
        seen = {}
        block_hashes, tx_positions, tx_hash_positions = {}, {}, {}
        chunk = min(chunk, MAX_LOG_BLOCKS)
        intervals = (((max(start, right - chunk + 1), right) for right in range(end, start - 1, -chunk))
                     if newest_first else
                     ((left, min(end, left + chunk - 1)) for left in range(start, end + 1, chunk)))
        for interval in intervals:
            pending = [interval]
            while pending:
                self.check()
                left, right = pending.pop()
                query = {"fromBlock": hex(left), "toBlock": hex(right), "topics": topics}
                if address is not None:
                    query["address"] = address
                try:
                    raw = self._rpc("eth_getLogs", [query])
                    if not isinstance(raw, list):
                        raise RpcError("RPC log response is not a list", kind="protocol")
                    if len(raw) >= MAX_PAGE_ROWS:
                        raise RpcError("Log page reaches suspected provider row cap", kind="cap", splittable=True)
                except RpcError as exc:
                    if not exc.splittable or left == right or self._recoveries >= 10:
                        coverage["status"] = "partial"
                        coverage["failure_kind"] = exc.kind
                        coverage["failure"] = str(exc)
                        raise
                    self._recoveries += 1
                    middle = (left + right) // 2
                    pending.extend([(left, middle), (middle + 1, right)] if newest_first else
                                   [(middle + 1, right), (left, middle)])
                    continue
                page, page_seen, page_blocks, page_transactions, page_hash_positions = [], {}, {}, {}, {}
                for raw_log in raw:
                    self.check()
                    log = _validated_log(raw_log)
                    self._observe_log(log)
                    if (address is not None and log["address"] != address) or not left <= log["blockNumber"] <= right:
                        raise RpcError("Wrong emitter or out-of-range event log", kind="integrity")
                    if log["topics"][0] not in selectors:
                        name = log["topics"][0]
                        coverage["unknown_topics"][name] = coverage["unknown_topics"].get(name, 0) + 1
                        raise RpcError("Unknown or unrequested event topic", kind="integrity")
                    for position, wanted in enumerate(topics):
                        if wanted is not None and (position >= len(log["topics"]) or log["topics"][position] not in (wanted if isinstance(wanted, list) else [wanted])):
                            raise RpcError("Returned event violates requested topic filter", kind="integrity")
                    identity = (log["blockNumber"], log["logIndex"])
                    fingerprint = (log["transactionIndex"], log["transactionHash"], log["blockHash"], log["address"], tuple(log["topics"]), log["data"])
                    previous = page_seen.get(identity, seen.get(identity))
                    if previous is not None:
                        if previous != fingerprint:
                            raise RpcError("Conflicting duplicate event log", kind="integrity")
                        continue
                    number, block_hash = log["blockNumber"], log["blockHash"]
                    known = page_blocks.get(number, block_hashes.get(number))
                    if known is not None and known != block_hash:
                        raise RpcError("Event page contains conflicting block hashes", kind="integrity")
                    if number in self._headers and self._headers[number]["hash"] != block_hash:
                        raise RpcError("Event block hash differs from known header", kind="integrity")
                    tx_key = (number, log["transactionIndex"])
                    known_tx = page_transactions.get(tx_key, tx_positions.get(tx_key))
                    if known_tx is not None and known_tx != log["transactionHash"]:
                        raise RpcError("Event transaction position conflicts", kind="integrity")
                    known_position = page_hash_positions.get(log["transactionHash"], tx_hash_positions.get(log["transactionHash"]))
                    if known_position is not None and known_position != tx_key:
                        raise RpcError("Transaction hash appears at conflicting positions", kind="integrity")
                    page_hash_positions[log["transactionHash"]] = tx_key
                    page_blocks[number], page_transactions[tx_key], page_seen[identity] = block_hash, log["transactionHash"], fingerprint
                    if address is None:
                        # ERC20 and ERC721 share this selector. Unknown event
                        # layouts remain candidates, never assumed token balances.
                        decoded = dict(log, event="Transfer", values={}, transfer_kind="unknown")
                        if len(log["topics"]) == 3 and len(log["data"]) == 66:
                            decoded.update(transfer_kind="erc20", values={"value": int(log["data"], 16)})
                        elif len(log["topics"]) == 4 and log["data"] == "0x":
                            decoded.update(transfer_kind="erc721", values={"tokenId": int(log["topics"][3], 16)})
                    else:
                        decoded = decode_event(raw_log, abi)
                    if decoded is None:
                        name = log["topics"][0]
                        coverage["unknown_topics"][name] = coverage["unknown_topics"].get(name, 0) + 1
                        raise RpcError("Unknown event topic in requested event filter", kind="integrity")
                    page.append(decoded)
                if self._rows + len(page) > self._row_limit:
                    self._stop("event_row_limit")
                page.sort(key=lambda event: (event["blockNumber"], event["transactionIndex"], event["logIndex"]))
                for previous, current in zip(page, page[1:]):
                    if previous["blockNumber"] == current["blockNumber"] and previous["logIndex"] >= current["logIndex"]:
                        raise RpcError("Event log and transaction ordering conflict", kind="integrity")
                seen.update(page_seen)
                block_hashes.update(page_blocks)
                tx_positions.update(page_transactions)
                tx_hash_positions.update(page_hash_positions)
                self._rows += len(page)
                coverage["rows"] += len(page)
                coverage["covered_ranges"] = _merge_ranges(coverage["covered_ranges"] + [[left, right]])
                coverage["missing_ranges"] = _missing_ranges(start, end, coverage["covered_ranges"])
                coverage["event_coverage_complete"] = not coverage["missing_ranges"]
                coverage["status"] = "completed" if coverage["event_coverage_complete"] else "in_progress"
                yield page
                # Consumers have now incorporated this page. Persist both their
                # quantities and the exact served/missing intervals before more RPC.
                self.checkpoint()

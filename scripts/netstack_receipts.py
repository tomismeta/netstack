"""Bounded emitter/event receipt research, never an economic-total calculator."""
import hashlib
import os
import re
import stat

from netstack_core import (
    CHAIN_ID, MAX_LOG_BLOCKS, MAX_RESPONSE_BYTES, ROOT, TRANSFER_TOPIC,
    RpcError, _address, _canonical_type, _hex, _integer, _named, _parse_json,
    _quantity, _validated_log, decode_event, signature, topic,
)

_TRANSFER = {"type": "event", "name": "Transfer", "anonymous": False, "inputs": [
    {"name": "from", "type": "address", "indexed": True},
    {"name": "to", "type": "address", "indexed": True},
    {"name": "value", "type": "uint256", "indexed": False},
]}


def _catalog_document(path):
    if not isinstance(path, str) or not re.fullmatch(r"assets/contracts/[A-Za-z0-9][A-Za-z0-9_-]{0,127}\.json", path):
        raise RpcError("Catalog must name one packaged assets/contracts JSON file", kind="input")
    descriptor = None
    try:
        descriptor = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        for component in ("assets", "contracts"):
            following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        file_fd = os.open(path.rsplit("/", 1)[1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                          dir_fd=descriptor)
        with os.fdopen(file_fd, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_RESPONSE_BYTES:
                raise RpcError("Catalog must be a bounded regular package file", kind="package")
            raw = handle.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RpcError("Catalog exceeds package size limit", kind="package")
    except OSError as exc:
        raise RpcError("Packaged catalog is unavailable or is not a regular nonsymlink file", kind="package") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    document = _parse_json(raw)
    if not isinstance(document, dict):
        raise RpcError("Catalog must be an object", kind="package")
    return document, hashlib.sha256(raw).hexdigest()


def _fields(items, *, indexed=False, depth=0, budget=None):
    if depth > 8 or not isinstance(items, list) or len(items) > 128:
        raise RpcError("Catalog ABI fields exceed supported bounds", kind="abi")
    projected = []
    for item in items:
        budget[0] += 1
        if budget[0] > 4096 or not isinstance(item, dict):
            raise RpcError("Catalog ABI exceeds supported field bound", kind="abi")
        name, kind = item.get("name", ""), item.get("type")
        if (not isinstance(name, str) or len(name) > 128
                or (name and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name))
                or not isinstance(kind, str) or len(kind) > 128):
            raise RpcError("Malformed catalog ABI field", kind="abi")
        field = {"name": name, "type": kind}
        if indexed:
            flag = item.get("indexed")
            if type(flag) is not bool:
                raise RpcError("Catalog indexed flag must be boolean", kind="abi")
            field["indexed"] = flag
        if kind.startswith("tuple"):
            field["components"] = _fields(item.get("components"), depth=depth + 1, budget=budget)
        _canonical_type(field)
        projected.append(field)
    _named(projected, [None] * len(projected))
    return projected


def load_catalog(path, events=None, address=None):
    """Validate one local descriptive catalog and project its event-only ABI."""
    document, digest = _catalog_document(path)
    catalog_address = _address(document.get("address"))
    if (type(document.get("chain_id")) is not int or document["chain_id"] != CHAIN_ID
            or document.get("contract_id") != "robinhood-" + catalog_address):
        raise RpcError("Catalog contract identity or chain does not match", kind="package")
    entries = document.get("events")
    if not isinstance(entries, list) or len(entries) > 256:
        raise RpcError("Catalog event list is missing or exceeds limit", kind="abi")
    projected, seen, budget = [], set(), [0]
    for entry in entries:
        if not isinstance(entry, dict) or type(entry.get("anonymous", False)) is not bool:
            raise RpcError("Malformed catalog event", kind="abi")
        if entry.get("anonymous", False):
            continue
        if entry.get("type", "event") != "event":
            raise RpcError("Catalog event has a conflicting ABI type", kind="abi")
        item = {"type": "event", "name": entry.get("name"), "anonymous": False,
                "inputs": _fields(entry.get("inputs"), indexed=True, budget=budget)}
        sig, selector = signature(item), topic(item)
        if sum(field["indexed"] for field in item["inputs"]) > 3:
            raise RpcError("Nonanonymous event has too many indexed fields", kind="abi")
        if entry.get("signature") != sig or _hex(entry.get("topic0"), 32) != selector:
            raise RpcError("Catalog event signature or topic does not match its ABI", kind="abi")
        if selector in seen:
            raise RpcError("Catalog event topic is ambiguous", kind="abi")
        seen.add(selector)
        projected.append(item)
    if events is None:
        events = []
    if not isinstance(events, (list, tuple)) or len(events) > 64:
        raise RpcError("Event selections exceed the supported bound", kind="input")
    chosen = []
    for requested in events:
        if not isinstance(requested, str) or not 0 < len(requested) <= 4096:
            raise RpcError("Invalid event selection", kind="input")
        matches = [item for item in projected if requested in (item["name"], signature(item))]
        if len(matches) != 1:
            raise RpcError("Selected event is missing or ambiguous; use an exact signature", kind="input")
        if matches[0] not in chosen:
            chosen.append(matches[0])
    if not events:
        chosen = projected
    if not 1 <= len(chosen) <= 64:
        raise RpcError("Select between one and 64 named nonanonymous events", kind="input")
    emitter = catalog_address if address is None else _address(address)
    return {"path": path, "sha256": digest, "contract_id": document["contract_id"], "chain_id": CHAIN_ID,
            "catalog_address": catalog_address, "address": emitter,
            "applicability": "unverified_address_override" if address is not None else "catalog_address_interface_not_runtime_verified",
            "abi": chosen, "events": [{"name": item["name"], "signature": signature(item), "topic0": topic(item)}
                                      for item in chosen]}


def prepare_result(result):
    """Project conservative completeness for every checkpoint, including failures."""
    coverage = result.setdefault("coverage", {})
    requested = coverage.setdefault("requested_scope", {})
    evidence = result.get("metrics", {}).get("receipts", {})
    scan = coverage.get("receipt_scan", {})
    retrieved = bool(scan.get("status") == "completed" and not scan.get("missing_ranges", [None]))
    boundaries = evidence.get("boundaries", {})
    confirmed = (result.get("snapshot", {}).get("recheck_status") == "confirmed"
                 and all(boundaries.get(side, {}).get("recheck_status") == "confirmed"
                         for side in ("opening", "closing")))
    code_complete = all("code" in boundaries.get(side, {}) for side in ("opening", "closing"))
    missing = {row["transaction_hash"] for row in evidence.get("transactions", [])
               if row.get("receipt_status") != "verified"}
    missing.update(row["transaction_hash"] for row in evidence.get("witnesses", [])
                   if row.get("status") in ("pending", "failed"))
    receipts_complete = bool(evidence.get("reconciliation_complete") and not missing
                             and all(row.get("receipt_verified") for row in evidence.get("events", [])))
    invalid = (result.get("snapshot", {}).get("confirmation") == "invalid"
               or any(error.get("kind") in ("permission", "integrity") for error in result.get("errors", [])))
    complete = bool(retrieved and confirmed and code_complete and receipts_complete and not invalid)
    requested.update(collection_complete=complete, scan_complete=retrieved and confirmed and not invalid,
                     receipts_complete=receipts_complete and confirmed and not invalid,
                     boundaries_confirmed=confirmed and not invalid,
                     code_identities_complete=code_complete and confirmed and not invalid,
                     scan_retrieval_complete=retrieved, receipts_reconciliation_complete=receipts_complete,
                     code_identities_observed=code_complete, missing_receipts=sorted(missing))
    if scan and scan.get("status") != "not_started":
        scan["retrieval_complete"] = retrieved
        scan["event_coverage_complete"] = complete
        scan["snapshot_valid"] = confirmed and not invalid
    return result


def _failure(ctx, error, area, **identity):
    ctx.result["errors"].append({"kind": error.kind, "message": str(error), "area": area, **identity})
    if error.kind in ("permission", "integrity"):
        ctx._terminal_error = error
        raise error


def _boundary(header):
    return {"block_number": header["number"], "block_hash": header["hash"],
            "timestamp": header["timestamp"], "recheck_status": "not_performed"}


def recheck(ctx):
    """Confirm both interval boundaries without pretending to verify every block."""
    boundaries = ctx.result.get("metrics", {}).get("receipts", {}).get("boundaries", {})
    for side in ("opening", "closing"):
        boundary = boundaries.get(side)
        if boundary is None or "block_hash" not in boundary:
            continue
        boundary["recheck_status"] = "unconfirmed"
        try:
            if side == "closing":
                ctx.recheck()
            else:
                header = ctx.header(boundary["block_number"], fresh=True)
                if (header["hash"], header["timestamp"]) != (boundary["block_hash"], boundary["timestamp"]):
                    ctx._invalidate_identity("Opening boundary changed; receipt scope is invalid")
        except RpcError as exc:
            boundary["recheck_status"] = "mismatch" if exc.kind == "integrity" else "unconfirmed"
            _failure(ctx, exc, side + "_recheck")
        else:
            boundary["recheck_status"] = "confirmed"
        ctx.checkpoint()
    prepare_result(ctx.result)


def run(ctx, args):
    start = _integer(args.from_block, "receipt interval start")
    chunk = _integer(args.chunk_blocks, "receipt chunk size")
    if start == 0 or ctx.block is None or start > ctx.block or not 1 <= chunk <= MAX_LOG_BLOCKS:
        raise RpcError("Receipts require positive start <= pinned block and a bounded positive chunk", kind="input")
    seeds = args.tx
    if not isinstance(seeds, (list, tuple)) or len(seeds) > 128:
        raise RpcError("Witness receipt seeds exceed the supported bound", kind="input")
    seeds = list(dict.fromkeys(_hex(seed, 32) for seed in seeds))
    catalog = getattr(args, "_receipt_catalog", None) or load_catalog(args.catalog, args.event, args.address)
    abi, emitter = catalog["abi"], catalog["address"]
    by_topic = {item["topic0"]: item for item in catalog["events"]}
    scope = {"catalog": catalog["path"], "catalog_sha256": catalog["sha256"],
             "contract_id": catalog["contract_id"], "catalog_address": catalog["catalog_address"],
             "emitter": emitter, "applicability": catalog["applicability"], "selected_events": catalog["events"],
             "from_block": start, "to_block": ctx.block, "opening_block": start - 1}
    evidence = {"scope": scope, "boundaries": {"closing": _boundary(ctx.header(ctx.block))},
                "events": [], "transactions": [],
                "witnesses": [{"transaction_hash": seed, "status": "pending"} for seed in seeds],
                "reconciliation_complete": False}
    ctx.result["metrics"]["receipts"] = evidence
    ctx.result["coverage"]["receipt_scan"] = {"requested_range": [start, ctx.block], "covered_ranges": [],
        "missing_ranges": [[start, ctx.block]], "event_coverage_complete": False, "status": "not_started"}
    ctx.result["coverage"]["requested_scope"] = {
        "collection_complete": False, "meaning": "Only the selected emitter/events and inclusive interval, with receipt reconciliation.",
        "provider_completeness_assumption": "RPC may silently omit logs; boundary confirmation is not a proof of every intermediate block."}
    ctx.result["not_proven"].extend([
        "No revenue, global economic total, full economic history, balances or unobserved zero is established.",
        "Catalog ABI applicability is unverified; decoding and endpoint code hashes do not prove full source/compiler equivalence, proxy implementation identity or unchanged intermediate code.",
        "Receipt-local ERC20-layout Transfer legs are raw token quantities, not proof of token behavior, settlement attribution, pricing or revenue.",
        "Witness seeds are candidates, never substitutes for the selected emitter/event scan; out-of-interval receipts are excluded.",
    ])
    ctx.checkpoint()
    try:
        evidence["boundaries"]["opening"] = _boundary(ctx.header(start - 1))
    except RpcError as exc:
        _failure(ctx, exc, "opening_boundary")
    for side, block in (("opening", start - 1), ("closing", ctx.block)):
        try:
            raw = bytes.fromhex(ctx.code(emitter, block)[2:])
            identity = {"byte_count": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "exists": bool(raw)}
            boundary = evidence["boundaries"].setdefault(side, {"block_number": block, "recheck_status": "not_available"})
            boundary["code"] = identity
        except RpcError as exc:
            _failure(ctx, exc, side + "_code")
        ctx.checkpoint()

    events, transactions, expected = {}, {}, {}

    def event_row(decoded, selector, source):
        key = (decoded["blockHash"], decoded["logIndex"])
        row = events.get(key)
        if row is None:
            row = dict(decoded, signature=by_topic[selector]["signature"], topic0=selector,
                       evidence_sources=[], receipt_verified=False)
            events[key] = row
            evidence["events"].append(row)
        if source not in row["evidence_sources"]:
            row["evidence_sources"].append(source)
        return row

    def transaction(tx_hash, source, decoded=None):
        row = transactions.get(tx_hash)
        if row is None:
            row = {"transaction_hash": tx_hash, "receipt_status": "pending", "status": None,
                   "evidence_sources": [], "selected_event_count": 0, "transfers": []}
            if decoded is not None:
                row.update(block_number=decoded["blockNumber"], block_hash=decoded["blockHash"],
                           transaction_index=decoded["transactionIndex"])
            transactions[tx_hash] = row
            evidence["transactions"].append(row)
        if source not in row["evidence_sources"]:
            row["evidence_sources"].append(source)
        return row

    def collect(tx_hash, witness=None):
        row = transactions.get(tx_hash)
        try:
            receipt = ctx.receipt(tx_hash, allow_after_snapshot=witness is not None)
            block = _quantity(receipt["blockNumber"])
            if witness is not None and not start <= block <= ctx.block:
                witness.update(status="excluded_outside_interval", block_number=block)
                return
            if _quantity(receipt["status"]) != 1:
                raise RpcError("Selected receipt transaction did not succeed", kind="integrity")
            source = "witness" if witness is not None else "scan"
            row = transaction(tx_hash, source)
            row.update(block_number=block, block_hash=_hex(receipt["blockHash"], 32),
                       transaction_index=_quantity(receipt["transactionIndex"]), status=1)
            receipt_keys = set()
            selected, transfers = [], []
            for raw_log in receipt["logs"]:
                ctx.check()
                log = _validated_log(raw_log)
                key = (log["blockHash"], log["logIndex"])
                receipt_keys.add(key)
                # Context has already reconciled exact emitter/topics/data fingerprints.
                if log["address"] == emitter and log["topics"] and log["topics"][0] in by_topic:
                    decoded = decode_event(raw_log, abi)
                    event = event_row(decoded, log["topics"][0], "receipt")
                    if witness is not None and "witness" not in event["evidence_sources"]:
                        event["evidence_sources"].append("witness")
                    event["receipt_verified"] = True
                    selected.append(key)
                if log["topics"] and log["topics"][0] == TRANSFER_TOPIC:
                    if len(log["topics"]) == 3 and len(log["data"]) == 66:
                        transfer = decode_event(raw_log, [_TRANSFER])
                        transfers.append(dict(transfer, token=log["address"], amount_raw=transfer["values"]["value"]))
            if not expected.get(tx_hash, set()).issubset(receipt_keys):
                raise RpcError("Observed scan log is missing from its transaction receipt", kind="integrity")
            row.update(receipt_status="verified", selected_event_count=len(selected), transfers=transfers)
            if witness is not None:
                witness.update(status="included", block_number=block, selected_event_count=len(selected))
        except RpcError as exc:
            if row is not None:
                row.update(receipt_status="failed", failure_kind=exc.kind)
            if witness is not None:
                witness.update(status="failed", failure_kind=exc.kind)
            _failure(ctx, exc, "receipt", transaction_hash=tx_hash)
        finally:
            ctx.checkpoint()

    for witness in evidence["witnesses"]:
        collect(witness["transaction_hash"], witness)
    pages = ctx.logs("receipt_scan", emitter, abi, [], start, ctx.block, chunk=chunk)
    while True:
        try:
            page = next(pages)
        except StopIteration:
            break
        except RpcError as exc:
            scan = ctx.result["coverage"]["receipt_scan"]
            scan.update(status="partial", failure_kind=exc.kind, failure=str(exc))
            _failure(ctx, exc, "scan")
            break
        page_transactions = set()
        for decoded in page:
            tx_hash = decoded["transactionHash"]
            key = (decoded["blockHash"], decoded["logIndex"])
            # The exact raw selector is retained by the guarded Context identity map.
            selector = ctx._observed_logs[key][4][0]
            event_row(decoded, selector, "scan")
            expected.setdefault(tx_hash, set()).add(key)
            transaction(tx_hash, "scan", decoded)
            page_transactions.add(tx_hash)
        ctx.checkpoint()
        for tx_hash in sorted(page_transactions):
            collect(tx_hash)
        ctx.checkpoint()
    covered = ctx.result["coverage"]["receipt_scan"]["covered_ranges"]
    for event in evidence["events"]:
        if ("scan" not in event["evidence_sources"] and event["receipt_verified"]
                and any(left <= event["blockNumber"] <= right for left, right in covered)):
            ctx._invalidate_identity("Scanned range omitted a receipt-proven selected event")
    evidence["reconciliation_complete"] = True
    ctx.checkpoint()

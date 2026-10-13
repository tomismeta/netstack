"""Source-bound standard-bond epochs, direct receipts and post-transaction capacity."""

import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit
from fractions import Fraction

from netstack_core import (MAX_LOG_BLOCKS, ZERO, TRANSFER_TOPIC, RpcError, _address,
                           _hex, _quantity, amount, decode_event, load_json, ratio,
                           resolve_routes, serialize_result, topic)
from netstack_package import loads_json_bytes

EPOCH_SECONDS = 28800
NET_UNIT = 10**9
CAP_BPS = 25
SCAN_KEYS = ("standard_bond_sales", "standard_bond_mints", "standard_bond_burns")
BINDINGS = (("net", "net"), ("usdg", "usdg"), ("treasury", "treasury"),
            ("pairContract", "pair"))


def quantity(raw, unit="NET"):
    decimals = {"NET": 9, "USDG": 6, "LP": 18}[unit]
    return {"raw": str(raw), "decimals": decimals, "unit": unit,
            "formatted": amount(raw, decimals)}


def epoch_window(start, timestamp, count):
    if type(count) is not int or not 1 <= count <= 30:
        raise RpcError("Epoch count must be 1..30", kind="input")
    if type(start) is not int or start <= 0 or timestamp < start:
        raise RpcError("Standard bonds have no enabled epoch origin at snapshot", kind="unavailable")
    current = (timestamp - start) // EPOCH_SECONDS
    return list(range(max(0, current-count), current)), current


def available(supply, used):
    return max(0, supply * CAP_BPS // 10000 - used)


def _order(row):
    return row["blockNumber"], row["transactionIndex"], row["logIndex"]


def _identity(row):
    return (row["blockNumber"], row["blockHash"], row["transactionHash"],
            row["transactionIndex"])


def _read(ctx, scope, function):
    try:
        return function()
    except RpcError as error:
        if error.kind in ("permission", "integrity"):
            raise
        ctx.result["errors"].append({"scope": scope, "kind": error.kind, "message": str(error)})
        return None


def _runtime(ctx, routes, evidence, role, block):
    raw = bytes.fromhex(ctx.code(routes[role]["address"], block=block)[2:])
    expected = evidence["contracts"][role]
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != expected["runtime_bytes"] or digest != expected["runtime_sha256"]:
        raise RpcError("Standard-bond dependency runtime differs from reviewed source generation", kind="unsupported")
    return {"role": role, "block": block, "runtime_sha256": digest,
            "runtime_bytes": len(raw), "status": "reviewed_runtime_matched"}


def opening_prices(ctx, routes, source, block):
    specs = [(routes["treasury"]["address"], source["treasury_abi"], "backingPerToken", ())]
    specs += [(routes["pair"]["address"], source["pair_abi"], name, ())
              for name in ("token0", "token1", "getReserves")]
    nav, token0, token1, reserves = ctx.calls(specs, block=block)
    if {_address(token0), _address(token1)} != {routes["net"]["address"], routes["usdg"]["address"]}:
        raise RpcError("Opening market pair assets differ from canonical NET/USDG", kind="integrity")
    net, usdg = ((reserves["0"], reserves["1"]) if _address(token0) == routes["net"]["address"]
                 else (reserves["1"], reserves["0"]))
    if net <= 0 or usdg <= 0:
        raise RpcError("Opening market reserves cannot price NET", kind="unavailable")
    spot = Fraction(usdg * NET_UNIT, net * 10**6)
    return {"nav": {"raw": str(nav), "decimals": 18, "unit": "USDG/NET",
                    "formatted": amount(nav, 18), "basis": "Treasury.backingPerToken; Core getter, not Sleeve-inclusive RFV"},
            "market_spot": {**ratio(spot), "unit": "USDG/NET",
                            "formatted_floor_18dp": amount(spot.numerator * 10**18 // spot.denominator, 18),
                            "basis": "Canonical v2 reserve ratio, before fees, tax and price impact; not TWAP or bond price"},
            "net_reserve": quantity(net), "usdg_reserve": quantity(usdg, "USDG"),
            "token0": _address(token0), "token1": _address(token1)}


def discovery_document(path, snapshot, block_range):
    """Read bounded inert evidence through nonsymlink descriptors; never fetch its URL."""
    descriptor = None
    try:
        if not isinstance(path, str) or not path or len(path) > 4096 or ".." in Path(path).parts:
            raise RpcError("Invalid discovery document path", kind="input")
        absolute = Path(os.path.abspath(path))
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptor = os.open(absolute.anchor, flags)
        for component in absolute.parts[1:-1]:
            following = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        file_fd = os.open(absolute.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
        with os.fdopen(file_fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 2*1024*1024:
                raise RpcError("Discovery input must be a regular file at most 2 MiB", kind="input")
            raw = handle.read(2*1024*1024+1)
        if len(raw) > 2*1024*1024:
            raise RpcError("Discovery input exceeds 2 MiB", kind="input")
        document = loads_json_bytes(raw)
    except (OSError, ValueError, UnicodeError):
        raise RpcError("Discovery input is unavailable, unsafe or malformed", kind="input") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(document, dict) or set(document) != {"schema_version", "snapshot", "block_range", "source", "complete", "transaction_hashes"}:
        raise RpcError("Discovery input has unsupported fields", kind="input")
    anchor = document["snapshot"]
    if (type(document["schema_version"]) is not int or document["schema_version"] != 1 or
            not isinstance(anchor, dict) or set(anchor) != {"block_number", "block_hash"} or
            type(anchor["block_number"]) is not int or anchor["block_number"] != snapshot["block_number"] or
            _hex(anchor["block_hash"], 32) != snapshot["block_hash"] or
            document["block_range"] != block_range or
            not isinstance(document["block_range"], list) or
            any(type(value) is not int for value in document["block_range"])):
        raise RpcError("Discovery input does not match pinned snapshot and complete epoch window", kind="input")
    source = document["source"]
    if (not isinstance(source, dict) or set(source) != {"url", "method", "coverage_basis"} or
            source["method"] not in ("blockscout_v1_logs", "authorized_index") or
            source["coverage_basis"] != "paginated_exact_window_all_three_filters" or
            type(document["complete"]) is not bool or not isinstance(source["url"], str) or len(source["url"]) > 2048):
        raise RpcError("Discovery provenance must declare bounded source and all three filters", kind="input")
    try:
        if any(ord(character) <= 32 or ord(character) >= 127 for character in source["url"]):
            raise ValueError()
        url = urlsplit(source["url"])
        if url.scheme != "https" or not url.hostname or url.username is not None or url.password is not None:
            raise ValueError()
        host = url.hostname.lower()
        if ":" in host:
            ipaddress.IPv6Address(host)
            host = "[" + host + "]"
        elif len(host) > 253 or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", host):
            raise ValueError()
        port = url.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        origin = "https://" + host + (":" + str(port) if port not in (None, 443) else "")
    except ValueError:
        raise RpcError("Discovery source must be a well-formed HTTPS URL without credentials or control characters", kind="input") from None
    hashes = document["transaction_hashes"]
    if not isinstance(hashes, list) or len(hashes) > 3000:
        raise RpcError("Discovery transaction list exceeds 3000 candidates", kind="input")
    hashes = [_hex(value, 32) for value in hashes]
    if len(set(hashes)) != len(hashes):
        raise RpcError("Discovery transaction hashes must be unique", kind="input")
    return hashes, {"source_origin": origin, "method": source["method"],
                    "coverage_basis": source["coverage_basis"], "document_sha256": hashlib.sha256(raw).hexdigest(),
                    "supplied_source_complete": document["complete"], "candidate_transactions": len(hashes),
                    "requested_range": block_range, "canonical_receipts_complete": False,
                    "assumption": "Caller asserts complete authorized index pagination for BondCreated and both NET zero-address Transfer directions over the exact interval. Receipt/state reconciliation does not independently prove index completeness."}


def receipt_events(receipt, routes, source):
    """Decode canonical relevant events and quote legs from an already validated receipt."""
    selector = topic(next(item for item in source["abi"] if item.get("name") == "BondCreated"))
    bond, net = (routes[name]["address"] for name in ("bond", "net"))
    tokens = {routes[name]["address"] for name in ("net", "usdg", "pair")}
    relevant, transfers, sales = [], [], []
    for raw in receipt["logs"]:
        if not raw["topics"]:
            continue
        address, first = _address(raw["address"]), raw["topics"][0].lower()
        if address == bond and first == selector:
            row = decode_event(raw, source["abi"])
            relevant.append(row)
            sales.append(row)
        elif address in tokens and first == TRANSFER_TOPIC:
            row = decode_event(raw, source["token_abi"])
            transfers.append(row)
            if address == net and ZERO in (row["values"]["from"], row["values"]["to"]):
                relevant.append(row)
    return relevant, transfers, sales


def reconcile_receipt(receipt, scanned, routes, source):
    """Assign only unique, exact preceding quote legs; retain unrelated cash separately."""
    if _quantity(receipt["status"]) != 1:
        raise RpcError("Standard-bond evidence has an unsuccessful receipt", kind="integrity")
    identity = (_quantity(receipt["blockNumber"]), receipt["blockHash"].lower(),
                receipt["transactionHash"].lower(), _quantity(receipt["transactionIndex"]))
    bond, net, treasury = (routes[name]["address"] for name in ("bond", "net", "treasury"))
    relevant, transfers, sales = receipt_events(receipt, routes, source)
    actual = {row["logIndex"]: row for row in relevant}
    expected = {row["logIndex"]: row for row in scanned}
    if any(_identity(row) != identity for row in scanned) or any(actual.get(index) != row for index, row in expected.items()):
        raise RpcError("Standard-bond receipt and scanned evidence disagree", kind="integrity")
    missing = sorted(set(actual)-set(expected))
    allocated, observations = set(), []
    previous = -1
    for sale in sorted(sales, key=_order):
        values = sale["values"]
        market = values["marketId"]
        if market not in (0, 1):
            raise RpcError("Unsupported standard-bond market", kind="integrity")
        token = routes["usdg" if market == 0 else "pair"]["address"]
        legs = [row for row in transfers if row["address"] == token and
                row["values"]["to"] == treasury and row["values"]["value"] == values["amountIn"] and
                previous < row["logIndex"] < sale["logIndex"]]
        mints = [row for row in transfers if row["address"] == net and
                 row["values"]["from"] == ZERO and row["values"]["to"] == bond and
                 row["values"]["value"] == values["payout"] and
                 previous < row["logIndex"] < sale["logIndex"]]
        matched = len(legs) == 1 and len(mints) == 1 and legs[0]["logIndex"] < mints[0]["logIndex"]
        if matched:
            allocated.add(legs[0]["logIndex"])
        observations.append({"event_log_index": sale["logIndex"], "market_id": market,
                             "payout": quantity(values["payout"]), "matched": matched,
                             "quote_receipt": quantity(values["amountIn"], "USDG" if market == 0 else "LP") if matched else None,
                             "quote_log_index": legs[0]["logIndex"] if matched else None,
                             "payer": legs[0]["values"]["from"] if matched else None,
                             "beneficiary": values["depositor"]})
        previous = sale["logIndex"]
    extra = [row for row in transfers if row["address"] == routes["usdg"]["address"] and
             row["values"]["to"] == treasury and row["logIndex"] not in allocated]
    return {"transaction_hash": identity[2], "block_number": identity[0],
            "status": "checked", "missing_scanned_log_indices": missing,
            "sales": observations, "matched": not missing and all(row["matched"] for row in observations),
            "direct_usdg_received": quantity(sum(int(row["quote_receipt"]["raw"]) for row in observations
                                                  if row["matched"] and row["market_id"] == 0), "USDG"),
            "lp_received": quantity(sum(int(row["quote_receipt"]["raw"]) for row in observations
                                         if row["matched"] and row["market_id"] == 1), "LP"),
            "unattributed_usdg_incoming": quantity(sum(row["values"]["value"] for row in extra), "USDG"),
            "basis": "Unique receipt-local quote Transfer to Treasury preceding the matching NET mint and BondCreated; gross incoming, not net retained cash or revenue."}


def reconstruct_epoch(events, opening_supply, opening_used, start, timestamps):
    """Evaluate capacity only after a whole transaction, including all mint/burn changes."""
    if opening_used != 0:
        raise RpcError("Epoch payout counter is nonzero before its start", kind="integrity")
    groups = {}
    for event in sorted(events, key=_order):
        groups.setdefault(event["transactionHash"], []).append(event)
    supply, used, first = opening_supply, opening_used, None
    transactions, block_states = [], {}
    for tx_hash, rows in groups.items():
        payout = 0
        for row in rows:
            values = row["values"]
            if row["event"] == "BondCreated":
                if values["marketId"] not in (0, 1):
                    raise RpcError("Unsupported standard-bond market", kind="integrity")
                payout += values["payout"]
            else:
                if values["from"] == ZERO:
                    supply += values["value"]
                if values["to"] == ZERO:
                    supply -= values["value"]
                if supply < 0:
                    raise RpcError("NET supply reconstruction became negative", kind="integrity")
        used += payout
        block = rows[0]["blockNumber"]
        timestamp = timestamps[block]
        if not start <= timestamp < start+EPOCH_SECONDS:
            raise RpcError("Epoch evidence timestamp is outside its epoch", kind="integrity")
        remaining = available(supply, used)
        point = {"transaction_hash": tx_hash, "block_number": block,
                 "transaction_index": rows[0]["transactionIndex"], "timestamp": timestamp,
                 "seconds_since_epoch_start": timestamp-start, "supply": quantity(supply),
                 "payout_in_epoch": quantity(used), "available_net": quantity(remaining)}
        transactions.append(point)
        block_states[block] = {"supply": supply, "used": used}
        # No initial zero-capacity inference. The definition is a post-transaction state.
        if first is None and remaining < NET_UNIT:
            first = point
    return {"first_below_one_net": first, "transactions": transactions,
            "block_states": block_states, "closing_supply": supply, "closing_used": used}


def _observed_totals(sales, receipts):
    return {"purchases": len(sales),
            "net_sold": quantity(sum(row["values"]["payout"] for row in sales)),
            "market_0_purchases": sum(row["values"]["marketId"] == 0 for row in sales),
            "market_1_purchases": sum(row["values"]["marketId"] == 1 for row in sales),
            "market_0_net_sold": quantity(sum(row["values"]["payout"] for row in sales if row["values"]["marketId"] == 0)),
            "market_1_net_sold": quantity(sum(row["values"]["payout"] for row in sales if row["values"]["marketId"] == 1)),
            "direct_usdg_received": quantity(sum(int(row["direct_usdg_received"]["raw"]) for row in receipts if row["status"] == "checked"), "USDG"),
            "lp_received": quantity(sum(int(row["lp_received"]["raw"]) for row in receipts if row["status"] == "checked"), "LP")}


def prepare_result(result):
    metrics, coverage = result.get("metrics", {}), result.get("coverage", {})
    if "events" not in metrics:
        return
    safe = not any(row.get("kind") in ("permission", "integrity") for row in result.get("errors", []))
    confirmed = result.get("snapshot", {}).get("recheck_status") == "confirmed"
    snapshot_ok = bool(safe and confirmed and metrics.get("bindings_complete"))
    discovery = coverage.get("supplied_discovery")
    scanned = (discovery.get("supplied_source_complete") and discovery.get("canonical_receipts_complete")
               if discovery is not None else
               all(coverage.get(key, {}).get("event_coverage_complete") for key in SCAN_KEYS))
    history_ok = bool(snapshot_ok and coverage.get("historical_headers_confirmed") and scanned)
    receipts = metrics["receipts"]
    checked = {row["transaction_hash"]: row for row in receipts if row["status"] == "checked" and row["matched"]}
    all_receipts = all(row["transactionHash"] in checked for row in metrics["events"])
    coverage["snapshot_scope_complete"] = snapshot_ok
    coverage["receipt_reconciliation"] = {"collection_complete": bool(history_ok and all_receipts),
                                           "checked_transactions": len(checked)}
    all_epochs = bool(metrics["epochs"])
    for epoch in metrics["epochs"]:
        complete = bool(history_ok and epoch.get("reconstruction_complete") and epoch.get("opening_prices") and
                        all(tx in checked for tx in epoch.get("transaction_hashes", [])))
        epoch["complete"] = complete
        epoch["totals"] = epoch.get("observed_subtotal") if complete else None
        model = epoch.get("reconstruction")
        epoch["sellout"] = ({"status": "first_post_transaction_below_one_net" if model["first_below_one_net"] else "not_reached",
                             "first_crossing": model["first_below_one_net"],
                             "seconds_to_sellout": model["first_below_one_net"]["seconds_since_epoch_start"] if model["first_below_one_net"] else None}
                            if complete and model else {"status": "unknown", "first_crossing": None, "seconds_to_sellout": None})
        all_epochs = all_epochs and complete
    sales = [row for row in metrics["events"] if row["event"] == "BondCreated"]
    metrics["observed_subtotal"] = _observed_totals(sales, receipts)
    complete = bool(all_epochs and all_receipts and metrics.get("window", {}).get("requested_count_available"))
    metrics["totals"] = metrics["observed_subtotal"] if complete else None
    coverage["collection_complete"] = complete
    coverage["effective_status"] = "complete" if complete else "partial_or_unknown"
    coverage["completeness_basis"] = ("Supplied index completeness assertion plus canonical receipt/state/header reconciliation"
                                      if discovery is not None else "Served RPC logs plus canonical receipt/state/header reconciliation")


def run(ctx, args):
    routes = resolve_routes("standard-bonds")
    source = load_json(routes["_route"]["interface"])
    evidence = load_json("assets/contracts/bond-depository-source-evidence.json")
    metrics, coverage = ctx.result["metrics"], ctx.result["coverage"]
    metrics.update(source_id=evidence["source_id"], epochs=[], events=[], receipts=[],
                   implementations=[], bindings=[], bindings_complete=False, totals=None)
    coverage.update(collection_complete=False, historical_headers_confirmed=False)
    ctx.result["not_proven"].extend([
        "Source-reviewed arithmetic with exact BondDepository/NET runtime identity checks; not independent compiler equivalence or a security audit.",
        "Served logs and receipts plus boundary/touched-block counters constrain omissions, but cannot disprove a provider silently omitting offsetting intra-block changes.",
        "Sellout means first post-transaction available NET strictly below 1 NET; capacity can later reopen. It is not an immutable sold-out flag or a last-purchase time.",
        "Market 0 delivers USDG directly to Treasury; market 1 delivers canonical LP. LP value is never reported as USDG cash. NET sold is committed payout, not redeemed NET.",
        "Opening NAV is Treasury.backingPerToken, not independently reconciled Core backing and not Sleeve-inclusive true RFV. Existing Core POL/haircut uncertainty is not resolved by this getter.",
        "Opening market spot is the last block strictly before epoch start. Receipt cash is gross incoming, not profit or retained Treasury balance. No stored financial history is used.",
    ])
    chunk = args.chunk_blocks
    if type(chunk) is not int or not 1 <= chunk <= MAX_LOG_BLOCKS:
        raise RpcError("Invalid standard-bond log chunk bound", kind="input")
    bond, net = routes["bond"]["address"], routes["net"]["address"]
    historical = set()
    try:
        for role in ("bond", "net"):
            metrics["implementations"].append(_runtime(ctx, routes, evidence, role, ctx.block))
        for getter, target in BINDINGS:
            value = _address(ctx.call(bond, source["abi"], getter))
            metrics["bindings"].append({"getter": getter, "observed": value, "expected": routes[target]["address"]})
            if value != routes[target]["address"]:
                raise RpcError("Standard-bond canonical dependency mismatch", kind="integrity")
        for role, decimals in (("net", 9), ("usdg", 6), ("pair", 18)):
            if ctx.call(routes[role]["address"], source["token_abi"], "decimals") != decimals:
                raise RpcError("Standard-bond quote or NET decimal identity differs", kind="integrity")
        if ctx.call(bond, source["abi"], "marketCount") != 2:
            raise RpcError("Standard-bond market count differs", kind="integrity")
        for market, role in ((0, "usdg"), (1, "pair")):
            if _address(ctx.call(bond, source["abi"], "quoteToken", [market])) != routes[role]["address"]:
                raise RpcError("Standard-bond quote token differs", kind="integrity")
        enabled, start = ctx.calls([(bond, source["abi"], "enabled", ()), (bond, source["abi"], "startTime", ())])
        if not enabled:
            raise RpcError("Standard bonds are not enabled at snapshot", kind="unavailable")
        selected, ongoing = epoch_window(start, ctx.timestamp, args.epochs)
        metrics["window"] = {"requested_completed_epochs": args.epochs, "selected_epochs": selected,
                             "requested_count_available": len(selected) == args.epochs,
                             "start_time": start, "epoch_seconds": EPOCH_SECONDS,
                             "ongoing_epoch_excluded": {"epoch": ongoing, "start_timestamp": start+ongoing*EPOCH_SECONDS,
                                                        "end_timestamp": start+(ongoing+1)*EPOCH_SECONDS}}
        metrics["bindings_complete"] = True
        if not selected:
            return
        boundaries = {}
        for epoch in selected + [ongoing]:
            boundary_time = start + epoch*EPOCH_SECONDS
            before = ctx.find_block(boundary_time-1)
            before_header, after_header = ctx.header(before), ctx.header(before+1)
            if not before_header["timestamp"] < boundary_time <= after_header["timestamp"]:
                raise RpcError("Epoch boundary is not the last block strictly before start", kind="integrity")
            boundaries[epoch] = before
            historical.update((before, before+1))
        first, last = boundaries[selected[0]]+1, boundaries[ongoing]
        coverage["window"] = {"requested_range": [first, last], "epoch_selection": "Last completed consecutive epochs; zero-activity epochs retained"}
        # These contracts have no upgrade/redeployment path in the reviewed source.
        for role in ("bond", "net"):
            metrics["implementations"].append(_runtime(ctx, routes, evidence, role, first))
        for epoch in selected:
            opening, closing = boundaries[epoch], boundaries[epoch+1]
            row = {"epoch": epoch, "start_timestamp": start+epoch*EPOCH_SECONDS,
                   "end_timestamp": start+(epoch+1)*EPOCH_SECONDS,
                   "opening_header": ctx.header(opening), "closing_header": ctx.header(closing),
                   "block_range": [opening+1, closing], "opening_prices": None,
                   "reconstruction_complete": False, "transaction_hashes": [], "totals": None}
            metrics["epochs"].append(row)
            row["opening_prices"] = _read(ctx, "opening_prices", lambda: opening_prices(ctx, routes, source, opening))
            # Epoch zero can be enabled within the first included block; prior counter must still be zero.
            row["opening_state"] = _read(ctx, "opening_state", lambda: ctx.calls([
                (net, source["token_abi"], "totalSupply", ()), (bond, source["abi"], "payoutInEpoch", (epoch,))], block=opening))
            row["closing_state"] = _read(ctx, "closing_state", lambda: ctx.calls([
                (net, source["token_abi"], "totalSupply", ()), (bond, source["abi"], "payoutInEpoch", (epoch,))], block=closing))
            ctx.checkpoint()
        discovery_path = getattr(args, "discovery", None)
        if discovery_path is not None:
            hashes, provenance = discovery_document(discovery_path, ctx.result["snapshot"], [first, last])
            coverage["supplied_discovery"] = provenance
            acquired = 0
            for tx_hash in hashes:
                receipt = _read(ctx, "discovery_receipt", lambda: ctx.receipt(tx_hash))
                if receipt is None:
                    continue
                if not first <= _quantity(receipt["blockNumber"]) <= last:
                    raise RpcError("Discovery receipt is outside the exact completed epoch window", kind="integrity")
                events, _, _ = receipt_events(receipt, routes, source)
                if not events:
                    raise RpcError("Discovery receipt contains no standard-bond or NET supply evidence", kind="input")
                if _quantity(receipt["status"]) != 1:
                    raise RpcError("Discovery receipt was not successful", kind="integrity")
                if ctx._rows + len(events) > ctx._row_limit:
                    ctx._stop("event_row_limit")
                ctx._rows += len(events)
                metrics["events"].extend(events)
                acquired += 1
                provenance["acquired_transactions"] = acquired
                ctx.checkpoint()
            provenance["canonical_receipts_complete"] = acquired == len(hashes)
        else:
            zero_topic = "0x" + "0"*64
            scans = ((SCAN_KEYS[0], bond, source["abi"], ["BondCreated"], None),
                     (SCAN_KEYS[1], net, source["token_abi"], ["Transfer"], [zero_topic]),
                     (SCAN_KEYS[2], net, source["token_abi"], ["Transfer"], [None, zero_topic]))
            for key, address, abi, names, filters in scans:
                if first > last:
                    coverage[key] = {"requested_range": [first, last], "event_coverage_complete": True,
                                     "status": "empty_chain_interval", "rows": 0}
                    continue
                for page in ctx.logs(key, address, abi, names, first, last, chunk=chunk, indexed_topics=filters):
                    metrics["events"].extend(page)
                    ctx.checkpoint()
        metrics["events"].sort(key=_order)
        ctx.headers(sorted({event["blockNumber"] for event in metrics["events"]}))
        groups = {}
        timestamps = {}
        for event in metrics["events"]:
            groups.setdefault(event["transactionHash"], []).append(event)
            block = event["blockNumber"]
            if block not in timestamps:
                header = ctx.header(block)
                if header["hash"] != event["blockHash"]:
                    raise RpcError("Standard-bond evidence header identity mismatch", kind="integrity")
                timestamps[block] = header["timestamp"]
                historical.add(block)
        for tx_hash, events in groups.items():
            row = {"transaction_hash": tx_hash, "block_number": events[0]["blockNumber"], "status": "not_checked"}
            metrics["receipts"].append(row)
            value = _read(ctx, "receipt", lambda: reconcile_receipt(ctx.receipt(tx_hash), events, routes, source))
            row.update(value or {"status": "unavailable"})
            ctx.checkpoint()
        for row in metrics["epochs"]:
            low, high = row["block_range"]
            events = [event for event in metrics["events"] if low <= event["blockNumber"] <= high]
            receipts = [receipt for receipt in metrics["receipts"] if low <= receipt["block_number"] <= high]
            row["transaction_hashes"] = sorted({event["transactionHash"] for event in events})
            sales = [event for event in events if event["event"] == "BondCreated"]
            row["observed_subtotal"] = _observed_totals(sales, receipts)
            if row["opening_state"] is None or row["closing_state"] is None:
                continue
            model = reconstruct_epoch(events, *row["opening_state"], row["start_timestamp"], timestamps)
            row["reconstruction"] = {key: value for key, value in model.items() if key != "block_states"}
            row["state_checks"] = []
            for block, expected in model["block_states"].items():
                observed = _read(ctx, "post_block_state", lambda: ctx.calls([
                    (net, source["token_abi"], "totalSupply", ()),
                    (bond, source["abi"], "payoutInEpoch", (row["epoch"],))], block=block))
                row["state_checks"].append({"block": block, "expected_supply": str(expected["supply"]),
                                             "expected_payout": str(expected["used"]), "observed": observed,
                                             "matches": observed == [expected["supply"], expected["used"]]})
                ctx.checkpoint()
            row["closing_state_matches"] = row["closing_state"] == [model["closing_supply"], model["closing_used"]]
            row["reconstruction_complete"] = row["closing_state_matches"] and all(check["matches"] for check in row["state_checks"])
            ctx.checkpoint()
        coverage["historical_header_rechecks"] = []
        ctx.headers(sorted(historical), fresh=True)
        for block in sorted(historical):
            original = ctx.header(block)
            coverage["historical_header_rechecks"].append({"block": block, "hash": original["hash"], "confirmed": True})
        coverage["historical_headers_confirmed"] = True
    finally:
        prepare_result(ctx.result)


def summarize(text, checkpoint_status):
    result = json.loads(text)
    metrics = result.get("metrics", {})
    for key in ("events", "receipts", "bindings", "implementations"):
        metrics.pop(key, None)
    for epoch in metrics.get("epochs", []):
        for key in ("reconstruction", "transaction_hashes", "state_checks"):
            epoch.pop(key, None)
    coverage = result.get("coverage", {})
    rechecks = coverage.pop("historical_header_rechecks", [])
    coverage["historical_header_recheck_count"] = len(rechecks)
    result.update(detail="summary", checkpoint_status=checkpoint_status)
    return serialize_result(result)

"""Fresh, bounded PremiumSeller event accounting and receipt-local remittances."""

import hashlib
import json
from fractions import Fraction

from netstack_core import (ZERO, TRANSFER_TOPIC, RpcError, _address, _quantity,
                           amount, decode_event, load_json, ratio, resolve_routes,
                           serialize_result, topic)

SALE_COVERAGE = "premium_sales"
BINDINGS = (("net", "net"), ("usdg", "usdg"), ("router", "router"),
            ("pairContract", "pair"), ("treasury", "treasury"),
            ("oracle", "oracle"), ("genesisBond", "genesis"))


def quantity(raw, decimals, unit):
    return {"raw": str(raw), "decimals": decimals, "unit": unit,
            "formatted": amount(raw, decimals)}


def price(net, usdg):
    # USDG6 / NET9, expressed in whole USDG per whole gross NET sold.
    return ratio(Fraction(usdg * 1000, net)) if net else None


def event_key(event):
    return event["transactionHash"], event["logIndex"]


def sale_row(event):
    net, usdg = event["values"]["netSold"], event["values"]["usdgSweptRaw"]
    return {"transaction_hash": event["transactionHash"], "log_index": event["logIndex"],
            "block_number": event["blockNumber"], "block_hash": event["blockHash"],
            "gross_net_sold": quantity(net, 9, "NET"),
            "event_proceeds": quantity(usdg, 6, "USDG"),
            "realized_price_usdg_per_gross_net": price(net, usdg),
            "receipt_status": "not_checked", "confirmed_remittance": None,
            "pool_net_transfer": None}


def reconcile_receipt(receipt, scanned, routes, source):
    """Partition by PremiumSold boundaries, never reuse a tx-wide transfer sum.

    Context.receipt validates every raw identity and log before this function.
    This additional check binds each scanned event to that successful receipt.
    """
    seller, usdg, treasury, net, pair = (routes[key]["address"] for key in
                                       ("seller", "usdg", "treasury", "net", "pair"))
    if _quantity(receipt["status"]) != 1:
        raise RpcError("PremiumSold belongs to an unsuccessful receipt", kind="integrity")
    identity = (_quantity(receipt["blockNumber"]), receipt["blockHash"].lower(),
                receipt["transactionHash"].lower(), _quantity(receipt["transactionIndex"]))
    sale_topic = next(topic(item) for item in source["abi"] if item.get("name") == "PremiumSold")
    sales, transfers = [], []
    for raw in receipt["logs"]:
        if not raw["topics"]:
            continue
        emitter = _address(raw["address"])
        selector = raw["topics"][0].lower()
        if emitter == seller and selector == sale_topic:
            sales.append(decode_event(raw, source["abi"]))
        elif emitter in (usdg, net) and selector == TRANSFER_TOPIC:
            transfers.append(decode_event(raw, source["token_abi"]))
    sales.sort(key=lambda row: row["logIndex"])
    transfers.sort(key=lambda row: row["logIndex"])
    indexed = {event_key(row): row for row in sales}
    for event in scanned:
        if (event["blockNumber"], event["blockHash"], event["transactionHash"], event["transactionIndex"]) != identity:
            raise RpcError("Sale and receipt block or transaction identity differ", kind="integrity")
        if indexed.get(event_key(event)) != event:
            raise RpcError("Scanned sale is absent from or differs from its receipt", kind="integrity")
    remittances = [row for row in transfers if row["address"] == usdg and
                   row["values"]["from"] == seller and row["values"]["to"] == treasury]
    reconciled, used, previous = {}, set(), -1
    for event in sales:
        candidates = [row for row in remittances if previous < row["logIndex"] < event["logIndex"]]
        status = "matched"
        if not candidates:
            status = "missing_remittance"
        elif len(candidates) != 1:
            status = "ambiguous_remittance_segment"
        elif candidates[0]["values"]["value"] != event["values"]["usdgSweptRaw"]:
            status = "mismatched_remittance"
        details = {"receipt_status": status, "confirmed_remittance": None,
                   "remittance_candidates": [{"log_index": row["logIndex"],
                                               "amount": quantity(row["values"]["value"], 6, "USDG")}
                                              for row in candidates],
                   "pool_net_transfer": None}
        if status == "matched":
            transfer = candidates[0]
            used.add(transfer["logIndex"])
            details["confirmed_remittance"] = quantity(transfer["values"]["value"], 6, "USDG")
            details["remittance_log_index"] = transfer["logIndex"]
        net_rows = [row for row in transfers if row["address"] == net and
                    previous < row["logIndex"] < event["logIndex"]]
        mints = [row for row in net_rows if row["values"]["from"] == ZERO and
                 row["values"]["to"] == seller]
        inputs = [row for row in net_rows if row["values"]["from"] == seller and
                  row["values"]["to"] == pair]
        if (len(mints) == len(inputs) == 1 and
                mints[0]["values"]["value"] == event["values"]["netSold"] and
                mints[0]["logIndex"] < inputs[0]["logIndex"]):
            details["pool_net_transfer"] = quantity(inputs[0]["values"]["value"], 9, "NET")
        outputs = [row for row in transfers if row["address"] == usdg and
                   previous < row["logIndex"] < event["logIndex"] and
                   row["values"]["from"] == pair and row["values"]["to"] == seller]
        details["pair_usdg_output"] = (
            quantity(outputs[0]["values"]["value"], 6, "USDG") if len(outputs) == 1 else None)
        details["pair_output_matches_event"] = (
            len(outputs) == 1 and outputs[0]["values"]["value"] == event["values"]["usdgSweptRaw"])
        if len(sales) > 1:
            # lastExecuteAt is set before external calls. One block timestamp
            # cannot satisfy the reviewed one-hour interval twice in a tx.
            details["segment_match_status"] = details["receipt_status"]
            details["receipt_status"] = "impossible_multiple_sales"
            details["confirmed_remittance"] = None
        reconciled[event_key(event)] = details
        previous = event["logIndex"]
    missing = [row["logIndex"] for row in sales if event_key(row) not in {event_key(e) for e in scanned}]
    unmatched = [{"log_index": row["logIndex"], "amount": quantity(row["values"]["value"], 6, "USDG")}
                 for row in remittances if row["logIndex"] not in used]
    return reconciled, {"transaction_hash": identity[2], "status": "checked",
                        "receipt_sale_count": len(sales), "missing_scanned_sale_log_indices": missing,
                        "implementation_invariant": "impossible_multiple_sales" if len(sales) > 1 else "consistent",
                        "unmatched_seller_treasury_transfers": unmatched}


def prepare_result(result):
    """Compute totals from retained evidence, including after stop/recheck failure."""
    metrics = result.get("metrics", {})
    if "sales" not in metrics:
        return
    coverage = result["coverage"]
    scan = coverage.get(SALE_COVERAGE, {})
    rows = metrics["sales"]
    net = sum(int(row["gross_net_sold"]["raw"]) for row in rows)
    proceeds = sum(int(row["event_proceeds"]["raw"]) for row in rows)
    confirmed = [row for row in rows if row["receipt_status"] == "matched"]
    remitted = sum(int(row["confirmed_remittance"]["raw"]) for row in confirmed)
    prices = [Fraction(int(row["event_proceeds"]["raw"]) * 1000,
                       int(row["gross_net_sold"]["raw"])) for row in rows if int(row["gross_net_sold"]["raw"])]
    valid = result.get("snapshot", {}).get("recheck_status") == "confirmed"
    bound = metrics.get("implementation", {}).get("status") == "matched" and metrics.get("bindings_complete", False)
    observed = {"sale_count": len(rows), "gross_net_sold": quantity(net, 9, "NET"),
                "event_proceeds": quantity(proceeds, 6, "USDG"),
                "weighted_realized_price_usdg_per_gross_net": price(net, proceeds),
                "realized_price_range_usdg_per_gross_net":
                    {"min": ratio(min(prices)), "max": ratio(max(prices))} if prices else None}
    receipts = metrics["receipts"]
    consistent = (not any(error.get("kind") == "integrity" for error in result.get("errors", [])) and
                  all(not row["missing_scanned_sale_log_indices"] and
                      row.get("implementation_invariant") != "impossible_multiple_sales" for row in receipts))
    last_execution = coverage.get("last_execution_reconciliation", {})
    event_complete = bool(bound and valid and consistent and scan.get("event_coverage_complete") and
                          last_execution.get("collection_complete"))
    receipt_complete = bool(event_complete and len(confirmed) == len(rows) and
                            all(row["status"] == "checked" and not row["missing_scanned_sale_log_indices"] and
                                not row["unmatched_seller_treasury_transfers"] for row in receipts))
    # Empty observations only become proven zeros after a complete served scan.
    remittance = {"sale_count": len(confirmed), "usdg_to_treasury": quantity(remitted, 6, "USDG")}
    lifetime = coverage.get("history", {}).get("includes_creation", False)
    metrics["event_reported"] = {"observed_subtotal": observed,
                                  "requested_window_total": observed if event_complete else None,
                                  "lifetime_total": observed if event_complete and lifetime else None,
                                  "collection_complete": event_complete}
    metrics["receipt_confirmed"] = {"observed_subtotal": remittance,
                                     "requested_window_total": remittance if receipt_complete else None,
                                     "lifetime_total": remittance if receipt_complete and lifetime else None,
                                     "collection_complete": receipt_complete}
    coverage["receipt_reconciliation"] = {"collection_complete": receipt_complete,
                                            "scanned_sale_count": len(rows), "matched_sale_count": len(confirmed),
                                            "transactions_checked": sum(row["status"] == "checked" for row in receipts)}
    coverage["collection_complete"] = bool(event_complete and receipt_complete)


def _bindings(ctx, routes, source):
    metrics = ctx.result["metrics"]
    seller = routes["seller"]["address"]
    raw = bytes.fromhex(ctx.code(seller)[2:])
    evidence = source["runtime_evidence"]
    matched = len(raw) == evidence["runtime_bytes"] and hashlib.sha256(raw).hexdigest() == evidence["runtime_sha256"]
    metrics["implementation"] = {"address": seller, "block": ctx.block,
                                  "runtime_sha256": hashlib.sha256(raw).hexdigest(), "runtime_bytes": len(raw),
                                  "status": "matched" if matched else "unsupported",
                                  "source_id": source["source_id"], "historical_implementation_audit": "not_performed"}
    if not matched:
        raise RpcError("Pinned PremiumSeller runtime is not the reviewed implementation", kind="unsupported")
    for getter, role in BINDINGS:
        value = _address(ctx.call(seller, source["abi"], getter))
        metrics["bindings"].append({"function": getter, "expected": routes[role]["address"],
                                     "observed": value, "block": ctx.block})
        if value != routes[role]["address"]:
            raise RpcError("Pinned PremiumSeller dependency differs from canonical route", kind="integrity")
        if ctx.code(value) == "0x":
            raise RpcError("PremiumSeller dependency has no code at pinned block", kind="integrity")
    for role, expected in (("net", 9), ("usdg", 6)):
        observed = ctx.call(routes[role]["address"], source["token_abi"], "decimals")
        if observed != expected:
            raise RpcError("PremiumSeller token decimal binding differs", kind="integrity")
    metrics["bindings_complete"] = True
    metrics["last_execute_at"] = ctx.call(seller, source["abi"], "lastExecuteAt")


def _reconcile_last_execution(ctx, start):
    """An empty/omitted event response cannot overrule contradictory state."""
    metrics = ctx.result["metrics"]
    last = metrics["last_execute_at"]
    rows = metrics["sales"]
    evidence = {"last_execute_at": last, "collection_complete": False,
                "meaning": "Activity-history consistency check, not execution eligibility or inactive status."}
    ctx.result["coverage"]["last_execution_reconciliation"] = evidence
    if not ctx.result["coverage"].get(SALE_COVERAGE, {}).get("event_coverage_complete"):
        evidence["status"] = "scan_incomplete"
        return
    if last > ctx.timestamp:
        evidence["status"] = "last_execution_after_snapshot"
    elif rows:
        latest = max(rows, key=lambda row: (row["block_number"], row["log_index"]))
        header = ctx.header(latest["block_number"])
        if header["hash"] != latest["block_hash"]:
            raise RpcError("Latest sale block header differs from event identity", kind="integrity")
        evidence.update(latest_observed_sale_block=latest["block_number"],
                        latest_observed_sale_timestamp=header["timestamp"])
        if last and header["timestamp"] == last:
            evidence.update(status="latest_sale_matches_state", collection_complete=True)
        else:
            evidence["status"] = "latest_sale_missing_or_inconsistent"
    elif last == 0:
        evidence.update(status="no_recorded_execution_and_empty_served_range", collection_complete=True)
    elif (not ctx.result["coverage"]["history"]["includes_creation"] and
          last < ctx.header(start)["timestamp"]):
        evidence.update(status="last_execution_before_requested_window", collection_complete=True)
    else:
        evidence["status"] = "recorded_execution_missing_from_served_range"
    if not evidence["collection_complete"]:
        ctx.result["errors"].append({"scope": "last_execution_reconciliation", "kind": "evidence",
                                     "message": "PremiumSold history conflicts with pinned lastExecuteAt; no complete totals."})


def run(ctx, args):
    routes = resolve_routes("premiumseller")
    source = load_json(routes["_route"]["interface"])
    metrics = ctx.result["metrics"]
    metrics.update(seller=routes["seller"]["address"], treasury=routes["treasury"]["address"],
                   source_id=source["source_id"], sales=[], receipts=[], bindings=[], bindings_complete=False)
    coverage = ctx.result["coverage"]
    coverage["collection_complete"] = False
    ctx.result["not_proven"].extend([
        "Amounts are NET9 and USDG6, not native fiat USD; USDG dollar parity is not established.",
        "PremiumSold reports gross minted NET input and swap USDG balance delta, not net NET received by the pool after possible transfer tax.",
        "Pre-existing seller USDG is not swept. Only receipt-local USDG Transfers from seller to canonical Treasury are matched; unrelated Treasury flows are excluded.",
        "Prices use actual event proceeds divided by gross NET, never today's mark or an unweighted mean; no gas, profit, revenue recognition or RFV delta is assumed.",
        "The pinned runtime/dependency match is not a historical implementation or token-behavior audit; historical event interpretation assumes the reviewed semantics.",
        "Log completeness assumes the provider did not silently omit events. Receipts can expose missing events in observed transactions, not transactions entirely omitted by the provider.",
        "Receipt-confirmed totals cover matched PremiumSold remittances only, not every Treasury inflow or an independent lifetime USDG transfer census.",
        "NET pool transfer evidence is receipt-local ERC20 event evidence, not an independent pair balance or invariant audit.",
        "Matched remittances corroborate gross USDG Transfer amounts, not a net Treasury balance change. Pair-to-seller output evidence is reported separately.",
        "The strict TWAP > 2x backing trigger and rounded 99% TWAP floor do not guarantee realized price > 2x backing or > 2 USDG.",
        "Empty logs do not establish inactive, unused or dead status. active() is execution eligibility, not activity history.",
    ])
    ctx.checkpoint()
    try:
        _bindings(ctx, routes, source)
        creation = ctx.deployment(routes["seller"])
        creation_header = ctx.header(creation)
        start = creation
        requested_timestamp = None
        if args.since_days is not None:
            # Exact comparison against the user-visible decimal day value.
            cutoff = max(Fraction(0), Fraction(ctx.timestamp) - Fraction(str(args.since_days)) * 86400)
            requested_timestamp = ratio(cutoff)
            if cutoff > creation_header["timestamp"]:
                # Find the block before the first eligible second. Several L2
                # blocks can share the cutoff timestamp; include all of them.
                prior_second = (cutoff.numerator - 1) // cutoff.denominator
                start = max(creation, ctx.find_block(prior_second) + 1)
        coverage["history"] = {"creation_block": creation, "requested_range": [start, ctx.block],
                                "creation_block_hash": creation_header["hash"],
                                "creation_timestamp": creation_header["timestamp"],
                                "since_days": args.since_days, "cutoff_timestamp_exact": requested_timestamp,
                                "includes_creation": start == creation,
                                "scan_order": "newest_first"}
        seen = {}
        for page in ctx.logs(SALE_COVERAGE, routes["seller"]["address"], source["abi"],
                             ["PremiumSold"], start, ctx.block, newest_first=True):
            grouped = {}
            for event in page:
                key = event_key(event)
                if key in seen:
                    if seen[key][0] != event:
                        raise RpcError("Conflicting canonical sale identity", kind="integrity")
                    continue
                row = sale_row(event)
                seen[key] = (event, row)
                metrics["sales"].append(row)
                grouped.setdefault(event["transactionHash"], []).append(event)
            # Publish the page's event subtotal before any receipt request can stop.
            ctx.checkpoint()
            for tx_hash, events in grouped.items():
                receipt_row = {"transaction_hash": tx_hash, "status": "not_checked",
                               "missing_scanned_sale_log_indices": [], "unmatched_seller_treasury_transfers": []}
                metrics["receipts"].append(receipt_row)
                try:
                    receipt = ctx.receipt(tx_hash)
                    reconciled, receipt_evidence = reconcile_receipt(receipt, events, routes, source)
                    receipt_row.update(receipt_evidence)
                    for event in events:
                        seen[event_key(event)][1].update(reconciled[event_key(event)])
                except RpcError as error:
                    receipt_row.update(status="failed", failure_kind=error.kind)
                    if error.kind in ("permission", "integrity"):
                        raise
                    ctx.result["errors"].append({"scope": "sale_receipt", "kind": error.kind, "message": str(error)})
                ctx.checkpoint()
        _reconcile_last_execution(ctx, start)
    finally:
        prepare_result(ctx.result)


def summarize(text, checkpoint_status):
    result = json.loads(text)
    metrics = result.get("metrics", {})
    result["metrics"] = {key: value for key, value in metrics.items() if key not in ("sales", "receipts", "bindings")}
    result["detail"] = "summary"
    result["checkpoint_status"] = checkpoint_status
    # Projection must not recompute totals without the omitted detailed evidence.
    return serialize_result(result)

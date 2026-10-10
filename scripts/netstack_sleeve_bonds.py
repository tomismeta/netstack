"""Pinned SleeveBondDesk obligations and optional fresh subscription evidence."""
import hashlib
import json

from netstack_core import (TRANSFER_TOPIC, RpcError, _address, _quantity, amount,
                           decode_event, load_json, resolve_routes, serialize_result, topic)

HISTORY = "sleeve_bond_events"
BINDINGS = (("net", "net"), ("usdg", "usdg"), ("treasury", "treasury"),
            ("pairOracle", "oracle"), ("manager", "manager"), ("sleeve", "sleeve"),
            ("feedAdapter", "feed_adapter"), ("routerSource", "router_source"))


def quantity(raw, decimals, unit):
    return {"raw": str(raw), "decimals": decimals, "unit": unit,
            "formatted": amount(raw, decimals)}


def note_row(note, index, timestamp):
    payout, claimed, start, end = (note[key] for key in ("payout", "claimed", "start", "end"))
    if end <= start or start > timestamp or claimed > payout:
        raise RpcError("Invalid Sleeve note state at snapshot", kind="integrity")
    vested = payout if timestamp >= end else payout * (timestamp - start) // (end - start)
    if claimed > vested:
        raise RpcError("Sleeve note claims exceed vested entitlement", kind="integrity")
    return {"note_id": index, "start": start, "end": end,
            "gross_entitlement": quantity(payout, 9, "NET"),
            "gross_claimed": quantity(claimed, 9, "NET"),
            "outstanding": quantity(payout - claimed, 9, "NET"),
            "claimable_now": quantity(vested - claimed, 9, "NET")}


def event_key(event):
    return event["transactionHash"], event["logIndex"]


def reconcile_receipt(receipt, scanned, routes, source):
    """Receipt-local gross transfers, never Treasury remittance or balance delta."""
    if _quantity(receipt["status"]) != 1:
        raise RpcError("Sleeve subscription belongs to a failed receipt", kind="integrity")
    equity_tokens = {event["values"]["rwaToken"] for event in scanned}
    identity = (_quantity(receipt["blockNumber"]), receipt["blockHash"].lower(),
                receipt["transactionHash"].lower(), _quantity(receipt["transactionIndex"]))
    desk, sleeve, usdg = (routes[key]["address"] for key in ("desk", "sleeve", "usdg"))
    bond_topic = next(topic(item) for item in source["abi"] if item.get("name") == "DeskBond")
    bonds, transfers = [], []
    for raw in receipt["logs"]:
        if not raw["topics"]:
            continue
        if _address(raw["address"]) == desk and raw["topics"][0].lower() == bond_topic:
            bonds.append(decode_event(raw, source["abi"]))
        elif _address(raw["address"]) in equity_tokens | {usdg} and raw["topics"][0].lower() == TRANSFER_TOPIC:
            transfers.append(decode_event(raw, source["token_abi"]))
    bonds.sort(key=lambda row: row["logIndex"])
    transfers.sort(key=lambda row: row["logIndex"])
    indexed = {event_key(row): row for row in bonds}
    for event in scanned:
        if (event["blockNumber"], event["blockHash"], event["transactionHash"], event["transactionIndex"]) != identity:
            raise RpcError("Sleeve event and receipt identity differ", kind="integrity")
        if indexed.get(event_key(event)) != event:
            raise RpcError("Sleeve event missing from or differs from receipt", kind="integrity")
    output, previous = {}, -1
    for event in bonds:
        values = event["values"]
        segment = [row for row in transfers if previous < row["logIndex"] < event["logIndex"]]
        inbound = [row for row in segment if row["address"] == usdg and row["values"]["to"] == desk]
        outbound = [row for row in segment if row["address"] == usdg and row["values"]["from"] == desk]
        equities = [row for row in segment if row["address"] == values["rwaToken"] and
                    row["values"]["from"] == desk and row["values"]["to"] == sleeve]
        funded, returns_match = {}, True
        for row in segment:
            if row["address"] != usdg:
                continue
            leg = row["values"]
            if leg["from"] == desk:
                funded[leg["to"]] = funded.get(leg["to"], 0) + leg["value"]
            elif leg["to"] == desk and row is not inbound[0]:
                available = funded.get(leg["from"], 0)
                if leg["from"] == sleeve or leg["value"] > available:
                    returns_match = False
                else:
                    funded[leg["from"]] = available - leg["value"]
        capital_matches = bool(
            inbound and inbound[0]["values"]["from"] != desk and
            inbound[0]["values"]["value"] == values["usdgIn"] and returns_match and
            all(row["logIndex"] > inbound[0]["logIndex"] for row in outbound) and
            sum(row["values"]["value"] for row in outbound) ==
            sum(row["values"]["value"] for row in inbound))
        equity_matches = len(equities) == 1 and equities[0]["values"]["value"] == values["rwaOut"]
        # More than one fill can be called sequentially. A segment is not a trace:
        # unrelated flows in the same segment remain explicitly ambiguous.
        output[event_key(event)] = {
            "status": "matched_gross_transfers" if capital_matches and equity_matches else "unresolved_transfers",
            "subscription_input_matches": capital_matches,
            "equity_transfer_matches_event": equity_matches,
            "return_legs_match_prior_outflows": returns_match,
            "usdg_returns_to_desk": [
                {"from": row["values"]["from"], "log_index": row["logIndex"],
                 "amount": quantity(row["values"]["value"], 6, "USDG")}
                for row in inbound[1:]],
            "usdg_outgoing": [{"to": row["values"]["to"], "log_index": row["logIndex"],
                                "amount": quantity(row["values"]["value"], 6, "USDG")}
                               for row in outbound],
            "residual_usdg_to_sleeve": quantity(sum(row["values"]["value"] for row in outbound
                                                     if row["values"]["to"] == sleeve), 6, "USDG")
                if capital_matches else None,
            "equity_token": values["rwaToken"],
            "gross_equity_transfer_raw": str(equities[0]["values"]["value"]) if len(equities) == 1 else None,
            "meaning": "Receipt ERC20 amounts; not net custody balance changes, execution traces or Treasury revenue."}
        previous = event["logIndex"]
    missing = [row["logIndex"] for row in bonds if event_key(row) not in {event_key(e) for e in scanned}]
    return output, missing


def prepare_result(result):
    metrics, coverage = result.get("metrics", {}), result.get("coverage", {})
    if "desk" not in metrics:
        return
    valid = result.get("snapshot", {}).get("recheck_status") == "confirmed"
    bound = metrics.get("bindings_complete", False)
    clean = not any(row.get("kind") == "integrity" for row in result.get("errors", []))
    snapshot = metrics.get("current", {})
    snapshot_complete = bool(snapshot.get("reads_complete") and valid and bound and clean)
    snapshot["collection_complete"] = snapshot_complete
    account = metrics.get("account")
    if account is not None:
        account["collection_complete"] = bool(account.get("reconciled") and valid and bound and clean)
    history_complete = metrics.get("history", {}).get("collection_complete", False)
    if "events" in metrics:
        events = metrics["events"]
        bonds = [row for row in events if row["event"] == "DeskBond"]
        redeemed = [row for row in events if row["event"] == "DeskRedeemed"]
        equities = {}
        for row in bonds:
            token = row["values"]["rwaToken"]
            equities[token] = equities.get(token, 0) + row["values"]["rwaOut"]
        subtotal = {"subscription_count": len(bonds),
                    "subscriber_capital": quantity(sum(row["values"]["usdgIn"] for row in bonds), 6, "USDG"),
                    "gross_existing_net_entitlement": quantity(sum(row["values"]["payout"] for row in bonds), 9, "NET"),
                    "gross_net_claimed": quantity(sum(row["values"]["payout"] for row in redeemed), 9, "NET"),
                    "equity_received_raw_by_token": {token: str(raw) for token, raw in equities.items()},
                    "meaning": "Observed event subtotal only; equity raw units are token-specific, not UI shares or dollars."}
        reconciliation = coverage.get("history_reconciliation", {})
        history_complete = bool(snapshot_complete and coverage.get(HISTORY, {}).get("event_coverage_complete") and
                                reconciliation.get("reconciled") and bonds)
        receipt_complete = bool(history_complete and all(row.get("receipt", {}).get("status") == "matched_gross_transfers"
                                                        for row in bonds))
        matched_receipts = [row["receipt"] for row in bonds
                            if row.get("receipt", {}).get("status") == "matched_gross_transfers"]
        destinations = {}
        for receipt in matched_receipts:
            for transfer in receipt["usdg_outgoing"]:
                address = transfer["to"]
                destinations[address] = destinations.get(address, 0) + int(transfer["amount"]["raw"])
        routing = {
            "matched_subscription_count": len(matched_receipts),
            "gross_usdg_outgoing_by_destination": {
                address: quantity(raw, 6, "USDG") for address, raw in destinations.items()},
            "residual_usdg_to_sleeve": quantity(sum(
                int(row["residual_usdg_to_sleeve"]["raw"]) for row in matched_receipts), 6, "USDG"),
            "meaning": "Matched receipt gross transfers only; destinations are not Treasury revenue labels or net custody changes."}
        metrics["history"] = {"observed_subtotal": subtotal,
                              "lifetime_event_total": subtotal if history_complete else None,
                              "collection_complete": history_complete,
                              "receipt_collection_complete": receipt_complete,
                              "treasury_remittance": None}
        metrics["history"]["receipt_routing"] = {
            "observed_subtotal": routing,
            "lifetime_total": routing if receipt_complete else None}
        coverage["receipt_reconciliation"] = {"collection_complete": receipt_complete,
                                              "meaning": "Subscription transfers only; redemption events are gross claim accounting, not recipient net transfers."}
    requested = coverage.get("requested_scope", {})
    coverage["collection_complete"] = bool(snapshot_complete and
        (not requested.get("account") or account and account.get("collection_complete")) and
        (not requested.get("history") or history_complete and metrics.get("history", {}).get("receipt_collection_complete")))
    requested["collection_complete"] = coverage["collection_complete"]


def _snapshot(ctx, routes, source):
    metrics, desk = ctx.result["metrics"], routes["desk"]["address"]
    raw = bytes.fromhex(ctx.code(desk)[2:])
    evidence = source["runtime_evidence"]
    digest = hashlib.sha256(raw).hexdigest()
    matched = len(raw) == evidence["runtime_bytes"] and digest == evidence["runtime_sha256"]
    metrics["implementation"] = {"runtime_bytes": len(raw), "runtime_sha256": digest,
                                 "status": "matched" if matched else "unsupported"}
    if not matched:
        raise RpcError("Sleeve desk runtime differs from reviewed implementation", kind="unsupported")
    for getter, role in BINDINGS:
        value = _address(ctx.call(desk, source["abi"], getter))
        metrics["bindings"].append({"function": getter, "address": value})
        if value != routes[role]["address"]:
            raise RpcError("Sleeve dependency differs from canonical binding", kind="integrity")
    for role, expected in (("net", 9), ("usdg", 6)):
        if ctx.call(routes[role]["address"], source["token_abi"], "decimals") != expected:
            raise RpcError("Sleeve token decimals differ from reviewed units", kind="integrity")
    metrics["bindings_complete"] = True
    current = metrics["current"]
    for name in ("inventory", "owedNet", "inventoryMax", "bHwm", "deskDiscountBps", "halted", "VEST",
                 "INVENTORY_HARD_CAP", "MAX_DISCOUNT_BPS", "MAX_ORACLE_DEV_BPS", "MIN_PREMIUM_WAD"):
        current[name] = ctx.call(desk, source["abi"], name)
    current["desk_net_balance"] = ctx.call(routes["net"]["address"], source["token_abi"], "balanceOf", [desk])
    required = current["inventory"] + current["owedNet"]
    current["gross_outstanding_claims"] = quantity(current["owedNet"], 9, "NET")
    current["unallocated_inventory"] = quantity(current["inventory"], 9, "NET")
    current["net_custody"] = quantity(current["desk_net_balance"], 9, "NET")
    current["custody_surplus_or_shortfall"] = quantity(current["desk_net_balance"] - required, 9, "NET")
    current["custody_covers_inventory_and_claims"] = current["desk_net_balance"] >= required
    current["menu"] = ctx.call(desk, source["abi"], "menu")
    current["menu_length"] = ctx.call(desk, source["abi"], "menuLength")
    if len(current["menu"]) != current["menu_length"]:
        raise RpcError("Sleeve menu length differs from returned menu", kind="integrity")
    current["reads_complete"] = True


def _account(ctx, args, routes, source):
    desk, account = routes["desk"]["address"], _address(args.account)
    report = {"address": account, "scope": "selected_account_only", "notes": [], "reconciled": False}
    ctx.result["metrics"]["account"] = report
    count = ctx.call(desk, source["abi"], "noteCount", [account])
    report["note_count"] = count
    pending = ctx.call(desk, source["abi"], "pendingFor", [account])
    report["pending_for"] = {"outstanding": quantity(pending["totalPending"], 9, "NET"),
                             "claimable_now": quantity(pending["claimableNow"], 9, "NET")}
    for index in range(min(count, args.max_notes)):
        note = ctx.call(desk, source["abi"], "noteAt", [account, index])
        report["notes"].append(note_row(note, index, ctx.timestamp))
        ctx.checkpoint()
    outstanding = sum(int(row["outstanding"]["raw"]) for row in report["notes"])
    claimable = sum(int(row["claimable_now"]["raw"]) for row in report["notes"])
    report["enumeration_complete"] = len(report["notes"]) == count
    if report["enumeration_complete"]:
        if outstanding != pending["totalPending"] or claimable != pending["claimableNow"]:
            raise RpcError("Sleeve notes disagree with pendingFor", kind="integrity")
        report["reconciled"] = True
    else:
        ctx.result["not_proven"].append("Selected account note enumeration capped; pendingFor is separate aggregate state, not complete note discovery.")


def _history(ctx, routes, source):
    metrics, coverage = ctx.result["metrics"], ctx.result["coverage"]
    desk = routes["desk"]["address"]
    creation = ctx.deployment(routes["desk"])
    ctx.header(creation)
    coverage["history_range"] = {"creation_block": creation, "requested_range": [creation, ctx.block],
                                 "includes_creation": True, "scan_order": "newest_first"}
    metrics["events"] = []
    seen = {}
    for page in ctx.logs(HISTORY, desk, source["abi"], ["DeskBond", "DeskRedeemed", "InventoryDeposited"],
                         creation, ctx.block, newest_first=True):
        for event in page:
            key = event_key(event)
            if key in seen:
                if seen[key] != event:
                    raise RpcError("Conflicting Sleeve event identity", kind="integrity")
                continue
            seen[key] = event
            metrics["events"].append(dict(event))
        ctx.checkpoint()
    grouped = {}
    for event in metrics["events"]:
        if event["event"] == "DeskBond":
            grouped.setdefault(event["transactionHash"], []).append(event)
    for tx_hash, events in grouped.items():
        receipt = ctx.receipt(tx_hash)
        reconciled, missing = reconcile_receipt(receipt, events, routes, source)
        if missing:
            raise RpcError("Receipt exposes missing Sleeve subscription events", kind="integrity")
        for event in events:
            event["receipt"] = reconciled[event_key(event)]
        ctx.checkpoint()
    bonds = [row for row in metrics["events"] if row["event"] == "DeskBond"]
    claims = [row for row in metrics["events"] if row["event"] == "DeskRedeemed"]
    evidence = {"reconciled": False, "accounts": [], "empty_logs_mean": "unknown_history_not_inactive"}
    coverage["history_reconciliation"] = evidence
    counts = {}
    for event in bonds:
        account = event["values"]["to"]
        counts[account] = counts.get(account, 0) + 1
        if event["values"]["fee"] != 0:
            raise RpcError("Sleeve bond event contradicts zero-fee implementation", kind="integrity")
    for account, observed in sorted(counts.items()):
        count = ctx.call(desk, source["abi"], "noteCount", [account])
        evidence["accounts"].append({"address": account, "observed_subscriptions": observed, "note_count": count})
        ctx.checkpoint()
    expected = sum(row["values"]["payout"] for row in bonds) - sum(row["values"]["payout"] for row in claims)
    evidence["event_implied_outstanding"] = quantity(expected, 9, "NET")
    evidence["outstanding_matches_state"] = expected == metrics["current"]["owedNet"]
    evidence["discovered_note_counts_match"] = all(row["observed_subscriptions"] == row["note_count"] for row in evidence["accounts"])
    evidence["reconciled"] = bool(bonds and evidence["outstanding_matches_state"] and evidence["discovered_note_counts_match"])
    evidence["limits"] = "No global lifetime note counter or independent subscriber census. Entirely omitted fully-redeemed accounts can escape these checks; empty history never proves zero lifetime capital."


def run(ctx, args):
    routes = resolve_routes("sleeve-bonds")
    source = load_json(routes["_route"]["interface"])
    metrics = ctx.result["metrics"]
    metrics.update(desk=routes["desk"]["address"], source_id=source["source_id"],
                   bindings=[], bindings_complete=False, current={})
    ctx.result["coverage"]["requested_scope"] = {
        "scope": "current_global_obligations_with_optional_selected_account_and_lifetime_events",
        "snapshot": True, "account": args.account, "history": args.history, "collection_complete": False}
    ctx.result["not_proven"].extend([
        "Current owedNet is gross global NET obligation, not claimable-now, receiver net delivery or subscriber discovery.",
        "NET9 and USDG6 are token units, not fiat USD. Equity event amounts are raw token units; no UI multiplier or market valuation is applied.",
        "Pre-funded NET inventory does not prove where NET was bought or minted earlier. Subscription and claim do not mint or burn NET in the reviewed desk runtime.",
        "Subscription fee field is zero. USDG residual can go to Sleeve; no Treasury remittance, Core revenue or RFV increase is inferred.",
        "No cancellation or USDG refund entrypoint was established. Halt stops new bonds, not already-issued gross NET vesting rights.",
        "Sleeve holdings, Credit collateral/debt and managed authority are separate from this desk's inventory and claims; use existing RFV Sleeve custody reporting without adding them to Core RFV.",
        "Runtime and binding checks do not audit external token taxes, oracle correctness, Safe owners or historical implementations.",
        "History completeness is provider-served creation-to-snapshot coverage plus discovered-account counts and owedNet reconciliation, not an independent global transaction census.",
        "A complete receipt segment matches gross ERC20 events, not net balance changes; unrelated same-segment transfers may make attribution ambiguous.",
    ])
    ctx.checkpoint()
    try:
        _snapshot(ctx, routes, source)
        ctx.checkpoint()
        if args.account:
            _account(ctx, args, routes, source)
        if args.history:
            _history(ctx, routes, source)
    finally:
        prepare_result(ctx.result)


def summarize(text, checkpoint_status):
    result = json.loads(text)
    metrics = result.get("metrics", {})
    metrics.pop("events", None)
    metrics.pop("bindings", None)
    if metrics.get("account"):
        metrics["account"].pop("notes", None)
    result["detail"] = "summary"
    result["checkpoint_status"] = checkpoint_status
    return serialize_result(result)

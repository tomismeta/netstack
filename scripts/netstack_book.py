"""Pinned THE BOOK state and explicitly bounded event/receipt evidence."""

import hashlib
import json

from netstack_core import (ZERO, TRANSFER_TOPIC, RpcError, _address, _quantity,
                           amount, decode_event, load_json, resolve_routes,
                           serialize_result, topic)

EVENT_COVERAGE = "book_events"
EVENTS = ("MarketOpened", "BetPlaced", "FeeSplit", "Graded", "Settled", "Voided",
          "Cancelled", "Deposited", "Withdrawn", "HouseDeposited", "HouseWithdrawn", "Skimmed")
STATE = ("marketCount", "betCount", "halted", "potsOf", "freePot", "playerTotal",
         "manager", "grader", "minBetWs", "maxBetBps", "reserveRateBps")
BINDINGS = (("desk", "wsNet", "wsnet"), ("desk", "sNet", "snet"),
            ("desk", "net", "net"), ("desk", "managerSleeve", "sleeve"),
            ("zap", "desk", "desk"), ("zap", "wsNet", "wsnet"),
            ("zap", "sNet", "snet"), ("zap", "net", "net"), ("zap", "usdg", "usdg"))


def quantity(raw):
    return {"raw": str(raw), "decimals": 18, "unit": "wsNET", "formatted": amount(raw, 18)}


def _read(ctx, scope, fn):
    try:
        return fn()
    except RpcError as error:
        if error.kind in ("permission", "integrity"):
            raise
        ctx.result["errors"].append({"scope": scope, "kind": error.kind, "message": str(error)})
        return None


def select_ids(count, requested, limit):
    if type(limit) is not int or limit < 1:
        raise RpcError("Invalid bounded ID limit", kind="input")
    if any(type(value) is not int or not 1 <= value <= count for value in requested):
        raise RpcError("Requested Book ID is outside the pinned counter", kind="input")
    selected = sorted(set(requested)) if requested else list(range(max(1, count-limit+1), count+1))
    if len(selected) > limit:
        raise RpcError("Explicit Book IDs exceed the selected bound", kind="input")
    return selected


def bet_row(bet_id, value, market):
    state = market.get("state") if market else None
    result = market.get("result") if market else None
    if value["player"] == ZERO or not value["marketId"]:
        raise RpcError("Book counter includes a missing bet", kind="integrity")
    if value["settled"]:
        status = "settled_internal_credit"
    elif state == 1:
        status = "ungraded_locked"
    elif state in (2, 3):
        status = "decided_unsettled"
    else:
        status = "market_state_unknown"
    # This is an attributed client model, not a simulated call or verified claim.
    model = None
    if not value["settled"] and state in (2, 3) and result in (0, 1, 2):
        if result == 2:
            model = value["amount"]
        elif not value["riskOff"] and value["side"] in (0, 1):
            model = 2*value["amount"] if result == value["side"] else 0
    return {"bet_id": bet_id, "state": value, "status": status,
            "amount_basis": "risk_off_principal" if value["riskOff"] else "publisher_fee_net_risk_on_stake",
            "stored_settled_wager": quantity(value["wager"]) if value["settled"] else None,
            "stored_settled_payout": quantity(value["payout"]) if value["settled"] else None,
            "publisher_unsettled_credit_model": quantity(model) if model is not None else None,
            "claimable_verified": None,
            "model_limit": "No verified Solidity or nonbroadcast settlement simulation. Risk-off decided non-push payout requires exact rounding/fee implementation; remains unknown."}


def reconcile_receipt(receipt, scanned, routes, source):
    """Receipt-local token legs, without inventing bet-level revenue attribution."""
    if _quantity(receipt["status"]) != 1:
        raise RpcError("Book event in unsuccessful receipt", kind="integrity")
    identity = (_quantity(receipt["blockNumber"]), receipt["blockHash"].lower(),
                receipt["transactionHash"].lower(), _quantity(receipt["transactionIndex"]))
    desk, wsnet = routes["desk"]["address"], routes["wsnet"]["address"]
    selectors = {topic(item) for item in source["abi"]
                 if item.get("type") == "event" and item["name"] in EVENTS}
    receipt_events, transfers = [], []
    for raw in receipt["logs"]:
        if not raw["topics"]:
            continue
        emitter, selector = _address(raw["address"]), raw["topics"][0].lower()
        if emitter == desk and selector in selectors:
            receipt_events.append(decode_event(raw, source["abi"]))
        elif emitter == wsnet and selector == TRANSFER_TOPIC:
            transfers.append(decode_event(raw, source["token_abi"]))
    indexed = {row["logIndex"]: row for row in receipt_events}
    for row in scanned:
        if (row["blockNumber"], row["blockHash"], row["transactionHash"], row["transactionIndex"]) != identity:
            raise RpcError("Book receipt and event identity disagree", kind="integrity")
        if indexed.get(row["logIndex"]) != row:
            raise RpcError("Book event missing or different in receipt", kind="integrity")
    selected = {row["logIndex"] for row in scanned}
    missing = [row["logIndex"] for row in receipt_events if row["logIndex"] not in selected]
    legs = []
    for row in transfers:
        values = row["values"]
        if values["from"] == desk:
            role = next((name for name in ("sleeve", "treasury")
                         if values["to"] == routes[name]["address"]), "other_recipient")
            legs.append({"log_index": row["logIndex"], "direction": "out", "recipient_role": role,
                         "from": values["from"], "to": values["to"], "amount": quantity(values["value"])})
        elif values["to"] == desk:
            legs.append({"log_index": row["logIndex"], "direction": "in", "recipient_role": "desk_custody",
                         "from": values["from"], "to": values["to"], "amount": quantity(values["value"])})
    fees = sum(row["values"]["sleeveHalf"] for row in receipt_events if row["event"] == "FeeSplit")
    withdrawals = sum(row["values"]["amount"] for row in receipt_events
                      if row["event"] == "HouseWithdrawn" and row["values"]["to"] == routes["sleeve"]["address"])
    sleeve_out = sum(int(row["amount"]["raw"]) for row in legs
                     if row["direction"] == "out" and row["recipient_role"] == "sleeve")
    return {"transaction_hash": identity[2], "status": "checked", "legs": legs,
            "missing_scanned_event_log_indices": missing,
            "sleeve_allocation_plus_house_withdrawals": quantity(fees+withdrawals),
            "sleeve_outflow_matches_allocations_plus_withdrawals": sleeve_out == fees+withdrawals,
            "attribution": "Actual wsNET Transfer legs only. Aggregate agreement does not assign a transfer to a fee, prove net balance change, or make house withdrawals revenue."}


def _counter_reconciliation(events, baseline, current):
    if baseline is None or current is None:
        return {"complete": False, "status": "boundary_counters_unavailable"}
    details = {}
    for name, counter, key in (("BetPlaced", "betCount", "betId"), ("MarketOpened", "marketCount", "marketId")):
        ids = [int(row["values"][key]) for row in events if row["event"] == name]
        low, high = int(baseline[counter]), int(current[counter])
        consistent = high >= low and len(ids) == high-low and len(set(ids)) == len(ids)
        consistent = consistent and all(low < value <= high for value in ids)
        details[name] = {"before": low, "at_snapshot": high, "observed_count": len(ids), "matches": consistent}
    return {"complete": all(row["matches"] for row in details.values()), "status": "counter_comparison", "counters": details}


def prepare_result(result):
    metrics, coverage = result.get("metrics", {}), result.get("coverage", {})
    if "markets" not in metrics or "bets" not in metrics:
        return  # Initial Context or summary projection: never recompute absent rows as zero.
    valid = result.get("snapshot", {}).get("recheck_status") == "confirmed"
    safe = not any(row.get("kind") in ("permission", "integrity") for row in result.get("errors", []))
    snapshot_complete = bool(valid and safe and metrics.get("snapshot_reads_complete"))
    coverage["snapshot_scope_complete"] = snapshot_complete
    metrics["selected_bet_observations"] = {
        "count": len(metrics["bets"]),
        "settled_count": sum(row["state"]["settled"] for row in metrics["bets"]),
        "decided_unsettled_count": sum(row["status"] == "decided_unsettled" for row in metrics["bets"]),
        "stored_settled_payout_subtotal": quantity(sum(int(row["state"]["payout"]) for row in metrics["bets"] if row["state"]["settled"])),
        "all_unsettled_payout_liability": None,
        "scope": "Selected/recent IDs only; stored payouts are cumulative internal credits, not external payments or profit."}
    history = coverage.get("history", {})
    if not history.get("requested"):
        coverage["collection_complete"] = snapshot_complete
        return
    if "events" not in metrics or "receipts" not in metrics:
        return
    events = metrics["events"]
    counters = _counter_reconciliation(events, metrics.get("history_baseline"), metrics.get("state"))
    coverage["history_counter_reconciliation"] = counters
    observed = {"event_count": len(events), "placements": sum(row["event"] == "BetPlaced" for row in events),
                "settlements": sum(row["event"] == "Settled" for row in events),
                "risk_off_placement_principal": quantity(sum(int(row["values"]["amount"]) for row in events if row["event"] == "BetPlaced" and row["values"]["riskOff"])),
                "risk_on_event_amount_basis_unverified": quantity(sum(int(row["values"]["amount"]) for row in events if row["event"] == "BetPlaced" and not row["values"]["riskOff"])),
                "settled_wager": quantity(sum(int(row["values"]["wager"]) for row in events if row["event"] == "Settled")),
                "settled_internal_payout": quantity(sum(int(row["values"]["payout"]) for row in events if row["event"] == "Settled")),
                "house_fee_allocation": quantity(sum(int(row["values"]["potHalf"]) for row in events if row["event"] == "FeeSplit")),
                "sleeve_fee_allocation": quantity(sum(int(row["values"]["sleeveHalf"]) for row in events if row["event"] == "FeeSplit")),
                "house_capital_deposits": quantity(sum(int(row["values"]["amount"]) for row in events if row["event"] == "HouseDeposited")),
                "house_capital_withdrawals": quantity(sum(int(row["values"]["amount"]) for row in events if row["event"] == "HouseWithdrawn"))}
    receipts = metrics["receipts"]
    checked = [row for row in receipts if row["status"] == "checked"]
    receipt_event_consistency = all(not row["missing_scanned_event_log_indices"] for row in checked)
    scan_complete = bool(snapshot_complete and coverage.get(EVENT_COVERAGE, {}).get("event_coverage_complete") and
                         counters["complete"] and receipt_event_consistency)
    receipt_complete = bool(scan_complete and len(checked) == len({row["transactionHash"] for row in events}) and
                            all(row["sleeve_outflow_matches_allocations_plus_withdrawals"] for row in checked))
    receipt_amounts = {name: quantity(sum(int(leg["amount"]["raw"]) for row in checked for leg in row["legs"]
                                       if leg["direction"] == "out" and leg["recipient_role"] == name))
                       for name in ("sleeve", "treasury", "other_recipient")}
    receipt_amounts["desk_custody_inflow"] = quantity(sum(int(leg["amount"]["raw"]) for row in checked
                                                        for leg in row["legs"] if leg["direction"] == "in"))
    metrics["event_reported"] = {"observed_subtotal": observed,
                                 "requested_window_total": observed if scan_complete else None,
                                 "lifetime_total": None,
                                 "basis": "Served event window plus placement/market boundary counters; no complete settlement/fee-history state census or source audit."}
    metrics["receipt_confirmed"] = {"observed_subtotal": receipt_amounts,
                                    "requested_event_transaction_total": receipt_amounts if receipt_complete else None,
                                    "all_book_outflows": None,
                                    "scope": "wsNET Desk custody inflows and recipient outflows in observed Book event receipts only. Custody inflow includes player deposits as well as house funding; allocation/capital event fields classify accounting separately. Not every token/transaction, net balance change or revenue."}
    coverage["receipt_reconciliation"] = {"collection_complete": receipt_complete, "checked_transactions": len(checked)}
    coverage["collection_complete"] = bool(snapshot_complete and scan_complete and receipt_complete)


def run(ctx, args):
    routes = resolve_routes("book")
    source = load_json(routes["_route"]["interface"])
    evidence = load_json("assets/contracts/book-source-evidence.json")
    metrics, coverage = ctx.result["metrics"], ctx.result["coverage"]
    metrics.update(source_id=evidence["source_id"], markets=[], bets=[], state={}, bindings=[], implementations={},
                   snapshot_reads_complete=False, events=[], receipts=[])
    coverage.update(collection_complete=False, history={"requested": args.from_block is not None})
    ctx.result["not_proven"].extend([
        "Publisher ABI matches observed explorer dispatcher, not verified Solidity, source equivalence or a security audit.",
        "Current Book housePot is already an RFV Sleeve component. Do not add this snapshot again in combined totals or call it Core backing.",
        "Player free balances, locked risk-on stakes, risk-off principal, house cover and actual custody are different quantities. Reserved cover overlaps housePot.",
        "Internal settled payout is not an external withdrawal. Wager volume, house capital and fee allocations are not house profit or Treasury revenue.",
        "Empty served logs never imply inactive or zero lifetime activity; boundary counters and available current state must agree.",
        "No stored financial state or history is consulted. Native wsNET18 only; no current or historical USD valuation is substituted.",
        "Unknown exact risk-off rounding and dependent implementation prevent verified all-unsettled payout liability; selected model outputs are explicitly attributed.",
    ])
    try:
        for role in ("desk", "zap"):
            raw = bytes.fromhex(ctx.code(routes[role]["address"])[2:])
            expected = evidence["contracts"][role]
            digest = hashlib.sha256(raw).hexdigest()
            matched = len(raw) == expected["runtime_bytes"] and digest == expected["runtime_sha256"]
            metrics["implementations"][role] = {"runtime_sha256": digest, "runtime_bytes": len(raw),
                                                 "status": "explorer_runtime_matched" if matched else "unsupported"}
            if not matched:
                raise RpcError("Book runtime differs from catalogued exact generation", kind="unsupported")
        for role, getter, expected_role in BINDINGS:
            abi = source["abi" if role == "desk" else "zap_abi"]
            value = _address(ctx.call(routes[role]["address"], abi, getter))
            metrics["bindings"].append({"contract": role, "function": getter, "observed": value,
                                         "expected": routes[expected_role]["address"]})
            if value != routes[expected_role]["address"]:
                raise RpcError("Book canonical dependency identity differs", kind="integrity")
        decimals = ctx.call(routes["wsnet"]["address"], source["token_abi"], "decimals")
        if decimals != 18:
            raise RpcError("Book wsNET decimal identity differs", kind="integrity")
        desk = routes["desk"]["address"]
        for name in STATE:
            metrics["state"][name] = _read(ctx, name, lambda name=name: ctx.call(desk, source["abi"], name))
            ctx.checkpoint()
        state = metrics["state"]
        custody = _read(ctx, "desk_wsnet_custody", lambda: ctx.call(routes["wsnet"]["address"], source["token_abi"], "balanceOf", [desk]))
        metrics["custody"] = quantity(custody) if custody is not None else None
        metrics["zap_cap_raw_usdg"] = _read(ctx, "zap_cap", lambda: ctx.call(routes["zap"]["address"], source["zap_abi"], "ZAP_CAP_USDG"))
        pots = state.get("potsOf")
        if pots is not None:
            house, reserved, wagers, principal = (pots[str(index)] for index in range(4))
            metrics["state_accounting"] = {"house_capital": quantity(house), "reserved_cover": quantity(reserved),
                "locked_risk_on": quantity(wagers), "locked_risk_off_principal": quantity(principal),
                "free_house_cover": quantity(state["freePot"]) if state["freePot"] is not None else None,
                "free_player_ledger": quantity(state["playerTotal"]) if state["playerTotal"] is not None else None,
                "free_pot_matches_house_minus_reserved": state["freePot"] == house-reserved if state["freePot"] is not None else None,
                "custody_minus_accounted_components": quantity(custody-house-wagers-principal-state["playerTotal"])
                    if custody is not None and state["playerTotal"] is not None else None,
                "basis": "Publisher ledger decomposition; surplus/deficit is reconciliation evidence, not profit, free liquidity or an audited solvency verdict."}
        market_count, bet_count = state.get("marketCount"), state.get("betCount")
        if market_count is None or bet_count is None:
            return
        market_ids = select_ids(market_count, args.market_ids, args.max_markets)
        bet_ids = select_ids(bet_count, args.bet_ids, args.max_bets)
        coverage["id_discovery"] = {"selected_market_ids": market_ids, "selected_bet_ids": bet_ids,
            "market_counter": market_count, "bet_counter": bet_count,
            "all_market_ids_selected": len(market_ids) == market_count, "all_bet_ids_selected": len(bet_ids) == bet_count,
            "scope": "Explicit IDs, otherwise newest bounded IDs; related bet markets read additionally. No global payout-total claim."}
        markets = {}
        def market_read(market_id):
            if market_id not in markets:
                value = _read(ctx, "marketOf", lambda: ctx.call(desk, source["abi"], "marketOf", [market_id]))
                markets[market_id] = value
                exposure = _read(ctx, "exposureOf", lambda: ctx.call(desk, source["abi"], "exposureOf", [market_id]))
                metrics["markets"].append({"market_id": market_id, "state": value,
                                             "exposure": quantity(exposure) if exposure is not None else None})
            return markets[market_id]
        for market_id in market_ids:
            market_read(market_id)
        for bet_id in bet_ids:
            value = _read(ctx, "betOf", lambda bet_id=bet_id: ctx.call(desk, source["abi"], "betOf", [bet_id]))
            if value is not None:
                if not 1 <= value["marketId"] <= market_count:
                    raise RpcError("Book bet market is outside counter", kind="integrity")
                metrics["bets"].append(bet_row(bet_id, value, market_read(value["marketId"])))
            ctx.checkpoint()
        metrics["snapshot_reads_complete"] = (not ctx.result["errors"] and all(value is not None for value in state.values()) and
                                                custody is not None and len(metrics["bets"]) == len(bet_ids))
        if args.from_block is None:
            return
        start = args.from_block
        if type(start) is not int or not 0 <= start <= ctx.block:
            raise RpcError("Book history start must be within snapshot", kind="input")
        coverage["history"].update(requested_range=[start, ctx.block], scope="All supported Desk events; snapshot ID filters do not filter history.")
        baseline = {}
        for name in ("betCount", "marketCount"):
            baseline[name] = 0 if start == 0 else _read(ctx, "history_boundary_"+name,
                lambda name=name: ctx.call(desk, source["abi"], name, block=start-1))
        metrics["history_baseline"] = baseline if all(value is not None for value in baseline.values()) else None
        for page in ctx.logs(EVENT_COVERAGE, desk, source["abi"], list(EVENTS), start, ctx.block):
            metrics["events"].extend(page)
            ctx.checkpoint()
        groups = {}
        for event in metrics["events"]:
            groups.setdefault(event["transactionHash"], []).append(event)
        for tx_hash, rows in groups.items():
            receipt_row = {"transaction_hash": tx_hash, "status": "not_checked"}
            metrics["receipts"].append(receipt_row)
            result = _read(ctx, "book_receipt", lambda: reconcile_receipt(ctx.receipt(tx_hash), rows, routes, source))
            receipt_row.update(result or {"status": "unavailable"})
            ctx.checkpoint()
    finally:
        prepare_result(ctx.result)


def summarize(text, checkpoint_status):
    result = json.loads(text)
    result["metrics"] = {key: value for key, value in result.get("metrics", {}).items()
                         if key not in ("markets", "bets", "events", "receipts", "bindings")}
    result.update(detail="summary", checkpoint_status=checkpoint_status)
    return serialize_result(result)

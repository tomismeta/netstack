"""Read-only, pinned-block Predict and internal House accounting analytics."""

from collections import Counter, defaultdict
from fractions import Fraction

from netstack_core import ZERO, RpcError, amount, load_json, ratio, resolve_routes


WAD = 10**18
_STATUS = {0: "none", 1: "open", 2: "resolved", 3: "voided"}
_TRADE_FIELDS = (
    "buy_count", "sell_count", "redemption_count", "buy_gross_usdg_raw",
    "buy_fees_usdg_raw", "sell_net_usdg_raw", "sell_fees_usdg_raw",
    "redemption_usdg_raw", "bought_tokens_raw", "sold_tokens_raw",
    "redeemed_tokens_raw",
)


def _raw(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _raw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_raw(v) for v in value]
    return value


def _problem(ctx, scope, error):
    ctx.result["errors"].append({"scope": scope, "error": str(error)})


def _optional(ctx, address, abi, method, args=(), block=None):
    try:
        return ctx.call(address, abi, method, args, block=block)
    except RpcError as error:
        _problem(ctx, method + ":" + address, error)
        return None


def _getters(ctx, address, abi, names, target):
    # Persist each successful value: a deadline may interrupt the next member.
    values = {}
    for name in names:
        value = _optional(ctx, address, abi, name)
        values[name] = value
        target[name] = _raw(value)
        ctx.checkpoint()
    return values


def _complete(ctx, key):
    return ctx.result["coverage"].get(key, {}).get("event_coverage_complete", False)


def _planned_scan(ctx, key, start):
    ctx.result["coverage"].setdefault(key, {
        "requested_range": [start, ctx.block], "covered_ranges": [],
        "missing_ranges": [[start, ctx.block]], "event_coverage_complete": False,
        "status": "not_started",
    })


def _scan(ctx, key, address, abi, names, start, consume, indexed_topics=None):
    _planned_scan(ctx, key, start)
    try:
        options = {} if indexed_topics is None else {"indexed_topics": indexed_topics}
        for page in ctx.logs(key, address, abi, names, start, ctx.block, **options):
            consume(page)
            ctx.checkpoint()
    except RpcError as error:
        _problem(ctx, key, error)
    # Generators can set completion only when resumed after the final page.
    consume([])
    ctx.checkpoint()


def _comparison(observed, expected, complete, **extra):
    return {
        "observed_raw": _raw(observed), "expected_raw": _raw(expected),
        "residual_raw": None if observed is None or expected is None else str(observed - expected),
        "supporting_event_coverage_complete": bool(complete),
        "interpretation": "observed reconciliation hypothesis, not verified implementation",
        **extra,
    }


def _setup(ctx, command):
    routes = resolve_routes("predict")
    source = load_json(routes["_route"]["desk_interface"])
    house_source = load_json(routes["_route"]["house_interface"])
    desk, house, usdg = (routes[name]["address"] for name in ("desk", "house", "usdg"))
    metrics = ctx.result["metrics"]
    metrics["scope"] = {
        "chain_id": 4663, "desk": desk, "house": house, "usdg": usdg,
        "deployment_scope": "selected registry deployment only; earlier deployments are not enumerated",
        "selected_deployment_only": True,
        "unit": "USDG; no USD parity or dollar valuation assumed",
        "interface_evidence": "published view ABI and live consumer, not verified Solidity",
        "source_id": source["source_id"], "metadata_observed_on": source["reviewed_on"],
        "snapshot_block": ctx.block,
    }
    ctx.result["coverage"]["collection_complete"] = False
    requested = ("activity", "funding", "counter_reconciliation", "outcome_supply_reconciliation", "fees_paid_reconciliation", "cash_reconciliation") if command == "predict" else ("ownership", "house_events", "performance", "cash_reconciliation")
    for name in requested:
        metrics[name] = {"status": "unavailable", "reason": "retrieval not reached; pinned snapshots take priority"}
    ctx.result["not_proven"].extend([
        "Selected deployment is not all historical Predict/House generations.",
        "RPC range completion assumes the provider did not silently omit logs.",
        "Role anchors and account getters do not prove every beneficial owner.",
        "Fees, book, cash, pending deposits and claim liabilities are not additive profit buckets.",
    ])
    for address in (desk, house, usdg):
        if ctx.code(address) in ("0x", "0x0", "0x00"):
            raise RpcError("No deployed code at pinned block: " + address)
    da, ha, ta = source["abi"], house_source["abi"], source["token_abi"]
    metrics["desk_snapshot"] = {}
    metrics["house_snapshot"] = {}
    # Preserve command-specific primary state before history or optional metadata.
    if command == "house":
        hv = _getters(ctx, house, ha, (
            "totalShares", "totalPending", "totalClaimable", "sharePriceWad",
            "activeAssets", "live", "seriesCount", "generation", "generationStartSeries",
            "desk", "usdg", "wired",
        ), metrics["house_snapshot"])
        dv = _getters(ctx, desk, da, ("seriesCount", "halted", "vault", "usdg", "sleeve", "treasury", "owner", "grader", "net"), metrics["desk_snapshot"])
    else:
        dv = _getters(ctx, desk, da, (
            "seriesCount", "halted", "minTicket", "vault", "usdg", "sleeve", "treasury",
            "reservedUsdg", "pendingNetUsdg", "prizeCarry", "net", "owner", "grader", "markPrice",
        ), metrics["desk_snapshot"])
        hv = _getters(ctx, house, ha, ("desk", "usdg", "wired"), metrics["house_snapshot"])
    expected = ((dv, "vault", house), (dv, "usdg", usdg), (hv, "desk", desk),
                (hv, "usdg", usdg), (dv, "sleeve", routes["sleeve"]["address"]),
                (dv, "treasury", routes["treasury"]["address"]))
    if any(values.get(key) != identity for values, key, identity in expected):
        raise RpcError("Pinned deployment wiring is missing or differs from selected canonical routes")
    if hv.get("wired") is not True:
        raise RpcError("Selected House is not established wired at the pinned block")
    decimals = _optional(ctx, usdg, ta, "decimals")
    metrics["usdg"] = {"address": usdg, "decimals": decimals, "reviewed_six_decimal_convention": decimals == 6}
    for name, address in (("desk", desk), ("house", house)):
        balance = _optional(ctx, usdg, ta, "balanceOf", (address,))
        metrics[name + "_snapshot"]["usdg_balance_raw"] = _raw(balance)
        metrics[name + "_snapshot"]["usdg_balance"] = None if balance is None or decimals is None else amount(balance, decimals)
        (dv if name == "desk" else hv)["usdg_balance_raw"] = balance
        ctx.checkpoint()
    metrics["desk_snapshot"]["markPrice_scope"] = "current Desk-level mark only, never a historical-series execution price"
    return routes, da, ha, ta, dv, hv, decimals


def _classification(raw, timestamp, halted):
    status = raw["status"]
    op, last, close, printing = (raw[k] for k in ("openTime", "lastCallTime", "closeTime", "printTime"))
    inconsistent = not (0 < op <= last <= close <= printing)
    state = _STATUS.get(status, "unknown_enum")
    if status == 1:
        if timestamp >= close:
            state = "closed_awaiting_settlement"
        elif inconsistent:
            state = "contradictory_timestamps"
        elif timestamp < op:
            state = "scheduled"
        elif timestamp >= last:
            state = "last_call"
        else:
            state = "trading_window"
    window = state in ("trading_window", "last_call") and not inconsistent
    return {
        "raw_status": status, "status_label": _STATUS.get(status, "unknown_enum"),
        "clock_state": state, "timestamp_inconsistency": inconsistent,
        "new_buy_halted": halted, "conditional_buy_window": window and halted is False,
        "buy_acceptance": "not proven; amount, side/skew, minimum and account gates remain",
        "last_call_skew_reducing_buys_only": state == "last_call",
        "sell_window": "acceptance_unproven" if window else "not_established",
        "halt_is_not_a_sell_halt": True,
        "closed_by_clock": status == 1 and timestamp >= close,
        "awaiting_posted_print": status == 1 and timestamp > printing,
        "settlement_established": status in (2, 3),
    }


def _discover(ctx, desk, da, dv, all_series=True):
    count = dv.get("seriesCount")
    rows, raw_rows = {}, {}
    ctx.result["metrics"]["series"] = rows
    cov = ctx.result["coverage"]["series_discovery"] = {
        "count": count, "inspected_ids": [], "missing_id_ranges": [],
        "discovery_complete": False, "scope": "all selected Desk IDs" if all_series else "latest selected Desk series only",
    }
    if count is None:
        cov["reason"] = "seriesCount unavailable"
        return raw_rows
    low = 1 if all_series else max(1, count)
    cov["missing_id_ranges"] = [[low, count]] if count else []
    # Newest-first bounded pages preserve the current series on interruption.
    for high in range(count, low - 1, -20):
        for sid in range(high, max(low - 1, high - 20), -1):
            raw = _optional(ctx, desk, da, "series", (sid,))
            if raw is not None:
                raw_rows[sid] = raw
                rows[str(sid)] = {
                    "identity": {"chain_id": 4663, "desk": desk, "series_id": sid, "vault": dv["vault"]},
                    "raw": _raw(raw), "state": _classification(raw, ctx.timestamp, dv.get("halted")),
                    "stored_mark_scope": "lastMarkWad belongs to this tuple, not current markPrice",
                    "onchain_question_title": None,
                    "line_display_convention": "raw / 10^18 million displayed dollars; attributed live frontend convention",
                    "outcome_tokens": {},
                }
                cov["inspected_ids"].append(sid)
                remaining = []
                for left, right in cov["missing_id_ranges"]:
                    if left <= sid <= right:
                        if left < sid:
                            remaining.append([left, sid - 1])
                        if sid < right:
                            remaining.append([sid + 1, right])
                    else:
                        remaining.append([left, right])
                cov["missing_id_ranges"] = remaining
            ctx.checkpoint()
    cov["discovery_complete"] = not cov["missing_id_ranges"]
    return raw_rows




def _trade_totals(counter):
    result = {key: counter[key] if key.endswith("_count") else str(counter[key]) for key in _TRADE_FIELDS}
    result.update({
        "buy_net_premium_usdg_raw": str(counter["buy_gross_usdg_raw"] - counter["buy_fees_usdg_raw"]),
        "sell_gross_value_event_convention_raw": str(counter["sell_net_usdg_raw"] + counter["sell_fees_usdg_raw"]),
        "total_trade_fees_usdg_raw": str(counter["buy_fees_usdg_raw"] + counter["sell_fees_usdg_raw"]),
        "trader_net_cash_outflow_event_labeled_raw": str(counter["buy_gross_usdg_raw"] - counter["sell_net_usdg_raw"] - counter["redemption_usdg_raw"]),
        "cash_interpretation": "event-labeled; consult separate transfer reconciliation; not House profit",
    })
    return result


def _event_id(event):
    return (event["blockHash"], event["transactionHash"], event["logIndex"])


def _event_ref(event):
    return {"transaction_hash": event["transactionHash"], "block": event["blockNumber"], "log_index": event["logIndex"]}


def _cash_key(token, event, sender, recipient):
    return (token, event["transactionHash"], sender, recipient)


class _Evidence:
    """Bounded event/transfer ledger; output consists of compact aggregates only."""

    def __init__(self, ctx, desk, house, usdg):
        self.ctx, self.desk, self.house, self.usdg = ctx, desk, house, usdg
        self.events = []
        self.transfers = {}
        self.starts = {}
        self.balances_before = {}
        self.event_keys = []
        self.cash_keys = []

    def extend(self, page):
        self.events.extend(page)

    def add_transfers(self, page):
        for event in page:
            self.transfers[_event_id(event)] = event

    def expected(self, outcomes=None):
        groups = defaultdict(lambda: {"amount": 0, "operations": [], "events": []})
        unknown_routing = defaultdict(int)
        for event in self.events:
            value, name, address = event["values"], event["event"], event["address"]
            account = value.get("account")
            sender = recipient = None
            quantity = None
            if address == self.desk:
                if name == "Bought":
                    sender, recipient, quantity = account, self.desk, value["usdgIn"]
                elif name in ("Sold", "Redeemed"):
                    sender, recipient, quantity = self.desk, account, value["usdgOut"]
                elif name == "PrizePaid":
                    sender, recipient, quantity = self.desk, account, value["usdg"]
                elif name == "NetBought":
                    unknown_routing[event["transactionHash"]] += value["usdgSpent"]
            elif address == self.house:
                if name in ("Deposited", "DepositQueued"):
                    sender, recipient, quantity = account, self.house, value["usdg"]
                elif name in ("DepositCancelled", "WithdrawClaimed"):
                    sender, recipient, quantity = self.house, account, value["usdg"]
                elif name == "Funded":
                    sender, recipient, quantity = self.house, self.desk, value["usdg"]
                elif name == "Settled":
                    sender, recipient, quantity = self.desk, self.house, value["usdgReturned"]
            if quantity is not None:
                group = groups[_cash_key(self.usdg, event, sender, recipient)]
                group["amount"] += quantity
                group["operations"].append(name)
                group["events"].append(event)
            if outcomes is not None and address == self.desk and name in ("Bought", "Sold", "Redeemed"):
                token = outcomes.get((value["series"], value["long"]))
                if token and token != ZERO:
                    sender, recipient = (ZERO, account) if name == "Bought" else (account, ZERO)
                    quantity = value[{"Bought": "tokensOut", "Sold": "tokensIn", "Redeemed": "tokens"}[name]]
                    group = groups[_cash_key(token, event, sender, recipient)]
                    group["amount"] += quantity
                    group["operations"].append(name + ":outcome")
                    group["events"].append(event)
        return groups, unknown_routing

    def matching(self, outcomes=None):
        expected, routing = self.expected(outcomes)
        actual = defaultdict(int)
        refs = defaultdict(list)
        for event in self.transfers.values():
            value = event["values"]
            key = _cash_key(event["address"], event, value["from"], value["to"])
            actual[key] += value["value"]
            refs[key].append(event)
        matches, mismatches, matched_keys = [], [], set()
        for key, group in expected.items():
            observed = actual.get(key, 0)
            # An absent zero-value Transfer does not prove a positive cash leg.
            matched = observed == group["amount"] and (key in actual or group["amount"] == 0)
            row = {
                "token": key[0], "transaction_hash": key[1], "from": key[2], "to": key[3],
                "event_amount_raw": str(group["amount"]), "transfer_amount_raw": str(observed),
                "operations": dict(Counter(group["operations"])), "matched": matched,
                "match_scope": "transaction + token + direction + counterpart aggregate; no per-operation attribution",
            }
            (matches if matched else mismatches).append(row)
            if matched:
                matched_keys.add(key)
        # NET routing has no recipient in its ABI. Match only the entire otherwise
        # unassigned outgoing Desk group; never choose a convenient equal transfer.
        route_matches = []
        for tx, quantity in routing.items():
            keys = [key for key in actual if key[0] == self.usdg and key[1] == tx and key[2] == self.desk and key not in expected]
            observed = sum(actual[key] for key in keys)
            matched = observed == quantity and (bool(keys) or quantity == 0)
            route_matches.append({"transaction_hash": tx, "event_raw": str(quantity), "unassigned_outgoing_raw": str(observed), "matched": matched, "scope": "aggregate outgoing USDG; NET token acquisition/burning not proven"})
            if matched:
                matched_keys.update(keys)
        unmatched = []
        for key in actual.keys() - matched_keys:
            if key[0] != self.usdg:
                continue
            unmatched.append({"transaction_hash": key[1], "from": key[2], "to": key[3], "value_raw": str(actual[key]), "log_indices": [e["logIndex"] for e in refs[key]]})
        unmatched.sort(key=lambda row: (row["transaction_hash"], row["from"], row["to"]))
        return expected, matched_keys, matches, mismatches, route_matches, unmatched

    def publish(self, outcomes=None):
        expected, matched_keys, matches, mismatches, routing, unmatched = self.matching(outcomes)
        cash_complete = bool(self.cash_keys) and all(_complete(self.ctx, key) for key in self.cash_keys)
        event_complete = bool(self.event_keys) and all(_complete(self.ctx, key) for key in self.event_keys)
        routing_matched = all(row["matched"] for row in routing)
        series_discovery_complete = self.ctx.result["coverage"].get("series_discovery", {}).get("discovery_complete", False)
        unmapped_outcome_events = []
        if outcomes is not None:
            for event in self.events:
                value = event["values"]
                if event["address"] == self.desk and event["event"] in ("Bought", "Sold", "Redeemed") and outcomes.get((value["series"], value["long"])) in (None, ZERO):
                    unmapped_outcome_events.append({
                        "series": value["series"], "side": "HIGHER" if value["long"] else "LOWER",
                        "event": event["event"], **_event_ref(event),
                    })
        rows = {}
        for name, address in (("desk", self.desk), ("house", self.house)):
            incoming = outgoing = 0
            for event in self.transfers.values():
                if event["address"] != self.usdg or event["blockNumber"] < self.starts.get(name, 0):
                    continue
                value = event["values"]
                if value["to"] == address:
                    incoming += value["value"]
                if value["from"] == address:
                    outgoing += value["value"]
            before = self.balances_before.get(name)
            raw_after = self.ctx.result["metrics"][name + "_snapshot"].get("usdg_balance_raw")
            after = None if raw_after is None else int(raw_after)
            rows[name] = {
                "balance_before_raw": _raw(before), "balance_at_snapshot_raw": _raw(after),
                "incoming_observed_raw": str(incoming), "outgoing_observed_raw": str(outgoing),
                "balance_delta_residual_raw": None if before is None or after is None else str(after - before - incoming + outgoing),
                "transfer_history_complete": cash_complete and name in self.starts,
                "balance_comparison_performed": before is not None and after is not None,
                "balance_reconciliation_complete": cash_complete and name in self.starts and before is not None and after is not None and after - before - incoming + outgoing == 0,
                "interval": [self.starts.get(name), self.ctx.block],
            }
            rows[name]["event_cash_legs_matched"] = cash_complete and event_complete and name in self.starts and not any(
                row["token"] == self.usdg and address in (row["from"], row["to"]) for row in mismatches
            ) and (address != self.desk or routing_matched)
            rows[name]["unmatched_transfer_count"] = sum(address in (row["from"], row["to"]) for row in unmatched)
        cash_mismatches = [row for row in mismatches if row["token"] == self.usdg]
        outcome_mismatches = [row for row in mismatches if row["token"] != self.usdg]
        outcome_keys = {"outcome_transfers:" + token for token in (outcomes or {}).values() if token != ZERO}
        mapped_outcome_history_complete = outcomes is not None and all(_complete(self.ctx, key) for key in outcome_keys)
        mapping_series = {series for series, side in (outcomes or {})}
        mapping_series.update(self.ctx.result["coverage"].get("series_discovery", {}).get("inspected_ids", []))
        unmapped_outcome_identities = [
            {"series": series, "side": "HIGHER" if side else "LOWER"}
            for series in sorted(mapping_series) for side in (True, False)
            if outcomes.get((series, side)) in (None, ZERO)
        ] if outcomes is not None else []
        outcome_scope_complete = outcomes is not None and series_discovery_complete and not unmapped_outcome_events and not unmapped_outcome_identities
        self.ctx.result["metrics"]["cash_reconciliation"] = {
            "accounts": rows, "event_coverage_complete": event_complete,
            "transfer_history_complete": cash_complete,
            "cash_matching_complete": cash_complete and event_complete and not cash_mismatches and not unmatched and routing_matched and all(rows[name]["balance_reconciliation_complete"] for name in self.starts),
            "event_cash_legs_matched": cash_complete and event_complete and not cash_mismatches and routing_matched,
            "mapped_outcome_transfer_history_complete": mapped_outcome_history_complete,
            "outcome_series_discovery_complete": series_discovery_complete,
            "unmapped_outcome_events": unmapped_outcome_events,
            "unmapped_outcome_identities": unmapped_outcome_identities,
            "outcome_transfer_history_complete": outcome_scope_complete and mapped_outcome_history_complete,
            "outcome_event_legs_matched": outcome_scope_complete and mapped_outcome_history_complete and event_complete and not outcome_mismatches,
            "matched_transaction_groups": len(matches), "expected_transaction_groups": len(expected),
            "mismatched_cash_groups": cash_mismatches, "mismatched_outcome_groups": outcome_mismatches,
            "unmatched_usdg_transfers": unmatched,
            "unmatched_usdg_signed_raw": {
                name: str(sum(int(row["value_raw"]) * ((row["to"] == address) - (row["from"] == address)) for row in unmatched))
                for name, address in (("desk", self.desk), ("house", self.house))
            },
            "net_routing": routing,
            "net_routing_comparison_performed": bool(routing),
            "net_routing_events_observed": len(routing),
            "net_routing_cash_matched": cash_complete and event_complete and routing_matched,
            "grouping": "Each token/direction/counterpart transaction total is consumed once; multiple operations are not independently assigned transfers.",
        }
        return expected, matched_keys


def _cash_history(ctx, ledger, ta, start, addresses, outcomes=None, after_page=None):
    indexed = ["0x" + address[2:].rjust(64, "0") for address in addresses]
    keys = ("usdg_outgoing", "usdg_incoming")
    ledger.cash_keys = list(keys)
    for key in keys:
        _planned_scan(ctx, key, start)
    for name, address in (("desk", ledger.desk), ("house", ledger.house)):
        if address in addresses:
            ledger.starts[name] = start
            ledger.balances_before[name] = _optional(ctx, ledger.usdg, ta, "balanceOf", (address,), block=start - 1) if start > 0 else 0
    def consume(page):
        ledger.add_transfers(page)
        ledger.publish(outcomes)
        if after_page:
            after_page()
    for key, filters in zip(keys, ([indexed, None], [None, indexed])):
        _scan(ctx, key, ledger.usdg, ta, ["Transfer"], start, consume, filters)


def _token_snapshots(ctx, ta, series):
    tokens = {}
    rows = ctx.result["metrics"]["series"]
    for sid, raw in series.items():
        for long_side, field in ((True, "long"), (False, "short")):
            address = raw[field]
            token = rows[str(sid)]["outcome_tokens"]["HIGHER" if long_side else "LOWER"] = {"address": address}
            if address == ZERO:
                token["error"] = "zero outcome identity"
                _problem(ctx, "series:" + str(sid), "zero outcome identity")
                continue
            if address not in tokens:
                values = _getters(ctx, address, ta, ("decimals", "totalSupply", "name", "symbol"), token)
                tokens[address] = values
            else:
                token.update(_raw(tokens[address]))
            token["reviewed_eighteen_decimal_convention"] = tokens[address]["decimals"] == 18
    return tokens


def run_predict(ctx, args):
    routes, da, ha, ta, dv, hv, decimals = _setup(ctx, "predict")
    desk, house, usdg = (routes[key]["address"] for key in ("desk", "house", "usdg"))
    series = _discover(ctx, desk, da, dv)
    tokens = _token_snapshots(ctx, ta, series)
    metrics = ctx.result["metrics"]
    metrics["activity"] = {"status": "unavailable", "event_coverage_complete": False, "series": {}}
    metrics["funding"] = {"status": "unavailable", "series": {}}
    metrics["counter_reconciliation"] = {}
    metrics["outcome_supply_reconciliation"] = {}
    metrics["fees_paid_reconciliation"] = {"accounts": {}, "complete": False}
    ledger = _Evidence(ctx, desk, house, usdg)
    desk_start = ctx.deployment(routes["desk"])
    house_start = ctx.deployment(routes["house"])
    ledger.event_keys = ["desk_events", "house_funding_events"]
    for key, start in (("desk_events", desk_start), ("house_funding_events", house_start)):
        _planned_scan(ctx, key, start)
    for key in ("usdg_outgoing", "usdg_incoming"):
        _planned_scan(ctx, key, min(desk_start, house_start))
    for token in tokens:
        _planned_scan(ctx, "outcome_transfers:" + token, desk_start)
    totals, sides, fees = defaultdict(Counter), defaultdict(Counter), defaultdict(int)
    openings, settlements, funds, returns = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    global_counts, global_amounts = Counter(), Counter()
    outcomes = {(sid, side): raw["long" if side else "short"] for sid, raw in series.items() for side in (True, False)}
    fees_cov = ctx.result["coverage"]["fees_paid"] = {"discovered_account_series_pairs": 0, "read_pairs": 0, "missing_pairs": [], "complete": False}

    def publish():
        complete = _complete(ctx, "desk_events")
        fees_cov["discovered_account_series_pairs"] = len(fees)
        fees_cov["missing_pairs"] = [[sid, account] for sid, account in sorted(fees) if str(sid) + ":" + account not in metrics["fees_paid_reconciliation"]["accounts"]]
        activity = metrics["activity"]
        activity.update({"status": "complete_event_scope" if complete else "partial_observed", "event_coverage_complete": complete,
                         "event_counts": dict(global_counts), "global_unassigned_routing_raw": _raw(global_amounts)})
        for sid in sorted(set(series) | set(totals)):
            row = _trade_totals(totals[sid])
            row["sides"] = {"HIGHER" if side else "LOWER": _trade_totals(sides[sid, side]) for side in (True, False)}
            row["event_coverage_complete"] = complete
            row["opened_events"] = len(openings[sid])
            row["settled_events"] = len(settlements[sid])
            row["zero_counts_mean"] = "zero in selected deployment scan" if complete else "zero observed only; unscanned history is unknown"
            row["redeemed_status_at_snapshot"] = _STATUS.get(series.get(sid, {}).get("status"), "uninspected_or_unknown")
            row["prizes_paid_event_usdg_raw"] = str(sum(e["values"]["usdg"] for e in ledger.events if e["address"] == desk and e["event"] == "PrizePaid" and e["values"]["series"] == sid))
            row["prizes_rolled_event_usdg_raw"] = str(sum(e["values"]["usdg"] for e in ledger.events if e["address"] == desk and e["event"] == "PrizeRolled" and e["values"]["series"] == sid))
            activity["series"][str(sid)] = row
            funding = sum(e["values"]["usdg"] for e in funds[sid])
            returned = sum(e["values"]["usdgReturned"] for e in returns[sid])
            fcomplete = _complete(ctx, "house_funding_events")
            metrics["funding"]["series"][str(sid)] = {
                "funded_event_usdg_raw": str(funding) if funds[sid] or fcomplete else None,
                "returned_event_usdg_raw": str(returned) if returns[sid] or fcomplete else None,
                "funding_events": len(funds[sid]), "return_events": len(returns[sid]),
                "event_coverage_complete": fcomplete, "cash_status": "consult cash_reconciliation; event values are not automatically cash-verified",
            }
            if sid not in series:
                continue
            raw, trade = series[sid], totals[sid]
            trade_fees = trade["buy_fees_usdg_raw"] + trade["sell_fees_usdg_raw"]
            gross_sell = trade["sell_net_usdg_raw"] + trade["sell_fees_usdg_raw"]
            diagnostic = {
                "volume_hypothesis": _comparison(raw["volumeUsdg"], trade["buy_gross_usdg_raw"] + gross_sell, complete),
                "fees_hypothesis": _comparison(raw["feesUsdg"], trade_fees, complete),
                "fee_allocation_hypothesis": _comparison(raw["feesUsdg"], raw["netSpentUsdg"] + raw["vaultFees"], complete, caveat="pending/deferred NET and other allocations unresolved; not a universal equality"),
                "opening_consistent": len(openings[sid]) == 1 and all(e["values"]["long"] == raw["long"] and e["values"]["short"] == raw["short"] for e in openings[sid]),
                "unexpected_none": raw["status"] == 0,
                "settled_return_hypothesis": _comparison(sum(e["values"]["toVault"] for e in settlements[sid]), returned, complete and fcomplete, caveat="Desk and House are two observations of the same return, never additive revenue"),
                "settlement_transaction_pairs_consistent": sorted((e["transactionHash"], e["values"]["toVault"]) for e in settlements[sid]) == sorted((e["transactionHash"], e["values"]["usdgReturned"]) for e in returns[sid]),
            }
            if funds[sid]:
                diagnostic["backing_hypothesis"] = _comparison(raw["backingUsdg"], funding + raw["virtualLiquidity"], complete and fcomplete)
                if raw["status"] == 1:
                    diagnostic["book_hypothesis"] = _comparison(raw["bookUsdg"], funding + trade["buy_gross_usdg_raw"] - trade["buy_fees_usdg_raw"] - gross_sell, complete and fcomplete, caveat="only meaningful absent other book-affecting legs; excludes buy and sell fees")
            else:
                diagnostic["original_funded_amount"] = {"value": None, "reason": "no Funded evidence retrieved; backing/book/virtualLiquidity cannot substitute"}
            if raw["status"] == 1 and sum(r["status"] == 1 for r in series.values()) == 1:
                diagnostic["desk_cash_book_plus_fee_hypothesis"] = _comparison(dv["usdg_balance_raw"], raw["bookUsdg"] + raw["vaultFees"], complete, caveat="Desk cash can include other series, prizes, liabilities or donations")
            metrics["counter_reconciliation"][str(sid)] = diagnostic
        metrics["funding"]["status"] = "complete_event_scope" if _complete(ctx, "house_funding_events") else "partial_observed"
        known_ids = set(series)
        event_ids = set(openings) | set(totals) | set(settlements)
        metrics["activity"]["series_identity_check"] = {
            "event_ids_not_inspected": sorted(event_ids - known_ids),
            "event_ids_outside_count": sorted(sid for sid in event_ids if dv.get("seriesCount") is not None and not 1 <= sid <= dv["seriesCount"]),
            "inspected_ids_without_opened_event": sorted(known_ids - {sid for sid, events in openings.items() if events}),
            "event_coverage_complete": complete,
        }
        ledger.publish(outcomes)

    def desk_page(page):
        ledger.extend(page)
        for event in page:
            value, name = event["values"], event["event"]
            global_counts[name] += 1
            sid = value.get("series")
            if name == "Opened":
                openings[sid].append(event)
            elif name == "Settled":
                settlements[sid].append(event)
            elif name in ("NetBought", "NetBuyDeferred"):
                global_amounts["net_bought_usdg_raw" if name == "NetBought" else "net_deferred_observations_usdg_raw"] += value["usdgSpent" if name == "NetBought" else "usdgPending"]
            elif name in ("Bought", "Sold", "Redeemed"):
                delta = Counter()
                if name == "Bought":
                    delta.update(buy_count=1, buy_gross_usdg_raw=value["usdgIn"], buy_fees_usdg_raw=value["fee"], bought_tokens_raw=value["tokensOut"])
                elif name == "Sold":
                    delta.update(sell_count=1, sell_net_usdg_raw=value["usdgOut"], sell_fees_usdg_raw=value["fee"], sold_tokens_raw=value["tokensIn"])
                else:
                    delta.update(redemption_count=1, redemption_usdg_raw=value["usdgOut"], redeemed_tokens_raw=value["tokens"])
                totals[sid].update(delta)
                sides[sid, value["long"]].update(delta)
                fees[sid, value["account"]] += value.get("fee", 0)
            elif name in ("PrizePaid", "PrizeRolled"):
                global_amounts[name + "_usdg_raw"] += value["usdg"]
        publish()

    def funding_page(page):
        ledger.extend(page)
        for event in page:
            (funds if event["event"] == "Funded" else returns)[event["values"]["series"]].append(event)
        publish()

    _scan(ctx, "desk_events", desk, da, [], desk_start, desk_page)
    _scan(ctx, "house_funding_events", house, ha, ["Funded", "Settled"], house_start, funding_page)
    _cash_history(ctx, ledger, ta, min(desk_start, house_start), [desk, house], outcomes, publish)
    # This command did not request House deposit/withdrawal history; Vault-side
    # unmatched cash is intentionally retained, never classified as wagers.
    for token, values in tokens.items():
        key = "outcome_transfers:" + token
        supply = {"minted": 0, "burned": 0}
        before = None
        baseline = {"block": desk_start - 1 if desk_start else None, "status": "unavailable", "reason": "opening supply has not been established"}
        code_before = None
        if desk_start:
            try:
                code_before = ctx.code(token, block=desk_start - 1)
            except RpcError as error:
                _problem(ctx, "outcome_opening_code:" + token, error)
                baseline["reason"] = str(error)
        if code_before in ("0x", "0x0", "0x00"):
            before = 0
            baseline.update(status="established", reason="verified absent code before selected Desk deployment")
        elif code_before is not None:
            before = _optional(ctx, token, ta, "totalSupply", block=desk_start - 1)
            baseline.update(status="established" if before is not None else "unavailable", reason="historical totalSupply getter" if before is not None else "historical totalSupply unavailable; no zero-opening assumption")
        def outcome_page(page, token=token, key=key, values=values, before=before, supply=supply, baseline=baseline):
            ledger.add_transfers(page)
            for event in page:
                value = event["values"]
                if value["from"] == ZERO:
                    supply["minted"] += value["value"]
                if value["to"] == ZERO:
                    supply["burned"] += value["value"]
            total = values.get("totalSupply")
            metrics["outcome_supply_reconciliation"][token] = {
                "opening_supply_evidence": baseline,
                "opening_supply_raw": _raw(before), "minted_raw": str(supply["minted"]), "burned_raw": str(supply["burned"]),
                "total_supply_raw": _raw(total), "event_coverage_complete": _complete(ctx, key),
                "supply_residual_raw": None if before is None or total is None else str(total - before - supply["minted"] + supply["burned"]),
                "supply_comparison_performed": before is not None and total is not None,
                "supply_reconciled": _complete(ctx, key) and before is not None and total is not None and total == before + supply["minted"] - supply["burned"],
                "tuple_exposure_comparisons": {str(sid) + (":HIGHER" if side else ":LOWER"): _comparison(raw["longOut" if side else "shortOut"], total, _complete(ctx, key), caveat="stored exposure need not decrement on redemption") for sid, raw in series.items() for side in (True, False) if outcomes[sid, side] == token},
            }
            ledger.publish(outcomes)
        _scan(ctx, key, token, ta, ["Transfer"], desk_start, outcome_page)
    for sid, raw in series.items():
        if raw["status"] in (2, 3):
            eligible = decimals == 6 and all(tokens.get(raw[field], {}).get("decimals") == 18 for field in ("long", "short")) and 0 <= raw["longPayoutUsdg"] <= 10**6
            estimate = {}
            for field in ("long", "short"):
                supply = tokens.get(raw[field], {}).get("totalSupply")
                payout = raw["longPayoutUsdg"] if field == "long" else 10**6 - raw["longPayoutUsdg"]
                estimate[field] = str(supply * payout // WAD) if eligible and supply is not None else None
            metrics["series"][str(sid)]["remaining_claim_frontend_estimate"] = {"usdg_raw_by_side": estimate, "scope": "aggregate frontend payout indication; holder rounding and deployed redemption semantics unproven; not solvency"}
    for (sid, account), event_fees in sorted(fees.items()):
        observed = _optional(ctx, desk, da, "feesPaid", (sid, account))
        metrics["fees_paid_reconciliation"]["accounts"][str(sid) + ":" + account] = _comparison(observed, event_fees, _complete(ctx, "desk_events"))
        if observed is not None:
            fees_cov["read_pairs"] += 1
            fees_cov["missing_pairs"].remove([sid, account])
        ctx.checkpoint()
    fees_cov["complete"] = fees_cov["read_pairs"] == len(fees) and _complete(ctx, "desk_events")
    metrics["fees_paid_reconciliation"]["complete"] = fees_cov["complete"]
    # Two actual headers per activity span, not assumed seconds-per-block.
    for sid in sorted(totals):
        events = [e for e in ledger.events if e["address"] == desk and e["values"].get("series") == sid and e["event"] in ("Bought", "Sold", "Redeemed")]
        if events:
            first, last = events[0], events[-1]
            metrics["activity"]["series"][str(sid)]["observed_activity_timestamps"] = {"first": ctx.header(first["blockNumber"])["timestamp"], "last": ctx.header(last["blockNumber"])["timestamp"], "scope": "timestamps of first/last observed activity blocks"}
    ctx.result["coverage"]["collection_complete"] = not ctx.result["errors"] and all(_complete(ctx, key) for key in ledger.event_keys + ledger.cash_keys + ["outcome_transfers:" + token for token in tokens]) and ctx.result["coverage"]["series_discovery"]["discovery_complete"] and fees_cov["complete"]
    ctx.checkpoint()


def _settled(index, hv):
    if hv.get("seriesCount") is None or hv.get("live") is None:
        return None
    return index < hv["seriesCount"] or (index == hv["seriesCount"] and not hv["live"])


def run_house(ctx, args):
    routes, da, ha, ta, dv, hv, decimals = _setup(ctx, "house")
    desk, house, usdg = (routes[key]["address"] for key in ("desk", "house", "usdg"))
    metrics = ctx.result["metrics"]
    series = _discover(ctx, desk, da, dv, all_series=False)
    total_shares, price = hv.get("totalShares"), hv.get("sharePriceWad")
    metrics["house_valuation"] = {
        "share_scale": str(WAD), "price_scale": "raw USDG per 10^18 shares",
        "total_shares": None if total_shares is None else amount(total_shares, 18),
        "share_price_usdg": None if price is None or decimals is None else amount(price, decimals),
        "share_price_accounting_usdg_raw": None if total_shares is None or price is None else str(total_shares * price // WAD),
        "scope": "struck-price accounting indication, not live underwriting liquidation equity; not additive with book/cash",
    }
    current = series.get(dv.get("seriesCount"))
    metrics["house_valuation"]["frontend_capital_display_raw"] = str(current["bookUsdg"]) if current and current["status"] == 1 else _raw(hv.get("activeAssets"))
    metrics["house_valuation"]["frontend_capital_display_basis"] = "open series bookUsdg" if current and current["status"] == 1 else "activeAssets"
    metrics["house_cash_pending_claim_hypothesis"] = _comparison(hv.get("usdg_balance_raw"), None if hv.get("totalPending") is None or hv.get("totalClaimable") is None else hv["totalPending"] + hv["totalClaimable"], False, caveat="diagnostic for live funded Vault; idle active capital, donations and other legs can differ")
    generation = hv.get("generation")
    start_series = hv.get("generationStartSeries")
    # No published generation event or reset semantics permits historical replay.
    gen = ctx.result["coverage"]["generation"] = {
        "current_generation": _raw(generation), "generation_start_series": _raw(start_series),
        "reset_semantics_established": False, "historical_ownership_replay_complete": False,
        "reason": "same-block getters retained; generation boundary/storage reset rules are not established by this ABI",
    }
    roles = defaultdict(list)
    for name in ("sleeve", "treasury"):
        roles[routes[name]["address"]].append(name)
    accounts = metrics["accounts"] = {}
    discovered = set(roles)
    account_cov = ctx.result["coverage"]["house_accounts"] = {
        "discovered_addresses": sorted(discovered), "fully_read_addresses": [],
        "missing_addresses": sorted(discovered), "event_discovery_complete": False,
        "discovered_account_reads_complete": False, "beneficial_ownership_complete": False,
    }
    metrics["ownership"] = {}
    metrics["house_events"] = {"status": "unavailable", "event_counts": {}, "event_labeled_sums_raw": {}}
    metrics["performance"] = {"underwriting_cycles": {}, "struck_price_returns": {}, "realized_share_price_return": None, "reason": "no compatible settled observations established yet; no assumed initial price or APY"}
    internal_accounts = {}

    def ownership():
        sums = Counter()
        pending_known = claims_known = 0
        for account, values in internal_accounts.items():
            category = "fund_controlled" if account in roles else "unattributed"
            if values.get("sharesOf") is not None:
                sums[category + "_shares_raw"] += values["sharesOf"]
            pending = values.get("pendingOf")
            if pending is not None:
                state = _settled(pending["series"], hv)
                if state is False:
                    pending_known += pending["usdg"]
                    sums[category + "_current_pending_raw"] += pending["usdg"]
            claim = values.get("claim_usdg_raw")
            if claim is not None:
                claims_known += claim
            notice = values.get("noticeOf")
            if notice:
                sums["noticed_shares_raw"] += notice["shares"]
        shares_known = sums["fund_controlled_shares_raw"] + sums["unattributed_shares_raw"]
        metrics["ownership"] = {
            "classified_raw": _raw(dict(sums)),
            "fund_controlled_shares": amount(sums["fund_controlled_shares_raw"], 18),
            "unattributed_observed_shares": amount(sums["unattributed_shares_raw"], 18),
            "evidenced_other_controlled_shares_raw": None,
            "total_shares_residual_raw": None if total_shares is None else str(total_shares - shares_known),
            "current_pending_observed_usdg_raw": str(pending_known),
            "total_pending_residual_raw": None if hv.get("totalPending") is None else str(hv["totalPending"] - pending_known),
            "matured_claim_observed_usdg_raw": str(claims_known),
            "total_claimable_residual_raw": None if hv.get("totalClaimable") is None else str(hv["totalClaimable"] - claims_known),
            "same_block": ctx.block, "generation_qualification": gen,
            "scope": "current raw getters, not ERC20 share replay; notice shares are not added to holdings; residual may include unread accounts, notice or generation semantics",
            "unknown_accounts_are_not_proven_external": True,
            "discovered_account_reads_complete": account_cov["discovered_account_reads_complete"],
            "event_discovery_complete": account_cov["event_discovery_complete"],
            "pending_getters_read_complete": all(values.get("pendingOf") is not None for values in internal_accounts.values()) and account_cov["discovered_account_reads_complete"],
            "claim_price_reads_complete": all(values.get("claim_usdg_raw") is not None for values in internal_accounts.values()) and account_cov["discovered_account_reads_complete"],
        }

    def read_account(account):
        values = internal_accounts.setdefault(account, {})
        row = accounts.setdefault(account, {
            "classification": "evidenced_fund_controlled_role" if account in roles else "unattributed_not_proven_external",
            "role_evidence": roles.get(account, []), "block": ctx.block,
            "generation_observed": _raw(generation), "raw_getters": {},
        })
        for method in ("sharesOf", "assetsOf", "pendingOf", "noticeOf"):
            if values.get(method) is None:
                values[method] = _optional(ctx, house, ha, method, (account,))
                row["raw_getters"][method] = _raw(values[method])
                ownership()
                ctx.checkpoint()
        pending, notice, shares = (values.get(name) for name in ("pendingOf", "noticeOf", "sharesOf"))
        if pending is not None:
            settled = _settled(pending["series"], hv)
            row["pending"] = {"raw_usdg": str(pending["usdg"]), "series": pending["series"], "accounting_matured": settled,
                              "currently_queued_usdg_raw": str(pending["usdg"]) if settled is False else "0" if settled is True else None,
                              "caveat": "matured raw pending may persist; not added to shares/assets or totalPending"}
            if pending["usdg"] and settled:
                join = _optional(ctx, house, ha, "joinPriceWad", (pending["series"],))
                row["pending"]["joinPriceWad_raw"] = _raw(join)
        if notice is not None:
            settled = _settled(notice["series"], hv)
            matured = notice["shares"] > 0 and notice["series"] != 0 and settled is True
            row["notice"] = {"raw_shares": str(notice["shares"]), "series": notice["series"], "matured": matured,
                             "maturity_predicate": "n<count or (n==count and not live), with nonzero notice series",
                             "free_shares_ui_raw": None if shares is None or matured else str(shares - notice["shares"]),
                             "generation_compatible": start_series is not None and notice["series"] >= start_series,
                             "assetsOf_claim_overlap_unresolved": True}
            if matured:
                exit_price = _optional(ctx, house, ha, "exitPriceWad", (notice["series"],))
                indication = None if exit_price is None else notice["shares"] * exit_price // WAD
                values["claim_usdg_raw"] = indication if row["notice"]["generation_compatible"] else None
                row["notice"]["exitPriceWad_raw"] = _raw(exit_price)
                row["notice"]["frontend_claim_usdg_raw"] = _raw(indication)
                row["notice"]["cash_paid"] = "not established by getter; consult WithdrawClaimed transfer evidence"
            else:
                values["claim_usdg_raw"] = 0 if settled is not None else None
                row["notice"]["current_price_indication_usdg_raw"] = None if price is None else str(notice["shares"] * price // WAD)
                row["notice"]["final_claim_usdg_raw"] = None if notice["shares"] else "0"
        if all(values.get(method) is not None for method in ("sharesOf", "assetsOf", "pendingOf", "noticeOf")):
            if account not in account_cov["fully_read_addresses"]:
                account_cov["fully_read_addresses"].append(account)
        account_cov["missing_addresses"] = sorted(discovered - set(account_cov["fully_read_addresses"]))
        account_cov["discovered_account_reads_complete"] = not account_cov["missing_addresses"]
        ownership()
        ctx.checkpoint()

    # Canonical fund identities are not left behind a potentially large history scan.
    for account in roles:
        read_account(account)
    ledger = _Evidence(ctx, desk, house, usdg)
    start = ctx.deployment(routes["house"])
    ledger.event_keys = ["house_events"]
    for key in ("house_events", "usdg_outgoing", "usdg_incoming"):
        _planned_scan(ctx, key, start)
    counts, sums = Counter(), Counter()
    funds, settlements = defaultdict(list), defaultdict(list)

    def house_page(page):
        ledger.extend(page)
        for event in page:
            value, name = event["values"], event["event"]
            counts[name] += 1
            if "account" in value:
                discovered.add(value["account"])
            if name == "Funded":
                funds[value["series"]].append(event)
            elif name == "Settled":
                settlements[value["series"]].append(event)
            for field in ("usdg", "shares", "usdgReturned", "exitUsdg", "joinUsdg"):
                if field in value:
                    sums[name + "." + field] += value[field]
        complete = _complete(ctx, "house_events")
        metrics["house_events"] = {"status": "complete_event_scope" if complete else "partial_observed", "event_counts": dict(counts), "event_labeled_sums_raw": _raw(dict(sums)), "event_coverage_complete": complete,
                                   "zero_settlements": "none in selected deployment history" if complete and not settlements else "not established" if not settlements else False,
                                   "cash_status": "event-labeled, consult independent cash reconciliation"}
        account_cov["discovered_addresses"] = sorted(discovered)
        account_cov["missing_addresses"] = sorted(discovered - set(account_cov["fully_read_addresses"]))
        account_cov["event_discovery_complete"] = complete
        account_cov["discovered_account_reads_complete"] = not account_cov["missing_addresses"]
        ownership()
        ledger.publish()

    _scan(ctx, "house_events", house, ha, [], start, house_page)
    # Cash gets an independent bounded scan before unbounded account enumeration.
    _cash_history(ctx, ledger, ta, start, [house])

    def performance():
        expected, matched_keys = ledger.publish()
        transfer_complete = all(_complete(ctx, key) for key in ledger.cash_keys)
        event_complete = _complete(ctx, "house_events")
        for sid in sorted(set(funds) | set(settlements)):
            funding = sum(e["values"]["usdg"] for e in funds[sid])
            returned = sum(e["values"]["usdgReturned"] for e in settlements[sid])
            events = funds[sid] + settlements[sid]
            cycle_keys = [_cash_key(usdg, event, house if event["event"] == "Funded" else desk, desk if event["event"] == "Funded" else house) for event in events]
            cash_matched = bool(events) and all(key in matched_keys and len(expected[key]["events"]) == 1 for key in cycle_keys)
            # Extra Vault/Desk transfers anywhere in the completely scanned
            # interval prevent asserting that a cycle's funding/return was final.
            unexplained = [e for e in ledger.transfers.values() if e["address"] == usdg and {e["values"]["from"], e["values"]["to"]} == {desk, house} and _cash_key(usdg, e, e["values"]["from"], e["values"]["to"]) not in matched_keys]
            ordered = len(funds[sid]) == 1 and len(settlements[sid]) == 1 and (funds[sid][0]["blockNumber"], funds[sid][0]["transactionIndex"], funds[sid][0]["logIndex"]) < (settlements[sid][0]["blockNumber"], settlements[sid][0]["transactionIndex"], settlements[sid][0]["logIndex"])
            established = event_complete and transfer_complete and ordered and cash_matched and not unexplained
            metrics["performance"]["underwriting_cycles"][str(sid)] = {
                "funded_event_raw": str(funding), "returned_event_raw": str(returned),
                "funding_events": len(funds[sid]), "settlement_events": len(settlements[sid]),
                "cash_matched": cash_matched, "event_coverage_complete": event_complete,
                "transfer_history_complete": transfer_complete, "result_established": established,
                "net_underwriting_cash_return_raw": str(returned - funding) if established else None,
                "return_fraction": ratio(Fraction(returned - funding, funding)) if established and funding > 0 else None,
                "scope": "scoped gross returned capital minus funding; investor joins/exits separate; already-netted costs not deducted twice",
                "settlement_observations": [{"raw": _raw(e["values"]), **_event_ref(e)} for e in settlements[sid]],
            }
    performance()
    # Prices are struck observations, never the current price substituted backward.
    factors = []
    for sid, events in sorted(settlements.items()):
        row = {"established": False, "return_fraction": None}
        metrics["performance"]["struck_price_returns"][str(sid)] = row
        if len(events) != 1 or start_series is None or sid - 1 < start_series or sid <= 1:
            row["reason"] = "no unique same-generation preceding struck comparator; initial price is not assumed"
            continue
        previous = sid - 1
        if len(settlements.get(previous, [])) != 1:
            row["reason"] = "preceding completed observation missing; do not bridge a generation or missing period"
            continue
        opening = _optional(ctx, house, ha, "joinPriceWad", (previous,))
        closing = _optional(ctx, house, ha, "exitPriceWad", (sid,))
        row.update({"opening_join_series": previous, "opening_price_raw": _raw(opening), "closing_exit_series": sid, "closing_price_raw": _raw(closing), "generation_observed": _raw(generation)})
        # Current generationStartSeries is the only available boundary evidence.
        # A reset-free historical basis is not established for older generations.
        previous_event = settlements[previous][0]
        ordered = (previous_event["blockNumber"], previous_event["transactionIndex"], previous_event["logIndex"]) < (events[0]["blockNumber"], events[0]["transactionIndex"], events[0]["logIndex"])
        compatible = generation == 0 and ordered and opening is not None and opening > 0 and closing is not None and _complete(ctx, "house_events") and closing == events[0]["values"]["sharePriceWad"] and opening == previous_event["values"]["sharePriceWad"]
        if compatible:
            factor = Fraction(closing, opening)
            row.update({"established": True, "return_fraction": ratio(factor - 1), "compatibility_evidence": "initial generation, complete ordered settlement history, preceding-series join and matching current exit/event price; live adapter comparator convention"})
            first_time = ctx.header(settlements[previous][0]["blockNumber"])["timestamp"]
            last_time = ctx.header(events[0]["blockNumber"])["timestamp"]
            row["elapsed_seconds"] = last_time - first_time
            factors.append((sid, factor))
        else:
            row["reason"] = "missing/nonpositive opening, price mismatch, incomplete history or reset basis not established"
        ctx.checkpoint()
    if factors:
        # Do not chain exit/join factors unless the shared boundary price itself
        # agrees; intervening rebasing or a changed basis is not cash-neutral.
        contiguous = all(factors[i][0] == factors[i - 1][0] + 1 for i in range(1, len(factors)))
        aligned = all(metrics["performance"]["struck_price_returns"][str(factors[i][0])]["opening_price_raw"] == metrics["performance"]["struck_price_returns"][str(factors[i - 1][0])]["closing_price_raw"] for i in range(1, len(factors)))
        if contiguous and aligned:
            factor = Fraction(1)
            for _, value in factors:
                factor *= value
            metrics["performance"]["realized_share_price_return"] = {
                "return_fraction": ratio(factor - 1), "completed_series": [sid for sid, _ in factors],
                "scope": "only this compatible contiguous subperiod, not lifetime performance",
            }
            metrics["performance"]["reason"] = "compatible completed-period factors only; no annualization or investor-specific return"
    if not settlements and _complete(ctx, "house_events"):
        metrics["performance"]["reason"] = "no settled cycles in complete selected-deployment history; realized return is unknown, not 0%"
    for account in sorted(discovered - set(account_cov["fully_read_addresses"])):
        read_account(account)
    ownership()
    ctx.result["coverage"]["collection_complete"] = not ctx.result["errors"] and _complete(ctx, "house_events") and all(_complete(ctx, key) for key in ledger.cash_keys) and account_cov["discovered_account_reads_complete"] and ctx.result["coverage"]["series_discovery"]["discovery_complete"]
    ctx.checkpoint()

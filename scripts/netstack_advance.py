"""Pinned, read-only Advance observations; event labels are not realized returns."""

from collections import defaultdict

from netstack_core import CHAIN_ID, RPC_HOST, ZERO, RpcError, amount, load_json, resolve_routes


POSITION_LIMIT = 128
_EVENTS = ("Opened", "Repaid", "Closed", "Shortfall")
_PARAMS = ("ADVANCE_BPS", "FEE_BPS", "TREASURY_BPS", "TERM",
           "MAX_ADVANCE_PER_POSITION", "MIN_LOCK_NET")
_CAPACITY = ("capacity", "maxAdvance", "halted", "unallocated", "escrowed",
             "inventory", "inventoryNet", "lockedTotal", "treasuryOwed")
_AMOUNT_ROLES = {
    "capacity": {"capacity": "usdg", "maxAdvance": "usdg", "unallocated": "usdg",
                 "escrowed": "usdg", "inventory": "wsnet", "inventoryNet": "net",
                 "lockedTotal": "wsnet", "treasuryOwed": "usdg", "ZAP_CAP_USDG": "usdg"},
    "params": {"MAX_ADVANCE_PER_POSITION": "usdg", "MIN_LOCK_NET": "net"},
}
_UNITS = {"usdg": "USDG", "net": "NET", "snet": "sNET", "wsnet": "wsNET"}
_LIMITS = (
    "Runtime hash match and successful settlement are not verified.",
    "Event amounts are not independently reconciled token transfers; paid includes collateral credit, not just cash.",
    "Borrower collateral is not protocol backing; token custody is not available capacity.",
)
_NO_LIVE = "No live getter observations; current capacity is unknown, not zero."


def _amount_fields(raw, role, decimals):
    # Production inputs are integers; decoded checkpoints may carry exact strings.
    def integer(value):
        if type(value) is int:
            return value
        if isinstance(value, str) and value.removeprefix("-").isascii() and value.removeprefix("-").isdigit():
            return int(value)
        return None

    quantity, precision = integer(raw), integer(decimals)
    formatted = (amount(quantity, precision) if quantity is not None
                 and precision is not None and 0 <= precision <= 255 else None)
    return {"raw": raw, "token": role, "decimals": decimals, "formatted": formatted,
            "display": formatted + " " + _UNITS[role] if formatted is not None and role in _UNITS else None}


def prepare_result(result):
    """One presentation contract for every checkpoint, including pre-RPC failures."""
    metrics, snapshot = result.get("metrics", {}), result.get("snapshot", {})
    coverage = result.setdefault("coverage", {})
    coverage.setdefault("collection_complete", False)
    for key in ("required_missing", "supplemental_missing"):
        if coverage.get(key) is None:
            coverage[key] = []
    reads = metrics.get("read_provenance", [])
    block = snapshot.get("block_number")
    context = metrics.get("read_context", {})
    observed = any(
        row.get("status") == "observed" and row.get("getter") not in (None, "eth_getCode")
        and row.get("contract") is not None and row.get("value") is not None
        and "error" not in row and "error_kind" not in row and block is not None
        and row.get("block", context.get("block") if row.get("context_reference") == "/metrics/read_context" else None) == block
        for row in reads)
    result["verification"] = {
        "live_state_observed": observed,
        "analyzed_runtime_match": "not_checked",
        "zap_halted": {"status": "unknown", "value": None,
                       "reason": "No separate Zap getter; Desk halt governs Desk opening restrictions."},
        "runtime_caveat": "Live getters do not verify runtime equality or successful settlement.",
    }
    limits = result.setdefault("not_proven", [])
    for text in _LIMITS:
        if text not in limits:
            limits.append(text)
    if observed and _NO_LIVE in limits:
        limits.remove(_NO_LIVE)
    elif not observed and _NO_LIVE not in limits:
        limits.append(_NO_LIVE)
    tokens = metrics.get("tokens", {})
    for family, fields in _AMOUNT_ROLES.items():
        values = metrics.get(family, {})
        if values:
            values["amounts"] = {
                name: _amount_fields(values[name], role, tokens.get(role, {}).get("decimals"))
                for name, role in fields.items() if name in values}
    for balance in metrics.get("balances", []):
        fields = _amount_fields(balance.get("raw"), balance.get("token_role"), balance.get("decimals"))
        balance.update(formatted=fields["formatted"], display=fields["display"])


def _event_ref(event):
    return {name: event[name] for name in
            ("blockNumber", "blockHash", "transactionHash", "transactionIndex", "logIndex")}


def _position_row(identifier, value, events, history_complete, term, timestamp):
    opening = events["Opened"][0] if len(events["Opened"]) == 1 else None
    repaid = sum(event["values"]["usdg"] for event in events["Repaid"])
    closed = events["Closed"][0] if len(events["Closed"]) == 1 else None
    estimated_unlock = None if term is None else value["openedAt"] + term
    return {
        "position_id": identifier, "owner": value["owner"],
        "destination": value["destination"], "raw_position": value,
        "original_advance_usdg_raw": None if opening is None else opening["values"]["advance"],
        "opening_ws_locked_raw": None if opening is None else opening["values"]["wsLocked"],
        "opening_event": None if opening is None else _event_ref(opening),
        "original_advance_basis": "Opened.advance event label; not reconstructed from owed/paid or current fees",
        "repaid_usdg_raw": repaid if history_complete else None,
        "observed_repaid_event_subtotal_usdg_raw": repaid,
        "repayment_basis": "Repaid.usdg events, not raw position.paid; transfers not independently reconciled",
        "owed_minus_paid_raw": value["owed"] - value["paid"],
        "owed_minus_paid_interpretation": "Raw arithmetic only; not a receivable valuation or realized profit, including for closed positions",
        "close_event": None if closed is None else {
            "raw": closed["values"], **_event_ref(closed)},
        "shortfall_event_usdg_raw": sum(event["values"]["usdg"] for event in events["Shortfall"]) if history_complete else None,
        "estimated_unlock_at": estimated_unlock,
        "estimated_term_elapsed": None if estimated_unlock is None else timestamp >= estimated_unlock,
        "maturity_basis": "openedAt + pinned live TERM; analyzed explorer runtime embeds a 30-day term, but this collection does not match its code hash or prove close will succeed",
        "unlock_at_getter": None,
        "realized_profit_usdg_raw": None,
        "realized_profit_reason": "Closed flag, owed and paid do not establish realized cash proceeds, costs or profit",
        "history_complete": history_complete,
    }


def _aggregate(rows, complete):
    observed = {
        "position_count": len(rows),
        "open_count": sum(not row["raw_position"]["closed"] for row in rows),
        "closed_count": sum(row["raw_position"]["closed"] for row in rows),
        "ws_locked_raw": sum(row["raw_position"]["wsLocked"] for row in rows),
        "principal_net_raw": sum(row["raw_position"]["principalNet"] for row in rows),
        "owed_raw": sum(row["raw_position"]["owed"] for row in rows),
        "paid_raw": sum(row["raw_position"]["paid"] for row in rows),
        "owed_minus_paid_raw": sum(row["owed_minus_paid_raw"] for row in rows),
        "original_advance_usdg_raw": sum(row["original_advance_usdg_raw"] for row in rows
                                        if row["original_advance_usdg_raw"] is not None),
        "repaid_event_usdg_raw": sum(row["observed_repaid_event_subtotal_usdg_raw"] for row in rows),
    }
    return {
        "inventory_complete": complete,
        "totals": observed.copy() if complete else {key: None for key in observed},
        "observed_subtotals": observed,
        "observed_original_advance_missing_count": sum(row["original_advance_usdg_raw"] is None for row in rows),
        "scope": "Selected Desk positions only. Raw current collateral/owed/paid and historical event-labeled advances/repayments are distinct, non-additive quantities.",
        "realized_profit_usdg_raw": None,
    }


def provenance(ctx):
    """Resolve catalog identity and evidence locally; never observe chain state."""
    routes = resolve_routes("advance")
    contracts = {role: routes[role] for role in ("desk", "zap")}
    source_ids = {entry["source_id"] for record in contracts.values()
                  for entry in record["provenance"]}
    sources = {entry["id"]: entry for entry in load_json("assets/sources.json")["sources"]
               if entry["id"] in source_ids}
    if source_ids != sources.keys():
        raise RpcError("Advance catalog source references are incomplete", kind="package")
    ctx.result["metrics"] = {
        "scope": {"view": "provenance", "chain_id": CHAIN_ID,
                  "evidence_kind": "offline_catalog", "selected_deployment_only": True},
        "contracts": contracts, "sources": sources,
        "provenance": {"reference": "/provenance/analysis"},
    }
    ctx.result["coverage"].update(
        collection_complete=True,
        requested_scope={"scope": "provenance", "collection_complete": True})
    ctx.result["not_proven"].append(
        "Offline catalog lookup: no network requests, current code/state verification or proof of the host-loaded revision.")
    ctx.checkpoint()


def run(ctx, args):
    view = args.view
    if view not in ("positions", "holders", "totals", "capacity", "params"):
        raise RpcError("Unknown Advance view", kind="input")
    routes = resolve_routes("advance")
    interface = load_json(routes["_route"]["interface"])
    desk, zap = routes["desk"]["address"], routes["zap"]["address"]
    da, za, ta = (interface[name] for name in ("desk_abi", "zap_abi", "token_abi"))
    metrics = ctx.result["metrics"]
    required, supplemental = [], []
    metrics.update({
        "scope": {"chain_id": CHAIN_ID, "desk": desk, "zap": zap,
                  "view": view, "snapshot_block": ctx.block,
                  "selected_deployment_only": True, "limits": routes["_route"]["scope"]},
        "provenance": {"reference": "/provenance/analysis"},
        "read_context": {"block": ctx.block, "rpc_origin": "https://" + RPC_HOST},
        "tokens": {}, "identity": {}, "params": {}, "capacity": {}, "balances": [],
        "positions": [], "holders": [], "totals": None,
        "read_provenance": [],
    })
    coverage = ctx.result["coverage"]
    requested = coverage["requested_scope"] = {"scope": view, "collection_complete": False}
    coverage.update(collection_complete=False, required_missing=required,
                    supplemental_missing=supplemental)

    def gap(scope, message, needed=True, kind="unavailable"):
        record = {"scope": scope, "reason": str(message), "kind": kind}
        target = required if needed else supplemental
        if record not in target:
            target.append(record)
            ctx.result["errors"].append({"scope": scope, "error": str(message),
                                         "kind": kind, "required": needed})

    def read(address, abi, method, arguments=(), needed=True):
        entry = {"contract": address, "getter": method, "arguments": list(arguments),
                 "context_reference": "/metrics/read_context",
                 "status": "not_observed"}
        metrics["read_provenance"].append(entry)
        try:
            value = ctx.call(address, abi, method, arguments)
        except RpcError as error:
            entry.update(status="unavailable", error_kind=error.kind)
            gap(method + ":" + address, error, needed, error.kind)
            if error.kind in ("permission", "integrity"):
                raise
            ctx.checkpoint()
            return None
        entry.update(status="observed", value=value)
        ctx.checkpoint()
        return value

    def code(address):
        entry = {"contract": address, "getter": "eth_getCode",
                 "context_reference": "/metrics/read_context", "status": "not_observed"}
        metrics["read_provenance"].append(entry)
        try:
            present = ctx.code(address) not in ("0x", "0x0", "0x00")
        except RpcError as error:
            entry.update(status="unavailable", error_kind=error.kind)
            gap("code:" + address, error, kind=error.kind)
            if error.kind in ("permission", "integrity"):
                raise
            return False
        entry.update(status="observed", code_present=present)
        if not present:
            raise RpcError("No deployed code at pinned block: " + address, kind="integrity")
        return True

    def finish():
        requested.update(collection_complete=not required)
        coverage["collection_complete"] = requested["collection_complete"]
        ctx.checkpoint()

    # Never follow an unexpected pointer or substitute a catalog balance.
    code_ok = {role: code(routes[role]["address"]) for role in
               ("desk", "zap", "usdg", "wsnet", "snet", "net")}
    bindings = ((desk, da, "usdg", "usdg"), (desk, da, "wsNet", "wsnet"),
                (desk, da, "sNet", "snet"), (desk, da, "house", "sleeve"),
                (desk, da, "zap", "zap"), (desk, da, "treasury", "treasury"),
                (zap, za, "desk", "desk"), (zap, za, "house", "sleeve"),
                (zap, za, "usdg", "usdg"), (zap, za, "wsNet", "wsnet"),
                (zap, za, "sNet", "snet"), (zap, za, "net", "net"))
    for address, abi, method, role in bindings:
        value = read(address, abi, method)
        metrics["identity"].setdefault(address, {})[method] = value
        if value is not None and value != routes[role]["address"]:
            raise RpcError("Advance " + method + " differs from canonical " + role, kind="integrity")
    for role in ("usdg", "wsnet", "snet", "net"):
        address = routes[role]["address"]
        token = metrics["tokens"][role] = {"address": address, "code_present": code_ok[role]}
        for method in ("decimals", "symbol", "name"):
            token[method] = read(address, ta, method, needed=method == "decimals")
    metrics["tokens"]["wsnet"]["index"] = {
        "source_contract": routes["snet"]["address"], "getter": "index",
        "raw": read(routes["snet"]["address"], interface["snet_abi"], "index"),
        "basis": "Published live consumer uses sNET.index for wsNET; raw observation, no assumed scale or future rebase",
    }
    if view != "capacity":
        for name in _PARAMS:
            metrics["params"][name] = read(desk, da, name, needed=view == "params" or name == "TERM")
        metrics["params"]["interpretation"] = "Pinned getter values; embedded constants were separately checked in explorer-supplied bytecode, without a pinned runtime hash match in this collection."
    if view != "params":
        for name in _CAPACITY:
            metrics["capacity"][name] = read(desk, da, name, needed=view == "capacity")
        metrics["capacity"]["ZAP_CAP_USDG"] = read(zap, za, "ZAP_CAP_USDG", needed=view == "capacity")
        metrics["capacity"]["zap_halted"] = None
        metrics["capacity"]["halt_scope"] = "halted is the Desk getter; reviewed Zap ABI exposes no separate halted getter"
        metrics["capacity"]["balance_interpretation"] = "Raw getters remain distinct observations. In the analyzed Desk, capacity is unallocated and opening consumes advance plus Treasury reserve; token custody is not lendable capacity. ZAP_CAP_USDG caps USDG input per Zap call, not Desk capacity."
        for holder_role in ("desk", "zap"):
            for token_role in ("usdg", "wsnet"):
                holder, token = routes[holder_role]["address"], routes[token_role]["address"]
                metrics["balances"].append({
                    "holder_role": holder_role, "holder": holder, "token_role": token_role, "token": token,
                    "raw": read(token, ta, "balanceOf", (holder,), needed=False),
                    "decimals": metrics["tokens"][token_role]["decimals"],
                    "basis": "Pinned token custody only; not available capacity, economic ownership or profit"})
    if view in ("params", "capacity"):
        finish()
        return

    expected = read(desk, da, "positionCount")
    discovery = coverage["advance_positions"] = {
        "method": "Complete bounded deployment event scan, unique Opened IDs, pinned positionCount reconciliation",
        "expected_issued_count": expected, "discovered_count": 0,
        "position_limit": POSITION_LIMIT, "event_coverage_complete": False,
        "count_reconciled": False, "collection_complete": False,
    }
    records = defaultdict(lambda: {name: [] for name in _EVENTS})
    metrics["event_history"] = {"coverage_key": "advance_events", "events": [],
                                "complete": False, "event_labels_only": True}
    scan_processed = False
    try:
        start = ctx.deployment(routes["desk"])
        discovery["deployment_block"] = start
        for page in ctx.logs("advance_events", desk, da, list(_EVENTS), start, ctx.block):
            for event in page:
                identifier = event["values"]["id"]
                if identifier not in records and len(records) >= POSITION_LIMIT:
                    raise RpcError("Advance discovered position count exceeds collection limit", kind="coverage")
                records[identifier][event["event"]].append(event)
                metrics["event_history"]["events"].append({"event": event["event"],
                                                           "raw": event["values"], **_event_ref(event)})
            discovery["discovered_count"] = sum(bool(row["Opened"]) for row in records.values())
            ctx.checkpoint()
        scan_processed = True
    except RpcError as error:
        gap("advance_events", error, kind=error.kind)
        if error.kind in ("permission", "integrity"):
            raise
    history_complete = scan_processed and coverage.get("advance_events", {}).get("event_coverage_complete", False)
    metrics["event_history"]["complete"] = history_complete
    discovery["event_coverage_complete"] = history_complete
    discovery["discovered_count"] = sum(bool(row["Opened"]) for row in records.values())
    discovery["count_reconciled"] = expected is not None and discovery["discovered_count"] == expected
    if not history_complete:
        gap("advance_events", "Deployment-to-snapshot event coverage is incomplete")
    if not discovery["count_reconciled"]:
        gap("advance_positions", "Unique Opened IDs do not reconcile with pinned positionCount")

    def publish():
        complete = (not required and history_complete and discovery["count_reconciled"]
                    and len(metrics["positions"]) == len(records)
                    and all(len(events["Opened"]) == 1 and len(events["Closed"]) <= 1
                            for events in records.values())
                    and all(row["original_advance_usdg_raw"] is not None
                            for row in metrics["positions"]))
        discovery["collection_complete"] = complete
        metrics["totals"] = _aggregate(metrics["positions"], complete)
        holders = defaultdict(list)
        for row in metrics["positions"]:
            holders[row["owner"]].append(row)
        metrics["holders"] = [dict(owner=owner, position_ids=[row["position_id"] for row in rows],
                                   ownership_scope="Observed position owner, not beneficial owner or necessarily USDG destination",
                                   **_aggregate(rows, complete)) for owner, rows in sorted(holders.items())]

    for identifier, events in sorted(records.items()):
        ctx.check()
        if len(events["Opened"]) != 1:
            gap("position:" + str(identifier), "No unique Opened event for discovered position")
            continue
        if len(events["Closed"]) > 1:
            gap("position:" + str(identifier), "Multiple Closed events; settlement interpretation unresolved")
        value = read(desk, da, "position", (identifier,))
        if value is None:
            continue
        if value["owner"] == ZERO:
            gap("position:" + str(identifier), "Opened event has no current nonzero position owner", kind="integrity")
            continue
        if value["owner"] != events["Opened"][0]["values"]["owner"]:
            gap("position:" + str(identifier), "Current owner differs from Opened owner; holder attribution unresolved", kind="integrity")
            continue
        row = _position_row(identifier, value, events, history_complete,
                            metrics["params"].get("TERM"), ctx.timestamp)
        metrics["positions"].append(row)
        publish()
        ctx.checkpoint()
        row["unlock_at_getter"] = read(desk, da, "unlockAt", (identifier,), needed=False)
        observed_advance = read(desk, da, "advanceOf", (identifier,), needed=False)
        row["advance_of_getter_usdg_raw"] = observed_advance
        row["advance_event_getter_agree"] = None if observed_advance is None else observed_advance == row["original_advance_usdg_raw"]
        if row["advance_event_getter_agree"] is False:
            gap("position:" + str(identifier), "advanceOf differs from Opened.advance; original advance unresolved")
            row["original_advance_usdg_raw"] = None
        publish()
        ctx.checkpoint()
    publish()
    if not discovery["collection_complete"]:
        gap("advance_positions", "Not every dynamically discovered position was fully observed")
    finish()

"""Bounded, same-block NetLong discovery and disjoint futures/margin accounting."""

import hashlib
import json
import re

from netstack_core import ZERO, RpcError, amount, load_json, resolve_routes, serialize_result

WAD = 10**18
MARKET_LIMIT = 32
POSITION_LIMIT = 128


def quantity(raw, decimals, unit):
    return {"raw": str(raw) if raw is not None else None, "decimals": decimals,
            "unit": unit, "formatted": amount(raw, decimals) if raw is not None else None}


def sides(long, short):
    return {name: quantity(value, 18, "USD-denominated WAD") for name, value in
            (("long", long), ("short", short), ("gross", long + short), ("net", long - short))}


def _problem(ctx, scope, error):
    if error.kind in ("permission", "integrity"):
        raise error
    ctx.result["errors"].append({"scope": scope, "kind": error.kind, "message": str(error)})


def _read(ctx, address, abi, method, args=()):
    value = ctx.call(address, abi, method, args)
    ctx.result["metrics"]["reads"].append({"address": address, "function": method,
                                            "arguments": list(args), "value": value,
                                            "block": ctx.block})
    return value


def _optional(ctx, address, abi, method, args=()):
    try:
        return _read(ctx, address, abi, method, args)
    except RpcError as error:
        _problem(ctx, address + ":" + method, error)
        return None


def _identity(ctx, address, models, family, *, block=None):
    """Match only reviewed runtime bytes; selectors or an ABI are not identity."""
    raw = bytes.fromhex(ctx.code(address, block)[2:] if block is not None else ctx.code(address)[2:])
    observed = hashlib.sha256(raw).hexdigest()
    evidence = {"address": address, "runtime_sha256": observed, "family": family,
                "status": "unsupported", "model": None, "block": ctx.block if block is None else block}
    ctx.result["metrics"]["implementation_checks"].append(evidence)
    for model in models:
        if model["family"] != family or len(raw) != model["runtime_bytes"]:
            continue
        normalized = bytearray(raw)
        # Only constructor-reviewed immutable locations can be masked. The
        # remaining runtime, including metadata, must match exactly.
        for offset, length in model.get("immutable_ranges", []):
            if type(offset) is not int or type(length) is not int or offset < 0 or length <= 0 or offset + length > len(raw):
                raise RpcError("Invalid packaged immutable range", kind="package")
            normalized[offset:offset + length] = bytes(length)
        groups = model.get("immutable_groups", [])
        if model.get("immutable_ranges") and not groups:
            raise RpcError("Masked runtime lacks constructor consistency groups", kind="package")
        consistent = True
        for group in groups:
            words = [raw[offset:offset + 32] for offset in group["offsets"]]
            expected = group.get("expected_word")
            if (not words or any(len(word) != 32 or word != words[0] for word in words)
                    or (expected is not None and words[0].hex() != expected)
                    or (expected is None and not any(words[0]))):
                consistent = False
                break
        if not consistent:
            continue
        if hashlib.sha256(normalized).hexdigest() == model["normalized_sha256"]:
            evidence.update(status="matched", model=model["id"], source_id=model["source_id"],
                            runtime_source_url=model.get("runtime_source_url"))
            return model
    raise RpcError("Pinned runtime is not a reviewed supported implementation", kind="unsupported")


def _enumerate(ctx, address, abi, count_method, at_method, coverage):
    coverage.update(collection_complete=False, count=None, discovered=0, limit=MARKET_LIMIT)
    count = _read(ctx, address, abi, count_method)
    coverage["count"] = count
    found = []
    for index in range(min(count, MARKET_LIMIT)):
        try:
            value = _read(ctx, address, abi, at_method, (index,))
            if value == ZERO or value in found:
                raise RpcError("Zero or duplicate market enumeration entry", kind="evidence")
            found.append(value)
            coverage["discovered"] = len(found)
            coverage["addresses"] = list(found)
            ctx.checkpoint()
        except RpcError as error:
            _problem(ctx, count_method + ":" + str(index), error)
    coverage["collection_complete"] = len(found) == count
    if count > MARKET_LIMIT:
        coverage["missing_reason"] = "market_limit"
    return found


def select_markets(rows, query, discovery_complete):
    if query is None:
        return rows
    is_address = bool(re.fullmatch(r"0x[0-9a-fA-F]{40}", query))
    matches = [row for row in rows if (row["address"].lower() == query.lower() if is_address
                                      else (row.get("symbol") or "").casefold() == query.casefold())]
    if len(matches) > 1:
        raise RpcError("Market symbol is ambiguous; select --product or a market address", kind="input")
    if not discovery_complete:
        raise RpcError("Incomplete market discovery cannot establish an unambiguous selection", kind="unavailable")
    if not matches:
        raise RpcError("Requested market was not found in the selected on-chain registries", kind="input")
    return matches


def prepare_result(result):
    """Project snapshot-qualified output without demoting live collection evidence."""
    metrics = result.get("metrics", {})
    if "aggregates" not in metrics:
        return result
    snapshot = result.get("snapshot", {})
    invalid = (snapshot.get("recheck_status") == "mismatch"
               or snapshot.get("confirmation") == "invalid"
               or any(error.get("kind") == "integrity" for error in result.get("errors", [])))
    # Exposure qualifies one pinned snapshot; interval revenue additionally
    # requires two boundary rechecks and treats terminal permission as invalid.
    valid = snapshot.get("recheck_status") == "confirmed" and not invalid
    confirmation = "invalid" if invalid else ("confirmed" if valid else "unconfirmed")

    def qualify(value):
        projected = dict(value, snapshot_valid=valid, snapshot_confirmation=confirmation)
        for key in ("collection_complete", "positions_complete", "event_coverage_complete"):
            if key in value:
                projected[key] = bool(valid and value[key])
        return projected

    def coverage_flags(value):
        if not isinstance(value, dict):
            return value
        projected = {key: coverage_flags(child) for key, child in value.items()}
        if any(key in value for key in ("collection_complete", "event_coverage_complete", "snapshot_valid")):
            return qualify(projected)
        return projected

    aggregates = {}
    for product, aggregate in metrics["aggregates"].items():
        projected = qualify(aggregate)
        for key, value in aggregate.items():
            if isinstance(value, dict) and "total" in value:
                projected[key] = qualify(value)
                projected[key]["total"] = value["total"] if valid and value["collection_complete"] else None
        aggregates[product] = projected
    # Context checkpoints share nested objects with the active collector. Only
    # copy changed shells; raw reads, positions and observed subtotals stay intact.
    return dict(result, metrics=dict(metrics, aggregates=aggregates,
                                    markets=[qualify(row) for row in metrics.get("markets", [])]),
                coverage=coverage_flags(result.get("coverage", {})))


def summarize(text, checkpoint_status):
    result = json.loads(text)
    metrics = result.get("metrics", {})
    result["metrics"] = {key: value for key, value in metrics.items() if key not in ("reads",)}
    for row in result["metrics"].get("markets", []):
        if "positions" in row:
            row["observed_position_count"] = len(row.pop("positions"))
    result["presentation"] = {"detail": "summary", "full_checkpoint": checkpoint_status,
                              "omitted": ["metrics.reads", "metrics.markets[].positions"]}
    return serialize_result(result)


def _discover_ids(ctx, address, abi, event, field, record, key):
    identifiers = set()
    coverage = ctx.result["coverage"]
    start = ctx.creation_block(address, record)
    bounded = True
    try:
        for page in ctx.logs(key, address, abi, [event], start, ctx.block):
            for row in page:
                value = row["values"][field]
                if value not in identifiers and len(identifiers) >= POSITION_LIMIT:
                    bounded = False
                    break
                identifiers.add(value)
            coverage[key].update(identifiers_discovered=len(identifiers),
                                 identifier_limit=POSITION_LIMIT)
            ctx.checkpoint()
            if not bounded:
                coverage[key]["missing_reason"] = "position_limit"
                break
    except RpcError as error:
        _problem(ctx, key, error)
    coverage.setdefault(key, {"event_coverage_complete": False})
    coverage[key]["identifier_limit"] = POSITION_LIMIT
    complete = bounded and coverage[key].get("event_coverage_complete", False)
    coverage[key]["collection_complete"] = complete
    return sorted(identifiers), complete


def _futures_snapshot(ctx, row, source, routes):
    abi, vault_abi = source["futures_abi"], source["vault_abi"]
    address = row["address"]
    model = _identity(ctx, address, source["models"], "futures")
    row["model"] = model["id"]
    for method, role in (("vault", "vault"), ("oracle", "oracle")):
        if _read(ctx, address, abi, method) != routes[role]["address"]:
            raise RpcError("Futures binding differs from selected canonical route", kind="evidence")
    config = _read(ctx, routes["vault"]["address"], vault_abi, "desks", (address,))
    row["vault_registration"] = config
    if config["registered"] is not True:
        raise RpcError("Enumerated futures desk is not registered", kind="evidence")
    long = _read(ctx, address, abi, "oiLongUsdWad")
    short = _read(ctx, address, abi, "oiShortUsdWad")
    row["entry_notional"] = sides(long, short)
    row["vault_oi_residual_wad"] = str(config["oiUsdWad"] - long - short)
    row["vault_skew_residual_wad"] = str(config["skewUsdWad"] - long + short)
    row["last_posted_mark"] = _optional(ctx, address, abi, "lastMark")
    mark = row["last_posted_mark"]
    row["mark_age_seconds"] = ctx.timestamp - mark["observedAt"] if mark else None
    row["mark_basis"] = "Last posted desk mark at the pinned block, not an independently fresh executable quote."
    if model.get("stream_market"):
        row["price_dependencies"] = {
            method: _read(ctx, address, abi, method)
            for method in ("streamId", "verifierProxy", "tapeVerifier")}
        row["price_dependency_scope"] = "Reported bindings only; no independent authentication of posted market prices."
    row["status"] = "entry_notional_observed"
    ctx.checkpoint()


def _futures_positions(ctx, row, source, record):
    abi, address = source["futures_abi"], row["address"]
    identifiers, complete = _discover_ids(ctx, address, abi, "Filled", "trader", record,
                                          "futures_positions:" + address)
    positions = row["positions"] = []
    long = short = marked_long = marked_short = 0
    mark = row["last_posted_mark"]
    price = mark["priceWad"] if mark else 0
    pricing_complete = price > 0 and mark["observedAt"] <= ctx.timestamp
    for trader in identifiers:
        try:
            value = _read(ctx, address, abi, "positions", (trader,))
            if value["sizeUsdWad"] == 0:
                continue
            entry = value["entryPriceWad"]
            if entry <= 0:
                raise RpcError("Nonempty futures position has zero entry price", kind="evidence")
            size = value["sizeUsdWad"]
            marked = size * price // entry if pricing_complete else None
            positions.append({"trader": trader, "is_long": value["isLong"],
                              "entry_notional": quantity(size, 18, "USD-denominated WAD"),
                              "entry_price_wad": str(entry),
                              "marked_notional": quantity(marked, 18, "USD-denominated WAD")})
            if value["isLong"]:
                long += size
                marked_long += marked or 0
            else:
                short += size
                marked_short += marked or 0
            row["observed_position_entry_subtotal"] = sides(long, short)
            row["observed_position_mark_subtotal"] = sides(marked_long, marked_short) if pricing_complete else None
            ctx.checkpoint()
        except RpcError as error:
            complete = False
            _problem(ctx, address + ":positions", error)
    expected = row["entry_notional"]
    reconciled = long == int(expected["long"]["raw"]) and short == int(expected["short"]["raw"])
    complete = complete and reconciled
    if long == short == 0 and complete:
        pricing_complete = True
    row["position_entry_reconciliation"] = {
        "matches": reconciled, "long_residual_wad": str(long - int(expected["long"]["raw"])),
        "short_residual_wad": str(short - int(expected["short"]["raw"]))}
    row["positions_complete"] = complete
    row["missing_coverage"] = [
        reason for condition, reason in (
            (not complete, "Current position inventory is incomplete or does not reconcile to entry OI."),
            (not pricing_complete, "A positive, non-future-dated last posted mark is unavailable."),
            (row["vault_oi_residual_wad"] != "0" or row["vault_skew_residual_wad"] != "0",
             "Desk entry OI does not reconcile to its vault registration."))
        if condition]
    row["mark_notional"] = sides(marked_long, marked_short) if complete and pricing_complete else None
    row["collection_complete"] = bool(complete and pricing_complete
                                       and row["vault_oi_residual_wad"] == "0"
                                       and row["vault_skew_residual_wad"] == "0")
    row["status"] = "observed" if row["collection_complete"] else "partial"


def _margin_snapshot(ctx, row, source, routes):
    abi, token_abi = source["margin_abi"], source["token_abi"]
    desk, token = routes["margin"]["address"], row["address"]
    listing = _read(ctx, desk, abi, "listings", (token,))
    row["listing"] = listing
    row["measurement_age_seconds"] = ctx.timestamp - listing["measuredAt"]
    decimals = _read(ctx, token, token_abi, "decimals")
    if decimals != listing["tokenDecimals"]:
        raise RpcError("Token precision differs from pinned listing", kind="evidence")
    row["decimals"] = decimals
    row["entry_notional"] = quantity(listing["notionalUsdWad"], 18, "USD-denominated WAD")
    row["cap_used"] = quantity(listing["capUsedWad"], 18, "USD-denominated WAD")
    row["opens_allowed"] = _optional(ctx, desk, abi, "opensAllowed", (token,))
    row["marks"] = _optional(ctx, desk, abi, "marks", (token,))
    row["desk_token_custody"] = quantity(_read(ctx, token, token_abi, "balanceOf", (desk,)),
                                         decimals, token)
    row["status"] = "listing_observed"
    row["positions"] = []
    ctx.checkpoint()


def _margin_positions(ctx, rows, source, routes):
    abi, desk = source["margin_abi"], routes["margin"]["address"]
    next_id = _read(ctx, desk, abi, "nextPositionId")
    if next_id < 1:
        raise RpcError("Invalid next margin position identifier", kind="evidence")
    count = next_id - 1
    history_complete = count <= POSITION_LIMIT
    ctx.result["coverage"]["margin_positions"] = {
        "collection_complete": False, "position_count": count,
        "position_limit": POSITION_LIMIT, "positions_read": 0,
        "missing_id_range": [POSITION_LIMIT + 1, count] if count > POSITION_LIMIT else None,
        "discovery": "Contiguous allocated IDs 1 <= id < nextPositionId; deleted slots are read, not omitted."}
    identifiers = range(1, min(count, POSITION_LIMIT) + 1)
    selected = {row["address"]: row for row in rows}
    registered_tokens = {row["address"] for row in ctx.result["metrics"]["discovered_markets"]
                         if row["product"] == "margin"}
    totals = {address: {"units": 0, "debt": 0, "shares": 0, "entry": 0, "marked": 0,
                        "complete": history_complete, "pricing_complete": True}
              for address in selected}
    for identifier in identifiers:
        try:
            value = _read(ctx, desk, abi, "positions", (identifier,))
            ctx.result["coverage"]["margin_positions"]["positions_read"] += 1
            token = value["token"]
            if value["trader"] == ZERO:
                continue
            if token not in registered_tokens:
                raise RpcError("Allocated margin position references a non-enumerated token", kind="evidence")
            if value["state"] not in (1, 2, 3):
                raise RpcError("Unsupported margin position state", kind="unsupported")
            if token not in selected:
                continue
            row, total = selected[token], totals[token]
            units = _read(ctx, desk, abi, "unitsOf", (identifier,))
            debt = _read(ctx, desk, abi, "debtUsdg", (identifier,))
            marks = row["marks"]
            priced = bool(marks and marks["twapLive"] and marks["twapPriceWad"] > 0 and marks["spotPriceWad"] > 0)
            marked = units * min(marks["twapPriceWad"], marks["spotPriceWad"]) // 10**row["decimals"] if priced else (0 if units == 0 else None)
            total["units"] += units
            total["debt"] += debt
            total["shares"] += value["shares"]
            total["entry"] += value["notionalUsdWad"]
            total["marked"] += marked or 0
            total["pricing_complete"] = total["pricing_complete"] and marked is not None
            row["positions"].append({"id": identifier, "trader": value["trader"], "state": value["state"],
                                     "state_label": {1: "pending-buy", 2: "open", 3: "pending-sell"}[value["state"]],
                                     "units": quantity(units, row["decimals"], token),
                                     "debt": quantity(debt, 6, "USDG"),
                                     "entry_notional": quantity(value["notionalUsdWad"], 18, "USD-denominated WAD"),
                                     "marked_token_exposure": quantity(marked, 18, "USD-denominated WAD")})
            row["observed_position_debt_subtotal"] = quantity(total["debt"], 6, "USDG")
            row["observed_position_units_subtotal"] = quantity(total["units"], row["decimals"], token)
            row["observed_position_mark_subtotal"] = quantity(
                total["marked"] if total["pricing_complete"] else None, 18, "USD-denominated WAD")
            ctx.checkpoint()
        except RpcError as error:
            # A failed position read cannot safely be assigned to any token.
            for total in totals.values():
                total["complete"] = False
            _problem(ctx, desk + ":position:" + str(identifier), error)
    for address, row in selected.items():
        total = totals[address]
        shares_match = total["shares"] == row["listing"]["totalShares"]
        row["position_share_reconciliation"] = {
            "matches": shares_match, "residual_raw": str(total["shares"] - row["listing"]["totalShares"])}
        row["position_entry_residual_wad"] = str(total["entry"] - row["listing"]["notionalUsdWad"])
        complete = total["complete"] and shares_match
        row["positions_complete"] = complete
        row["missing_coverage"] = [
            reason for condition, reason in (
                (not complete, "Position IDs are incomplete or position shares do not reconcile."),
                (not total["pricing_complete"], "Nonempty token exposure lacks positive live TWAP/spot pricing."))
            if condition]
        row["debt"] = quantity(total["debt"] if complete else None, 6, "USDG")
        row["token_units"] = quantity(total["units"] if complete else None, row["decimals"], address)
        row["marked_token_exposure"] = quantity(
            total["marked"] if complete and total["pricing_complete"] else None, 18, "USD-denominated WAD")
        row["collection_complete"] = complete and total["pricing_complete"]
        row["status"] = "observed" if row["collection_complete"] else "partial"
    ctx.result["coverage"]["margin_positions"]["collection_complete"] = (
        history_complete and all(total["complete"] for total in totals.values()))


def _discover_futures(ctx, source, routes):
    coverage = ctx.result["coverage"].setdefault("futures_discovery", {"collection_complete": False})
    _identity(ctx, routes["vault"]["address"], source["models"], "vault")
    addresses = _enumerate(ctx, routes["vault"]["address"], source["vault_abi"],
                           "deskCount", "deskAt", coverage)
    ctx.result["metrics"]["vault_entry_notional"] = quantity(
        _read(ctx, routes["vault"]["address"], source["vault_abi"], "totalOiUsdWad"),
        18, "USD-denominated WAD")
    labels = {routes[item["route"]]["address"]: item for item in routes["_route"]["futures_labels"]}
    return [{"product": "futures", "address": address, "symbol": labels.get(address, {}).get("symbol"),
             "symbol_source": source["source_id"] if address in labels else None,
             "collection_complete": False, "status": "discovered"}
            for address in addresses]


def _discover_margin(ctx, source, routes):
    coverage = ctx.result["coverage"].setdefault("margin_discovery", {"collection_complete": False})
    for role, family in (("margin", "margin"), ("pot", "pot"), ("twap", "twap")):
        _identity(ctx, routes[role]["address"], source["models"], family)
    for library in source["margin_libraries"]:
        _identity(ctx, library["address"], source["models"], library["family"])
    for role, abi_key, method, expected in (
            ("margin", "margin_abi", "pot", "pot"),
            ("margin", "margin_abi", "marginOracle", "oracle"),
            ("margin", "margin_abi", "twapSource", "twap"),
            ("margin", "margin_abi", "usdg", "usdg"),
            ("pot", "pot_abi", "desk", "margin"),
            ("pot", "pot_abi", "usdg", "usdg")):
        if _read(ctx, routes[role]["address"], source[abi_key], method) != routes[expected]["address"]:
            raise RpcError("Margin binding differs from selected canonical route", kind="evidence")
    if _read(ctx, routes["usdg"]["address"], source["token_abi"], "decimals") != 6:
        raise RpcError("Margin model requires six-decimal USDG", kind="unsupported")
    addresses = _enumerate(ctx, routes["margin"]["address"], source["margin_abi"],
                           "tokenCount", "tokenAt", coverage)
    rows = []
    for address in addresses:
        symbol = _optional(ctx, address, source["token_abi"], "symbol")
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", symbol):
            symbol = None
        rows.append({"product": "margin", "address": address, "symbol": symbol,
                     "symbol_source": "pinned token.symbol()", "collection_complete": False,
                     "status": "discovered"})
    return rows


def _totals(rows, product, discovery_complete):
    selected = [row for row in rows if row["product"] == product]
    complete = discovery_complete and all(row.get("collection_complete", False) for row in selected)
    result = {"collection_complete": complete, "market_count": len(selected)}
    if product == "futures":
        for key in ("entry_notional", "mark_notional"):
            values = [row[key] for row in selected if row.get(key)]
            observed = [row.get(key) or row.get("observed_position_mark_subtotal")
                        for row in selected] if key == "mark_notional" else values
            observed = [value for value in observed if value is not None]
            subtotal = (sides(sum(int(value["long"]["raw"]) for value in observed),
                              sum(int(value["short"]["raw"]) for value in observed))
                        if observed or (discovery_complete and not selected) else None)
            field_complete = (discovery_complete and len(values) == len(selected)
                              and all(row.get("vault_oi_residual_wad") == "0"
                                      and row.get("vault_skew_residual_wad") == "0" for row in selected))
            result[key] = {"total": subtotal if field_complete else None,
                           "observed_subtotal": subtotal, "collection_complete": field_complete}
    else:
        for key, precision, unit in (("entry_notional", 18, "USD-denominated WAD"),
                                      ("debt", 6, "USDG"),
                                      ("marked_token_exposure", 18, "USD-denominated WAD")):
            values = [row[key] for row in selected if row.get(key, {}).get("raw") is not None]
            fallback = {"debt": "observed_position_debt_subtotal",
                        "marked_token_exposure": "observed_position_mark_subtotal"}.get(key)
            observed = [row[key] if row.get(key, {}).get("raw") is not None else row.get(fallback)
                        for row in selected]
            observed = [value for value in observed if value is not None and value.get("raw") is not None]
            subtotal = (sum(int(value["raw"]) for value in observed)
                        if observed or (discovery_complete and not selected) else None)
            field_complete = discovery_complete and len(values) == len(selected)
            result[key] = {"total": quantity(subtotal, precision, unit) if field_complete else None,
                           "observed_subtotal": quantity(subtotal, precision, unit) if subtotal is not None else None,
                           "collection_complete": field_complete}
    return result


def run(ctx, args):
    routes = resolve_routes("netlong")
    source = load_json(routes["_route"]["interface"])
    metrics = ctx.result["metrics"]
    metrics.update(scope={"product": args.product, "market": args.market, "block": ctx.block,
                          "selected_deployments_only": True,
                          "source_id": source["source_id"], "interface": routes["_route"]["interface"],
                          "no_cross_product_total_oi": True},
                   interface_evidence={key: source[key] for key in
                                       ("source_id", "source_url", "source_sha256", "reviewed_on")},
                   reads=[], implementation_checks=[], markets=[], aggregates={})
    coverage = ctx.result["coverage"]
    coverage["collection_complete"] = False
    ctx.result["not_proven"].extend([
        "Runtime matching is byte identity/template evidence, not full source verification, an audit, or successful settlement.",
        "Futures stored entry OI, last-posted-mark notional, margin token exposure and USDG debt are distinct non-additive quantities.",
        "A last posted futures mark is not guaranteed fresh, independently correct or executable; age is reported.",
        "Margin marks use the lower of live TWAP and spot; neither valuation guarantees proceeds or dollar parity of USDG.",
        "Registry enumeration covers selected deployments, not superseded programs, hidden beneficial owners or all future implementations.",
        "Event completeness assumes no silent provider omission; unknown desk creation search assumes monotonic code existence.",
    ])
    ctx.checkpoint()
    _identity(ctx, routes["oracle"]["address"], source["models"], "oracle")
    products = ("futures", "margin") if args.product == "all" else (args.product,)
    discovered = []
    for product in products:
        try:
            discover = _discover_futures if product == "futures" else _discover_margin
            found = discover(ctx, source, routes)
            discovered.extend(found)
            metrics["markets"].extend(found)
        except RpcError as error:
            coverage.setdefault(product + "_discovery", {})["collection_complete"] = False
            _problem(ctx, product + ":discovery", error)
        ctx.checkpoint()
    discovery_complete = all(coverage.get(product + "_discovery", {}).get("collection_complete", False)
                             for product in products)
    if args.market and not re.fullmatch(r"0x[0-9a-fA-F]{40}", args.market):
        if any(row.get("symbol") is None for row in discovered):
            raise RpcError("Unknown symbols prevent proving symbol-query uniqueness; use an address", kind="unavailable")
    selected = select_markets(discovered, args.market, discovery_complete)
    # Keep discovery evidence even when the requested market filters accounting.
    metrics["discovered_markets"] = [{key: row[key] for key in ("product", "address", "symbol")}
                                      for row in discovered]
    metrics["markets"] = selected
    accounting_products = tuple(product for product in products
                                if args.market is None or any(row["product"] == product for row in selected))
    for row in selected:
        try:
            if row["product"] == "futures":
                _futures_snapshot(ctx, row, source, routes)
            else:
                _margin_snapshot(ctx, row, source, routes)
        except RpcError as error:
            row["status"] = "unsupported" if error.kind == "unsupported" else "partial"
            _problem(ctx, row["address"], error)
        ctx.checkpoint()
    if "margin" in accounting_products and coverage.get("margin_discovery", {}).get("collection_complete"):
        pot = routes["pot"]["address"]
        metrics["lending_account"] = {"address": pot, "scope": "Whole selected pot, not filtered to --market.",
                                       "principal": quantity(_optional(ctx, pot, source["pot_abi"], "totalPrincipalUsdg"), 6, "USDG"),
                                       "debt": quantity(_optional(ctx, pot, source["pot_abi"], "totalDebtUsdg"), 6, "USDG")}
        ctx.checkpoint()
    for row in selected:
        if row["product"] != "futures" or row["status"] != "entry_notional_observed":
            continue
        record = next((record for key, record in routes.items() if key != "_route"
                       and isinstance(record, dict) and record.get("address") == row["address"]), None)
        try:
            _futures_positions(ctx, row, source, record)
        except RpcError as error:
            row["status"] = "partial"
            _problem(ctx, row["address"] + ":position_inventory", error)
        ctx.checkpoint()
    margin_rows = [row for row in selected if row["product"] == "margin" and row["status"] == "listing_observed"]
    if margin_rows:
        try:
            _margin_positions(ctx, margin_rows, source, routes)
        except RpcError as error:
            _problem(ctx, "margin:position_inventory", error)
        ctx.checkpoint()
    for product in accounting_products:
        metrics["aggregates"][product] = _totals(
            selected, product, coverage.get(product + "_discovery", {}).get("collection_complete", False))
    if args.market is None and metrics["aggregates"].get("futures", {}).get("entry_notional", {}).get("total"):
        observed = int(metrics["aggregates"]["futures"]["entry_notional"]["total"]["gross"]["raw"])
        expected = int(metrics["vault_entry_notional"]["raw"])
        metrics["vault_entry_reconciliation"] = {"residual_wad": str(observed - expected), "matches": observed == expected}
        if observed != expected:
            aggregate = metrics["aggregates"]["futures"]
            aggregate["collection_complete"] = False
            for key in ("entry_notional", "mark_notional"):
                aggregate[key].update(total=None, collection_complete=False)
            _problem(ctx, "futures:vault_entry_reconciliation",
                     RpcError("Desk entry OI differs from vault total OI", kind="evidence"))
    coverage["collection_complete"] = (discovery_complete
                                        and all(row["collection_complete"] for row in selected)
                                        and not ctx.result["errors"])
    coverage["missing_markets"] = [{"product": row["product"], "address": row["address"], "status": row["status"]}
                                   for row in selected if not row["collection_complete"]]
    ctx.checkpoint()

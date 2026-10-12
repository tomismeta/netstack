"""Bounded, dual-boundary NetLong accounting inputs, never protocol profit."""

import hashlib
import json

from netstack_core import (MAX_LOG_BLOCKS, TRANSFER_TOPIC, ZERO, RpcError, _integer,
                           _quantity, amount, decode_event, load_json, resolve_routes,
                           serialize_result)
from netstack_netlong import MARKET_LIMIT, _identity
from netstack_receipts import _TRANSFER, _boundary, _failure, load_catalog

ASSETS = (("wsnet", 18, "wsNET"), ("usdg", 6, "USDG"), ("net", 9, "NET"))
ASSET_METADATA = {key: (decimals, unit) for key, decimals, unit in ASSETS}
ENDPOINTS = ("vault", "pot", "futures_router", "margin_router", "treasury")
SIDES = ("opening", "closing")


def quantity(raw, decimals, unit):
    raw = int(raw) if raw is not None else None
    return {"raw": str(raw) if raw is not None else None, "decimals": decimals,
            "unit": unit, "formatted": amount(raw, decimals)
            if raw is not None and decimals is not None else None}


def _read_many(ctx, specs, side, block):
    """Retain guarded batch successes and failures without retrying failed reads."""
    values = []
    for offset in range(0, len(specs), 20):
        part = specs[offset:offset + 20]
        answers = ctx.calls(part, block=block, allow_errors=True)
        for (address, abi, method, args), value in zip(part, answers):
            if isinstance(value, RpcError):
                _failure(ctx, value, "boundary_read", side=side, address=address, function=method)
                value = None
            ctx.result["metrics"]["reads"].append({"address": address, "function": method,
                "arguments": list(args), "value": value, "block": block, "side": side})
            values.append(value)
        ctx.checkpoint()
    return values


def _read(ctx, address, abi, method, side, block, args=()):
    return _read_many(ctx, [(address, abi, method, args)], side, block)[0]


def _model(ctx, address, source, family, side, block):
    row = {"address": address, "family": family, "side": side, "block": block,
           "status": "unsupported", "model": None}
    ctx.result["metrics"]["entities"].append(row)
    try:
        model = _identity(ctx, address, source["models"], family, block=block)
    except RpcError as error:
        _failure(ctx, error, "implementation", side=side, address=address, family=family)
        return None
    row.update(status="matched", model=model["id"])
    return model


def _bindings(ctx, specs, side, block):
    answers = _read_many(ctx, [(address, abi, method, ()) for address, abi, method, expected in specs], side, block)
    for (address, abi, method, expected), observed in zip(specs, answers):
        ctx.result["metrics"]["bindings"].append({"side": side, "block": block, "address": address,
            "function": method, "observed": observed, "expected": expected, "matches": observed == expected})
        if observed is not None and observed != expected:
            _failure(ctx, RpcError("Live binding differs from the canonical revenue route", kind="evidence"),
                     "binding", side=side, address=address, function=method)


def _enumerate(ctx, address, abi, count_method, at_method, side, block, family):
    row = ctx.result["metrics"]["discovery"][side][family]
    count = _read(ctx, address, abi, count_method, side, block)
    row["count"] = count
    if count is None:
        return []
    values = _read_many(ctx, [(address, abi, at_method, (index,))
                             for index in range(min(count, MARKET_LIMIT))], side, block)
    found = []
    for index, value in enumerate(values):
        if value is None:
            row["missing_indices"].append(index)
        elif value == ZERO or value in found:
            row["missing_indices"].append(index)
            _failure(ctx, RpcError("Zero or duplicate registry entry", kind="evidence"),
                     "discovery", side=side, family=family)
        else:
            found.append(value)
    row.update(addresses=found, discovered=len(found), collection_complete=len(found) == count)
    if count > MARKET_LIMIT:
        row.update(missing_reason="market_limit", omitted_indices=[MARKET_LIMIT, count - 1])
    return found


def _scan_complete(coverage, key):
    scan = coverage.get(key, {})
    return scan.get("status") == "completed" and scan.get("missing_ranges") == []


def _observations(metrics, coverage, complete, confirmation):
    """Only measured native quantities; no cross-product or capital-as-profit sum."""
    events = metrics["events"]
    transfers = metrics["transfers"]
    assets = metrics["assets"]
    routes = metrics["scope"]["addresses"]
    valid = confirmation == "confirmed"

    def q(raw, asset):
        expected, unit = ASSET_METADATA[asset]
        decimals = assets.get(asset, {}).get("decimals", {})
        precision = decimals.get("closing")
        if precision != decimals.get("opening") or precision != expected:
            precision = None
        return quantity(raw, precision, unit)

    def qualified(observed, acquired, **extra):
        return dict(extra, observed_subtotal=observed,
                    requested_window_total=observed if acquired and valid else None,
                    raw_acquisition_complete=bool(acquired), collection_complete=bool(acquired and valid),
                    snapshot_confirmation=confirmation)

    fees, reconciliations = [], []
    for product, name, field, asset, router, family in (
            ("futures", "Filled", "feeWs", "wsnet", "futures_router", "futures"),
            ("futures", "Settled", "feeWs", "wsnet", "futures_router", "vault"),
            ("margin", "Bought", "feeUsdg", "usdg", "margin_router", "margin"),
            ("margin", "Sold", "feeUsdg", "usdg", "margin_router", "margin")):
        selected = [event for event in events if event["family"] == family and event["event"] == name]
        scopes = [scope for scope in metrics["event_scopes"] if scope["family"] == family]
        served = bool(scopes) and all(_scan_complete(coverage, scope["key"]) for scope in scopes)
        subtotal = sum(int(event["values"][field]) for event in selected) if selected or served else None
        fees.append(qualified(q(subtotal, asset), complete, product=product, assessment_basis=name,
                              event_count=len(selected), receipt_verified_count=sum(event["receipt_verified"] for event in selected),
                              meaning="Event-assessed fees, not collected cash. Combining opening/closing charges requires nonoverlap; never add assessments to matching receipts or LP results."))
        by_tx = {}
        for event in selected:
            by_tx.setdefault(event["transactionHash"], []).append(event)
        for tx_hash, rows in sorted(by_tx.items()):
            tx = next((tx for tx in metrics["transactions"] if tx["transaction_hash"] == tx_hash), {})
            legs = [leg for leg in tx.get("transfers", []) if leg["address"] == assets[asset]["address"]
                    and leg["values"]["to"] == routes[router]]
            assessed = sum(int(row["values"][field]) for row in rows)
            received = sum(int(leg["values"]["value"]) for leg in legs) if tx.get("receipt_status") == "verified" else None
            residual = received - assessed if received is not None else None
            reconciliations.append({"transaction_hash": tx_hash, "product": product, "assessment_basis": name,
                "assessed": q(assessed, asset), "router_receipts": q(received, asset), "residual": q(residual, asset),
                "equality": residual == 0 if residual is not None else None,
                "receipt_verified": tx.get("receipt_status") == "verified", "snapshot_confirmation": confirmation,
                "event_log_indices": [row["logIndex"] for row in rows],
                "transfer_log_indices": [leg["logIndex"] for leg in legs],
                "meaning": "Transaction-local comparison, not causal allocation. Mixed orders, penalties, pot interest or duplicate assessment bases remain unattributed."})

    states = metrics["states"]

    def delta(role, getter, asset):
        left = states.get("opening", {}).get(role, {}).get(getter)
        right = states.get("closing", {}).get(role, {}).get(getter)
        observed = q(int(right) - int(left), asset) if left is not None and right is not None else q(None, asset)
        return qualified(observed, complete and left is not None and right is not None,
                         opening=q(left, asset), closing=q(right, asset))

    vault = delta("vault", "equityWs", "wsnet")
    capital = {}
    for name, field in (("Subscribed", "ws"), ("Donated", "ws"), ("Deposited", "ws"),
                        ("RedemptionsPaid", "paidWs"), ("RedeemClaimed", "ws")):
        rows = [event for event in events if event["family"] == "vault" and event["event"] == name]
        scanned = any(scope["family"] == "vault" and _scan_complete(coverage, scope["key"])
                      for scope in metrics["event_scopes"])
        capital[name] = q(sum(int(row["values"][field]) for row in rows) if rows or scanned else None, "wsnet")
    vault.update(capital_and_claim_events=capital, economic_result=None,
                 meaning="Whole LP-class equity movement, not trading profit or protocol-owned revenue. Trader deposits are liabilities, subscriptions/donations are capital; redemption funding and later claims must not be counted twice. Clearing/ADL and unexposed reserved-cash transitions remain unresolved.")
    pot = {getter: delta("pot", getter, "usdg") for getter in
           ("totalDebtUsdg", "totalPrincipalUsdg", "equityUsdg", "cashUsdg", "insuranceUsdg", "owedUsdg")}
    accrued = {}
    for side in SIDES:
        state = states.get(side, {}).get("pot", {})
        debt, principal = state.get("totalDebtUsdg"), state.get("totalPrincipalUsdg")
        accrued[side] = q(int(debt) - int(principal) if debt is not None and principal is not None else None, "usdg")
    pot.update(outstanding_indexed_interest=accrued, cash_interest_received=None,
               meaning="Debt minus principal is outstanding indexed interest; its delta and lender-equity delta are not cash interest received. Capital, repayment, impairment, insurance and seized-ws valuation are non-additive. Equity saturates at zero.")
    bridges, treasury, router_receipts = [], [], []
    for asset, _, unit in ASSETS:
        token = assets[asset]["address"]
        relevant = [row for row in transfers if row["address"] == token and row["receipt_verified"]]
        for endpoint in ENDPOINTS:
            address = routes[endpoint]
            incoming = sum(int(row["values"]["value"]) for row in relevant if row["values"]["to"] == address)
            outgoing = sum(int(row["values"]["value"]) for row in relevant if row["values"]["from"] == address)
            values = {row["side"]: row["value"] for row in metrics["balances"]
                      if row["asset"] == asset and row["endpoint"] == endpoint}
            left, right = values.get("opening"), values.get("closing")
            change = int(right) - int(left) if left is not None and right is not None else None
            acquired = complete and change is not None
            residual = change - incoming + outgoing if change is not None else None
            bridges.append({"asset": asset, "endpoint": endpoint, "address": address,
                "opening": q(left, asset), "closing": q(right, asset), "balance_delta": q(change, asset),
                "observed_incoming": q(incoming, asset), "observed_outgoing": q(outgoing, asset),
                "observed_net_transfers": q(incoming - outgoing, asset), "residual": q(residual, asset),
                "reconciled": residual == 0 and acquired and valid,
                "raw_acquisition_complete": acquired, "collection_complete": acquired and valid,
                "snapshot_confirmation": confirmation,
                "meaning": "Balance delta minus receipt-verified scoped net Transfers. A residual is unreconciled, never automatically profit; emitter token and endpoint beneficiary differ."})
            if endpoint in ("futures_router", "margin_router"):
                router_receipts.append(qualified(q(incoming, asset), complete, asset=asset, endpoint=endpoint,
                    meaning="All observed incoming scoped token Transfers, including possible donations/old inventory; not automatically assessed fees."))
        direct = [row for row in relevant if row["values"]["to"] == routes["treasury"]
                  and row["values"]["from"] in {routes[role] for role in ENDPOINTS if role != "treasury"}]
        treasury.append(qualified(q(sum(int(row["values"]["value"]) for row in direct), asset), complete,
            asset=asset, transfer_count=len(direct), meaning="Direct tracked NetLong-endpoint to Treasury receipts only, not global Treasury revenue or indirect routing."))
    return {"assessed_fees": fees, "fee_receipt_reconciliation": reconciliations,
            "router_receipts": router_receipts, "vault_equity_delta": vault,
            "pot_state_deltas": pot, "asset_bridges": bridges, "treasury_receipts": treasury}


def prepare_result(result):
    """Project every checkpoint without erasing raw acquisition evidence."""
    metrics = result.get("metrics", {})
    if "acquisition_finished" not in metrics:
        return result
    coverage = result.get("coverage", {})
    boundaries = metrics["boundaries"]
    invalid = (result.get("snapshot", {}).get("confirmation") == "invalid"
               or result.get("snapshot", {}).get("recheck_status") == "mismatch"
               or any(error.get("kind") in ("integrity", "permission") for error in result.get("errors", [])))
    confirmed = (not invalid and result.get("snapshot", {}).get("recheck_status") == "confirmed"
                 and all(boundaries.get(side, {}).get("recheck_status") == "confirmed" for side in SIDES))
    confirmation = "invalid" if invalid else "confirmed" if confirmed else "unconfirmed"
    scans = [scope["key"] for scope in metrics["event_scopes"]] + metrics["transfer_scopes"]
    raw = bool(metrics["acquisition_finished"] and metrics.get("acquisition_error_count") == 0
               and all(_scan_complete(coverage, key) for key in scans)
               and all(metrics["discovery"][side][family].get("raw_collection_complete",
                       metrics["discovery"][side][family]["collection_complete"])
                       for side in SIDES for family in ("futures", "margin"))
               and all(row["receipt_status"] == "verified" for row in metrics["transactions"])
               and all(row["receipt_verified"] for row in metrics["events"] + metrics["transfers"]))

    def qualify(value):
        if isinstance(value, list):
            return [qualify(child) for child in value]
        if not isinstance(value, dict):
            return value
        out = {key: qualify(child) for key, child in value.items()}
        for flag in ("collection_complete", "event_coverage_complete"):
            if flag in value:
                out["raw_" + flag] = value.get("raw_" + flag, value[flag])
                out[flag] = bool(out["raw_" + flag] and confirmed and not invalid)
                out["snapshot_confirmation"] = confirmation
        if "snapshot_valid" in out:
            out["snapshot_valid"] = confirmed
        return out

    projected_coverage = qualify(coverage)
    projected_coverage["requested_scope"] = {"collection_complete": raw and confirmed,
        "raw_acquisition_complete": raw, "boundaries_confirmed": confirmed,
        "snapshot_confirmation": confirmation,
        "missing_receipts": [row["transaction_hash"] for row in metrics["transactions"] if row["receipt_status"] != "verified"],
        "meaning": "Supported current-generation reads and selected named-event/scoped-transfer interval only; not complete economic history."}
    projected = dict(metrics, discovery=qualify(metrics["discovery"]),
                     observations=_observations(metrics, coverage, raw, confirmation))
    return dict(result, metrics=projected, coverage=projected_coverage)


def recheck(ctx):
    boundaries = ctx.result.get("metrics", {}).get("boundaries", {})
    for side in SIDES:
        boundary = boundaries.get(side)
        if not boundary or "block_hash" not in boundary:
            continue
        boundary["recheck_status"] = "unconfirmed"
        try:
            if side == "closing":
                ctx.recheck()
            else:
                header = ctx.header(boundary["block_number"], fresh=True)
                if (header["hash"], header["timestamp"]) != (boundary["block_hash"], boundary["timestamp"]):
                    ctx._invalidate_identity("Opening boundary changed; NetLong revenue evidence is invalid")
        except RpcError as error:
            boundary["recheck_status"] = "mismatch" if error.kind == "integrity" else "unconfirmed"
            _failure(ctx, error, side + "_recheck")
        else:
            boundary["recheck_status"] = "confirmed"
        ctx.checkpoint()


def run(ctx, args):
    start = _integer(args.from_block, "revenue interval start")
    chunk = _integer(args.chunk_blocks, "revenue chunk size")
    if start == 0 or ctx.block is None or start > ctx.block or not 1 <= chunk <= MAX_LOG_BLOCKS:
        raise RpcError("Revenue evidence requires positive start <= pinned block and a bounded positive chunk", kind="input")
    routes = resolve_routes("netlong-revenue")
    source = load_json(routes["_route"]["exposure_interface"])
    revenue = load_json(routes["_route"]["interface"])
    metrics = ctx.result["metrics"]
    metrics.update(scope={"from_block": start, "to_block": ctx.block, "opening_block": start - 1,
        "current_generation": True, "addresses": {key: value["address"] for key, value in routes.items() if key != "_route"},
        "interface": routes["_route"]["interface"], "source_ids": revenue["source_ids"]},
        boundaries={"closing": _boundary(ctx.header(ctx.block))}, implementation_checks=[], entities=[], reads=[],
        bindings=[], states={side: {} for side in SIDES}, assets={key: {"address": routes[key]["address"], "decimals": {}}
        for key, _, _ in ASSETS}, balances=[], discovery={side: {family: {"count": None, "addresses": [],
        "missing_indices": [], "limit": MARKET_LIMIT, "collection_complete": False} for family in ("futures", "margin")}
        for side in SIDES}, event_scopes=[], transfer_scopes=[], events=[], transfers=[], transactions=[],
        acquisition_finished=False, warnings=[], unsupported_surfaces=revenue["unsupported_surfaces"])
    ctx.result["coverage"]["requested_scope"] = {"collection_complete": False}
    ctx.result["not_proven"].extend([
        "No universal NetLong revenue, profit, lifetime history, combined fee-plus-LP total or cross-asset total is calculated.",
        "Endpoint roster unions cover current configured generations only. Intermediate-only registration/listing, historical deployments and unnamed events remain outside established coverage.",
        "Endpoint runtime hashes prove reviewed byte identity only, not unchanged intermediate code, verified Solidity, economic ownership or correct external prices.",
        "Named-event/scoped Transfer completeness assumes no silent provider omission; receipt-local extra logs are not global event coverage. Empty logs do not prove inactive status or zero whole revenue.",
        "Native/internal transfers, other assets, indirect Treasury routes and beneficial LP ownership remain unknown. USDG parity and wsNET-to-NET conversion are not assumed.",
        "Fees, penalties, token receipts, LP equity, lender accrual, principal recovery, capital and claims are distinct non-additive measures. Carry-versus-price PnL and received interest require further accounting.",
    ])
    ctx.checkpoint()
    try:
        metrics["boundaries"]["opening"] = _boundary(ctx.header(start - 1))
    except RpcError as error:
        _failure(ctx, error, "opening_boundary")
    models = {side: {} for side in SIDES}
    for side, block in (("opening", start - 1), ("closing", ctx.block)):
        for role in ("vault", "oracle", "margin", "pot", "twap", "futures_router", "margin_router"):
            model = _model(ctx, routes[role]["address"], revenue if role.endswith("router") else source, role, side, block)
            if model:
                models[side][role] = model
        for library in source["margin_libraries"]:
            _model(ctx, library["address"], source, library["family"], side, block)
        try:
            code = bytes.fromhex(ctx.code(routes["treasury"]["address"], block)[2:])
            boundary = metrics["boundaries"].setdefault(side, {"block_number": block, "recheck_status": "not_available"})
            boundary["treasury_code"] = {"sha256": hashlib.sha256(code).hexdigest(), "byte_count": len(code)}
            if not code:
                raise RpcError("Canonical Treasury has no endpoint code", kind="unsupported")
        except RpcError as error:
            _failure(ctx, error, "treasury_code", side=side)
        if "vault" in models[side]:
            surface = load_json("assets/contracts/netlong-futures-runtime-surface.json")
            for label, role in (("wsNET", "wsnet"), ("feeRouter", "futures_router"), ("marginOracle", "oracle")):
                dependency = next(item for item in surface["dependencies"]["vault"] if item["role"] == label)
                observed = dependency["address"].lower()
                expected = routes[role]["address"]
                metrics["bindings"].append({"side": side, "block": block, "address": routes["vault"]["address"],
                    "function": None, "role": role, "observed": observed, "expected": expected,
                    "matches": observed == expected, "basis": "exact_endpoint_runtime_reviewed_immutable",
                    "evidence": "assets/contracts/netlong-futures-runtime-surface.json#/dependencies/vault"})
                if observed != expected:
                    _failure(ctx, RpcError("Reviewed vault immutable differs from canonical revenue route", kind="package"),
                             "immutable_binding", side=side, role=role)
        specs = []
        for role, abi_key, method, expected in (
                ("margin", "margin_abi", "pot", "pot"), ("margin", "margin_abi", "marginOracle", "oracle"),
                ("margin", "margin_abi", "twapSource", "twap"), ("margin", "margin_abi", "usdg", "usdg"),
                ("pot", "pot_abi", "desk", "margin"), ("pot", "pot_abi", "usdg", "usdg")):
            if role in models[side]:
                specs.append((routes[role]["address"], source[abi_key], method, routes[expected]["address"]))
        for role in ("margin", "pot"):
            if role in models[side]:
                specs.append((routes[role]["address"], revenue["binding_abi"], "feeRouter", routes["margin_router"]["address"]))
        if "futures_router" in models[side]:
            for getter, role in (("wsNet", "wsnet"), ("sNet", "snet"), ("net", "net"), ("usdg", "usdg"), ("treasury", "treasury")):
                specs.append((routes["futures_router"]["address"], revenue["router_abi"], getter, routes[role]["address"]))
        _bindings(ctx, specs, side, block)
        for role in ("vault", "pot"):
            if role not in models[side]:
                continue
            abi = revenue[role + "_abi"]
            answers = _read_many(ctx, [(routes[role]["address"], abi, item["name"], ()) for item in abi], side, block)
            metrics["states"][side][role] = {item["name"]: value for item, value in zip(abi, answers)}
        for asset, expected, unit in ASSETS:
            address = routes[asset]["address"]
            try:
                code = bytes.fromhex(ctx.code(address, block)[2:])
                metrics["assets"][asset].setdefault("code", {})[side] = {"sha256": hashlib.sha256(code).hexdigest(), "byte_count": len(code)}
                if not code:
                    raise RpcError("Scoped token has no endpoint code", kind="unsupported")
            except RpcError as error:
                _failure(ctx, error, "asset_code", side=side, asset=asset)
            decimals = _read(ctx, address, source["token_abi"], "decimals", side, block)
            metrics["assets"][asset]["decimals"][side] = decimals
            if decimals is not None and decimals != expected:
                _failure(ctx, RpcError("Token precision differs from reviewed native accounting convention", kind="unsupported"), "asset_precision", side=side, asset=asset)
            answers = _read_many(ctx, [(address, source["token_abi"], "balanceOf", (routes[endpoint]["address"],))
                                     for endpoint in ENDPOINTS], side, block)
            for endpoint, value in zip(ENDPOINTS, answers):
                metrics["balances"].append({"side": side, "block": block, "asset": asset, "endpoint": endpoint,
                    "address": routes[endpoint]["address"], "value": value})
        if "vault" in models[side]:
            _enumerate(ctx, routes["vault"]["address"], source["vault_abi"], "deskCount", "deskAt", side, block, "futures")
        if "margin" in models[side]:
            _enumerate(ctx, routes["margin"]["address"], source["margin_abi"], "tokenCount", "tokenAt", side, block, "margin")
        ctx.checkpoint()

    futures = sorted({address for side in SIDES for address in metrics["discovery"][side]["futures"]["addresses"]})
    tokens = sorted({address for side in SIDES for address in metrics["discovery"][side]["margin"]["addresses"]})
    metrics["scope"].update(futures_desks=futures, margin_tokens=tokens)
    for family in ("futures", "margin"):
        if metrics["discovery"]["opening"][family]["addresses"] != metrics["discovery"]["closing"][family]["addresses"]:
            metrics["warnings"].append({"kind": "endpoint_roster_change", "family": family,
                "meaning": "Endpoint union retained; registration/listing timing and intermediate-only entities are not established."})
    desk_models = {}
    for address in futures:
        desk_models[address] = {}
        for side, block in (("opening", start - 1), ("closing", ctx.block)):
            model = _model(ctx, address, source, "futures", side, block)
            if model:
                desk_models[address][side] = model
                _bindings(ctx, [(address, source["futures_abi"], getter, routes[role]["address"])
                                for getter, role in (("vault", "vault"), ("oracle", "oracle"))], side, block)
            config = _read(ctx, routes["vault"]["address"], source["vault_abi"], "desks", side, block, (address,))
            if config is not None and address in metrics["discovery"][side]["futures"]["addresses"] and config["registered"] is not True:
                _failure(ctx, RpcError("Enumerated desk is not registered", kind="evidence"), "desk_registration", address=address, side=side)
    metrics["margin_listings"] = []
    for token in tokens:
        for side, block in (("opening", start - 1), ("closing", ctx.block)):
            listing, decimals = _read_many(ctx, [(routes["margin"]["address"], source["margin_abi"], "listings", (token,)),
                                               (token, source["token_abi"], "decimals", ())], side, block)
            metrics["margin_listings"].append({"address": token, "side": side, "block": block, "listing": listing, "decimals": decimals})
            if listing is not None and decimals is not None and listing["tokenDecimals"] != decimals:
                _failure(ctx, RpcError("Margin listing precision differs from token", kind="evidence"), "listing", address=token, side=side)
    identities = {}
    for identity in metrics["implementation_checks"]:
        identities.setdefault(identity["address"], {})[identity["block"]] = identity["runtime_sha256"]
    for asset in metrics["assets"].values():
        for side, code in asset.get("code", {}).items():
            block = start - 1 if side == "opening" else ctx.block
            identities.setdefault(asset["address"], {})[block] = code["sha256"]
    for address, endpoints in identities.items():
        if len(endpoints) == 2 and len(set(endpoints.values())) != 1:
            _failure(ctx, RpcError("Endpoint code identity changed across the requested interval", kind="evidence"),
                     "endpoint_code_change", address=address)

    catalogs = {}

    def add_scope(address, family, catalog_path):
        catalog = load_catalog(catalog_path, address=address)
        key = "events:" + family + ":" + address
        row = {"key": key, "address": address, "family": family, "catalog": catalog_path,
               "catalog_sha256": catalog["sha256"], "selected_events": catalog["events"],
               "applicability": "reviewed_endpoint_model; intermediate_code_not_audited"}
        metrics["event_scopes"].append(row)
        catalogs[address] = (row, catalog["abi"])

    for role in ("vault", "margin"):
        if any(role in models[side] for side in SIDES):
            add_scope(routes[role]["address"], role, revenue["event_catalogs"][role])
    for address, endpoints in desk_models.items():
        if endpoints:
            model = endpoints.get("closing", endpoints.get("opening"))
            add_scope(address, "futures", revenue["event_catalogs"]["futures_stream" if model.get("stream_market") else "futures_net"])
    metrics["transfer_scopes"] = ["transfers:" + asset + ":" + direction
                                  for asset, _, _ in ASSETS for direction in ("outgoing", "incoming")]
    for key in [scope["key"] for scope in metrics["event_scopes"]] + metrics["transfer_scopes"]:
        ctx.result["coverage"][key] = {"requested_range": [start, ctx.block], "covered_ranges": [],
            "missing_ranges": [[start, ctx.block]], "event_coverage_complete": False, "status": "not_started"}
    ctx.checkpoint()
    endpoint_addresses = {routes[role]["address"] for role in ENDPOINTS}
    asset_addresses = {routes[key]["address"] for key, _, _ in ASSETS}
    event_index, transfer_index, tx_index = {}, {}, {}

    def record(decoded, family, scope, origin, verified=False):
        index, target = (transfer_index, metrics["transfers"]) if family == "transfer" else (event_index, metrics["events"])
        key = (decoded["blockHash"], decoded["logIndex"])
        existing = index.get(key)
        if existing is None:
            existing = dict(decoded, family=family, scope=scope, evidence_sources=[], receipt_verified=False)
            index[key] = existing
            target.append(existing)
        elif any(existing[field] != value for field, value in decoded.items()):
            ctx._invalidate_identity("Conflicting decoded receipt/event identity")
        if origin not in existing["evidence_sources"]:
            existing["evidence_sources"].append(origin)
        if verified:
            existing["receipt_verified"] = True
        return existing

    def collect(tx_hash, expected):
        tx = tx_index.get(tx_hash)
        if tx is None:
            tx = {"transaction_hash": tx_hash, "receipt_status": "pending", "transfers": []}
            tx_index[tx_hash] = tx
            metrics["transactions"].append(tx)
        try:
            receipt = ctx.receipt(tx_hash)
            if _quantity(receipt["status"]) != 1:
                raise RpcError("Observed revenue evidence has an unsuccessful receipt", kind="integrity")
            keys, decoded_transfers = set(), []
            for raw in receipt["logs"]:
                ctx.check()
                key = (raw["blockHash"].lower(), _quantity(raw["logIndex"]))
                keys.add(key)
                address = raw["address"].lower()
                selector = raw["topics"][0].lower() if raw["topics"] else None
                if address in catalogs:
                    scope, abi = catalogs[address]
                    if selector in {item["topic0"] for item in scope["selected_events"]}:
                        record(decode_event(raw, abi), scope["family"], scope["key"], "receipt", True)
                if address in asset_addresses and selector == TRANSFER_TOPIC:
                    decoded = decode_event(raw, [_TRANSFER])
                    decoded_transfers.append(decoded)
                    if decoded["values"]["from"] in endpoint_addresses or decoded["values"]["to"] in endpoint_addresses:
                        record(decoded, "transfer", "scoped_transfers", "receipt", True)
            if not set(expected).issubset(keys):
                raise RpcError("Scanned event is absent from its successful receipt", kind="integrity")
            tx.update(receipt_status="verified", status=1, block_number=_quantity(receipt["blockNumber"]),
                      block_hash=receipt["blockHash"].lower(), transaction_index=_quantity(receipt["transactionIndex"]),
                      transfers=decoded_transfers)
        except RpcError as error:
            tx.update(receipt_status="failed", failure_kind=error.kind)
            _failure(ctx, error, "receipt", transaction_hash=tx_hash)
        ctx.checkpoint()

    def scan(key, address, abi, family, indexed=None):
        try:
            for page in ctx.logs(key, address, abi, [], start, ctx.block, chunk=chunk, indexed_topics=indexed):
                transactions = {}
                for decoded in page:
                    record(decoded, family, key, key)
                    transactions.setdefault(decoded["transactionHash"], []).append((decoded["blockHash"], decoded["logIndex"]))
                ctx.checkpoint()
                for tx_hash, expected in transactions.items():
                    collect(tx_hash, expected)
        except RpcError as error:
            _failure(ctx, error, "scan", scope=key)

    for scope, abi in catalogs.values():
        scan(scope["key"], scope["address"], abi, scope["family"])
    topics = ["0x" + address[2:].rjust(64, "0") for address in sorted(endpoint_addresses)]
    for asset, _, _ in ASSETS:
        for direction, indexed in (("outgoing", [topics]), ("incoming", [None, topics])):
            key = "transfers:" + asset + ":" + direction
            scan(key, routes[asset]["address"], [_TRANSFER], "transfer", indexed)
    # Receipt-local evidence can expose silent omissions in served selected scopes.
    # It never fills a missing global range or substitutes for another scan.
    for event in metrics["events"]:
        scope = event["scope"]
        covered = ctx.result["coverage"].get(scope, {}).get("covered_ranges", [])
        if event["receipt_verified"] and scope not in event["evidence_sources"] and any(left <= event["blockNumber"] <= right for left, right in covered):
            ctx._invalidate_identity("Served named-event range omitted a receipt-proven event")
    for event in metrics["transfers"]:
        asset = next(key for key, _, _ in ASSETS if routes[key]["address"] == event["address"])
        for direction, field in (("incoming", "to"), ("outgoing", "from")):
            key = "transfers:" + asset + ":" + direction
            covered = ctx.result["coverage"].get(key, {}).get("covered_ranges", [])
            if (event["values"][field] in endpoint_addresses and event["receipt_verified"]
                    and key not in event["evidence_sources"] and any(left <= event["blockNumber"] <= right for left, right in covered)):
                ctx._invalidate_identity("Served scoped Transfer range omitted a receipt-proven event")
    for event in metrics["events"]:
        if event["family"] == "vault" and event["event"] == "Settled" and event["values"]["desk"] not in futures:
            _failure(ctx, RpcError("Settlement refers to desk absent from endpoint registries", kind="evidence"), "historical_registry_gap")
        if event["family"] == "margin" and "token" in event["values"] and event["values"]["token"] not in tokens:
            _failure(ctx, RpcError("Margin event token absent from endpoint registries", kind="evidence"), "historical_registry_gap")
    metrics["acquisition_finished"] = True
    metrics["acquisition_error_count"] = len(ctx.result["errors"])
    ctx.checkpoint()


def summarize(text, checkpoint_status):
    result = json.loads(text)
    metrics = result.get("metrics", {})
    # Project the already-qualified document, not a new calculation with omitted
    # evidence. The acquisition marker is omitted so serialization is idempotent.
    keep = ("scope", "boundaries", "discovery", "observations", "warnings", "unsupported_surfaces")
    result["metrics"] = {key: value for key, value in metrics.items() if key in keep}
    result["metrics"]["evidence_counts"] = {key: len(metrics.get(key, [])) for key in
        ("reads", "events", "transfers", "transactions", "implementation_checks")}
    observations = result["metrics"].get("observations", {})
    bridges = observations.get("asset_bridges", [])
    observations["asset_bridges"] = [row for row in bridges if not row["reconciled"]
        or any(row[key]["raw"] not in (None, "0") for key in
               ("balance_delta", "observed_incoming", "observed_outgoing", "residual"))]
    observations["unchanged_reconciled_zero_flow_bridges_omitted"] = len(bridges) - len(observations["asset_bridges"])
    comparisons = observations.get("fee_receipt_reconciliation", [])
    prioritized = sorted(comparisons, key=lambda row: row["equality"] is True)
    observations["fee_receipt_reconciliation"] = prioritized[:8]
    observations["receipt_comparison_counts"] = {
        "transaction_assessment_bases": len(comparisons),
        "equal": sum(row["equality"] is True for row in comparisons),
        "unequal_or_unavailable": sum(row["equality"] is not True for row in comparisons),
        "omitted_details": max(0, len(comparisons) - 8)}
    for key in ("assessed_fees", "router_receipts", "asset_bridges", "treasury_receipts", "fee_receipt_reconciliation"):
        for row in observations.get(key, []):
            row.pop("meaning", None)
    observations["interpretation_limits"] = [
        "Opening/closing assessments stay separate until nonoverlap is established; never add fees to matching receipts or LP results.",
        "Receipt equality is a transaction-local comparison, not per-order or penalty/interest attribution.",
        "Token balance residuals are unreconciled differences, not profit. Router receipts may include donations.",
        "Treasury rows cover direct tracked-endpoint receipts only, not Treasury-wide revenue."]
    for boundary in result["metrics"].get("boundaries", {}).values():
        boundary.pop("treasury_code", None)
    result["coverage"] = {key: value for key, value in result.get("coverage", {}).items()
                          if key == "requested_scope" or isinstance(value, dict) and value.get("status") != "completed"}
    result["presentation"] = {"detail": "summary", "full_checkpoint": checkpoint_status,
        "omitted": ["raw reads", "events", "transfers", "receipts", "implementation checks",
                    "completed scan ranges", "unchanged reconciled zero-flow bridges",
                    "receipt comparison details beyond eight"]}
    return serialize_result(result)

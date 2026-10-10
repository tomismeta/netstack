"""Pinned Credit claims and accrued market debt, never cached financial history."""
import hashlib
import json
from fractions import Fraction

from netstack_core import (ZERO, RpcError, _address, keccak256, load_json,
                           ratio, resolve_routes, serialize_result)

WAD = 10 ** 18
MARKET_FIELDS = ("totalSupplyAssets", "totalSupplyShares", "totalBorrowAssets",
                 "totalBorrowShares", "lastUpdate", "fee")
PARAM_FIELDS = ("loanToken", "collateralToken", "oracle", "irm", "lltv")


def values(value):
    return list(value.values()) if isinstance(value, dict) else list(value)


def market_id(params):
    words = [bytes.fromhex(_address(params[k])[2:]).rjust(32, b"\0") for k in PARAM_FIELDS[:4]]
    words.append(params["lltv"].to_bytes(32, "big"))
    return "0x" + keccak256(b"".join(words)).hex()


def assets_for_shares(shares, assets, total_shares, *, up=False):
    """Morpho virtual offsets: one asset and one million shares."""
    numerator, denominator = shares * (assets + 1), total_shares + 10 ** 6
    return (numerator + denominator - 1) // denominator if up else numerator // denominator


def accrue_market(stored, timestamp, rate):
    """Exact reviewed Morpho Taylor/floor ordering; no floating-point APR."""
    m = dict(stored)
    elapsed = timestamp - m["lastUpdate"]
    if elapsed < 0 or m["totalBorrowAssets"] > m["totalSupplyAssets"] or not 0 <= m["fee"] <= WAD:
        raise RpcError("Inconsistent market state", kind="integrity")
    first = rate * elapsed
    second = first * first // (2 * WAD)
    third = second * first // (3 * WAD)
    interest = m["totalBorrowAssets"] * (first + second + third) // WAD
    fee_assets = interest * m["fee"] // WAD
    m["totalBorrowAssets"] += interest
    m["totalSupplyAssets"] += interest
    fee_shares = fee_assets * (m["totalSupplyShares"] + 10 ** 6) // (m["totalSupplyAssets"] - fee_assets + 1)
    m["totalSupplyShares"] += fee_shares
    if any(m[k] >= 2 ** 128 for k in MARKET_FIELDS[:4]):
        raise RpcError("Accrued market exceeds source uint128 bounds", kind="integrity")
    m.update(pending_interest_assets=interest, pending_fee_assets=fee_assets,
             pending_fee_shares=fee_shares, borrow_rate_wad_per_second=rate,
             available_liquidity_assets=m["totalSupplyAssets"] - m["totalBorrowAssets"])
    return m


def account_position(position, market, price, lltv, *, is_fee_recipient):
    supply, borrow, collateral = values(position)
    pending_fee_shares = market["pending_fee_shares"] if is_fee_recipient else 0
    accrued_supply = supply + pending_fee_shares
    debt = assets_for_shares(borrow, market["totalBorrowAssets"], market["totalBorrowShares"], up=True)
    claim = assets_for_shares(accrued_supply, market["totalSupplyAssets"], market["totalSupplyShares"])
    marked = None if price is None else collateral * price // 10 ** 36
    limit = None if marked is None else marked * lltv // WAD
    return {"supply_shares": supply, "borrow_shares": borrow, "collateral_raw": collateral,
            "pending_fee_shares": pending_fee_shares, "accrued_supply_shares": accrued_supply,
            "supply_claim_assets": claim, "accrued_debt_assets": debt,
            "oracle_collateral_loan_assets": marked, "borrow_limit_assets": limit,
            "healthy_at_reported_oracle": None if limit is None else debt <= limit,
            "ltv": ratio(Fraction(debt, marked)) if marked else (ratio(Fraction(0)) if debt == 0 else None),
            "oracle_mark_minus_debt_assets": None if marked is None else marked - debt,
            "income": None, "meaning": "Collateral exposure less debt, not realized proceeds or income."}


def prepare_result(result):
    metrics = result.get("metrics", {})
    if "credit_scope" not in metrics:
        return
    complete = bool(metrics.get("snapshot_reads_complete") and
                    result.get("snapshot", {}).get("recheck_status") == "confirmed" and
                    not result.get("errors"))
    coverage = result.setdefault("coverage", {})
    coverage["collection_complete"] = complete
    coverage["requested_scope"] = {"scope": metrics["credit_scope"], "collection_complete": complete}
    coverage["credit_snapshot"] = {"collection_complete": complete,
                                    "scope": metrics["credit_scope"],
                                    "historical_receipts_complete": False,
                                    "all_morpho_markets_complete": False}
    metrics["confirmed_vault_accounting"] = metrics.get("vault") if complete else None
    metrics["lifetime_earnings"] = None
    metrics["cash_fee_receipts"] = None


def _bind(ctx, address, evidence, role):
    raw = bytes.fromhex(ctx.code(address)[2:])
    digest = hashlib.sha256(raw).hexdigest()
    row = {"role": role, "address": address, "runtime_sha256": digest,
           "status": "matched" if digest == evidence["runtime_sha256"] and len(raw) == evidence["runtime_bytes"] else "unsupported"}
    ctx.result["metrics"]["implementations"].append(row)
    if row["status"] != "matched":
        raise RpcError("Credit dependency runtime differs from reviewed evidence", kind="unsupported")


def run(ctx, args):
    routes = resolve_routes("credit")
    interface = load_json(routes["_route"]["interface"])
    evidence = load_json(interface["source_evidence"])["contracts"]
    metrics = ctx.result["metrics"]
    account = _address(args.account) if args.account else None
    metrics.update(credit_scope={"chain_id": 4663, "discovery": "vault_adapters_union_router_listings_and_loopback",
                                 "account": account, "all_accounts": False,
                                 "history": "not_requested_or_reconstructed"},
                   implementations=[], adapters=[], markets=[], unsupported=[],
                   snapshot_reads_complete=False, lifetime_earnings=None, cash_fee_receipts=None)
    ctx.result["coverage"]["collection_complete"] = False
    addresses = {role: routes[role]["address"] for role in ("vault", "router", "adapter", "loopback", "morpho", "irm", "oracle", "usdg")}
    for role, name in (("vault", "credit-vault"), ("router", "credit"), ("adapter", "market-adapter"),
                       ("loopback", "loopback-router"), ("morpho", "morpho"), ("irm", "credit-irm"), ("oracle", "loopback-oracle")):
        _bind(ctx, addresses[role], evidence[name], role)

    def call(role, name, *args):
        return ctx.call(addresses[role], interface[role + "_abi"], name, args)

    for role, getter, expected in (("vault", "asset", "usdg"), ("adapter", "parentVault", "vault"),
                                   ("adapter", "morpho", "morpho"), ("adapter", "adaptiveCurveIrm", "irm"),
                                   ("adapter", "asset", "usdg"), ("loopback", "morpho", "morpho"),
                                   ("loopback", "irm", "irm"), ("loopback", "oracle", "oracle"),
                                   ("irm", "MORPHO", "morpho"), ("router", "adapter", "adapter")):
        if _address(call(role, getter)) != addresses[expected]:
            raise RpcError("Credit dependency binding differs", kind="integrity")
    if ctx.call(addresses["usdg"], interface["token_abi"], "decimals") != 6:
        raise RpcError("Credit loan asset decimals differ", kind="integrity")
    vault = {name: call("vault", name) for name in
             ("totalAssets", "totalSupply", "virtualShares", "decimals", "_totalAssets", "lastUpdate", "maxRate",
              "performanceFee", "managementFee", "performanceFeeRecipient", "managementFeeRecipient",
              "owner", "curator", "liquidityAdapter", "liquidityData", "adapterRegistry",
              "receiveSharesGate", "sendSharesGate", "receiveAssetsGate", "sendAssetsGate")}
    metrics["vault"] = vault
    accrued_assets, performance_shares, management_shares = values(call("vault", "accrueInterestView"))
    if accrued_assets != vault["totalAssets"]:
        raise RpcError("Vault accrued assets disagree", kind="integrity")
    vault.update(pending_performance_fee_shares=performance_shares,
                 pending_management_fee_shares=management_shares,
                 diluted_supply=vault["totalSupply"] + performance_shares + management_shares,
                 loan_asset_decimals=6, loan_asset=addresses["usdg"],
                 idle_assets=ctx.call(addresses["usdg"], interface["token_abi"], "balanceOf", (addresses["vault"],)),
                 max_functions_meaning="Always zero by source design; not an inactivity or liquidity signal.",
                 withdrawal_constraint="Idle cash plus single liquidityAdapter/data deallocation, gates, allowance and underlying liquidity; no withdraw queue.",
                 fee_entitlement_meaning="Pending shares at snapshot, not USDG received, protocol ownership or lifetime earnings.")
    denominator = vault["diluted_supply"] + vault["virtualShares"]
    vault["pending_performance_fee_claim_assets"] = performance_shares * (accrued_assets + 1) // denominator
    vault["pending_management_fee_claim_assets"] = management_shares * (accrued_assets + 1) // denominator
    if account:
        shares = call("vault", "balanceOf", account)
        vault["account"] = {"address": account, "shares": shares, "claim_assets": call("vault", "convertToAssets", shares),
                            "can_send_shares": call("vault", "canSendShares", account),
                            "can_receive_assets": call("vault", "canReceiveAssets", account),
                            "max_withdraw_reported": call("vault", "maxWithdraw", account)}
    count = call("vault", "adaptersLength")
    metrics["adapter_count"] = count
    ids = set()
    for index in range(min(count, args.max_adapters)):
        address = _address(call("vault", "adapters", index))
        row = {"address": address, "status": "supported" if address == addresses["adapter"] else "unsupported_variant"}
        metrics["adapters"].append(row)
        if address != addresses["adapter"]:
            metrics["unsupported"].append(row)
            continue
        row["real_assets"] = call("adapter", "realAssets")
        length = call("adapter", "marketIdsLength")
        row["market_count"] = length
        if length > args.max_markets:
            metrics["unsupported"].append({"reason": "adapter_market_bound", "count": length})
        row["market_ids"] = [call("adapter", "marketIds", i) for i in range(min(length, args.max_markets))]
        if len(set(row["market_ids"])) != len(row["market_ids"]):
            raise RpcError("Duplicate indexed adapter market", kind="integrity")
        ids.update(row["market_ids"])
    if count > args.max_adapters:
        metrics["unsupported"].append({"reason": "adapter_bound", "count": count})
    listed = call("router", "listedMarkets")
    metrics["router_listing_count"] = len(listed)
    metrics["router_semantics"] = "Runtime matched; publisher listing reads only. Implementation source unavailable; no activation or cap/borrow guarantee inferred."
    ids.update(listed)
    loopback_id = call("loopback", "marketId")
    ids.add(loopback_id)
    metrics["discovered_market_count"] = len(ids)
    if len(ids) > args.max_markets:
        metrics["unsupported"].append({"reason": "union_market_bound", "count": len(ids)})
    metrics["morpho_fee_recipient"] = call("morpho", "feeRecipient")
    for mid in sorted(ids)[:args.max_markets]:
        row = {"chain_id": 4663, "morpho": addresses["morpho"], "market_id": mid,
               "loopback": mid == loopback_id, "status": "collecting"}
        metrics["markets"].append(row)
        params = dict(zip(PARAM_FIELDS, values(call("morpho", "idToMarketParams", mid))))
        row["params"] = params
        if market_id(params) != mid:
            raise RpcError("Market ID does not hash to parameters", kind="integrity")
        if params["loanToken"] != addresses["usdg"] or params["irm"] != addresses["irm"]:
            row["status"] = "unsupported_asset_or_irm"
            metrics["unsupported"].append({"market_id": mid, "reason": row["status"]})
            continue
        stored = dict(zip(MARKET_FIELDS, values(call("morpho", "market", mid))))
        if not stored["lastUpdate"]:
            raise RpcError("Discovered market is not created", kind="integrity")
        row["stored_market"] = stored
        rate = call("irm", "borrowRateView", params, stored)
        accrued = accrue_market(stored, ctx.timestamp, rate)
        row["accrued_market"] = accrued
        row["adapter_claim_assets"] = call("adapter", "expectedSupplyAssets", mid)
        row["caps"] = []
        for cap_id in call("adapter", "ids", params):
            row["caps"].append({"id": cap_id, **{name: call("vault", name, cap_id) for name in ("allocation", "absoluteCap", "relativeCap")}})
        row["caps_meaning"] = "Recorded allocations may lag accrual; shared adapter/collateral caps must not be summed. Relative caps use firstTotalAssets, not real assets."
        oracle = _address(params["oracle"])
        known = next((e for e in evidence.values() if _address(e["address"]) == oracle), None)
        row["oracle_source_status"] = known["source_status"] if known else "unknown_variant"
        if not known:
            metrics["unsupported"].append({"market_id": mid, "reason": "unknown_oracle_variant"})
        price = None
        if account:
            if known:
                _bind(ctx, oracle, known, "market_oracle")
            try:
                price = ctx.call(oracle, interface["oracle_abi"], "price")
            except RpcError as exc:
                if exc.kind != "revert":
                    raise
                row["oracle_status"] = "reverted_health_unknown"
                metrics["unsupported"].append({"market_id": mid, "reason": "oracle_reverted_health_unknown"})
            row["oracle_price_1e36"] = price
            row["account"] = account_position(
                call("morpho", "position", mid, account), accrued, price, params["lltv"],
                is_fee_recipient=account == _address(metrics["morpho_fee_recipient"]))
        row["status"] = "collected"
        ctx.checkpoint()
    if not metrics["unsupported"]:
        market_rows = {row["market_id"]: row for row in metrics["markets"]}
        for adapter in metrics["adapters"]:
            accounted = sum(market_rows[mid]["adapter_claim_assets"] for mid in adapter["market_ids"])
            if accounted != adapter["real_assets"]:
                raise RpcError("Adapter indexed claims do not reconcile to realAssets", kind="integrity")
        real_assets = vault["idle_assets"] + sum(row["real_assets"] for row in metrics["adapters"])
        elapsed = ctx.timestamp - vault["lastUpdate"]
        if elapsed < 0:
            raise RpcError("Vault update is after snapshot", kind="integrity")
        cap = vault["_totalAssets"] + vault["_totalAssets"] * elapsed * vault["maxRate"] // WAD
        if min(real_assets, cap) != accrued_assets:
            raise RpcError("Vault real assets and growth cap do not reconcile", kind="integrity")
        vault["reconciliation"] = {"status": "matched", "real_assets": real_assets,
                                   "growth_cap_assets": cap, "indexed_adapter_claims": "matched"}
    metrics["snapshot_reads_complete"] = not metrics["unsupported"]
    metrics["activation"] = "Current state observed only; neither old pending labels nor an empty log response establish inactive/zero."
    prepare_result(ctx.result)


def summarize(text, checkpoint_status):
    result = json.loads(text)
    metrics = result.get("metrics", {})
    metrics.pop("implementations", None)
    for row in metrics.get("markets", []):
        row.pop("caps", None)
    result["detail"] = "summary"
    result["checkpoint_status"] = checkpoint_status
    return serialize_result(result)

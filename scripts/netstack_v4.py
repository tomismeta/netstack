"""Pinned V4 NFT discovery, principal and accrued fees; no valuation or wallet access."""
from netstack_core import ZERO, RpcError, keccak256, load_json, resolve_routes

Q96 = 1 << 96
Q128 = 1 << 128
U256 = 1 << 256
# Q128 reciprocal square-root factors for the powers-of-two ticks of 1.0001.
# Numerical constants; integer rounding matches Uniswap's TickMath convention.
_TICK_FACTORS = (
    0xfffcb933bd6fad37aa2d162d1a594001, 0xfff97272373d413259a46990580e213a,
    0xfff2e50f5f656932ef12357cf3c7fdcc, 0xffe5caca7e10e4e61c3624eaa0941cd0,
    0xffcb9843d60f6159c9db58835c926644, 0xff973b41fa98c081472e6896dfb254c0,
    0xff2ea16466c96a3843ec78b326b52861, 0xfe5dee046a99a2a811c461f1969c3053,
    0xfcbe86c7900a88aedcffc83b479aa3a4, 0xf987a7253ac413176f2b074cf7815e54,
    0xf3392b0822b70005940c7a398e4b70f3, 0xe7159475a2c29b7443b29c7fa6e889d9,
    0xd097f3bdfd2022b8845ad8f792aa5825, 0xa9f746462d870fdf8a65dc1f90e061e5,
    0x70d869a156d2a1b890bb3df62baf32f7, 0x31be135f97d08fd981231505542fcfa6,
    0x9aa508b5b7a84e1c677de54f3e99bc9, 0x5d6af8dedb81196699c329225ee604,
    0x2216e584f5fa1ea926041bedfe98, 0x48a170391f7dc42444e8fa2,
)


def sqrt_ratio_at_tick(tick):
    if type(tick) is not int or not -887272 <= tick <= 887272:
        raise RpcError("Position tick is outside TickMath bounds", kind="integrity")
    bits, ratio = abs(tick), Q128
    for bit, factor in enumerate(_TICK_FACTORS):
        if bits & (1 << bit):
            ratio = ratio * factor >> 128
    if tick > 0:
        ratio = (U256 - 1) // ratio
    return (ratio + (1 << 32) - 1) >> 32


def liquidity_amounts(liquidity, tick_lower, tick_upper, sqrt_price_x96):
    if (type(liquidity) is not int or not 0 <= liquidity < Q128
            or type(sqrt_price_x96) is not int or not 0 < sqrt_price_x96 < 1 << 160
            or tick_lower >= tick_upper):
        raise RpcError("Invalid concentrated-liquidity position", kind="integrity")
    lower, upper = sqrt_ratio_at_tick(tick_lower), sqrt_ratio_at_tick(tick_upper)
    price = min(max(sqrt_price_x96, lower), upper)
    return ((liquidity << 96) * (upper - price) // upper // price,
            liquidity * (price - lower) // Q96)


def fee_growth_inside(tick, lower, upper, global_growth, lower_outside, upper_outside):
    if tick < lower:
        return (lower_outside - upper_outside) % U256
    if tick >= upper:
        return (upper_outside - lower_outside) % U256
    return (global_growth - lower_outside - upper_outside) % U256


def _word(value):
    return (value % U256).to_bytes(32, "big")


def _signed24(value):
    value &= (1 << 24) - 1
    return value - (1 << 24) if value & (1 << 23) else value


def pool_id(key):
    encoded = b"".join((bytes.fromhex(key["currency0"][2:]).rjust(32, b"\0"),
                        bytes.fromhex(key["currency1"][2:]).rjust(32, b"\0"),
                        _word(key["fee"]), _word(key["tickSpacing"]),
                        bytes.fromhex(key["hooks"][2:]).rjust(32, b"\0")))
    return "0x" + keccak256(encoded).hex()


def storage_slots(identifier, owner, lower, upper, token_id):
    pool = int.from_bytes(keccak256(bytes.fromhex(identifier[2:]) + _word(6)), "big")
    low = int.from_bytes(keccak256(_word(lower) + _word(pool + 4)), "big")
    high = int.from_bytes(keccak256(_word(upper) + _word(pool + 4)), "big")
    # The position key is packed (20 + 3 + 3 + 32 bytes), not padded abi.encode.
    packed = (bytes.fromhex(owner[2:]) + (lower % (1 << 24)).to_bytes(3, "big")
              + (upper % (1 << 24)).to_bytes(3, "big") + _word(token_id))
    position = int.from_bytes(keccak256(keccak256(packed) + _word(pool + 6)), "big")
    return ["0x" + _word(slot).hex() for slot in
            (pool, pool + 1, pool + 2, low + 1, low + 2, high + 1, high + 2,
             position, position + 1, position + 2)]


def collect(ctx, sleeve):
    routes = resolve_routes("v4")
    interface = load_json(routes["_route"]["interface"])
    pm, manager = routes["position_manager"]["address"], routes["pool_manager"]["address"]
    nft_abi, pool_abi = interface["position_manager_abi"], interface["pool_manager_abi"]
    result = {"position_manager": pm, "pool_manager": manager, "positions": [], "missing": [],
              "ownership_complete": False, "collection_complete": False, "read_provenance": [],
              "scope": routes["_route"]["scope"], "expected_owned_count": None,
              "observed_owned_count": 0, "ownership_status": "partial",
              "ownership_reason": "Pinned current ownership has not been reconciled.",
              "history_complete": False,
              "owner": sleeve, "candidates": [], "exhaustive_across_managers": False,
              "uninspected": ["Other NFT managers", "Direct PoolManager custody", "Indirect/third-party custody"],
              "discovery": {"method": "Per-run incoming position-manager Transfer logs from 0 through the pinned block, newest first; current ownerOf cardinality reconciled with balanceOf.",
                            "coverage_key": "v4_incoming_nfts", "event_scan_required": None,
                            "history_complete": False, "status": "not_started",
                            "reason": "Discovery has not started.", "candidate_limit": 128}}
    ctx.result["metrics"]["v4_positions"] = result
    coverage = ctx.result["coverage"].setdefault("v4_positions", {"collection_complete": False})

    def read(address, abi, name, args=()):
        entry = {"contract": address, "getter": name, "arguments": list(args), "block": ctx.block}
        result["read_provenance"].append(entry)
        try:
            value = ctx.call(address, abi, name, args)
        except RpcError as exc:
            entry.update(status="unavailable", error_kind=exc.kind)
            raise
        entry.update(status="observed", value=value)
        return value

    def missing(message):
        result["missing"].append(message)

    try:
        if read(pm, nft_abi, "poolManager") != manager:
            raise RpcError("V4 position manager points to an unexpected PoolManager", kind="integrity")
        expected = read(pm, nft_abi, "balanceOf", (sleeve,))
        result["expected_owned_count"] = expected
        if expected > 128:
            missing("V4 owned position count exceeds collection limit")
        candidates, owners = {}, set()

        def inspect(token_id, source):
            if token_id in candidates:
                if source not in candidates[token_id]["sources"]:
                    candidates[token_id]["sources"].append(source)
                return
            if len(candidates) >= 128:
                raise RpcError("V4 historical NFT candidate count exceeds collection limit", kind="coverage")
            row = {"position_id": token_id, "sources": [source], "owner": None,
                   "disposition": "ownership_unresolved"}
            candidates[token_id] = row
            result["candidates"].append(row)
            try:
                row["owner"] = read(pm, nft_abi, "ownerOf", (token_id,))
            except RpcError as exc:
                if exc.kind in ("permission", "integrity"):
                    raise
                row["error_kind"] = exc.kind
                row["reason"] = ("ownerOf reverted; historical receipt does not prove current custody or a burn."
                                 if exc.kind == "revert" else
                                 "Pinned ownerOf is unavailable; historical receipt does not prove current custody.")
                ctx.checkpoint()
                return
            if row["owner"] == sleeve:
                owners.add(token_id)
                result["observed_owned_count"] = len(owners)
                if len(owners) > expected:
                    raise RpcError("V4 ownerOf matches exceed pinned balanceOf", kind="integrity")
                row.update(disposition="unpriced", reason="Pinned direct NFT ownership; position quantities not yet inspected.")
            else:
                row.update(disposition="excluded", reason="Pinned ownerOf is a different custodian; no beneficial ownership inferred.")
            ctx.checkpoint()

        result["discovery"]["event_scan_required"] = expected != 0
        if expected:
            result["discovery"].update(status="in_progress", reason="Current ownership is not yet reconciled.")
            try:
                for page in ctx.logs("v4_incoming_nfts", pm, nft_abi, ["Transfer"], 0, ctx.block,
                                     indexed_topics=[None, "0x" + sleeve[2:].rjust(64, "0")], newest_first=True):
                    # Context yields each page in canonical ascending order.
                    # Inspect recent receipts first, including within a page.
                    for event in reversed(page):
                        inspect(event["values"]["tokenId"], {"kind": "incoming_transfer",
                                                            "transaction_hash": event["transactionHash"],
                                                            "block": event["blockNumber"], "log_index": event["logIndex"]})
                        if len(owners) == expected:
                            break
                    ctx.checkpoint()
                    if len(owners) == expected:
                        event_coverage = ctx.result["coverage"].get("v4_incoming_nfts")
                        if event_coverage is not None and not event_coverage["event_coverage_complete"]:
                            event_coverage["status"] = "stopped_after_ownership_reconciliation"
                        break
            except RpcError as exc:
                if exc.kind in ("permission", "integrity"):
                    raise
                result["discovery"]["failure_kind"] = exc.kind
                missing("Bounded incoming NFT discovery: " + str(exc))
        event_coverage = ctx.result["coverage"].get("v4_incoming_nfts", {})
        result["history_complete"] = event_coverage.get("event_coverage_complete", False)
        result["discovery"]["history_complete"] = result["history_complete"]
        result["ownership_complete"] = len(owners) == expected
        if result["ownership_complete"]:
            result["ownership_status"] = "complete"
            result["ownership_reason"] = ("Pinned balanceOf is zero; the selected manager has no directly owned NFTs."
                                          if expected == 0 else
                                          "Distinct pinned ownerOf matches exactly reconcile with pinned balanceOf; no additional current NFTs can remain undiscovered at this manager.")
            result["discovery"].update(
                status="not_required_zero_balance" if expected == 0 else "ownership_reconciled",
                reason=result["ownership_reason"])
            for candidate in candidates.values():
                if candidate["disposition"] == "ownership_unresolved":
                    candidate.update(
                        disposition="excluded", exclusion_basis="reconciled_current_owner_count",
                        reason="ownerOf remains unavailable, but the exact current-owner count is already reconciled by other NFTs; this historical candidate cannot be an additional owned NFT. No burn inferred.")
        else:
            result["ownership_reason"] = "Current ownerOf matches do not reconcile with position-manager balanceOf; observed positions are a partial universe."
            result["discovery"].update(status="partial", reason=result["ownership_reason"])
            missing(result["ownership_reason"])
        for token_id in sorted(owners):
            ctx.check()
            provenance_start = len(result["read_provenance"])
            row = {"position_id": token_id, "status": "partial"}
            result["positions"].append(row)
            try:
                info = read(pm, nft_abi, "getPoolAndPositionInfo", (token_id,))
                key, packed = info["poolKey"], info["info"]
                lower, upper = _signed24(packed >> 8), _signed24(packed >> 32)
                identifier = pool_id(key)
                row.update(pool_id=identifier, currency0=key["currency0"], currency1=key["currency1"],
                           tick_lower=lower, tick_upper=upper, pool_key=key)
                if packed >> 56 != int(identifier, 16) >> 56:
                    raise RpcError("V4 packed position pool identity disagrees with its key", kind="integrity")
                if key["hooks"] != ZERO:
                    raise RpcError("Hooked V4 position requires separately established accounting", kind="unavailable")
                if key["currency0"] >= key["currency1"] or key["tickSpacing"] <= 0:
                    raise RpcError("Invalid V4 pool currency ordering or tick spacing", kind="integrity")
                if lower % key["tickSpacing"] or upper % key["tickSpacing"]:
                    raise RpcError("V4 position ticks disagree with pool spacing", kind="integrity")
                slots = storage_slots(identifier, pm, lower, upper, token_id)
                words = [int(read(manager, pool_abi, "extsload", (slot,)), 16) for slot in slots]
                slot0, global0, global1, low0, low1, high0, high1, stored_liquidity, last0, last1 = words
                sqrt_price, tick = slot0 & ((1 << 160) - 1), _signed24(slot0 >> 160)
                liquidity = stored_liquidity & (Q128 - 1)
                observed_liquidity = read(pm, nft_abi, "getPositionLiquidity", (token_id,))
                if liquidity != observed_liquidity or stored_liquidity >= Q128:
                    raise RpcError("V4 storage liquidity disagrees with independent NFT getter", kind="integrity")
                if not -887272 <= tick <= 887272:
                    raise RpcError("V4 current tick outside accounting bounds", kind="integrity")
                amount0, amount1 = liquidity_amounts(liquidity, lower, upper, sqrt_price)
                inside0 = fee_growth_inside(tick, lower, upper, global0, low0, high0)
                inside1 = fee_growth_inside(tick, lower, upper, global1, low1, high1)
                row.update(liquidity_raw=liquidity, sqrt_price_x96=sqrt_price, tick=tick,
                           amount0_raw=amount0, amount1_raw=amount1,
                           fees0_raw=(inside0 - last0) % U256 * liquidity // Q128,
                           fees1_raw=(inside1 - last1) % U256 * liquidity // Q128,
                           status="observed", read_provenance=result["read_provenance"][provenance_start:])
                candidates[token_id].update(disposition="included",
                                            reason="Verified direct ownership; exact principal and accrued fee quantities included, valuation separate.")
            except RpcError as exc:
                if exc.kind in ("permission", "integrity"):
                    raise
                row["error"] = {"kind": exc.kind, "message": str(exc)}
                missing("V4 position " + str(token_id) + ": " + str(exc))
            ctx.checkpoint()
    except RpcError as exc:
        missing(str(exc))
        if exc.kind in ("permission", "integrity"):
            raise
    result["collection_complete"] = result["ownership_complete"] and not result["missing"]
    coverage.update(collection_complete=result["collection_complete"],
                    ownership_complete=result["ownership_complete"], ownership_status=result["ownership_status"],
                    ownership_reason=result["ownership_reason"], history_complete=result["history_complete"],
                    expected_owned_count=result["expected_owned_count"],
                    observed_owned_count=result["observed_owned_count"], missing=result["missing"])
    ctx.checkpoint()
    return result

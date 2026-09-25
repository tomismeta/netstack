"""Pinned-block Core RFV, independently reconstructed from canonical custody."""

from math import isqrt

from netstack_core import RpcError, amount, load_json, resolve_routes


WAD = 10**18


def _raw(value):
    if type(value) is int:
        return str(value)
    if isinstance(value, dict):
        return {key: _raw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_raw(item) for item in value]
    return value


def _unsigned(value):
    if type(value) is not int or value < 0:
        raise RpcError("Expected a nonnegative raw quantity", kind="decode")
    return value


def _wad(raw, decimals):
    _unsigned(raw)
    if type(decimals) is not int or not 0 <= decimals <= 255:
        raise RpcError("Missing or invalid token decimals", kind="decode")
    return raw * WAD // 10**decimals


def _pol(usdg_raw, net_raw, usdg_decimals, net_decimals, held, supply):
    x, y = _wad(usdg_raw, usdg_decimals), _wad(net_raw, net_decimals)
    _unsigned(held)
    _unsigned(supply)
    if held > supply:
        raise RpcError("Treasury LP holding exceeds total LP supply", kind="integrity")
    if supply == 0:
        if held or usdg_raw or net_raw:
            raise RpcError("Nonempty pair has zero LP supply", kind="integrity")
        return 0
    # Do not floor the ownership share or LP underlying before the square root.
    return 2 * isqrt(x * y) * held // supply


def _nav(rfv_wad, supply, decimals):
    _unsigned(rfv_wad)
    _unsigned(supply)
    _wad(0, decimals)
    if supply == 0:
        raise RpcError("NAV is undefined at zero NET total supply", kind="integrity")
    return rfv_wad * 10**decimals // supply


def _comparison(observed, expected, unit):
    available = observed is not None and expected is not None
    numeric = type(observed) is int and type(expected) is int
    delta = observed - expected if available and numeric else None
    return {
        "observed_raw": _raw(observed), "expected_raw": _raw(expected),
        "delta_raw": _raw(delta), "unit": unit,
        "status": "unavailable" if not available else "match" if observed == expected else "mismatch",
    }


def _problem(ctx, scope, message):
    ctx.result["errors"].append({"scope": "core_rfv:" + scope, "error": str(message)})


class _Reads:
    def __init__(self, ctx, report):
        self.ctx, self.report = ctx, report

    def get(self, key, address, abi, getter, args=(), unit="address"):
        row = {"contract": address, "getter": getter, "arguments": _raw(args),
               "block": self.ctx.block, "unit": unit, "status": "unavailable", "raw": None}
        self.report["reads"][key] = row
        try:
            value = self.ctx.call(address, abi, getter, args)
        except RpcError as error:
            row["error"] = str(error)
            if error.kind == "permission":
                raise
            _problem(self.ctx, key, error)
            value = None
        else:
            row.update(status="observed", raw=_raw(value))
        self.ctx.checkpoint()
        return value

    def code(self, key, address):
        row = {"contract": address, "getter": "eth_getCode", "arguments": [],
               "block": self.ctx.block, "unit": "code presence", "status": "unavailable"}
        self.report["reads"][key] = row
        try:
            present = self.ctx.code(address) not in ("0x", "0x0", "0x00")
            row.update(status="observed", present=present)
            if not present:
                _problem(self.ctx, key, "No deployed code at pinned block")
        except RpcError as error:
            row["error"] = str(error)
            if error.kind == "permission":
                raise
            _problem(self.ctx, key, error)
            present = False
        self.ctx.checkpoint()
        return present


def run(ctx, args):
    routes = resolve_routes("reserves")
    source = load_json(routes["_route"]["interface"])
    pair_source = load_json(routes["_route"]["pair_interface"])
    addresses = {name: routes[name]["address"] for name in ("treasury", "usdg", "net", "pair", "vault", "sleeve")}
    treasury, usdg, net, pair, vault = (addresses[name] for name in ("treasury", "usdg", "net", "pair", "vault"))
    ta, token_abi, va, pa = source["treasury_abi"], source["token_abi"], source["vault_abi"], pair_source["pair_abi"]
    report = ctx.result["metrics"]["core_rfv"] = {
        "status": "partial", "block": ctx.block, "addresses": addresses,
        "unit": "USDG; no USD parity or dollar valuation assumed",
        "scope": "Canonical Treasury Core RFV formula only; not an inventory of every Treasury holding",
        "source_id": source["source_id"], "interface_provenance": source["provenance"],
        "methodology": source["methodology"], "reads": {}, "components": {},
        "reported": {}, "reconciliation": {}, "relationships": {},
    }
    coverage = ctx.result["coverage"]
    coverage["collection_complete"] = False
    coverage["core_rfv"] = {"collection_complete": False, "scope": "canonical formula endpoints"}
    ctx.result["not_proven"].extend([
        "Core RFV does not enumerate unrecognized Treasury holdings or accidental transfers; outside-formula inventory is separate.",
        "Published interfaces and matching snapshot arithmetic do not prove deployed source equivalence or immutable policy. The 200 bps Morpho haircut is documented methodology, not a live parameter read.",
        "Core RFV is USDG-denominated accounting, not a redemption, solvency, USD peg or liquidity guarantee. LP look-through is memo only and must not be added again.",
    ])
    reads = _Reads(ctx, report)
    tv = {}
    for getter in ("rfv", "liquidUsdg", "morphoAssets", "backingPerToken"):
        unit = "USDG per NET wad" if getter == "backingPerToken" else "USDG wad"
        tv[getter] = reads.get("treasury." + getter, treasury, ta, getter, unit=unit)
        report["reported"][getter] = {"raw": _raw(tv[getter]), "decimals": 18, "unit": unit,
                                       "value": None if tv[getter] is None else amount(tv[getter], 18),
                                       "read": "treasury." + getter}
        ctx.checkpoint()

    def compare(target, key, observed, expected, unit):
        row = target[key] = _comparison(observed, expected, unit)
        if row["status"] == "mismatch":
            _problem(ctx, key, "Observed value differs from independently reconstructed or canonical value")
        return row["status"] == "match"

    for getter, name in (("net", "net"), ("usdg", "usdg"), ("morphoVault", "vault"), ("canonicalPair", "pair")):
        value = reads.get("treasury." + getter, treasury, ta, getter)
        compare(report["relationships"], "treasury." + getter, value, addresses[name], "address")
    code_ok = True
    for name in ("treasury", "usdg", "net", "vault", "pair"):
        code_ok = reads.code(name + ".code", addresses[name]) and code_ok

    ud = reads.get("usdg.decimals", usdg, token_abi, "decimals", unit="decimal places")
    nd = reads.get("net.decimals", net, token_abi, "decimals", unit="decimal places")
    cash = reads.get("usdg.treasury_balance", usdg, token_abi, "balanceOf", (treasury,), "USDG raw")
    supply = reads.get("net.totalSupply", net, token_abi, "totalSupply", unit="NET raw")
    report["denominator"] = {"basis": "total NET supply, not circulating supply", "contract": net,
                              "getter": "totalSupply", "block": ctx.block, "raw": _raw(supply),
                              "decimals": nd, "value": None if supply is None or nd is None else amount(supply, nd)}

    def calculate(key, function, *values):
        if any(value is None for value in values):
            return None
        try:
            return function(*values)
        except RpcError as error:
            _problem(ctx, key, error)
            return None

    def component(key, value, evidence, **extra):
        report["components"][key] = {
            "status": "unavailable" if value is None else "computed", "value_wad": _raw(value),
            "value_usdg": None if value is None else amount(value, 18),
            "unit": "USDG wad", "block": ctx.block, "reads": evidence, **extra,
        }
        ctx.checkpoint()

    cash_wad = calculate("liquid_usdg", _wad, cash, ud)
    component("liquid_usdg", cash_wad, ["usdg.treasury_balance", "usdg.decimals"], raw=_raw(cash), decimals=ud)
    asset = reads.get("vault.asset", vault, va, "asset")
    compare(report["relationships"], "vault.asset", asset, usdg, "address")
    vd = reads.get("vault.decimals", vault, va, "decimals", unit="decimal places")
    shares = reads.get("vault.treasury_shares", vault, va, "balanceOf", (treasury,), "vault shares raw")
    assets = None if shares is None else reads.get("vault.convertToAssets", vault, va, "convertToAssets", (shares,), "vault asset raw")
    gross = calculate("morpho_gross", _wad, assets, ud) if asset == usdg else None
    policy = source["methodology"]
    haircut_bps, bps = policy["morpho_haircut_bps"], policy["bps_denominator"]
    counted = None if gross is None else gross * (bps - haircut_bps) // bps
    component("morpho", counted, ["vault.asset", "vault.treasury_shares", "vault.convertToAssets", "usdg.decimals"],
              gross_wad=_raw(gross), gross_usdg=None if gross is None else amount(gross, 18),
              assets_raw=_raw(assets), asset_decimals=ud, shares_raw=_raw(shares), share_decimals=vd,
              haircut_bps=haircut_bps, haircut_wad=None if gross is None else str(gross - counted),
              parameter_status=policy["parameter_status"])

    t0 = reads.get("pair.token0", pair, pa, "token0")
    t1 = reads.get("pair.token1", pair, pa, "token1")
    pair_tokens_ok = None if t0 is None or t1 is None else {t0, t1} == {usdg, net}
    compare(report["relationships"], "pair.tokens", pair_tokens_ok, True, "canonical USDG/NET identity")
    reserves = reads.get("pair.getReserves", pair, pa, "getReserves", unit="token raw reserves; uint32 timestamp")
    lp_supply = reads.get("pair.totalSupply", pair, pa, "totalSupply", unit="LP raw")
    held = reads.get("pair.treasury_balance", pair, pa, "balanceOf", (treasury,), "LP raw")
    ld = reads.get("pair.decimals", pair, pa, "decimals", unit="decimal places")
    pol = None
    memo = {"additive": False, "scope": "Proportional reserve quantities, not an executable redemption quote"}
    if pair_tokens_ok and reserves is not None:
        r0, r1 = reserves["reserve0"], reserves["reserve1"]
        ru, rn = (r0, r1) if t0 == usdg else (r1, r0)
        pol = calculate("pol", _pol, ru, rn, ud, nd, held, lp_supply)
        if held is not None and lp_supply is not None and 0 <= held <= lp_supply and lp_supply > 0:
            for name, reserve, decimals in (("usdg", ru, ud), ("net", rn, nd)):
                raw = reserve * held // lp_supply
                memo[name] = {"raw": str(raw), "decimals": decimals,
                              "value": None if decimals is None else amount(raw, decimals),
                              "ownership_numerator": str(held), "ownership_denominator": str(lp_supply)}
    component("pol", pol, ["pair.token0", "pair.token1", "pair.getReserves", "pair.totalSupply", "pair.treasury_balance", "usdg.decimals", "net.decimals"],
              held_raw=_raw(held), total_supply_raw=_raw(lp_supply), lp_decimals=ld,
              integer_order=policy["pol_integer_order"], look_through_memo=memo)
    assembled = None if any(value is None for value in (cash_wad, counted, pol)) else cash_wad + counted + pol
    nav = calculate("nav", _nav, assembled, supply, nd)
    reported_nav = calculate("reported_nav", _nav, tv["rfv"], supply, nd)
    report["assembled"] = {"rfv_wad": _raw(assembled), "rfv_usdg": None if assembled is None else amount(assembled, 18),
                           "nav_wad": _raw(nav), "nav_usdg_per_net": None if nav is None else amount(nav, 18),
                           "basis": "independent canonical endpoint calculation; inspect relationships and reconciliation before use"}
    lp_usdg_raw = memo.get("usdg", {}).get("raw")
    own_net_pol_raw = memo.get("net", {}).get("raw")
    if pol == 0 and held == 0:
        lp_usdg_raw = own_net_pol_raw = "0"
    lp_usdg_wad = None if lp_usdg_raw is None else calculate("external_lp_usdg", _wad, int(lp_usdg_raw), ud)
    external_assets = None if any(v is None for v in (cash_wad, gross, lp_usdg_wad)) else cash_wad + gross + lp_usdg_wad
    report["external_asset_basis"] = {
        "value_wad": _raw(external_assets),
        "cash_wad": _raw(cash_wad), "gross_vault_claim_wad": _raw(gross),
        "lp_usdg_wad": _raw(lp_usdg_wad), "excluded_own_net_pol_raw": own_net_pol_raw,
        "own_net_decimals": nd,
        "scope": "Alternative external-claim basis: cash + full USDG vault claim + proportional LP USDG only. Excludes the LP NET leg; replaces, never adds to, Core RFV in net-assets.",
        "limits": "LP share floors to native units. Gross vault claims are not immediately withdrawable cash; this is not redemption proceeds or the risk-adjusted Treasury formula.",
    }
    for getter, expected in (("liquidUsdg", cash_wad), ("morphoAssets", gross), ("rfv", assembled), ("backingPerToken", nav)):
        compare(report["reconciliation"], getter, tv[getter], expected,
                "USDG per NET wad" if getter == "backingPerToken" else "USDG wad")
    compare(report["reconciliation"], "backing_from_reported_rfv", tv["backingPerToken"], reported_nav, "USDG per NET wad")
    complete = (code_ok and all(row["status"] == "match" for row in report["relationships"].values())
                and all(row["status"] == "match" for row in report["reconciliation"].values())
                and all(row["status"] == "observed" for row in report["reads"].values()))
    report["status"] = "reconciled" if complete else "partial"
    coverage["core_rfv"]["collection_complete"] = complete
    coverage["collection_complete"] = complete
    ctx.checkpoint()
    if args.scope != "core":
        import netstack_sleeve
        # A later partial Sleeve must not erase the independently completed Core.
        core = dict(addresses, usdg_decimals=ud, net_decimals=nd, rfv_wad=tv["rfv"],
                    supply_raw=supply, nav_wad=tv["backingPerToken"], core_complete=complete,
                    external_assets_wad=external_assets, own_net_pol_raw=own_net_pol_raw)
        coverage["collection_complete"] = False
        ctx.checkpoint()
        from netstack_discovery import inventory, token_candidates, inspect_tokens, discover_transfers, disposition
        audit = inventory(ctx, treasury, "treasury_inventory")
        core["treasury_inventory"] = audit
        inspect_tokens(ctx, audit, token_candidates(), token_abi)
        nft_abi = load_json("assets/analytics/sleeve-interface.json")["nfpm_abi"]
        discover_transfers(ctx, audit, token_abi, nft_abi)
        for candidate in audit["candidates"]:
            if candidate["address"] in (usdg, vault, pair):
                disposition(candidate, "excluded", "Already represented by the reconciled Core cash, vault claim or POL formula; never add custody again.")
        ctx.checkpoint()
        netstack_sleeve.collect(ctx, args, core)
        coverage["collection_complete"] = complete and coverage.get("collection_complete", False)
        ctx.checkpoint()

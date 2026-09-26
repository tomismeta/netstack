"""Pinned RPC sleeve inventory; Reports conventions are not economic net assets."""
from fractions import Fraction

from netstack_core import ZERO, RpcError, StopRun, amount, keccak256, load_json, ratio, resolve_routes
from netstack_v4 import collect as collect_v4, liquidity_amounts
from netstack_discovery import TRANSFER_WINDOW, inventory, token_candidates, inspect_tokens, discover_transfers, disposition

WAD = 10**18
Q128 = 1 << 128
MOD256 = 1 << 256
MAX_ITEMS = 128
FEED_MAX_AGE = 14400
FAMILIES = ("wallet", "credit", "v3", "turbo", "predict", "book", "v4", "advance", "treasury_extra")


def _raw(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Fraction):
        return ratio(value)
    if isinstance(value, dict):
        return {str(k): _raw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_raw(v) for v in value]
    return value


def _value_wad(value):
    return None if value is None else str(value.numerator // value.denominator)


def debt_assets(shares, assets, total_shares):
    """Morpho virtual shares: borrow conversion rounds up, never down."""
    denominator = total_shares + 10**6
    return (shares * (assets + 1) + denominator - 1) // denominator


def accrued_market(market, rate, timestamp):
    """Morpho v1.0.0 expectedMarketBalances, including fee-share dilution."""
    elapsed = timestamp - market["lastUpdate"]
    if elapsed < 0 or not 0 <= market["fee"] <= WAD:
        raise RpcError("Inconsistent Morpho timestamp or fee", kind="integrity")
    first = rate * elapsed
    second = first * first // (2 * WAD)
    third = second * first // (3 * WAD)
    interest = market["totalBorrowAssets"] * (first + second + third) // WAD
    supply = market["totalSupplyAssets"] + interest
    fee_assets = interest * market["fee"] // WAD
    fee_shares = fee_assets * (market["totalSupplyShares"] + 10**6) // (supply - fee_assets + 1)
    result = dict(market, totalSupplyAssets=supply,
                  totalBorrowAssets=market["totalBorrowAssets"] + interest,
                  totalSupplyShares=market["totalSupplyShares"] + fee_shares,
                  lastUpdate=timestamp)
    if (any(result[k] >= Q128 for k in result) or first * first >= MOD256 or second * first >= MOD256 or
        market["totalBorrowAssets"] * (first + second + third) >= MOD256 or
        fee_assets * (market["totalSupplyShares"] + 10**6) >= MOD256):
        raise RpcError("Morpho accrual exceeds deployed integer bounds", kind="integrity")
    return result, interest, fee_shares


def book_exposure(market):
    """Open-market maximum net house risk; the two outcomes are alternatives."""
    return max(0, market["owedFav"] - market["wagersDog"],
               market["owedDog"] - market["wagersFav"])


def book_claim(bet, market):
    """Reviewed Book bytecode settlement rule; raw wsNET, never a transaction."""
    if bet["settled"]:
        return {"stage": "settled", "payable": 0, "fee": 0, "reserved": 0}
    if market["state"] == 1:
        return {"stage": "open", "payable": None, "fee": None,
                "reserved": bet["reserve"] if bet["riskOff"] else bet["amount"]}
    if market["state"] not in (2, 3) or market["result"] not in (0, 1, 2):
        return {"stage": "unknown", "payable": None, "fee": None, "reserved": None}
    push = market["result"] == 2
    won = bet["side"] == market["result"]
    if not bet["riskOff"]:
        payout = bet["amount"] if push else 2 * bet["amount"] if won else 0
        return {"stage": "decided_unsettled", "payable": payout, "fee": 0,
                "reserved": bet["amount"] if won else 0}
    index = market["indexAtGrade"]
    if push:
        wager = 0
    elif index <= 0 or bet["index0"] <= 0:
        return {"stage": "unknown", "payable": None, "fee": None, "reserved": None}
    else:
        # ceil principal conversion preserves committed NET for the loser.
        principal = (bet["amount"] * bet["index0"] + index - 1) // index
        wager = min(max(0, bet["amount"] - principal), bet["reserve"])
    fee = wager * bet["feeBps"] // 10000
    payout = bet["amount"] if push else bet["amount"] + wager - fee if won else bet["amount"] - wager
    return {"stage": "decided_unsettled", "payable": payout, "fee": fee,
            "reserved": bet["reserve"] if won else 0, "wager": wager}


def predict_claims(assets, shares, price, pending, notice, count, live, generation_start, exit_price):
    """Effective shares already include converted queues and unmatured notices."""
    if assets != shares * price // WAD:
        raise RpcError("Predict assetsOf/share-price identity mismatch", kind="accounting")
    pstate = settled(pending["series"], count, live)
    nstate = settled(notice["series"], count, live)
    queued = pending["usdg"] if pstate is False else 0 if pstate is True else None
    claim = 0
    if notice["shares"]:
        if nstate is None:
            claim = None
        elif nstate:
            claim = None if exit_price is None else notice["shares"] * exit_price // WAD
    return {"active_share_assets": assets, "unconverted_pending": queued,
            "matured_notice": claim, "pending_converted": pstate, "notice_matured": nstate,
            "generation_start_series": generation_start}


def accrued_owed(liquidity, tick, lower, upper, global_growth, outside_lower,
                 outside_upper, last, stored):
    if liquidity == 0:
        return stored, 0
    below = outside_lower if tick >= lower else (global_growth - outside_lower) % MOD256
    above = outside_upper if tick < upper else (global_growth - outside_upper) % MOD256
    inside = (global_growth - below - above) % MOD256
    pending = liquidity * ((inside - last) % MOD256) // Q128
    if stored + pending >= Q128:
        raise RpcError("V3 credit exceeds uint128; overflow semantics unresolved", kind="integrity")
    return stored + pending, pending


def settled(series, count, live):
    if series == 0:
        return False
    if count is None or live is None:
        return None
    return series < count or (series == count and not live)


def feed_valid(round_data, now, max_age=FEED_MAX_AGE):
    return bool(round_data and round_data["answer"] > 0 and
                round_data["roundId"] > 0 and
                round_data["answeredInRound"] >= round_data["roundId"] and
                0 < round_data["updatedAt"] <= now and
                now - round_data["updatedAt"] <= max_age)


class Collector:
    def __init__(self, ctx, core):
        self.ctx, self.core = ctx, core
        self.routes = resolve_routes("sleeve")
        self.source = load_json(self.routes["_route"]["interface"])
        self.abis = {key: value for key, value in self.source.items() if key.endswith("_abi")}
        self.abis["house_abi"] = load_json("assets/analytics/house-interface.json")["abi"]
        self.abis["book_abi"] = load_json("assets/analytics/book-interface.json")["abi"]
        self.abis["predict_abi"] = load_json("assets/analytics/predict-interface.json")["abi"]
        self.abis["advance_abi"] = load_json("assets/analytics/advance-interface.json")["desk_abi"]
        self.owner = core["sleeve"].lower()
        self.usdg = core["usdg"].lower()
        self.net = core["net"].lower()
        self.snet, self.wsnet = self.address("snet"), self.address("wsnet")
        self.own_tokens = {self.net, self.snet, self.wsnet}
        self.cache, self.tokens, self.feeds, self.prices = {}, {}, {}, {}
        self.net_mark, self.index, self.usdg_usd = None, None, None
        self.scope = "reports"
        self.families = {name: {"status": "not_started", "rows": [], "missing": [],
                               "supplemental_missing": [], "historical_reports_collection_complete": False,
                               "collection_complete": False, "discovery_complete": False,
                               "historical_reports_value_wad": None} for name in FAMILIES}
        self.metrics = {"owner": self.owner, "block": ctx.block,
                        "interface_source": self.source["source_url"],
                        "interface_sha256": self.source["source_sha256"],
                        "components": self.families, "tokens": self.tokens,
                        "price_observations": self.prices, "reads": [],
                        "universe": {"arbitrary_erc20_exhaustive": False,
                                     "scope": "canonical six stocks plus live RWA/Pack/Asset menus, discovered collateral and NFT currencies; direct Sleeve custody only"},
                        "product_settlement": "Independent reconstruction only; never Predict's posted printWad or historical settlement."}
        ctx.result["metrics"]["sleeve"] = self.metrics
        self.values, self.economic_values = {}, {}
        self.economic_gaps = []
        self.methodology = {
            "status": "unavailable", "v4_principal_included": None, "fetched_this_run": False,
            "reviewed_at": None, "sources": [], "evidence": [],
            "reason": "Current publisher methodology has not yet been checked.",
            "limits": ["Methodology is a current source observation, not a pinned-chain fact."]}
        ctx.result["metrics"]["reports_methodology"] = self.methodology

    def address(self, key):
        return self.routes[key]["address"]

    def missing(self, family, message, supplemental=False):
        target = self.families[family]["supplemental_missing" if supplemental else "missing"]
        if message not in target:
            target.append(message)
        self.ctx.result["coverage"]["collection_complete"] = False

    def read(self, address, abi, method, args=()):
        address = address.lower()
        key = (address, abi, method, tuple(args))
        if key in self.cache:
            return self.cache[key]
        trace = {"contract": address, "getter": method, "arguments": _raw(args),
                 "block": self.ctx.block, "result": None}
        self.metrics["reads"].append(trace)
        try:
            value = self.ctx.call(address, self.abis[abi], method, args)
        except RpcError as exc:
            if exc.kind in ("permission", "integrity"):
                raise
            trace["error"] = str(exc)
            self.ctx.result["errors"].append({"scope": "sleeve:" + method + ":" + address,
                                                 "error": str(exc)})
            self.cache[key] = None
            return None
        trace["result"] = _raw(value)
        self.cache[key] = value
        return value

    def many(self, specs):
        # Context commits successful batch members even when another member fails.
        try:
            self.ctx.calls([(a, self.abis[abi], method, args) for a, abi, method, args in specs])
        except RpcError as exc:
            if exc.kind in ("permission", "integrity"):
                raise
        return [self.read(*spec) for spec in specs]

    def register(self, token, source, feed=None, symbol=None, oracle=None):
        token = token.lower()
        row = self.tokens.setdefault(token, {"sources": [], "symbol": symbol,
                                             "decimals": None, "feed": None, "oracle": None})
        if source not in row["sources"]:
            row["sources"].append(source)
        if symbol and not row["symbol"]:
            row["symbol"] = symbol
        for key, value in (("feed", feed), ("oracle", oracle)):
            if value and value.lower() != ZERO:
                value = value.lower()
                if row[key] and row[key] != value:
                    row["mapping_conflict"] = True
                else:
                    row[key] = value
        return row

    def code_matches(self, address, evidence):
        try:
            code = self.ctx.code(address)
        except RpcError as exc:
            if exc.kind in ("permission", "integrity"):
                raise
            return False
        actual = "0x" + keccak256(bytes.fromhex(code[2:])).hex()
        self.metrics.setdefault("code_identities", {})[address] = {
            "block": self.ctx.block, "keccak256": actual,
            "reviewed_keccak256": evidence["runtime_keccak256"],
            "matches": actual == evidence["runtime_keccak256"]}
        return actual == evidence["runtime_keccak256"]

    def feed_policy(self, feed):
        documented = self.source.get("feed_policies", {}).get(feed.lower())
        return documented or {"max_age_seconds": FEED_MAX_AGE, "policy_owner": "collector",
                              "basis": "Conservative 4-hour fallback; feed-specific heartbeat not established",
                              "market_hours_extension": False}

    def decimals(self, token):
        row = self.register(token, "observed_component")
        if row["decimals"] is None:
            row["decimals"] = self.read(token, "token_abi", "decimals")
        return row["decimals"]

    def mark(self, token, basis="wallet"):
        token = token.lower()
        if token == self.usdg:
            return Fraction(1)
        if token in self.own_tokens:
            if self.net_mark is None:
                return None
            if token != self.wsnet:
                return self.net_mark
            snet_decimals = self.decimals(self.snet)
            return None if self.index is None or snet_decimals is None else self.net_mark * Fraction(self.index, 10**snet_decimals)
        metadata = self.register(token, "observed_component")
        if metadata.get("mapping_conflict"):
            return None
        oracle = metadata["oracle"]
        if oracle:
            key = "twap:" + oracle
            if key not in self.prices:
                methods = ("priceWad", "asset", "assetDecimals", "quoteDecimals", "newestAt", "maxAge", "count", "window")
                vals = self.many([(oracle, "twap_abi", m, ()) for m in methods])
                data = dict(zip(methods, vals))
                valid = all(data[m] is not None for m in methods)
                valid = valid and data["asset"] == token and data["assetDecimals"] == self.decimals(token) and data["quoteDecimals"] == self.core["usdg_decimals"]
                valid = valid and data["priceWad"] > 0 and 0 < data["newestAt"] <= self.ctx.timestamp and self.ctx.timestamp - data["newestAt"] <= data["maxAge"]
                self.prices[key] = {"contract": oracle, "raw": _raw(data), "valid": bool(valid),
                                    "age_seconds": None if data["newestAt"] is None else self.ctx.timestamp - data["newestAt"],
                                    "basis": "USDG per whole asset, priceWad; no live spot fallback"}
                self.values[key] = Fraction(data["priceWad"], WAD) if valid else None
            return self.values[key]
        feed = metadata["feed"]
        if not feed:
            return None
        key = "feed:" + feed
        if key not in self.prices:
            rd, decimals = self.many([(feed, "feed_abi", "latestRoundData", ()), (feed, "feed_abi", "decimals", ())])
            policy = self.feed_policy(feed)
            valid = decimals is not None and feed_valid(rd, self.ctx.timestamp, policy["max_age_seconds"])
            self.prices[key] = {"contract": feed, "round": _raw(rd), "decimals": decimals,
                                "valid": valid, "max_age_seconds": policy["max_age_seconds"],
                                "freshness_policy": policy,
                                "age_seconds": None if rd is None else self.ctx.timestamp - rd["updatedAt"],
                                "basis": "USD feed; Reports USDG parity convention only"}
            self.values[key] = Fraction(rd["answer"], 10**decimals) if valid else None
        price = self.values[key]
        if basis in ("lp", "turbo") and price is not None:
            mult = self.read(token, "token_abi", "uiMultiplier")
            metadata["ui_multiplier_raw"] = _raw(mult)
            metadata["basis_warning"] = "Reports LP/TURBO use feed times uiMultiplier once. uiMultiplier is a display conversion, not another economic accrual or raw balance."
            return None if mult is None or mult <= 0 else price * Fraction(mult, WAD)
        return price

    def economic_mark(self, token):
        if token in self.own_tokens:
            return None
        price = self.mark(token, "wallet")
        if token == self.usdg or self.tokens[token].get("oracle"):
            return price
        if not self.tokens[token].get("direct_token_feed"):
            return Fraction() if price == 0 else None
        return None if price is None or self.usdg_usd is None else price / self.usdg_usd

    def quantity(self, family, token, raw, label, basis="wallet", sign=1,
                 reports=True, extra=None):
        token = token.lower()
        row = {"label": label, "token": token, "quantity_raw": _raw(raw),
               "block": self.ctx.block, "included_in_historical_reports": reports,
               "included_in_reports": None,
               "own_net_exposure": token in self.own_tokens, "basis": basis,
               "decimals": None, "amount": None, "reports_value_wad": None,
               "economic_value_wad": None, "sign": sign}
        if extra:
            row.update(extra)
        self.families[family]["rows"].append(row)
        self.values[id(row)] = self.economic_values[id(row)] = None
        if raw is None:
            self.missing(family, label + ": quantity unavailable", supplemental=not reports)
            return row
        decimals = self.decimals(token)
        row["decimals"] = decimals
        row["amount"] = None if decimals is None else amount(sign * raw, decimals)
        price = self.mark(token, basis) if raw else Fraction(0)
        value = None if decimals is None or price is None else Fraction(sign * raw, 10**decimals) * price * WAD
        self.values[id(row)] = value
        economic_price = self.economic_mark(token) if raw else Fraction()
        economic = None if decimals is None or economic_price is None else Fraction(sign * raw, 10**decimals) * economic_price * WAD
        self.economic_values[id(row)] = economic
        if economic is not None:
            row["economic_value_wad"] = str(economic.numerator // economic.denominator)
            metadata = self.tokens[token]
            if token == self.usdg:
                row["economic_basis"] = "Native USDG cash/claim; no USD peg assumption."
                row["economic_mark_observations"] = []
            elif metadata.get("oracle"):
                row["economic_basis"] = "Pinned asset TWAP in USDG per raw token; no feed/UI multiplier."
                row["economic_mark_observations"] = ["twap:" + metadata["oracle"]]
            else:
                row["economic_basis"] = "Exact catalog token/direct total-return feed divided by pinned USDG/USD; no uiMultiplier."
                row["economic_mark_observations"] = ["feed:" + metadata["feed"], "usdg_usd"] if metadata.get("feed") else []
        if value is not None:
            row["reports_value_wad"] = str(value.numerator // value.denominator)
            row["exact_value_wad"] = ratio(value)
            row["unit"] = "USDG under published Reports convention, not independent USD valuation"
        elif raw:
            self.missing(family, label + ": unpriced or stale; native quantity retained", supplemental=not reports)
        return row

    def finish(self, family, discovery=None):
        f = self.families[family]
        if discovery is not None:
            f["discovery_complete"] = discovery
        included = [r for r in f["rows"] if r["included_in_historical_reports"]]
        vals = [self.values.get(id(r)) for r in included]
        value = sum(vals, Fraction()) if all(v is not None for v in vals) and not f["missing"] else None
        f["historical_reports_value_wad"] = None if value is None else str(value.numerator // value.denominator)
        report_discovery = f.get("reports_discovery_complete", f["discovery_complete"])
        f["historical_reports_collection_complete"] = not f["missing"] and report_discovery and value is not None
        f["collection_complete"] = not f["missing"] and not f["supplemental_missing"] and f["discovery_complete"]
        f["status"] = "collected_known_scope" if f["collection_complete"] else "partial"
        self.ctx.checkpoint()

    def bootstrap(self):
        feed = load_json("assets/addresses/feeds/usdg.json")["contracts"][0]["address"].lower()
        rd, decimals = self.many([(feed, "feed_abi", "latestRoundData", ()), (feed, "feed_abi", "decimals", ())])
        policy = self.feed_policy(feed)
        valid = decimals is not None and feed_valid(rd, self.ctx.timestamp, policy["max_age_seconds"])
        self.usdg_usd = Fraction(rd["answer"], 10**decimals) if valid else None
        self.prices["usdg_usd"] = {"contract": feed, "round": _raw(rd), "decimals": decimals,
                                    "valid": valid, "max_age_seconds": policy["max_age_seconds"],
                                    "age_seconds": None if rd is None else self.ctx.timestamp - rd["updatedAt"],
                                    "freshness_policy": policy, "block": self.ctx.block}
        self.register(self.usdg, "core", symbol="USDG")
        self.tokens[self.usdg]["decimals"] = self.core["usdg_decimals"]
        for token, symbol in ((self.net, "NET"), (self.snet, "sNET"), (self.wsnet, "wsNET")):
            self.register(token, "canonical", symbol=symbol)
        self.tokens[self.net]["decimals"] = self.core["net_decimals"]
        for symbol in ("nvda", "spcx", "aapl", "googl", "msft", "coin"):
            catalog = load_json("assets/addresses/feeds/" + symbol + ".json")
            for mark in catalog.get("trusted_product_marks", []):
                row = self.register(mark["token_address"], "canonical_stock_catalog", mark["feed_address"], symbol.upper())
                row["direct_token_feed"] = True
                row["economic_mark_provenance"] = {"catalog": "assets/addresses/feeds/" + symbol + ".json",
                                                    "relationship": mark}
        self.register(self.address("hohm"), "canonical_asset_desk", symbol="hOHM", oracle=self.address("hohm_twap"))
        oracle = self.address("net_twap")
        price, pair, minimum, maximum, index = self.many([
            (oracle, "net_twap_abi", "twapNetUsdg", ()),
            (oracle, "net_twap_abi", "pair", ()),
            (oracle, "net_twap_abi", "twapMinWindow", ()),
            (oracle, "net_twap_abi", "twapMaxWindow", ()),
            (self.snet, "index_abi", "index", ())])
        self.index = index
        self.net_mark = Fraction(price, WAD) if price is not None and price > 0 and pair == self.core["pair"].lower() else None
        self.metrics["net_twap_index"] = {"oracle": oracle, "pair": pair, "twap_wad": _raw(price),
                                         "min_window_seconds": _raw(minimum), "max_window_seconds": _raw(maximum),
                                         "index_raw": _raw(index), "index_contract": self.snet,
                                         "block": self.ctx.block, "observation_age_seconds": None,
                                         "age_limit": "Published interface exposes windows, not last update; successful getter is not independently proven freshness."}
        menu, pack, assets = self.many([(self.address("rwa"), "rwa_abi", "menu", ()),
                                        (self.address("pack"), "pack_abi", "menuAssets", ()),
                                        (self.address("asset_desk"), "asset_desk_abi", "assetList", ())])
        self.metrics["menus"] = {"rwa": _raw(menu), "pack": _raw(pack), "asset_desk": _raw(assets)}
        for name, rows in (("rwa", menu), ("pack", pack), ("asset_desk", assets)):
            if rows is None:
                self.missing("wallet", name + " menu unavailable")
        for item in menu or []:
            self.register(item["token"], "rwa_menu", item["feed"])
        for token in pack or []:
            self.register(token, "pack_menu", self.read(self.address("pack"), "pack_abi", "feedOf", (token,)))
        for token in assets or []:
            info = self.read(self.address("asset_desk"), "asset_desk_abi", "assetInfo", (token,))
            self.register(token, "asset_desk_menu", oracle=info["oracle"] if info else None)
            if info is None:
                self.missing("wallet", "assetInfo unavailable for " + token)
        self.metrics["universe"]["menu_discovery_complete"] = all(v is not None for v in (menu, pack, assets))

    def wallet(self):
        observed = {row["token"] for row in self.families["wallet"]["rows"]}
        tokens = [token for token in self.tokens if token not in observed]
        specs = [(token, "token_abi", "balanceOf", (self.owner,)) for token in tokens]
        balances = self.many(specs)
        self.many([(t, "token_abi", "decimals", ()) for t in tokens if self.tokens[t]["decimals"] is None])
        for token, balance in zip(tokens, balances):
            self.quantity("wallet", token, balance, "Sleeve wallet", extra={"contract": token, "getter": "balanceOf(address)", "account": self.owner})
        self.families["wallet"]["reports_discovery_complete"] = self.metrics["universe"]["menu_discovery_complete"]
        self.finish("wallet", self.metrics["universe"]["menu_discovery_complete"])

    def credit(self):
        f = self.families["credit"]
        vault, morpho = self.address("credit_vault"), self.address("morpho")
        shares, asset = self.many([(vault, "vault_abi", "balanceOf", (self.owner,)),
                                   (vault, "vault_abi", "asset", ())])
        claim = None if shares is None else self.read(vault, "vault_abi", "convertToAssets", (shares,))
        if asset != self.usdg:
            self.missing("credit", "ERC4626 loan asset identity unavailable or mismatched")
            claim = None
        claim_row = self.quantity("credit", self.usdg, claim, "Credit ERC4626 claim", extra={"contract": vault, "getter": "convertToAssets(balanceOf(sleeve))", "shares_raw": _raw(shares)})
        f["vault_claim_complete"] = self.values.get(id(claim_row)) is not None
        ids = {row["market_id"] for row in load_json(self.routes["_route"]["markets"])["markets"]}
        router_id = self.read(self.address("loopback_router"), "router_abi", "marketId")
        if router_id:
            ids.add(router_id)
        f["market_ids"] = sorted(ids)
        f["markets"] = {}
        self.credit_ids(ids)
        f["universe"] = "catalog plus live Loopback marketId plus explicitly bounded recent Supply/SupplyCollateral window; earlier markets may be undiscovered"
        self.finish("credit", False)

    def credit_ids(self, ids):
        f = self.families["credit"]
        address = self.address("morpho")
        coverage = f.setdefault("stored_position_valuation_complete", {})
        for mid in sorted(ids):
            if mid in f["markets"]:
                continue
            coverage[mid] = False
            params, position, market = self.many([(address, "morpho_abi", "idToMarketParams", (mid,)),
                                                  (address, "morpho_abi", "position", (mid, self.owner)),
                                                  (address, "morpho_abi", "market", (mid,))])
            row = {"parameters": _raw(params), "position": _raw(position), "market": _raw(market), "block": self.ctx.block}
            f["markets"][mid] = row
            if params is None or position is None or market is None:
                self.missing("credit", mid + ": market/position/parameters unavailable")
                continue
            encoded = b"".join(bytes.fromhex(params[n][2:]).rjust(32, b"\0") for n in ("loanToken", "collateralToken", "oracle", "irm")) + params["lltv"].to_bytes(32, "big")
            if "0x" + keccak256(encoded).hex() != mid:
                self.missing("credit", mid + ": parameter hash mismatch")
                continue
            token = params["collateralToken"]
            self.register(token, "morpho_collateral")
            extra = {"contract": address, "market_id": mid, "getter": "position(bytes32,address)"}
            collateral_row = self.quantity("credit", token, position["collateral"], "Posted collateral", extra=extra)
            debt = debt_assets(position["borrowShares"], market["totalBorrowAssets"], market["totalBorrowShares"])
            debt_row = self.quantity("credit", params["loanToken"], debt, "Stored-share debt", sign=-1, extra=extra)
            coverage[mid] = all(self.values.get(id(r)) is not None for r in (collateral_row, debt_row))
            current, interest, fee_shares = None, None, None
            rate = 0
            supported = self.source["morpho_accrual_source"]
            if market["lastUpdate"] < self.ctx.timestamp and market["totalBorrowAssets"] and params["irm"] != ZERO:
                rate = None
                if address == supported["morpho"] and params["irm"] == supported["supported_irm"]:
                    parent = self.read(params["irm"], "morpho_accrual_abi", "MORPHO")
                    if parent == address:
                        pargs = tuple(params[n] for n in ("loanToken", "collateralToken", "oracle", "irm", "lltv"))
                        margs = tuple(market[n] for n in ("totalSupplyAssets", "totalSupplyShares", "totalBorrowAssets", "totalBorrowShares", "lastUpdate", "fee"))
                        rate = self.read(params["irm"], "morpho_accrual_abi", "borrowRateView", (pargs, margs))
            if rate is not None:
                current, interest, fee_shares = accrued_market(market, rate, self.ctx.timestamp)
            row["accrual"] = {"timestamp": self.ctx.timestamp, "average_borrow_rate_wad_per_second": _raw(rate),
                              "interest_assets_raw": _raw(interest), "fee_shares_raw": _raw(fee_shares),
                              "expected_market": _raw(current), "source": "morpho_accrual_source"}
            current_debt = None if current is None else debt_assets(position["borrowShares"], current["totalBorrowAssets"], current["totalBorrowShares"])
            debt_row["included_in_economic"] = False
            self.quantity("credit", params["loanToken"], 0 if not position["borrowShares"] else current_debt,
                          "Accrued Morpho debt", sign=-1, reports=False, extra=extra)
            supplied = None
            owner_shares = position["supplyShares"]
            if current is not None:
                if fee_shares:
                    recipient = self.read(address, "morpho_accrual_abi", "feeRecipient")
                    row["accrual"]["fee_recipient"] = recipient
                    if recipient is None:
                        owner_shares = None
                    elif recipient == self.owner:
                        owner_shares += fee_shares
                if owner_shares is not None:
                    supplied = owner_shares * (current["totalSupplyAssets"] + 1) // (current["totalSupplyShares"] + 10**6)
            elif not owner_shares and market["fee"] == 0:
                supplied = 0
            self.quantity("credit", params["loanToken"], supplied, "Accrued direct Morpho supply claim", reports=False, extra=extra)
            if current is None and (position["borrowShares"] or position["supplyShares"] or market["fee"]):
                self.economic_gaps.append("Morpho " + mid + ": current accrual unavailable; unsupported IRM or missing pinned borrowRateView/MORPHO identity.")
        f["market_ids"] = sorted(f["markets"])

    def predict(self):
        address = self.address("predict_house")
        names = ("assetsOf", "sharesOf", "pendingOf", "noticeOf")
        account = self.many([(address, "house_abi", n, (self.owner,)) for n in names])
        values = dict(zip(names, account))
        meta_names = ("seriesCount", "live", "generationStartSeries", "usdg", "desk", "sharePriceWad")
        meta = dict(zip(meta_names, self.many([(address, "house_abi", n, ()) for n in meta_names])))
        f = self.families["predict"]
        f["account"] = _raw(values)
        f["house"] = _raw(meta)
        if meta["usdg"] != self.usdg or meta["desk"] != self.address("predict_desk"):
            self.missing("predict", "House dependency identities unavailable or mismatched")
        self.quantity("predict", self.usdg, values["assetsOf"], "Predict House assetsOf only", extra={"contract": address, "getter": "assetsOf(address)", "account": self.owner})
        pending, notice = values["pendingOf"], values["noticeOf"]
        if any(v is None for v in account) or meta["sharePriceWad"] is None:
            self.missing("predict", "Attributable share/pending/notice getters unavailable", supplemental=True)
        elif not self.code_matches(address, self.source["predict_accounting_source"]):
            self.missing("predict", "House runtime differs from reviewed assetsOf/queue semantics", supplemental=True)
        else:
            exit_price = None
            if notice["shares"] and settled(notice["series"], meta["seriesCount"], meta["live"]):
                exit_price = self.read(address, "house_abi", "exitPriceWad", (notice["series"],))
            try:
                claims = predict_claims(values["assetsOf"], values["sharesOf"], meta["sharePriceWad"],
                                        pending, notice, meta["seriesCount"], meta["live"],
                                        meta["generationStartSeries"], exit_price)
            except RpcError as exc:
                self.missing("predict", str(exc), supplemental=True)
            else:
                f["claim_stages"] = _raw(claims)
                f["exit_price_raw"] = _raw(exit_price)
                for key, label in (("unconverted_pending", "Unconverted refundable deposit"),
                                   ("matured_notice", "Matured notice payable")):
                    self.quantity("predict", self.usdg, claims[key], label, reports=False,
                                  extra={"included_in_economic": True, "contract": address})
            f["overlap_policy"] = "assetsOf values effective active shares, including converted pending and unmatured notices. Add unconverted refundable deposit and matured exit once, never vault/desk gross USDG."
        f["reports_discovery_complete"] = values["assetsOf"] is not None
        self.finish("predict", all(v is not None for v in account))

    def book(self):
        address = self.address("book")
        names = ("potsOf", "freePot", "marketCount", "betCount", "wsNet", "sNet", "net")
        v = dict(zip(names, self.many([(address, "book_abi", n, ()) for n in names])))
        f = self.families["book"]
        f["raw"] = _raw(v)
        f["markets"] = {}
        if (v["wsNet"], v["sNet"], v["net"]) != (self.wsnet, self.snet, self.net):
            self.missing("book", "Book token identities unavailable or mismatched")
        pots = v["potsOf"]
        labels = ("House pot (gross)", "Reserved house risk", "Player locked wagers", "Player locked principal")
        for i, label in enumerate(labels):
            raw = None if pots is None else pots[str(i)]
            self.quantity("book", self.wsnet, raw, label, reports=i == 0,
                          extra={"contract": address, "getter": "potsOf()", "output_index": i})
        self.quantity("book", self.wsnet, v["freePot"], "Free pot (subset, not additional asset)", reports=False)
        balance = self.read(self.wsnet, "token_abi", "balanceOf", (address,))
        f["custody_balance_raw"] = _raw(balance)
        player_total, sleeve_account = self.many([
            (address, "book_balance_abi", "playerTotal", ()),
            (address, "book_balance_abi", "accountOf", (self.owner,))])
        f["player_total_raw"] = _raw(player_total)
        f["sleeve_account_free_locked_raw"] = _raw(sleeve_account)
        for key in ("free", "locked"):
            self.quantity("book", self.wsnet, None if sleeve_account is None else sleeve_account[key],
                          "Sleeve Book player account " + key, reports=False,
                          extra={"contract": address, "getter": "accountOf(address)",
                                 "account": self.owner, "attributable_to_sleeve": True})
        f["player_balance_unit"] = "raw wsNET; playerTotal is free player balances, not locked pots or Sleeve-owned cash"
        f["custody_accounting_residual_raw"] = None if pots is None or balance is None or player_total is None else str(balance - pots["0"] - player_total - pots["2"] - pots["3"])
        if player_total is None or sleeve_account is None:
            self.missing("book", "Dedicated player balance getter unavailable", supplemental=True)
        f["free_pot_residual_raw"] = None if pots is None or v["freePot"] is None else str(v["freePot"] - (pots["0"] - pots["1"]))
        f["liability_status"] = "Open risk is contingent; decided bet claims become free player balances on settlement. All Book backing and obligations are wsNET, excluded from external net assets."
        f["accounting_code_matches"] = self.code_matches(address, self.source["book_accounting_source"])
        if not f["accounting_code_matches"]:
            self.missing("book", "Book runtime differs from reviewed obligation semantics", supplemental=True)
        if f["free_pot_residual_raw"] not in (None, "0"):
            self.missing("book", "freePot differs from housePot minus reservedTotal", supplemental=True)
        if f["custody_accounting_residual_raw"] is not None and int(f["custody_accounting_residual_raw"]) < 0:
            self.missing("book", "Custody below house plus free players and locked pots", supplemental=True)
        f["reports_discovery_complete"] = pots is not None
        self.finish("book", False)
        return v["marketCount"]

    def book_markets(self, count):
        f = self.families["book"]
        if count is None:
            self.missing("book", "marketCount unavailable", supplemental=True)
            return
        low = max(1, count - MAX_ITEMS + 1)
        f["market_id_range"] = [low, count]
        if low > 1:
            self.missing("book", "Book market enumeration bounded to latest 128; earlier unpaid claims unresolved", supplemental=True)
        markets = {}
        for mid in range(count, low - 1, -1):
            value = self.read(self.address("book"), "book_abi", "marketOf", (mid,))
            f["markets"][str(mid)] = _raw(value)
            if value is None:
                self.missing("book", "marketOf unavailable: " + str(mid), supplemental=True)
            else:
                markets[mid] = value
        bet_count_raw = f["raw"].get("betCount")
        bet_count = None if bet_count_raw is None else int(bet_count_raw)
        f["bets"] = {}
        if bet_count is None:
            self.missing("book", "betCount unavailable", supplemental=True)
            return
        bet_low = max(1, bet_count - MAX_ITEMS + 1)
        f["bet_id_range"] = [bet_low, bet_count]
        f["bet_history_exhaustive"] = bet_low == 1
        f["uninspected_bet_id_ranges"] = [[1, bet_low - 1]] if bet_low > 1 else []
        open_risk = sum(book_exposure(m) for m in markets.values() if m["state"] == 1)
        reserved, wagers, principal, payable, sleeve_fees, house_delta = open_risk, 0, 0, 0, 0, 0
        resolved = low == 1 and len(markets) == count and f["accounting_code_matches"]
        for bid in range(bet_count, bet_low - 1, -1):
            bet = self.read(self.address("book"), "book_abi", "betOf", (bid,))
            entry = {"raw": _raw(bet)}
            f["bets"][str(bid)] = entry
            if bet is None or bet["marketId"] not in markets:
                resolved = False
                self.missing("book", "Bet or corresponding market unavailable: " + str(bid), supplemental=True)
                continue
            m = markets[bet["marketId"]]
            claim = book_claim(bet, m)
            entry["obligation"] = _raw(claim) if f["accounting_code_matches"] else None
            if bet["settled"]:
                continue
            if claim["stage"] == "unknown":
                resolved = False
                self.missing("book", "Settlement stage/index unresolved: bet " + str(bid), supplemental=True)
                continue
            if bet["riskOff"]:
                principal += bet["amount"]
            elif m["state"] == 1 or m["result"] == 2 or m["result"] == bet["side"]:
                wagers += bet["amount"]
            if claim["stage"] == "open":
                continue
            reserved += claim["reserved"]
            payable += claim["payable"]
            fee_sleeve = claim["fee"] - claim["fee"] // 2
            sleeve_fees += fee_sleeve
            if bet["riskOff"]:
                wager = claim.get("wager", 0)
                house_delta += -wager + claim["fee"] // 2 if m["result"] == bet["side"] else wager - fee_sleeve
            elif m["result"] == bet["side"]:
                house_delta -= bet["amount"]
        pots = f["raw"]["potsOf"]
        residuals = None if pots is None else {
            "reserved": int(pots["1"]) - reserved,
            "locked_wagers": int(pots["2"]) - wagers,
            "locked_principal": int(pots["3"]) - principal}
        if residuals is None or any(residuals.values()):
            resolved = False
            self.missing("book", "Bet-stage totals do not reconcile all reserved/locked pots; omitted payable claims unresolved", supplemental=True)
        f["obligations"] = {
            "unit": "wsNET raw", "source": "book_accounting_source",
            "open_contingent_house_exposure_raw": str(open_risk),
            "decided_unsettled_payouts_raw": str(payable) if resolved else None,
            "pending_fee_to_sleeve_raw": str(sleeve_fees) if resolved else None,
            "house_after_decided_settlement_raw": str(int(pots["0"]) + house_delta) if resolved and pots else None,
            "free_player_balances_raw": f["player_total_raw"],
            "remaining_reservation_raw": str(reserved),
            "state_reconciliation_residuals": _raw(residuals),
            "collection_complete": resolved,
            "method_status": "conditional_bytecode_and_conservation_reconstruction",
            "omitted_bet_rule": "Every positive unsettled risk-off payout retains locked principal; risk-on win/push retains locked wager, and a winner also retains house reservation. Zero residuals across all three nonnegative stocks exclude additional positive claims in uninspected bets. Settled payouts are already free playerTotal, not another obligation.",
            "economic_inclusion": "Excluded together with own-NET house backing; never subtract both alternative sides or gross player principal from external assets."}
        f["dedicated_liabilities"] = "Settled bet payouts are historical and already credited to playerTotal; current payable counts only decided unsettled bets. Fee counters are not additional balances."
        self.finish("book", resolved)

    def turbo(self):
        address = self.address("turbo")
        names = ("asset0", "asset1", "asset2", "usdgFees", "seriesCount", "sleeve", "usdg")
        vals = dict(zip(names, self.many([(address, "turbo_abi", n, ()) for n in names])))
        f = self.families["turbo"]
        f["raw"] = _raw(vals)
        f["books"], f["series"] = {}, {}
        if vals["sleeve"] != self.owner or vals["usdg"] != self.usdg:
            self.missing("turbo", "TURBO dependency identities unavailable or mismatched")
        for token in dict.fromkeys(vals[n] for n in ("asset0", "asset1", "asset2")):
            if token is None:
                self.missing("turbo", "TURBO asset getter unavailable")
                continue
            if token == ZERO:
                continue
            self.register(token, "turbo_assets")
            book = self.read(address, "turbo_abi", "bookOf", (token,))
            f["books"][token] = _raw(book)
            if book is None:
                self.missing("turbo", "bookOf unavailable for " + token)
                continue
            for key in ("potUnits", "reservedUnits", "feeManagerTok", "feeSleeveTok"):
                self.quantity("turbo", token, book[key], key, basis="turbo",
                              reports=key in ("potUnits", "reservedUnits"),
                              extra={"contract": address, "getter": "bookOf(address)", "asset_token": token,
                                     "attributable_to_sleeve": key != "feeManagerTok"})
            for key in ("putPotUsdg", "putReservedUsdg", "premiumUsdg"):
                self.quantity("turbo", self.usdg, book[key], key,
                              extra={"contract": address, "getter": "bookOf(address)", "asset_token": token})
        fees = vals["usdgFees"]
        for key in ("feeManager", "feeSleeve"):
            self.quantity("turbo", self.usdg, None if fees is None else fees[key], "USDG " + key,
                          reports=False, extra={"contract": address, "getter": "usdgFees()", "attributable_to_sleeve": key == "feeSleeve"})
        f["reports_discovery_complete"] = all(vals[n] is not None for n in ("asset0", "asset1", "asset2"))
        self.finish("turbo", False)
        return vals["seriesCount"]

    def turbo_series(self, count):
        f = self.families["turbo"]
        if count is None:
            self.missing("turbo", "seriesCount unavailable", supplemental=True)
            return
        low = max(1, count - MAX_ITEMS + 1)
        f["series_id_range"] = [low, count]
        if low > 1:
            self.missing("turbo", "TURBO series scan bounded to latest 128; older outstanding liabilities unresolved", supplemental=True)
        for sid in range(count, low - 1, -1):
            series = self.read(self.address("turbo"), "turbo_abi", "seriesOf", (sid,))
            row = {"raw": _raw(series), "liability_raw": None, "basis": None}
            f["series"][str(sid)] = row
            if series is None:
                self.missing("turbo", "seriesOf unavailable: " + str(sid), supplemental=True)
                continue
            outstanding = series["outstanding"]
            if not outstanding:
                row.update(liability_raw="0", basis="no outstanding cards")
                continue
            token = series["asset"] if series["side"] == 0 else self.usdg
            liability = None
            if series["state"] == 1:
                quote = self.read(self.address("turbo"), "turbo_abi", "quoteCashOut", (sid, outstanding, ZERO))
                row["quote"] = _raw(quote)
                if quote is not None:
                    liability = quote["netOut"] + quote["perfFee"]
                row["basis"] = "Published gross cashout indication for zero holder, not holder-specific entitlement, final settlement or an executable instruction"
            elif series["state"] == 3:
                liability = series["settlePerCard"] * outstanding
                row["basis"] = "posted settlePerCard times outstanding"
            elif series["state"] == 4 and series["sold"] > 0:
                token = self.usdg
                liability = series["premiumUsdgRaw"] * outstanding // series["sold"]
                row["basis"] = "publisher void premium refund proportion; rounding may depend on individual claims"
                self.economic_gaps.append("TURBO void per-holder rounding not established for series " + str(sid))
            elif series["state"] == 2:
                liability = 0
                row["basis"] = "publisher knocked-state zero payoff convention"
            if liability is None:
                self.missing("turbo", "Outstanding liability unresolved: " + str(sid), supplemental=True)
            row["liability_raw"] = _raw(liability)
            self.quantity("turbo", token, liability, "TURBO outstanding liability", basis="turbo", sign=-1,
                          reports=False, extra={"series_id": sid, "contract": self.address("turbo"), "liability_basis": row["basis"]})
        self.finish("turbo", low == 1)

    def v3(self):
        address = self.address("position_manager")
        count, factory = self.many([(address, "nfpm_abi", "balanceOf", (self.owner,)),
                                    (address, "nfpm_abi", "factory", ())])
        f = self.families["v3"]
        f["owned_nft_count"], f["positions"] = _raw(count), {}
        if count is None or factory != self.address("factory"):
            self.missing("v3", "NFT count or factory identity unavailable/mismatched")
            self.finish("v3", False)
            return
        if count > MAX_ITEMS:
            self.missing("v3", "NFT enumeration exceeds 128-position bound")
        ids = self.many([(address, "nfpm_abi", "tokenOfOwnerByIndex", (self.owner, i)) for i in range(min(count, MAX_ITEMS))])
        if len(set(ids)) != len(ids):
            self.missing("v3", "Duplicate/unavailable NFT IDs")
        for tid in ids:
            if tid is None:
                self.missing("v3", "NFT index unavailable")
                continue
            owner, p = self.many([(address, "nfpm_abi", "ownerOf", (tid,)), (address, "nfpm_abi", "positions", (tid,))])
            row = {"owner": owner, "raw": _raw(p)}
            f["positions"][str(tid)] = row
            if owner != self.owner or p is None:
                self.missing("v3", "Position/ownership unavailable: " + str(tid))
                continue
            pool = self.read(factory, "factory_abi", "getPool", (p["token0"], p["token1"], p["fee"]))
            row["pool"] = pool
            if pool is None or pool == ZERO:
                self.missing("v3", "Position pool unavailable: " + str(tid))
                continue
            names = ("factory", "token0", "token1", "fee", "slot0")
            data = dict(zip(names, self.many([(pool, "pool_abi", n, ()) for n in names])))
            row["pool_state"] = _raw(data)
            if (data["factory"], data["token0"], data["token1"], data["fee"]) != (factory, p["token0"], p["token1"], p["fee"]) or data["slot0"] is None:
                self.missing("v3", "Pool identity/state unavailable: " + str(tid))
                continue
            slot = data["slot0"]
            try:
                principal = liquidity_amounts(p["liquidity"], p["tickLower"], p["tickUpper"], slot["sqrtPriceX96"])
            except (ValueError, RpcError) as exc:
                self.missing("v3", str(exc))
                continue
            growth = None
            if p["liquidity"]:
                growth = self.many([(pool, "pool_abi", "feeGrowthGlobal0X128", ()),
                                    (pool, "pool_abi", "feeGrowthGlobal1X128", ()),
                                    (pool, "pool_abi", "ticks", (p["tickLower"],)),
                                    (pool, "pool_abi", "ticks", (p["tickUpper"],))])
            for i, token in enumerate((p["token0"], p["token1"])):
                self.register(token, "enumerated_v3_NFT")
                extra = {"nft_id": str(tid), "contract": address, "pool": pool,
                         "getter": "positions/slot0; standard exact TickMath principal"}
                self.quantity("v3", token, principal[i], "V3 LP principal", basis="lp", extra=extra)
                owed, pending = None, None
                if not p["liquidity"]:
                    owed, pending = p["tokensOwed" + str(i)], 0
                elif growth and all(g is not None for g in growth) and growth[2]["initialized"] and growth[3]["initialized"]:
                    try:
                        owed, pending = accrued_owed(p["liquidity"], slot["tick"], p["tickLower"], p["tickUpper"],
                                                     growth[i], growth[2]["feeGrowthOutside" + str(i) + "X128"],
                                                     growth[3]["feeGrowthOutside" + str(i) + "X128"],
                                                     p["feeGrowthInside" + str(i) + "LastX128"], p["tokensOwed" + str(i)])
                    except RpcError as exc:
                        self.missing("v3", str(exc), supplemental=True)
                self.quantity("v3", token, owed, "V3 mixed stored owed plus pending growth", basis="lp", reports=False,
                              extra={**extra, "stored_owed_raw": str(p["tokensOwed" + str(i)]),
                                     "pending_fee_growth_raw": _raw(pending),
                                     "fee_principal_split": "Stored owed can contain withdrawn principal; pending growth alone is new fee entitlement."})
        self.finish("v3", count <= MAX_ITEMS and len(set(ids)) == count and None not in ids)

    def v4(self):
        result = collect_v4(self.ctx, self.owner)
        f = self.families["v4"]
        f["inventory"] = result
        f["reports_scope"] = "Principal inclusion requires current supported publisher methodology; pending fees remain separate. The dated historical recipe excludes V4."
        for message in result.get("missing", []):
            self.missing("v4", str(message))
        for p in result.get("positions", []):
            if "currency0" not in p or "currency1" not in p:
                self.missing("v4", "Partial V4 position identity retained without invented token amounts")
                continue
            for i in (0, 1):
                token = p["currency" + str(i)]
                self.register(token, "verified_v4_position")
                for field, label in (("amount", "V4 principal"), ("fees", "V4 pending fees")):
                    value = p.get(field + str(i) + "_raw")
                    raw = None if value is None else int(value)
                    self.quantity("v4", token, raw, label, reports=False,
                                  extra={"nft_id": str(p["position_id"]), "pool_id": p["pool_id"],
                                         "exposure_kind": "principal" if field == "amount" else "fees",
                                         "owner": self.owner, "ownership_status": "verified_direct",
                                         "provenance": p.get("read_provenance")})
        self.finish("v4", result.get("ownership_complete", False) and result.get("collection_complete", False))

    def advance(self):
        family = self.families["advance"]
        desk = resolve_routes("advance")["desk"]["address"]
        family["contract"] = desk
        bindings = dict(zip(("house", "usdg", "wsNet", "sNet"), self.many([
            (desk, "advance_abi", method, ()) for method in ("house", "usdg", "wsNet", "sNet")])))
        family["bindings"] = bindings
        family["binding_complete"] = bindings == {
            "house": self.owner, "usdg": self.usdg, "wsNet": self.wsnet, "sNet": self.snet}
        fields = ("capacity", "unallocated", "escrowed", "inventory", "inventoryNet",
                  "lockedTotal", "positionCount", "halted")
        state = dict(zip(fields, self.many([(desk, "advance_abi", method, ()) for method in fields])))
        family["state"] = _raw(state)
        family["reader_complete"] = family["binding_complete"] and all(v is not None for v in state.values())
        if not family["binding_complete"]:
            self.missing("advance", "Advance House/token dependencies do not reconcile to the pinned Sleeve routes")
        if not family["reader_complete"]:
            self.missing("advance", "Publisher Advance reader or dependency bindings incomplete")
        for getter, token in (("unallocated", self.usdg), ("escrowed", self.usdg), ("inventory", self.wsnet)):
            row = self.quantity("advance", token, state[getter], "Advance " + getter, reports=False,
                                extra={"contract": desk, "getter": getter, "included_in_economic": False})
            row["economic_value_wad"] = None
            row["economic_basis"] = "Custody/receivable ownership and escrow liabilities not independently reconstructed."
            self.economic_values[id(row)] = None
        family["economic_missing"] = [
            "advance: custody, receivable ownership and escrow liabilities not independently reconstructed; no gross balances, collateral or owed amounts added to net assets."]
        self.finish("advance", family["reader_complete"])

    def credit_discovery(self):
        key = "sleeve_morpho_discovery"
        ids = set()
        address = self.address("morpho")
        topic_owner = "0x" + self.owner[2:].rjust(64, "0")
        start = max(0, self.ctx.block - TRANSFER_WINDOW + 1)
        self.families["credit"]["discovery_scope"] = {
            "searched_range": [start, self.ctx.block],
            "unsearched_prior_ranges": [[0, start - 1]] if start else [],
            "exhaustive": False, "methods": ["catalog", "live Loopback marketId", "incoming Supply/SupplyCollateral"]}
        try:
            for page in self.ctx.logs(key, address, self.abis["morpho_abi"], ["Supply", "SupplyCollateral"],
                                      start, self.ctx.block,
                                      indexed_topics=[None, None, topic_owner]):
                ids.update(event["values"]["id"] for event in page)
                self.families["credit"]["discovered_market_ids"] = sorted(ids)
                self.ctx.checkpoint()
        except RpcError as exc:
            if exc.kind in ("permission", "integrity"):
                raise
            self.missing("credit", "Bounded incoming Morpho position discovery failed: " + str(exc))
        self.credit_ids(ids)
        complete = self.ctx.result["coverage"].get(key, {}).get("event_coverage_complete", False)
        if not complete:
            self.missing("credit", "Requested Morpho discovery window incomplete; known markets retained")
        self.finish("credit", complete)
        self.wallet()

    def discover_assets(self):
        audit = inventory(self.ctx, self.owner, "sleeve_inventory")
        seeds = [{"address": token, "sources": row["sources"]} for token, row in self.tokens.items()]
        inspect_tokens(self.ctx, audit, seeds + token_candidates(), self.abis["token_abi"])
        discover_transfers(self.ctx, audit, self.abis["token_abi"], self.abis["nfpm_abi"])
        self.metrics["universe"]["candidate_inventory"] = audit
        self.account_inventory(audit, "wallet")
        treasury = self.core.get("treasury_inventory")
        if treasury is not None:
            self.metrics["universe"]["treasury_candidate_inventory"] = treasury
            self.account_inventory(treasury, "treasury_extra")
        else:
            self.finish("treasury_extra", True)

    def account_inventory(self, audit, family):
        observed = {r["token"] for r in self.families[family]["rows"]}
        for candidate in audit["candidates"]:
            token = candidate["address"]
            if candidate["disposition"] == "excluded":
                continue
            if candidate["asset_kind"] == "erc721" and audit["owner"] == self.owner:
                tid = candidate["token_id"]
                v3 = self.families["v3"].get("positions", {})
                v4 = self.families["v4"].get("inventory", {})
                if ((token == self.address("position_manager") and tid in v3 and v3[tid].get("owner") == self.owner) or
                    any(str(p.get("position_id")) == tid and token == v4.get("position_manager") for p in v4.get("positions", []))):
                    disposition(candidate, "excluded", "Attributed LP underlying/fees already represented by position ledger; NFT is not an additional asset.")
                    continue
            if candidate["asset_kind"] == "erc20" and candidate["ownership"]["status"] == "verified_direct":
                if audit["owner"] == self.owner and token == self.address("credit_vault"):
                    disposition(candidate, "excluded", "Credit ERC4626 claim already represented; receipt token is not an additional asset.")
                    continue
                if token in self.tokens:
                    if token not in observed:
                        self.quantity(family, token, int(candidate["quantity_raw"]), "Discovered direct custody",
                                      reports=False, extra={"included_in_economic": True, "account": audit["owner"],
                                                           "candidate_sources": candidate["sources"]})
                        observed.add(token)
                    matched = next(r for r in self.families[family]["rows"] if r["token"] == token)
                    if token in self.own_tokens:
                        disposition(candidate, "excluded", "Own-NET exposure disclosed separately, not external economic backing.")
                    elif matched["economic_value_wad"] is not None:
                        disposition(candidate, "included", "Direct quantity and independently mapped pinned mark represented once in economic ledger.")
                    else:
                        disposition(candidate, "unpriced", "Native quantity retained; exact token/feed economics or freshness unresolved.")
            if candidate["disposition"] not in ("included", "excluded"):
                self.missing(family, "Candidate " + token + ((" NFT " + candidate["token_id"]) if candidate["token_id"] else "") +
                             ": " + candidate["reason"], supplemental=True)
        complete = not audit["candidate_limit_reached"] and all(s.get("status", "completed") == "completed" for s in audit["searches"])
        if not complete:
            self.missing(family, "Bounded candidate search incomplete; inspect searched/unsearched ranges", supplemental=True)
        self.finish(family, complete and (family != "wallet" or self.metrics["universe"]["menu_discovery_complete"]))

    def check_methodology(self):
        self.methodology.update(status="unavailable", v4_principal_included=None,
                                fetched_this_run=False, reason="Current methodology check in progress.")
        try:
            from netstack_methodology import collect_reports_methodology
            evidence = collect_reports_methodology(self.ctx)
            if not isinstance(evidence, dict):
                raise ValueError("Methodology evidence unavailable")
            self.methodology = evidence
        except StopRun:
            raise
        except RpcError as exc:
            if exc.kind in ("permission", "integrity"):
                raise
            self.methodology = dict(self.ctx.result["metrics"].get("reports_methodology", self.methodology), status="unavailable",
                                    v4_principal_included=None, fetched_this_run=False,
                                    reason="Current methodology retrieval failed: " + exc.kind)
        except Exception as exc:
            self.methodology = dict(self.ctx.result["metrics"].get("reports_methodology", self.methodology), status="unavailable",
                                    v4_principal_included=None, fetched_this_run=False,
                                    reason="Current methodology unavailable: " + type(exc).__name__)
        self.ctx.result["metrics"]["reports_methodology"] = self.methodology

    def v4_details(self, inclusion):
        family = self.families["v4"]
        inventory = family.get("inventory", self.ctx.result["metrics"].get("v4_positions", {}))
        ownership_complete = inventory.get("ownership_complete", False)
        expected = inventory.get("expected_owned_count")
        supported_tokens = {self.usdg, self.wsnet}
        hohm = self.address("hohm")
        if "asset_desk_menu" in self.tokens.get(hohm, {}).get("sources", []):
            supported_tokens.add(hohm)
        scope = self.methodology.get("v4_position_scope", {})
        scope_valid = (scope.get("selection") == "publisher_registry_allowlist" and
                       scope.get("position_manager", "").lower() == inventory.get("position_manager") and
                       scope.get("owner", "").lower() == self.owner and
                       isinstance(scope.get("token_ids"), list))
        selected_ids = set(scope.get("token_ids", [])) if scope_valid else set()
        owned_ids = {str(p["position_id"]) for p in inventory.get("candidates", [])
                     if p.get("owner") == self.owner}
        selected_owned = owned_ids & selected_ids
        for row in family["rows"]:
            row["included_in_reports"] = (
                inclusion and row.get("exposure_kind") == "principal" and
                row.get("nft_id") in selected_ids) if scope_valid and inclusion is not None else (
                    False if inclusion is False else None)
        summary = {
            "block": self.ctx.block, "owner": self.owner,
            "publisher_principal_included": inclusion,
            "publisher_fees_included": False if inclusion is not None else None,
            "historical_recipe_included": False,
            "publisher_position_scope": scope,
            "publisher_position_scope_supported": scope_valid,
            "owned_positions_outside_publisher_scope": sorted(owned_ids - selected_ids) if scope_valid else None,
            "observed_positions": inventory.get("positions", []),
            "ownership": {
                "collection_complete": ownership_complete, "expected_owned_count": expected,
                "observed_owned_count": inventory.get("observed_owned_count"),
                "status": inventory.get("ownership_status"),
                "reason": inventory.get("ownership_reason"),
                "history_complete": inventory.get("history_complete"),
                "discovery": inventory.get("discovery"),
                "position_manager": inventory.get("position_manager"),
                "candidates": inventory.get("candidates", []),
                "read_provenance": [r for r in inventory.get("read_provenance", [])
                                    if r.get("getter") in ("balanceOf", "ownerOf")],
                "uninspected": inventory.get("uninspected", [])},
            "missing": list(dict.fromkeys(inventory.get("missing", []) + family["missing"] + family["supplemental_missing"])),
            "economic_treatment": "Include attributable external principal and pending fees once at supported economic marks; exclude every own NET/sNET/wsNET leg, including fees.",
            "valuation_basis": "Pinned RPC quantities and marks only; USDG cash, wsNET at NET TWAP times index, hOHM at supported desk oracle. No website numerical input or live spot fallback."}
        publisher_principal = None
        for kind in ("principal", "fees"):
            rows = [r for r in family["rows"] if r.get("exposure_kind") == kind]
            values = [self.values.get(id(r)) for r in rows]
            known = sum((v for v in values if v is not None), Fraction())
            quantities_complete = (ownership_complete and expected is not None and
                                   len(rows) == 2 * expected and
                                   all(r["quantity_raw"] is not None for r in rows))
            valued = quantities_complete and all(v is not None for v in values)
            publisher_supported = all(r["quantity_raw"] == "0" or r["token"] in supported_tokens
                                      for r in rows)
            own = sum((self.values.get(id(r)) or Fraction()) for r in rows if r["own_net_exposure"])
            external_rows = [r for r in rows if not r["own_net_exposure"]]
            external = [self.economic_values.get(id(r)) for r in external_rows]
            external_total = (sum(external, Fraction()) if quantities_complete and
                              all(v is not None for v in external) else None)
            summary[kind] = {
                "rows": rows, "quantity_collection_complete": bool(quantities_complete),
                "valuation_complete": bool(valued),
                "reports_value_wad": str(known.numerator // known.denominator) if valued else None,
                "known_priced_subtotal_wad": str(known.numerator // known.denominator),
                "publisher_valuation_supported": publisher_supported,
                "economic_external_value_wad": _value_wad(external_total),
                "own_net_known_reports_mark_wad": str(own.numerator // own.denominator)}
            if kind == "principal":
                selected = [r for r in rows if r.get("nft_id") in selected_owned]
                selected_values = [self.values.get(id(r)) for r in selected]
                selected_complete = (scope_valid and ownership_complete and
                                     len(selected) == 2 * len(selected_owned) and
                                     all(v is not None for v in selected_values) and
                                     all(r["quantity_raw"] == "0" or r["token"] in supported_tokens for r in selected))
                if selected_complete:
                    publisher_principal = sum(selected_values, Fraction())
        impact = publisher_principal if inclusion is True else Fraction() if inclusion is False else None
        summary["publisher_total_impact_wad"] = _value_wad(impact)
        summary["principal_if_included_wad"] = _value_wad(publisher_principal)
        summary["impact_status"] = ("included" if inclusion is True and publisher_principal is not None else
                                    "excluded" if inclusion is False else
                                    "unvalued" if inclusion is True else "methodology_unverified")
        return publisher_principal, summary

    def publisher_rows(self, methodology_valid):
        policy = self.methodology.get("selection_policy", {})
        v3, wallet, credit = (policy.get(name, {}) for name in ("v3", "wallet", "credit"))
        supported = (v3.get("selection") == "owner_enumeration" and v3.get("fee") == 500 and
                     v3.get("position_manager") == self.address("position_manager") and
                     v3.get("usdg") == self.usdg and isinstance(v3.get("assets"), list) and
                     isinstance(wallet.get("fixed_stock_tokens"), list) and
                     isinstance(credit.get("market_ids"), list) and
                     credit.get("vault") == self.address("credit_vault"))
        advance = policy.get("advance")
        advance_supported = (isinstance(advance, dict) and
                             advance.get("desk") == self.families["advance"].get("contract") and
                             advance.get("principal_fields") == ["unallocated", "escrowed", "inventory"] and
                             advance.get("usdg_decimals") == 6 and advance.get("wsnet_decimals") == 18)
        gaps = [] if supported else ["Publisher component selection policy is unavailable or incompatible with collector routes."]
        if advance is not None and not advance_supported:
            gaps.append("Publisher Advance selection policy is incompatible with the observed desk.")
        assets = v3.get("assets", []) if supported else []
        pools = {asset["pool"] for asset in assets}
        stocks = {asset["token"] for asset in assets}
        fixed = set(wallet.get("fixed_stock_tokens", []))
        market_ids = set(credit.get("market_ids", []))
        selected = []
        for name, family in self.families.items():
            if name == "v4":
                continue
            for row in family["rows"]:
                include = row["included_in_historical_reports"]
                if name == "advance":
                    include = advance_supported and row.get("getter") in advance["principal_fields"]
                    if include and row["decimals"] != (6 if row["token"] == self.usdg else 18):
                        gaps.append("Publisher Advance token decimals do not match the reviewed calculation.")
                token = row["token"]
                metadata = self.tokens.get(token, {})
                sources = set(metadata.get("sources", []))
                if include and supported:
                    if name == "v3":
                        include = row.get("pool") in pools
                    elif name == "wallet":
                        stock = token in fixed or bool(sources & {"rwa_menu", "pack_menu"})
                        desk = "asset_desk_menu" in sources
                        include = token in self.own_tokens or token == self.usdg or stock or desk
                        if stock and desk and row["quantity_raw"] != "0":
                            gaps.append("Overlapping stock and asset-desk custody requires separately reviewed publisher multiplicity: " + token)
                    elif name == "credit":
                        include = (row.get("market_id") in market_ids if "market_id" in row
                                   else row.get("contract") == credit["vault"])
                    elif name == "turbo":
                        include = row.get("asset_token") in stocks
                    if include and token not in self.own_tokens and token != self.usdg and metadata.get("feed") and row["quantity_raw"] != "0":
                        observed_feed = self.prices.get("feed:" + metadata["feed"], {})
                        if row["decimals"] != 18 or observed_feed.get("decimals") != 8:
                            gaps.append("Publisher stock 18-decimal token/8-decimal feed convention not matched: " + token)
                row["included_in_reports"] = include if methodology_valid and supported else None
                if include and supported:
                    selected.append(row)
        return selected, list(dict.fromkeys(gaps))

    def publish(self, checkpoint=True):
        metrics = self.ctx.result["metrics"]
        self.methodology = metrics.get("reports_methodology", self.methodology)
        methodology_valid = (self.methodology.get("status") == "verified" and
                             self.methodology.get("fetched_this_run") is True and
                             type(self.methodology.get("v4_principal_included")) is bool)
        inclusion = self.methodology["v4_principal_included"] if methodology_valid else None
        replica_names = tuple(name for name in FAMILIES if name not in ("v4", "advance", "treasury_extra"))
        core_complete = self.core.get("core_complete", False) and self.core.get("rfv_wad") is not None
        historical_complete = core_complete and all(
            self.families[name]["historical_reports_collection_complete"] for name in replica_names)
        known_rows = [r for f in self.families.values() for r in f["rows"]]
        historical_subtotal = sum((self.values.get(id(r)) or Fraction()) for r in known_rows
                                  if r["included_in_historical_reports"])
        historical_total = historical_subtotal + self.core["rfv_wad"] if historical_complete else None
        historical_missing = {
            n: f["missing"] or ["Included quantity/valuation or discovery not complete"]
            for n, f in self.families.items()
            if n in replica_names and not f["historical_reports_collection_complete"]}
        if not core_complete:
            historical_missing["core"] = ["Core RFV reconstruction incomplete"]
        selected_rows, selection_gaps = self.publisher_rows(methodology_valid)
        v4_principal, v4_details = self.v4_details(inclusion)
        credit_policy = self.methodology.get("selection_policy", {}).get("credit", {})
        credit_family = self.families["credit"]
        credit_required_ids = credit_policy.get("market_ids", [])
        credit_complete = (credit_family.get("vault_claim_complete", False) and
                           bool(credit_required_ids) and
                           all(credit_family.get("stored_position_valuation_complete", {}).get(mid, False)
                               for mid in credit_required_ids) and
                           all(self.values.get(id(row)) is not None for row in credit_family["rows"]
                               if row["included_in_reports"] is True))
        publisher_family_complete = {
            name: credit_complete if name == "credit" else self.families[name]["historical_reports_collection_complete"]
            for name in replica_names}
        advance_selected = self.methodology.get("selection_policy", {}).get("advance") is not None
        advance_family = self.families["advance"]
        publisher_family_complete["advance"] = (
            not advance_selected or
            (advance_family.get("reader_complete", False) and
             len(advance_family["rows"]) == 3 and
             all(row["included_in_reports"] is True and self.values.get(id(row)) is not None
                 for row in advance_family["rows"])))
        pinned_complete = core_complete and all(publisher_family_complete.values()) and (inclusion is False or v4_principal is not None)
        complete = methodology_valid and not selection_gaps and pinned_complete
        subtotal = (sum((self.values.get(id(r)) or Fraction()) for r in selected_rows) +
                    (v4_principal or Fraction()) * (inclusion is True)) if methodology_valid and not selection_gaps else None
        total = subtotal + self.core["rfv_wad"] if complete else None
        missing = {name: messages for name, messages in historical_missing.items() if name != "credit"}
        if not credit_complete:
            missing["credit"] = ["Publisher-selected vault claim or stored market position valuation incomplete."]
        if not publisher_family_complete["advance"]:
            missing["advance"] = advance_family["missing"] + advance_family["supplemental_missing"] or [
                "Publisher Advance snapshot, dependency bindings or marks incomplete."]
        if not methodology_valid:
            missing["methodology"] = ["Current supported publisher calculation was not fetched and verified in this run."]
        if selection_gaps:
            missing["publisher_selection"] = selection_gaps
        if inclusion is not False and v4_principal is None:
            missing["v4"] = self.families["v4"]["missing"] or [
                "V4 ownership, principal quantities or supported publisher marks incomplete"]
        metrics["reports_historical_rfv"] = {
            "recipe_date": "2026-09-25",
            "scope": "Frozen 2026-09-25 known-component Reports recipe at the requested block; not the current publisher total or a historical-block observation.",
            "unit": "USDG under published stock-feed USD parity convention",
            "value_wad": _value_wad(historical_total),
            "value": None if historical_total is None else amount(historical_total.numerator // historical_total.denominator, 18),
            "known_components_subtotal_wad": _value_wad(historical_subtotal),
            "collection_complete": bool(historical_complete), "required_missing": historical_missing,
            "component_selection": "metrics.component_summary"}
        metrics["reports_true_rfv"] = {
            "scope": "Current publisher-source-derived pinned RPC reconstruction; not independently matched to a rendered headline, product settlement or exhaustive net assets",
            "unit": "USDG under published stock-feed USD parity convention",
            "value_wad": _value_wad(total),
            "value": None if total is None else amount(total.numerator // total.denominator, 18),
            "known_components_subtotal_wad": _value_wad(subtotal),
            "collection_complete": bool(complete), "pinned_collection_complete": bool(pinned_complete),
            "methodology_valid": methodology_valid, "methodology_status": self.methodology.get("status"),
            "publisher_selection_valid": not selection_gaps,
            "selection_policy": self.methodology.get("selection_policy"),
            "methodology_evidence": "metrics.reports_methodology",
            "core_complete": bool(core_complete), "required_missing": missing,
            "component_summary": "metrics.component_summary",
            "publisher_headline_comparison": {
                "status": "unavailable", "publisher_value_wad": None, "difference_wad": None,
                "reason": "No independent comparable displayed headline observation; static source review does not observe a rendered value."},
            "excluded_known_exposure": "Each component summary discloses selected, excluded and unclassified rows, unresolved valuations, and distinct economic treatment.",
            "rounding": "Sum exact rational row values, floor once to 18 decimals; never sum displayed values."}
        own = Fraction()
        external, own_ledger, net_values = {}, [], []
        gaps = list(self.economic_gaps)
        if not core_complete:
            gaps.append("Core RFV reconstruction incomplete")
        core_external = self.core.get("external_assets_wad")
        if core_external is None:
            gaps.append("Treasury external-asset basis unavailable; Core geometric own-NET POL is not external backing")
        needs_usd_conversion = any(r["quantity_raw"] not in (None, "0") and
                                   not r["own_net_exposure"] and self.tokens.get(r["token"], {}).get("feed")
                                   for r in known_rows)
        if needs_usd_conversion and self.usdg_usd is None:
            obs = self.prices.get("usdg_usd", {})
            gaps.append("USDG/USD conversion unavailable: round age " + str(obs.get("age_seconds")) +
                        " seconds; applicable current-mark limit " + str(obs.get("max_age_seconds")) +
                        " seconds; positive stock exposures retained without economic valuation.")
        component_summary = {}
        economic_treatment = {
            "wallet": "External direct custody at supported economic marks; all own NET/sNET/wsNET excluded.",
            "credit": "Accrued debt replaces stored debt; attributable accrued supply and vault claims included once; own-token collateral excluded.",
            "v3": "External LP principal and attributable mixed owed/pending growth included once; own-token legs excluded.",
            "turbo": "External principal and attributable sleeve fees less supported liabilities; manager fees and own-token legs excluded.",
            "predict": "Active claims, refundable deposits and matured exits included once, without adding gross vault custody.",
            "book": "Own-NET house backing and obligations disclosed separately and excluded from external backing; attributable external claims only.",
            "v4": "External LP principal and attributable pending fees included once; own-token principal and fees excluded.",
            "advance": "Publisher reserve snapshot only; collateral and owed are not added. Economic ownership, escrow liabilities and receivables remain unresolved.",
            "treasury_extra": "Discovered external Treasury custody not already represented in Core; own-token holdings excluded."}
        for name, family in self.families.items():
            selected = []
            if not family["discovery_complete"]:
                gaps.append(name + ": scoped discovery incomplete")
            for message in family["missing"] + family["supplemental_missing"]:
                if ": unpriced or stale;" not in message:
                    gaps.append(name + ": " + message)
            gaps.extend(family.get("economic_missing", []))
            for row in family["rows"]:
                additive = row["included_in_historical_reports"] or name in ("v3", "v4", "credit", "treasury_extra")
                if name == "turbo" and not additive:
                    additive = row.get("attributable_to_sleeve", False) or "liability_basis" in row
                if name == "book" and row.get("attributable_to_sleeve"):
                    additive = True
                additive = row.get("included_in_economic", additive)
                if not additive:
                    continue
                entry = {"token": row["token"], "quantity_raw": row["quantity_raw"], "sign": row["sign"],
                         "label": row["label"], "basis": row["basis"],
                         "economic_value_wad": row["economic_value_wad"],
                         "indicative_reports_basis_wad": row["reports_value_wad"], "block": self.ctx.block}
                for key in ("contract", "account", "market_id", "nft_id", "economic_basis", "economic_mark_observations"):
                    if key in row:
                        entry[key] = row[key]
                if row["own_net_exposure"]:
                    own_ledger.append(dict(entry, family=name))
                    own += self.values.get(id(row)) or Fraction()
                else:
                    value = self.economic_values.get(id(row))
                    selected.append((entry, value))
                    if value is None:
                        gaps.append(name + ": " + row["label"] + " economic quantity/mark missing for " + row["token"])
            exact = sum((v for _, v in selected), Fraction()) if all(v is not None for _, v in selected) else None
            if exact is not None:
                net_values.append(exact)
            external[name] = {"rows": [r for r, _ in selected],
                              "known_rows_value_wad": None if exact is None else str(exact.numerator // exact.denominator),
                              "collection_complete": family["collection_complete"]}
            rows = family["rows"]
            chosen = [i for i, row in enumerate(rows) if row["included_in_reports"] is True]
            excluded = [i for i, row in enumerate(rows) if row["included_in_reports"] is False]
            unclassified = [i for i, row in enumerate(rows) if row["included_in_reports"] is None]
            selected_values = [self.values.get(id(rows[i])) for i in chosen]
            selected_subtotal = sum((v for v in selected_values if v is not None), Fraction())
            publisher_complete = (methodology_valid and not selection_gaps and
                                  publisher_family_complete.get(name, False))
            contribution = selected_subtotal if publisher_complete else None
            if name == "v4":
                contribution = (v4_principal if inclusion is True else
                                Fraction() if inclusion is False else None)
                publisher_complete = methodology_valid and contribution is not None
            elif name == "treasury_extra":
                publisher_complete = methodology_valid and not selection_gaps
                contribution = Fraction() if publisher_complete else None
            policy_key = "sportsbook" if name == "book" else name
            policy = (self.methodology.get("v4_position_scope") if name == "v4" else
                      {"selection": "Outside publisher Reports scope"} if name == "treasury_extra" else
                      self.methodology.get("selection_policy", {}).get(policy_key))
            component_gaps = [message for message in gaps if message.startswith(name + ":")]
            if name == "credit":
                component_gaps.extend(self.economic_gaps)
            component_summary[name] = {
                "status": family["status"],
                "observed": {"collection_complete": family["collection_complete"],
                             "discovery_complete": family["discovery_complete"], "rows": rows},
                "valuation": {
                    "reports_basis_complete": family["collection_complete"] and
                                              all(self.values.get(id(row)) is not None for row in rows),
                    "valued_row_count": sum(self.values.get(id(row)) is not None for row in rows),
                    "unpriced_row_indices": [i for i, row in enumerate(rows) if self.values.get(id(row)) is None],
                    "meaning": "Individual row marks are not an additive total; alternative debt/claim analyses may overlap."},
                "publisher": {
                    "selection": policy, "collection_complete": bool(publisher_complete),
                    "contribution_wad": _value_wad(contribution),
                    "known_selected_subtotal_wad": _value_wad(selected_subtotal) if methodology_valid else None,
                    "selected_row_indices": chosen, "excluded_row_indices": excluded,
                    "unclassified_row_indices": unclassified,
                    "required_missing": ([] if publisher_complete else
                                         missing.get(name, []) + selection_gaps +
                                         ([] if methodology_valid else missing.get("methodology", [])))},
                "historical": {
                    "included": name in replica_names,
                    "contribution_wad": family["historical_reports_value_wad"] if name in replica_names else "0",
                    "collection_complete": family["historical_reports_collection_complete"] if name in replica_names else True},
                "economic": {
                    "treatment": economic_treatment[name],
                    "known_rows_value_wad": external[name]["known_rows_value_wad"],
                    "collection_complete": not component_gaps, "required_missing": component_gaps,
                    "external_rows": external[name]["rows"],
                    "excluded_own_net_rows": [row for row in own_ledger if row["family"] == name]},
                "missing": list(dict.fromkeys(family["missing"] + family["supplemental_missing"])),
                "details": v4_details if name == "v4" else {"evidence": "metrics.sleeve.components." + name}}
        gaps = list(dict.fromkeys(gaps))
        net_total = core_external + sum(net_values, Fraction()) if not gaps else None
        metrics["adjusted_net_assets"] = {
            "scope": "Treasury external cash/vault claim/LP USDG plus external Sleeve and discovered Treasury assets less supported liabilities; all own NET/sNET/wsNET excluded, arbitrary assets/indirect custody not asserted exhaustive",
            "unit": "USDG; stock USD marks converted through pinned USDG/USD, no uiMultiplier applied",
            "value_wad": None if net_total is None else str(net_total.numerator // net_total.denominator),
            "value": None if net_total is None else amount(net_total.numerator // net_total.denominator, 18),
            "own_net_reports_mark_wad": str(own.numerator // own.denominator),
            "treasury_external_assets_wad": _raw(core_external),
            "treasury_own_net_pol_raw": _raw(self.core.get("own_net_pol_raw")),
            "liabilities_and_fees": "Accrued Morpho debt replaces stored debt, direct supply includes fee-recipient shares only when attributable. Predict active/queued/matured claims included once. Book own-NET obligations disclosed separately. Sleeve fees and supported TURBO indications included; manager fees excluded.",
            "required_missing": gaps, "external_asset_ledger": external,
            "own_net_exposure_ledger": own_ledger, "collection_complete": not gaps,
            "all_assets_exhaustive": False,
            "discovery_scope": {"morpho": self.families["credit"].get("discovery_scope"),
                                "sleeve": self.metrics["universe"].get("candidate_inventory"),
                                "treasury": self.core.get("treasury_inventory")},
            "reason": "Required economic inputs unresolved" if gaps else "Conditional known-universe net assets at pinned marks; not future product settlement"}
        core_missing = [] if core_complete else ["Core RFV reconstruction incomplete"]
        core_economic_missing = core_missing + ([] if core_external is not None else ["Treasury external-asset basis unavailable"])
        component_summary["core"] = {
            "status": "collected_known_scope" if core_complete else "partial",
            "observed": {"collection_complete": bool(core_complete), "discovery_complete": bool(core_complete),
                         "evidence": "metrics.core_rfv"},
            "valuation": {"reports_basis_complete": bool(core_complete),
                          "reports_value_wad": _value_wad(self.core.get("rfv_wad"))},
            "publisher": {
                "selection": "Pinned Treasury.rfv", "collection_complete": bool(core_complete and methodology_valid),
                "contribution_wad": _value_wad(self.core.get("rfv_wad")) if core_complete and methodology_valid else None,
                "known_selected_subtotal_wad": _value_wad(self.core.get("rfv_wad")) if methodology_valid else None,
                "required_missing": core_missing + ([] if methodology_valid else missing.get("methodology", []))},
            "historical": {"included": True, "contribution_wad": _value_wad(self.core.get("rfv_wad")),
                           "collection_complete": bool(core_complete)},
            "economic": {
                "treatment": "Alternative external basis replaces Core RFV: cash, gross vault claim and LP USDG only; own-NET POL excluded.",
                "known_rows_value_wad": _value_wad(core_external),
                "collection_complete": not core_economic_missing, "required_missing": core_economic_missing,
                "evidence": "metrics.core_rfv.external_asset_basis"},
            "missing": core_missing, "details": {"evidence": "metrics.core_rfv"}}
        metrics["component_summary"] = component_summary
        self.metrics["universe"]["known_component_collection_complete"] = all(f["collection_complete"] for f in self.families.values())
        selected_complete = complete if self.scope == "reports" else not gaps
        self.ctx.result["coverage"]["sleeve"] = {
            "collection_complete": selected_complete, "exhaustive_asset_universe": False,
            "reports_pinned_collection_complete": bool(pinned_complete),
            "reports_methodology_valid": methodology_valid,
            "current_reports_total_complete": bool(complete),
            "known_component_collection_complete": self.metrics["universe"]["known_component_collection_complete"],
            "families": {n: {"collection_complete": f["collection_complete"], "discovery_complete": f["discovery_complete"]} for n, f in self.families.items()}}
        self.ctx.result["coverage"]["collection_complete"] = selected_complete
        self.ctx.result["coverage"]["requested_scope"] = {
            "scope": self.scope, "collection_complete": selected_complete,
            "all_assets_exhaustive": False}
        if checkpoint:
            self.ctx.checkpoint()


def collect(ctx, args, core):
    c = Collector(ctx, core)
    c.scope = args.scope
    # Install null aggregate placeholders before the first optional call. A StopRun
    # preserves all earlier quantities and never advertises a partial sum as total.
    c.publish()
    try:
        c.bootstrap()
        c.wallet()
        c.credit()
        c.predict()
        book_count = c.book()
        turbo_count = c.turbo()
        c.publish()
        c.v3()
        c.v4()
        c.advance()
        c.turbo_series(turbo_count)
        c.book_markets(book_count)
        c.credit_discovery()
        c.discover_assets()
        c.publish()
        # Source availability must never erase or prevent authorized RPC evidence.
        c.check_methodology()
    finally:
        # No RPC, HTTP or checkpoint after cancellation; retain all observed rows.
        c.publish(checkpoint=False)
    ctx.checkpoint()
    return c.metrics

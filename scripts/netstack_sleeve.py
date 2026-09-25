"""Pinned RPC sleeve inventory; Reports conventions are not economic net assets."""
from fractions import Fraction

from netstack_core import ZERO, RpcError, amount, keccak256, load_json, ratio, resolve_routes
from netstack_v4 import collect as collect_v4, liquidity_amounts
from netstack_discovery import TRANSFER_WINDOW, inventory, token_candidates, inspect_tokens, discover_transfers, disposition

WAD = 10**18
Q128 = 1 << 128
MOD256 = 1 << 256
MAX_ITEMS = 128
FEED_MAX_AGE = 14400
FAMILIES = ("wallet", "credit", "v3", "turbo", "predict", "book", "v4", "treasury_extra")


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
        self.owner = core["sleeve"].lower()
        self.usdg = core["usdg"].lower()
        self.net = core["net"].lower()
        self.snet, self.wsnet = self.address("snet"), self.address("wsnet")
        self.own_tokens = {self.net, self.snet, self.wsnet}
        self.cache, self.tokens, self.feeds, self.prices = {}, {}, {}, {}
        self.net_mark, self.index, self.usdg_usd = None, None, None
        self.scope = "reports"
        self.families = {name: {"status": "not_started", "rows": [], "missing": [],
                               "supplemental_missing": [], "reports_collection_complete": False,
                               "collection_complete": False, "discovery_complete": False,
                               "reports_value_wad": None} for name in FAMILIES}
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
               "block": self.ctx.block, "included_in_reports": reports,
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
        included = [r for r in f["rows"] if r["included_in_reports"]]
        vals = [self.values.get(id(r)) for r in included]
        value = sum(vals, Fraction()) if all(v is not None for v in vals) and not f["missing"] else None
        f["reports_value_wad"] = None if value is None else str(value.numerator // value.denominator)
        self.values[family] = value
        report_discovery = f.get("reports_discovery_complete", f["discovery_complete"])
        f["reports_collection_complete"] = not f["missing"] and report_discovery and value is not None
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
        self.quantity("credit", self.usdg, claim, "Credit ERC4626 claim", extra={"contract": vault, "getter": "convertToAssets(balanceOf(sleeve))", "shares_raw": _raw(shares)})
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
        for mid in sorted(ids):
            if mid in f["markets"]:
                continue
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
            self.quantity("credit", token, position["collateral"], "Posted collateral", extra=extra)
            debt = debt_assets(position["borrowShares"], market["totalBorrowAssets"], market["totalBorrowShares"])
            debt_row = self.quantity("credit", params["loanToken"], debt, "Stored-share debt", sign=-1, extra=extra)
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
                              extra={"contract": address, "getter": "bookOf(address)", "attributable_to_sleeve": key != "feeManagerTok"})
            for key in ("putPotUsdg", "putReservedUsdg", "premiumUsdg"):
                self.quantity("turbo", self.usdg, book[key], key, extra={"contract": address, "getter": "bookOf(address)"})
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
        f["reports_scope"] = "Current 2026-09-25 publisher registry gates V4 as PLACEHOLDER; independently observed holdings are supplemental, never asserted zero."
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
                                         "provenance": p.get("read_provenance")})
        self.finish("v4", result.get("ownership_complete", False) and result.get("collection_complete", False))

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

    def publish(self):
        metrics = self.ctx.result["metrics"]
        replica_names = tuple(name for name in FAMILIES if name not in ("v4", "treasury_extra"))
        core_complete = self.core.get("core_complete", False) and self.core.get("rfv_wad") is not None
        complete = core_complete and all(self.families[name]["reports_collection_complete"] for name in replica_names)
        known_rows = [r for f in self.families.values() for r in f["rows"]]
        subtotal = sum((self.values.get(id(r)) or Fraction()) for r in known_rows if r["included_in_reports"])
        total = subtotal + self.core["rfv_wad"] if complete else None
        own = sum((self.values.get(id(r)) or Fraction()) for r in known_rows if r["own_net_exposure"] and r["included_in_reports"])
        metrics["reports_true_rfv"] = {
            "scope": "2026-09-25 published known-component formula with full V3 enumeration; not product settlement or exhaustive net assets",
            "unit": "USDG under published stock-feed USD parity convention",
            "value_wad": None if total is None else str(total.numerator // total.denominator),
            "value": None if total is None else amount(total.numerator // total.denominator, 18),
            "known_components_subtotal_wad": str(subtotal.numerator // subtotal.denominator),
            "collection_complete": complete,
            "core_complete": bool(core_complete),
            "required_missing": {n: f["missing"] or ["Included quantity/valuation or discovery not complete"] for n, f in self.families.items() if n in replica_names and not f["reports_collection_complete"]},
            "excluded_known_exposure": "V4 holdings excluded by dated publisher display gate, not a chain whitelist. LP owed/TURBO fees/direct Morpho supply supplemental.",
            "rounding": "Sum exact rational row values, floor once to 18 decimals; never sum displayed values."}
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
        for name, family in self.families.items():
            selected = []
            if not family["discovery_complete"]:
                gaps.append(name + ": scoped discovery incomplete")
            for message in family["missing"] + family["supplemental_missing"]:
                if ": unpriced or stale;" not in message:
                    gaps.append(name + ": " + message)
            for row in family["rows"]:
                additive = row["included_in_reports"] or name in ("v3", "v4", "credit", "treasury_extra")
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
        self.metrics["universe"]["known_component_collection_complete"] = all(f["collection_complete"] for f in self.families.values())
        selected_complete = complete if self.scope == "reports" else not gaps
        self.ctx.result["coverage"]["sleeve"] = {
            "collection_complete": selected_complete, "exhaustive_asset_universe": False,
            "known_component_collection_complete": self.metrics["universe"]["known_component_collection_complete"],
            "families": {n: {"collection_complete": f["collection_complete"], "discovery_complete": f["discovery_complete"]} for n, f in self.families.items()}}
        self.ctx.result["coverage"]["collection_complete"] = selected_complete
        self.ctx.result["coverage"]["requested_scope"] = {
            "scope": self.scope, "collection_complete": selected_complete,
            "all_assets_exhaustive": False}
        self.ctx.checkpoint()


def collect(ctx, args, core):
    c = Collector(ctx, core)
    c.scope = args.scope
    # Install null aggregate placeholders before the first optional call. A StopRun
    # preserves all earlier quantities and never advertises a partial sum as total.
    c.publish()
    c.bootstrap()
    c.wallet()
    c.credit()
    c.predict()
    book_count = c.book()
    turbo_count = c.turbo()
    c.publish()
    c.v3()
    c.v4()
    c.turbo_series(turbo_count)
    c.book_markets(book_count)
    c.credit_discovery()
    c.discover_assets()
    c.publish()
    return c.metrics

"""Read-only v2 holdings and conditional, exact gross-fee accounting."""

from collections import defaultdict
from datetime import datetime, timezone
from fractions import Fraction
from itertools import groupby
from math import isqrt

from netstack_core import ZERO, RpcError, amount, decode_event, load_json, ratio, resolve_routes


_FEE = Fraction(3, 1000)
_TERMINALS = {"Mint", "Burn", "Swap"}
_APPLICABILITY = "conditional_on_standard_v2_implementation_and_event_semantics"


def _position(event):
    return event["blockNumber"], event["transactionIndex"], event["logIndex"]


def _identity(event):
    return event["blockHash"], event["transactionHash"], event["logIndex"]


def _utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _range_copy(coverage, name):
    return [list(row) for row in coverage.get(name, [])]


def _missing_ranges(start, end, covered):
    if start is None:
        return [[None, end]]
    missing = []
    cursor = start
    for first, last in sorted(covered):
        if first > cursor:
            missing.append([cursor, min(first - 1, end)])
        cursor = max(cursor, last + 1)
        if cursor > end:
            break
    if cursor <= end:
        missing.append([cursor, end])
    return missing


class _Ledger:
    def __init__(self):
        self.balances = defaultdict(int)
        self.supply = 0
        self.valid = True
        self.errors = []
        self.minimum_minted = 0

    def apply(self, event, kind, minimum):
        if not self.valid:
            return
        values = event["values"]
        source, destination, value = values["from"], values["to"], values["value"]
        if kind == "ambiguous":
            self.fail(event, "Internal burn versus ordinary transfer unresolved")
            return
        if kind == "mint":
            # In v2 _mint(zero, m) increases BOTH supply and zero's balance.
            if source == destination == ZERO and self.supply == 0 and value == minimum:
                self.minimum_minted += value
            self.supply += value
            self.balances[destination] += value
        elif kind == "burn":
            self.supply -= value
            self.balances[source] -= value
        else:
            # This also preserves ordinary transfers to zero and self-transfers.
            if self.balances[source] < value:
                self.fail(event, "Transfer exceeds reconstructed sender balance")
                return
            self.balances[source] -= value
            self.balances[destination] += value
        if self.supply < 0 or self.balances[source] < 0 or self.balances[destination] < 0:
            self.fail(event, "Negative reconstructed LP balance or supply")

    def fail(self, event, reason):
        self.valid = False
        self.errors.append({"position": list(_position(event)), "reason": reason})


class _LP:
    def __init__(self, ctx, args):
        self.ctx = ctx
        self.args = args
        self.routes = resolve_routes("liquidity")
        self.interface = load_json("assets/analytics/v2-interface.json")
        self.pair_abi = self.interface["pair_abi"]
        self.factory_abi = self.interface["factory_abi"]
        self.token_abi = self.interface["token_abi"]
        self.pair = self.routes["pair"]["address"]
        self.pair_values = {}
        self.factory_values = {}
        self.token_values = {}
        self.balances = {}
        self.failed_reads = {}
        self.pair_code = None
        self.identity_valid = False
        self.snapshot_done = False
        self.creation = None
        self.discovery_start = None
        self.creation_status = "not_located"
        self.opening = None
        self.opening_header = None
        self.next_header = None
        self.duration = Fraction(str(args.since_days)) * 86400
        self.cutoff = Fraction(ctx.timestamp) - self.duration
        self.history = []
        self.history_done = False
        self.history_processed_ranges = []
        self.replay = _Ledger()
        self.semantic_errors = []
        self.candidates = {ZERO, self.pair}
        self.anchor_roles = {}
        for key, category in (("treasury", "protocol_treasury_anchor"),
                              ("sleeve", "manager_anchor"),
                              ("team_safe", "protocol_team_anchor")):
            if key in self.routes:
                address = self.routes[key]["address"]
                self.candidates.add(address)
                self.anchor_roles[address] = (key, category)
        self.burn_count = 0
        self.burn_receipts = 0
        self.ordinary_zero_count = 0
        self.issuance = defaultdict(int)
        self.period_issuance = defaultdict(int)
        self.period_issuance_count = 0
        self.unclassified_mints = 0
        self.period_done = False
        self.period_started = False
        self.period_processed_ranges = []
        self.swap_count = 0
        self.swap_inputs = [0, 0]
        self.additions = [0, 0]
        self.removals = [0, 0]
        self.mint_count = 0
        self.period_burn_count = 0
        self.sync_count = 0
        self.attribution = defaultdict(lambda: [Fraction(0), Fraction(0)])
        self.attribution_ledger = _Ledger()
        self.attribution_cursor = 0
        self.attributed_swaps = 0
        self.epoch_inputs = [0, 0]
        self.epoch_swaps = 0
        self.flushing_epoch = False
        self.last_swap_position = None
        self.last_history_position = None
        self.opening_supply = None
        self.opening_state = {}
        self.historical_reads_done = False
        self.phase = "snapshot"
        self.ctx.result["not_proven"].extend([
            "Deployed bytecode equivalence and token transfer behavior are not established; all standard-v2 replay and 3/1000 fee calculations are conditional.",
            "Address-held LP is not beneficial ownership. No independently attributable external owner is established by canonical role anchors, an EOA, or a contract address.",
            "Historical feeTo policy/control is not proved by endpoint reads; the current feeTo address is not retrospectively a protocol-owned category.",
            "Swap inputs can include unsynchronized donations or other nontrade balance changes; trader-paid fees and nontrade exclusions are not established.",
            "Gross fees remain mixed in reserves. Net economic fee split, collectable fees, actual net withdrawal cash, token levies, deposited cost, PnL and APR are not established.",
            "Reserve-share spot values are denominated in USDG, not USD, executable quotes, guaranteed redemption, Treasury NAV or RFV.",
        ])
        self._publish()

    def _error(self, scope, error):
        if error.kind in ("permission", "integrity"):
            raise error
        self.ctx.result["errors"].append({"scope": scope, "error": str(error), "kind": error.kind})

    def _fetch(self, requests, destination, block=None):
        """Retain successful batch members even if one archive read fails."""
        for offset in range(0, len(requests), 20):
            part = requests[offset:offset + 20]
            try:
                values = self.ctx.calls([spec for _, spec in part], block=block)
            except RpcError as error:
                if error.kind in ("permission", "integrity"):
                    raise
                for key, spec in part:
                    try:
                        destination[key] = self.ctx.call(*spec, block=block)
                    except RpcError as error:
                        scope = str(key) + "@" + str(self.ctx.block if block is None else block)
                        self.failed_reads[scope] = str(error)
                        self._error(scope, error)
                    self._publish()
                    self.ctx.checkpoint()
            else:
                destination.update((key, value) for (key, _), value in zip(part, values))
                self._publish()
                self.ctx.checkpoint()

    def _snapshot(self):
        self.pair_code = self.ctx.code(self.pair)
        if self.pair_code in ("0x", "0x0", ""):
            raise RpcError("Canonical pair has no code at pinned block")
        names = ("factory", "token0", "token1", "getReserves", "totalSupply", "decimals",
                 "MINIMUM_LIQUIDITY", "kLast")
        self._fetch([(name, (self.pair, self.pair_abi, name, ())) for name in names], self.pair_values)
        tokens = [self.pair_values.get("token0"), self.pair_values.get("token1")]
        expected = {self.routes["net"]["address"], self.routes["usdg"]["address"]}
        if None in tokens or set(tokens) != expected:
            raise RpcError("Pair token ordering/identity is unavailable or differs from canonical NET/USDG")
        factory = self.pair_values.get("factory")
        if factory is None or factory == ZERO:
            raise RpcError("Pair factory is unavailable or zero")
        self._fetch([
            ("getPair", (factory, self.factory_abi, "getPair", tuple(tokens))),
            ("feeTo", (factory, self.factory_abi, "feeTo", ())),
        ], self.factory_values)
        if self.factory_values.get("getPair") != self.pair:
            raise RpcError("Factory getPair does not confirm canonical pair identity")
        self.identity_valid = True
        fee_to = self.factory_values.get("feeTo")
        if fee_to is not None:
            self.candidates.add(fee_to)
        self._fetch([
            ((index, name), (token, self.token_abi, name, arguments))
            for index, token in enumerate(tokens)
            for name, arguments in (("decimals", ()), ("balanceOf", (self.pair,)))
        ], self.token_values)
        self._fetch_balances(sorted(self.candidates))
        self.snapshot_done = True
        self._publish()
        self.ctx.checkpoint()

    def _fetch_balances(self, addresses):
        self._fetch([(address, (self.pair, self.pair_abi, "balanceOf", (address,)))
                     for address in addresses if address not in self.balances], self.balances)

    def _boundary(self):
        self.phase = "time_boundary"
        self.opening = self.ctx.find_block(self.cutoff.numerator // self.cutoff.denominator)
        self.opening_header = self.ctx.header(self.opening)
        if self.opening < self.ctx.block:
            self.next_header = self.ctx.header(self.opening + 1)
        if self.opening_header["timestamp"] > self.cutoff:
            raise RpcError("Requested interval precedes available genesis timestamp")
        if self.next_header and self.next_header["timestamp"] <= self.cutoff:
            raise RpcError("Opening block is not the last block at or before requested cutoff")
        self._publish()
        self.ctx.checkpoint()

    def _operation_classes(self, events):
        """Unique ordered burn candidates, never a blanket to-zero rule."""
        classes = {}
        issuance = {}
        ambiguous = []
        segment = []
        for event in events:
            if event["event"] == "Transfer":
                values = event["values"]
                classes[_identity(event)] = "mint" if values["from"] == ZERO and values["value"] > 0 else "transfer"
                if classes[_identity(event)] == "mint":
                    issuance[_identity(event)] = "unclassified"
                segment.append(event)
            elif event["event"] in _TERMINALS:
                mints = [row for row in segment if classes[_identity(row)] == "mint"]
                if event["event"] == "Mint" and mints:
                    issuance[_identity(mints[-1])] = "provider"
                    protocol = [row for row in mints[:-1] if row["values"]["to"] != ZERO]
                    if len(protocol) == 1:
                        issuance[_identity(protocol[0])] = "protocol"
                elif event["event"] == "Burn":
                    candidates = [row for row in segment
                                  if row["values"]["from"] == self.pair
                                  and row["values"]["to"] == ZERO
                                  and row["values"]["value"] > 0]
                    if len(candidates) == 1:
                        classes[_identity(candidates[0])] = "burn"
                    else:
                        ambiguous.append((event, candidates))
                    if len(mints) == 1 and mints[0]["values"]["to"] != ZERO:
                        issuance[_identity(mints[0])] = "protocol"
                segment = []
        return classes, issuance, ambiguous

    def _classify_transaction(self, events):
        classes, issuance, ambiguous = self._operation_classes(events)
        if ambiguous:
            # A receipt supplies missing Swap boundaries and all operation ordering;
            # one receipt per transaction, cached by Context. Still-ambiguous transfers
            # are deliberately NOT guessed from amount or proximity alone.
            try:
                receipt = self.ctx.receipt(events[0]["transactionHash"])
                self.burn_receipts += 1
                complete = []
                for raw in receipt["logs"]:
                    if raw["address"].lower() == self.pair:
                        event = decode_event(raw, self.pair_abi)
                        if event is not None:
                            complete.append(event)
                complete.sort(key=_position)
                by_id = {_identity(event): event for event in complete}
                if any(by_id.get(_identity(event)) != event for event in events):
                    raise RpcError("Burn receipt does not reproduce the scanned pair events")
                classes, issuance, ambiguous = self._operation_classes(complete)
            except RpcError as error:
                self._error("burn_context", error)
            for burn, candidates in ambiguous:
                self.semantic_errors.append({
                    "transaction_hash": burn["transactionHash"],
                    "position": list(_position(burn)),
                    "reason": "No unique pair-internal burn transfer in ordered operation context",
                    "candidate_count": len(candidates),
                })
                for candidate in candidates:
                    classes[_identity(candidate)] = "ambiguous"
        return classes, issuance

    def _lifetime(self):
        self.phase = "holder_discovery"
        try:
            self.creation = self.ctx.creation_block(self.pair, self.routes["pair"])
            self.discovery_start = self.creation
            self.creation_status = "located"
        except RpcError as error:
            # Pruned historical code does not prevent a complete filtered log
            # search from genesis. Zero here is a scan start, NOT a deployment.
            self.discovery_start = 0
            self.creation_status = "unavailable_scanning_from_genesis"
            self.ctx.result["not_proven"].append("Pair creation boundary unavailable; full discovery starts at block 0: " + str(error))
        self._publish()
        try:
            pages = self.ctx.logs("holder_transfers", self.pair, self.pair_abi,
                                  ["Transfer", "Mint", "Burn"], self.discovery_start,
                                  self.ctx.block, chunk=1000000)
            for page in pages:
                for _, grouped in groupby(page, key=lambda event: (event["blockHash"], event["transactionHash"])):
                    events = list(grouped)
                    classes, issuance = self._classify_transaction(events)
                    for event in events:
                        if event["event"] != "Transfer":
                            continue
                        values = event["values"]
                        kind = classes[_identity(event)]
                        source, destination = values["from"], values["to"]
                        self.candidates.update((source, destination))
                        self.history.append((event, kind))
                        initial_lock = (kind == "mint" and source == destination == ZERO
                                        and self.replay.supply == 0
                                        and values["value"] == self.pair_values.get("MINIMUM_LIQUIDITY"))
                        self.replay.apply(event, kind, self.pair_values.get("MINIMUM_LIQUIDITY"))
                        self.last_history_position = list(_position(event))
                        if kind == "burn":
                            self.burn_count += 1
                        elif kind == "transfer" and destination == ZERO and source != ZERO:
                            self.ordinary_zero_count += 1
                        if kind == "mint":
                            mint_kind = issuance.get(_identity(event), "unclassified")
                            if mint_kind == "protocol":
                                self.issuance[destination] += values["value"]
                                if event["blockNumber"] > self.opening:
                                    self.period_issuance[destination] += values["value"]
                                    self.period_issuance_count += 1
                            elif mint_kind == "unclassified" and not initial_lock:
                                self.unclassified_mints += 1
                self.history_processed_ranges = _range_copy(self.ctx.result["coverage"]["holder_transfers"], "covered_ranges")
                self._publish()
                self.ctx.checkpoint()
            self.history_done = self.ctx.result["coverage"]["holder_transfers"]["event_coverage_complete"]
        except RpcError as error:
            self._error("holder_transfers", error)
        self.phase = "holder_getter_reconciliation"
        self._fetch_balances(sorted(self.candidates))
        self._publish()
        self.ctx.checkpoint()

    def _ownership_frontier(self):
        """Last block with a contiguous processed creation-to-block ledger."""
        if self.discovery_start is None:
            return -1
        end = self.discovery_start - 1
        for first, last in sorted(self.history_processed_ranges):
            if first > end + 1:
                break
            end = max(end, last)
        return end

    def _flush_epoch(self):
        if not self.epoch_swaps or self.flushing_epoch:
            return
        # A signal can interrupt arithmetic. Never reapply a partially committed
        # epoch from run()'s final checkpoint.
        self.flushing_epoch = True
        ledger = self.attribution_ledger
        if ledger.valid and ledger.supply > 0:
            bases = [Fraction(value * 3, 1000 * ledger.supply) for value in self.epoch_inputs]
            updated = dict(self.attribution)
            for address, balance in ledger.balances.items():
                if balance:
                    totals = self.attribution.get(address, (Fraction(0), Fraction(0)))
                    updated[address] = [totals[0] + bases[0] * balance, totals[1] + bases[1] * balance]
            self.attribution = updated
            self.attributed_swaps += self.epoch_swaps
        self.epoch_inputs = [0, 0]
        self.epoch_swaps = 0
        self.flushing_epoch = False

    def _advance_ownership(self, position):
        while self.attribution_cursor < len(self.history):
            event, kind = self.history[self.attribution_cursor]
            if _position(event) >= position:
                break
            self._flush_epoch()
            self.attribution_ledger.apply(event, kind, self.pair_values.get("MINIMUM_LIQUIDITY"))
            self.attribution_cursor += 1

    def _period(self):
        self.phase = "period_fees_and_flows"
        self._advance_ownership((self.opening + 1, -1, -1))
        if self.attribution_ledger.valid and self._ownership_frontier() >= self.opening:
            self.opening_supply = self.attribution_ledger.supply
        start = max(self.opening + 1, self.discovery_start)
        self.period_started = True
        try:
            for page in self.ctx.logs("period_events", self.pair, self.pair_abi,
                                      ["Swap", "Mint", "Burn", "Sync"], start,
                                      self.ctx.block, chunk=1000000):
                for event in page:
                    values = event["values"]
                    name = event["event"]
                    if name == "Swap":
                        self._advance_ownership(_position(event))
                        inputs = [values["amount0In"], values["amount1In"]]
                        self.swap_count += 1
                        self.swap_inputs[0] += inputs[0]
                        self.swap_inputs[1] += inputs[1]
                        self.last_swap_position = list(_position(event))
                        if (event["blockNumber"] <= self._ownership_frontier()
                                and self.attribution_ledger.valid
                                and self.attribution_ledger.supply > 0
                                and not self.semantic_errors):
                            self.epoch_inputs[0] += inputs[0]
                            self.epoch_inputs[1] += inputs[1]
                            self.epoch_swaps += 1
                    elif name == "Mint":
                        self.mint_count += 1
                        self.additions[0] += values["amount0"]
                        self.additions[1] += values["amount1"]
                    elif name == "Burn":
                        self.period_burn_count += 1
                        self.removals[0] += values["amount0"]
                        self.removals[1] += values["amount1"]
                    elif name == "Sync":
                        self.sync_count += 1
                self._flush_epoch()
                self.period_processed_ranges = _range_copy(self.ctx.result["coverage"]["period_events"], "covered_ranges")
                self._publish()
                self.ctx.checkpoint()
            self.period_done = self.ctx.result["coverage"]["period_events"]["event_coverage_complete"]
        except RpcError as error:
            self._error("period_events", error)
        finally:
            self._flush_epoch()
        self._publish()
        self.ctx.checkpoint()

    def _historical_state(self):
        # Optional archive cross-checks come AFTER fee evidence. Unavailable state
        # must neither erase log-based results nor refresh selected reads at latest.
        self.phase = "opening_archive_cross_checks"
        if self.creation is not None and self.opening < self.creation:
            self.opening_state["status"] = "pair_not_yet_deployed"
            self.historical_reads_done = True
            return
        factory = self.pair_values["factory"]
        self._fetch([
            ("totalSupply", (self.pair, self.pair_abi, "totalSupply", ())),
            ("getReserves", (self.pair, self.pair_abi, "getReserves", ())),
            ("kLast", (self.pair, self.pair_abi, "kLast", ())),
            ("feeTo", (factory, self.factory_abi, "feeTo", ())),
        ], self.opening_state, block=self.opening)
        self.historical_reads_done = True
        header = self.ctx.header(self.opening, fresh=True)
        if header["hash"] != self.opening_header["hash"]:
            self.ctx.result["coverage"]["opening_block_recheck"] = {"status": "hash_mismatch", "complete": False}
            raise RpcError("Opening block hash changed during collection")
        self.ctx.result["coverage"]["opening_block_recheck"] = {"status": "matched", "complete": True}

    def _role(self, address):
        if address == ZERO:
            return "locked_or_unspendable", "zero_address"
        if address in self.anchor_roles:
            key, role = self.anchor_roles[address]
            return role, key
        if address == self.pair:
            return "custody_or_transit", "pair"
        if address == self.factory_values.get("feeTo"):
            return "current_protocol_fee_recipient_control_unresolved", "feeTo_at_B"
        return "unknown_beneficial_owner", None

    def _token_rows(self, values, fractions=False):
        rows = []
        for index, value in enumerate(values):
            token = self.pair_values.get("token" + str(index))
            decimals = self.token_values.get((index, "decimals"))
            symbol = next((key.upper() for key in ("net", "usdg")
                           if self.routes[key]["address"] == token), None)
            row = {"address": token, "asset": symbol, "decimals": decimals}
            row["raw_fraction" if fractions else "raw"] = ratio(Fraction(value)) if fractions else str(value)
            if decimals is not None:
                row["units_fraction"] = ratio(Fraction(value, 10 ** decimals))
            rows.append(row)
        return rows

    def _pending_protocol(self):
        supply = self.pair_values.get("totalSupply")
        reserves = self.pair_values.get("getReserves")
        k_last = self.pair_values.get("kLast")
        fee_to = self.factory_values.get("feeTo")
        if supply is None or reserves is None or k_last is None or fee_to is None:
            return None
        root = isqrt(reserves["reserve0"] * reserves["reserve1"])
        root_last = isqrt(k_last)
        if fee_to == ZERO or not k_last or root <= root_last:
            return 0
        return supply * (root - root_last) // (5 * root + root_last)

    def _reconciliation(self):
        supply = self.pair_values.get("totalSupply")
        observed = sum(self.balances.values())
        remaining = sorted(self.candidates.difference(self.balances))
        mismatches = [{"address": address, "replayed_raw": str(self.replay.balances.get(address, 0)),
                       "getter_raw": str(balance)}
                      for address, balance in sorted(self.balances.items())
                      if self.history_done and self.replay.balances.get(address, 0) != balance]
        valid = self.replay.valid and not self.semantic_errors
        complete = (self.history_done and valid and not remaining and not mismatches
                    and supply is not None and self.replay.supply == supply == observed
                    and sum(self.replay.balances.values()) == supply)
        return {
            "complete": complete, "applicability": _APPLICABILITY,
            "getter_supply_raw": None if supply is None else str(supply),
            "observed_balance_sum_raw": str(observed),
            "unassigned_supply_raw": None if supply is None else str(supply - observed),
            "replayed_supply_raw": str(self.replay.supply),
            "replayed_balance_sum_raw": str(sum(self.replay.balances.values())),
            "all_candidate_getters_observed": not remaining,
            "missing_balance_addresses": remaining,
            "replay_balance_mismatches": mismatches,
            "replay_valid": valid,
            "replay_errors": self.replay.errors + self.semantic_errors,
            "positive_balance_coverage": ("exhaustive_conditional_on_standard_accounting"
                                          if supply is not None and supply == observed
                                          else "observed_set_only"),
        }

    def _holdings(self, reconciliation):
        supply = self.pair_values.get("totalSupply")
        reserves = self.pair_values.get("getReserves")
        lp_decimals = self.pair_values.get("decimals")
        pending = self._pending_protocol()
        rows = []
        categories = defaultdict(int)
        unresolved = 0
        for address, balance in sorted(self.balances.items()):
            category, role_key = self._role(address)
            categories[category] += balance
            if category in ("unknown_beneficial_owner", "custody_or_transit", "current_protocol_fee_recipient_control_unresolved"):
                unresolved += balance
            row = {"address": address, "category_at_B": category, "role_key": role_key,
                   "balance_raw": str(balance), "role_scope": "direct_address_not_beneficiary"}
            if role_key in self.routes:
                row["role_evidence"] = self.routes[role_key].get("provenance", [])
            if lp_decimals is not None:
                row["lp_units"] = amount(balance, lp_decimals)
            if supply is not None and supply > 0:
                row["share"] = ratio(Fraction(balance, supply))
                if pending is not None:
                    row["existing_receipt_share_after_conditional_pending_protocol_mint"] = ratio(Fraction(balance, supply + pending))
                    new_balance = balance + pending if address == self.factory_values.get("feeTo") else balance
                    row["address_share_after_conditional_pending_protocol_mint"] = ratio(Fraction(new_balance, supply + pending))
                if reserves is not None:
                    claims = [Fraction(balance * reserves["reserve" + str(index)], supply) for index in range(2)]
                    row["reserve_claims"] = self._token_rows(claims, True)
                    usd_index = next((index for index in range(2) if self.pair_values.get("token" + str(index)) == self.routes["usdg"]["address"]), None)
                    if (usd_index is not None and self.token_values.get((usd_index, "decimals")) is not None
                            and reserves["reserve0"] > 0 and reserves["reserve1"] > 0):
                        row["spot_reserve_share_value_USDG"] = ratio(2 * claims[usd_index] / 10 ** self.token_values[(usd_index, "decimals")])
            rows.append(row)
        residual = None if supply is None else supply - sum(self.balances.values())
        upper = None if residual is None or residual < 0 else unresolved + residual
        return {
            "status": "reconciled" if reconciliation["complete"] else "observed_set",
            "applicability": _APPLICABILITY, "as_of_block": self.ctx.block, "holders": rows,
            "category_balances_raw": {key: str(value) for key, value in sorted(categories.items())},
            "independently_external_holdings": {
                "status": "not_established", "established_lower_bound_raw": "0",
                "conditional_upper_bound_raw": None if upper is None else str(upper),
                "assumption": "All unknown/custody/feeTo-control-unresolved holdings and unassigned supply could be external; documented Treasury/Manager/team anchors and zero are excluded, without custody look-through.",
                "no_external_evidence_does_not_prove_absence": True,
            },
        }

    def _publish(self):
        result = self.ctx.result
        metrics, coverage = result["metrics"], result["coverage"]
        supply = self.pair_values.get("totalSupply")
        reserves = self.pair_values.get("getReserves")
        snapshot = {
            "status": "collected" if self.snapshot_done else "partial",
            "pair": self.pair, "factory": self.pair_values.get("factory"),
            "identity_verified": self.identity_valid, "code_present_at_B": self.pair_code not in (None, "0x", "0x0", ""),
            "total_supply_raw": None if supply is None else str(supply),
            "lp_decimals": self.pair_values.get("decimals"),
            "minimum_liquidity_raw": str(self.pair_values["MINIMUM_LIQUIDITY"]) if "MINIMUM_LIQUIDITY" in self.pair_values else None,
            "feeTo_at_B": self.factory_values.get("feeTo"),
            "kLast_raw": str(self.pair_values["kLast"]) if "kLast" in self.pair_values else None,
            "tokens": [], "failed_reads": dict(self.failed_reads),
        }
        for index in range(2):
            reserve = reserves["reserve" + str(index)] if reserves is not None else None
            balance = self.token_values.get((index, "balanceOf"))
            snapshot["tokens"].append({
                "index": index, "address": self.pair_values.get("token" + str(index)),
                "decimals": self.token_values.get((index, "decimals")),
                "reserve_raw": None if reserve is None else str(reserve),
                "pair_balance_raw": None if balance is None else str(balance),
                "balance_minus_reserve_raw": None if balance is None or reserve is None else str(balance - reserve),
            })
        if reserves is not None:
            snapshot["reserve_timestamp_modulo_2_32"] = reserves["blockTimestampLast"]
            if self.identity_valid and all(self.token_values.get((index, "decimals")) is not None for index in range(2)):
                net_index = 0 if self.pair_values["token0"] == self.routes["net"]["address"] else 1
                usd_index = 1 - net_index
                net_reserve, usd_reserve = reserves["reserve" + str(net_index)], reserves["reserve" + str(usd_index)]
                if net_reserve > 0 and usd_reserve > 0:
                    snapshot["spot_USDG_per_NET"] = ratio(Fraction(usd_reserve * 10 ** self.token_values[(net_index, "decimals")], net_reserve * 10 ** self.token_values[(usd_index, "decimals")]))
        metrics["pool_snapshot"] = snapshot
        complete_snapshot = (self.identity_valid and len(self.pair_values) == 8
                             and len(self.factory_values) == 2 and len(self.token_values) == 4
                             and all(address in self.balances for address in self.anchor_roles)
                             and ZERO in self.balances and self.pair in self.balances
                             and self.factory_values.get("feeTo") in self.balances)
        coverage["lp_snapshot"] = {"complete": complete_snapshot, "block": self.ctx.block,
                                   "no_mixed_block_refresh": True}
        metrics["interval"] = {
            "requested_since_days": str(self.args.since_days),
            "requested_duration_seconds": ratio(self.duration),
            "requested_cutoff_timestamp": ratio(self.cutoff),
            "end_block": self.ctx.block, "end_timestamp": self.ctx.timestamp, "end_utc": _utc(self.ctx.timestamp),
            "opening_block_exclusive": self.opening, "opening_header": self.opening_header,
            "next_block_header": self.next_header, "creation_block": self.creation,
            "creation_status": self.creation_status, "discovery_start_block": self.discovery_start,
            "event_time_predicate": "requested_cutoff < block_timestamp <= pinned_B_timestamp",
            "opening_boundary_offset_seconds": (ratio(self.cutoff - self.opening_header["timestamp"])
                                                if self.opening_header is not None else None),
            "shortened_interval": False,
        }
        reconciliation = self._reconciliation()
        metrics["holdings_reconciliation"] = reconciliation
        metrics["holdings"] = self._holdings(reconciliation)
        coverage["current_holdings"] = {
            "complete": reconciliation["complete"],
            "positive_balance_coverage": reconciliation["positive_balance_coverage"],
            "beneficial_ownership_complete": False,
        }
        history_cov = coverage.get("holder_transfers", {
            "missing_ranges": [[self.discovery_start, self.ctx.block]],
        })
        ownership_missing = _missing_ranges(self.discovery_start, self.ctx.block, self.history_processed_ranges)
        coverage["holder_replay"] = {
            "complete": reconciliation["complete"], "applicability": _APPLICABILITY,
            "requested_scope": "all LP Transfer/Mint/Burn events from deployment (or genesis fallback) through B",
            "requested_range": [self.discovery_start, self.ctx.block],
            "processed_ranges": self.history_processed_ranges,
            "missing_event_ranges": ownership_missing,
            "retrieval_missing_ranges": _range_copy(history_cov, "missing_ranges"),
            "transfer_count": len(self.history), "verified_internal_burn_count": self.burn_count,
            "burn_receipts_fetched": self.burn_receipts,
            "ordinary_nonmint_transfers_to_zero_count": self.ordinary_zero_count,
            "initial_minimum_mint_raw": str(self.replay.minimum_minted),
            "last_processed_transfer_position": self.last_history_position,
            "contiguous_ownership_through_block": self._ownership_frontier(),
            "missing_balance_addresses": reconciliation["missing_balance_addresses"],
        }
        period_cov = coverage.get("period_events", {
            "missing_ranges": [[None if self.opening is None else self.opening + 1, self.ctx.block]],
        })
        activity_start = None if self.opening is None else max(self.opening + 1, self.discovery_start or 0)
        activity_missing = _missing_ranges(activity_start, self.ctx.block, self.period_processed_ranges)
        opening_consistent = coverage.get("opening_block_recheck", {}).get("status") != "hash_mismatch"
        gross = [Fraction(value) * _FEE for value in self.swap_inputs]
        metrics["pool_fees"] = {
            "status": ("conditional_complete" if self.period_done else
                       "partial_observed_basis" if self.period_started else "not_started"),
            "applicability": _APPLICABILITY,
            "formula": "Swap.amount_iIn * 3 / 1000 (both input fields, without per-swap rounding)",
            "swap_count": self.swap_count, "swap_inputs": self._token_rows(self.swap_inputs),
            "gross_assessed_fees": self._token_rows(gross, True),
            "trader_paid_fee_status": "not_established_nontrade_input_changes_unreconciled",
            "nontrade_input_adjustment": None, "net_economic_fee_split": None,
        }
        coverage["pool_fees"] = {
            "complete": self.period_done, "processed_ranges": self.period_processed_ranges,
            "requested_range": [None if self.opening is None else self.opening + 1, self.ctx.block],
            "missing_ranges": activity_missing,
            "retrieval_missing_ranges": _range_copy(period_cov, "missing_ranges"),
            "opening_block_not_disproven": opening_consistent,
            "last_processed_swap_position": self.last_swap_position,
            "depends_on_holder_coverage": False,
        }
        totals = [sum((values[index] for values in self.attribution.values()), Fraction(0)) for index in range(2)]
        attribution_complete = (self.period_done and reconciliation["complete"]
                                and not self.flushing_epoch and opening_consistent
                                and self.attributed_swaps == self.swap_count and totals == gross)
        if "totalSupply" in self.opening_state and self.opening_supply != self.opening_state["totalSupply"]:
            attribution_complete = False
        attributed = []
        for address in sorted(set(self.attribution).union(self.anchor_roles).union(self.balances).union({ZERO, self.pair})):
            values = self.attribution.get(address, [Fraction(0), Fraction(0)])
            role, _ = self._role(address)
            attributed.append({"address": address, "current_address_category_at_B_only": role,
                               "historical_control_or_beneficiary": "not_established",
                               "gross_fees": self._token_rows(values, True)})
        metrics["address_gross_fee_attribution"] = {
            "status": "conditional_complete" if attribution_complete else "partial_or_unreconciled",
            "applicability": _APPLICABILITY,
            "scope": "historical_direct_address_held_pro_rata_gross_basis_not_net_income",
            "observation_boundary": "immediately_before_each_Swap_event_after_callback_transfers",
            "method": "exact Fraction allocation per unchanged ownership/supply epoch; not closing share",
            "opening_replayed_supply_raw": None if self.opening_supply is None else str(self.opening_supply),
            "attributed_swap_count": self.attributed_swaps, "rows": attributed,
            "attributed_total": self._token_rows(totals, True),
            "unallocated_observed_gross_basis": self._token_rows([gross[i] - totals[i] for i in range(2)], True),
            "sums_to_observed_pool_basis": totals == gross,
            "independently_external_gross_fee_attribution": {
                "status": "not_established", "established_lower_bound": self._token_rows([0, 0], True),
                "conditional_upper_bound_on_observed_swaps_only": self._token_rows(gross, True),
                "scope": "Nonnegative external group allocation cannot exceed observed gross basis; not a full-period bound if events are missing, and not a PnL/cash bound.",
            },
        }
        coverage["address_gross_fee_attribution"] = {
            "complete": attribution_complete, "beneficial_or_external_attribution_complete": False,
            "ownership_missing_ranges": ownership_missing,
            "swaps_missing_ranges": activity_missing,
            "holder_reconciliation_complete": reconciliation["complete"],
            "ambiguous_burns": self.semantic_errors,
        }
        metrics["liquidity_flows"] = {
            "status": ("pool_event_totals_complete" if self.period_done else
                       "partial_pool_event_totals" if self.period_started else "not_started"),
            "mint_count": self.mint_count, "burn_count": self.period_burn_count, "sync_count": self.sync_count,
            "gross_additions": self._token_rows(self.additions),
            "gross_removals": self._token_rows(self.removals),
            "net_additions": self._token_rows([self.additions[i] - self.removals[i] for i in range(2)]),
            "scope": "Pool-side Mint/Burn event quantities, including protocol-origin and mixed-origin burns; not independently external principal or net recipient cash.",
            "independently_external_flows": None,
            "underlying_transfer_and_levy_reconciliation": "not_collected_in_holdings_and_fees_scope",
        }
        coverage["liquidity_flows"] = {"pool_event_totals_complete": self.period_done,
                                       "external_principal_or_cash_complete": False,
                                       "processed_ranges": self.period_processed_ranges,
                                       "missing_ranges": activity_missing}
        pending = self._pending_protocol()
        metrics["protocol_fees"] = {
            "applicability": _APPLICABILITY, "feeTo_at_B": self.factory_values.get("feeTo"),
            "opening_archive_state": {
                key: ({name: str(value) if name.startswith("reserve") else value
                       for name, value in item.items()} if key == "getReserves"
                      else str(item) if key in ("totalSupply", "kLast") else item)
                for key, item in self.opening_state.items()
            },
            "opening_supply_matches_replay": (self.opening_state["totalSupply"] == self.opening_supply
                                              if "totalSupply" in self.opening_state else None),
            "historical_feeTo_policy": "not_established_even_if_endpoints_equal",
            "lifetime_operation_classified_protocol_LP_by_recipient_raw": {key: str(value) for key, value in sorted(self.issuance.items())},
            "period_operation_classified_protocol_LP_by_recipient_raw": {key: str(value) for key, value in sorted(self.period_issuance.items())},
            "period_protocol_mint_count": self.period_issuance_count,
            "unclassified_mint_count": self.unclassified_mints,
            "pending_protocol_LP_raw": None if pending is None else str(pending),
            "pending_formula": "floor(S*(floor_sqrt(R0*R1)-floor_sqrt(kLast))/(5*floor_sqrt(R0*R1)+floor_sqrt(kLast))) if feeTo!=zero, kLast!=0 and root growth positive; otherwise zero",
            "pending_assumptions": "Observed B fee setting and stored reserves unchanged; standard integer arithmetic; not a promised later mint or net-exit quote.",
            "classification_scope": "Operation-confirmed LP issuance identifies receipt recipients, not historical beneficiary control or realized protocol cash. Existing/mixed receipts at current feeTo are not retrospectively protocol-owned.",
        }
        coverage["protocol_mints"] = {"complete": self.history_done and self.replay.valid and not self.semantic_errors and not self.unclassified_mints,
                                      "historical_fee_policy_complete": False}
        coverage["opening_archive_state"] = {"collection_finished": self.historical_reads_done,
                                             "all_requested_reads_available": all(key in self.opening_state for key in ("totalSupply", "getReserves", "kLast", "feeTo"))}
        coverage["collection_complete"] = (self.phase == "finished" and complete_snapshot
                                            and reconciliation["complete"] and self.period_done
                                            and not self.ctx.result["errors"])
        result["collection_phase"] = self.phase

    def run(self):
        try:
            self._snapshot()
            self._boundary()
            self._lifetime()
            self._period()
            self._historical_state()
            self.phase = "finished"
        finally:
            self._flush_epoch()
            self._publish()
            self.ctx.checkpoint()


def run(ctx, args):
    """Collect one pinned snapshot, complete discovery and the requested fee window."""
    _LP(ctx, args).run()

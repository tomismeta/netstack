# NetLong futures contracts and shared collateral oracle

Observation date: **2026-10-10 UTC**. This is descriptive research, not a transaction recipe, security audit or authorization to interact. Full function inputs/outputs, selectors, event topics, errors and per-function permissions/economic analysis are in the linked JSON catalogs.

## Evidence boundary

The complete publisher [terminal entry](https://trading.netnet.capital/assets/index-BViJKZuW.js) was statically parsed, never executed: 1,162,426 bytes; SHA256 `b62b66a56fbaa9d7b387761108e99e72633369c14f3a8ad6fda8444ba9be70bc`. Its resolved literals supply 99 entries for stream desks, 90 for NET, 88 for the vault and 12 for the shared oracle. These are **complete publisher literals, not complete deployed ABIs**. Shared error/event unions include entries not necessarily reachable on every desk. Publisher `HUMAN-VERIFIED` is an assertion, not this review's verification result. Demo/mock accounts and calculations are not evidence of live state.

All seven current `perpV1*` contracts returned creation and deployed bytecode through explorer v2. None returned Solidity source or an ABI. Material dispatcher, permission, immutable-binding, arithmetic and settlement paths were reviewed, with source gaps retained per function. Explorer bytecode is not an independent block-pinned `eth_getCode` observation. Solidity metadata points to IPFS; single desk and oracle metadata retrievals returned HTTP429, without retry or alternative gateway. The entry has no source-map link or public repository link; a bounded public-repository search found no relevant implementation source. Full source review of these seven contracts is therefore **unavailable**, not completed by substituting ABI labels.

The separately bound [Chainlink VerifierProxy](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xcE73c8ad08CBDEaCa6078BF0627C8fe0a9a536E7) does provide source and ABI. All available files, including inherited ownership and imported interfaces, were read. Its explorer explicitly reports `is_verified=true`, `is_partially_verified=true`, `is_fully_verified=false`; no independent compiler rebuild was performed. The tape verifier has bytecode only.

A single fresh read-only `eth_chainId` POST to the canonical public RPC returned **HTTP403, `error code: 1010`**. No denied RPC was retried or rerouted. No live permission, balance, position, OI or financial reconciliation is claimed, and none is packaged as state. Browser product availability is not RPC proof.

## Current and historical bindings

| Publisher role | Address | Catalog |
|---|---|---|
| Futures vault | `0x50dC51CE9e633bed99D1D826fa0E2CaAc3183bF6` | [vault](../assets/contracts/netlong-futures-vault.json) |
| BTC stream desk | `0xcA728E8ee6c8D59C1a3aBDF1DeA43f2f4a63C575` | [BTC](../assets/contracts/netlong-futures-btc.json) |
| ETH stream desk | `0x8784014A4CaFEC70Bbc2aE678c59BBe64dbE7858` | [ETH](../assets/contracts/netlong-futures-eth.json) |
| SOL stream desk | `0x87b14A8e5304e35B0CbDDaBA3454587B85Ff2470` | [SOL](../assets/contracts/netlong-futures-sol.json) |
| NET pool-mark desk | `0x77D247Ec5E2094E8226BCC1A5b8bfB8A903Bb00f` | [NET](../assets/contracts/netlong-futures-net.json) |
| Shared margin oracle | `0x90f5B57A7236A1447Ce786B1ebE42433e55D9fD0` | [oracle](../assets/contracts/netlong-futures-oracle.json) |
| Futures fee router | `0x56a8816132579c6c080e65147682DA2d6D20efb0` | [fee router](../assets/contracts/netlong-futures-fee-router.json) |

The publisher places this futures redeployment at block **83638649 on October 8**. Its older `VITE_PERP_V1_FROM_BLOCK=83634617` UI log bound predates this redeployment and is not an exact creation proof. Creation receipts were not independently reconciled here. The superseded vault `0x62407957401Bb3C78e001aEd2A68cFDD5f1CcEf2` is separately recorded; its desk identities and historical/current liabilities must be established rather than guessed or aliased to current desks.

The [published futures documentation](https://docs.netnet.capital/futures) still describes the older tNET/SPCX/CASHCAT test program. Its fee routers and test parameters are not this current futures system. The [NET LONG prospectus](https://docs.netnet.capital/net-long) concerns real leveraged-spot margin, not synthetic futures: its 25bps fees, variable interest and five-minute liquidation rules cannot be transplanted wholesale. It independently names the **same shared oracle**. Standalone LOSE documentation remains sparse; distributor behavior requires its own contract evidence.

## Implementation identity and discovery

BTC, ETH and SOL each have 23,475 runtime bytes. Their **full runtime hashes differ**. The embedded zero-immutable creation runtime templates, including metadata, are exactly equal after masking 49 independently located 32-byte words. Every masked word is a zero `PUSH32` immediate in the creation template and has a matching constructor `MSTORE` patch offset. The 11 constructor patch groups identify halter, tape feed, tape verifier, stream feed, stream verifier, LOSE distributor, taker fee, maintenance, leverage, collateral oracle and vault. Repeated words in each group must agree; merely ignoring arbitrary differing bytes is unsafe.

Normalized stream template SHA256: `668148d67ef8bfb14fd47ecdd4c87bd9bd82cfdb761a119611e9d072500bfb1b`. This supports a common runtime family, **not source/compiler equivalence**. NET is a separate 20,666-byte implementation and is not deduplicated with the stream desks. Exact hashes, constructor patch groups and unresolved selectors are in [runtime surface](../assets/contracts/netlong-futures-runtime-surface.json).

For extensible market discovery, read bounded `vault.deskCount()` and `deskAt(i)` at one pinned block, then `desks(address)`, desk runtime and collateral/dependency bindings. Registration does not establish implementation safety or semantic compatibility. Unknown bytecode, mismatched repeated immutables, unsupported feed models or incomplete discovery must produce explicit missing coverage, not guessed arithmetic. The current publisher four-market roster is not a permanent hardcoded bound.

## Units and OI: do not substitute financial quantities

- `sizeUsdWad`, entry price, reported asset prices and funding indices use WAD scaling. Trader wsNET and LP accounting use 18-decimal raw units; NET/sNET use 9; USDG uses 6. Timestamps are seconds except signed tape observations, which the stream desk divides by 1000.
- Desk `oiLongUsdWad` and `oiShortUsdWad` are **stored remaining entry-dollar notionals**, storage slots 4 and 5. Fill adds size, close subtracts closed size. They do not change just because price changes.
- Gross stored entry OI is long plus short; signed desk entry skew is long minus short. Vault `totalAbsSkewUsdWad` is the **sum of the absolute desk skews**, not the absolute cross-market sum. `totalOiUsdWad` is gross stored entry notional across desks.
- No supplied ABI exposes aggregate base quantities or a complete trader enumeration. `nextCommitId` and `commits` cannot recover cleared historical fills on their own. Pending commits are not positions or OI.
- Marked notional requires a complete current position set and an explicitly identified mark: sum, per side, of `floor(sizeUsdWad * markPriceWad / entryPriceWad)`. This is an analytics measure, not the stored OI getter. Reject zero entry prices, missing trader discovery, incomplete event coverage and unreconciled remaining size.
- A `lastMark`-based total must be called **last-posted-mark notional**, carry observation timestamp/age/rung and not be represented as executable-current OI. NET close marks are side-specific; cached TWAP may survive a live-feed outage. Neither cached mark nor `servingRung()` alone proves a currently executable fill.

At stream runtime `0x39ec` and NET `0x29e6`, directional price PnL is remaining size times signed `(price-entry)/entry`, negated for shorts. Signed division truncates toward zero. Carry liability uses remaining size times `(sideCarry-entryCarry)/1e18`. Equity adds credited wsNET and price PnL and subtracts carry. The caller-supplied price in `equityUsdWad` and `liquidatableAt` is hypothetical, not authenticated by those views.

## Futures state transitions

### Commit, fill and owner actions

There is one position and one outstanding intent per trader per desk. An open commit requires size at least $10 WAD, positive margin, no existing position/intent, deadline at least `now+2`, and leverage within credited margin. It reserves margin and the quoted opening fee in the vault; it does not create OI. Fill rechecks requirements. Close commits are size-bounded; partial residuals below $10 are refused unless closing fully. TP/SL orders set trigger prices, not guaranteed execution prices.

Effective intent expiry is the earlier of user deadline and creation plus 30 seconds. Stream fills use observations within the delayed window, no more than 10 seconds old and within the initial three seconds of eligibility. Cancellation removes intent/index state and releases open margin; the reserved opening fee is charged where present. Do not interpret cancellation as universally fee-free or automatic: expiry itself does not submit a cancellation.

`addMargin` moves free wsNET into the position without increasing size. `removeMargin` preserves both initial credited collateral and equity requirements, disallows pending close, and updates last touch. Stream removal needs an authenticated recent post-touch report; NET also respects the under-maintenance checkpoint/live TWAP gates. Owner actions and permissionless execution are separately described for every function in each desk catalog.

### Carry, fees and cash settlement

The observed common carry path is stream `0x2231` / NET `0x230c`. It first pokes collateral oracle, then advances the carry timestamp and computes skew ratio `abs(long-short)/(long+short)` WAD. Payer-index movement is `0.001 WAD * ratio * elapsed / 28800`, with flooring at each unsigned division. The larger side pays and the opposite index receives 90% of that movement. Zero elapsed, equal sides and empty books do not move indices. This is **futures carry**, not the margin lending account's utilization-based interest.

On closing, the common cash path prorates margin on partial close, calculates price PnL and carry, applies ordinary taker fee unless the special path waives it, and asks the vault to settle. Positive USD PnL is converted using the higher wsNET payout valuation; negative PnL and fees use the lower loss valuation. Positive carry charges include a 10% protocol fee component. A cash credit to `freeOf` is not an outbound wallet transfer. Profit in excess of available equity/reserve/outflow headroom can become dated `owedOf` or ADL episode claims; returned collateral, free balances and unpaid profits are not interchangeable.

Constructor evidence establishes futures taker fee **50bps**; leverage/maintenance are BTC and ETH **10x/100bps**, SOL **5x/200bps**, NET **3x/500bps**. These are immutable deployment parameters, not a declaration that a new open is currently permitted.

### Reports, fallback exits and liquidation

Stream reports go through the immutable Chainlink verifier gateway, then desk decoding checks matching feed, positive price, validity/observation bounds and supported report formats. Report versions 3, 8 and 11 have distinct decoding branches; market-status checks are conditional on format. All decoding/security corner cases remain unresolved without desk source. Posting a report can cache an observation older than a fill permits; posting is not evidence a trade is executable.

`servingRung` selects primary when its cached age is at most 60 seconds, tape when primary is down and tape age is at most 600 seconds, otherwise stale-last. Tape exits require their own verification and timing checks; they never create new positions. Stale closes require both fresher routes unavailable and apply adverse haircut `clamp(floor(ageSeconds*25/3600),25,300)` bps to last primary price. This fallback is not symmetric market valuation.

Stream `marginCall` checks two reports under maintenance: A after last touch, B at least five and at most fifteen seconds after A, with fresh B. It fully closes and assesses 1% notional penalty; caller rebate is 10% of penalty. This is not NET's persistence mechanism.

NET uses bounded pair TWAP/spot: longs open on the higher and close on the lower; shorts the reverse. Opens refuse raw spot/TWAP divergence over 300bps. A net-short increase above long OI has a floor-relative loss cap: when mark exceeds floor, incremental net-short worst loss down to floor must fit 15% of vault capacity. This is distinct from aggregate 3x gross-OI and skew limits.

NET `recordUnder` requires live TWAP and unhealthy equity and starts `underSince`. `liquidate` requires five minutes and still-under health. `clear` removes the checkpoint on recovery or dark TWAP; while live and still under it reverts. Pending checkpoint restricts NET exit/removal paths. ADL on either family requires vault ADL mode and positive price PnL; it can close profitable traders into queued claims rather than cash.

## Vault accounting, LP liquidity and bankruptcy

The vault owns all physical wsNET while maintaining separate liabilities. `equityWs` at runtime `0x2cbb` is signed physical balance minus trader free, trader locked, clearing reserve, funded owed claims and reserved redemption cash. `unencumberedWs` is a different saturating cash measure and does not subtract the same owed bucket. Never label physical balance “LP TVL available for withdrawal.”

LP `subscribe` issues shares using current equity, flooring minted shares; existing nonzero shares with nonpositive equity cannot accept a normal subscription. `subscribedWs` is adjusted historical subscription basis, not current equity. Share price is 1 WAD at zero supply, zero with nonpositive equity, otherwise equity per share. Capacity values positive LP equity at collateral backing floor. Utilization is absolute entry-skew sum over capacity; zero capacity with nonzero skew returns a maximum-uint sentinel. The breaker has 60% trip / 70% recovery hysteresis against subscribed basis. The cached breaker flag and the computed opens gate have different purposes.

Redemption requests require at least 0.01 share WAD, no existing request, enough available shares and utilization at most 80%. Notice is 24 hours. Requests remove available owner shares but do not immediately burn total shares; maturation joins a pro-rata epoch pool. `payRedemptions` burns paid shares and reserves wsNET, constrained by remaining risk capital, ADL seniority and outflow budget; `claimRedeem` subsequently transfers already reserved cash. Maturation is not a promise of immediate full payment, and queued shares remain exposed until paid/burned.

Outflow accounting uses 600-second windows and a 20% opening-pot budget, adjusted by amounts already paid and loss cash taken during the window. Reserve funding grants no LP/trader entitlement. Donations recapitalize residual equity and can fund ADL claims. Neither is an ordinary free-margin deposit.

A registered desk can lock/unlock trader collateral, update risk and submit settlement through runtime entrypoints omitted by the frontend ABI. Caller checks use registered-desk mapping. The observed risk-update path limits per-desk and aggregate absolute skew against floor-valued capacity and gross OI to three times capacity. Registrar may append desks and seal registration; the publisher says it sealed the current registry, but fresh registrar storage was not obtained. There is no source-backed proof of a globally immutable authority surface simply because publisher ABI omits admin functions.

Profits are subject to reserve/equity funding and outflow limits. Cash-dated claims and ADL episode claims have different accumulators and liability timing. `closeAdlEpisode` requires a flat book, pays what it can, zeroes residual unpaid current episode and advances epoch: **bankruptcy closeout is not full repayment**. Existing funded entitlements remain distinguishable from written-off unfunded residue. Fee and penalty collections are capped by collateral actually available. Runtime penalty routing allocates half to reserve, a conditional caller rebate, and residual plus collected ordinary fee to fee router; no unlimited collectible debt is inferred.

## Shared margin collateral oracle

This oracle is shared by futures and leveraged-spot margin; it is not the traded BTC/ETH/SOL price oracle. Immutable bindings are PairOracle, Treasury, sNET and the resolved canonical NET/USDG pair. It reads the sNET index (raw9), Treasury floor (USD/NET WAD), pair reserves and TWAP.

`marks()` returns live positive TWAP when possible, otherwise cached TWAP with `twapLive=false`; raw spot, floor and index remain separate. `poke()` catches failed/zero TWAP and only caches a positive result, timestamped at the poke. It does not advance the PairOracle checkpoint. `lastTwapAt` is cache update time, not the underlying cumulative-price observation time; this oracle's cache read path has no independent expiry check.

`boundedMarks()` requires a nonzero live-or-cached reference and clamps spot to 97%–103% of it; zero spot uses the reference. Its `twapLive` flag still describes original availability. Let `m=min(twapRef,spotBounded)`, `M=max(...)`, `F=backing floor`, `I=sNET index`:

| Function | Runtime economic meaning |
|---|---|
| `usablePerWsWad` | Live TWAP required; `I * min(2F,max(F,0.85m)) / 1e9`, flooring in actual operation order. |
| `creditPerWsWad` | `I*m/1e9`; same dispatcher body as `lossPerWsWad`, **not** the usable-credit formula. |
| `lossPerWsWad` | Lower bounded collateral valuation used when converting trader losses/fees to wsNET. |
| `payoutPerWsWad` | `I*M/1e9`; higher valuation used to pay fewer wsNET for a given positive USD profit. |
| `floorPerWsWad` | `I*F/1e9`; does not require TWAP but still depends on working Treasury and index calls. |

Cached fallback can keep some settlement views available without making new margin credit available. Reverts, zero values, underlying overflow and exact external source behavior must not be suppressed. These are bytecode-path findings, not independently recompiled Solidity assertions.

## Futures fee router and LOSE binding

The current futures fee router is **not** the leveraged-spot USDG fee router. Its runtime has an immutable boolean **false**: active `route()` unwraps wsNET, unstakes sNET and burns the resulting NET. Its dormant true branch swaps NET to USDG for Treasury through a v2 router and checks keeper or Safe authority. Active burn branch is permissionless in the observed body. The dormant quote uses pair TWAP and raw9→raw6 conversion with 500+30+100bps deductions. The reconstructable interface is deliberately marked partial; unnamed dispatch getters remain explicit gaps.

All four desks embed current LOSE distributor `0x1DEdDa4dE44f406FD25CdD3A22ABb8e524368719`, also exposed by `loseDistributor()` absent from the publisher literal. The settlement hook bounds notification by posted margin actually lost plus liquidation penalty, not uncovered house loss; a low-level notification failure emits a missed-loss event rather than blocking the close. This does not establish token minting, a successful distribution, or the distributor's own authority/curve behavior; use the separate LOSE review.

## External verifier authority and remaining dependencies

The stream [verifier catalog](../assets/contracts/netlong-futures-stream-verifier.json) contains every explorer ABI function, with exact source locations. Source shows optional access-controller gating and fee billing, then digest-selected routing to a verifier. The proxy itself does not enforce feed ID, positive price or report freshness. Owner can replace controller/fee manager, initialize verifiers and unset digests without a timelock. An initialized verifier maps a previously unmapped new digest to itself; the supplied previous digest is event context, not a validated predecessor. Owner transfer is two-step. This is mutable dependency behavior even though the desk's proxy address is immutable.

Current `owner`, access controller, fee manager and config-specific actual verifier were not obtainable through pinned reads. Zero constructor access-controller argument is historical, not current permission proof. Current report configuration is another unresolved dependency boundary.

The [tape verifier](../assets/contracts/netlong-futures-tape-verifier.json) embeds the team Safe as manager and initially authorizes the published dialup print signer. Source is absent; selector/body analysis establishes manager-only signer updates and desk-consumed `verify(bytes)` output. Current signer membership was not read. Full signature-decoder security, mutable signer roster and exact unnamed entrypoints remain gaps. The signer is a public role, not a private-key or wallet-control assertion.

The [dependency map](../assets/contracts/netlong-futures-runtime-surface.json) preserves core token, staking/helper, pair/Treasury, fee-route, initial registrar, halter, LOSE and verifier bindings and distinguishes historical constructor facts from current storage. Existing shared records are reused rather than duplicated. No linked Solidity library address was recovered for the current seven futures runtimes; absence of source prevents claiming a complete high-level library dependency graph.

## Reading the function catalogs safely

Each function preserves exact supplied input/output widths, mutability, canonical signature, selector, public/owner/role constraints, economic purpose and unresolved source status. `runtime_dispatch.entry_pc` identifies the observed compiler dispatcher wrapper, not a full proof of the named ABI. Events preserve indexed fields and canonical topic hashes; replay requires complete bounded logs and reorg-aware block identity. Publisher error messages are separately labeled interface documentation, not treated as exhaustive revert predicates.

Unrepresented runtime selectors are listed rather than deleted, guessed from similar contracts or mistaken for absent functionality. Fee/tape reconstructed interfaces are descriptive only. Analytics must use its separate read-only allowlist; it must not execute write-capable entries, verifier billing, transactions, approvals, report posting or commit/settlement calls to obtain a quote. All current holdings, OI, claims, authority and oracle observations require fresh bounded reads with explicit missing coverage when access fails.

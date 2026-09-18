# Read-only NET/USDG v2 liquidity analytics

Use for **current LP holdings**, **period liquidity flows** and **swap-fee generation/attribution**: three different measurements. This concerns the canonical fungible v2 LP receipt, not the Sleeve's [v3 NFT fee-growth recipe](lp-fee-inspection.md) or Predict's House Vault. V2 has no per-holder `feeGrowthInside` or separate collectable-fee balance. **[Safety](safety.md) governs all retrieval.** Never call `sync`, `skim`, or simulate state-changing methods, including through `eth_call`. Dashboards are optional evidence.

## 1. Pin identities, scope and coverage

Read the `analytics.net_usdg_v2` entry in [address-index.json](../assets/address-index.json), follow its literal route file, then the selected canonical `{file,id}` records and [address conventions](../assets/address-conventions.json). Resolve the **NET/USDG canonical pair (Uniswap v2)**, original NET, USDG, Treasury and Manager Sleeve; do not substitute NET-scaled18, another pool, the LP Zap or a v3 factory. The returned pair `factory()` supplies the v2 factory to cross-check; a catalogued v3 factory does not. No contract address is duplicated here. Known Treasury/Manager addresses are classification anchors, not an exhaustive control map. Discover routers, the pair itself, custody contracts and any `feeTo` recipient separately, recording their role evidence.

- Define chain **4663**, exact question, holder versus beneficial-owner scope and interval `(A,B]`. Default to the requested seven days, locating `A` by block timestamps and reporting the actual boundary difference. If the request allows a shorter interval, label its exact duration. Otherwise an incomplete seven-day scan remains an incomplete seven-day answer: never silently substitute a shorter complete period or extrapolate it.
- Check `eth_chainId`, canonical head/time, and deployed code. Pin `B` by block number/hash/time; use that same block for **all** snapshot reads. Pin `A` for period opening state. Recheck hashes after retrieval; reject mixed-fork results. Distinguish observation time, retrieval time and stale heads.
- Follow the shared [execution limits](integrations.md#live-analytics-execution-limits) before retrieval. First preserve required pair/factory identity, token units, supply, reserves and balances at B. These can support a pool snapshot, **not complete holder discovery or third-party ownership**. Then prioritize creation-to-B LP Transfers and `(A,B]` fee evidence required by the question; do not expand a holdings/fees request into unrelated flow or cost-basis research. If an uncached value at B becomes unavailable through pruning, retain the missing value or restart the entire dependent snapshot within the original deadline; never splice latest state into the old snapshot. Logs may remain available when archive `eth_call` state does not.
- Verify current interface and implementation applicability. The [bounded read/event ABI](../assets/analytics/v2-interface.json) comes from pinned upstream v2 source; the app separately confirms a subset. Successful getters or matching event topics alone do not prove fee constants, token behavior or deployed-code equivalence. Use verified deployed source/bytecode evidence where available; otherwise label standard-v2 calculations **conditional**, not audited facts.
- Public JSON-RPC supports the basic workflow: `eth_getBlockByNumber`, `eth_getCode`, view/pure `eth_call`, `eth_getLogs`, and `eth_getTransactionReceipt`. The [official public RPC](https://docs.robinhood.com/chain/connecting/#public-endpoints), `https://rpc.mainnet.chain.robinhood.com`, is rate-limited, not a guaranteed archive/indexer.
- Stop at the first shared deadline or recipe cap: **250 RPC members including retries and 50,000 log rows total**. Record usage. Start with address/topic-filtered chunks no larger than 1,000,000 blocks; shrink rejected chunks only within shared recovery limits. `eth_getLogs` has no standard cursor: partition inclusive block ranges, or exhaust documented pagination. Adjacent ranges must have no gaps. Suspected silent truncation, capped pages or a missing single-block page prevent completeness; retain the gap if further splitting cannot finish in budget. Deduplicate by block hash/transaction hash/log index and sort by block, transaction index, log index. Exhaustion or unavailable archive state is **missing evidence**, not zero activity.

Keep a range ledger separately for creation-to-`B` LP-holder discovery and `(A,B]` activity. A complete recent activity scan does not discover every older holder. Retain request parameters, block hashes, raw outputs and receipts outside the skill; do not turn a successful example into a permanent holder list.

If history cannot finish, return the verified pool snapshot and exact covered/missing ranges promptly. A partially enumerated holder set cannot establish the complete unknown-owner remainder; pool-wide fees cannot establish holder-attributed fees without ownership/supply at each swap. Report these missing results as unavailable, preserving the requested seven-day interval. Current ownership multiplied by historical fees is not a shortcut.

## 2. Exact public interfaces

Decode strict ABI types and lengths; malformed, empty or reverting results are unavailable, not zero. Use exact integers/rationals, not floating-point JSON numbers for raw uint256 values; retain hex or decimal strings across tools that cannot preserve integers above `2^53-1`. Use the ABI asset or encode ordinary RPC calls: selector = first four bytes of Ethereum Keccak-256 of the canonical method signature, followed by 32-byte ABI argument words. `eth_call` receives `{"to":"<resolved address>","data":"<encoded read>"}` and the pinned hexadecimal block number. Never use SHA3-256 in place of Ethereum Keccak-256.

| Contract / exact read | Return / use |
|---|---|
| Pair `factory()` | `address`; resolve actual v2 factory |
| Pair `token0()`, `token1()` | Each `address`; verify exact NET/USDG identities and ordering |
| Pair `getReserves()` | `(uint112 reserve0,uint112 reserve1,uint32 blockTimestampLast)`; reserve timestamp is modulo `2^32`, not proof of current block freshness |
| Pair `totalSupply()`, `balanceOf(address)` | Each `uint256`; LP supply and direct address balance |
| Pair `decimals()` | `uint8`; receipt display scale, not either asset's scale |
| Pair `MINIMUM_LIQUIDITY()`, `kLast()` | Each `uint256`; locked initial issuance and protocol-fee accounting checkpoint |
| Factory `getPair(address,address)` | `address`; must equal the selected pair for the verified tokens |
| Factory `feeTo()` | `address`; current protocol-fee recipient/configuration only |
| Each underlying token `decimals()`, `balanceOf(address)` | `uint8`, `uint256`; query pair token balances as well as holder receipts |

All snapshot reads above use `B`. Read opening values at `A` where required; reconstruct intra-block state from ordered evidence rather than substituting end-of-block calls for transaction-time state. Do not assume NET, USDG and LP decimals are equal.

Hash the following canonical signatures for topic0. Indexed addresses occupy the listed topics, padded to 32 bytes; all remaining fields are ABI data words in declaration order. Filter **pair events by pair address**, not the token or router. Underlying tokens have their own ERC20 `Transfer` logs.

| Canonical event signature | Indexed fields / non-indexed data |
|---|---|
| `Transfer(address,address,uint256)` | topics1/2 = `from,to`; data = `value` |
| `Mint(address,uint256,uint256)` | topic1 = `sender`; data = `amount0,amount1` |
| `Burn(address,uint256,uint256,address)` | topics1/2 = `sender,to`; data = `amount0,amount1` |
| `Swap(address,uint256,uint256,uint256,uint256,address)` | topics1/2 = `sender,to`; data = `amount0In,amount1In,amount0Out,amount1Out` |
| `Sync(uint112,uint112)` | No indexed fields; data = `reserve0,reserve1` |
| Factory `PairCreated(address,address,address,uint256)` | topics1/2 = `token0,token1`; data = `pair,pairCount` |

Factory `PairCreated` or independently evidenced creation identifies the discovery start; otherwise locate the deployment boundary with code/history reads within budget. The standard factory has **no feeTo-change event**. Do not invent one or infer unchanged policy from equal endpoint reads.

## 3. Discover holders without inventing economic owners

1. Fetch **all pair LP `Transfer` logs**, with no from/to-holder filter, from creation through `B`, or use a justified complete opening holder ledger plus every subsequent transfer. Collect every distinct from/to address, including zero and the pair. Fetch `balanceOf` at `B` for these candidates and known role anchors; retain positive balances and explicit zero observations. Do not discover only Treasury's counterparties or only the last seven days.
2. Replay balances and supply using the verified implementation and complete transaction event groups. Standard first issuance calls `_mint(zero,MINIMUM_LIQUIDITY)`, emitting **`Transfer(zero,zero,m)`**: increase supply and the zero-address balance once; do not cancel it as a self-transfer. Ordinary nonzero self-transfers have no net effect. A standard ordinary LP transfer **to zero** credits zero's balance but does **not** reduce supply. Only the actual `_burn` inside a pair burn reduces supply and does not credit zero; recognize it from the verified operation/receipt, not merely `to=zero`. Separate liquidity-provider minting, locked initial issuance and protocol-fee minting.
3. Reconcile `sum(balanceOf(h,B)) = totalSupply(B)` over all distinct holders **including zero, pair, routers and custodians**. Compare replayed balances and supply with getters. The zero balance includes the initial locked minimum and any later transfers to zero; do not assume it always equals the minimum. Zero remains in the share denominator but is never a third party. Any unexplained negative balance, supply mismatch or residual prevents a complete attribution claim.
4. Classify each direct holder with dated evidence: **known protocol Treasury/control**, **known Manager/control** (separate from Core), **known custody/transit or protocol-fee recipient**, **independently attributable external**, **unknown**, and **locked/unspendable**. A router, bond escrow, pair balance or fee recipient is not automatically an outside investor. A nonzero code result identifies a contract, not its beneficiaries; an EOA label does not prove independence. Do not call `supply - Treasury` third-party LP. A holder is not necessarily the depositor: receipts can be transferred, sold, bonded into Treasury or held for someone else.
5. Look through a custodian only with a verified, same-block entitlement ledger. Report direct custody and beneficial attribution separately and never count both the custodian's receipt and its beneficiaries as extra LP supply. If control/beneficiaries are uncertain, keep that quantity unattributed.

If discovery is incomplete, report verified balances as a scoped observed set and `S - sum(observed distinct balances)` as **unassigned supply**, not a discovered holder. Reconciliation to all of `S` can support exhaustive current positive-balance coverage under verified standard accounting even when history is incomplete, but cannot establish cumulative deposits or historical ownership. For beneficial external holdings, an evidenced external subset is a lower bound; an upper bound may add all unresolved potentially external custody/supply, explicitly stating that assumption. Known non-Treasury Manager or locked balances are not added as external. No evidence of independent holders means **no externally attributed amount established**, not proof there are none.

## 4. Current reserve-share position, not deposited cost

At `B`, let `S` be raw LP supply, `L_h` raw holder LP, `R_i` stored reserves and `Q_i` underlying `balanceOf(pair)`. Require `S>0`, correct token ordering and positive reserves for ratio pricing. Report each `Q_i-R_i`: donations, unsynchronized transfers, rebases or other token behavior can make balances differ from reserves. Do not silently substitute one for the other.

```text
share_h = L_h / S
reserve_claim_i,h = L_h * R_i / S                   (exact rational raw-token units)
net_units_h  = reserve_claim_NET,h  / 10^d_NET
usdg_units_h = reserve_claim_USDG,h / 10^d_USDG
spot_USDG_per_NET = (R_USDG / 10^d_USDG) / (R_NET / 10^d_NET)
spot_value_USDG_h = usdg_units_h + net_units_h * spot_USDG_per_NET
```

This is a **spot reserve-share valuation in USDG**, not an executable sale quote, guaranteed redemption, Treasury RFV/NAV or USD principal. At that same internal spot it equals `2 * share_h * R_USDG / 10^d_USDG`; cross-check without valuing USDG twice. USD requires a separately acceptable USDG/USD observation and freshness/decimal handling from the [pricing walkthrough](addresses-and-roles.md#read-only-pricing-walkthrough); never silently assume parity.

Actual standard burn arithmetic uses token **balances**, floors each token output and first may mint protocol-fee LP, diluting existing receipts. NET's separately documented transfer levy may further reduce recipient proceeds. Present pending dilution and `Q-R` separately; do not label reserve-share amounts exact net withdrawable cash. No burn/sync/skim call is permitted to estimate them. Keep integer/rational calculations unrounded until display; a raw fractional claim is an accounting proportion, not a transferable fractional base unit.

## 5. Period net liquidity additions

Fetch complete `(A,B]` pair `Mint`, `Burn`, `Transfer` and `Sync` events and relevant transaction receipts. Group them by the actual operations, preserving multiple operations in one transaction; never join merely by matching transaction hash. In standard v2, `_mintFee` and LP transfers occur before the operation's `Sync`, then `Mint`/`Burn`; this ordering matters. `Mint.sender` is the caller (often a router), not necessarily the funder or receipt beneficiary. LP mint transfers identify receipt recipients; follow any transit transfers. `Burn.to` is the requested token recipient, not necessarily the original depositor or the party whose LP was transferred to the pair.

For each underlying token, publish these pool-side quantities independently:

```text
gross_liquidity_additions_i = sum(Mint.amount_i)
gross_liquidity_removals_i  = sum(Burn.amount_i)
net_liquidity_additions_i   = additions_i - removals_i
```

`Mint.amount_i` measures balance minus prior reserves, so it can absorb prior donations or excess transfers, not only fresh investor capital. `Burn.amount_i` is the pair's gross requested transfer, not necessarily net receipts after token levies. Reconcile underlying transfer logs and operation context; unusual tax/rebase semantics may require verified source or transaction-time traces unavailable from basic RPC. Separate unexplained/non-investor deltas instead of forcing them into deposits. Protocol-fee LP issuance is dilution, not new deposited tokens. Ordinary LP transfers between holders are not liquidity additions/removals.

Pool-side totals include **burns of LP originating from protocol-fee issuance**. Trace fee-recipient and intermediary transfers, any sale/consideration and actual token recipients before calling these external-provider withdrawals or protocol cash realization. Mixed protocol/provider LP needs a stated allocation or an unresolved split; an entire mixed-origin burn is not automatically protocol fees. Preserve it in the pool gross totals and disclose the evidenced subset separately. Same-period mint/burn round trips likewise remain in gross flows; they do not establish lasting new capital or independent providers.

An **external-provider** additions/removals subtotal requires independently supported funding/beneficiary attribution for each operation and a documented allocation when funds are mixed. Do not map all Mint senders to investors or assign Burn outflows using today's owner. If unavailable, publish complete pool-level flows plus the attributed subset and unresolved remainder. These flows are not cumulative lifetime deposits, current position value, deposited cost basis or realized PnL. Do not net different tokens by addition; any flow valuation must specify contemporaneous prices or an explicitly common mark, keeping quantities alongside values.

## 6. Swap fees, protocol dilution and historical attribution

### Gross fee basis

Verify the fee formula against deployed implementation evidence. In the pinned standard source, adjusted balances subtract `3 * amountIn` from `1000 * balance`: the nominal input fee rate is **3/1000**. The app's 0.3% description corroborates intent, not deployed equivalence. There is no standard pair `fee()` getter. With that formula applicable, for every complete `Swap` event `s` and token `i`:

```text
gross_assessed_fee_i,s = amount_iIn,s * 3 / 1000
gross_assessed_fee_i,period = sum_s(gross_assessed_fee_i,s)
```

Use actual **Swap input amounts**, not the router's requested input, token gross sent amount, output volume or dashboard volume. Input transfer taxes reduce what reaches the pair; output taxes reduce recipient cash, not the Swap input fee base. Both input fields can be nonzero (including flash repayment); account for each once. NET's token levy is a separate flow to its levy mechanism, not the LP swap fee. Do not infer current exemptions from historic UI copy.

This is an exact rational **nominal fee assessed on the observed input basis under the verified/assumed formula**, not an emitted fee transfer or a rounded fee bucket. Do not floor each swap as though the pair separately credited integer fee tokens. Trade rounding, overpayment and price movement remain separate. `amountIn` is derived from balance versus reserves and may absorb prior unsynchronized donations or rebases. Reconcile them through ordered `Sync`, liquidity events, underlying transfers and available transaction evidence before calling all of this **trader-paid** fees. A reserve increase or `sqrt(k)` increase alone is not trade-fee evidence.

### Ownership at each swap, not closing share

Start from the complete opening LP ledger and supply at `A`, then replay **all** LP events, including transfers between existing holders, provider mints/burns, minimum lock and protocol mints, in `(block,transaction,log)` order. Alternatively reverse-replay the complete interval from a reconciled closing ledger using verified operation semantics. Include disposed positions and holders absent at `B`; a closing getter cannot recover within-block ownership. Process LP transfers made during a swap callback as well. Define the observation boundary as **swap completion** (immediately before the pair's `Swap` event; the paired `Sync` precedes it).

For raw LP `L_h,s` and issued supply `S_s` at that boundary:

```text
gross_address_share_i,h = sum_s(gross_assessed_fee_i,s * L_h,s / S_s)
```

This is a clearly defined **historical address-held pro-rata gross-fee attribution**, not current uncollected fees or the economic owner's exact earnings. Category/control attribution must hold at the event time, not merely today. Include locked, custody, protocol and unknown shares: the complete per-swap allocation must sum to the gross basis. LP transfers convey an already mixed reserve claim; they do not retroactively make the recipient the earlier fee earner. Never use closing share × period/lifetime volume, average endpoint share, or v3 fee growth as a shortcut. If ownership coverage is incomplete, give only an evidenced subset or explicit conditional bounds (at most the covered pool gross basis for a nonnegative group share); do not publish an exact external attribution.

### Protocol fees are LP dilution, not a flat cash deduction

A nonzero `factory.feeTo()` is material. Standard `_mintFee` runs on each mint/burn, using the **pre-operation stored reserves**, pre-protocol-mint supply and `kLast`. If fees are on, `kLast!=0` and integer roots satisfy `r>rLast`:

```text
r = floor_sqrt(reserve0 * reserve1)
rLast = floor_sqrt(kLast)
protocol_LP_mint = floor(S * (r - rLast) / (5*r + rLast))
```

Otherwise no LP is minted by that calculation. When fees are off, a nonzero `kLast` is reset on a liquidity operation; when on, `kLast` is updated to the post-operation reserve product. Source ordering and integer floors are essential. Reconcile materialized protocol LP mints, recipients and dilution against all LP transfers, keeping them separate from investor issuance. Prior-window growth and nontrade reserve changes can contribute to a period mint; an interval's protocol LP issuance is not necessarily that interval's swap fees.

Read `feeTo` and `kLast` at relevant historical boundaries, but endpoints alone do not prove historical policy. The factory can change `feeTo` without an event, including inside a block. Exact transaction-time policy requires adequate source/state/transaction evidence; ordinary archive end-of-block calls may be insufficient. At `B`, the same formula can describe **pending dilution under the observed fee setting and unchanged reserves**, without executing a mint/burn, but is not a promise about a later exit.

Do **not** turn 0.3% into net LP income, deduct a universal 1/6 or claim exactly 0.25% for providers merely from `feeTo!=zero`. The mechanism mints rounded LP against growth and transfers claims through dilution; donations, timing, ownership changes and pending issuance matter. Report gross assessed fees, historical gross share attribution, observed protocol LP issuance and pending-dilution sensitivity as separate metrics. Only call a net external fee split exact when full implementation, ownership, protocol-state and nontrade-change evidence establishes the specified accounting definition; otherwise state **net economic fee split not established**, with conditional estimates/bounds and their assumptions. A bounds claim must name its object: `[0,gross basis]` can bound a group's gross fee allocation, not its PnL or cash withdrawals.

Fees remain mixed in reserves and are reinvested by the AMM. Withdrawals include principal and accumulated reserve changes; there is no universal fee-first/FIFO split. Report **fee generation/accrual**, **gross withdrawal accounting**, **actual token cash received**, **capital additions**, **token levy/costs**, and **investment PnL** separately. An LP can earn gross fees and still lose value. Neither current value minus deposits nor reserve growth alone establishes fee earnings.

## 7. Answer template and method sources

Lead with established versus conditional/unavailable findings. Include requested metric rows and their supporting reconciliations:

| Output | Fields |
|---|---|
| Scope/evidence | Chain, canonical/resolved pair and factory; `A/B` blocks/hashes/UTC times; requested/covered interval; retrieval time/provider; request/log/page budget used, complete/missing ranges; implementation applicability and fee-policy status |
| Current holdings | Holder, role/evidence/date, raw LP/share, raw/rational and scaled NET/USDG reserve claims, spot USDG value; section 3 categories, external bounds and unresolved beneficiaries |
| Holdings reconciliation | Supply, summed balances, unassigned residual; token order/decimals, reserves, pair balances, `Q-R` |
| Period flows, per token | Gross additions/removals, net additions; attributed external/unresolved split; receipt reconciliation and levies; pool-side amounts, not cost basis |
| Fees, per token | Swap inputs, formula/status, gross basis, historical category shares, protocol LP issuance, pending dilution/assumptions; excluded nontrade changes, ownership/policy gaps, net economic split/status |
| Valuation/limits | Denomination, same-block marks/freshness, any USDG/USD conversion; unresolved ownership, fee retention, cost, cash or PnL; relevant canonical explorer links |

Round only for display. Show the rounding residual when rounded rows differ from the rounded total; explain non-rounding token/category mismatches rather than adjusting a row. No guaranteed availability, levy exemption, APR, principal protection or spendable buyback budget follows.

Pinned accounting/interface sources (all v2-core commit `4dd59067c76dea4a0e8e4bfdda41877a6b16dedc`, upstream v1.0.1): [pair interface](https://github.com/Uniswap/v2-core/blob/4dd59067c76dea4a0e8e4bfdda41877a6b16dedc/contracts/interfaces/IUniswapV2Pair.sol), [pair implementation](https://github.com/Uniswap/v2-core/blob/4dd59067c76dea4a0e8e4bfdda41877a6b16dedc/contracts/UniswapV2Pair.sol), [LP ERC20 implementation](https://github.com/Uniswap/v2-core/blob/4dd59067c76dea4a0e8e4bfdda41877a6b16dedc/contracts/UniswapV2ERC20.sol), [factory](https://github.com/Uniswap/v2-core/blob/4dd59067c76dea4a0e8e4bfdda41877a6b16dedc/contracts/UniswapV2Factory.sol), [token interface](https://github.com/Uniswap/v2-core/blob/4dd59067c76dea4a0e8e4bfdda41877a6b16dedc/contracts/interfaces/IERC20.sol) and [integer square root](https://github.com/Uniswap/v2-core/blob/4dd59067c76dea4a0e8e4bfdda41877a6b16dedc/contracts/libraries/Math.sol). Source ID: `uniswap-v2-liquidity-accounting`. These establish the method, not deployed equivalence. The [September 18 app bundle](https://app.netnet.capital/assets/index-9OJ6-wtv.js), source ID `netnet-app-registry-20260918`, confirms its pair ABI subset and displayed 0.3% claim, not the full standard event set or protocol-fee policy. Missing history or implementation evidence narrows what can be established, never silently the user's question.

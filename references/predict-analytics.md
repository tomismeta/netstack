# Read-only Predict and House Vault analytics

Use for current series, activity since opening, and House capital/ownership/performance. **[Safety](safety.md) governs all retrieval.** No trade quotes or simulations; never call state-changing methods through `eth_call`. Dashboards are optional evidence; [product terms](products.md#netnet-predict-weekly-outcomes-and-house-vault) remain separate from measured balances.

## 1. Select identities, evidence and a bounded snapshot

Read `analytics.predict_house` in [address-index.json](../assets/address-index.json), follow its literal route file, then the selected canonical `{file,id}` records, this recipe, and the needed [Predict interface](../assets/analytics/predict-interface.json) / [House interface](../assets/analytics/house-interface.json). Do not load all contract files. The Predict asset's `abi` applies to the Desk; `token_abi` applies to USDG and discovered outcome tokens. The House asset's `abi` applies to the Vault, **not an ERC-20 share token**. Both contain only view functions and events; no executable code or transaction methods.

The interface source is the pinned official [September 18 app asset](https://app.netnet.capital/assets/index-9OJ6-wtv.js), source ID `netnet-app-registry-20260918`, SHA-256 `379faedc6c6494416fada1208e61dfd0913f2ab399f27a9ba56e5031913fca5d`. `An` / `Ot` supply Desk / House ABIs; `Re` supplies the token ABI; `HO` is the live adapter. `C_` selects `HO` for live mode and `iI` for mock mode; `J7` is the mock vault. The supplied enum decoding and account/display interpretations below come from live/shared consumers, **not mock state transitions**. Published ABI and a successful getter are interface evidence, not verified Solidity, enforced economics or a solvency audit.

- Define chain **4663**, Desk/Vault generation(s), interval `(A,B]` or **opening transaction through B inclusive**, desired series/owner scope, and native USDG versus USD valuation. USDG units are not automatically US dollars; use independently supported USDG/USD pricing for conversion, or leave amounts in USDG.
- Check `eth_chainId`, pin canonical block number/hash/timestamp `B`, and record retrieval time separately. All snapshot reads use B; history reads end at B. Use block timestamps, not the app's wall clock, to classify historical state. Recheck hashes after retrieval; reject mixed forks. Current app labels and registry metadata need their own observation dates and cannot silently be backdated to B.
- Follow the shared [execution limits](integrations.md#live-analytics-execution-limits) before retrieval. Preserve the question's required same-block state before scanning history. For market/wager questions, prioritize Desk identity, `seriesCount()`, inspected series tuples, USDG units and named counters; do not add a full House ownership/queue scan. For House questions, prioritize its wiring, share/price/queue/claim fields and relevant series state, then the ownership and cash history needed by the requested metrics; do not add unrelated wager histories. A snapshot does not establish complete event totals or beneficial ownership. If B is pruned, retain the missing value or restart all dependent reads within the original deadline; never splice newer values into old state.
- The [official public endpoint](https://docs.robinhood.com/chain/connecting/#public-endpoints) is `https://rpc.mainnet.chain.robinhood.com`; availability, log limits and archive support are not guaranteed. Missing history is not zero activity.
- Check nonempty deployed code and Desk `vault()`, `usdg()`, `sleeve()`, `treasury()`, `net()` and House `desk()`, `usdg()`, `wired()`. Match the chosen canonical identities and dynamically returned dependencies. Record `owner()`, `grader()` and `halted()` as current roles/flags, not an audit of all privileges. Code presence does not verify implementation. A mismatched generation or decode stops application of this ABI; do not silently switch addresses.
- Stop at the first shared deadline or recipe cap: **250 RPC members including retries, 20 series per discovery page, 100,000 blocks per initial log chunk and 10,000 decoded logs total**. These are research limits, not provider guarantees. Count dependent token/account reads and every batch member. Shrink rejected chunks only within shared recovery limits; detect truncation/caps and follow documented pagination. Return exact uncovered ranges/IDs when any limit is reached. Neither an empty page nor a partial discovery page proves completeness.
- Decode exact integer widths, bools, address padding and tuple lengths; reject empty/malformed replies. Keep raw exact integers until final scaling; use hex/decimal strings across tools that round JSON numbers above `2^53-1`. Token `decimals()` must be read at B; the reviewed app assumes USDG 6 and outcome tokens 18, so any discrepancy makes its displayed-unit formulas inapplicable until explained.

Use the optional runner's `predict` or `house` command for repeatable collection under the shared limits. Grade selected-deployment discovery, event coverage, getter/account reconciliation and actual cash matching independently. Event-complete purchases are not transfer-reconciled purchases unless the USDG legs match. Unknown beneficial ownership or unestablished net return does not itself mean event coverage failed.

## 2. Discover series; distinguish time, state and availability

Call Desk `seriesCount()` at B. Discover IDs **1 through count**, in bounded pages, then call `series(id)` for each relevant ID. Never assume the count is one, reuse the app's current series cache, or treat its twelve-row history limit as completeness. For a large count, a newest-first page is useful but must say which older IDs were not inspected. Cross-check against all covered `Opened` events; count, duplicate/missing IDs, zero tokens, unexpected `none` entries and inconsistent opening records are evidence gaps, not entries to discard silently. A count of zero is meaningful only for that identified deployment at B.

The tuple is **26 static ABI words in this exact order**; use the supplied ABI rather than guessed offsets:

```text
status:uint8, openTime:uint64, lastCallTime:uint64, closeTime:uint64,
printTime:uint64, settledAt:uint64, todayWad:uint256, lineWad:uint256,
long:address, short:address, longOut:uint256, shortOut:uint256,
bookUsdg:uint256, virtualLiquidity:uint256, backingUsdg:uint256,
volumeUsdg:uint256, feesUsdg:uint256, netSpentUsdg:uint256,
vaultFees:uint256, lastMarkWad:uint256, printWad:uint256,
longPayoutUsdg:uint256, prizePot:uint256, prizePaid:bool,
bestGuesser:address, guessCount:uint256
```

Live decoder `zO` maps **0 none, 1 open, 2 resolved, 3 voided**. Any other value is unknown, not `none` (do not copy the frontend's unknown-to-none fallback). `long` / boolean `true` maps to **HIGHER**; `short` / `false` to **LOWER**. These are series-specific addresses, not evergreen token identities. Read each discovered token's `name()`, `symbol()`, `decimals()` and `totalSupply()`; names alone do not prove the series association.

There is **no question/title string in this tuple**. The observed current app labels the product Treasury Weekly and displays a combined Treasury-plus-Sleeve question. Attribute that metadata to the dated app; do not claim it is an on-chain title, Core RFV alone, or the authoritative valuation oracle. The shared UI formats `lineWad`, `todayWad`, `printWad` as **millions of displayed dollars with 18 decimals** (`raw / 10^18` million; `raw / 10^12` displayed dollars), unlike probability `markWad / 10^18`. Retain raw values and verify the applicable generation's display convention before composing a question. Do not derive the settlement print from today's unrelated asset marks.

At block timestamp `t`, report raw status, all six timestamps, global `halted`, and separate flags:

| Observation | Report |
|---|---|
| status 1, `openTime <= t < lastCallTime` and `t < closeTime` | Trading window; buys remain conditional on halt, side/skew, amount, minimum and account restrictions; sells have a separate gate |
| status 1, `lastCallTime <= t < closeTime` | Last call: published live UI permits only skew-reducing buys and describes sells as open; not every amount/account is proven acceptable |
| status 1, `t >= closeTime` | Closed, awaiting settlement; neither a passed print time nor an app countdown creates a payout |
| status 1, `t > printTime` | Specifically awaiting a posted print/settlement; preserve overdue timing |
| status 2 | Resolved; use stored settlement result/time, not a newly calculated winner |
| status 3 | Voided; retain stored payout and redemption evidence; do not substitute resolved binary-win rules |
| status 0, pre-opening timestamps, unknown enum or contradictory times | None/scheduled/unknown as supported; explain the inconsistency instead of advertising an active market |

`halted` is described by the live error/UI text as a **new-buy halt**, not a sell halt. `minTicket()` is a USDG raw-unit gate; read it rather than substituting the frontend's separate minimum, which can differ. `barred(account)` establishes only that account's flag. Shared `wx` / `KE` side/skew constants are frontend model evidence, not deployed getters. **Only when the timestamp table indicates trading or last call**, describe the relevant buy window as conditional and sell window as acceptance-unproven, never “executable now”; preserve halt and last-call restrictions. At/after close, report closed even if status remains 1 and halted is false. Status 1 is an enum, not a trading-window flag; House `live()` is not a buy gate. Label any frontend-derived per-side availability and its assumptions rather than importing model constants into verified chain state.

`markPrice()` is a Desk-level current mark, **not a per-historical-series getter**. The live adapter computes open-series indicative marks with shared frontend curve code and uses `lastMarkWad` for non-open series. For historical rows retain the stored value and its scope; do not relabel the current Desk mark or a modeled chart as a historical execution price. Retrieve actual log block timestamps for activity, not the app trail's estimated timestamps based on assumed block rate.

**Generations:** a new Desk/Vault can reset counts and IDs. Key rows by `(chain, desk address, series ID)` and track associated Vault. The selected registry's known deployment(s) are not proof that every historical generation is catalogued. A request for “all Predict activity” needs each relevant deployment's start/end and complete history. Otherwise report “this selected deployment” and the unresolved historical scope. House `generation()` / `generationStartSeries()` expose an additional internal boundary; record them without conflating them with a replacement address or guessing undocumented reset rules.

## 3. Retrieve complete event evidence, not a chart sample

Use address + topic-filtered `eth_getLogs`, bounded inclusive ranges and provider-supported pagination. For since-opening figures, obtain the exact `Opened` transaction/block (or a justified deployment-to-B scan); openTime-to-block-rate estimates are not a completeness proof. Scan through B without gaps, deduplicate by block hash/transaction hash/log index, reject removed/noncanonical logs and sort by block/transaction/log order. Retain source ranges, page limits, errors and completion status. Receipts are needed for transaction-specific transfers. Never assume every same-transaction transfer belongs to the measured leg.

Topic0 is **Ethereum Keccak-256 of the canonical signature**, not NIST SHA3-256. Indexed values are 32-byte padded; data contains only nonindexed fields, in ABI order. Supplied event ABIs establish that layout. Important Desk signatures (all amounts below are uint256):

```text
Opened(uint256,uint256,uint256,uint256,address,address)
Bought(uint256,address,bool,uint256,uint256,uint256,uint256)
Sold(uint256,address,bool,uint256,uint256,uint256,uint256)
Redeemed(uint256,address,bool,uint256,uint256)
Settled(uint256,bool,uint256,uint256,uint256)
NetBought(uint256)
NetBuyDeferred(uint256)
PrizePaid(uint256,address,uint256)
PrizeRolled(uint256,uint256)
```

`Opened`, Desk `Settled`, `PrizeRolled` have series in topic1. `Bought`, `Sold`, `Redeemed`, `PrizePaid` have series in topic1 and account in topic2. `NetBought` / `NetBuyDeferred` have **no series index**: a global sum cannot be assigned to a series without transaction/state evidence, especially when deferred spending crosses a boundary. Configuration events retained in the ABI can explain historical flag/role changes; today's flag is not yesterday's state.

Never decode `Sold` with the `Bought` field order. Their nonindexed data words are respectively `(long,tokensIn,fee,usdgOut,markAfterWad)` and `(long,usdgIn,fee,tokensOut,markAfterWad)`; their similar type sequences do not make token units into USDG. The ABI subset intentionally omits guesses and winner proposals: those are not purchases. Identify excluded topics separately in an unfiltered scan; other unknown logs remain unclassified, not wager volume or automatically irrelevant.

House signatures:

```text
Funded(uint256,uint256)
Settled(uint256,uint256,uint256,uint256,uint256)
Deposited(address,uint256,uint256)
DepositQueued(address,uint256,uint256)
DepositCancelled(address,uint256)
WithdrawNoticed(address,uint256,uint256)
WithdrawCancelled(address,uint256)
WithdrawClaimed(address,uint256,uint256)
```

House `Funded` / `Settled` have series in topic1. Account events have account in topic1; `DepositQueued` additionally has series in topic2, and `WithdrawNoticed` has paidAtSeries in topic2. **Desk and House Settled are different events with different signatures and fields.** Filter the correct emitter. USDG/outcome `Transfer(address,address,uint256)` has from/to in topics1/2 and value in data. Do not apply this ERC-20 event ABI to internal House shares.

## 4. Activity since opening: purchases, exits and funding are different

For each series and side, report complete-log counts and these **separate** raw-unit sums before scaling. The event field names are from the published live ABI; cash interpretations require matched USDG transfers. The shared live UI buy/sell amount functions distinguish gross, fee and net, but are not proof of deployed internal counter updates.

| Metric | Event calculation / interpretation |
|---|---|
| Gross purchases | `sum(Bought.usdgIn)`; trader USDG paid, not House funding |
| Buy fees | `sum(Bought.fee)` |
| Net purchase premium | Gross purchases minus buy fees; not token count or a claim that every remaining unit stays in House equity |
| Net sell proceeds | `sum(Sold.usdgOut)`; confirm actual trader receipts |
| Sell fees | `sum(Sold.fee)` |
| Gross sell value | Net sell proceeds plus sell fees, provided transfers confirm this net/fee convention |
| Redemptions | `sum(Redeemed.usdgOut)` separately, with redeemed token amounts and settled/voided status; not sell volume or a new wager |
| Outcome token flow | `Bought.tokensOut`, `Sold.tokensIn`, `Redeemed.tokens`, split by side and scaled by that token's decimals; **not USDG** |
| House funding | House `Funded.usdg`, series-tagged and matched to Vault-to-Desk USDG transfer; capital, not a trader purchase |
| House returned capital | House `Settled.usdgReturned` and Desk `Settled.toVault`, matched to Desk-to-Vault transfer; gross return, not fees or net profit |
| Prizes / NET routing | `PrizePaid.usdg`, `PrizeRolled.usdg`, `NetBought.usdgSpent`, `NetBuyDeferred.usdgPending` separately; rollover/pending are not cash payments, NET buying is not burning |

**Do not invent funded capital from a field name.** `Opened.backingUsdg`, tuple `backingUsdg`, `bookUsdg`, `virtualLiquidity`, `vaultFees` and `Funded.usdg` describe different values. There is no per-series `fundedAmount` getter in the supplied ABI. Use the actual `Funded` event and receipt when available. If it is missing, show the getter's exact raw field under its own name and mark original funded amount **unknown**, unless another reviewed implementation/transfer reconstruction establishes it. Do not divide by a guessed prize percentage or copy a mock funding formula. A bare Vault-to-Desk transfer without series association is only an observed transfer, not proof of that series' original funding.

**Backing and book are not cash synonyms.** Compare `backingUsdg` with actual `Funded.usdg + virtualLiquidity`: the virtual part must not be counted as deposited capital. Separately compare `bookUsdg` with `Funded.usdg + gross purchases - buy fees - gross sell value` for an open series with no other book-affecting legs. This book calculation excludes both buy and sell fees; subtract **gross**, not net, sell value. Compare actual Desk USDG balance with `bookUsdg + vaultFees`, rather than assuming balance equals book. Check `feesUsdg` against `netSpentUsdg + vaultFees` only with deferred spending and any other fee allocations separately resolved. These are diagnostic reconciliations for the observed open-series accounting, not universal equalities across settlement, deferred spending, donations or later generations. Do not infer fees, deposits or a funded amount solely by rearranging them when their supporting history is missing.

Reconcile instead of silently adjusting totals:

1. **Counter comparisons:** compare event-derived buy gross + sell gross with `volumeUsdg`, and buy fees + sell fees with `feesUsdg`; compare account fee sums with `feesPaid(series,account)`. These are explicit reconciliation hypotheses, not asserted Solidity formulas: the reviewed `volumeUsdg` increment code belongs to the **mock**, while the live adapter only reads the getter. A match establishes an observed reconciliation over the covered scope, not a general implementation audit. Report both sides and any residual. `volumeUsdg` alone cannot distinguish purchases from sells. `vaultFees` is an exposed fee-accounting field, not realized net PnL or a guaranteed half of total fees.
2. **Outcome supply:** reconcile each token's complete zero-address mint/burn Transfer history with `totalSupply()` at B, starting from known zero issuance or a justified opening supply. Compare buy/sell/redemption amounts with their actual token mint/burn receipts and tuple `longOut` / `shortOut`. Do not assume the tuple counters are decremented by redemption without evidence; stored exposure can differ from redeemable token supply after settlement. Transfers between holders change attribution, not aggregate supply. Current token holdings are exposure, not cumulative wagers or holder cost basis.
3. **Cash:** for USDG at each Desk/Vault address, `balance_B - balance_A = incoming Transfers - outgoing Transfers` over complete `(A,B]` history. Reconcile the actual receipt legs with buy, sell, funding, return, redemption, prizes and fee routing. Keep unmatched transfers as a signed residual with transaction references; never force them into wager volume. An opening in the middle of a block requires transaction/log-order treatment, not using the end-of-block balance as the pre-open state.
4. **Liabilities:** record Desk USDG balance, `reservedUsdg()`, `pendingNetUsdg()`, `prizeCarry()`, per-series `prizePot`/`prizePaid`, and unresolved outcome exposure separately. These fields are not established disjoint buckets; do not add them all or subtract them twice. For settled claims, the shared live payout display uses `floor(tokens * payoutRaw / 10^18)`, with HIGHER payout `longPayoutUsdg` and LOWER `10^6 - longPayoutUsdg`; apply only with confirmed 18-decimal outcomes / 6-decimal USDG and valid payout range. Voids use the stored payout, not an assumed 0/1 winner. Label this a frontend-indicated remaining claim estimate unless deployed redemption semantics are established; per-holder rounding can differ from aggregate multiplication. A notional sum is neither cash already redeemed nor proof of solvency.
5. **No fee/volume/PnL collapse:** gross purchase minus net sales minus redemptions is trader net cash outflow in the covered interval, not house realized earnings: open claims, funding, fee allocations, prizes and unpaid obligations remain. Do not add fees again to cash balances that already contain them. Gross purchases count repeated use of the same money and are not unique capital or unique people.

On deadline, resource exhaustion or unavailable event ABI/history/receipts/archive reads, return the preserved pinned snapshot promptly: inspected series identities/states, named getter counters, balances and relevant House fields. Label flow metrics and decomposition **unavailable/partial**, not zero. `volumeUsdg` cannot substitute for gross purchases or absent buy/sell/redemption history; queue getters cannot prove account ownership; absence of settlement in a partial scan cannot establish zero lifetime settlements. Give inspected/uninspected IDs and exact covered/missing ranges. An exact observed partial sum is not a “since opening” total.

## 5. House capital, ownership, queues and claims

At B read House `live()`, `seriesCount()`, `generation()`, `generationStartSeries()`, `activeAssets()`, `totalShares()`, `sharePriceWad()`, `totalPending()`, `totalClaimable()`, plus USDG `balanceOf(vault)`. Preserve named values rather than relabeling all as TVL. `activeAssets=0` while a series is funded is not by itself zero House capital. The reviewed live House UI displays **open series.bookUsdg when status is open, otherwise activeAssets**; it does not add the two. This book is not all Desk cash: compare fee reserves separately as above. Nor is it settled House equity or shareholder liquidation value, because trader payout exposure remains. For a live Vault, compare its held USDG with pending/claimable cash rather than treating the balance as a second copy of its already-funded underwriting capital; only the evidenced components belong in that reconciliation.

House shares use a **10^18 accounting scale in the live UI**. `sharePriceWad` is named WAD but contains **raw USDG per 10^18 shares**, not an ordinary 18-decimal dollar price. The UI displays raw price divided by 10^6 and computes `floor(sharesRaw * sharePriceWad / 10^18)` raw USDG. Keep shares, raw USDG and displayed USDG distinct. `totalShares * price` is a share-price accounting valuation, not another asset bucket to add to the cash/book. During an open series the price can be a previous struck price rather than mark-to-market underwriting equity.

For each known fund-controlled identity (including the canonical Sleeve, without assuming it is the sole fund owner), call `sharesOf(address)`, `assetsOf(address)`, `pendingOf(address)` returning **(usdg,series)**, and `noticeOf(address)` returning **(shares,series)**. Discover other account addresses from complete House deposit/queue/withdrawal events from deployment or a justified opening inventory, then read the same four getters for them. A page of depositors is not every current owner; no holder-count/enumeration getter or ERC-20 share Transfer ABI is supplied.

Classify **evidenced fund-controlled**, **evidenced other-controlled**, and **unattributed** claims. Unknown is not automatically third-party retail. Keep contract custody/beneficial-ownership uncertainty. The fund's own shares share gains/losses according to publisher terms; that is not a first-loss guarantee. Reconcile classified share totals to `totalShares` only after handling notice/generation semantics; residual ownership stays unattributed. Never infer outside ownership solely by subtracting one Sleeve read when other protocol custody is unexamined.

The live adapter's settled-series predicate for a House queue index `n` is:

```text
settled(n) = n < house.seriesCount OR (n == house.seriesCount AND NOT house.live)
matured_notice = notice.shares > 0 AND notice.series != 0 AND settled(notice.series)
```

This is an **accounting-state predicate**, not a wall-clock deadline. A passed print time does not mature a claim by itself. For a matured notice read `exitPriceWad(notice.series)`; the live adapter indicates `floor(notice.shares * exitPriceWad / 10^18)` raw USDG. A zero stored exit price can mean a zero-value result; a failed/missing read is unknown, not zero. Claim readiness is not proof of payout: require actual `WithdrawClaimed` plus USDG transfer for cash paid.

- **Queued deposits:** the live adapter displays positive `pendingOf.usdg` only while its series is not settled. Raw pending records can persist after accounting maturity; do not add every raw pending value to current shares/assets or `totalPending`. `joinPriceWad(series)` supplies the named join-price observation, but not permission to invent storage synchronization. Separate pending principal, matured/accounted entry and actual cash refund. `DepositCancelled.usdg` needs its transfer before calling it refunded cash.
- **Unmatured notices:** the live UI subtracts notice shares from `sharesOf` to display free shares; an outstanding notice is not an extra holding to add on top. Its final USDG value is unknown until the applicable exit price is established. Keep noticed share units and only a clearly labeled current-price indication.
- **Matured notices:** report claim amounts separately from active/free shares. `totalClaimable` is the global getter, not a new deposit; compare to enumerated matured notices, allowing only evidenced rounding/generation effects. Do not add an account's `assetsOf` to notice value without establishing that the getter excludes that claim. Report its raw getter valuation separately if this boundary cannot be reconciled.
- **Aggregate buckets:** `totalPending`, `totalClaimable`, active/share accounting and the live Desk book represent different stages/locations of capital. Reconcile them with cash transfers and funding/settlement transitions, not a naïve sum of every displayed number. Direct donations/unattributed transfers can make cash differ from accounting. The app ABI's `noticedShares(uint256,uint256)` has unnamed keys and no reviewed live consumer establishing order, so it is intentionally **not supplied or called**. Enumerated notices are a useful partial fallback, not a fabricated global schedule.
- **Generation changes:** the ABI exposes generation getters but the reviewed live adapter does not establish complete reset/storage rules or a generation event. Do not replay a mock's zero-capital reset or carry old shares, notices or price series across a reset unqualified. If boundary semantics cannot be established, report current raw getters and known account observations, but mark historical ownership/performance reconciliation incomplete.

## 6. Fees, realized result and cashflow-neutral performance

`feesUsdg` / `vaultFees` are not “the House earned” net profit. A settled series with complete source-labeled and transfer-reconciled `Funded.usdg = F` and returned `Settled.usdgReturned = R` supports **net underwriting cash return `R - F`** for that scoped funding cycle, only after proving no extra funding/refund/return legs were omitted. Preserve whether other prizes/costs were already netted; do not deduct them twice. Desk `toVault` and House `usdgReturned` are two observations of the same leg, not additive revenue. An open series has no finalized result; observed fee income does not remove its outcome losses.

House `Settled` also names `sharePriceWad`, `exitUsdg`, `joinUsdg`. Joining/exiting investor capital is not underwriting profit. Reconcile aggregate settlement fields with the corresponding queue/notice observations and transfers; event labels do not by themselves prove when internal per-account storage synchronized. For a broader fully reconciled period, the accounting identity is closing equity minus opening equity minus external contributions plus external withdrawals, with equity measured consistently after liabilities. If such endpoint equity or complete cashflows are unavailable, **net PnL is unknown**; do not replace it with balance growth.

For performance, use compatible **struck share prices**, not gross vault balance changes. Read the relevant `exitPriceWad(series)` and preceding applicable `joinPriceWad(series)` / opening struck price, confirm their place on the same generation's timeline, and calculate `price_end / price_start - 1` with a positive opening price. The live history adapter uses previous-series `joinPriceWad(id-1)` as its historical comparator; that consumer convention does not justify assuming an unobserved initial price or bridging a reset. Investor cashflows at established join/exit prices must be neutral to the per-share comparison; changes to the share basis or generation break it. Chain compatible completed-period factors for a period return, stating actual elapsed time and missing periods. A withdrawal is realization of a claim, not a new yield.

With no compatible settled observations, report **no realized share-price return established**. Do not extrapolate fees earned in an hour/day or the current series into instant APY, guaranteed weekly yield or one-year income. The app's trailing annualized display is a historical presentation, not a forecast; use measured completed-period returns by default and distinguish them from an individual investor's cashflow-dependent return.

## 7. Answer with the coverage boundary attached

Include requested metrics and their supporting reconciliations. Mark each exact/partial/unavailable and transfer-reconciled versus event-labeled:

| Output | Fields |
|---|---|
| Scope/evidence | Chain/deployments; B number/hash/time, retrieval and metadata dates; interval, log coverage/budget, inspected/uninspected IDs and generations |
| Series | IDs, attributed question/line, outcome identities, raw status, buy/sell/closed/pending/resolved/void flags, halt and relevant timestamps |
| Activity | Gross purchases, buy fees/net premium; gross/net sell value and fees; redemptions, outcome-token amounts; House funding/return |
| Reconciliation | Getter comparisons, cash/supply/liability residuals, unclassified transfers and unresolved semantics |
| House | Named asset/share/price fields; fund/other/unattributed ownership; queued deposits, noticed shares, matured unpaid claims, paid withdrawals; current-price indications versus settled entitlements |
| Performance | Established completed underwriting result and compatible share-price return, or why PnL/ownership remains unknown |

State denomination and rounding residuals; USDG is not assumed dollar parity. Attach relevant address/transaction links using [address conventions](../assets/address-conventions.json).

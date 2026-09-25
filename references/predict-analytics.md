# Read-only Predict and House Vault analytics

Use for current series, activity since opening, and House capital/ownership/performance. The [research guardrail](guardrail.md) and [Safety](safety.md) govern retrieval and execution. Concrete user-operated workflow explanations, separately validated read-only quotes and isolated nonbroadcast simulations are allowed. The agent must not operate wallets, sign, submit transactions, mutate live-chain state or prepare execution-ready transaction artifacts; a quote or simulation is not an actual outcome. Dashboards are optional evidence; [product terms](products.md#netnet-predict-weekly-outcomes-and-house-vault) remain separate from measured balances.

**Recipe reviewed: 2026-09-25.** This is separate from the September 18 interface source pin and from any RPC block/retrieval time. Settlement depends on a publisher-controlled print: the documented team Safe/grader posts it. Range bounds do not authenticate the correct Treasury-plus-Sleeve valuation. Read the settlement trust boundary below before treating a resolved enum as a correct result.

## 1. Select identities, evidence and a bounded snapshot

Read `analytics.predict_house` in [address-index.json](../assets/address-index.json), follow its literal route file, then the selected canonical `{file,id}` records, this recipe, and the needed [Predict interface](../assets/analytics/predict-interface.json) / [House interface](../assets/analytics/house-interface.json). Load relevant contract records rather than the entire catalog by default. The Predict asset's `abi` applies to the Desk; `token_abi` applies to USDG and discovered outcome tokens. The House asset's `abi` applies to the Vault, **not an ERC-20 share token**. Both bundled fragments contain only view functions and events; no executable code or transaction methods. They are not exhaustive research allowlists: supplemental interfaces, public metadata, balances, ownership, historical events and evidenced local calculations may be investigated after establishing provenance, exact semantics and applicability. Quote and other ABI omissions limit the fragment and helper, not separately validated research.

The interface source is the pinned official [September 18 app asset](https://app.netnet.capital/assets/index-9OJ6-wtv.js), source ID `netnet-app-registry-20260918`, SHA-256 `379faedc6c6494416fada1208e61dfd0913f2ab399f27a9ba56e5031913fca5d`. `An` / `Ot` supply Desk / House ABIs; `Re` supplies the token ABI; `HO` is the live adapter. `C_` selects `HO` for live mode and `iI` for mock mode; `J7` is the mock vault. The supplied enum decoding and account/display interpretations below come from live/shared consumers, **not mock state transitions**. Published ABI and a successful getter are interface evidence, not verified Solidity, enforced economics or a solvency audit.

- Define chain **4663**, Desk/Vault generation(s), interval `(A,B]` or **opening transaction through B inclusive**, desired series/owner scope, and native USDG versus USD valuation. USDG units are not automatically US dollars; use independently supported USDG/USD pricing for conversion, or leave amounts in USDG.
- Check `eth_chainId`, pin canonical block number/hash/timestamp `B`, and record retrieval time separately. All snapshot reads use B; history reads end at B. Use block timestamps, not the app's wall clock, to classify historical state. Recheck hashes after retrieval; reject mixed forks. Current app labels and registry metadata need their own observation dates and cannot silently be backdated to B.
- Follow the shared [quick-pass defaults and collector limits](integrations.md#live-analytics-execution-limits) before retrieval; requested deeper research may use a suitable host-authorized scope beyond those defaults. Preserve the question's required same-block state before scanning history. For market/wager questions, prioritize Desk identity, `seriesCount()`, inspected series tuples, USDG units and named counters; do not add a full House ownership/queue scan unless needed by the question. For House questions, prioritize its wiring, share/price/queue/claim fields and relevant series state, then the ownership and cash history needed by the requested metrics; do not add unrelated wager histories. A snapshot does not establish complete event totals or beneficial ownership. If B is pruned, retain the missing value or restart all dependent reads within the applicable research budget; never splice newer values into old state.
- The [official public endpoint](https://docs.robinhood.com/chain/connecting/#public-endpoints) is `https://rpc.mainnet.chain.robinhood.com`; availability, log limits and archive support are not guaranteed. Missing history is not zero activity.
- Check nonempty deployed code and Desk `vault()`, `usdg()`, `sleeve()`, `treasury()`, `net()` and House `desk()`, `usdg()`, `wired()`. Match the chosen canonical identities and dynamically returned dependencies. Record `owner()`, `grader()` and `halted()` as current roles/flags, not an audit of all privileges. Code presence does not verify implementation. A mismatched generation or decode stops application of this ABI; do not silently switch addresses.
- Default quick-pass scope: **250 RPC members including retries, 20 series per discovery page, 100,000 blocks per initial log chunk and 10,000 decoded logs total**, stopping at the shared deadline or cap. These are defaults, not provider guarantees or ceilings on separately host-authorized deeper research; the runner's enforced limits remain local to its implementation. Count dependent token/account reads and every batch member. Adjust chunking and recovery to provider constraints and the authorized scope; detect truncation/caps and follow documented pagination. Return exact uncovered ranges/IDs when the applicable budget is reached. Neither an empty page nor a partial discovery page proves completeness.
- Decode exact integer widths, bools, address padding and tuple lengths; reject empty/malformed replies. Keep raw exact integers until final scaling; use hex/decimal strings across tools that round JSON numbers above `2^53-1`. Token `decimals()` must be read at B; the reviewed app assumes USDG 6 and outcome tokens 18, so any discrepancy makes its displayed-unit formulas inapplicable until explained.

Use the optional runner's `predict` or `house` command for repeatable collection under its fixed limits; use separately validated research methods for needed coverage beyond its support. Grade selected-deployment discovery, event coverage, getter/account reconciliation and actual cash matching independently. Event-complete purchases are not transfer-reconciled purchases unless the USDG legs match. Unknown beneficial ownership or unestablished net return does not itself mean event coverage failed.

For a quick single-series answer run `python3 -I scripts/analytics.py predict --series 2 --json` (replace `2` with the requested positive ID). **`--series ID` means snapshot only**: pin/recheck B, check Desk/House/USDG code and wiring, record roles/flags/dependencies, decode only that series and its outcome-token metadata/supply. It makes no log scans, deployment searches, original-funding reconstruction or unrelated House/account-history reads. IDs outside `seriesCount` fail rather than silently selecting the latest row. `discovery_complete` applies only to the requested ID; history is `not_requested`, never zero. Omit `--series` for the existing all-series/history collection. Both modes retain fixed RPC/deadline limits, checkpoints and runtime provenance. Neither mode supplies a quote.

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

The **September 18 pinned live consumer** (`zO`, source `netnet-app-registry-20260918`, observed 2026-09-18) maps **0 none, 1 open, 2 resolved, 3 voided** and `long` / boolean `true` to **HIGHER**, `short` / `false` to **LOWER**. This is attributed enum/side interpretation, not a Solidity enforcement proof. Any other value remains unknown, not `none`. The September 25 [current app asset](https://app.netnet.capital/assets/index-BpcUqlRH.js) independently exposes `K_=["none","open","resolved","voided"]` and `Ja=e=>e==="higher"` in its live consumer path. Series-specific token addresses are not evergreen identities. Read each discovered token's `name()`, `symbol()`, `decimals()` and `totalSupply()`; names alone do not prove the series association.

There is **no question/title string in this tuple**. The observed current app labels the product Treasury Weekly and displays a combined Treasury-plus-Sleeve question. Attribute that metadata to the dated app; do not claim it is an on-chain title, Core RFV alone, or the authoritative valuation oracle. The shared UI formats `lineWad`, `todayWad`, `printWad` as **millions of displayed dollars with 18 decimals** (`raw / 10^18` million; `raw / 10^12` displayed dollars), unlike probability `markWad / 10^18`. Retain raw values and verify the applicable generation's display convention before composing a question. Do not derive the settlement print from today's unrelated asset marks.

At block timestamp `t`, report raw status, all six timestamps, global raw `halted`, and clock comparisons separately from the following **publisher-derived interpretation**. The runner's `state.observations` contains raw values/comparisons; `state.publisher_interpretation` contains the dated enum mapping, interpreted clock state and attributed rules. Neither buy nor sell acceptance is verified.

| Observation | Report |
|---|---|
| status 1, `openTime <= t < lastCallTime` and `t < closeTime` | Trading window; buys remain conditional on halt, side/skew, amount, minimum and account restrictions; sells have a separate gate |
| status 1, `lastCallTime <= t < closeTime` | Last call: publisher docs say skew-reducing buys and sells open; see the strict-skew distinction below, not proof every amount/account is acceptable |
| status 1, `t >= closeTime` | Closed, awaiting settlement; neither a passed print time nor an app countdown creates a payout |
| status 1, `t > printTime` | Specifically awaiting a posted print/settlement; preserve overdue timing |
| status 2 | Resolved; use stored settlement result/time, not a newly calculated winner |
| status 3 | Voided; retain stored payout and redemption evidence; do not substitute resolved binary-win rules |
| status 0, pre-opening timestamps, unknown enum or contradictory times | None/scheduled/unknown as supported; explain the inconsistency instead of advertising an active market |

The [publisher docs](https://docs.netnet.capital/predict), reviewed **2026-09-25**, describe `halted` as a **new-buy halt**, not a sell halt, and last call as “only skew-reducing buys.” `minTicket()` is a raw USDG gate; read it instead of the frontend's separate minimum. `barred(account)` establishes only that account's flag. At/after close report closed even when status remains 1 and `halted=false`; House `live()` is not a buy gate. Shared frontend curve constants are model evidence, not deployed parameters or live quotes.

**Strict-skew distinction:** the September 25 app asset (SHA-256 `7b499d958448f670e7e93f9c1fe9fffbac4a79343d3f097395266263aa802e6a`) has `sm` set `raisesSkew` only when post-trade absolute skew **exceeds** pre-trade absolute skew; amount gate `aA` rejects that condition at last call. Thus that frontend amount model permits equal absolute skew, including a symmetric book flip, rather than requiring strict reduction. Side badge `mT` is a different, amount-free indication. This reconciles the UI model with the docs' shorthand without asserting deployed strictness: contract enforcement, rounding and account/amount gates remain independently unverified. Do not convert either model or prose into unqualified `can_buy`/`can_sell` booleans.

`markPrice()` is a Desk-level current mark, **not a per-historical-series getter**. The live adapter computes open-series indicative marks with shared frontend curve code and uses `lastMarkWad` for non-open series. For historical rows retain the stored value and its scope; do not relabel the current Desk mark or a modeled chart as a historical execution price. Retrieve actual log block timestamps for activity, not the app trail's estimated timestamps based on assumed block rate.

**Generations:** a new Desk/Vault can reset counts and IDs. Key rows by `(chain, desk address, series ID)` and track associated Vault. The selected registry's known deployment(s) are not proof that every historical generation is catalogued. A request for “all Predict activity” needs each relevant deployment's start/end and complete history. Otherwise report “this selected deployment” and the unresolved historical scope. House `generation()` / `generationStartSeries()` expose an additional internal boundary; record them without conflating them with a replacement address or guessing undocumented reset rules.

### Settlement authority and distinct remedies

The [Predict docs](https://docs.netnet.capital/predict), reviewed **2026-09-25**, name the team Safe as grader and list the Safe as owner/grader. Fresh `owner()` and `grader()` at B establish returned role addresses only. Equal returned addresses do not establish appointment authority, Safe threshold/signers or a complete privileged-control audit; observations at one block do not prove later control. Those controls and any independent print-dispute rights are **unverified** until matching implementation/authority evidence is obtained.

The same docs describe lower/upper print bounds, but an in-range incorrect Sleeve mark can still be incorrect; bounds do not authenticate correctness. Keep three mechanisms separate: **challenging a posted print** (rights not independently established), **permissionless void if ungraded 72 hours after print** (documented liveness remedy, last-mark settlement, not correction of an incorrect posted print), and the **24-hour closest-guess winner challenge** (prize allocation, not outcome print arbitration).

Source reachability checked September 25: the [Blockscout Desk contract API](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x7EF9528408D99f98056922291048F0710001e015) returned creation/deployed bytecode but no verified Solidity/source ABI. The pinned September 18 bundle URL returned 404; retain its original pin/date rather than pretending it was freshly retrieved. The current asset above exposes the published `jn` Desk ABI (including `grade`, `setGrader`, `setHalted`, `setMinTicket`, `void`, `proposeWinner`, `payPrize`) but is not verified source. Neither that interface nor the deliberately view/event-only bundled fragment proves absence of print-challenge rights. No full-source control or grading audit is claimed.

### Short read-only quote research recipe

The current app's `jn` ABI and live adapter publish `quoteBuy(bool long_,uint256 usdgIn) -> (uint256 tokensOut,uint256 fee)` and `quoteSell(bool long_,uint256 tokensIn) -> (uint256 usdgOut,uint256 fee)`, both `view`. These are supplemental published interfaces, **not supported by this helper**, and are not an established Solidity implementation or an acceptance guarantee.

1. Pin/recheck chain 4663, Desk identity/code, `seriesCount`, selected tuple, timestamps, halt, `minTicket`, USDG and outcome decimals at B. The quote signatures have **no series ID**: establish which current series they price; do not apply them to a historical row.
2. Supply the user's chosen side and exact input: gross USDG raw units for buy, outcome-token raw units for sell. The reviewed convention is 6/18 decimals respectively, contingent on same-block token reads. With a relevant public account, independently read `barred(account)` and applicable balances/allowances; the helper snapshot does not claim account acceptance.
3. Independently validate the supplemental view ABI against the deployed target and decode exact return widths at B before calling the result a live read-only quote. Record inputs, output/fee units, block/hash and errors. Failed/missing quote evidence is unavailable, not zero and not a license to substitute frontend constants. A successful quote still does not prove clock/halt/skew/minimum/account, balance, allowance or slippage gates will accept a transaction.
4. Explain the user-operated choice and confirmation steps if asked, but do not connect wallets, sign, submit, or prepare execution-ready artifacts. This helper intentionally has **no quote engine or quote CLI**; frontend models may be described only as explicitly conditional models, never live quoted fills.


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
- **Unmatured notices:** the live UI subtracts notice shares from `sharesOf` to display free shares; an outstanding notice is not an extra holding to add on top. Its final USDG value is unknown until the applicable exit price is established. Keep noticed share units and clearly distinguish a current-price indication or assumed-exit-price projection from the final entitlement.
- **Matured notices:** report claim amounts separately from active/free shares. `totalClaimable` is the global getter, not a new deposit; compare to enumerated matured notices, allowing only evidenced rounding/generation effects. Do not add an account's `assetsOf` to notice value without establishing that the getter excludes that claim. Report its raw getter valuation separately if this boundary cannot be reconciled.
- **Aggregate buckets:** `totalPending`, `totalClaimable`, active/share accounting and the live Desk book represent different stages/locations of capital. Reconcile them with cash transfers and funding/settlement transitions, not a naïve sum of every displayed number. Direct donations/unattributed transfers can make cash differ from accounting. The app ABI's `noticedShares(uint256,uint256)` has unnamed keys and no reviewed live consumer establishing order, so it is intentionally **omitted from the bundled fragment and helper**. Do not guess its keys. Independently verified public implementation/interface evidence may establish key order and semantics for a supplemental read; absence from the package does not bar that investigation. Until then, enumerated notices are a useful partial fallback, not a fabricated global schedule.
- **Generation changes:** the ABI exposes generation getters but the reviewed live adapter does not establish complete reset/storage rules or a generation event. Do not replay a mock's zero-capital reset or carry old shares, notices or price series across a reset unqualified. If boundary semantics cannot be established, report current raw getters and known account observations, but mark historical ownership/performance reconciliation incomplete.

## 6. Fees, realized result and cashflow-neutral performance

`feesUsdg` / `vaultFees` are not “the House earned” net profit. A settled series with complete source-labeled and transfer-reconciled `Funded.usdg = F` and returned `Settled.usdgReturned = R` supports **net underwriting cash return `R - F`** for that scoped funding cycle, only after proving no extra funding/refund/return legs were omitted. Preserve whether other prizes/costs were already netted; do not deduct them twice. Desk `toVault` and House `usdgReturned` are two observations of the same leg, not additive revenue. An open series has no finalized result; observed fee income does not remove its outcome losses.

House `Settled` also names `sharePriceWad`, `exitUsdg`, `joinUsdg`. Joining/exiting investor capital is not underwriting profit. Reconcile aggregate settlement fields with the corresponding queue/notice observations and transfers; event labels do not by themselves prove when internal per-account storage synchronized. For a broader fully reconciled period, the accounting identity is closing equity minus opening equity minus external contributions plus external withdrawals, with equity measured consistently after liabilities. If such endpoint equity or complete cashflows are unavailable, **net PnL is unknown**; do not replace it with balance growth.

For performance, use compatible **struck share prices**, not gross vault balance changes. Read the relevant `exitPriceWad(series)` and preceding applicable `joinPriceWad(series)` / opening struck price, confirm their place on the same generation's timeline, and calculate `price_end / price_start - 1` with a positive opening price. The live history adapter uses previous-series `joinPriceWad(id-1)` as its historical comparator; that consumer convention does not justify assuming an unobserved initial price or bridging a reset. Investor cashflows at established join/exit prices must be neutral to the per-share comparison; changes to the share basis or generation break it. Chain compatible completed-period factors for a period return, stating actual elapsed time and missing periods. A withdrawal is realization of a claim, not a new yield.

With no compatible settled observations, report **no realized share-price return established**. Use measured completed-period returns by default and distinguish them from an individual investor's cashflow-dependent return. The app's trailing annualized display is a historical presentation, not a forecast. When requested, show explicit projected fees, share prices, exit values, underwriting outcomes or returns with a stated horizon, formula and assumptions about volume, fees, outcome probabilities, losses, capital and costs. Hour/day fee annualizations or current-series one-year projections are conditional constant-rate scenarios, not realized APY, established future income or guaranteed weekly yield. Separate observed inputs, derived historical results and modeled estimates; missing actual accrual or finalized PnL does not prohibit such a model.

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
| Requested models/quotes | Forecast or quote scope, block/horizon, validated interface or model, observed versus assumed inputs, sensitivities and uncertainty; not a realized result or transaction authority |

State denomination and rounding residuals; USDG is not assumed dollar parity. Attach relevant address/transaction links using [address conventions](../assets/address-conventions.json).

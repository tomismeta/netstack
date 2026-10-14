# PredictDesk, House and outcome-contract semantics

**Evidence observed October 10, 2026.** This is an exact-generation, targeted runtime review, not verified Solidity, compiler equivalence, a full audit or a live solvency report. The independently accessible Blockscout contract responses returned creation/deployed bytecode but no verified source or ABI. The canonical RPC was denied in this session; no alternate RPC or bypass was used and no live totals were obtained. The [analytics recipe](predict-analytics.md) describes fresh collection; [guardrail](guardrail.md) and [safety](safety.md) remain controlling.

## Identity and evidence

- [Desk catalog](../assets/contracts/predict.json): all 33 functions in the obtained publisher ABI, with permission/economic semantics and runtime offsets.
- [House catalog](../assets/contracts/vault.json): all 27 functions, including one-shot wiring, deposits/queues, notice/claim accounting and reset semantics.
- Outcome catalogs: the 12-function, 1,993-byte variant independently observed at eight canonical HIGHER/LOWER addresses for series 1–4, each bound to its own identity below. These are deployment identities, not collection seeds or current positions.
- [Evidence manifest](../assets/contracts/predict-source-evidence.json): hashes, exact paths, dependency identities, provenance URLs and remaining limits. No third-party source/runtime blobs or financial history are packaged.

| Series | HIGHER catalog | LOWER catalog |
|---|---|---|
| 1 | [HIGHER #1](../assets/contracts/predict-outcome-series-1-higher.json) | [LOWER #1](../assets/contracts/predict-outcome-series-1-lower.json) |
| 2 | [HIGHER #2](../assets/contracts/predict-outcome-series-2-higher.json) | [LOWER #2](../assets/contracts/predict-outcome-series-2-lower.json) |
| 3 | [HIGHER #3](../assets/contracts/predict-outcome-series-3-higher.json) | [LOWER #3](../assets/contracts/predict-outcome-series-3-lower.json) |
| 4 | [HIGHER #4](../assets/contracts/predict-outcome-series-4-higher.json) | [LOWER #4](../assets/contracts/predict-outcome-series-4-lower.json) |

| Target | Exact explorer runtime identity (Keccak-256) |
|---|---|
| Desk `0x7ef9528408d99f98056922291048f0710001e015`, 18,317 bytes | `e7a63f394ad5aaf5f737f49508c136ea5db2ecc90d3019f53215d3b3d6ad2c43` |
| House `0xb488368902b1cbd7533f1536c3f860065398d3e9`, 5,534 bytes | `23b13523c73c5eeb691d96744f9cdd96eb32eca5668310798eb605ca4c75c65e` |
| Reviewed outcome variant, immutable Desk as above | `1e885071188ec8e93373085aafb1569fae587912b48aa61ffd2564538b7718c7` |

Primary sources: [Desk explorer](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x7EF9528408D99f98056922291048F0710001e015), [House explorer](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xb488368902b1CbD7533F1536C3F860065398D3e9), per-outcome URLs in the outcome catalog, [October 7 publisher ABI bundle](https://app.netnet.capital/assets/index-BbeISxZe.js), and [Predict documentation](https://docs.netnet.capital/predict). Main dispatchers match 33/27/12 obtained functions with no unmatched selectors in that scoped extraction. This does not establish exhaustive symbolic reachability or correctness of external dependencies.

The collectors compare same-block runtime bytes/hash with the reviewed identities before applying these accounting rules. A different future outcome implementation is an **unknown variant**, even if its name and ERC20 getters look familiar. Current series and token associations are dynamically read from the pinned Desk; never substitute the canonical historical list for discovery. No state/balance/nonce/wager/holder history is retained in assets.

## Desk authority and purchases/exits

Immutable `owner()` controls `open`, `setGrader`, `setHalted`, `setMinTicket`. `grader()` is mutable and independently controls `grade`; constructor identity does not prove the current grader. Owner identity is a contract authority fact, not a claim about Safe signers or personal control. `barred(account)` is a constructor-initialized buy exclusion in this runtime; no matching setter was observed.

`buy` requires an open current series, pre-close clock, nonzero gross USDG meeting `minTicket`, non-halted/non-barred caller, slippage and curve/skew constraints. It pulls gross USDG and mints the selected outcome to the caller. Book increases by gross less fee; volume increases by gross. Increased post-trade absolute skew is rejected after last call; equality is not rejected by that comparison. Other size/backing and rounding gates remain relevant.

`sell` has its own pre-close/current-series/nonzero/slippage guards but does not read the buy halt/barred flags. It burns caller outcomes, decreases book by **gross** curve value, increments volume by that gross value and sends **net** USDG after fee. `quoteBuy`/`quoteSell` use the current series (no series ID) and are not account acceptance or execution guarantees. The bundled helper still exposes no quote engine or transaction artifacts; supplemental read-only quote research remains possible under the existing recipe.

`feesUsdg` and `feesPaid(series,account)` accumulate both trade fees. The allocator sends `floor(fee/2)` into NET-spend budget and retains the remainder as `vaultFees`. It can combine prior deferred USDG with new fees; later `netSpentUsdg`/`NetBought` cannot be assigned to an earlier series or a single trade without further evidence. The immutable router path is USDG→NET with Sleeve recipient; NET purchase is not burning, and deferred/failed attempts are not successful acquisition. Fee observations are accounting, not a distinct trader-to-House transfer or realized underwriting profit.

Curve helpers use integer full-precision multiplication/division and conservative one-unit adjustments. Do not replace them with a frontend floating-point approximation, nor infer a fill from a quote.

## Settlement, print authority and claims

`grade` requires the current grader, current open series and time **strictly after** `printTime`. It checks numeric bounds using stored line and the Treasury `rfv()` dependency, stores the supplied print and resolves HIGHER only when **print > line**; equality selects LOWER. Bounds are sanity checks, not an independently reconstructed Treasury-plus-Sleeve oracle.

`void` is permissionless only **strictly after `printTime + 259200` seconds** for an ungraded open series, and settles from stored last mark. It is a liveness remedy, not a way to challenge or correct an already posted print. `proposeWinner` is a separate prize path: the runtime accepts an eligible stored guess not above the print, improving the stored eligible value, with earlier guess order breaking ties. `payPrize` is public after the 24-hour settlement interval and pays the selected account once or rolls the pot forward. None of these prize paths edits `printWad` or market payout. “Closest guess” prose must not be silently interpreted as an unrestricted absolute-distance competition above and below the print.

Settlement converts the mark to a raw USDG payout, reserving each outcome side with upward rounding. The House return is book less outcome reserve plus retained vault fees less the prize allocation; the reviewed allocation is `floor(vaultFees * 1000 / 10000)`. Book and vault-fee accounting are then cleared, retained claim/prize obligations remain on Desk, USDG is sent to House, and House `settle` is called. Voided and resolved prize/carry treatment remain separate; do not add overlapping `reservedUsdg`, `prizeCarry`, balance and prize-pot figures.

`redeem(series,side,tokens)` is holder-accessible for resolved/voided series, burns the caller's selected outcome through Desk authority, then pays `floor(tokens * payoutRaw / 10^18)`. HIGHER uses stored `longPayoutUsdg`; LOWER uses `10^6 - longPayoutUsdg`. Zero-valued losing outcomes can burn without positive USDG. The function reduces `reservedUsdg`, but **does not decrement stored tuple `longOut`/`shortOut`**. Use actual token supply and receipt burns for remaining claims, not the pre-settlement tuple exposure. Upward aggregate reserves and downward individual payouts can leave dust.

### Versioned publisher print definition remains a separate blocker

The October 7 documentation describes Treasury plus Reports Sleeve **part for part**, including Asset Bond Desk assets, V3/V4, TURBO, House deposit, THE BOOK, NET/sNET/wsNET and Advance cash/principal/inventory. Stock marks use live Rialto one-share quotes with Reports fallback; NET uses market/index. September 25 fee additions, NET-inventory exclusion and frozen opening House claim are historical definitions, not current instructions.

No reachable versioned print script/constituent ledger was recovered from the inspected official surfaces. Exact independent reconstruction still needs the script/version, print block/hash, positions and liabilities, Rialto quote/fallback ledger and actual grader submission. Neither the website Reports figure nor stored `printWad` fills those gaps. Core certification separately requires [block-specific validation](reserve-analytics.md#evidence-boundaries).

## House deposits, queues, share claims and generations

`wire` is one-shot and restricted to immutable deployer; it assigns the nonzero Desk authority. `fund`/`settle` require that wired Desk, not a depositor or arbitrary owner. `fund` sets live, increments House series count, zeros idle `activeAssets` and sends that capital to Desk. `settle(returned)` trusts the Desk's supplied accounting amount; it does **not** itself pull cash, so the preceding transfer must be corroborated.

In the [House indexed runtime](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xb488368902b1CbD7533F1536C3F860065398D3e9) observed October 10, idle `deposit` pulls USDG and issues floored shares at the struck price. Live deposits pull USDG into a current-series queue. Settlement processes the aggregate queue, while individual `pendingOf` records can persist until lazy sync. `sharesOf` incorporates eligible matured joins; syncing them emits **Deposited without fresh cash**. Therefore `sum(Deposited.usdg) + sum(DepositQueued.usdg)` is not contributed capital. `cancelDeposit` refunds only still-pending principal after synchronization. This is retained runtime analysis, not a fresh source or chain check.

`requestWithdraw` moves free internal shares into a notice for `seriesCount+1`. Exact mapping order is `noticedShares(generation,paidAtSeries)`. `sharesOf` includes unmatured notices, so they are not additional shares to add. `cancelWithdraw` restores shares only before maturity. A notice is matured by accounting state (`series<count` or `series==count && !live`), not the wall clock.

Settlement strikes `floor(returned*10^18/totalShares)` raw USDG per `10^18` shares, removes that generation's noticed shares and reserves floored aggregate exit cash. Remaining capital plus newly joined principal becomes active. A zero exit price with remaining shares advances generation and resets the active share basis; stale active shares/old joins are excluded lazily. **Matured notices survive reset.** `assetsOf` excludes matured claims, which use their stored exit price and are paid by `claimWithdraw`. Aggregate/per-account rounding can leave reserves not assigned by a naive sum.

House shares are not transferable ERC20 tokens. Raw getter ownership is not exhaustive beneficial ownership, and the helper does not replay every generation's account history. Cross-generation prices cannot be chained as investment performance. Gross returned capital minus uniquely identified, receipt-matched funding supports a scoped completed underwriting cash result; open exposure, missing returns, fees alone or balance growth do not establish realized PnL/APY.

## Fresh report interpretation

Existing commands remain `predict`, `predict --series ID` (snapshot only), and `house`. Their histories and receipts are bounded by the shared deadline/member/log limits. Partial results retain pinned state, exact observed subtotals and missing coverage rather than interpreting unreturned events as zero. A completed provider range must reconcile against independently read counters/state. Full totals additionally require a confirmed final block hash; event-labeled, receipt-matched and independent cash/supply evidence remain distinct.

`receipt_reconciliation.transactions` records cash/burn groups and lazy joins; singleton operation groups contribute attributed matched subtotals. Ambiguous same-transaction aggregates, absent/mismatched legs and receipt-discovered omitted events withhold confirmed cash totals. A scanned event that differs from its receipt is a terminal integrity failure even if the receipt's own cash legs balance. Fees remain event accounting, with deferred NET routing separately identified. Receipt checks cannot discover transactions entirely omitted by the provider; counters/state and an independent Transfer census remain necessary.


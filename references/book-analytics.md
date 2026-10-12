# Fresh THE BOOK analytics

Use the bundled read-only `book` command for a **new pinned snapshot** and optional bounded event/receipt collection. No cached financial state, market/bet list, transaction history, holdings or balances are loaded. [Contract evidence](book-contracts.md) describes the exact-generation publisher ABI, runtime correlation and unavailable Solidity boundary.

**THE BOOK's house pot is not Predict House Vault.** In the October 10 retained [SportsBookDesk evidence](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x3174dE69a84c53F82F6B6Dca5C64E705cFFe8Dd6), a settled winner's free **wsNET** credit belongs to the Book player ledger. It is not a liability, cashflow or profit adjustment of the separate **USDG** [Predict House Vault](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xb488368902b1CbD7533F1536C3F860065398D3e9). A shared Sleeve beneficiary and the word “house” do not merge those ledgers. For a separately scoped Book or consolidated analysis, establish ownership and claim treatment, and do not deduct settled credits again if the measured house pot already reflects settlement. These are dated identity/accounting findings, not fresh chain observations.

```sh
python3 scripts/analytics.py book --json
python3 scripts/analytics.py book --market-id MARKET_ID --bet-id BET_ID --detail full --json
python3 scripts/analytics.py book --max-markets 16 --max-bets 64 --deadline 120 --json
python3 scripts/analytics.py book --block SNAPSHOT_BLOCK --from-block START_BLOCK --detail full --json
```

Replace `MARKET_ID` and `BET_ID` with positive integer IDs selected for the question, and `SNAPSHOT_BLOCK` and `START_BLOCK` with the intended nonnegative block numbers (`START_BLOCK <= SNAPSHOT_BLOCK`). These are placeholders, not recorded observations; the numeric `--max-*` and `--deadline` examples are collection limits, not financial state. Canonical RPC permission denial ends the run; never retry through an alternate provider/client or turn failure into zero. Current research could not exercise live collection because that RPC was already denied.

## Options and finite scope

| Option | Scope |
|---|---|
| `--market-id` | Repeatable positive ID selection; otherwise newest IDs through the pinned `marketCount`. |
| `--bet-id` | Repeatable positive ID selection; otherwise newest IDs through pinned `betCount`. |
| `--max-markets` | Default8, range1–128. Bounds explicit/default selected markets; additional markets directly referenced by selected bets are read separately. |
| `--max-bets` | Default32, range1–512. Bounds explicit/default selected bet IDs. |
| `--from-block` | Optional nonnegative integer, through snapshot B inclusive. Without it **no historical logs or receipts** are requested. History covers all supported Desk events in that interval; snapshot ID options do not filter the history window. |
| `--block`, `--deadline`, `--detail`, `--json`, `--output` | Shared runner snapshot/budget/detail/output controls. Collection uses the existing sequential bounded Context,750-member budget and global event/response/deadline limits. A large selected scope can return partial when its budget runs out. |

The collector checks chain4663, pins B, compares Desk/Zap runtime hashes with the exact-address explorer evidence, reconciles canonical token/Sleeve/Desk getters and confirms wsNET18 before interpreting financial units. Unsupported runtime or identity mismatch stops semantic collection. The snapshot is rechecked before complete claims. A matching current runtime does not prove historical dependency behavior, source equivalence or finality.

## What the snapshot answers

- Current `marketCount`, `betCount`, `halted`, manager/grader and minimum/cap/reserve-rate parameters; unknown failed reads remain null, not UI defaults.
- `potsOf`, `freePot`, `playerTotal` and actual Desk wsNET custody. House capital, reserved cover, free player balances, locked risk-on stake and risk-off principal are displayed separately. Reservations overlap house capital.
- Native custody minus the publisher ledger decomposition, plus free-pot equality comparison; no deficit clamp and no automatic solvency/profit claim.
- Selected/recent market records and exposure, and selected/recent bet records with related markets. Status separates ungraded locked, decided-but-unsettled, settled internal credit and unknown market state.
- Stored wager/payout is counted only for settled records. An unsettled zero storage field is not a zero claim. A risk-on/push credit model is explicitly publisher-attributed, **not a verified claim or external payout**. Exact decided non-push risk-off payout is unavailable without verified rounding/implementation evidence.

`id_discovery` exposes selected IDs/counters and whether the selection covers every ID. Successful **bounded snapshot collection** can finish while `all_bet_ids_selected=false`; that flag is not transformed into a whole-book claim. `all_unsettled_payout_liability` remains null rather than summing a plausible subset. House reserve, player locks and free ledger are nevertheless useful global getter observations independent of selected-record enumeration. `selected_bet_observations.stored_settled_payout_subtotal` is selected cumulative internal credit, not interval cash or revenue.

No price conversion is performed here. wsNET18 amounts remain native; do not silently apply today's sNET index/NET price to historical receipts. Existing Sleeve RFV already values the house pot, so **do not add this collector again to combined totals**.

## Requested history and receipts

Only `--from-block` starts the optional history phase, **after** snapshot reads. Supported events are `MarketOpened`, `BetPlaced`, `FeeSplit`, `Graded`, `Settled`, `Voided`, `Cancelled`, `Deposited`, `Withdrawn`, `HouseDeposited`, `HouseWithdrawn`, `Skimmed`. Zap event signatures were not supplied and are not fabricated.

1. Read `marketCount` and `betCount` at the preceding block. A zero start uses zero baseline for these newly deployed counters; it does not promote the response to a verified lifetime ledger. A missing/pruned boundary prevents complete interval totals.
2. Scan exact Desk emitter/topics through B with Context's bounded ranges, page-cap splitting, identity checks and deduplication. Preserve covered/missing ranges and returned events even on later failure.
3. Compare unique contiguous placement/open IDs with before/after counter increments. **Empty logs with a counter increase are inconsistent**, not zero activity. Empty logs with unchanged counters support zero observed placements/openings in that interval only, subject to provider completeness. Existing bets and current liabilities remain visible.
4. Fetch successful receipts for each observed event transaction; compare scanned events and all supported same-receipt events, validate identities and inspect wsNET Transfer logs. Missing scanned receipt events prevent complete claims. Permission/integrity stops are terminal.
5. Preserve actual Desk custody inflows and outgoing transfers to canonical Sleeve, canonical Treasury and other recipients. Count each receipt once. Treasury zero, when available, means no such wsNET leg in this narrow collected transaction set; **not zero Treasury revenue generally**.

`event_reported.observed_subtotal` separates risk-off placement **principal**, qualified risk-on event amount, realized settlement wager, internal payout, house/Sleeve fee allocations, house capital deposits/withdrawals. These are not summed as revenue. `requested_window_total` requires all served ranges, matching boundary counters, receipt-event consistency and confirmed B. This is explicitly an **event-reported window**, conditioned on provider completeness; there is no all-bet historical settlement/fee-state census. `lifetime_total` is always null.

`receipt_confirmed.requested_event_transaction_total` additionally requires a checked receipt for every observed event transaction and agreement between each transaction's Sleeve outflow and fee allocation plus house withdrawals. A mismatch preserves the actual transfer observations but withholds the reconciled total. It is not a census of every Desk outflow, every funding token or every transaction omitted by the provider. Desk custody inflow mixes player funding and house capital; accounting event fields classify these separately. Matching Sleeve sums **do not prove a unique fee-level attribution**, wallet balance delta or house profit. An allocation without a matching transfer remains an allocation.

## Coverage, failures and output

- `coverage.collection_complete` means the requested bounded snapshot and, if requested, its event/receipt window passed the implemented checks and final B recheck. It does not imply source verification, global discovery, all lifetime activity or audited liabilities.
- Errors preserve successful observations. Denial, integrity failure, absent runtime match, missing boundary state, partial history, missing receipts and failed recheck withhold affected totals; no fallback/cached financial values are used.
- `--detail summary` removes detail rows while retaining precomputed scope/aggregates. Summary serialization must not recompute absent arrays as zero. Full output includes current observations and collected event/receipt evidence for this run only.
- Claim credit, actual withdrawal, house capital, reserved cover, received fees and realized net profit remain different. `won=false` is not sufficient to call a settlement a loss; push/void must be resolved against market state/result.


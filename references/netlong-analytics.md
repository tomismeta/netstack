# NetLong read-only market analytics

`netlong` discovers and accounts for the current selected futures vault and the separate real-token, long-only margin program. It does not submit transactions, create trade payloads, connect a wallet, or treat terminal demonstration data as chain state. LOSE awards are not open interest.

## Plain-language open-interest requests

An unqualified question such as **“How much open interest is there for NetLong?”** requests fresh authorized coverage of both programs unless the user explicitly asks for offline/package-only work. Do not silently narrow it to futures because “open interest” is futures terminology, require an extra live-read instruction, or require the user to know the product distinction.

1. **Discover both:** use `netlong --product all` (already the collector default), enumerating the futures vault and margin desk at the same pinned block and selected provider when feasible. One all-product collection supplies that shared context; if supplemental reads cannot share it, label their separate provider/block/time and do not claim same-snapshot reconciliation. For counts, retain `--detail full` or a full `--output` checkpoint from that collection. The four known futures symbols and example margin tokens are not coverage limits.
2. **Return two separately labeled blocks:** futures entry OI by desk (long, short, gross; USD-denominated notional) and margin funded debt by token (USDG, including accrued interest), with token exposure and position counts as defined below. Never produce a futures-plus-margin “total OI”; these measure different things and USDG parity is not assumed.
3. **Honor explicit scope:** “futures only” or “margin only” narrows the collection. An unqualified symbol such as NET can match both: discover both, then show the matching rows separately. Do not pass an ambiguous symbol to `--market` and silently choose the first match; use the all-product result or separately identified product/address queries.
4. **Keep missing coverage visible:** if one program is denied, unsupported or incomplete, say which program was not established alongside any supported results. Do not stop after a successful futures read and present it as whole-NetLong coverage. Access denial still ends the affected retrieval under the existing safety rules; breadth is not permission to bypass it.

The result must retain block/hash/time, sanitized provider/run provenance, per-program coverage and distinctions between complete totals, observed subtotals and unavailable values. No stored balances, reported historical totals, older checkpoints or dated market rosters are fallback inputs for a current answer. Keep any historical comparison in a separate dated section; failure to obtain current reads cannot be repaired by relabeling earlier observations.

## Commands and safety

From the package root, on a POSIX system with Python 3.10+:

```sh
python3 -I -B scripts/analytics.py netlong --detail summary
python3 -I -B scripts/analytics.py netlong --product futures --market BTC --detail summary
python3 -I -B scripts/analytics.py netlong --product margin --market NET --detail summary
python3 -I -B scripts/analytics.py netlong --product futures --market 0x77D247Ec5E2094E8226BCC1A5b8bfB8A903Bb00f --detail full
python3 -I -B scripts/analytics.py netlong --product margin --deadline 300 --output /tmp/netlong-margin-evidence.json --detail summary
```

`--market` accepts an unambiguous symbol, a futures **desk** address, or a margin **token** address. `--product` defaults to `all`. A bare `--market NET` can be ambiguous across products; select `--product futures` or `--product margin`. Discovery is not symbol-hardcoded. Unknown futures labels remain null and are address-queryable; a symbol query cannot establish uniqueness while discovered symbols are unknown. Unknown token symbols are read from the token, not guessed from names or liquidity pools. Refused, stale and delisted margin tokens remain visible if enumerated; visible is not necessarily eligible to open.

The default is one `latest-2` snapshot. `--block BLOCK` selects an explicit nonnegative block. All state and code calls use that block; historical event discovery ends there. The common collector checks the pinned block hash again after collection. A result without a confirmed recheck is not confirmed chain evidence. Prefer an authorized HTTPS endpoint selected before the run through host-injected `NETSTACK_RPC_URL`; absent configuration uses the optional public no-credential endpoint. The [shared provider contract](integrations.md#provider-selection-and-confidential-configuration) retains chain-ID, public-DNS, no-proxy/no-redirect, request, response, retry and walltime controls without exposing secrets. A permission denial terminates retrieval; no alternate endpoint is automatically attempted. On 2026-10-10 a separate integration accessibility probe returned HTTP 403: this is a live-verification gap, not evidence of zero OI, and not permission to retry through another route. These recipes describe supported operation when access is legitimately available; do not run them to evade an outstanding denial.

Stdout is JSON, with exact raw decimal strings and formatted quantities. `--detail summary` omits getter-level reads and individual positions, retaining accounting, coverage, errors and implementation checks. `--detail full` is the default. `--output` preserves atomic full partial/final checkpoints outside the installed package even when stdout uses summary; existing common output path and symlink protections apply. No results are written into the package. Exit 0 means the requested collection completed, 2 means partial/blocked, and 1 means invalid arguments/fatal initialization. A completed last-posted-mark calculation is not a promise that its price is fresh or executable.

## Discovery and implementation identity

Canonical records are referenced through `assets/analytics/netlong-routes.json`, not copied address inventories in the collector. The interface's publisher evidence is the complete October 10 trading entry bundle, identified by URL and SHA-256 in `assets/analytics/netlong-interface.json`. Code identity evidence uses separately recorded explorer runtime hashes. These are independent analysis assets, not a NetNet publication, verified Solidity, or an audit.

The separate October 12 [rendered futures review](netlong-futures-contracts.md#rendered-terminal-review-october-12) and [margin/lending/LOSE review](netlong-margin-and-lose-contracts.md#rendered-margin-lending-and-lose-review-october-12) cover terminal mechanics and UI/client discrepancies without replacing that executable-interface provenance. Margin `CAP USED` / `$ OPEN`, projected lender rates and LOSE's original-issuance `SUPPLY` label are not substitutes for funded debt, realized yield or current token supply. Use fresh contract inputs for analytics; UI observations explain the presentation, not a reusable financial snapshot.

- **Futures:** enumerate `vault.deskCount()` and every bounded `deskAt(i)`, then check `vault.desks(desk).registered`, the desk's `vault()` and `oracle()`, and its runtime model. Static BTC/ETH/SOL/NET labels are only publisher metadata for known addresses, never discovery filters. A new desk with no known symbol can still be addressed directly.
- **Margin:** match the desk, pot, TWAP, shared oracle and two linked-library runtime identities; check `pot`, `marginOracle`, `twapSource`, `usdg`, and the pot's reciprocal `desk`/`usdg` bindings. Require the model's six-decimal USDG convention from a pinned token getter. Enumerate `tokenCount()`/`tokenAt(i)` and read each token's actual metadata, listing, opening eligibility and marks. No NET/AI/CASHCAT/PONS token allowlist restricts discovery. Listing precision must agree with the token's pinned `decimals()`.
- **Supported future streams:** exact known deployed runtimes are accepted. The reviewed BTC/ETH/SOL creation template additionally supports new stream/feed identifiers with the same reviewed constructor configuration. All 49 masked words are constructor-patched PUSH32 operands; repeated copies must agree. Only stream/tape feed IDs may differ from that template's selected configuration. All non-immutable bytes, metadata, fixed dependencies and other configuration must match. NET is a separate exact-runtime model. Different implementations or unsupported constructor configurations remain explicitly unsupported, rather than inheriting an ABI/formula by selector resemblance.
- Runtime code is read at the selected block. Matching a hash/template establishes only equality to the analyzed bytes. It does not independently authenticate posted prices or prove all dependencies' current behavior. Stream IDs and verifier bindings are exposed, without pretending that reading them verifies a signed report. The collector does not fetch or submit off-chain reports.

A changed model requires new reviewed identity and accounting evidence; changing a token symbol alone requires no release. Additional same-model tokens automatically enter margin discovery. Superseded deployments are outside this command's totals.

## Futures: entry OI versus marked notional

`oiLongUsdWad()` and `oiShortUsdWad()` are **stored entry-size notional**, not mark-repriced base exposure. Reviewed runtime fill/close paths add/subtract `sizeUsdWad`. Each uses 18 decimal places and USD-denominated notional units, not raw NET or wsNET units:

- long = stored long size;
- short = stored short size, positive rather than a signed quantity;
- gross = long + short;
- net = long - short.

The desk's gross/net are reconciled against its vault registration `oiUsdWad`/`skewUsdWad`; all-market entry gross is compared with `vault.totalOiUsdWad()`.

To reprice current positions, scan bounded `Filled` events from the desk's recorded creation boundary, deduplicate trader addresses, and read each trader's current `positions(address)`. Closed/zero-size slots do not contribute. A newly discovered desk without a recorded deployment uses the common bounded historical-code binary search; that boundary assumes monotonic code existence and does not disprove historical redeployment. Event coverage remains explicit and assumes the provider has not silently omitted logs.

For each nonempty position:

```
markedNotionalWad = floor(sizeUsdWad * lastMark.priceWad / entryPriceWad)
```

These values are summed by side and then into gross/net. This is a **last-posted-mark notional**, not realized PnL, a liquidation quote, a new independently fetched market price, or an opening/closing execution guarantee. `lastMark`, its observation timestamp/rung and its age relative to the pinned block are exposed. In particular, NET's live bounded pool close mark can differ from its last posted mark. A nonempty position with a zero entry price, missing/zero mark or future-dated observation prevents the marked total. An empty, fully reconciled book has zero marked notional without requiring a nonzero price. Summed current position entry sizes must reconcile to the stored long/short counters before a marked total is published.

Current position entry notional and last-posted-mark notional are separately named in every aggregate. There is no double-counting of opposing longs/shorts as one-sided OI and no unlabelled division by two. Collateral in wsNET is not added to these notional values.

## Margin: funded debt and real token exposure

The [NET LONG prospectus](https://docs.netnet.capital/net-long) describes a real-token purchase funded by a USDG loan, with unspent wsNET collateral. The purchase loan is based on credited margin times leverage, not a generic leverage-minus-one shortcut. Pending-buy state is a request, not proof that a loan or swap occurred.

For a margin token's colloquial “open interest” question, lead with **funded USDG debt, including accrued interest**: the sum of pinned `debtUsdg(id)` for positions attributed to that token. This is the primary margin activity analogue chosen for the answer, **not a contract-defined futures OI metric**, not principal-only borrowing and not position market value. Supply these secondary measures separately:

- **Token exposure:** summed `unitsOf(id)` in that token's native units and its marked value where valid pricing is available. Debt can remain evidenced while marked exposure is unavailable.
- **Funded-position count:** count attributed, successfully read nondeleted positions with `debtUsdg(id) > 0`, including pending-sell positions with debt. Label it explicitly; distinguish pending-buy, open and pending-sell state counts when useful. Allocated IDs (`nextPositionId()-1`) are not active positions, and state2 alone does not prove positive debt.
- Use the full result's position rows for these counts. Summary `observed_position_count` counts retained nondeleted rows, including pending requests; it is **not** a funded-position count. With incomplete ID coverage or failed reads, report only qualified observed counts/subtotals, not whole-token totals or an inferred zero.


`nextPositionId()` allocates contiguous IDs starting at 1. Read bounded IDs in `[1, nextPositionId)` including deleted slots; do not rely on a hardcoded trader list or infer ownership from terminal screenshots. Supported observed states are 1 pending-buy, 2 open and 3 pending-sell. An unrecognized nonzero state or a non-enumerated position token is missing coverage, not an inferred open position.

For each current nonzero-trader slot:

- `debtUsdg(id)` is the actual pinned indexed debt, including accrued interest, in six-decimal USDG. Do not sum `loanUsdg` fields as funded current debt. The reviewed getter returns zero for zero scaled debt; borrowing occurs on execution of the pending buy. The lending account's independent `totalPrincipalUsdg()` and `totalDebtUsdg()` are reported for the **whole selected pot**, even under a market filter, and never added to per-position debt.
- `unitsOf(id)` is actual share-allocated token exposure at the pinned balance, not entry units or the desk's whole custody balance. The reviewed implementation returns zero when listing total shares are zero; otherwise virtual balances use `floor(shares * (tokenBalance + 1) / (totalShares + 1e6))`. Calling the getter avoids reconstructing obsolete entry units for rebasing/splitting tokens. Sum of current position shares is reconciled to the listing's `totalShares` before complete debt/exposure totals are published.
- Listing `notionalUsdWad` is shown as **stored entry notional**; `capUsedWad` is a separate reservation/cap quantity. Neither is current debt. The sum of current position stored notional is also compared with the listing, with the residual reported rather than silently overwritten.
- Marked real-token exposure is `floor(unitsOf(id) * min(twapPriceWad, spotPriceWad) / 10**tokenDecimals)`, summed across positions. It requires a live TWAP and positive TWAP/spot values. A nonempty unpriceable position has null marked exposure, never an invented zero. Zero token units can have zero exposure without a price. The result is USD-denominated WAD; it is not guaranteed sale proceeds, and it assumes neither perfect liquidity nor USDG dollar parity.
- The token's full `balanceOf(desk)` is reported only as custody. Virtual-share dust, unsolicited transfers and token behavior can make it differ from summed position units. Custody is not substituted for owned position exposure. Raw token units are summed only within their own token, never across symbols.

Stored entry notional, funded USDG debt, marked token exposure, cap reservations, collateral and lending-account principal are **non-additive**. The output never creates a futures-plus-margin “total OI”. Listing and `opensAllowed` remain explicit even for a delisted token that still has an outstanding loan; stale eligibility does not erase debt.

### Historical comparisons and closure claims

Compare like-for-like products, deployments, token identities, count definitions, block/time, provider capabilities and discovery/ID/event coverage before calculating a change. A funded-position count, a nondeleted-row count and an open-state count are different populations. Incomplete coverage, a changed filter or a failed read can change an observed count without proving economic activity.

A **net decline in position count does not establish an exact number of closures**. New positions can offset exits, pending requests can be cancelled or funded, and state transitions can change membership in the selected count. To attribute closures, compare position-level evidence across the specified blocks and inspect applicable lifecycle events/receipts and semantics with explicit interval completeness. Futures trader slots and margin IDs also have different lifecycles; do not infer identical closure behavior. Report a supported net change as such, and leave exact gross closures or their causes unresolved unless the evidence establishes them. Historical analysis may use independently authorized archive access; it is not a stale substitute for a fresh current snapshot.

### Position ID to token: decode the ABI, not address patterns

The [published Desk ABI](../assets/contracts/netlong-margin-desk.json) defines `positions(uint256)` (`0x99fbab88`) as one **static** `Position` tuple. The [runner interface](../assets/analytics/netlong-interface.json) uses the same field order. This is the return layout for that evidenced deployment/interface, not a universal struct layout or proof of an unknown implementation.

Offsets below are zero-based bytes from the start of decoded `eth_call` return data, after removing `0x`. Each field occupies a full 32-byte ABI word regardless of its declared integer width; Solidity storage packing does not apply. There is **no leading dynamic-tuple offset**. The complete return is 20 words / 640 bytes.

| Word | Byte offset | Field | ABI type |
|---|---|---|---|
| 0 | 0x000 | trader | address |
| 1 | 0x020 | token | address |
| 2 | 0x040 | state | uint8 |
| 3 | 0x060 | openedAt | uint64 |
| 4 | 0x080 | lastTouch | uint64 |
| 5 | 0x0a0 | underSince | uint64 |
| 6 | 0x0c0 | deadline | uint64 |
| 7 | 0x0e0 | marginWs | uint128 |
| 8 | 0x100 | loanUsdg | uint128 |
| 9 | 0x120 | scaledDebtWad | uint128 |
| 10 | 0x140 | shares | uint128 |
| 11 | 0x160 | entryPriceWad | uint128 |
| 12 | 0x180 | notionalUsdWad | uint128 |
| 13 | 0x1a0 | capShareWad | uint128 |
| 14 | 0x1c0 | leverageWad | uint64 |
| 15 | 0x1e0 | slipBps | uint16 |
| 16 | 0x200 | maintenanceBps | uint16 |
| 17 | 0x220 | maxPriceWad | uint128 |
| 18 | 0x240 | minProceedsUsdg | uint128 |
| 19 | 0x260 | sharesPending | uint128 |

**Synthetic ABI illustration, not a live position or deployment:** let the trader be `0x1111111111111111111111111111111111111111`, token `0x2222222222222222222222222222222222222222`, state2. The first three return words are:

```text
word 0: 0000000000000000000000001111111111111111111111111111111111111111
word 1: 0000000000000000000000002222222222222222222222222222222222222222
word 2: 0000000000000000000000000000000000000000000000000000000000000002
```

Words3–19 are omitted from this illustration, not from a valid response. The token is the rightmost 20 bytes of **word1** (return bytes44–63), not the first recognizable address anywhere in the blob. A strict ABI decoder must validate the full length, address padding and integer widths. Map the decoded token to same-block `tokenCount()`/`tokenAt(i)` discovery by exact chain-qualified address, not a ticker or byte-pattern search. The collector already performs this decode and attribution; no handwritten struct parser is needed.

A zero `trader` marks a deleted/unused slot for this collector. Nonzero-trader slots with an unknown state or non-enumerated token are coverage gaps. `loanUsdg`, `scaledDebtWad`, `shares` and stored notional are not substitutes for the separate `debtUsdg(id)` and `unitsOf(id)` getters.

## Completeness, bounds and evidence gaps

The collector permits at most 32 enumerated markets per family and 128 historical futures trader candidates per desk or 128 allocated margin position IDs. The common NetLong request budget is 750 RPC members, with the existing response-byte/event-row limits and a default 120-second whole-process deadline (maximum 600 seconds, including the serialization reserve). Increasing the deadline does not increase cardinality limits. Counts, missing ranges/reasons, partial position subtotals, failed identities and reconciliation residuals remain evidence; incomplete inventories never become complete zero totals. Historical trader/position counts can therefore exhaust bounds even for a small current book.

Aggregate fields distinguish `total` from `observed_subtotal`, each with completeness. No observed values means a null subtotal, not zero; a fully established empty book can be zero. Desk/vault reconciliation failures revoke complete futures totals while retaining observed subtotals and residuals. `--market` restricts accounting only after discovery establishes uniqueness; it does not treat the first ticker match as authoritative. Unsupported markets remain explicit. Summaries retain status, stopping reason, errors and coverage from the exact serialized full checkpoint.

Reportable aggregate `total` values and exported completion flags require both the original scoped collection/reconciliation evidence and a **confirmed pinned-block recheck**. Before confirmation, or after an identity conflict, totals are null and completion flags are false. Retained observed subtotals and market amounts carry `snapshot_valid` and `snapshot_confirmation` (`confirmed`, `unconfirmed` or `invalid`); an invalid snapshot's observations are not valid chain totals. Interim checkpoints preserve collection evidence so a later successful recheck can publish supported totals, including genuine complete zeros. Confirmation never repairs incomplete discovery, unsupported implementations or failed reconciliation.

The [reviewed collector projection](https://github.com/tomismeta/netstack/blob/5f9a9fc6db2fc07a00bdc1ef47029d790ab53df5/scripts/netstack_netlong.py#L121-L160) pins this output behavior to source reviewed October 12, 2026 UTC. It is evidence for Netstack's serialization rules, not a NetNet contract's behavior or a current chain observation.

Missing or denied RPC access, unavailable historical code/logs, unsupported runtime/configuration, missing symbols, stale token pricing and incomplete reconciliation are distinct gaps. No fallback uses package balances, UI/demo rows, a previous snapshot or off-chain guessed symbols; the collector never automatically switches providers. Packaged executable ABIs contain only the exact view functions/events required by this collector; the broader descriptive contract catalogs do not expand its call permissions. Those helper boundaries do not prohibit independently authorized supplemental research, additional interfaces or deliberate archive work with established semantics and separate provenance. Never weaken helper checks or use another path to evade denial.

Regression cases in `tests/test_netlong.py` cover accounting, real event-scanner integration, discovery/ambiguity, runtime and immutable consistency, stale pricing, bounds, pending versus funded debt, reconciliation failures, terminal permission denial and exact summary serialization. Isolated synthetic scenarios are not live-chain verification.

## Revenue and house proceeds

The bundled `netlong` command collects **exposure**; `netlong-revenue` collects supported **bounded revenue evidence**. Neither is a universal historical profit ledger. A revenue question authorizes relevant read-only discovery, archive state, logs, receipts and public implementation research under the same access rules. Do not answer “unsupported” solely because a quantity is outside the helper's fields, weaken safety checks, or execute settlement/routing to manufacture evidence. For cross-product consolidation use [protocol revenue analytics](protocol-revenue-analytics.md).

### Bounded revenue evidence collector

For an explicit inclusive interval, start the guarded collection before writing supplemental RPC code:

```sh
python3 -I -B scripts/analytics.py netlong-revenue \
  --from-block FIRST_BLOCK --block LAST_BLOCK --chunk-blocks 10 \
  --deadline 120 --detail summary \
  --output /absolute/research/netlong-revenue.json
```

Replace the boundary placeholders with the requested positive starting block and closing block; opening state is `FIRST_BLOCK-1`. Choose the deadline within the host's whole-answer allowance and leave time to report the result. One pass shares its transport, resource/deadline accounting and checkpoints across the current selected vault, dynamically discovered desks, margin program, supported boundary getters and scoped token transfers. It does not reset the budget for each emitter. Keep the full checkpoint outside the installed skill; summary output supplies observations and gaps for the answer, not just a file-written acknowledgment.

Read the returned scope and confirmation before using a subtotal. Both boundary hashes, relevant discovery/implementation/binding checks, served log ranges, receipts and reconciliation matter. Unknown deployments, missing reads, registry changes, unconfirmed boundaries and residuals remain explicit. Endpoint registries do not prove no transient market existed between them. A successful selected-event scan is not complete economic history or deployment-to-date revenue.

Separate assessed fees, receipt-confirmed router flows, balance/claim deltas and scoped Treasury receipts. Vault equity growth is not automatically LP profit: subscriptions, withdrawals, liabilities and ownership matter. Pot debt/equity growth is not cash interest received. Neither burns nor fee-router inventory are Treasury revenue. Keep wsNET, USDG and NET in their native units; no combined fees-plus-LP or cross-asset “total revenue.” Supplemental research remains available for other generations, unnamed router events/modes, beneficial ownership, carry decomposition and other uncovered economics.

The full output and summary include `event_coverage` by emitter and an explicit unmeasured `router_disposition`. `not_collected` with a null event count means **unknown activity**, not unused topics or zero processing. Scoped router token transfers—even no outgoing transfers or unchanged inventory—do not by themselves establish that processing, unwrap, unstake or NET burning was absent. Do not contradict an unknown disposition with an absolute absence claim elsewhere in the answer. Named-event coverage, transfers and operation/supply semantics are separate; any stronger inference needs matched implementation/effect evidence, the exact covered entities and explicit assumptions. Investigate that surface with suitable authorized evidence when relevant rather than silently turning null into zero.

### Scope the entity and measure without unnecessary clarification

In a NetLong conversation, “the house” ordinarily means the selected **NetLong futures liquidity vault** and its LP underwriting result; show that assumption and separately include the margin lending account when the question covers all NetLong. The vault is **not PredictHouse, THE BOOK, the Treasury or the Sleeve**. The margin lending account is another balance sheet, not a futures desk. Do not require clarification merely because other products also use “house.” For an unqualified cumulative question, investigate lifetime through the fresh endpoint unless context supplies another period, matching [protocol revenue accounting](protocol-revenue-analytics.md). A shorter served interval must be labeled as a bounded subtotal with lifetime coverage unresolved, not silently substituted for the requested total.

Keep these columns separate by product, asset and recipient:

| Measure | Futures | Margin |
|---|---|---|
| Earned/assessed activity | Opening/closing fees, carry settlement components, penalties | Executed opening/closing fees, realized interest and penalties |
| Accrual / outstanding obligation | Open-position carry liability/credit; dated and ADL profit claims | Indexed borrower interest, principal, lender withdrawal obligations |
| Actual cash/token receipts | wsNET received by fee router, LP/trader/reserve inflows separately | USDG received by fee router/pot; seized wsNET separately |
| Financing/capital proceeds | LP subscriptions, trader deposits, donations, reserve funding | Lender deposits, borrower margin; principal repayments are asset recovery |
| Distribution / use | Router unwrap/unstake/NET burn; LP redemption or trader payment | NET purchase/burn, insurance allocation/use, lender withdrawals |
| Net economic result | LP-equity movement adjusted for capital and accounting transitions | Lender-equity movement adjusted for capital, impairment and valuation |

These are different views of overlapping flows, **not additive revenue categories**. LP net result can already include the retained effect of fees/carry/trader PnL; never add gross fees to it again. LP/lender proceeds can be material without being protocol earned revenue. Owed trader profits and queued lender/LP claims are not cash receipts.

### Evidence and fresh interval procedure

Implementation evidence is the [futures review](netlong-futures-contracts.md), [margin review](netlong-margin-and-lose-contracts.md) and their exact catalogs, based on the [publisher entry](https://trading.netnet.capital/assets/index-BViJKZuW.js) and explorer-indexed runtimes observed October 10, 2026. Supplemental router disassembly was analyzed October 12 from those retained bytes. These are neither independently compiled source nor current block-pinned financial observations. A static explorer read succeeded for the margin router; a separate programmatic request returned HTTP403 and stopped. No revenue balances/history are packaged.

Use `netlong-revenue` first for its covered boundary/event/receipt/transfer plan. For an additional named-event/emitter scope, use the [bounded `receipts` helper](integrations.md#bounded-receipt-research) with its catalog and explicit interval. It projects descriptive catalog events to standard ABI and reuses guarded collection. Unnamed router topics and uncovered economic/ownership reconciliation still require their evidenced supplemental procedures. A partial result is useful evidence to report, not a reason to silently abandon the answer or declare revenue unsupported.

Build any supplemental read plan **from the remaining gaps**, rather than reimplementing the helper's completed work. Read the relevant recipe/catalog sections rather than repeatedly loading whole manuals or reverse-engineering a helper that already covers the selected inputs. The exposure helper's getter list is not the revenue read plan: use the [reviewed supplemental selectors](#safe-read-plan-and-native-units) through suitable authorized tooling without altering helper permissions. Keep supported inclusive chunk sizes for supplemental router/Transfer scans too; a raw `_rpc("eth_getLogs", ...)` call does not inherit `Context.logs` chunking. Save full results and return the needed boundary values, deltas and coverage to the model in the same tool result, or read that checkpoint before synthesis. A file-written acknowledgment alone does not supply those values, and matching balance deltas corroborate a receipt without proving complete gross flows or net profit.

1. Select chain 4663, generation, asset and interval `(B0, B1]`. Read and retain both block hashes/timestamps, provider provenance, code identities and historical-read capability. For an inclusive log interval `[A,B]`, start state is `A-1`, not `A`. If predeployment, establish code absence/creation boundary before treating opening inventory as zero. State and logs from different snapshots cannot be silently joined.
2. Discover **all** futures `deskCount()`/`deskAt(uint256)`/`desks(address)` and margin `tokenCount()`/`tokenAt(uint256)` at both ends. Also retain interval event emitters/token fields and any registration/listing changes: an end-only roster can miss an earlier entity. Verify bindings and runtime identities. Unknown models and delisted tokens remain explicit. Publisher BTC/ETH/SOL/NET labels are not a lifetime coverage limit; superseded deployments need their own investigation.
3. Query explicit emitter/topic filters in provider-supported chunks, paginate without holes and record covered/missing ranges. A provider allowing only ten blocks per `eth_getLogs` call needs chunks of at most ten inclusive block numbers, not a claim of whole-history coverage from ten blocks. Stop on denial; select larger research scopes only within authorized capability. Record `(chain, blockHash, transactionHash, logIndex)`, deduplicate and order receipts. Independently authorized transfer-index discovery follows the [shared period ledger](protocol-revenue-analytics.md#shared-period-ledger); it does not replace economic-event coverage. Recheck **both opening and closing boundary hashes** after collection; changed hashes invalidate the joined interval and unavailable rechecks leave it unconfirmed.
4. Join successful transaction receipts for every classified event and relevant token transfer. An RPC log address is the **emitter**, not necessarily the revenue owner. Margin SettleLib uses `DELEGATECALL`; its settlement logs are emitted at the Desk, not the library address. Verify library binding/code rather than scanning its address for Desk sales.
5. At both ends read accounting getters and token `balanceOf(address)` for vault, pot, both routers and any claimed recipient. Reconcile each token separately: `endBalance - startBalance = receipts - sends + independently evidenced mint/rebase/other balance adjustments`. A residual is missing reconciliation, never automatically a fee, interest or profit. Receipt transfers are especially important for taxed tokens and internal custody movements.
6. Publish complete interval totals only for reconciled, complete scope. Otherwise show **observed bounded subtotals**, missing markets/ranges/receipts, unresolved components and null values. A zero router balance does not mean no revenue; old inventory can be spent during a period with no new fees. An event-complete ten-block subtotal is not deployment-to-date revenue.

### Exact event decoding and attribution

The linked catalogs contain descriptive event records with canonical signatures, topic hashes and indexed flags, **not ready-to-pass standard JSON ABI entries**: their `events` records omit `"type": "event"`. Passing those raw records to `Context.logs` causes `Requested events are not present in ABI`; that is an interface-shape failure, not empty chain history.

`Context` is a constrained collector utility, **not a general unrestricted RPC adapter**. Supplying a correctly shaped ABI does not expand its method/function/target permissions or supported types. Keep those checks intact; additional independently authorized research uses appropriate tooling under the same access rules.

For supplemental research, construct a fresh standard ABI entry for each evidenced named event: retain the exact `name`, set `"type": "event"`, retain the evidenced boolean `anonymous`, and project `inputs` in declaration order with each input's `name`, exact ABI `type` and boolean `indexed`. Preserve recursive `components` (names/types and further components) for tuple and tuple-array inputs; never flatten tuples, drop array dimensions or infer missing indexed flags. Keep catalog signatures, topics and evidence metadata separately. For example, the catalog's `Cancelled` becomes:

```json
{"name":"Cancelled","type":"event","anonymous":false,"inputs":[{"name":"commitId","type":"uint256","indexed":true},{"name":"trader","type":"address","indexed":true},{"name":"returnedWs","type":"uint256","indexed":false}]}
```

Recompute the canonical signature from that shape (canonical integer types, recursively expanded tuple components, array suffixes preserved; no names or `indexed` keywords). For a nonanonymous event, compute Ethereum **Keccak-256**, not SHA3-256, and require equality with the catalog signature/topic0 and the deployed log's topic0. `Cancelled(uint256,address,uint256)` must hash to `0xaa17fdf5ffb610a4cc0887f35c13c501975a370005080f68441055871952eb81`. A matching topic alone does **not** verify indexed placement: check applicable deployed runtime/source and receipt evidence for topic count/order and exact data layout at the emitter/generation in question. Distinguish `publisherABI` evidence from runtime-backed layout evidence; a publisher fragment or successful syntactic decode is not proof of deployed semantics. Conflicts remain unresolved, not silently patched to fit.

For the static events below, each nonindexed data field occupies one 32-byte word in listed order; require the exact data length. Indexed arguments occupy topics1 onward in indexed-field order, so topic count is one plus the indexed-field count. Signed values require signed decoding; narrower integers and address padding require validation. No dynamic tuple offset is present in these rows. Other events need their actual tuple/dynamic ABI layout; indexed arrays/tuples/dynamic values are hashes, not decodable values. Anonymous events have no signature topic0 and are not supported by `Context.logs`; unnamed runtime topics cannot be converted by inventing an event name. Use a suitable independently authorized read/decoder when needed, without widening packaged helper allowlists or weakening their checks.

| Emitter / catalog | Canonical event signature | Indexed fields | Nonindexed data words, in order |
|---|---|---|---|
| Discovered futures desk ([stream](../assets/contracts/netlong-futures-btc.json), [NET](../assets/contracts/netlong-futures-net.json)) | `Filled(uint256,address,bool,uint256,uint256,uint8,uint256,uint256)` | commitId, trader | isLong, sizeUsdWad, priceWad, rung, marginWs, feeWs |
| Futures desk | `Closed(address,uint8,uint256,uint256,uint8,int256,int256,uint256,address)` | trader, by | reason, sizeUsdWad, priceWad, rung, pnlUsdWad, pnlWs, returnedWs |
| Futures desk | `CarryAccrued(bool,uint256,int256,int256)` | none | longsPay, rateWad, carryLongWad, carryShortWad |
| Futures desk, where runtime supports it | `MarginCalled(address,address,uint256,uint256,uint256,uint256)` | trader, caller | priceA, priceB, penaltyWs, rebateWs |
| [Futures vault](../assets/contracts/netlong-futures-vault.json) | `Settled(address,address,int256,uint256,uint256,uint256,uint256,uint256)` | desk, trader | pnlWs, feeWs, penaltyWs, paidWs, deferredWs, adlClaimWs |
| [Margin Desk](../assets/contracts/netlong-margin-desk.json) | `Opened(uint256,address,address,uint256,uint256,uint256,uint16,uint16,uint256,uint64)` | id, trader, token | marginWs, leverageWad, loanUsdg, slipBps, maintenanceBps, maxPriceWad, deadline |
| Margin Desk | `Bought(uint256,address,address,uint256,uint256,uint256,uint256,address)` | id, trader, token | spendUsdg, units, fillPriceWad, feeUsdg, by |
| Margin Desk | `Sold(uint256,address,address,uint8,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,address)` | id, trader, token | reason, units, proceedsUsdg, feeUsdg, penaltyUsdg, debtRepaidUsdg, seizedWs, shortfallUsdg, returnedUsdg, by |
| Margin Desk | `MarginReturned(uint256,address,uint256)` | id, trader | ws |
| Actual asset token, not vault/router | `Transfer(address,address,uint256)` | from, to | value |

`Transfer` topic0 is `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`. Validate token semantics as well as that topic. A NET transfer to zero can corroborate a burn under the reviewed NET implementation; an unrelated token's zero-address log alone is not equivalent proof.

The vault `Settled` row is **not desk-only indexed**. Independently fetched successful receipt [0x206d5862…41c7a0](https://robinhoodchain.blockscout.com/tx/0x206d586246ff1d4c8f1aac7a4dc97c87d6cdeb21016af714b76214183041c7a0), block 86749326/log index 4, has topic0 plus desk plus trader and 192 data bytes, agreeing with the publisher ABI and reviewed runtime `LOG3` at `0x27b7`. Data word 0 is signed `pnlWs`; words 1–5 are `feeWs`, `penaltyWs`, `paidWs`, `deferredWs`, `adlClaimWs`. Do not move trader into data or shift the fee offset on an unverified report. The [vault catalog](../assets/contracts/netlong-futures-vault.json) retains block/hash/code provenance; raw receipt values remain outside the package. Candidate discovery through a bounded transfer index is not a complete settlement-log scan.

**Futures fees and carry.** Group fills/closes by emitter and vault settlements by indexed `desk`; reconcile transaction/trader/order, not just date or equal amount. `Filled.feeWs` supports opening-fee activity. Cancellations can consume reserved opening fees without a fill: include `Cancelled(uint256,address,uint256)` and receipt/state evidence, not only fills. `Settled.feeWs`/`penaltyWs` are settlement evidence to reconcile to actual router/reserve/rebate movements; do not equate a field label with unrestricted cash collection or add the same fill/settlement fee twice. Runtime caps charges by available collateral. The reviewed penalty waterfall is half to reserve, conditional caller rebate, residual plus collected ordinary fee to router; compare actual allocations, not `1% × all OI`.

`CarryAccrued` emits **indices and a rate**, not cash revenue. Reconstruct positions at settlement, including entry carry, partial-size reductions and integer signed truncation: `carryUsdWad = truncTowardZero(closedSizeUsdWad × (sideCarryWad - entryCarryWad) / 1e18)`. Larger-side index moves with skew and elapsed time; opposite side receives 90% of index movement. Positive carry has the reviewed 10% protocol-fee component at cash settlement. Neither the payer/receiver index spread nor `current OI × elapsed × advertised rate` is a realized router receipt. Separately show accrued position carry, settled trader carry, allocated protocol carry fee and actual collected wsNET where replay supports each. There is no publisher event isolating every carry-fee component: if settlement/receipt evidence cannot separate ordinary fee from carry allocation, report the combined supported amount and the unresolved decomposition.

`Closed.pnlUsdWad`, `Closed.pnlWs` and `Settled.pnlWs` are related observations, not three profits. The close path incorporates carry and asymmetric oracle conversion; do not silently call the event value pure price PnL or infer a universal event reason enum without matching runtime. Profit credited to `freeOf` is internal liability, not payment to a wallet. `paidWs`, `deferredWs`, ADL claims and later claim transfers need separate stages.

**Margin opening and closing fees.** Use executed `Bought.feeUsdg` and `Sold.feeUsdg`, not `Opened.loanUsdg` or pending loan sums. Reviewed opening fee is `floor(loanUsdg × 25 / 10000)` and sale settlement deducts 25bps from proceeds. Reconcile each event to the actual USDG transfers in that receipt. `Sold` includes token and ID even after the position is deleted; current `positions(id)` alone cannot recover a closed token's interval revenue. Per-token event fee/penalty attribution is therefore possible with complete event coverage. Runtime-derived proportional debt/seized collateral and event proceeds are non-additive balance-sheet movements.

**Accrued versus realized interest.** At each boundary collect pot `totalDebtUsdg()` and `totalPrincipalUsdg()`, and full discovered position `debtUsdg(id)` with ID/token mappings where supported. Their difference is outstanding indexed interest under this model, not interest received during the interval. A change in that difference combines new accrual, repayment and debt retirement. `Sold.debtRepaidUsdg` is not an interest-only event. Derive realized interest only from supported repayment accounting/replay or exact pot-to-router allocations joined to settlements; do not label every USDG transfer to the pot as interest.

The reviewed realization split is 20% fee router, 10% USDG insurance, remainder lender interest, with integer rounding. The lender equity getter projects net interest; projection is not spendable cash. A pot-wide fee-router interest receipt can be established without proving per-token attribution. If one receipt settles multiple IDs, allocate only when ordered call/event evidence disambiguates each repayment; otherwise retain an unattributed pot-level bucket. Absence of a supplied pot event ABI is not proof that the runtime emits no events, nor permission to guess them.

**Insurance and shortfall.** Reviewed liquidation penalty allocates `floor(penalty / 2)` to pot insurance and remainder to fee router. Track insurance ledger credits separately from token receipts: insurance USDG is held inside pot custody, not necessarily transferred to another account. `Sold.shortfallUsdg` is settlement shortfall evidence, not automatically final lender loss. Uncovered debt consumes USDG insurance, then credit-valued insurance wsNET via rounded-up conversion, then lender equity. Reconcile start/end `insuranceUsdg()`/`insuranceWs()`, debt retirement, seized wsNET and every independently established insurance contribution/use. A decline in insurance can be absorption; an increase can be allocation, not earnings. Without full waterfall evidence leave final lender loss unresolved.

### Actual router receipts, burns and downstream recipients

- **Futures router** `0x56a8816132579c6c080e65147682DA2d6D20efb0`: fee receipts are wsNET18. Its reviewed immutable mode is false; active `route()` unwraps wsNET, unstakes sNET and burns NET9. Track wsNET start/in/out/end, conversion receipts and NET burn separately. Preexisting inventory/donations prevent automatic attribution of a processed batch to the current period's markets. The dormant USDG-to-Treasury path is not an actual distribution.
- **Margin router** `0x56AE9Dd336525A9C29a10E80963cCbCaF4b3CfA0`: receives USDG6, buys NET and burns measured NET output under its false immutable mode. Its processing selector `0x15ce45a2` is write-capable and **not** a safe view; no source function name is established. USDG spent and NET burned are uses of collected fees, not a second earned-revenue line. Conversion fees/tax/slippage can separate gross spend from actual NET output.
- The [futures router catalog](../assets/contracts/netlong-futures-fee-router.json) records unnamed runtime `LOG1` topic `0x1e9301528d148faec4e5a2a81ccbc4f4a66f801001fe2cc7437c6a8d17da9fc9` at PC `0x0a05`; the [margin router catalog](../assets/contracts/netlong-margin-fee-router.json) records `0xf19b38dc0f9599107b200aae774b4b4cb8248bc622a4a23f844799029efd0453` at `0x0ebe`. Each has five data words (160 bytes), no indexed argument beyond topic0. Margin word4 is caller. Other word names and both canonical signatures remain unresolved. Use these as processing witnesses and reconcile token logs; **do not fabricate `Routed(...)` ABIs or numeric meanings**. Compiler metadata bytes containing `LOG` opcodes are not executable event evidence.
- Attribute actual Treasury/Sleeve receipts only from the **destination's token transfer evidence and transaction cause**, with beginning/ending recipient inventory if claiming net receipts. The selected router modes do not directly send their fees there. NET tax arising on a swap leg can feed a separate tax mechanism; prove that path and classify it once. LOSE levy conversion can send USDG to Sleeve, but is a distinct LOSE-tax stream, not another booking of NetLong realized trading loss or initial LOSE allocation. When funds mix, report the supported destination and product-unattributed amount instead of fabricating per-market tracing.

A complete zero **scoped router-to-Treasury remittance** is not zero Treasury revenue from every route: tax conversion, other products, historical routers and indirect paths require their own discovery and attribution. Lifetime receipt/processing flows also differ from the endpoint router inventory, LP/lender claim or available capacity; none substitutes for another.

### Vault/LP and lender net result

Read futures `balanceWs`, `totalFreeWs`, `totalLockedWs`, `clearingReserveWs`, `totalOwedWs`, signed `equityWs`, `totalShares`, `sharePriceWad`, `subscribedWs`, `pendingRedeemWs`, `adlEpoch` and `adlUnpaidWs` at both boundaries. The reviewed equity is physical wsNET less trader/free/locked, clearing, funded-claim and reserved-redemption liabilities. `pendingRedeemWs()` is **matured shares at floating share price**, not the reserved-redemption cash bucket. The supplied getter set does not expose every liability separately; report residuals rather than forcing equality with that proxy. Unfunded ADL episodes are not all included in `totalOwedWs()`.

Use vault events `Subscribed(address,uint256,uint256)`, `Donated(address,uint256)`, `RedeemRequested(address,uint256,uint64)`, `RedeemMatured(address,uint256,uint256)`, `RedemptionsPaid(uint256,uint256)`, `RedeemClaimed(address,uint256)`, `OwedPaid(address,uint256)`, `AdlClaimRecorded(uint64,address,uint256)`, `AdlClaimsPaid(uint64,uint256,uint256)`, `AdlClaimed(address,uint256)` and `AdlEpisodeClosed(uint64,uint256)` from the exact vault catalog. Reconcile reserve funding and other uncataloged movements from receipts/state rather than silently excluding them.

The useful bridge is **`LP equity change − equity-increasing external capital + equity-decreasing capital distributions`**, with donations/recapitalization, reserve-to-equity changes, claim recognition/writeoffs and rounding shown explicitly. Identify when equity actually changes: redemption funding/share burning can reduce equity before later `RedeemClaimed` transfers already-reserved cash. Adding both as distributions double-counts. Trader deposits/withdrawals normally move physical assets and trader liabilities together, not LP earned revenue. Funding the excluded clearing reserve is not the same as subscribing LP capital. Until this bridge reconciles, call it an equity movement/partial net-result bridge, not a fully established trading-profit total.

For margin, read `cashUsdg`, `idleUsdg`, `insuranceUsdg`, `heldWs`, `insuranceWs`, `heldWsValueUsdg`, `totalPrincipalUsdg`, `totalDebtUsdg`, `owedUsdg`, `equityUsdg`, `totalShares` and `sharePriceWad`. Its equity includes loan assets, lender-net projected interest and lender-owned seized-ws credit value, less unfunded dated withdrawals; it is not just USDG cash. Lender deposit/withdrawal and dated-claim transitions require receipt/state accounting because the supplied pot ABI contains no events. The equity getter saturates at zero, so two zero readings do not prove no further impairment. USDG-principal recovery is not income, seized wsNET is not already sold USDG, and allocated insurance is not also lender capital.

**Attribute ownership before calling a class result protocol revenue.** Whole-vault LP and whole-pot lender results include outside capital. Discover the relevant account roster from vault subscription/redemption events; for the pot, combine asset transfers with source-decoded historical deposit/withdraw/claim inputs or authorized traces rather than inventing pot events. Read each established beneficiary's `sharesOf(address)` and applicable `redemptionOf(address)` / `withdrawalOf(address)` claims at the interval boundaries, then replay contributions, distributions, ownership changes and claim transitions using the exact share-valuation rules. An account bridge is closing attributable claim minus opening claim minus contributed capital plus distributed capital, with marks, fees and losses separately reconciled; do not count active shares and the same redeemed claim twice. Today's ownership fraction cannot allocate earlier or lifetime earnings. If roster, beneficial ownership or claim history is incomplete, report the supported LP/lender-class result but keep protocol-owned fraction and attributed amount unknown/unattributed.

An LP share-price change is return per remaining share, not total house dollars; supply changes, virtual offsets, donations, claims and valuation can all matter. Preserve a marked-economic-result view separately from cash realization. No supported model here turns gross fees into net profit without costs, losses and liabilities.

### Safe read plan and native units

After identity/binding discovery, the following exact zero-argument selectors are suitable supplemental `eth_call` reads at **both** boundary blocks; all outputs are one 32-byte word unless noted. They do not authorize mutating calls. Full tuple layouts remain in the existing catalogs.

| Emitter | Function → selector | Output |
|---|---|---|
| Futures vault | `balanceWs()` → `0xa7363cb5`; `totalFreeWs()` → `0xba928ccf`; `totalLockedWs()` → `0xdcac5049`; `clearingReserveWs()` → `0x2ad80df3`; `totalOwedWs()` → `0xd8182b5d` | uint256 wsNET18 |
| Futures vault | `equityWs()` → `0xd28acb13`; `pendingRedeemWs()` → `0x34c9d205`; `adlUnpaidWs()` → `0x9875fd05` | int256 wsNET18 for equity; uint256 wsNET18 otherwise |
| Vault / pot | `totalShares()` → `0x3a98ef39`; `sharePriceWad()` → `0x2770c503` | uint256, separately identified share conventions |
| Futures desk | `carryLongWad()` → `0xb60eda80`; `carryShortWad()` → `0x5a67481d`; `lastCarryAt()` → `0x599bf762` | int256, int256, uint64 respectively |
| Margin pot | `cashUsdg()` → `0x103ec6d0`; `idleUsdg()` → `0x39883d54`; `insuranceUsdg()` → `0xe129a2fd`; `owedUsdg()` → `0xd52e6da8`; `equityUsdg()` → `0x40f73c30` | uint256 USDG6 |
| Margin pot | `totalPrincipalUsdg()` → `0x426006f7`; `totalDebtUsdg()` → `0x78232a68`; `heldWsValueUsdg()` → `0x3210b40c` | uint256 USDG6 |
| Margin pot | `heldWs()` → `0x84d3aa1a`; `insuranceWs()` → `0x453ed186` | uint256 wsNET18 |
| Margin pot | `borrowRateWad()` → `0x791b2d89`; `wsCreditPerWsWad()` → `0xb918c95a` | uint256 WAD rate / credit valuation, not received USDG |
| Actual token | `balanceOf(address)` → `0x70a08231`; `decimals()` → `0x313ce567`; `totalSupply()` → `0x18160ddd` | uint256, uint8, uint256 |

Parameter-bearing discovery signatures/selectors: futures `deskCount()` `0x47d0a311`, `deskAt(uint256)` `0x1f0113f5`, `desks(address)` `0x957cfb9c`; margin `tokenCount()` `0x9f181b5e`, `tokenAt(uint256)` `0x92a91a3a`, `positions(uint256)` `0x99fbab88`, `debtUsdg(uint256)` `0x93f8bf36`. Append canonical 32-byte argument words, not packed storage fields. Futures `positions(address)` is `0x55f57510`; carry entry is word7 (`int128`), size word4 (`uint128`) of the catalog's 12-word static tuple. Margin uses the 20-word layout above. Do not extrapolate either to unknown runtimes.

Read only already-reviewed immutable router surfaces for this state/receipt procedure: futures `wsNet()` `0xd52014e3`, `sNet()` `0x1adb8eb6`, `net()` `0xc2fff4a5`, `usdg()` `0xf5b91b7b`, `treasury()` `0x61d027b3` return addresses. Unnamed but body-reviewed no-argument mode selectors are futures `0x63f7324a` and margin `0x3395b222`, returning one bool word. Keep their names null and require the exact catalog runtime identity before using these interpretations; changed code needs new research. Do not execute routing, accrual, claims, report posting or swaps to manufacture historical receipts. Separately labeled isolated non-broadcasting simulations remain permitted under the [guardrail](guardrail.md), but simulated effects are not observed revenue or proof of actual payment.

Native accounting is **wsNET18, NET/sNET9, USDG6**, with metadata checked at the selected block. “Native units” does not mean chain-native gas currency. Preserve integer raw units and show decimals; USD-denominated WAD notional is not USDG cash. For a USD presentation, identify asset, quote source, quote block/time and conversion policy (receipt-time versus interval-end mark). Use the actual sNET index and wsNET conversion semantics, not 1 wsNET = 1 NET; distinguish floor/credit/loss/payout valuations from executable market prices. Do not assume USDG = $1. A missing historical price leaves native totals intact and USD value unavailable. Report conversion/valuation changes separately from operating earnings.

### Synthetic accounting cases (not live observations)

- **Router inventory:** opening 5 wsNET + 3 collected − 6 processed = closing 2. Current-period receipt is 3, processing is 6, and neither the closing balance nor 6 is “fees earned this period.” Without inventory provenance the 6 cannot be assigned wholly to the new markets.
- **Margin fee/interest:** an executed 1,000 USDG loan has 2.5 USDG opening fee. Separately, fully collectible realized interest of 100 USDG allocates 20 router / 10 insurance / 70 lender. Total borrower interest is 100, not 200 after adding allocations. A pending loan has no executed opening fee; accrued-but-unpaid 100 is not the realized case.
- **LP bridge:** opening equity 100 wsNET, subscription 50, donation 7 and equity-stage redemption distribution 20, ending equity 142 gives adjusted residual `142 − 100 − 50 − 7 + 20 = 5` wsNET. This is a net-result candidate only after other liability/reserve transitions reconcile. A later transfer of the same reserved redemption cash adds no second 20.
- **Insurance shortfall:** if independently evidenced uncovered debt is 12 USDG, insurance absorbs 5 USDG plus 3 USDG of wsNET credit and lender impairment is 4, do not book 12 as lender loss and then add 8 as another loss. wsNET credit of 3 is not three USDG received.
- **Coverage:** two successfully decoded markets plus an unsupported third yield a two-market subtotal, even if zero in both decoded markets. An unknown carry-fee split or unattributed pot repayment remains null/unattributed, not zero or pro-rata guessed.

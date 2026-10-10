# NetLong read-only market analytics

`netlong` discovers and accounts for the current selected futures vault and the separate real-token, long-only margin program. It does not submit transactions, create trade payloads, connect a wallet, or treat terminal demonstration data as chain state. LOSE awards are not open interest.

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

The default is one `latest-2` snapshot. `--block BLOCK` selects an explicit nonnegative block. All state and code calls use that block; historical event discovery ends there. The common collector checks the pinned block hash again after collection. A result without a confirmed recheck is not confirmed chain evidence. The only RPC is the package's fixed HTTPS Robinhood mainnet endpoint, with chain-ID, public-DNS, no-proxy/no-redirect, request, response, retry and walltime controls. A permission denial terminates retrieval; no alternate endpoint is attempted. On 2026-10-10 a separate integration accessibility probe returned HTTP 403: this is a live-verification gap, not evidence of zero OI, and not permission to retry through another route. The recipes above describe supported operation when access is legitimately available; do not run them to evade an outstanding denial.

Stdout is JSON, with exact raw decimal strings and formatted quantities. `--detail summary` omits getter-level reads and individual positions, retaining accounting, coverage, errors and implementation checks. `--detail full` is the default. `--output` preserves atomic full partial/final checkpoints outside the installed package even when stdout uses summary; existing common output path and symlink protections apply. No results are written into the package. Exit 0 means the requested collection completed, 2 means partial/blocked, and 1 means invalid arguments/fatal initialization. A completed last-posted-mark calculation is not a promise that its price is fresh or executable.

## Discovery and implementation identity

Canonical records are referenced through `assets/analytics/netlong-routes.json`, not copied address inventories in the collector. The interface's publisher evidence is the complete October 10 trading entry bundle, identified by URL and SHA-256 in `assets/analytics/netlong-interface.json`. Code identity evidence uses separately recorded explorer runtime hashes. These are independent analysis assets, not a NetNet publication, verified Solidity, or an audit.

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

`nextPositionId()` allocates contiguous IDs starting at 1. Read bounded IDs in `[1, nextPositionId)` including deleted slots; do not rely on a hardcoded trader list or infer ownership from terminal screenshots. Supported observed states are 1 pending-buy, 2 open and 3 pending-sell. An unrecognized nonzero state or a non-enumerated position token is missing coverage, not an inferred open position.

For each current nonzero-trader slot:

- `debtUsdg(id)` is the actual pinned indexed debt, including accrued interest, in six-decimal USDG. Do not sum `loanUsdg` fields as funded current debt. The reviewed getter returns zero for zero scaled debt; borrowing occurs on execution of the pending buy. The lending account's independent `totalPrincipalUsdg()` and `totalDebtUsdg()` are reported for the **whole selected pot**, even under a market filter, and never added to per-position debt.
- `unitsOf(id)` is actual share-allocated token exposure at the pinned balance, not entry units or the desk's whole custody balance. The reviewed implementation returns zero when listing total shares are zero; otherwise virtual balances use `floor(shares * (tokenBalance + 1) / (totalShares + 1e6))`. Calling the getter avoids reconstructing obsolete entry units for rebasing/splitting tokens. Sum of current position shares is reconciled to the listing's `totalShares` before complete debt/exposure totals are published.
- Listing `notionalUsdWad` is shown as **stored entry notional**; `capUsedWad` is a separate reservation/cap quantity. Neither is current debt. The sum of current position stored notional is also compared with the listing, with the residual reported rather than silently overwritten.
- Marked real-token exposure is `floor(unitsOf(id) * min(twapPriceWad, spotPriceWad) / 10**tokenDecimals)`, summed across positions. It requires a live TWAP and positive TWAP/spot values. A nonempty unpriceable position has null marked exposure, never an invented zero. Zero token units can have zero exposure without a price. The result is USD-denominated WAD; it is not guaranteed sale proceeds, and it assumes neither perfect liquidity nor USDG dollar parity.
- The token's full `balanceOf(desk)` is reported only as custody. Virtual-share dust, unsolicited transfers and token behavior can make it differ from summed position units. Custody is not substituted for owned position exposure. Raw token units are summed only within their own token, never across symbols.

Stored entry notional, funded USDG debt, marked token exposure, cap reservations, collateral and lending-account principal are **non-additive**. The output never creates a futures-plus-margin “total OI”. Listing and `opensAllowed` remain explicit even for a delisted token that still has an outstanding loan; stale eligibility does not erase debt.

## Completeness, bounds and evidence gaps

The collector permits at most 32 enumerated markets per family and 128 historical futures trader candidates per desk or 128 allocated margin position IDs. The common NetLong request budget is 750 RPC members, with the existing response-byte/event-row limits and a default 120-second whole-process deadline (maximum 600 seconds, including the serialization reserve). Increasing the deadline does not increase cardinality limits. Counts, missing ranges/reasons, partial position subtotals, failed identities and reconciliation residuals remain evidence; incomplete inventories never become complete zero totals. Historical trader/position counts can therefore exhaust bounds even for a small current book.

Aggregate fields distinguish `total` from `observed_subtotal`, each with completeness. No observed values means a null subtotal, not zero; a fully established empty book can be zero. Desk/vault reconciliation failures revoke complete futures totals while retaining observed subtotals and residuals. `--market` restricts accounting only after discovery establishes uniqueness; it does not treat the first ticker match as authoritative. Unsupported markets remain explicit. Summaries retain status, stopping reason, errors and coverage from the exact serialized full checkpoint.

Missing or denied RPC access, unavailable historical code/logs, unsupported runtime/configuration, missing symbols, stale token pricing and incomplete reconciliation are distinct gaps. No fallback uses package balances, UI/demo rows, a previous snapshot, off-chain guessed symbols or an alternate provider. Packaged executable ABIs contain only the exact view functions/events required by this collector; the broader descriptive contract catalogs do not expand its call permissions.

Regression cases in `tests/test_netlong.py` cover accounting, real event-scanner integration, discovery/ambiguity, runtime and immutable consistency, stale pricing, bounds, pending versus funded debt, reconciliation failures, terminal permission denial and exact summary serialization. Isolated synthetic scenarios are not live-chain verification.

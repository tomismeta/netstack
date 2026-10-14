# THE BOOK contract evidence

## Exact generation and source boundary

Resolve chain **4663** through [book-routes.json](../assets/analytics/book-routes.json), never a similarly named Predict/House contract. SportsBookDesk is `0x3174dE69a84c53F82F6B6Dca5C64E705cFFe8Dd6`; SportsBookZap is `0xC866E4f53f1439d85171a06395ce37b887D16Fa1`.

On October 10, 2026, static discovery from [PLAY](https://play.netnet.capital/) led through `index-r5d6-Bbh.js` and `book-entry-B32Mj9Na.js` to the [current publisher adapter](https://play.netnet.capital/assets/sportsbook-live-BuQ1LO4q.js). Downloaded code was parsed as text, **not executed**. The complete supplied Desk literal contains **56 functions, 18 events, 28 errors and one constructor**. The Zap literal contains **12 functions and nine errors**, but **no constructor or events**. Full descriptive catalogs:

- [SportsBookDesk](../assets/contracts/sports-book-desk.json)
- [SportsBookZap](../assets/contracts/sports-book-zap.json)
- [Hashes, literal ranges and dispatcher evidence](../assets/contracts/book-source-evidence.json)

The exact-address [Desk](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x3174dE69a84c53F82F6B6Dca5C64E705cFFe8Dd6) and [Zap](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xC866E4f53f1439d85171a06395ce37b887D16Fa1) explorer responses supplied creation and runtime bytecode, `implementations=[]` and `proxy_type=null`, **not verified Solidity or an explorer ABI**. Instruction-boundary dispatch comparisons find all 56/12 supplied function selectors and no unmatched branches in the respective dispatcher prefixes. Desk `quoteFee` uses a leading-zero selector emitted by `PUSH3`, accounted for explicitly. This is stronger than identity-only coverage, but **not source equivalence, independent chain pinning, an exhaustive decompilation or security audit**. Zap contains event-like LOG constants whose signatures/indexing are unavailable; no event ABI is invented for them.

Canonical RPC was already denied with HTTP403/error1010 in this research session. No retry, alternative RPC, fresh financial totals or current authority observation is claimed. Durable assets contain identity/source metadata only, not market/bet/transaction-history snapshots.

## Roles, permissions and dependencies

[Official Book documentation](https://docs.netnet.capital/the-book) is the controlling *publisher description*. Current ABI plus targeted runtime entry review corroborate its shape, but enforcement is not represented as a verified-source audit.

| Surface | Interpretation and permission boundary |
|---|---|
| `manager`, `grader`, `managerSleeve`, `barred` | Manager is an immutable Safe binding in the obtained runtime; grader is mutable storage and must be read afresh. The Sleeve is the house and fee recipient, not Treasury or PredictVault. Named team/Sleeve/keeper betting exclusions are publisher claims, not evidence every address was checked. |
| `open`, `cancel`, `halt`, `resume`, parameter setters, `setGrader` | Manager controls the board, halt and configurable minimum/cap/reserve rate and scorer. No line-update method appears in the obtained interface. A successful `halted` read is a current gate, not proof of activity or inactivity. |
| `grade` | Configured grader or manager posts scores; each at most99, no earlier than close+3hours. Spread and scores decide favourite/underdog/push. No decentralized sports oracle, random beacon or market-price feed decides the score. |
| `void` | Permissionless for still-ungraded market after close+72hours. Requires a transaction; neither expiry nor an empty event result automatically refunds anybody. |
| `settle`, `settleMany` | Permissionless idempotent per-bet settlement on decided markets. Claim credits internal free wsNET, not an external token withdrawal. |
| `deposit`, `depositFor`, `withdraw`, `withdrawFrom`, `approveWithdraw` | Player ledger, payer and beneficiary are distinct. Delegated withdrawal uses internal withdrawal allowance, not token allowance. Halt is documented to stop new bets/deposits, not withdrawal/settlement/grade/void. |
| `depositHouse`, `withdrawHouse`, `skim` | Contributions are capital, not earnings. Manager/Sleeve house withdrawal is limited to free cover and pays Sleeve regardless of caller. Skim assigns custody surplus to house accounting; it is not a new recipient transfer or proved revenue. |
| `wsNet`, `sNet`, `net`, `staking`, `distributor` | Immutable dependency getters appear in runtime. Wrapper/index and staking/distributor behavior still requires independent dependency evidence. Address agreement does not audit code or current permissions. |

Read-only quotes (`quoteFee`, `quoteRiskOn`, `quoteRiskOff`, `epochsUntil`) are catalogued descriptively but **not added to the runner allowlist**. All executable entrypoints above remain descriptive only; the runner has no wallet, write RPC or transaction-execution path.

## Units, odds, reservation and fees

All Desk balances, stakes, reservations, fees and payouts are **wsNET18**. Index fields use the published **sNET9 per whole wsNET** convention (index scale1e9); scores and side/result are small integers, spread is signed tenths, timestamps Unix seconds and fee/cap/rate are basis points. The collector checks wrapper decimals, preserves raw values and does not substitute USDG/USD or current-price marks for native or historical accounting.

- **Odds:** fixed spread and even money before fees. Risk-on gross debit is reduced by its placement fee; stored `betOf.amount` is treated by the client as **fee-net stake**. A win credits twice that amount, a loss zero, push/void that amount. Placement fee remains charged on push/void. Do not subtract the fee again. `BetPlaced.amount` emission basis remains separately qualified: the ABI does not itself show the emission expression.
- **Risk off:** amount is locked principal `P`, not turnover. The publisher uses realized through-grade yield `P − P × i0/i1`, clipped to the stored reserve. No yield exists merely because a placement or projection is present. Reserve is a cover budget projected at a configurable rate (documented baseline90bps per epoch) through kickoff+24hours, not the actual dividend rate. Clipping can leave excess yield with the player, so “exact original sNET” is not universal. A positive NET-unit preservation claim does not protect dollar value.
- **Fees:** documented pre-bet exposure ratio gives300bps baseline, up to600 for adding exposure and down to150 for reducing it. Rate is fixed at placement. Risk-on fee is immediate; risk-off fee is tied to realized settled yield and is zero on push/void. Grade fixes the index/outcome; per-bet settlement performs the account credit. `FeeSplit.potHalf` is an **internal house allocation**; `sleeveHalf` is an expected **external wsNET transfer**, not proof it arrived. Odd raw amounts need not divide equally. Preserve the actual two event fields rather than rounding a guessed half.
- **Rounding limits:** the runtime contains integer multiplication/division and bounded compounding paths, but no complete source was available. Do not promote a floating-point publisher formula to an exact claimable amount. The collector returns explicit attributed risk-on/push credit models and leaves decided non-push risk-off payout unknown. Exact risk-off principal protection, fee timing/rounding and claimability require verified implementation/path evidence or a separately authorized nonbroadcast simulation.
- **Cover:** open-market imbalance nets only opposite risk-on stakes as certain inflows, not potential risk-off yield. Reserved house cover also includes unpaid decided winners. `freePot` must be compared with house minus reserve without silently clamping an observed deficit. The documented per-bet cap is500bps of house capital and minimum0.0004wsNET, but current parameters require reads.

`potsOf` order remains `[housePot, reservedTotal, lockedWagers, lockedPrincipal]`. The first two **overlap**: reserve is not extra capital. `playerTotal` is free player ledger, distinct from locked stakes/principal. Custody may be compared with `housePot + lockedWagers + lockedPrincipal + playerTotal`; the residual is evidence for reconciliation, not profit or an audited solvency verdict. Grade can move losing risk-on stakes into house capital before each bet is individually settled; do not reconcile lock stock against raw placement volume.

## Zap boundary

The supplied Zap ABI identifies dependency reads, `ZAP_CAP_USDG` and four conversion writes, all excluded from execution. USDG deposit buys NET through the router, stakes and wraps into a Desk credit; sNET deposit wraps directly. USDG exit unwraps/unstakes and sells NET; sNET exit unwraps and transfers sNET. Internal Desk withdrawal allowance, token approvals, minimum-output bounds, deadline, staking warmup and exact dependency wiring matter. The documented2500USDG cap is **per call**, not a wallet/daily cap. USDG amounts are raw funding-token units, never wsNET or guaranteed dollars.

Targeted obtained-runtime paths use whole Zap intermediate sNET/NET balances in places rather than uniformly isolating transaction deltas. Do not attribute stray balances or every intermediate transfer to the current user's contribution. The USDG output path measures a recipient balance delta. This is bounded runtime evidence, not a full tax/slippage/path audit. The publisher's5% NET trading load plus pool costs on USDG entry/exit is not Book fee revenue and is not counted as Treasury receipts by this collector.

## Receipt and combined-accounting boundaries

`Settled.payout` is an internal account credit. `Withdrawn` plus wsNET receipt transfer is separate cash movement. `HouseWithdrawn` can return contributed capital and accumulated outcomes; it is not automatically fee income. Receipt-confirmed Desk-to-Sleeve or Desk-to-Treasury transfers establish token legs only within the explicitly collected Book-event transactions, not wallet balance deltas or every economic source.

The Book **house pot is already included in Sleeve RFV reporting**. This collector does not duplicate that valuation or add player escrow, reserved cover, fees, payouts or transfers to combined backing totals. Core certification has separate [block-specific evidence requirements](reserve-analytics.md#evidence-boundaries). See [fresh Book analytics](book-analytics.md) for bounds and coverage.

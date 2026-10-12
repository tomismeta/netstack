# NetLong margin, market tokens and LOSE: implementation review

Observed **2026-10-10**. This is independent Netstack analysis, not a NetNet publication, outside audit, proof of solvency or full-contract validation. It describes durable identities and conditional mechanics, **not retained balances, OI, positions, nonces or a trade ledger**. Nothing here authorizes a wallet, signature or transaction.

## Evidence boundary and catalogs

The [publisher entry](https://trading.netnet.capital/assets/index-BViJKZuW.js), SHA-256 `b62b66a56fbaa9d7b387761108e99e72633369c14f3a8ad6fda8444ba9be70bc`, was parsed as literals; it was not executed to extract contracts. Its `HUMAN-VERIFIED` labels and rehearsal/deployment diary remain **publisher assertions**. Demo `qa(...)` addresses, AINU demo symbol, mock prices and mock loans are not identities or accounting evidence.

The [address shard](../assets/addresses/contracts/netlong-margin-and-lose.json) uses existing `robinhood-<lowercase-address>` identities. CASHCAT reuses its [existing record](../assets/addresses/contracts/cashcat-climb-and-coinflip.json). Every catalog below retains every supplied ABI function, event, error and constructor, canonical signatures/selectors/topics, per-function semantics, evidence locators and precise missing coverage. Full third-party source and website archives are not redistributed.

| Contract | Address | Catalog / evidence obtained |
|---|---|---|
| MarginDesk | `0xE1685b19367E066af3e499DD4B0E51866B762c84` | [Desk](../assets/contracts/netlong-margin-desk.json): 23 published functions plus 5 runtime-reviewed getters, 4 events; indexed runtime with targeted RPC confirmation, no Solidity/full ABI |
| Lending Account | `0x068904944fCF4A18aB40cA112F385fAa430F60f2` | [Pot](../assets/contracts/netlong-margin-lending-account.json): 22 published functions; full indexed runtime, no Solidity/full ABI |
| Fee router | `0x56AE9Dd336525A9C29a10E80963cCbCaF4b3CfA0` | [Fee router](../assets/contracts/netlong-margin-fee-router.json): full indexed runtime; complete ABI/source missing |
| TWAP source | `0x2Ff4b46B6BF08ecAf0c374676b9a5baa15524311` | [TWAP](../assets/contracts/netlong-margin-twap-source.json): full indexed runtime; complete ABI/source missing |
| Route executor | `0x2D96BbF7859520Ac6EcD2987a69e334b57de9de6` | [Executor](../assets/contracts/netlong-margin-route-executor.json): full indexed runtime; complete ABI/source missing |
| Listing library | `0xA8Ad2540Af00381b8acD7e41fa6FdB7E0A1FD048` | [ListerLib](../assets/contracts/netlong-margin-lister-lib.json): all 10 dispatcher locations; full indexed runtime, source/storage-reference ABI missing |
| Settlement library | `0x39Ce3cf58d65c96c86803556e4091F735efDaB17` | [SettleLib](../assets/contracts/netlong-margin-settle-lib.json): all 6 dispatcher locations; full indexed runtime, source/storage-reference ABI missing |
| LOSE token | `0xF4D567e3C0B7b24Bd2f379db8249701A6F929E93` | [LOSE](../assets/contracts/netlong-lose-token.json): 3 published reads, 1 event; full indexed runtime, full ABI/source missing |
| LOSE distributor | `0x1DEdDa4dE44f406FD25CdD3A22ABb8e524368719` | [Distributor](../assets/contracts/netlong-lose-distributor.json): 4 published reads, 1 event; full indexed runtime, full ABI/source missing |
| LOSE/USDG pair | `0x718B03bcC00b1A585E6aA58c5d081170BEE93b6e` | [Pair](../assets/contracts/netlong-lose-pair.json): complete 34-entry ABI and source attributed to verified twin; indexed runtime equality corroborated |
| PONS | `0x39dBED3a2bd333467115dE45665cC57F813C4571` | [PONS](../assets/contracts/netlong-margin-pons-token.json): 44-entry ABI and complete explorer-returned source files |
| CASHCAT | `0x020bfC650A365f8BB26819deAAbF3E21291018b4` | [CASHCAT](../assets/contracts/netlong-margin-cashcat-token.json): 41-entry ABI and complete explorer-returned source files |
| AI / Artificial Inu | `0x2E8c31162b855A2ffa90F6F8634643Ad6F111e18` | [AI clone](../assets/contracts/netlong-margin-ai-token.json): 44-byte fixed EIP-1167 runtime; implementation ABI bound explicitly |
| AI implementation | `0x3Be8B97Fd0e713B5aBE0649Fa830223B6B4BC599` | [DopplerERC20V1](../assets/contracts/netlong-margin-ai-implementation.json): 107-entry ABI and complete source files, including Solady inheritance |
| Executor WETH/USDG bridge pool | `0x69bfaf19c9f377bb306a89aed9f6b07e2c1a8d9a` | [V3 pool](../assets/contracts/netlong-margin-weth-usdg-pool.json): 36-entry ABI and explorer-returned source files |

The shared margin oracle `0x90f5B57A7236A1447Ce786B1ebE42433e55D9fD0` belongs to the futures/shared-oracle review; do not create a second oracle identity or conflicting arithmetic convention.

### What was and was not accessible

The individual Blockscout `api/v2/smart-contracts/<address>` responses provided complete indexed creation/deployed bytecode. They did **not** return Solidity or ABI for the new margin contracts, linked libraries, LOSE token or distributor. A MarginDesk Etherscan source request returned HTTP 403; an IPFS metadata request derived from the runtime hash returned 429; the Sourcify full-match metadata path returned 404. Denied/rate-limited requests were stopped, not circumvented. The October 10 canonical RPC probe also returned 403. Separately authorized October 12 research used the host's existing configured Alchemy provider, without retrying the denied route: Desk code and five read-only getters were pinned to block **86749326**, hash `0xe732dff53a34fcd596dca76bb236df54ea36b9b2e32c9095ccb13001d020d125`, with a matching header recheck. Code matches the reviewed SHA-256; this narrow historical witness is not current permissions, complete financial state or compiler equivalence. Raw responses and transient state remain outside the package.

PONS, CASHCAT, AI implementation and bridge pool responses say `is_verified=true`, `is_fully_verified=false`. These flags are explorer assertions, not independent recompilation. LOSE pair itself says `is_verified=false`; its source is attributed to [verified twin `0xb9C67…A08`](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xb9C67A370D6c2E1426Df424E53430408aCe21A08). Separately retrieved pair and twin **indexed deployed runtimes are byte-for-byte identical**. This materially supports the pair implementation analysis, but still is not a pinned RPC/code-state or independent compiler equivalence claim.

Each runtime-only catalog inventories **every detected dispatcher**, including unnamed selectors and their entry PCs. A selector-name match is not a complete ABI, and an unknown selector is not silently deleted. For those entries the missing prerequisite is the complete source/ABI plus exhaustive path/storage-layout analysis. Source-file hashes and function-declaration line locators are retained for obtained source, without vendoring the files.

## Margin is a loan financing real spot, not a perpetual

The controlling [Margin Program documentation](https://docs.netnet.capital/net-long) reports operation beginning October 9 following October 8 deployment. Do not import the older tNET SPCX/CASHCAT futures-test program's parameters.

The product is long-only. Posted wsNET is held alongside purchased tokens, not sold to finance the purchase. The loan finances **the whole credited-margin-times-leverage purchase**, not `(leverage − 1) × margin`. Debt carries interest; there is no perpetual funding payment. NET/sNET entry adapters stake/wrap before the pending-open path; exact external adapter/tax/rounding behavior remains a dependency boundary where source was unavailable.

### Pending request, funded loan and current exposure are different

The bound publisher consumer maps state `1` to pending-buy, `2` to open and `3` to pending-sell. Unknown states must not inherit the UI's permissive `?? "open"` presentation fallback.

`open`, `openWithNet` and `openWithSNet` create a pending request and reserve cap/margin. `executeBuy` actually calls the pot's lending path. Runtime Desk PCs `0x2f00–0x3107` check state 1, deadline and fresh listing before the lending call. Opening fee is `floor(loanUsdg × 25 / 10000)`; remaining borrowed USDG buys the token. Received units are measured, TWAP minimum units and trader maximum fill price are enforced, and actual shares/scaled debt are recorded. A reverting leg reverts atomically.

Consequently:

- `loanUsdg` in a pending request is **not funded principal or OI**.
- `debtUsdg(id)` is zero if scaled debt is zero; otherwise it calls the pot's current index conversion. It includes interest and rounding, not a mark of the spot position.
- `notionalUsdWad` is stored entry/reservation accounting. Neither it nor `capUsedWad` is automatically current marked exposure.
- `token.balanceOf(desk)` is custody. It can include donations and rebase effects; it is not automatically the sum of borrower-owned units.
- `positionOf(trader, token)` is a lookup, not a complete trader registry. `nextPositionId()` supplies an exclusive upper bound for bounded ID discovery; zero/default/terminal records need explicit classification.

The five supplemental catalog getters mirror the existing executable `margin_abi`, not newly recovered publisher literal entries. `nextPositionId()` (`0x899346c7`) enters at `0x812`, reads **slot 6** at `0x818`, and returns one full uint256 through `0x462–0x46f` and `0x3c7–0x3cf`; retained creation bytes initialize slot 6 to 1 at `0x6–0xa`. The `pot`, `marginOracle`, `twapSource` and `usdg` bodies return embedded address words through the masking/32-byte return path `0x3b3–0x3cf`. Their body/return layouts and successful block-pinned calls support the named entries beyond selector plausibility. None proves dependency safety or authorizes writes.

### State 3 has a traced runtime entry, not just a publisher label

Focused analysis **2026-10-12** reused the retained **2026-10-10 [MarginDesk explorer-indexed bytes](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xE1685b19367E066af3e499DD4B0E51866B762c84)**, without another RPC request. The Desk's 24,403-byte runtime again hashes to SHA-256 `17b0806d172eab539e3fd362416666284dfb8656d2b93ec5b73e75cf4593555f` and Keccak-256 `0xa74be8a609bdb8472728ecea5b5f10b0695f5a016b80ceecec422ab2491d67e7`. This matches the reviewed generation; it is **not fresh pinned on-chain code**.

The omitted-from-publisher-ABI selector **`0x70c6cea8`** has a concrete **open state 2 → pending-sell state 3** path. Its dispatcher entry `0x0773` decodes three full calldata words at `0x4fbf` and jumps to body `0x1600`. Their runtime roles are position ID, requested token units and minimum USDG proceeds. **The source function name and canonical signature remain unresolved**: do not invent a `requestSell` ABI entry or use this analysis as transaction authorization.

The traced path:

1. Acquire the reentrancy lock at slot 8; require a nonzero recorded trader equal to `CALLER` (`0x3fcc–0x4020`).
2. Require state 2, no `underSince` checkpoint and a **nonzero minimum proceeds**, not nonzero requested units (`0x161e–0x16a0`).
3. Convert units to pending shares (`0x41e1–0x428d`). Zero units, or a request at least as large as current position units, selects all position shares. Otherwise use `floor(positionShares × requestedUnits / currentPositionUnits)` and reject a zero rounded result. Current units use the balance/virtual-share formula below.
4. For `B = keccak256(abi.encode(id, uint256(4)))`, `SSTORE` at **`0x16d2`** writes `(oldWord & ~(0xff << 160)) | (3 << 160)` to `B + 1`. The direct `PUSH21 0x03…00` at `0x16ba` supplies state 3. Subsequent writes set `sharesPending` (`B + 8`, low 128 bits, `0x16ef`), minimum proceeds (`B + 7`, high 128 bits, `0x1719`) and `lastTouch` (`B + 2`, low 64 bits, `0x1739`).
5. Minimum proceeds must fit `uint128`; this check occurs after the first writes, but a revert rolls them all back. Successful token `balanceOf(desk)` reads and arithmetic are required through the event path (`LOG2 0x178c`); lock release is `0x1792`, then `STOP 0x0496`. **No library delegatecall is needed to create state 3.** This is a request, not an executed token sale or loan repayment.

A bounded local opcode interpreter followed the complete dispatcher-to-STOP path with **synthetic storage and simulated token responses only**. With position/listing shares 2,000,000, token balance 2,999 and input words `(1, 100, 50)`, it reached state 3 with 100,000 pending shares, minimum proceeds 50 and the supplied timestamp as last touch in 1,009 opcodes. Zero units and oversized requests selected all shares; wrong caller, wrong starting state, active checkpoint, zero minimum, overflowing minimum, zero rounded shares and failed balance reads exercised reverting branches. These are conditional runtime witnesses, **not retained real positions, a consensus-client/gas cross-check, a constructor-to-live-state proof or exhaustive path verification**.

Related paths corroborate the lifecycle without filling the missing ABI: selector `0x316e13a3` (`0x0482 → 0x115b`) requires the borrower and state 3, resets state 2 at `0x11be`, and clears the pending fields; that cancellation also completed offline. Selector `0xa99c38af` (`0x0afd → 0x23c6`) checks state 3/no checkpoint and consumes capped pending shares/stored proceeds through shared settlement. Published `closeNow` (`0x8c778fa1`, body `0x1ea3`) accepts states 2/3; it is not this pending-request creator. Shared settlement delegates at `0x3e96` to fixed SettleLib selector `0x0a48f8df`; retained SettleLib bytes contain the state-2 reset/pending-field clears at `0x2106/0x2121/0x2131`. Exhaustive settlement predicates and library storage-alias analysis remain outside this focused proof.

The hash-bound publisher consumer still only supplies `cancelOpen`/`closeNow` exit interfaces and calls `closeNow` directly. Its enum at character range `[861247, 861294)` is presentation evidence; it neither proves nor disproves the additional runtime entry. No full ABI, Solidity source, fresh configuration or current use of state 3 was obtained.

### Exact token-share units

The reviewed Desk path `unitsOf → 0x20fa → 0x3ca0 → 0x4b97` reads the actual token balance. With nonzero shares and listing total shares:

```
units = floor(positionShares × (deskTokenBalance + 1)
              / (listingTotalShares + 1_000_000))
```

Zero shares or zero listing total shares returns zero. The virtual offsets mean plain `shares / totalShares × balance` is **not exact**, even if the difference looks small. Rebases, splits, donations and transfer-tax receipts flow through the underlying balance. This is not a guarantee against a hostile token's pause/blacklist/upgrade or a manipulation of its balance reporting.

For current gross long spot exposure, value actual `unitsOf` with the applicable live conservative mark and actual token decimals. Report accrued USDG debt and posted wsNET margin separately. Do not add either to gross token exposure, call lender principal OI, or net one product's short against another product's long without labeling the measure.

## Listings, measurements, depth and leverage

`tokenCount()` / `tokenAt(i)` are the discovery surface. A historical listing entry can remain after delisting. A browser tab or token registry row is not an active loan market; fetch listing and eligibility state for each question rather than retaining a status snapshot. Metadata symbols are not globally unique; `AI`, not demo `AINU`, is the publisher identity for the real clone.

Read `listings(token)` and `opensAllowed(token)` together at one observation block. Keep `listed`, `allowed`, `probeOk`, `ownerRisk`, `measuredAt`, oracle-live state and refusal reason separate. Neither `allowed` alone nor a nonzero pool address proves an opening is possible.

### ListerLib: all dispatcher bodies and trust boundaries

The Desk links the library by fixed address and `DELEGATECALL`; it operates on Desk storage, not an independent pool balance. Its mutating entries have the Solidity library delegatecall-context guard. Without source, its storage-reference ABI must not be invented from ordinary contract tuple signatures.

The ten body targets are recorded in the catalog: open checks `0x027f`, depth `0x065f`, token cap `0x0707`, leverage parameters `0x0767`, listing `0x0801`, quote `0x0cde`, Safe ceilings `0x0fa0`, marks `0x10e6`, liquidation thresholds `0x126a`, and measurement `0x13b5`.

Material traced behavior:

- Listing rejects USDG/wsNET and tokens with decimals above 18. It resolves/validates the canonical mark pool and requires usable marks.
- A changed mark pool or quote basis is refused with nonzero token shares. Delisting does not itself sell existing positions.
- Additional depth pools are bounded by `MAX_DEPTH_POOLS = 8`; duplicate identities and duplication of the mark pool are rejected through source validation calls.
- Effective submitted depth is capped to the source's measured depth and halved for `ownerRisk`.
- Probe success and volatility are submitted inputs. The contract enforcing a formula is **not** proof that an off-chain probe detected every pause, mint, blacklist, upgrade or sellability hazard.
- Opening measurements stale after 21,600 seconds are refused. This is not a requirement that borrower exits wait for fresh measurements.
- Marks try full TWAP/spot first, spot-only next, then zero; fallback remains `twapLive=false`. A returned number with false liveness must not be treated as a healthy liquidation oracle.

### Integer formula, not approximate prose

For leverage `L` in WAD and volatility `sigmaHBps`:

```
formulaMaxL = clamp(floor(9000 × 1e18 / (3 × sigmaHBps + 200)),
                    1.2e18, 10e18)
maxL        = min(formulaMaxL, nonzero Safe leverage ceiling)
slipBps     = floor(1000 × 1e18 / L)
maintenance = slipBps + 200
rawTokenCap = min(floor(effectiveDepthUsdWad × slipBps / 10000), 250000e18)
tokenCap    = min(rawTokenCap, nonzero Safe cap)
positionCap = min(floor(tokenCap / 4), 50000e18)
```

The 9000 numerator is the algebraic effect of the leverage-dependent slippage term in the publisher's implicit formula. Preserve integer flooring and Safe overrides; do not naively iterate the prose equation using binary floats. Cap reservations use normalized cap shares and are released proportionally; they are not lender debt.

The documentation gives Safe listing/delisting and ceiling authority without a timelock, and a keeper that measures rather than lists. Exact current `lister` / `listerAdmin` holders were **not pinned** here. Do not promote constructor/publisher roles into a current permission observation.

### TWAP/depth implementation gaps

MarginTwapSource pins NET/USDG canonical V2 pair, V3 factory, WETH, USDG, PairOracle, ETH/USD feed and V4 PoolManager. Token prices require the correct token/quote orientation and raw decimal scale; WETH-quoted routes have an additional ETH/USD leg. The full source was unavailable. Exhaustive V3 tick-walk depth, V4 hook/pool validation, all oracle freshness conditions, negative-tick rounding and every failure branch therefore remain explicitly unvalidated. **TVL/reserves are not a substitute for liquidity within 1% of spot.**

## Health, exit, liquidation and impaired debt

Publisher maintenance compares equity to combined token mark plus wsNET credit:

```
value  = tokenValueAtMinLiveTwapSpot + wsNETCredit
under  = (value - debt) / value < (slipBps + 200) / 10000
```

There are two risk legs: token price and NET/wsNET credit. A stable token can still be called by falling NET credit. Read the contract's health tuple and **both** liveness flags; derived thresholds are not guaranteed execution prices.

The documentation describes an under-maintenance checkpoint, five minutes of persistence, recovery/margin-addition clearance, then partial sale first if it can restore health. That policy is not an assumption that every fresh request below maintenance immediately liquidates. The all-path timing/state-machine proof remains incomplete with unavailable Desk source.

### SettleLib: actual sale and waterfall

The six public library dispatcher bodies are sell/settle `0x0172`, buy leg `0x0970`, route selection `0x09b2`, surplus sweep `0x0b43`, margin removal `0x0d21`, and zero-token-unit impaired exit `0x10b2`. Their catalog preserves selectors and missing parameter/storage ABI, rather than pretending these are ordinary user-call APIs.

The examined paths:

1. Accrue the pot and derive current proportional token units from shares.
2. Transfer the sale input to executor. Measure output by actual destination balance delta and cap against the executor-reported output. Nominal route quotes alone do not settle a tax token.
3. Deduct the 25-bps close fee; liquidation-reason branches additionally deduct a 100-bps penalty. Half the penalty, floored, goes to pot insurance and the remainder to the fee router.
4. Liquidation net proceeds retire debt; ordinary partial close retires proportional debt. A full sale can call on posted wsNET for the remaining debt.
5. Seize wsNET using rounded-up credit conversion, capped by margin. The pot receives **wsNET**, not sale proceeds from dumping wsNET. A voluntary exit with still-uncovered debt reverts; borrower exits are not a path to hand arbitrary deficits to lenders.
6. Retire appropriate principal/scaled debt and proportional entry/cap shares; return residual USDG and remaining wsNET where the path closes the position.
7. Report only credited seized borrower margin as eligible realized loss. Pot-uncovered debt is not the trader's eligible LOSE loss.

The zero-unit impaired exit is a distinct path for a position whose pro-rata token holding has vanished. It accrues debt, uses available margin credit, retires debt through the pot and reports the relevant borrower loss; it must not be confused with a no-op “zero OI means no obligation.”

### Route and margin permissions

The route selector permits the lister's route; the borrower's own route is allowed only on a borrower-directed branch. Other callers use the canonical pool. A nontrader borrower-close fallback includes a **600-second last-touch** check; this is separate from the documented **300-second under-maintenance** checkpoint.

Removing margin is borrower-only, restricted to open/pending-sell states, refuses an active underSince checkpoint, and rechecks live token/NET oracles and the opening-margin requirement after subtraction. Adding margin is not a new leveraged purchase. “Closes never pause on a stale listing” must not be expanded into “closes cannot fail”: sellability, token transfer, route proceeds, debt coverage and dependency failures can still prevent a close.

The executor's `execute` path is Desk-only and guarded against reentrancy. It restricts resolved targets and bars input/output tokens as arbitrary call targets; V3 callbacks authenticate the active pool before paying input. No assertion is made that arbitrary quote bytes are safe merely because the target is a router. Complete allowance-reset/partial-spend and every adapter-kind predicate remain a source gap.

## Lending Account: debt is an asset, not cash

The pot has internal lender shares, not a supplied ERC20 share interface. The runtime separates actual USDG custody, insurance USDG, seized wsNET, insurance wsNET, outstanding principal, scaled debt, dated withdrawal obligations and already-funded claim reserves.

```
idle = max(actualUSDG - insuranceUSDG - fundedWithdrawalReserve, 0)
equity = max(idle + outstandingPrincipal + lenderNetAccruedInterest
             + creditValue(heldWs - insuranceWs) - unfundedDatedOwed, 0)
```

Adding gross cash, all debt, all wsNET and lender shares would double-count. The seized asset is credit/floor-valued through the oracle, not presumed liquid USDG.

### Interest and rounding

Utilization uses `floor(principal × 10000 / (principal + idle))`, zero if principal is zero. The annual rate is 4% at zero, 20% at 80%, and 60% at full utilization. The current borrow index advances from the last accrual using:

```
newIndex = storedIndex
         + floor(storedIndex × annualRateWad × elapsedSeconds
                 / (1e18 × 31536000))
debt     = ceil(scaledDebt × newIndex / 1e18)
```

Do not replace this interval accrual with an assumed exponential or independent per-position APR. Lender projected net interest excludes the 20% fee-router and 10% insurance cuts. Realization allocates them; a view's projected interest is not already spendable cash.

Deposit shares are `floor(amount × (totalShares + 1e6) / (equity + 1))`; withdrawal valuation reverses those virtual offsets and floors. Nonzero amount/recipient and nonzero minted shares are required. Donations, insolvency and rounding can change share economics; the formula is not a deposit guarantee.

### Withdrawal priority and shortfall absorption

A withdrawal burns caller shares, pays from idle immediately and dates the remainder to the caller. The recipient argument directs immediate cash, not someone else's dated entitlement. Dated claims use cohort/index accounting and are funded pro rata as idle arrives. Funded-but-unclaimed amounts remain reserved. While unfunded dated owed is nonzero, lending refuses new loans.

`claim(account)` can be triggered by another caller but pays that account, caps payment by available cash and returns zero when nothing is payable. “Empty cash does not revert” is scoped to that payout behavior, not a claim that all functions succeed under every missing dependency.

Desk-only repayment retires principal/scaled debt. An uncovered liquidation shortfall first reduces USDG insurance, then reallocates credit-valued insurance wsNET by rounded-up conversion, then reaches lender equity. Insurance wsNET is not simultaneously lender equity, and paper credit value is not immediate withdrawal cash.

**Frontend permission trap:** `buyHeldWs(ws,to)` appears in the publisher ABI/client, but the examined runtime at `0x1e61` requires the fixed admin. It excludes insuranceWs, takes rounded-up credit-valued USDG and sends wsNET to the chosen recipient. Do not expose it as a permissionless “buy seized margin” transaction just because the interface has no modifier metadata.

## Fee router: NET demand and burn, not a Treasury deposit

The official margin description sends open/close fees, 20% interest and half liquidation penalties to the fee router. The reviewed router measures USDG spent and NET actually received; supplied routes are subject to authorization/minimum-output checks. Its fixed mode is false at runtime `0x0b30`, selecting the `NET.burn(uint256)` branch at `0x0df7`. A compiled alternate staking/insurance-ws route is not active under that immutable pin.

Thus do not model those USDG fees as a direct Treasury reserve deposit. NET tax on route legs, liquidity, oracle minimums and actual fill determine how much NET is burned. The presence of a burn path does not prove a particular fee was processed or how much backing changed.

Use the [revenue and house-proceeds recipe](netlong-analytics.md#revenue-and-house-proceeds) for executed fee events, pot-wide accrued versus realized interest, insurance allocation/shortfall and actual router receipts/burn reconciliation. October 12 supplemental disassembly of retained router bytes establishes unnamed mode getter `0x3395b222` (one bool word), and `LOG1` topic `0xf19b38dc0f9599107b200aae774b4b4cb8248bc622a4a23f844799029efd0453` at PC `0x0ebe`: five 32-byte data words, word4 `CALLER`, no indexed arguments. Source event name and the other field meanings remain unresolved. The write-capable processing selector `0x15ce45a2` is not an accounting view; no guessed named ABI is added. The catalog records these structural observations without claiming full-function verification.

### Discovered WETH/USDG pool

Executor immutable getter at `0x011b` points to `0x69bf…8d9a`, which is **UniswapV3Pool**, not a router. Its indexed immutable getters identify WETH token0, USDG token1, V3 factory `0x1f7d7550b1b028f7571e69a784071f0205fd2efa`, fee 500 (0.05%) and tick spacing 10.

The complete supplied ABI includes initialization, mint/burn/collect, swap/flash, observation growth and cumulative reads, factory-only protocol fee controls, tick/position/fee-growth getters and events. Source review establishes:

- swaps walk initialized ticks until amount/price limit, using concentrated-liquidity math; active liquidity is not a complete depth estimate;
- mint/swap callbacks must actually pay the input balance delta, so fee-on-transfer inputs are not made safe by an optimistic nominal quote;
- burn credits tokens owed and collect pays the caller-owned range separately;
- flash fees round up, and actual postcallback balances must cover principal plus fee;
- factory owner alone changes protocol fee denominators (0 or 4–10) and collects protocol fees; full collection deliberately leaves one raw unit;
- observation capacity growth does not create missing historical observations.

The source files include its inlined math/oracle libraries. Their hashes and function declarations are recorded, but independent compilation and an exhaustive audit of all math-library edge cases are not claimed.

## LOSE: fixed issuance, loss-triggered distribution, no redemption

The [standalone LOSE documentation](https://docs.netnet.capital/lose) supplied only “Don’t lose.” It does not establish a redemption right, backing claim, guaranteed price or a cash-loss reimbursement scheme.

The examined [token constructor](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xF4D567e3C0B7b24Bd2f379db8249701A6F929E93) allocates **exactly 1 billion LOSE at 18 decimals** (`1e27` raw units): 10% to the Sleeve and 90% to the distributor. This is original issuance, **not a rounded estimate or an assertion of current `totalSupply()`**. Token burning reduces current supply; `burned()` is original issuance minus current supply. Current supply requires a fresh pinned read, not a stored financial snapshot. Distributor `released()` is a transfer ledger, not circulating supply or user holdings.

`record(address,uint256)` is selector `0xc6685617`. The [distributor's indexed runtime](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x1DEdDa4dE44f406FD25CdD3A22ABb8e524368719), observed October 10, requires an approved desk, nonzero trader and a loss at least `1e18` USDWad ($1). It updates aggregate qualifying losses/releases and invokes `LOSE.transfer(trader, amount)`. **It does not mint new token supply.** Smaller reports return zero before updating cumulative loss; they are not a per-user carry-forward credit. Lost lender equity and every theoretical mark-to-market loss are not automatically eligible.

### Curve: exact numerator and rounding

Let:

- `C = 900,000,000 × 1e18` LOSE units (distribution allocation);
- `L0 = 1,000,000 × 1e18` USDWad;
- `K = 5,000,000 × 1e18` USDWad;
- `L` be aggregate qualifying recorded USDWad loss.

The inspected `cumulativeAt` body at `0x04cd` implements:

```
if L <= L0:
    F(L) = floor(C × L / (L0 + K))
else:
    base = floor(C × L0 / (L0 + K))
    tail = floor(C × K / (L0 + K))
    F(L) = base + floor(tail × (L - L0) / (K + L - L0))

release = F(oldLoss + reportLoss) - F(oldLoss)
```

The initial rate is **150 LOSE per dollar**, flat through $1m qualifying aggregate losses. Afterwards the `rateAt` body implements the WAD-scaled decay `150 × K² / (K + L - L0)²`, with integer floor. The tail tends toward the remaining 750m tokens, so total distribution tends toward **900m**, not the entire 1b issuance. Extreme checked intermediate arithmetic can revert; “asymptotic” is not an unlimited-input safety claim.

A single report spanning the knee uses the difference of cumulative entitlements, not current marginal rate times loss. Integer cumulative differences can give zero raw-unit marginal release at extreme tail scales. Transaction ordering controls each report's interval; no personalized fixed rate or guaranteed token-dollar value follows.

### Two concrete publisher/implementation discrepancies

1. **“Minted” versus distributed, and best effort.** The margin prose says LOSE is minted in the same transaction. Token/distributor runtime instead shows fixed preissuance and transfers. More importantly, MarginSettleLib `0x2133–0x2262` calls the distributor with a low-level call and emits a failure event if it fails without reverting settlement. Do not promise every eligible settlement successfully awards LOSE, or assume a retry/backfill entitlement. The event field named `minted` is vocabulary, not proof of supply creation.
2. **UI curve numerator.** The entry literal at approximately characters 838816 onward defines `Cz=1e9`, `L0=1e6`, `K=5e6`, and initial rate `Cz/(L0+K)`. That uses **the whole 1b issuance**, yielding 166.666… LOSE/$ and a 1b asymptote. The current distributor runtime uses **900m allocation**, yielding 150 LOSE/$ and a 900m asymptote. The [LOSE page module](https://trading.netnet.capital/assets/LosePage-rEbrSJ86.js) consumes that frontend calculation. This is a durable formula discrepancy, not a retained live-rate snapshot. Use the applicable distributor formula/quote, not the graph, for economic analysis.

### Authority and finite supply relationships

The distributor registration body permits only registrar additions before `sealBy`, rejects zero/duplicate desks, and increments desk count. The sealing body permits the registrar or a caller after the deadline and zeroes registrar. These are runtime conditions, not a claim that the registry is presently sealed or that current desk membership was fetched. No desk-removal path was found in the inventoried 22-selector dispatcher; absence of source remains explicit.

The token's hardcoded distributor-sender exemption makes reward delivery untaxed. It does not create a holder redemption promise. Do not treat `quote` as a reserved balance, user claim proof, oracle price or an execution recommendation.

## LOSE transfer tax, conversion and pair mechanics

### Token transfer behavior

For ordinary transfers touching a flagged pool, the examined token path burns `floor(amount × 200 / 10000)` and accumulates `floor(amount × 300 / 10000)` in the token's levy inventory; recipient receives the remainder. If both endpoints are pools it is still that one transfer's tax, not two independent taxes. Wallet-to-wallet transfers are untaxed **unless one endpoint has been flagged as a pool**.

Transfers **from** the fixed distributor or **from** the token itself bypass the levy/burn path. This is a directional sender exception, not an arbitrary caller exemption. Safe-only `setPool(address,bool)` rejects zero and refuses changes to the canonical pair flag, but can immediately flag/unflag other addresses. The publisher also names V4 PoolManager among initial pools; do not assume every possible market venue is tax-equivalent without fresh configuration.

Automatic conversion can run on a non-pool-origin transfer when not already swapping and levy inventory exceeds the threshold. It caps a chunk at the threshold, checks canonical USDG reserves and stored TWAP availability, and catches swap failure so the triggering transfer need not fail solely because conversion failed. Explicit conversion has amount/balance/chunk guards, reserve/TWAP requirements and a user minimum at least the prescribed slippage floor. The router sends resulting USDG to the fixed Sleeve, not token holders.

Inspected immutable parameters are 250,000 LOSE per conversion chunk, 1,000 USDG minimum canonical reserve, 1,800-second TWAP update interval and 300-bps quote slippage. A TWAP update interval does not prove a complete fresh, manipulation-resistant price history. Conversion, underlying pair operations and transfers can still encounter unavailable liquidity or downstream reverts.

### The actual pair, not merely ERC20

The attributed/equal-runtime pair is UniswapV2Pair with its UniswapV2ERC20 LP implementation, not LOSE token itself:

- LP `approve`, `transfer`, `transferFrom` and nonce/deadline-bound `permit` control LP shares. Maximum allowance is non-decrementing. LP `totalSupply` is unrelated to LOSE's 1b issuance.
- `mint(to)` uses actual deposited balance increments. First mint locks 1,000 raw LP permanently; subsequent mint uses the smaller pro-rata contribution. It has no implicit protection against an unsynced deposit being skimmed first.
- `burn(to)` burns LP already held by the pair and sends a pro-rata share of actual token balances. Pair amounts are gross; LOSE tax can reduce net receipts.
- `swap` transfers outputs optimistically, optionally calls `uniswapV2Call`, then checks actual inputs and the 0.3%-fee-adjusted constant-product inequality. LOSE's 5% transfer levy/burn is additional and changes route outcomes.
- `skim(to)` is permissionless and sends balances above stored reserves. An unminted/unsynced seed or donation is not protected liquidity. `sync()` instead changes reserves to actual balances. This explains why a “tokens sent to pair” observation is not equivalent to initialized, owned LP.
- `_mintFee` consults factory `feeTo`; when enabled, it mints protocol LP from growth in square-root invariant, rather than directly transferring 1/6 of gross swap proceeds.
- Cumulative prices use reserve ratios in UQ112x112 times elapsed seconds, with intentional timestamp/cumulative wrapping. A cumulative alone is not a quote.
- `initialize` is factory-only but has no pair-local once-only flag. The safety assumption is the factory's deployment behavior; LP code itself has no upgrade or owner interface.

No reserve, liquidity, supply or reward-ledger snapshot is packaged. The pair implementation does not guarantee a market price, liquidity continuity or redemption of LOSE for loss dollars.

## Market token implementation distinctions

### PONS

Explorer-returned `PonsLauncherToken` mints its entire configured supply to the launch factory in the constructor. It supplies ordinary OpenZeppelin ERC20 accounting, **no external mint, burn, pause or upgrade entrypoint** in the obtained ABI. Metadata's `deployer` is not itself an owner role.

During its configured launch window, buys from any recognized V3 pool for token/pair asset are restricted. The launch block blocks nonexempt buys; the factory can open an initial-recipient exemption. Other buys enforce recipient max wallet and cumulative per-recipient pool-buy limit. After the window, the hook becomes ordinary ERC20. This is not CASHCAT's tx.origin rule. Canonical pool resolution and alternate-fee recognition depend on the pinned V3 factory; historical registry promotion is not a fresh determination that restrictions have expired.

### CASHCAT

Explorer-returned `LaunchToken` likewise constructor-mints configured supply and exposes standard OpenZeppelin ERC20 and metadata, with no external mint/pause/upgrade operation in the obtained ABI. Its launch rules differ:

- only the configured canonical pool is the recognized buy pool;
- factory and creator exemptions exist in the launch checks;
- cumulative buys are keyed by **tx.origin**, with allowance `floor(maxTxAmount × 11000 / 10000)`;
- during the restriction window the recipient wallet cap also covers applicable transfers not just recognized pool buys;
- a missing canonical pool disables the launch restriction checks in that path.

Do not substitute PONS's recipient accounting or generic “tax token” assumptions. Neither obtained launcher implementation rebases balances or charges LOSE-like transfer tax.

### AI / Artificial Inu

The real AI address is a 44-byte EIP-1167 clone whose runtime contains fixed implementation `0x3Be8…C599`. Its source ABI is the implementation's ABI bound through that proxy, **not an ABI independently returned for the clone**. The implementation constructor disables initialization on itself; clone initialization is separate. Current clone owner, controller, pool-lock, limits and vesting configuration were not fetched.

DopplerERC20V1 includes:

- one-time initialization, metadata, pool lock, max-balance rules, vesting, voting and permits;
- initial vesting allocation caps of 80% per beneficiary and 80% aggregate, validated schedule arrays, cliffs and duration (zero or at least one day);
- already-issued vesting inventory transferred on `release` / `releaseFor`; cliff-gated linear flooring from vesting start, all available when amount zero, and permissionless `releaseFor` always paying the beneficiary;
- owner-controlled pool lock/unlock, stopping transfers **into** the configured pool when locked, and owner token-URI updates;
- controller-only permanent early disabling of balance limit, and lazy expiry disabling; excluded recipients include configured parties/vesting beneficiaries and new owners while applicable;
- holder-only burn, ordinary token transfers subject to those hooks, vote checkpoint updates, delegation and signature delegation;
- owner transfer/renunciation and 48-hour request/complete/cancel handover operations;
- block-number voting clock, strictly historical past-vote lookups and signature nonce consumption;
- **fixed infinite Permit2 allowance** in the Solady ERC20 implementation: token-level approve/permit to Permit2 with a nonmaximum amount reverts, and Permit2 transferFrom bypasses ordinary ERC20 allowance deduction. This does not authorize an analytics tool to sign Permit2 messages.

No arbitrary external post-initialization mint was found in the supplied implementation ABI. Owner control of a receiving-pool lock is nevertheless a concrete sellability risk. Do not infer the current listing's `ownerRisk`/probe decision solely from this source, nor treat the 44-byte fixed clone as proof that its mutable permissions are benign.

## Superseded deployments and remaining validation

The publisher explicitly supersedes MarginDesk `0x422e49Df6DA02Bd19C92d6D0b3d9CBb324C53B77`, and LOSE token `0xF71B999D3cb520E4214F38262424c8D398B8e0a0`, distributor `0x37feC09Ef3cE2f3e1d1566F0f451c60d1C772a94`, pair `0xBd033f7BF613E6ECfb7539a5b939D16607BF0821`. Do not attach their seed paths, roles, configuration or accounting to current addresses. The old seed incident is a publisher history claim, not an independently replayed exploit here.

Remaining evidence is specific: complete current margin/LOSE source and ABIs; every unnamed dispatcher and exact storage-reference library ABI; independent compile/runtime equivalence; fresh authorized-provider block/hash/runtime and permissions; exact listing/pool/probe/oracle state; whole-system principal/debt/shares/withdrawal/insurance reconciliation; and current external router/token/factory authority. Fixed deployment identities and conditional source/runtime findings remain useful without pretending those missing checks happened.

The catalogs and read-only analytics are separate layers. Descriptive ABIs can explain writes; executable analytics assets remain read-only. Missing source/state evidence requires qualified answers, not transaction execution, invented signatures or a full-validation flag.

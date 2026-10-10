# PremiumSeller: contract semantics and accounting evidence

This is descriptive, read-only contract analysis, not a transaction guide. The complete obtained ABI includes a write function for explanation only; it does not authorize signing, approvals, execution, calldata generation or ready-to-submit artifacts.

## Identity, source and review scope

PremiumSeller is the chain 4663 contract [`0x346e1a31171A0f7aC73909010b5435768d3B5462`](https://robinhoodchain.blockscout.com/address/0x346e1a31171A0f7aC73909010b5435768d3B5462). Its canonical record is in [the address catalog](../assets/addresses/contracts/perp-oracles-pendle-lp-premium-seller-and-presser-prizes.json).

On October 10, 2026, the [explorer source response](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x346e1a31171A0f7aC73909010b5435768d3B5462) supplied the complete PremiumSeller source, nine additional files, a 21-entry ABI and creation/deployed bytecode. All ten supplied files were read, including FixedPointMath and every dependency interface. The [descriptive catalog](../assets/contracts/premium-seller.json) now preserves all 13 functions, six custom errors, one event and one constructor. The older five-function publisher literal remains separately dated provenance, not the current completeness claim. Its `premiumThresholdWad` label was `view`; the explorer/source definition is `pure`.

[Portable evidence](../assets/contracts/premium-seller-source-evidence.json) contains source hashes, declaration line locators, original analysis, dependency boundaries, dispatcher matches and immutable bindings—not third-party Solidity archives or runtime bytecode blobs. Source ID: `netnet-premium-seller-implementation-20261010`.

- Explorer-returned runtime: **3,908 bytes**, SHA-256 `e221c12443a8c1c39a7921d53341c8b689546777ccbc990a2e68ae8aa2e4a067`.
- All 13 instruction-boundary dispatcher comparisons match the 13 ABI function selectors; none remain unidentified in that detected dispatcher. Default dispatch reverts, and the runtime has a global nonpayable value check.
- The creation template and explorer runtime differ only at 23 nonzero immutable words. A further cached token-order word is zero. Seven address arguments match their corresponding runtime words; the cached USDG factor is `10^12`, consistent with six decimals at construction, and cached NET ordering selects reserve 1.
- Explorer reports Solidity `v0.8.30+commit.73712a01`, Osaka, optimizer 800 runs, no via-IR, `is_verified=true`, `is_fully_verified=true`, no indexed proxy implementation and no changed-bytecode flag for this seller.

These are **provider evidence and static consistency checks**, not an independent compiler rebuild, exhaustive bytecode/source equivalence proof, security audit, pinned RPC code/state verification or current permission check. Solidity was not executed. Interface comments are not substitutes for dependency implementations; for example, the supplied Genesis interface retains older cap commentary inconsistent with its supplied Constants file.

### Creation boundary, not transaction history

The [address metadata](https://robinhoodchain.blockscout.com/api/v2/addresses/0x346e1a31171A0f7aC73909010b5435768d3B5462), [creation transaction](https://robinhoodchain.blockscout.com/api/v2/transactions/0xbc4e2476b101f79753191364a4bc83fe6ff053c49998c48674c97521149f3c3e) and [block record](https://robinhoodchain.blockscout.com/api/v2/blocks/11439688) corroborate deployment in block **11,439,688**, at **2026-07-16 17:32:50 UTC**, block hash `0xa8a1a4768b0db740643e05b547c6ac9c6cde8a779572887bda4df390997d525f`. The transaction reports successful direct creation of the canonical seller. This fixed identity is a starting boundary for fresh history, not proof of provider log completeness. A live run must independently validate the canonical creation receipt and block provenance; do not treat explorer metadata as an already-pinned receipt.

No sale counts, proceeds, transaction roster, financial snapshot or present activity assessment is distributed here.

## What one successful execution actually does

The concrete source, rather than the name “seller” or “sweep,” establishes the following sequence:

1. Require GenesisBond `finalizeTime()!=0`.
2. Read the oracle TWAP and Treasury backing. Require **TWAP strictly greater than 2 × backing**; equality fails. Oracle failure propagates. The oracle interface documents a 30-minute–4-hour window, but the seller delegates validity to that dependency and does not checkpoint or independently implement window checks.
3. Require at least **3,600 seconds** since `lastExecuteAt`; equality is allowed. Record the current timestamp before minting or swapping. Any later revert rolls this write back.
4. Compute **floor(pool NET reserve × 25 / 10,000)** and require a positive clip. This is 0.25% of the selected stored pool reserve, not seller inventory, total supply or the pool's possibly unsynced NET token balance.
5. Call Treasury `mintNet(seller, clip)`, minting new NET to the seller.
6. Compute the ordered, rounded protocol minimum, then take the larger of that minimum and the caller-specified minimum.
7. Snapshot the seller's USDG balance, approve the immutable router for the gross clip, and use the fee-on-transfer-supporting NET→USDG swap path, recipient seller, deadline current block timestamp.
8. Measure `usdgOutRaw = seller balance after swap − seller balance before swap`; enforce the minimum again.
9. Transfer **exactly that measured delta** to Treasury, requiring the USDG transfer to return true, then emit `PremiumSold(clip, delta)`.

**Pre-existing USDG donations to the seller are not swept.** The local variable/event name does not change the balance-difference formula. The source contains no separate rescue, withdrawal, owner, parameter setter or upgrade entrypoint. Dependency contracts can still have their own permissions and mutable behavior.

### Units, floors and prices

NET uses raw units of `10^-9 NET`; USDG uses raw units of `10^-6 USDG` for this deployment's cached conversion. TWAP and backing are WAD USDG **per whole NET** (`10^18` scale). The threshold getter is a dimensionless WAD multiplier, not a fixed USDG price.

Let `N` be the gross minted NET raw amount, `P` the WAD TWAP, and `B` the WAD backing. The implemented operation order is:

- `thresholdWad = floor(B × 2e18 / 1e18)`; require `P > thresholdWad`.
- `expectedWad = floor(N × P / 1e9)` using full-precision 512-bit `mulDiv`.
- `minAllowedRaw = floor(floor(expectedWad × 9900 / 10000) / 1e12)`.
- `minOutRaw = max(callerMinRaw, minAllowedRaw)`.

The multiplication by 9900 is ordinary checked 256-bit arithmetic, not `mulDiv`; overflow reverts. The floors are downward and can matter at small quantities. No extra positive-USDG minimum is enforced by this seller beyond those formulas and dependency behavior.

For receipt-attributed USDG raw proceeds `Q`, realized USDG per gross minted NET is the exact ratio `(Q / 1e6) / (N / 1e9)`, equivalently `Q × 1000 / N`. For several sales, volume-weighted price is **total USDG / total corresponding NET**, not an unweighted average of prices. If quoting a price per **actual pool NET input**, label the different denominator and establish it from receipt evidence.

The strict TWAP gate **does not guarantee the actual realized execution price exceeds 2 × backing, 2 USDG, or any unconditional fixed USDG floor**. The 1% execution allowance and integer rounding can put realized price below the gate's level. Narrative statements such as “every NET sold brings more than 2 USDG” or “every sale is above 2× NAV” must not be repeated as unconditional implementation guarantees.

USDG amounts are token-denominated proceeds, not independently established fiat dollars, redeemable bank cash, profit after keeper gas or investment returns.

## Complete obtained function surface

| Function | Selector | Meaning and limitations |
| --- | --- | --- |
| `active()` | `0x02fb0c5e` | Present eligibility hint: finalized genesis, interval elapsed, threshold helper succeeds and positive clip. Not a full execution simulation or liveness claim. |
| `clipSize()` | `0x0c614ba0` | Floors 25 bps of stored pool NET reserves, in NET raw units; can be zero or revert on dependency failure. |
| `execute(uint256)` | `0xfe0d94c1` | Permissionless, nonpayable mint→swap→delta-transfer operation with the gates above; descriptive only, not an allowed skill action. Returns gross minted NET and measured net-new USDG. |
| `genesisBond()` | `0x748a0ab0` | Immutable finalization-gate dependency; getter does not prove it is currently finalized. |
| `lastExecuteAt()` | `0x44120c56` | Stored uint64 time of last successful execution; initially zero. Historical consistency indicator, not a count or total. |
| `net()` | `0xc2fff4a5` | Immutable NET binding; mint authority and tax behavior belong to dependencies. |
| `oracle()` | `0x7dc0d1d0` | Immutable oracle binding; no assertion about its present window, config or identity equivalence. |
| `pairContract()` | `0x4d709adf` | Immutable reserve/constructor-order pair, not a direct swap destination argument. Router/factory alignment needs separate evidence. |
| `premiumThresholdWad()` | `0xdc727a38` | Pure constant `2e18`, the relative backing multiplier; no setter. |
| `router()` | `0xf887ea40` | Immutable FoT-supporting router binding; getter does not validate router implementation/factory. |
| `treasury()` | `0x61d027b3` | Immutable backing source, mint intermediary and USDG recipient; not proof of seller mint authorization or reserves. |
| `twapIfAbove()` | `0x6af08d89` | Public view helper used by `active()` through an external self-call; not restricted to self. Checks genesis/threshold, not interval/clip/mint/swap. |
| `usdg()` | `0xf5b91b7b` | Immutable USDG proxy address; immutable address does not mean immutable token implementation or transfer policy. |

The seven-address constructor rejects zero addresses, caches `pair.token0()==NET` and `10^(18−USDG.decimals())`, and is nonpayable. Decimals above 18 or dependency call failures revert. It does **not** validate NET decimals, token1, router factory membership, matching oracle pair, Treasury wiring or mint authorization. It creates no owner role.

Six custom errors are preserved: `IntervalNotElapsed` (cadence), `NotActive` (genesis, threshold or zero clip), `SlippageExceeded` (seller-measured output below minimum), `TransferFailed` (USDG transfer returned false), `ZeroAddress` (constructor) and imported `MulDivOverflow` (unrepresentable full-precision quotient). Solidity arithmetic panics and external dependency reverts can also propagate; the six-name list is not every possible failure payload.

FixedPointMath's supplied `mulDivUp` and `sqrt` were reviewed but are not seller entrypoints and are not called by the seller. `mulDiv` floors a 512-bit product quotient, checking overflow; `mulDivUp` adds one on a nonzero remainder; `sqrt` returns the floored integer square root. The complete source/ABI has no fallback or receive function.

## Eligibility is not history or liveness

`active()` does not test Treasury wiring or `isMinter`, NET authorization/exemption, successful router execution, allowance consumption, actual output, the caller's minimum, or USDG transfer to Treasury. It catches the **external self-call** to `twapIfAbove`, not all possible errors: the initial Genesis call, timestamp subtraction and `clipSize()` in the success body may still revert. A true return is therefore not a warranty of execution; false is not evidence the contract is unused or permanently inactive.

Similarly, **an empty filtered `eth_getLogs` response does not mean unavailable, inactive or never used**. It says only that the particular provider/filter/range returned no matching records. Establish the emitter, topic, creation boundary, range coverage, receipt/header consistency and explicit truncation/failures before making a scoped historical claim. `lastExecuteAt` supplies an independent historical consistency check: nonzero last execution contradicts a supposedly complete lifetime history with no sale, or with no matching latest sale. A legitimate time-window query can contain no sales while earlier sales exist. Incomplete scans must report observed subtotals and incomplete lifetime totals, not zero lifetime activity.

## Mint, tax and Treasury receipt boundaries

The relevant [Treasury source](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x04822Ea321A0DEE6F40656172F29312104855d66) and [NET source](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xCA9c78Dd337A67F6e0077F65F5E9218719d30eDf) were inspected for this path:

- Treasury `mintNet` checks wired state and `isMinter[msg.sender]`, then calls NET `mint`, then emits `NetMinted(minter,to,amount)`. One-time deployer wiring receives arrays; comments naming PremiumSeller are not proof of the actual permission roster.
- NET `mint` checks wired state, caller equals Treasury and nonzero recipient, then increases total supply and recipient balance and emits `Transfer(zero,to,amount)`. **Neither reviewed mint function imposes an RFV/supply cap before or after this transient mint.** Protocol invariant comments are not enforcement on this path.
- NET `approve` emits `Approval` and returns true. Seller ignores its Boolean result; the source-reviewed NET behavior, not the interface name, supports that assumption.
- NET `transferFrom` spends the gross allowance. A transfer is taxed only if tax is enabled, neither endpoint is exempt, and either endpoint is a mapped pair. Tax is `floor(gross × 500 / 10000)`. When nonzero it emits the tax transfer and `TaxCollected`, then emits the remaining transfer to the destination. Minting itself is not taxed.
- Thus event `netSold` is the gross newly minted/routed clip; pool receipt can be lower. Do not blindly multiply by 95%, assume seller exemption, or count separately collected NET tax as USDG from this sale. Current/historical exemptions and wiring were not pinned.
- Treasury USDG inflow is a **token transfer**, not Treasury `UsdgSpent` (an outgoing-spend event). The seller checks the USDG transfer return, but does not measure the Treasury balance increase.

The [USDG source endpoint](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168) returns an ERC1967 proxy whose implementation is read from storage and called by delegatecall. Its explorer-listed implementation is not a pinned current or historical storage observation. This review establishes the proxy trust boundary, **not** complete token transfer semantics, historical upgrades, pause/blacklist/owner state or a tax-free-transfer guarantee. Router, pair and oracle implementation equivalence likewise remains outside this seller review.

## Attributing fresh historical accounting

`PremiumSold(uint256,uint256)` has topic0 `0x79374ec49ec36f76193b30b6763852a2777fce5bc71823cfd79cd3ba7e66763e`, exactly one topic and 64 bytes of event data. Both fields are nonindexed: gross `netSold`, then `usdgSweptRaw`. The event has no caller, price, backing, tax or timestamp field; any such report must derive those separately and preserve evidence scope.

For deeper end-to-end execution validation, uniquely associate the ordered same-execution legs:

1. NET mint `Transfer(zero,seller,netSold)` and Treasury `NetMinted(seller,seller,netSold)`.
2. Gross router approval, any source-consistent NET tax leg, and seller→canonical-pair NET transfer.
3. Canonical pair exchange evidence and USDG delivered to seller, consistent with the measured output.
4. USDG seller→Treasury transfer matching the event delta, followed by the seller event.

Use successful receipts, exact emitters, topics/data, ordered log indices, block/transaction identity and existing pinned-header/recheck safeguards. Never attribute every Treasury inflow, swap or mint in the same transaction to PremiumSeller. Reject or explicitly leave ambiguous/missing/mismatched groups unreconciled; do not manufacture sales to fill gaps. Pair actual-input calculations can include pre-existing unsynced balances, so a Swap input field is not automatically the seller's transfer amount.

The [bundled collector](premium-seller-analytics.md) makes the narrower receipt-confirmed claim below: matching seller→Treasury USDG transfer evidence. NET mint/pool transfers and pair USDG output are supplemental corroboration; it does not claim to validate every approval, Treasury mint event, pair Swap or dependency invariant listed above.

Keep these quantities distinct:

- **Event-reported sale proceeds:** the seller's reported net-new USDG output/requested transfer.
- **Receipt-confirmed sale delivery:** uniquely matched USDG token-transfer evidence from the seller to Treasury for that sale.
- **Other Treasury receipts:** donations, genesis contributions and unrelated protocol flows, not PremiumSeller proceeds.
- **Treasury balance/RFV or profit:** different questions; cumulative delivered USDG is neither a current reserve balance nor net profit.

Historical totals must be computed afresh with a pinned endpoint block and explicitly bounded scans. Preserve provider limits, omissions, failed receipts, stale/reorg checks and observed subtotals. Do not ship an execution timestamp list or transaction history as a cache. This reference makes no current or lifetime financial assertion.

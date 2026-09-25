# Reserve analytics

Use RPC evidence, not website totals. Prefer the read-only helper for supported collection; extend it with host-authorized research where needed. The app and docs establish labels, interfaces and methodology; **every balance, reserve, supply, conversion and price used by the helper comes from the approved RPC at one pinned block**. The helper accepts no wallet execution, transaction submission or arbitrary endpoint. Its provider and method restrictions do not prohibit supplemental authorized read-only research.

```sh
python3 scripts/analytics.py rfv --scope core --json
python3 scripts/analytics.py rfv --scope reports --deadline 600 --json
python3 scripts/analytics.py rfv --scope net-assets --deadline 600 --json
python3 scripts/analytics.py rfv --scope core --block 72309518 --deadline 120 --json
```

`core` is the default. `--block` accepts a nonnegative block number or `latest-2` (default); all scopes use the same pinned snapshot. Existing `--output` preserves checkpoints; inspect the envelope's snapshot confirmation, errors, coverage and stopping reason before using a result. A deadline, unavailable component, incompatible relationship or reconciliation mismatch is partial, not zero. Successful Core reads survive a partial Sleeve collection.

For non-core scopes, `coverage.requested_scope` controls successful completion of the requested figure. Supplemental ledgers can retain missing evidence or RPC diagnostics without invalidating a complete Reports calculation; they are not thereby complete themselves. A requested total stays null and partial when one of its own required inputs is missing.

Historical replay requires archive state. A retained block header does not imply its contract state is still available; a pruned historical read stays unavailable rather than being replaced with a current-block value.

## Plain-language RFV requests

For “what's the current RFV and what makes it up?”, act without making the user choose a metric, find addresses or learn command syntax:

1. **Collect broadly.** Prefer `rfv --scope net-assets --deadline 600` within host permissions; one collection emits Core, Reports and economic ledgers. Do not run all three scopes redundantly. Keep the CLI's Core default for explicitly narrow requests, not as a reason to omit the wider holdings from a general answer.
2. **Establish today's perimeter.** Start with catalog identities, check live Treasury pointers and relevant ownership/configuration, enumerate current asset menus and positions, and investigate evidence of successor contracts or changed custody. A mismatch must not be followed blindly: establish chain, role and applicable interface independently before supplemental reads. Neither common deployer nor the entire balance of a product contract proves protocol ownership.
3. **Look beyond wallet balances.** Include attributable vault shares/underlying, lending supply and collateral less debt, owned LP NFTs and fees, product capital, queued/claimable amounts and liabilities. Check evidence of additional Treasury assets outside the Core formula and Sleeve assets outside the helper's supported families, including other position managers, maturity/redemption claims or indirect custody when relevant. Use public transfer/position history or authorized indexed discovery as leads; verify current quantities and prices through RPC. Avoid counting a claim and its underlying twice.
4. **Continue past helper gaps.** A missing ABI, catalog entry or supported family is a research task, not a permission denial. Use applicable verified interfaces/source, additional authorized RPC reads and analysis code to close it. Obey host restrictions and provider backoff; do not evade denials or rate limits. If the remaining evidence is unavailable, retain successful observations and name the exact missing scope/input. Never silently mix snapshots; disclose and reconcile unavoidable differences.
5. **Answer simply, with an auditable breakdown.** Lead with dated Core RFV and what its formula includes; alongside it show the broader Reports and adjusted figures when supported. Use component rows with owner/claim location, native amount, mark/unit, value, inclusion/exclusion reason and completeness. Separate own-NET exposure and liabilities. A valued asset excluded by Core or the dated Reports formula still appears in the wider inventory, not as zero or an omitted row.
6. **Qualify coverage, not usefulness.** State the addresses, discovery methods, managers and asset families actually searched, plus unpriced assets, missing intervals, unresolved liabilities and unsupported custody. A complete known-scope result is not proof of exhaustive ownership. If a broader total cannot be supported, give the reconciled Core and known breakdown, with the broader total explicitly unavailable—not Core relabelled as everything.

The only wallet boundary here is execution: public balance/state reads, transaction and event inspection, calculations, explanations and non-broadcasting analysis remain allowed. Never connect, sign, approve, submit or prepare execution artifacts.

## Three distinct figures

- **Core RFV / NAV** (`core_rfv`): canonical Treasury USDG, haircut-adjusted Morpho USDG and geometric protocol-owned NET/USDG liquidity. NAV divides by **total NET supply**, never circulating supply. This is the Treasury's reserve formula, not every asset controlled by the ecosystem.
- **Reports True RFV** (`reports_true_rfv`, `--scope reports`): Core plus separately identified Sleeve assets, using the Reports methodology. The output discloses collected custody, valuation evidence and missing inputs; no website mark or formatted total fills a gap.
- **Adjusted net assets** (`adjusted_net_assets`, `--scope net-assets`): Treasury cash, its gross attributable vault claim and its LP's USDG underlying only, plus supported external Sleeve/extra Treasury assets less supported liabilities. Unlike Core RFV, this removes own-NET POL backing and does not apply the reserve-formula Morpho haircut. Neither this conditional accounting view nor a claim conversion guarantees immediate withdrawability.

The non-core scopes also emit `sleeve`. Neither its holdings nor the LP underlying memo is an additional bucket to add again to an already inclusive figure. Partial known components are evidence, not an exact total or a guaranteed lower bound on net assets.

Reports collects the six-stock registry plus live RWA/Pack/Asset menus, wallet USDG and NET-family/hOHM holdings, Credit vault claims and posted collateral less stored-share debt, V3 principal, TURBO free/reserved/put pots and premiums, Predict `assetsOf(Sleeve)`, and THE BOOK's `housePot`. Credit direct supply, LP owed/growth fees and TURBO fee buckets remain supplemental to that Reports recipe. Predict queues/notices and Book player locks are retained separately, not added again.

Net-assets additionally retains independently discovered V4 exposures, LP owed fees, attributable Sleeve fees, accrued Morpho debt/supply and gross cashout/posted-settlement liability indications. Own-NET exposure stays separate from external assets, including the Treasury LP's NET side. Economic stock marks use only the six catalogued exact token/direct total-return feed relationships, divided by the same-block USDG/USD feed, without Reports' LP/TURBO `uiMultiplier`; a newly discovered token with an arbitrary feed is not silently given that interpretation. Asset TWAP marks are already USDG. A stale conversion feed, unresolved obligation or incomplete requested discovery window prevents the conditional known-universe total.

NET-family Reports marks use `pairOracle.twapNetUsdg` and the staking index; asset-desk marks use their RPC TWAP, without a spot-price fallback. The [Chainlink directory](https://reference-data-directory.vercel.app/feeds-robinhood-mainnet.json), reviewed September 25, documents **86,400-second heartbeats and 0.5% deviation triggers** for the exact USDG and six stock proxies. USDG is `Crypto`; the stocks are `us_equities_24/5`. The collector accepts a positive nonfuture complete round through the heartbeat boundary, but never extends it for weekends/market hours. These are publisher metadata, not an on-chain safety guarantee; deviation is not an observed price-error bound. Unknown feeds retain an explicitly collector-owned four-hour fallback. Feed rounds, age, exact policy and row observation references remain visible.

Reports' **NAV incl. RWAs** uses total supply; **True NAV (circulating)** is a different website denominator, not interchangeable with Core NAV. Do not infer circulating supply merely by subtracting whatever balances this collection happens to expose.

Neither non-core scope is an official [Predict grade](https://docs.netnet.capital/predict). Predict's documented mark excludes NET desk inventory and fixes the Sleeve's House contribution at the series open; a current Reports mark can differ. House Vault assets belong pro rata to its depositors, not automatically to the Sleeve. [THE BOOK](https://docs.netnet.capital/the-book) also separates its house pot from player balances, locked principal and payouts; gross contract token custody is not all house equity.

## Economic accounting and discovery boundaries

### THE BOOK: reservations are not payable balances

The [Book rules](https://docs.netnet.capital/the-book) and targeted [indexed runtime-bytecode review](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x3174dE69a84c53F82F6B6Dca5C64E705cFFe8Dd6) distinguish:

- **Open:** `max(owedFav - wagersDog, owedDog - wagersFav, 0)` is contingent house exposure, not the sum of two mutually exclusive payouts. Locked wagers/principal remain player property.
- **Graded, unsettled:** risk-on losing wagers have moved to the house; winning amounts remain reserved. Per-bet positive payouts remain unpaid, rather than being inferred from lifetime `owedFav/owedDog` or fee counters. Risk-off yield uses the clipped reservation and `P - ceil(P*i0/indexAtGrade)`; placement fee bps apply to the settled wager, not principal. A winner receives `P+wager-fee`; a loser receives `P-wager`.
- **Push/cancel/void:** refund the fee-net risk-on amount or risk-off principal; no new risk-off fee. These refunds remain locked until settlement.
- **Settled:** the stored payout is historical. It has been credited to free player balances and is not added as another claim.

`playerTotal` is free player balances. The checked custody identity is **housePot + playerTotal + lockedWagers + lockedPrincipal**; excess unsolicited custody is disclosed, not credited as house equity. `freePot == housePot - reservedTotal` is checked separately.

The collector records all markets up to its 128-market bound and the latest 128 bets. Aggregate obligation reconstruction may be complete without full bet history **only conditionally on the reviewed exact runtime, known token identities and all three nonnegative reservation/locked-stock reconciliations**: every positive unsettled risk-off payout retains locked principal; every positive unsettled risk-on win/push retains locked wagers. Thus zero residuals exclude another positive payable in omitted bets; settled payouts are already in `playerTotal`. Missing markets, unknown stages or nonzero residuals retain a blocker and null payable total. Output gives uninspected bet IDs and labels this `conditional_bytecode_and_conservation_reconstruction`, not verified Solidity or an audit. The exact runtime hash is checked at the pinned block; matching bytecode alone is not the semantic evidence.

All these assets and obligations are **wsNET**. The external net-assets view excludes them together with own-NET house backing; it neither owns gross player custody nor subtracts both outcome risks from external USDG. Native obligations and house value after decided settlements remain disclosed.

### Predict House: one claim per stage

The [House mechanics](https://docs.netnet.capital/predict) plus targeted [runtime-bytecode getter review](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xb488368902b1CbD7533F1536C3F860065398D3e9) establish the supported conditional method: `assetsOf == floor(sharesOf * sharePriceWad / 1e18)` values **effective active shares**, not gross House/Desk custody. Effective shares already include converted pending deposits and unmatured withdrawal notices. Add only:

1. The refundable pending USDG **before** its series has settled.
2. Matured notice shares times their own posted `exitPriceWad`, floored to raw USDG, **after** that series has settled.

Do not add a lingering converted `pendingOf` field, an unmatured notice or the vault's underlying again. Maturity means an earlier series, or the current series with `live == false`, never merely a scheduled date. Matured old-generation notices still use their stored exit price; they are not erased just because active shares rolled generations. Runtime hash and same-block getter identity are required; failure remains explicit instead of selecting whichever interpretation gives a convenient total.

### Morpho current accrual

The [official Robinhood deployment registry](https://docs.morpho.org/developers/contracts/addresses/) identifies the supported singleton and Adaptive Curve IRM. The collector implements the [v1.0.0 expected-market arithmetic](https://raw.githubusercontent.com/morpho-org/morpho-blue/v1.0.0/src/libraries/periphery/MorphoBalancesLib.sol), corroborated by [explorer-published singleton source](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x9D53d5E3bd5E8d4Cbfa6DB1ca238AEA02E651010). It reads the supported IRM's **view** `borrowRateView(params, storedMarket)` at the pinned timestamp, checking `MORPHO`; no `accrueInterest` or other state-changing call is used.

The rate is the interval-average rate returned by the [IRM](https://raw.githubusercontent.com/morpho-org/morpho-blue-irm/v1.0.0/src/AdaptiveCurveIrm.sol), not an instantaneous APR extrapolation. Three integer Taylor terms produce interest, which is added to borrow and supply assets. Protocol fee assets and minted virtual fee shares round down; supply conversion rounds down, borrow conversion rounds up with one virtual asset and one million virtual shares. New fee shares belong to the Sleeve only if pinned `feeRecipient == Sleeve`; missing attribution prevents the affected supply claim. Zero elapsed time, zero borrowing or zero IRM needs no rate. Unsupported IRMs remain explicit. Reports retains its dated stored-debt convention; adjusted assets replace that row with accrued debt, never subtract both.

### Known-universe completion is not exhaustive ownership

Supplemental Treasury/Sleeve inventories retain each candidate's provenance, direct owner/quantity verification and disposition (`included`, `excluded`, `unpriced`, `ownership_unresolved`, `uninspected`). Canonical Core custody and ERC4626/NFT receipts already represented by underlying claims are non-additive. Nonzero unknown tokens and unsupported NFT/claim semantics remain blockers, not invented assets or zero.

Owner incoming-Transfer and Morpho Supply/SupplyCollateral discovery search an explicitly disclosed recent **1,000,000-block window**, using bounded pages, plus catalog/live-menu/live-market seeds. Output retains searched and unsearched prior ranges, candidate limits, missing intervals and exact managers/custodians. Completed requested windows can support a conditional **known-universe** number; `all_assets_exhaustive` remains false. Earlier markets/transfers, other standards/managers and indirect custody can still exist. Provider failures, denials and integrity conflicts do not become empty history.


## Core recipe and integer units

Resolve the pointers in `assets/analytics/reserves-routes.json`. Read Treasury `rfv`, `liquidUsdg`, `morphoAssets`, `backingPerToken`, `net`, `usdg`, `morphoVault` and `canonicalPair`. The four value getters are **18-decimal wad**, independently of the underlying token decimals. Check code presence and the Treasury pointers against canonical routes; do not follow a mismatched address.

1. Read USDG `decimals` and `balanceOf(Treasury)`. Normalize the raw balance to wad.
2. Read the canonical Morpho vault's `asset`, `decimals`, `balanceOf(Treasury)` and `convertToAssets(shares)`. Require `asset == USDG`. Converted assets are USDG raw units, **not vault share units**. Normalize using the successful USDG decimal read, then apply the documented 200 bps haircut.
3. Read both pair token identities, `getReserves`, `totalSupply`, `balanceOf(Treasury)` and `decimals`. Require exactly USDG and NET; orient reserves by their actual identities. Read NET `decimals` and `totalSupply`.
4. Reconstruct with integer arithmetic, in this order:

```text
wad(q, d) = floor(q * 10^18 / 10^d)
x = wad(pair USDG reserve, USDG decimals)
y = wad(pair NET reserve, NET decimals)
POL = floor(2 * isqrt(x * y) * Treasury LP raw / total LP raw)
Morpho counted = floor(wad(converted assets, USDG decimals) * 9800 / 10000)
Core RFV = wad(Treasury USDG raw, USDG decimals) + Morpho counted + POL
NAV = floor(Core RFV * 10^NET decimals / NET totalSupply raw)
```

Do not round the LP ownership fraction first, substitute spot LP value, take the square root before decimal normalization, or apply USDG's decimals to Treasury wad getters. An empty pair with zero reserves and supply has zero POL; a nonempty pair with zero supply or a holding above supply is inconsistent. Zero NET supply leaves NAV undefined.

`core_rfv.reads` records each contract, getter, arguments, block, raw result and unit. Components reference those reads and expose cash, gross/countable Morpho, haircut and POL separately. `denominator` records NET supply and precision. `assembled` remains visible even on a mismatch; `reconciliation` compares all four Treasury getters and also checks reported RFV against backing per token. Signed `delta_raw` means **observed minus independently expected**, in wad. `relationships` reports incompatible identities. `look_through_memo` is proportional underlying reserve quantity only: it is not additive value, an executable redemption quote or a second reserve asset.

## Evidence boundaries

The [Treasury documentation](https://docs.netnet.capital/treasury) supplies the stated formula. The read-only fragment in `assets/analytics/reserves-interface.json` cites the dated app assets and ERC-4626 interface. Those sources are **interface/methodology provenance, not verified deployed Solidity**. The historical app asset may disappear; no runtime collection depends on fetching it.

The published Treasury interface exposes no Morpho haircut getter. The helper tests the documented 200 bps methodology against observed RFV, but snapshot equality does not prove that parameter is immutable or the implementation universally equivalent. Proving that requires applicable deployed source/runtime evidence. Likewise a successful `convertToAssets` does not promise immediately withdrawable cash.

Core scope does **not** enumerate unrecognized Treasury tokens, accidental transfers or every historical deployment. An outside-formula Treasury inventory is a separate investigation; do not imply that the three formula components are exhaustive custody. Sleeve, other contracts, liabilities, future obligations, beneficial ownership and USDG's USD peg are not proved by Core RFV. Values are in USDG unless an output explicitly supplies a different evidenced unit.

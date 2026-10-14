# SleeveBondDesk: exact generation and obtained contract semantics

This review concerns September 30 **SleeveBondDesk**, `0x732b3D1d3E8912CaE75164FA14a6E1c4C64615B3`, Robinhood Chain 4663. Its explorer-indexed creation is transaction `0x6517270f4acb4093fc3a391a069452be43b576b107591a0ca42e72309448393d`, block **76732423**, not the publisher rehearsal block 76730211. This is not RwaDesk V1 or V2. Their existing notes, claims and historical economics remain separate.

## Evidence strength

On October 10, the [exact-address explorer endpoint](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x732b3D1d3E8912CaE75164FA14a6E1c4C64615B3) supplied runtime and creation bytes, **not verified Solidity or ABI**. [Address metadata](https://robinhoodchain.blockscout.com/api/v2/addresses/0x732b3D1d3E8912CaE75164FA14a6E1c4C64615B3) reports `is_verified=false`, no proxy. Sourcify exact-address full/partial metadata endpoints returned 404. The obtained runtime is **13092 bytes**, SHA256 `a9530676de951374979dd16ca5ce237fc80f7ff8c18849370cd842bca6272c02`.

The complete publisher ABI literal has 37 functions; all their dispatcher branches and four additional unnamed branches received targeted static review. This is **not** independently compiled source equivalence, exhaustive symbolic execution or a security audit. The [full function catalog](../assets/contracts/sleeve.json) preserves exact inputs, outputs, selectors, access conditions and economic descriptions. [Source evidence](../assets/contracts/sleeve-bond-source-evidence.json) preserves hashes, locators and limitations, not third-party code or financial snapshots.

Canonical RPC was denied HTTP403/error1010 in this research session. No retries, alternate RPCs, live balances, permissions or history were obtained. Explorer source evidence is unpinned; a fresh collector must match code and confirm its snapshot before promoting totals.

## What a subscription actually does

1. `bond(usdgIn,maxPriceWad,rwaToken,swapCalldata,minRwaOut,to)` is public and nonreentrant; it rejects a halted desk, zero/desk recipient and guarded third-party note spam. A recipient subscribing to itself is distinct from a third party filling its note list.
2. Read Treasury backing through selector `0x1521843e`; raise stored `bHwm` only if backing is higher. Obtain the paired oracle quote through `0x10aa790e`. **No Treasury transfer is part of this step.**
3. Compute `priceWad = floor(oracleQuoteWad × (10000 − deskDiscountBps) / 10000)`. Reject when above buyer maximum, below `floor(bHwm × MIN_PREMIUM_WAD / 1e18)`, or below the additional manager-set slot-4 floor. The implementation **rejects**, rather than increasing the quoted price to the floor.
4. Allocate `payoutNET9 = floor((usdgInUSDG6 × 1e12) × 1e9 / priceWad)`. Payout must be nonzero, at least `1e7` raw NET (0.01 NET), and no more than unsold inventory. Decrease inventory; pull USDG from caller.
5. Look up the **caller-selected active menu token** and its canonical feed. Resolve the current router from the fixed RouterSource. Approve the subscription input, execute the supplied swap bytes and measure the desk's received equity delta. The contract does not select the most-underweight name from current custody positions.
6. Check the oracle-marked equity delta against the downside bound, transfer it to the fixed Sleeve, then require the Sleeve's measured equity increase to meet `minRwaOut`. `DeskBond.rwaOut` is that **measured Sleeve increase**, not the gross equity transfer or a display-share amount.
7. Any USDG above the desk's pre-subscription baseline is transferred to the **Sleeve**, not refunded to the buyer and not paid to Treasury. The desk requires its USDG baseline restored, clears router allowance, and requires its equity baseline restored.
8. Append the recipient's note, increase active-note count and `owedNet`, and emit `DeskBond`. The event's `fee` argument is **literal zero**. The subscriber receives a gross existing-NET vesting entitlement, not equity, shares in the Sleeve, immediate NET or a Treasury claim.

The current desk has no obtained mint or burn path. That proves a narrower statement than “every deposited NET was bought”: the funding source of earlier inventory acquisitions requires separate purchase/receipt evidence. Do not count a deposit, allocation or claim as a new NET mint; do not combine it with Core mint/burn accounting or book subscription capital as Core revenue.

## Units, rounding and immutable bounds

| Quantity | Unit and interpretation |
|---|---|
| `inventory`, `inventoryMax`, `owedNet`, note payout/claimed | NET raw9; `1e9` = 1 NET |
| `usdgIn`, subscription residual | USDG raw6; not native fiat USD |
| `bHwm`, price, slot-4 floor | WAD USDG per whole NET |
| `deskDiscountBps`, max discount/deviation | Basis points out of 10000 |
| `start`, `end`, `VEST` | Unix seconds / duration seconds |
| `rwaOut` | Equity token raw amount, not scaled UI shares or dollars |

Indexed runtime freezes `MAX_DISCOUNT_BPS=750`, `MIN_PREMIUM_WAD=1.2e18`, `INVENTORY_HARD_CAP=300e9` raw NET9 (**300 NET**, not 300 billion whole NET), `MAX_ORACLE_DEV_BPS=500`, `VEST=172800` seconds and USDG WAD factor `1e12`. Mutable launch values are **not** current observations.

The cap was re-decoded from the retained indexed bytes, not inferred from an economically plausible size: dispatcher selector `0xe52442cc` at byte `0x007b` targets `0x06b5`; `PUSH32` at `0x06b9` carries `0x00000000000000000000000000000000000000000000000000000045d964b800` (immediate bytes `[0x06ba,0x06da)`). The return helper `0x02d9–0x02eb` ABI-encodes that uint256. `0x45d964b800 = 300000000000`; dividing raw9 by `1000000000` gives **300 NET**. There is no demonstrated numeric transcription mismatch.

This is the immutable ceiling on **manager-set `inventoryMax`**, not a quote-price, USDG-input, lifetime-sale or total outstanding-note cap. `setInventoryMax(uint256)` (`0x3d17c5ab`, body `0x0f8e`) compares the input with the same `PUSH32` constant at `0x0fd8`, reverting above it and storing accepted input in slot 5 at `0x101d`. Deposits compare the measured NET receipt plus unsold inventory (slot 1) against slot 5 at `0x134d–0x1363`. Bonds instead compare their raw NET9 payout against available slot-1 inventory at `0x09c1–0x09cb`, then subtract it; they do not apply a separate hard-cap quote guard. Replenishment can therefore support cumulative sales above 300 NET, and `owedNet` is a separate liability rather than part of this deposit ceiling. These are static branch semantics, not observations of current inventory or liabilities.

The oracle guard uses 18-decimal raw equity arithmetic: `floor(deskEquityDelta × unitPriceWad / 1e18) >= floor(usdgIn × 1e12 × (10000−500) / 10000)`. This is a downside oracle-value bound, not best execution, symmetric slippage, USDG parity, guaranteed stock liquidity or proof of the external feed's accuracy. Token units and scaled UI require their own evidence.

## Inventory, claims, cancellation and leftovers

- `depositInventory(amount)` permits the immutable **Manager or Sleeve**. It credits the actual NET balance increase, checks resulting inventory against `inventoryMax`, and checks custody covers inventory plus owed claims. Nominal input may differ under token transfer taxes.
- `inventory()` is unsold allocation. `owedNet()` is the **global gross unpaid liability**, including unvested amounts. Their sum is not a lifetime issuance counter. NET donations can create surplus without increasing either.
- `noteCount(account)` is append-only note count, including fully claimed notes. `noteAt(account,i)` returns payout, claimed, start, end. It is not the active-note mapping exposed by an unnamed selector.
- `pendingFor(account)` loops the account's notes and returns total unpaid NET and currently claimable NET. Before maturity, vested NET is `floor(payout × (timestamp−start)/(end−start))`; at/after end it is full payout. Claimed amount is subtracted. Large account arrays can make reads expensive or fail.
- Both `redeem(to)` and `redeem(to,noteIds)` operate on **msg.sender's notes**. They update per-note claims, emit `DeskRedeemed` for positive claims, decrease `owedNet`, and transfer aggregate gross NET to `to`. The selective form is the bounded alternative to all-notes redemption. Repeated ids cannot double-pay after the first update. A gross claim is not necessarily net receiver delivery under external NET transfer behavior.
- `halted` is checked on new bonds, **not on redemption**. It does not cancel notes or establish historical inactivity.
- No obtained function cancels an issued note or refunds subscriber USDG. Reverting an unsuccessful atomic subscription is not a successful subscription refund. The unnamed inventory withdrawal does not touch `owedNet` or cancel subscriber claims.
- `skim(token)` is a permissionless trigger with a **fixed Sleeve beneficiary**. For NET, it transfers only custody surplus above inventory plus owedNet, reverting if underfunded. For another token, it transfers the desk's whole balance. It is not a caller-owned refund mechanism.

## Four unnamed dispatcher selectors

Names have **not** been recovered. These entries remain descriptive evidence, excluded from callable analytics ABI. Runtime shape/effects do not authorize fabricating a signature.

| Selector | Targeted runtime finding |
|---|---|
| `0x083893e1` | One uint256-shaped input; Manager or Sleeve only, nonreentrant. Subtracts no more than unsold inventory, transfers NET to fixed Sleeve, and checks custody still covers inventory+owedNet. This establishes an **unsold inventory withdrawal** path absent from the reused ABI. |
| `0x14ae9e4e` | Address-shaped input; returns slot-9 per-account **active-note count**. Bonds increment it; fully redeemed notes decrement it. |
| `0x5ea8cd12` | Manager-only uint256-shaped setter for slot-4 **additional WAD price floor**, with an event. No upper bound identified in this branch. |
| `0xb8fea0a1` | No-input getter for that slot-4 floor. |

Exact entry/body offsets and unnamed event topics are in the evidence asset. No speculative function names are used for read calls or calldata.

## All remaining obtained functions and authority

`manager`, `sleeve`, `net`, `usdg`, `treasury`, `pairOracle`, `feedAdapter`, `routerSource` expose fixed bindings. Manager is the Team Safe; Sleeve is a separate dedicated Safe. Fixed addresses do not establish today's owners, thresholds, modules, token minters, router governance or safety. No desk-level manager-transfer, minter-management or subscriber equity-redemption function was obtained.

`setDiscount` is Manager-only and bounded by the immutable maximum; `setInventoryMax` is Manager-only and bounded by hard cap (lowering it need not liquidate existing inventory); `setHalt` is Manager-only. `setMenu` is Manager-only: active entries must be nonzero and match constructor-fixed `canonicalFeed(token)`, duplicate active tokens are rejected, and entry weights total 10000. It replaces configuration, not existing Sleeve holdings. `menu`, `menuLength`, `isActiveMenuToken`, `canonicalFeed` expose configuration, not historical asset discovery. `pokeHwm` is public and only raises backing HWM; `bondPrice` returns the discounted quote without guaranteeing all fill guards. All immutable/mutable getters and both redemption overloads remain separately represented in the catalog.

### RouterSource: obtained source, qualified verification

[Exact RouterSource endpoint](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x9ca38c9c144ff411231c82da03c7d30286a7dbf6) supplied `RwaAdapters.sol` and three supporting files. Explorer says verified **but partially, not fully**, with no independent compiler rebuild here. The obtained constructor rejects zero registry; `registry()` and `routerTokenId()` expose immutable bindings; `router()` returns `registry.ownerOf(routerTokenId)`. The indexed bindings are registry `0x71a120CbBf3Ce7cD910a3c50fF77aFc62735687E` and token id 2. There are no RouterSource setters. Registry-controlled router resolution and its reverts are external dependencies. [Complete obtained ABI/catalog](../assets/contracts/sleeve-router-source.json).

### Current feed adapter is not the old source beside RouterSource

The [exact current adapter](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x55e76ba1f7c7603c27bbdf8dfa1b235f7e512540) supplies runtime, not source/full ABI. The obtained interface establishes `priceWad(address feed,address token)`; its current runtime separately requires positive answer, complete round, nonfuture update and age **at most 345600 seconds (four days)**. It reads `token.uiMultiplier()`, accepting **0.8e18 through 1.2e18**, then returns `floor(answer × 10^(18−feedDecimals) × multiplier / 1e18)`; feed decimals over18 fail arithmetic. Its other three getter names remain unresolved.

The RouterSource compilation includes an **older sibling RwaFeedAdapter** with session-dependent age and identity-only multiplier. That is not exact-address source for `0x55e...`. Likewise its sibling DeskMath Treasury fee helper is not evidence that the current SleeveBondDesk remits a fee. Never transplant those old source bodies to this generation.

## Documentation disagreements and accounting boundary

[Current official Real World Bonds docs](https://docs.netnet.capital/rwa-desk) correctly distinguish zero Treasury fee, pre-funded inventory, two-day vest and unsold withdrawals. They also describe both buyer selection and “most underweight” purchases, and ambiguously describe a maximum-of-price/floor guard. The reviewed runtime supports **buyer-selected active token and rejection below guards**, not an onchain rebalancer or floor-clamped quote. “Whole amount buys equities” needs the residual-USDG qualification above. Historical V1/V2 remittance formulas and no-withdrawal descriptions do not apply here.

The Sleeve's equities may be posted to Credit and financed with debt; gross custody, pledged collateral, debt/interest and spendable surplus are different quantities. Reuse existing [reserve/Sleeve accounting](reserve-analytics.md); do not add subscription receipts or gross managed assets to Core RFV. Core certification has separate block-specific requirements. See [fresh Sleeve bond analytics](sleeve-bond-analytics.md) for supported questions and coverage.

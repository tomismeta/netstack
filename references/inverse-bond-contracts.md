# InverseBond: standing bid, burn and Treasury expenditure

Explain user-operated mechanics without operating a wallet. The catalog's write function supports behavioral and procedural explanation, not signing, approval, submission or ready-to-submit artifacts. Read-only quotes and isolated non-broadcasting simulations remain permitted under the [guardrail](guardrail.md). Use [fresh InverseBond analytics](inverse-bond-analytics.md) for quotes and history, and [protocol-wide revenue accounting](protocol-revenue-analytics.md) for consolidation.

## Identity and evidence strength

InverseBond is chain 4663 [`0x92166e94Eea5B7799b761653881692f881dFC4C9`](https://robinhoodchain.blockscout.com/address/0x92166e94Eea5B7799b761653881692f881dFC4C9). On October 12, 2026 the [explorer response](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x92166e94Eea5B7799b761653881692f881dFC4C9) provided the complete source and eight dependency compilation files, a 22-entry ABI, creation bytecode, indexed runtime and constructor arguments. All nine files were reviewed. The [canonical catalog](../assets/contracts/inverse-bond.json) preserves all **13 functions, seven errors, one event and one constructor**, superseding the five-function publisher literal as the obtained interface. `spreadBps` is actually `pure`, not the prior literal's `view`.

[Portable evidence](../assets/contracts/inverse-bond-source-evidence.json), source ID `netnet-inverse-bond-implementation-20261012`, contains original analysis, hashes, source-line locators and compiler correlation. Third-party Solidity, response JSON and compiler input/output are retained outside the runtime package; no financial snapshots, transaction roster or event history are shipped.

- Explorer reports full verification and no proxy implementation. That alone is provider evidence, not an audit.
- An independent **solc-js 0.8.30+commit.73712a01** compilation used all supplied source paths and exact settings: Osaka, optimizer 800 runs, no via-IR, original metadata options and remapping. No compiler diagnostics were returned. Its ABI exactly matches; creation bytecode exactly matches the indexed prefix, followed by the five address arguments.
- The independently compiled runtime matches **all 3,241 indexed runtime bytes**, including metadata, after replacing **only the 17 compiler-declared immutable words**. All occurrences of each immutable agree: five address bindings match constructor arguments, and the cached USDG WAD factor is `10^12`. This is explicit immutable-patched correlation, not an unmodified-template equality claim or an independent constructor execution.
- Runtime SHA-256: `fdd6194fdfc5960d7e78287f434e593145ee83378b7a019f2a7457e1ea4e7acd`. All 13 instruction-boundary dispatcher branches match obtained ABI functions. Unknown/short calldata and native value revert. No fallback, receive, owner, setter, rescue, arbitrary-call or upgrade path exists in this obtained contract.

These compiler results strengthen the source-to-**explorer-indexed**-bytecode association. A separate October 12 read-only probe matched InverseBond and the four reviewed dependency runtime hashes at [block 86,729,870](https://robin.etherscan.io/block/86729870), hash `0xbf38fafe943e7adbabe1aaa204ec1d7a559f8a0b3948791f5f81ec85089cc50d`, with a confirmed header recheck. Only durable code-identity evidence is retained; current balances, permissions, quotes and oracle observations must be fetched afresh. Neither compiler correlation nor this pin establishes historical permissions, USDG/vault settlement behavior, complete dependency compiler equivalence, security or economic correctness. Relevant actual Treasury, NET, PairOracle and GenesisBond bodies—not only interfaces—were separately read below.

## Successful fill, in actual order

1. Reject `netAmount == 0`; require GenesisBond `finalizeTime()!=0`.
2. Call PairOracle `twapNetUsdg()`. Failure propagates. Its value is discarded: this is an oracle-liveness gate, **not** the payout price and not a requirement that market price be below backing.
3. Read Treasury backing and compute the discounted price; full-precision `mulDiv` floors the NET amount's WAD payout.
4. Compute the genesis-anchored epoch. If its stored cap is zero, store the live cap. Require payout no greater than remaining cap, then increment that epoch's filled WAD.
5. Floor the WAD payout into raw USDG. Reject only if below the caller's `minUsdgOutRaw`.
6. Pull the **gross requested NET** from the caller to InverseBond, checking the Boolean return. Burn that same gross amount from InverseBond.
7. Call Treasury `spendUsdg(caller,rawOutput)`, then emit `InverseBonded(caller,grossNet,payoutWad)`.

Every preceding mutation and transfer rolls back if a later dependency reverts. There is no vesting claim or lingering per-seller obligation on successful settlement. There is no explicit reentrancy modifier in InverseBond; accounting is updated before token calls, but that is not a full reentrancy/security proof. The contract does not check a post-fill NAV invariant or measure either its NET receipt or the seller's USDG balance delta.

## Units and exact rounding

Let `N` be raw NET (`1e9` per whole NET), `B` Treasury-reported backing in WAD USDG per whole NET, `L` liquid Treasury USDG in WAD, `F` the cached USDG conversion factor (`1e12` in the indexed deployment), `T` the pinned block timestamp, and `G` Genesis `finalizeTime`.

```text
epoch       = floor((T - G) / 28800)
priceWad    = floor(B * 9850 / 10000)
payoutWad   = floor(N * priceWad / 1e9)       # full-precision mulDiv
liveCapWad  = floor(L * 100 / 10000)
capWad      = stored cap if nonzero, otherwise liveCapWad
remaining   = max(capWad - filledInEpoch[epoch], 0)
require payoutWad <= remaining
outputRaw   = floor(payoutWad / F)
require outputRaw >= minUsdgOutRaw
```

The **150 bps spread is 1.5% below reported backing**, not a separately collected fee, income or guaranteed absolute USDG price. `price()` can return zero and can return successfully before genesis or while the oracle is invalid. Backing multiplication by 9850 and liquid multiplication by 100 use checked 256-bit arithmetic, not `mulDiv`; overflow can revert. Epoch subtraction and filled addition are checked too. Dependency failures and Solidity panics are additional failures beyond the catalog's seven custom errors.

**Only zero NET input is explicitly rejected.** There is no nonzero price, WAD payout, raw USDG output or protocol minimum-USDG guard. With a zero caller minimum, nonzero NET can burn for zero raw USDG if all dependencies permit. Even `payoutWad==0` can succeed with no remaining budget, although `active()` would be false. A positive cap can become fixed by a successful zero-output fill; a zero cap remains the sentinel and can be recomputed later. A positive caller minimum prevents zero output but cannot guarantee execution or future price.

For each successful fill, `residualWad = payoutWad - outputRaw*F` lies in `[0,F-1]`. It consumes budget although no corresponding USDG raw unit is requested. For multiple fills, **sum each fill's floored raw output**, not `floor(sum(payoutWad)/F)`. Event WAD and actual USDG transfer totals can legitimately differ by these per-fill residues.

For `priceWad>0`, the exact budget-only maximum raw NET amount is `floor(((remaining+1)*1e9-1)/priceWad)`, capped at the uint256 input limit. Compute it off-chain with arbitrary-precision integers; this incorporates the first payout floor and is not an executable maximum. Funding, minimum, allowance, tax and settlement remain separate. At zero price no finite budget-derived maximum exists; do not divide by zero or present a useful sell quote.

## Epoch budget is not current cash

Epoch zero starts at **GenesisBond's successful finalization timestamp**, not midnight, deployment time or the Staking epoch number. Eight-hour boundaries are `G + k*28800`. There is no cooldown or limit on fills per epoch except its WAD budget.

The live budget is **1% of liquid, non-Morpho Treasury USDG**, not 1% of total RFV, pool reserves, supply or all USDG including vault assets. Before a nonzero snapshot, views use current liquid reserves. The first successful fill snapshots the budget; failed fills roll it back. Once nonzero, mid-epoch inflows cannot inflate it, outflows do not shrink it, and later cash changes do not replenish used capacity. Each new epoch starts fresh; **unused capacity does not roll over**. These are separate concepts:

- `capOfEpoch(k)`: stored budget; zero means use live reading, not necessarily a historical zero-budget assessment.
- `filledInEpoch(k)`: successful cumulative **payout WAD**, not amount burned, cash paid or fill count.
- `capacityRemaining()`: remaining current-epoch WAD budget, not a reserved cash balance.
- Treasury liquid cash and ERC4626 withdrawal ability: determine payment funding separately.

A zero `filledInEpoch` does not prove no fill: zero-WAD-payout burns do not increase it. Nonzero filled state contradicts a purported complete epoch log scan reporting no fills. These mappings are not a lifetime counter and do not enumerate themselves.

## Activation and complete obtained surface

| Function | Selector | Meaning |
| --- | --- | --- |
| `active()` | `0x02fb0c5e` | Genesis timestamp nonzero, oracle external self-call succeeds, remaining budget positive. Not full quote eligibility. |
| `capOfEpoch(uint256)` | `0x57207fa0` | Stored WAD budget at an explicit index; zero sentinel. |
| `capacityRemaining()` | `0xbf6f3bf3` | Current WAD remaining; zero before finalization; no oracle or price gate. |
| `filledInEpoch(uint256)` | `0x544b9b9f` | Stored payout-WAD usage by explicit index. |
| `genesisBond()` | `0x748a0ab0` | Immutable finalization/epoch-origin dependency. |
| `net()` | `0xc2fff4a5` | Immutable gross pull/burn token. |
| `oracle()` | `0x7dc0d1d0` | Immutable liveness dependency. |
| `oracleGate()` | `0xd8862a5c` | Public unrestricted view forwarding oracle TWAP; not only-self. |
| `price()` | `0xa035b1fe` | Current discounted Treasury-reported backing in WAD. |
| `spreadBps()` | `0x6dd5635d` | Pure 150-bps constant. |
| `swap(uint256,uint256)` | `0xd96073cf` | Permissionless gross NET burn/Treasury payment; descriptive write surface only. |
| `treasury()` | `0x61d027b3` | Immutable backing/cap source and payment intermediary. |
| `usdg()` | `0xf5b91b7b` | Immutable token binding used to cache conversion at construction. |

`active()` catches **only** its external self-call to `oracleGate`; initial Genesis reads and subsequent epoch/capacity computation can still revert. It does not call `price()`, test a user's amount/minimum/balance/allowance, or check Treasury spender status, withdrawability, NET tax receipt, USDG transfer restrictions or successful burn. A true result is not a settlement warranty; false is not proof of never-used or permanently unavailable.

The five-address nonpayable constructor rejects zero addresses and caches `10^(18-USDG.decimals())`. Decimals above 18 panic; metadata-call failures propagate. It does not validate NET decimals, dependency implementations/wiring, matching Treasury tokens/oracle pair or spender authority. There is no owner initialization. Internal `_epochIndex`, `_liveCap` and `_capacityRemaining` implement the formulas above. `FixedPointMath.mulDiv` is used directly; its `mulDivUp` and `sqrt` were read but are not InverseBond entrypoints or direct calls.

Errors: `ZeroAmount` (NET input only), `NotActive` (unfinalized genesis), `ExceedsCapacity` (strictly greater WAD payout), `SlippageExceeded` (raw output below supplied minimum), `TransferFailed` (NET pull returns false), `ZeroAddress` (constructor), imported `MulDivOverflow` (unrepresentable quotient). Equality at cap/minimum passes. External error payloads, malformed returns and arithmetic panics can propagate independently.

## Actual dependency paths and trust boundaries

### Treasury payment and the original RFV blocker

The [actual Treasury source](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x04822Ea321A0DEE6F40656172F29312104855d66) checks `wired` and `isSpender[InverseBond]`. Its one-time deployer `wire` takes arbitrary nonzero arrays; a comment naming InverseBond does not prove the installed roster. `spendUsdg` reads raw USDG cash; if insufficient, it calls the immutable ERC4626 vault's `withdraw(shortfall,Treasury,Treasury)`, emits `MorphoWithdrawn`, then transfers the requested raw amount to the seller, checks Boolean success and emits `UsdgSpent(InverseBond,seller,raw)`.

This auto-unwind is a **code path, not guaranteed redemption liquidity**. The vault or USDG can reject settlement; a vault `convertToAssets` value is not immediately available cash. Treasury does not measure seller receipt. USDG proxy implementation, upgrade/pause/restriction state and vault behavior need fresh/historical evidence as applicable. Treasury's permissionless rebalancing can change cash without changing a previously fixed InverseBond budget.

Obtained Treasury backing is zero for zero NET supply, otherwise `floor(rfv()*1e9/totalSupply)`. Its current indexed source computes `rfv` with `floor(M*9800/10000)` plus cash and geometric POL; **this differs from the user's validated subtract-floored haircut** `M-floor(M*200/10000)`. Its POL source scales raw NET by `1e9` and raw USDG by its cached factor before integer square root and LP fraction. These observations are not permission to replace known-good arithmetic or to resolve the original **18,432.08 USDG POL discrepancy** with a new block or residual identity. The original validation block/hash/raw/runtime packet remains missing. See [Core evidence boundaries](reserve-analytics.md#evidence-boundaries). A fresh direct `backingPerToken()` observation may be quoted as contract-reported backing, but not independently certified reconstructed RFV/NAV.

### NET gross pull, tax and burn

The [actual NET source](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xCA9c78Dd337A67F6e0077F65F5E9218719d30eDf) spends **gross allowance** in `transferFrom` (unlimited allowance is unchanged), checks the gross sender balance, then applies tax only if enabled, neither endpoint is exempt and either endpoint is mapped as a taxed pair. Tax is `floor(gross*500/10000)`; when nonzero the tax transfer and `TaxCollected` precede the remaining seller→InverseBond transfer. Do not blindly assume 5%, 0%, or an exemption from product naming.

`burn` is permissionless from its caller, not Treasury-only; it checks the caller's balance, subtracts the amount and total supply, emits `Transfer(InverseBond,zero,amount)` and applies no transfer tax. InverseBond burns gross requested NET without measuring the pull. If a taxed pull delivered less, burning gross ordinarily fails—but **pre-existing NET at InverseBond can cover the shortfall**. A successful gross burn therefore does not by itself prove that this seller delivered the gross amount. Initial wiring can pre-map addresses and exemptions; actual current/historical state and receipt legs must establish the case. Never silently assign a donation-funded shortfall to the seller or count a separate NET tax leg as USDG proceeds.

### Oracle and genesis

The [actual PairOracle source](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x929631b33F4070D6f54477fba3FD27566567dAca) maintains 16 timestamp-bucketed observations. `checkpoint` ignores zero reserves or spacing under 1,800 seconds; it otherwise stores a counterfactual cumulative. The read selects the **newest** nonzero observation at least 1,800 seconds old, rejects none or age above 14,400 seconds, takes the wrapping cumulative difference divided by elapsed time, scales UQ112 into WAD, and rejects a zero result. Both window endpoints are inclusive. Future observations can cause checked subtraction failure. Counterfactual current cumulative uses selected pair reserves and wrapping uint32 elapsed time. There is no separate spot/TWAP deviation test here. Valid TWAP does not establish manipulation immunity, current spot liquidity or the payout price. InverseBond does not call `checkpoint`; read-only research must not do so either.

The [actual Genesis source](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0x575b7B7c97Ef3E21C82DAeB427899d583e1E913f) sets its initially zero uint64 `finalizeTime` once in `finalize`: wired, not already finalized, and hard cap hit or post-deadline minimum raise. The timestamp, Treasury transfer, pair seed, issuance, enablement and first oracle checkpoint occur atomically; later failure rolls them all back. No timestamp setter/reset exists. First finalization does not make the just-created oracle observation immediately old enough to be valid.

## NAV accretion: conditional mathematics, not an unconditional guarantee

Source comments claim every fill is strictly accretive. For an unchanged valuation convention, positive reserve value `R`, raw NET supply `S`, actual gross burn `0<N<S` and true reserve decrement `q`, exact backing increases when `q < R*N/S`, because `(R-q)/(S-N) > R/S`. Discounting the pre-fill reported backing and flooring the USDG output is consistent with that inequality **under those assumptions**; it is not a fee earned or cash profit.

The implementation has no assertion enforcing that model after settlement. Integer displayed backing can remain unchanged after a small favorable fill; `R==0` defeats strict positive-value accretion; burning the entire supply makes the Treasury backing getter return zero instead of the ratio. Vault haircut release, valuation movement, token transfer behavior, extra taxed NET movement, dependency errors and the unresolved original POL evidence must be separated from the simple model. A USDG cash outflow and lower reserve total can coexist with higher backing per remaining token. Neither label proves economic profit, fiat-dollar realizability or an unconditional redeem-at-NAV floor.

## Revenue and consolidation classification

InverseBond is **reserve expenditure plus own-token supply retirement**, not earned product revenue. Treasury is the payer; the indexed seller is the payee. InverseBond receives/burns NET, not new reserve consideration. Morpho→Treasury withdrawal is internal reserve funding; it is neither a second payout nor newly earned yield merely because cash arrived. `InverseBonded`, Treasury `UsdgSpent` and USDG `Transfer` are evidence of the same payment, not additive flows. The 150-bps spread is not a separate cash fee and does not distribute USDG to holders.

Keep buybacks visible in a broader cash-flow/proceeds report as outflows, alongside—but distinct from—earned fees/interest/underwriting results, PremiumSeller issuance financing, subscriptions and internal remittances. No protocol-wide net-profit conclusion follows from this contract alone.

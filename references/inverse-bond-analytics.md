# Fresh InverseBond quotes, burns and Treasury payments

Use this read-only supplemental procedure for current standing-bid questions, an explicit NET amount, a date interval, a particular epoch or historical buyback accounting. It is **not a bundled InverseBond helper CLI** and does not claim that one exists. The catalog describes all obtained functions; that is not permission to call write functions. Do not approve, sign, submit, fund, checkpoint the oracle, invoke `swap`, or construct a ready-to-submit transaction. General public RPC/explorer/source research can extend beyond bundled helper limits with disclosed provider limits and coverage.

Start with [contract semantics and exact rounding](inverse-bond-contracts.md), [the descriptive ABI](../assets/contracts/inverse-bond.json) and [original source/compiler evidence](../assets/contracts/inverse-bond-source-evidence.json). Evidence was inspected on October 12, 2026; present state must be read afresh. No observed balances, quotes, burns, payment totals, activity roster or historical financial series are stored in this reference.

## Establish a pinned read context

1. Resolve chain identity (`eth_chainId == 4663`), a sufficiently confirmed endpoint block, its number/hash/timestamp and provider. Every related call uses that same explicit block tag; use block-hash pinning where supported or numeric tags with end-of-run header rechecks. A batch is not automatically an atomic/latest-block snapshot.
2. Read InverseBond `eth_getCode` at that block. Compare byte length and SHA-256 of decoded bytes to the evidence's indexed-runtime identity. A mismatch is new implementation/identity evidence to investigate, not a reason to decode against a familiar ABI or substitute cached state. Equality associates this read with the reviewed InverseBond runtime; it does not pin all external dependencies.
3. Read the five immutable getters and verify exact bindings below. Fetch dependency code at the same block and distinguish reviewed source/indexed runtime from freshly matched code. Verify Treasury and Genesis tokens/pair/oracle bindings, NET wiring, and oracle pair. Do not infer address wiring from UI labels.
4. Read failures, empty return data, decoding failure, unsupported historical calls or timeouts are **unavailable/inconsistent**, not numerical zero or boolean false. Preserve sanitized call-specific errors/revert identities, never credentials or private endpoint details. Stop the affected retrieval on access denial; finish independent authorized reads where meaningful without treating a partial collection as complete.
5. Recheck the pinned block hash before presenting results; invalidate/recollect on a mismatch. A current quote is only for that block, not a promise for a later execution.

| Inverse getter | Expected indexed binding |
| --- | --- |
| `net()` | `0xCA9c78Dd337A67F6e0077F65F5E9218719d30eDf` |
| `usdg()` | `0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168` |
| `treasury()` | `0x04822Ea321A0DEE6F40656172F29312104855d66` |
| `oracle()` | `0x929631b33F4070D6f54477fba3FD27566567dAca` |
| `genesisBond()` | `0x575b7B7c97Ef3E21C82DAeB427899d583e1E913f` |

These are static identity expectations, not current financial observations.

## Safe view ABI and read order

The complete obtained ABI supplies the following minimal read surface. All calls here are `view`/`pure`; no write-function simulation is needed to produce a conditional quote.

**InverseBond:**

```text
net() -> address                      treasury() -> address
usdg() -> address                     oracle() -> address
genesisBond() -> address               spreadBps() -> uint256 [pure]
active() -> bool                      oracleGate() -> uint256
price() -> uint256                    capacityRemaining() -> uint256
capOfEpoch(uint256) -> uint256         filledInEpoch(uint256) -> uint256
```

**Relevant actual dependency views:**

| Dependency | Safe functions | Reason |
| --- | --- | --- |
| GenesisBond | `finalizeTime()->uint64`, `finalized()->bool`, `wired()->bool`, `net()->address`, `usdg()->address`, `treasury()->address`, `pairContract()->address`, `oracle()->address` | Finalization clock and cross-wiring; no `finalize` call. |
| Treasury | `wired()->bool`, `isSpender(address)->bool`, `net()->address`, `usdg()->address`, `morphoVault()->address`, `canonicalPair()->address`, `liquidUsdg()->uint256`, `backingPerToken()->uint256`, `rfv()->uint256`, `morphoAssets()->uint256`, `polRfv()->uint256` | Authorization and reported values; last three are optional diagnostics, not independent resolution of Core RFV. |
| NET | `decimals()->uint8`, `totalSupply()->uint256`, `balanceOf(address)->uint256`, `allowance(address,address)->uint256`, `wired()->bool`, `treasury()->address`, `genesisBond()->address`, `taxEnabled()->bool`, `taxCollector()->address`, `isTaxedPair(address)->bool`, `isTaxExempt(address)->bool` | Units, available NET, existing InverseBond NET, allowance and exact endpoint tax conditions. No approval or burn. |
| USDG | ERC20 `decimals()->uint8`, `balanceOf(address)->uint256`; proxy implementation identity/storage as applicable | Current decimals/cash versus immutable cached factor; token policy is a separate trust boundary. |
| PairOracle | `pair()->address`, `pairContract()->address`, `netIsToken0()->bool`, `priceScale()->uint256`, `lastCheckpointAt()->uint64`, `twapMinWindow()->uint256` and `twapMaxWindow()->uint256` [pure], `twapNetUsdg()->uint256`, `observations(uint256)->(uint32 timestamp,uint256 priceCumulative)` for indices 0–15 | Distinguish no eligible observation, too-young, stale, zero price or dependency failure. Last checkpoint alone is insufficient: a newer observation may be too young while an older one is valid. |
| Treasury's pair | Source/interface-evidenced `token0`, `token1`, `getReserves`, cumulative getters, `totalSupply`, `balanceOf(Treasury)` | Pair alignment and optional counterfactual TWAP/backing diagnostics; discover and verify implementation, do not assume every same-shaped address is canonical. |
| Treasury's vault | Verified ERC4626 `asset`, `balanceOf(Treasury)`, `convertToAssets(shares)`, `maxWithdraw(Treasury)` when its actual implementation supports them | Distinguish value from withdrawal capacity. A reported maximum still does not guarantee later settlement or token delivery; no withdrawal transaction. |

Treasury spender read uses **InverseBond** as its address argument. If an account-specific quote was requested, read NET balance and allowance for that account with spender InverseBond, and map/exemption status for **both** sender and InverseBond. Otherwise leave wallet-specific checks not requested/unknown; do not request a wallet merely to explain protocol price or budget. Check InverseBond's NET balance separately because it can subsidize a taxed pull's gross burn. Current `isSpender`, tax flags and proxy state are not historical permission proof.

Obtain `G=finalizeTime`, then use the **pinned header timestamp** `T`. If `G==0`, report pre-finalization with capacity zero by code; do not invent an epoch from `T/28800`. If `G>T`, mark inconsistent/future clock instead of unsigned subtraction. Otherwise derive `k=floor((T-G)/28800)`, its start/end, read the two mappings for `k`, then `capacityRemaining`, `price`, `spreadBps`, `active` and `oracleGate`. Compare capacity using stored cap or the same-block live liquid cap, not the current cash balance directly. Preserve zero cap as the unsnapshotted sentinel.

## Quote presentation: reported price, conditional amount

For a supplied NET amount, require exact raw9 conversion without floating-point loss. Report:

- Pinned block/hash/time, dependency/code-match scope and call failures.
- Treasury-reported backing, `priceWad`, spread, finalization time, derived epoch boundaries, stored cap, live fallback if needed, filled WAD and remaining WAD.
- Input raw9/whole NET; `payoutWad=floor(N*priceWad/1e9)`; `outputRaw=floor(payoutWad/1e12)`; whole USDG `outputRaw/1e6`; residual WAD. Use cached runtime conversion for contract arithmetic and separately flag conflicting fresh token decimals.
- Whether the **WAD** payout fits budget; do not compare raw USDG directly with WAD capacity. Equality fits.
- If provided, whether raw output meets the user's stated minimum. Do not choose or lower a minimum for the user.
- Separate oracle status, Treasury spender/wired evidence, raw Treasury cash, potential vault shortfall and account balance/allowance/tax checks. Unknown settlement conditions remain explicit.
- A prominent warning for zero price, zero WAD payout or zero raw output. A positive NET input can burn for zero USDG under source semantics with a zero minimum. `active()==true` neither prevents this nor guarantees price computation; `active()==false` from zero capacity does not rule out zero-WAD-payout burns.

A result is **a conditional same-block read-only quote**, not a guaranteed sellable amount, execution preview, redeem-at-NAV right, recommendation or fiat-dollar cash claim. Keep contract-reported backing distinct from independently reconstructed RFV, which requires [block-specific validation](reserve-analytics.md#evidence-boundaries). Fresh direct views and compiler correlation alone do not certify reconstruction or resolve the historical discrepancy.

## Hypothetical models and state overrides

Keep three outputs separate: **observed same-block views**, an **offline hypothetical model**, and any **hypothetical state-override `eth_call`**. Prefer the offline model: retain the pinned baseline, name every assumed change (backing, liquid cash, epoch, stored cap/filled amount, supply or NET input), and apply the [exact integer recipe](inverse-bond-contracts.md#units-and-exact-rounding). Changing liquid cash does not reset an already nonzero epoch cap; changing a quote assumption is not evidence that the oracle, spender, funding or token-transfer conditions pass. Multi-fill scenarios must update cap, filled WAD, cash and supply under stated assumptions rather than multiply one quote. A NAV scenario additionally needs the [conditional reserve-decrement assumptions](inverse-bond-contracts.md#nav-accretion-conditional-mathematics-not-an-unconditional-guarantee); it is not independent Core certification.

An authorized external client may use a provider-supported state override with `eth_call`, separately labelled hypothetical, when its isolated non-broadcasting behavior is established under [the governing simulation policy](guardrail.md#calculations-forecasts-and-simulations-are-allowed). The documented view/pure surface is sufficient for conditional quotes; an established isolated simulation of a state-changing method is also permitted when it cannot mutate the live chain/node, impersonate a real wallet, sign or submit. This is not a bundled runner capability and does not widen its curated method/ABI allowlist. No real wallet credentials, connection, approval, execution-ready transaction artifact or actual swap/broadcast is permitted. Missing override support is a capability gap for independently authorized research; an access denial ends that retrieval and must not be bypassed.

Record the base chain/block/hash, target interface, raw research arguments, provider override dialect and every overridden address/field/value, alongside the unmodified baseline and hypothetical result. Storage-slot overrides require applicable, independently evidenced layout/implementation; never guess slots or treat source comments as layout proof. Code overrides replace the dependency being measured, so their results establish only the assumed model, not deployed behavior. Do not silently alter time/block context or pretend a state override advances an epoch. Overrides are ephemeral assumptions, not on-chain observations, valid current quotes, historical evidence or proof a fill can settle; no override call was executed for this reference.

## Historical interval, epoch and lifetime coverage

Ask the evidence question precisely: successful fills, gross NET burned, event-reported WAD budget used, requested raw USDG, receipt-confirmed USDG delivery, or net reserve change? They are not the same metric. A quote is not a past fill and current capacity is not lifetime volume.

For an interval, derive block boundaries from pinned canonical headers and disclose inclusivity, any partial boundary blocks and timestamp filtering. For an epoch, use the genesis timestamp origin and its exact eight-hour interval. For lifetime claims, first discover and independently validate the canonical creation receipt/block/header and code identity; the first observed event is **not** the creation boundary. Scan every required block from that boundary through the pinned end, following explicit provider range/page limits. Record searched, unsearched, failed and truncated intervals and whether receipts and headers were reconciled. Do not silently use a recent slice as lifetime.

Parent/operator RPC plans can have a ten-block `eth_getLogs` cap; adapt page size rather than treating that limit as proof of absent older activity. A smaller completed interval is useful if it is labeled as such. Supplemental authorized research is not constrained to a helper's unrelated default lookback, but unresolved provider errors or practical incomplete coverage must not disappear from the output.

Filter emitter **InverseBond** and topic0:

```text
InverseBonded(address,uint256,uint256)
0x47e163d7ecea0a4fcc846a2d8ec421d101f4ca2b9bebe3fcd4a26f5a722f1861
```

Expect exactly **two topics** (signature, canonical padded seller address) and **64 data bytes** (`netBurned` raw9, `usdgPaidWad` WAD). Validate sizes, canonical address padding, emitter, duplicate identity `(blockHash,transactionHash,logIndex)`, removed flags, receipt success and matching receipt/block/header identity. Event logs in failed receipts are not successful fills. Reject malformed/conflicting records; do not silently coerce them to zero.

An empty response means **this provider/filter/range returned no matching records**. It does not establish never-used, unavailable, inactive or zero lifetime burns. An interval may legitimately have no fills while prior epochs do. For each fully covered epoch, compare the sum of `usdgPaidWad` with pinned `filledInEpoch(k)` at an endpoint covering that epoch; nonzero state with empty logs is inconsistent. A partial epoch/time interval needs compatible beginning/end state or full epoch coverage, not comparison with the whole epoch counter. Even zero state is not proof against missing zero-payout burns. There is no lifetime fill counter; mapping equality is a useful cross-check, **not an independent completeness proof** for all events or burns.

## Receipt-local end-to-end attribution

Obtain each candidate's successful receipt and uniquely associate the ordered same-execution legs, using exact canonical token/Treasury/InverseBond emitters and monotonically increasing log indices:

1. NET sender→InverseBond pull. Under an untaxed path, `Transfer(seller,InverseBond,N)`; under a taxed path, source-consistent seller→taxCollector `Transfer`, `TaxCollected` and smaller seller→InverseBond transfer. Gross allowance consumption need not emit `Approval` in the obtained NET implementation; do not require an event that is absent by design.
2. NET `Transfer(InverseBond,zero,N)` proving the gross burn of the event amount. For a taxed pull, distinguish seller delivery from any pre-existing InverseBond NET consumed. Receipt logs alone may not establish that earlier balance; do not invent its source.
3. Optional vault withdrawal and Treasury `MorphoWithdrawn(shortfall)` as payment funding. Their absence is normal when cash suffices; their presence is not newly earned revenue or a second seller payment.
4. USDG token `Transfer(Treasury,seller,Q)` where `Q=floor(usdgPaidWad/1e12)`, followed by Treasury `UsdgSpent(InverseBond,seller,Q)`.
5. InverseBond's matching `InverseBonded(seller,N,usdgPaidWad)`.

Treasury `UsdgSpent(address,address,uint256)` topic0 is `0x21f378978b7bc6aa0d100202fe2a7f4444bc0e2ff51c4d8bf54603e396a8fb50`; its spender and recipient are indexed and raw USDG amount is one data word. ERC20 `Transfer(address,address,uint256)` topic0 is `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`. A Transfer topic from a different token contract is not equivalent evidence.

Match **per fill**, not all transfers in the transaction. Multiple fills, routed contract sellers, unrelated burns/donations, identical values and multiple Treasury spends can make a receipt ambiguous. Require a unique source-consistent grouping and do not reuse a leg across fills; seek actual traces or leave unmatched/ambiguous groups unreconciled rather than inventing attribution. The seller is `msg.sender` recorded in the event, not necessarily transaction origin, an end user or the ultimate beneficiary. Contract sellers may forward USDG; such onward transfers are not a second protocol payout. Zero-output fills can have zero-valued token logs according to actual token behavior; label event-derived zero separately from missing receipt confirmation.

The source proves the requested transfer and checked Boolean return, not the seller balance delta. Token Transfer evidence provides a narrower receipt-confirmed transfer claim, not independently proved fiat receipt, token policy or profit. If complete actual delivery is required, inspect applicable token implementation and execution/state evidence; fee-on-transfer/upgrade/restriction assumptions must be evidenced. Do not count unrelated NET burns or Treasury outflows as InverseBond fills merely because amounts agree.

## Output and consolidation contract

For the requested scope, preserve separate columns/fields:

- **Observed successful fill count** and gross event NET9 burn; independently receipt-confirmed burn total and unresolved count.
- **Event WAD budget debit**; per-fill-derived requested raw USDG; total floor residue.
- **Uniquely receipt-confirmed USDG transfer** Treasury→seller and matching Treasury spend evidence; missing/ambiguous/mismatched legs disclosed.
- **Seller-delivered NET**, any source-consistent NET tax and any donation-funded burn shortfall only when established; do not equate all three with event gross burn.
- Endpoint pin, requested interval, scanned/omitted ranges, creation-boundary status, event/receipt/header consistency, per-epoch mapping cross-check scope and overall coverage.

If coverage is incomplete, label figures **observed subtotals**, with complete interval/lifetime totals unavailable—not zero. State/history contradictions remain inconsistent, not a complete zero result. A fully scanned interval does not certify provider completeness or all source-history assumptions; describe the evidence-backed claim narrowly.

InverseBond is a USDG **reserve outflow** and NET supply retirement. It earns no separate fee in the obtained source. Include it in the [protocol cash-flow/proceeds view](protocol-revenue-analytics.md), not earned-revenue sums. A Treasury spend event, its USDG Transfer and the InverseBond event describe one payment; a preceding vault redemption is internal funding. A backing-per-token gain is not cash income or holder distribution. Keep this distinct from PremiumSeller issuance financing, other products' earned fees/interest/underwriting results, Sleeve/team recipients and unrelated Treasury cash changes. Do not derive period profit from these flows or double-count principal, cash receipts and remittances.

## Isolated synthetic acceptance cases

These are cases for a parent-owned offline test harness, not historical observations, executed tests or network transactions:

- Genesis zero; timestamp just before/at `G+28800`; no UTC or staking-counter epoch substitution; future `G` handled as inconsistent.
- First successful fill snapshots 1% liquid; failure rolls snapshot/filled back; later inflow does not enlarge a nonzero cap; cash outflow does not shrink it; next epoch has no rollover; zero cap retains sentinel behavior.
- Cap equality versus one WAD over; input floors near the exact budget-limited raw9 boundary. Caller minimum equal to output passes; one raw USDG above fails.
- `B=1e18`, `N=1` raw NET: price `985000000000000000`, payout `985000000` WAD, raw USDG `0`. Nonzero NET guard passes; positive user minimum fails. No claim this happened on chain.
- Two synthetic payouts of `F-1` WAD each yield total raw USDG `0`, while flooring their sum gives `1`; ensure aggregation floors per event. Zero payout with zero budget can pass `swap` guards despite `active()==false` from capacity, subject to mocked dependency success.
- Oracle observations aged 1799/1800/14400/14401 seconds; newest eligible selection; stale newest checkpoint versus older eligible observation; no observations, zero TWAP, arithmetic/dependency revert outside `active` catch.
- Treasury not wired/not spender; insufficient cash with successful or failed vault shortfall withdrawal; token transfer false/revert; full rollback of filled cap/NET effects on failure.
- Untaxed pull; taxed pull with insufficient InverseBond prebalance causing burn failure; taxed pull with prebalance covering shortfall and gross burn succeeding. No automatic 95% assumption.
- Empty interval logs with previous activity; empty full-epoch logs but nonzero filled state; zero-filled state with a zero-payout burn; malformed topics/data, wrong emitters, duplicates, failed/reorged receipts, conflicting headers, two identical fills and ambiguous/shared transfer legs.
- NAV model with positive residual supply versus zero reserve value, entire-supply burn, integer-unchanged displayed backing, and independent vault/valuation changes. Do not promote source commentary into a tested unconditional invariant.

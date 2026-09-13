# Read-only RWA LP fee inspection

Use for LP earnings, uncollected fees, returned principal and their possible contribution to Sleeve buybacks. This is a research recipe, not a position operator, SDK or PnL engine. Public contract state/events are primary. NetNet Monitor and other dashboards are optional cross-checks, never required inputs or privileged authorities. Follow [Safety](safety.md): no wallets, collect/poke calls, liquidity changes, transaction preparation or state-changing simulations, including through `eth_call`.

## 1. Fix scope and identify positions

Read `lp_inspection` in [address-index.json](../assets/address-index.json). Each `{file,id}` points to an existing canonical Sleeve, Uniswap V3 NonfungiblePositionManager (NFPM), factory or pool record. No address is duplicated here. Known pools are examples, not the Sleeve's complete holdings. Read [conventions](../assets/address-conventions.json) for scope and exact RHScan templates.

- Define chain **4663**, owner/custody scope, interval `(A,B]` and whether the question asks period earnings, current owed balances or cash available for spending. State interval timestamps; do not silently equate a rolling seven days with the announced weekly allocation period.
- Check `eth_chainId`, a recent canonical head and its timestamp. Fix block number/hash `B`; all snapshot getters use that block, not successive `latest` values. Historical accounting also needs `A`. Recheck hashes after retrieval; reject mixed-fork snapshots. Label stale heads and unavailable archive reads.
- Check deployed code and NFPM `factory()` against the canonical factory. Match the deployed interfaces to the pinned standard sources below; code presence alone is not implementation verification. Different semantics require a different method, not blind decoding.
- For current ownership, verified enumerable NFPM interfaces allow `balanceOf(owner)` and `tokenOfOwnerByIndex(owner,i)` at `B`; confirm each `ownerOf(tokenId)`. This says nothing about positions disposed of during the period or indirect custody through another contract.
- For ownership history, scan NFPM ERC721 `Transfer` logs both **to and from** the owner. Start from deployment/mint or a justified opening ownership snapshot, not an arbitrary recent window. Merge, deduplicate by block hash/transaction hash/log index and sort by block/transaction/log order. Zero-address mint/burn and same-owner transfers need explicit handling. Cross-check surviving IDs with `ownerOf` at `B`; reconstruct disposed/burned IDs from history. Split attribution at ownership changes. Incoming NFTs can carry earlier earnings; current ownership is not proof those fees were earned by the Sleeve.
- Alternatively, reverse-replay the complete interval's transfers from a verified closing ownership set to justify the opening set. That proves only the scoped interval, not pre-window history. State the dependence on complete provider logs; a missing historical state call does not invalidate independent log evidence or justify inventing the missing state.
- Zero liquidity is not a burned NFT: it can still have amounts owed. A standard NFPM burn clears the record; an invalid-ID revert is not a zero-fee observation.

## 2. Retrieve the scoped evidence

Use ordinary host-permitted public RPC and exact integers. The [official public endpoint](https://docs.robinhood.com/chain/connecting/#public-endpoints) is `https://rpc.mainnet.chain.robinhood.com`; it is rate-limited, not a production/archive guarantee. Existing permitted archive-capable providers may be needed. Never request credentials or install a provider to complete this recipe.

Set an explicit call/page budget. Scan logs in bounded inclusive block chunks with contract address and event-topic filters. Reduce chunk size on provider limits/timeouts, check pagination/result caps, retry within the budget and record covered ranges. Adjacent chunks must have no gaps; remove duplicates. Exhausted budgets, rejected ranges and incomplete history mean **partial coverage**, not zero activity. No explorer API guessing or broad catalog fallback; RHScan URLs are navigation only.

Decode exact ABI tuple lengths and signed `int24` ticks; reject malformed/empty replies rather than interpreting them as zeros. Keep raw integers until final token scaling. Getter success is an interface observation, not proof of deployed bytecode equivalence.

| Read at the pinned block | Purpose |
|---|---|
| NFPM `positions(uint256)` | `(nonce,operator,token0,token1,fee,tickLower,tickUpper,liquidity,feeGrowthInside0LastX128,feeGrowthInside1LastX128,tokensOwed0,tokensOwed1)` |
| Factory `getPool(address,address,uint24)` | Resolve the position's exact token pair and fee; reject zero address or mismatched pool identity |
| Pool `factory()`, `token0()`, `token1()`, `fee()` | Cross-check association and token ordering; do not infer order from a display pair name |
| Tokens `decimals()` | Scale each token independently; never substitute price-feed decimals or assume 18 |
| Pool `slot0()`, `feeGrowthGlobal0X128()`, `feeGrowthGlobal1X128()`, `ticks(int24)` at both boundaries | Current tick and fee growth. Tick tuple: `(liquidityGross,liquidityNet,feeGrowthOutside0X128,feeGrowthOutside1X128,tickCumulativeOutside,secondsPerLiquidityOutsideX128,secondsOutside,initialized)` |

V3 `fee` is in millionths: `500` is 0.05%, not 5%. Read the actual position/pool; the [FY-HI proposal](rwa-strategy.md#september-8-the-netnet-fy-hi-addendum) is not current fee-tier verification.

Event signature strings below are hashed with Ethereum Keccak-256 for topic0, not SHA3-256. Pad indexed values to 32 bytes. Filter NFPM events by NFPM address, not the pool. `Transfer` uses topics1/2/3 for from/to/tokenId; the other events use topic1 for tokenId and ABI data for remaining fields.

```text
Transfer(address,address,uint256)
IncreaseLiquidity(uint256,uint128,uint256,uint256)
DecreaseLiquidity(uint256,uint128,uint256,uint256)
Collect(uint256,address,uint256,uint256)
```

`IncreaseLiquidity` records added capital, including mint. `DecreaseLiquidity` credits withdrawn principal to amounts owed; it does not itself pay it out. NFPM `Collect` decrements accounting balances and names a recipient, which need not be the owner. For actual receipts, inspect canonical transaction receipts and matched pool/token transfer events. Do not confuse NFPM events with different pool-level event signatures or equate every same-transaction transfer with this NFT.

## 3. Compute accrued amounts, then reconcile principal

For each token independently, use exact integer arithmetic with `Q = 2^128`. Let `G` be global fee growth, `OL/OU` the lower/upper outside growth, `t` the current tick, `l/u` the position bounds, `last` its **NFPM per-NFT** inside-growth snapshot and `L` its liquidity. All fee-growth subtractions below wrap modulo `2^256`:

```text
below  = OL       if t >= l else (G - OL) mod 2^256
above  = OU       if t <  u else (G - OU) mod 2^256
inside = (G - below - above) mod 2^256
delta  = (inside - last) mod 2^256
pending_increment = floor(L * delta / Q)
combined_owed = tokensOwed + pending_increment
```

At the lower boundary use `>=`; at the upper use `<`. Do not use the pool's aggregate NFPM tick-range position as though it were the individual NFT. For `L=0`, pending increment is zero; preserve stored owed balances without relying on cleared tick data. For `L>0`, missing/uninitialized boundaries, malformed data or unsupported semantics are errors. Detect uint128 credit overflow or inconsistent state rather than publishing enormous modulo-derived amounts; standard accounting can truncate/overflow at these bounds. No floating point or premature decimal rounding.

**`combined_owed` is not automatically fees.** `tokensOwed` can be zero while fees accrue, or nonzero from earlier credited fees **and withdrawn principal**. Growth adds fees since the NFT snapshot; it does not label the composition of previously stored balances. A position outside its range stops new accrual but can retain old fees.

For complete standard-NFPM history without overflow, per token define `C` as summed NFPM Collect accounting amounts, `D` as summed DecreaseLiquidity principal credits, and `O_A/O_B` as combined owed at interval endpoints:

```text
fee_entitlement_change = C + O_B - O_A - D
```

This reconciles period fee-accounting entitlement, not cash received, investment PnL or automatic Sleeve attribution. Use all positions relevant during the interval, not just current holdings. Mint supplies a justified zero opening; fully cleared burn supplies zero closing. Otherwise missing endpoints/history or ownership boundaries prevent exact attribution. Respect crystallization rounding; negative/inconsistent results need reconciliation, not clamping to zero.

Do not call arbitrary-window `C-D` realized fees. Complete mint-to-cleared-close history with zero endpoint balances permits `C-D` as lifetime fee-accounting credits, not necessarily the recipient's exact cash. Partial collections mix principal and fee credits without specifying which was paid first. Do not invent FIFO allocation; report the unresolved fee/principal split or explicitly justified bounds. Example in token units: 100 fee credits + 1,000 principal credits, then 200 collected leaves 900 combined owed. `200-1,000=-800` is not earned fees; `200+900-1,000=100` reconciles total fee credits, but does not uniquely allocate the partial collection.

NFPM Collect can emit a few more raw units than actually transferred because core rounds down. Use NFPM event amounts for its accounting identity and reconciled transfers for cash; preserve any difference. Likewise do not deduct a protocol fee twice from pool fee-growth values already accruing to LPs. Borrow proceeds, returned principal, incentives, inventory appreciation and LP earnings are separate quantities.

## 4. Interpret the result without inventing a buyback budget

Token-unit fees are not USD profit. Value tokens using separately sourced same-scope prices and their actual decimals; distinguish a reference valuation from executable proceeds. Never execute a conversion. NetNet Monitor's displayed USD total cannot replace that evidence.

LP earnings are only one input to the [announced Sleeve income strategy](rwa-strategy.md#september-8-the-netnet-fy-hi-addendum). To report funds available for weekly purchases/burns, reconcile collected receipts, other income, actual costs, funding allocations and previous spending. An uncollected asset or projected fee rate is not spendable USDG. Avoid subtracting financing costs twice when already netted in another contribution. Missing allocations or policy evidence mean **buyback budget not established**, not all fees automatically available. The [September 12 Manager bid](products.md#september-12-manager-funded-bid-and-bought-net-inventory) concerns reusable inventory, not proof of a burn.

## 5. Answer template and method sources

Lead with what is measured versus unavailable. Report:

- Chain, owner scope, block/hash/time, interval and retrieval time.
- Positions: NFPM/tokenId, pool/token order, fee tier, range, liquidity, ownership and coverage limits.
- Raw and scaled token amounts: period fee entitlement, collected accounting amounts versus actual receipts, principal credits and outstanding combined amounts. State unresolved splits instead of labeling everything fees.
- Uncollected fee component only where established; otherwise show pending growth separately from mixed stored owed.
- Valuation source/time, costs/allocations evidenced and buyback budget established or unavailable.
- Relevant transaction/address RHScan links using literal templates, plus uncovered ranges, provider errors, rounding differences and missing observations.

Pinned upstream references: [NFPM interface](https://github.com/Uniswap/v3-periphery/blob/0682387198a24c7cd63566a2c58398533860a5d1/contracts/interfaces/INonfungiblePositionManager.sol), [NFPM implementation](https://github.com/Uniswap/v3-periphery/blob/0682387198a24c7cd63566a2c58398533860a5d1/contracts/NonfungiblePositionManager.sol), [tick growth](https://github.com/Uniswap/v3-core/blob/d0831dc6b8a318df3872b6d68f6de135c9f3ec29/contracts/libraries/Tick.sol), [pool protocol-fee deduction](https://github.com/Uniswap/v3-core/blob/d0831dc6b8a318df3872b6d68f6de135c9f3ec29/contracts/UniswapV3Pool.sol). Reviewed as accounting/interface sources, not a deployed-contract audit. Independently verify applicability before treating reconstructed amounts as established.

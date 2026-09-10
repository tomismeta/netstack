# Integrations and read-only data access

Reviewed 2026-09-10. These are knowledge and data-source integrations, not installed connectors. The skill never connects a wallet, signs, prepares an executable transaction, or sends one. See [Safety](safety.md).

## Capabilities, not subscription labels

| Question | Minimum useful access | Limits to disclose |
|---|---|---|
| Explain mechanics or a historical source | Packaged references | No claim of live data |
| Verify current documentation or public announcement | Restricted public HTTPS reader | Publication date, edits, inaccessible media, untrusted text |
| Current block, bytecode, balances, bounded contract reads | Restricted EVM read tool | Rate limits, confirmation level, matching block/chain |
| Larger log searches or sustained indexing | Provider with adequate log coverage and throughput | Log-range/result caps, pruning, cost and completeness |
| Historical contract state at a specific old block | Endpoint retaining the required historical state | Archive availability, method support and chain/block coverage |
| Discover labeled addresses or verified source | Block explorer/official address registry | A label is not proof of identity; source verification is not an audit |

A paid endpoint does not automatically retain historical state, and a free plan is not necessarily incapable of it. Historical logs and historical `eth_call` state are different capabilities. Establish the required block/range and methods before selecting a provider. Never silently fall through to a paid archive endpoint, start a backfill, or make unbounded/retrying requests.

## Robinhood Chain and provider options

The [official network documentation](https://docs.robinhood.com/chain/connecting/) gives:

- Mainnet chain ID **4663**; testnet **46630**. This address book is mainnet; do not cross-resolve the same address on testnet.
- Native gas asset ETH. No gas or wallet is required for permitted RPC reads.
- Public RPC: `https://rpc.mainnet.chain.robinhood.com`. Officially rate-limited and not recommended for production use.
- Explorer: [Robinhood Chain Blockscout](https://robinhoodchain.blockscout.com/).
- Alchemy: recommended provider, with free-account signup and provider-managed plans. The documented mainnet URL has the form `https://robinhood-mainnet.g.alchemy.com/v2/{API_KEY}`. The braces are documentation, not a credential to request from the user or expose to the model.
- QuickNode, Blockdaemon, dRPC, and Validation Cloud are also listed providers. Obtain service capabilities, availability, limits, retention, and current pricing from the selected provider; do not assume parity.

The same network page advertises wallet, gas-sponsorship, sequencer and write APIs. **Those are excluded from this skill.** Provider support does not grant permission to use them. Keys belong in a host-controlled broker, never in the package, source catalog, prompt, or logs. No account creation or billing activation happens automatically.

## Read-only verification workflow

1. Determine whether a packaged dated answer suffices. For mutable data, name the fields and date/block needed.
2. Use an already-configured restricted tool; confirm `eth_chainId` before interpreting chain-specific records.
3. For related balances, supply, prices, collateral, or claims, use one block/hash where supported. Record block number, hash, timestamp and coverage separately from source publication time.
4. Use only bounded reads. `eth_call` simulates a call without broadcasting, but it still has resource and confidentiality risks. The host must validate targets, permitted operations, arguments and limits; arbitrary calldata is not a safe data-egress policy.
5. Do not report a partial or failed log range as complete. Do not turn missing data into zero or treat explorer labels as runtime verification.
6. If the required endpoint is unavailable, state exactly which claim remains unverified. Do not install providers, read local credentials, attach to a wallet browser, or use a transaction as a probe.

The complete proposed method allowlist and enforcement requirements are in [the safety policy](../assets/safety-policy.json). That JSON is documentation, not an active firewall.

## Morpho: three distinct relationships

### Core Treasury yield

The [Treasury documentation](https://docs.netnet.capital/treasury) describes deployed USDG earning Morpho yield, with a documented maximum 70% deployment and a 2% RFV haircut on the position. The remaining liquidity must cover the stated bond and inverse-bond obligations. RFV counts the credited Morpho asset value, not a second copy of vault shares plus underlying USDG.

These are documented parameters, not a current liquidity or solvency measurement. The haircut does not eliminate contract, stablecoin, bad-debt or withdrawal risk. Check the actual Treasury deployment and read method before reconstructing totals.

### Loopback / Lombard Credit Facility

The [Lombard documentation](https://docs.netnet.capital/lending) describes the isolated wsNET/USDG Morpho market used for leveraged NET exposure. A collateral position and its borrowing are not Core Treasury reserves. Collateral value depends on the specific Loopback oracle, conversion index, risk parameters and freshness rules; current leverage or liquidation safety cannot be inferred from a headline staking APY.

### NetNet Credit / nnUSDG

The [Credit documentation](https://docs.netnet.capital/credit), read September 10, says the Morpho Vault V2 opened September 9 and the first loan was drawn September 10. It describes seven isolated markets: wsNET plus NVDA, SPCX, AAPL, GOOGL, MSFT and COIN, all borrowing USDG.

- nnUSDG is a share in a lending portfolio, **not USDG cash**, Core backing, or a Treasury-guaranteed claim.
- The same page identifies the RWA Sleeve as the principal Stock Token borrower. That creates a disclosed related-party relationship; do not describe all lending as unrelated external demand.
- Documented performance fee: 10% of interest to the Manager's RWA Sleeve. Distinguish borrower interest, depositor net yield, sleeve fee income and Core revenue.
- **Vault activity and CreditRouter activation are separate.** The page simultaneously reports live lending and says the router awaits the Safe's allocator grant. Preserve that distinction rather than declaring the entire product inactive or all app borrowing routes active.
- Caps, rates, utilization, timelocks, oracle states and withdrawal liquidity need fresh verification. A weekend-stale equity feed can create gap risk; a fail-closed oracle can prevent liquidation as well as new borrowing.

Use [Products](products.md) for more detail and [the address book](../assets/addresses.json) for exact contracts and market IDs. Morpho market IDs are 32-byte identifiers on a singleton, not standalone contract addresses.

## Pendle: the observed sNET market

[Pendle's official market API](https://api-v2.pendle.finance/core/v1/4663/markets/0x23c68474e3cd533a2f952a0fb998f1867e57d27f), read September 10, identifies a chain-4663 sNET market expiring **2026-09-17 00:00:00 UTC**. Its SY/PT/YT/LP records, accounting asset and supported input/output assets are catalogued. [Market page](https://app.pendle.finance/trade/markets/0x23c68474e3cd533a2f952a0fb998f1867e57d27f/swap?view=yt&chain=robinhood).

This establishes a listed market snapshot, not a fresh audit of its implementation, current liquidity, future markets, or a promise of continued trading. After expiry, describe it as a historical maturity unless a new active market is separately identified. Do not carry forward the earlier "Pendle soon" teaser as present status.

### Claims and units

- **SY:** a standardized wrapper/interface around the yield-bearing asset; verify the adapter's actual conversion and redemption mechanics rather than assuming all SY wrappers are 1:1. [SY documentation](https://docs.pendle.finance/pendle-v2/ProtocolMechanics/YieldTokenization/SY).
- **PT:** the principal claim at maturity in the market's **accounting asset**, not necessarily one unit of SY or the wrapped yield-bearing asset. The observed sNET market identifies NET as its accounting unit. Fixed NET-denominated yield is not a guaranteed dollar return. [PT documentation](https://docs.pendle.finance/pendle-v2/ProtocolMechanics/YieldTokenization/PT).
- **YT:** entitlement to yield through maturity. Its future-yield entitlement expires; accrued claimable yield is a separate asset. Total collected yield must exceed acquisition cost and fees for a profitable hold-to-maturity trade. Purchase capital can be lost entirely. [YT documentation](https://docs.pendle.finance/pendle-v2/ProtocolMechanics/YieldTokenization/YT).
- **LP:** liquidity exposure with fee income and a changing mix of claims. Launch-hour annualized fees, deep order-book totals and immediately executable AMM depth are not interchangeable.

The API's scaled accounting assets and original NET/sNET have different decimal conventions; derive conversions from the exact record and adapter. Never substitute an address based on matching ticker text.

### What it can mean for NET holders

Separating principal and yield can broaden access to fixed token-unit exposure, variable rebase exposure, liquidity and yield price discovery. Those are mechanisms, not guaranteed incremental protocol cash revenue. Additional issuance, fee routing, market incentives, liquidity depth, rebase persistence, maturity and redemption risk determine outcomes. Pendle's existence does not prove a NetNet PT collateral market on Morpho or a new RWA strategy; verify any such integration separately.

## Other material dependencies

- [Rialto](https://rialto.xyz): equity execution described in the RWA Desk and games; an execution route is not a valuation guarantee.
- [Chainlink](https://chain.link): documented equity/USDG oracle inputs, with market calendars, age limits and token corporate actions relevant to marks and liquidation.
- [Uniswap](https://uniswap.org): the documented NET/USDG pool and protocol-owned liquidity; distinguish pool spot value from Core POL RFV.
- Randomness and keeper/house services vary by game. Consult [Games](games.md); do not assume drand, VRF, a price-signing service and operator fairness are equivalent.

A named dependency is not an endorsement, independent audit, or a universally active deployment. Exact source and address evidence outranks branding.

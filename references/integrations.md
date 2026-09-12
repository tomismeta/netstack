# Integrations and read-only data access

Documentation/data reviewed 2026-09-10; dated announcement context added through 2026-09-12 (unpublished working update). These are knowledge and data-source integrations, not installed connectors. The skill never connects a wallet, signs, prepares an executable transaction, or sends one. See [Safety](safety.md).

## Capabilities, not subscription labels

| Question | Minimum useful access | Limits to disclose |
|---|---|---|
| Explain mechanics or a historical source | Packaged references | No claim of live data |
| Verify current documentation, dashboard, collection data, price or public announcement | Ordinary unauthenticated public reader/browser/API tool | Publication/retrieval date, edits, inaccessible media, untrusted text |
| Current block, bytecode, balances, bounded contract reads | Public RPC access through a host-permitted read tool | Rate limits, confirmation level, matching block/chain |
| Larger log searches or sustained indexing | Provider with adequate log coverage and throughput | Log-range/result caps, pruning, cost and completeness |
| Historical contract state at a specific old block | Endpoint retaining the required historical state | Archive availability, method support and chain/block coverage |
| Discover labeled addresses or verified source | Block explorer/official address registry | A label is not proof of identity; source verification is not an audit |

A paid endpoint does not automatically retain historical state, and a free plan is not necessarily incapable of it. Historical logs and historical `eth_call` state are different capabilities. Establish the required block/range and methods before selecting a provider. Never silently fall through to a paid archive endpoint, start a backfill, or make unbounded/retrying requests.

Ordinary public retrieval and following relevant public source links need no custom broker, purpose-built reader or prior per-destination administrator setup. Prefer public endpoints. Existing host restrictions and [Safety](safety.md) still apply: minimum public inputs, no private/local/metadata destinations, and an unauthenticated browser without wallets/providers, WalletConnect, authenticated sessions or signing/broadcast paths. Navigation and read-only clicks are allowed; wallet prompts and actions are not.

## Robinhood Chain and provider options

The [official network documentation](https://docs.robinhood.com/chain/connecting/) gives:

- Mainnet chain ID **4663**; testnet **46630**. This address book is mainnet; do not cross-resolve the same address on testnet.
- Native gas asset ETH. No gas or wallet is required for permitted RPC reads.
- Public RPC: `https://rpc.mainnet.chain.robinhood.com`. Officially rate-limited and not recommended for production use.
- Alchemy: recommended provider, with free-account signup and provider-managed plans. The documented mainnet URL has the form `https://robinhood-mainnet.g.alchemy.com/v2/{API_KEY}`. The braces are documentation, not a credential to request from the user or expose to the model.
- QuickNode, Blockdaemon, dRPC, and Validation Cloud are also listed providers. Obtain service capabilities, availability, limits, retention, and current pricing from the selected provider; do not assume parity.

The same network page advertises wallet, gas-sponsorship, sequencer and write APIs. **Those are excluded from this skill.** Provider support does not grant permission to use them. Do not access credentials, create an account or activate billing for research. Provider plans are background information, not setup instructions. If an independently managed host service uses credentials, they must remain outside the model, package, source catalog and logs, scoped to the exact service origin/path and never forwarded across origins.

For **all Robinhood Chain explorer navigation**, including historical addresses and transactions, return [RHScan](https://rh-scan.com/) links. This is the user-selected default, separate from the network documentation's historical Blockscout listing. Read `explorers["4663"]` in [address-conventions.json](../assets/address-conventions.json) and substitute only the exact validated chain-qualified address or transaction hash; a Morpho market ID is neither. Do not infer a chain or substitute an unrelated object when identity is missing.

RHScan's public homepage and address/transaction UI shells and identity titles were observed on 2026-09-12, not dynamic balances, receipts or code. Its [API documentation](https://rh-scan.com/api-docs) says it is unfinished. Do not infer API endpoints, keys, limits or stability from UI routes, or move Blockscout API paths onto the RHScan hostname. Earlier Blockscout API readings remain explicitly historical source evidence with their actual URLs and dates in [sources.json](../assets/sources.json); they are not RHScan verification or default explorer guidance.

## Read-only verification workflow

1. Determine whether a packaged dated answer suffices. For mutable data, name the fields and date/block needed.
2. Use existing host-permitted access to a suitable public endpoint; no provider installation or custom broker is needed. Confirm `eth_chainId` before interpreting chain-specific records.
3. For related balances, supply, prices, collateral, or claims, use one block/hash where supported. Record block number, hash, timestamp and coverage separately from source publication time.
4. Use only bounded reads with public inputs. ABI-encoding a read method such as a balance query for `eth_call` is allowed. A non-broadcasting call is not automatically read-only research: do not simulate state-changing methods, impersonate accounts, use state overrides or construct ready-to-sign/submit transaction artifacts. Check the target, operation, arguments and limits, including every batch member; arbitrary calldata is not a confidentiality safeguard.
5. Do not report a partial or failed log range as complete. Do not turn missing data into zero or treat explorer labels as runtime verification.
6. If the required endpoint is unavailable, state exactly which claim remains unverified and use available public evidence or the dated package. Do not install shell/provider tools, read credentials, create accounts, activate billing, change host permissions, attach to a privileged/wallet browser or use a transaction as a probe.

The permitted method boundaries and optional higher-assurance controls are in [the safety policy](../assets/safety-policy.json). That JSON is documentation, not an active firewall. A broker and denial tests are needed only for corresponding enforced-safety claims, not ordinary public reads; current runtime enforcement is unproven.

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

See [Credit's product terms](products.md#netnet-credit-a-curated-lender-not-a-replacement-loopback) and [router-status distinction](products.md#documented-market-operation-versus-interface-activation). For an exact identity question, start at the [address index](../assets/address-index.json), load [markets.json](../assets/addresses/markets.json), then the selected market's literal `singleton_record` and match `singleton_id`. **Return that record's singleton address and RHScan address URL separately** from the 32-byte market ID. A market ID is neither a standalone contract address nor a transaction hash; merely explaining that distinction is incomplete when the singleton is recorded. If a file is unavailable, disclose it rather than fabricate the identity or load broad source/reference files as a fallback.

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

## Privy: historical WinNET onboarding

The publisher [announced WinNET's Privy integration on July 27, 2026](https://x.com/NetNetCap/status/2081839101783974128); its [July 28 post](https://x.com/NetNetCap/status/2082190279764025712) described email-only onboarding, “completely gasless” play and crew-code referrals. This historical claim does not verify wallet architecture, sponsor, continuing subsidy, current configuration or availability. Sponsored gas removes a stated gas charge—not entry costs, NET taxes, market risk or authorization requirements. “Free money” does not establish cash: see [WinNET's draw-credit and grant-status conflict](games.md#winnet--pooled-staking-not-a-cash-preserving-lottery).

**Research only:** no connector or permission to sign in, submit email, request an OTP, create an embedded wallet, use an authenticated session, claim referrals, invoke a sponsor/paymaster or play is added. Read public descriptions unauthenticated; do not test onboarding. Research needs no credentials, account setup or wallet action.

## Other material dependencies

- [Rialto](https://rialto.xyz): equity execution described in the RWA Desk and games; an execution route is not a valuation guarantee.
- [Chainlink](https://chain.link): documented equity/USDG oracle inputs, with market calendars, age limits and token corporate actions relevant to marks and liquidation.
- [Uniswap](https://uniswap.org): the documented NET/USDG pool and protocol-owned liquidity; distinguish pool spot value from Core POL RFV.
- Randomness and keeper/house services vary by game. Consult [Games](games.md); do not assume drand, VRF, a price-signing service and operator fairness are equivalent.
- **NetNet RealTime Pricing Feed / Real Time Game Pricing Primitive:** historical names from the publisher's August 30/31, 2026 Runner posts. [Runner's source chronology and app rules](games.md#subway-runner) identify house-signed Hyperliquid-perpetual reports and report-selection/dispute limits—not Chainlink reference feeds, NET spot/TWAP or Loopback collateral marks. The name verifies no current signer, implementation, deployment or trustlessness.

A named dependency is not an endorsement, independent audit, or a universally active deployment. Exact source and address evidence outranks branding.

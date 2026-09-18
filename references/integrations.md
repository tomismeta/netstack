# Integrations and read-only data access

Documentation/data reviewed 2026-09-10; dated announcement context retained through September 12, with targeted **September 18** Pendle, Credit, Predict and retail-liquidity updates below. This is not a blanket refresh of every integration. These are knowledge and data-source integrations, not installed connectors; the [safety policy](safety.md) governs all access.

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

Use ordinary host-permitted public reads under [Safety's public-research rules](safety.md#everyday-public-research); no custom broker or per-destination setup is required.

## Live analytics execution limits

Read this section before LP, Predict or House retrieval. These are agent execution instructions, **not an installed timeout controller or a guarantee of completion**. Keep the requested accounting scope; missing history must yield an explicitly incomplete answer, not a shorter replacement interval.

- **One deadline:** default to **180 seconds total per answer**, including reference loading, permission waits, retrieval, decoding and response preparation. Record the start of handling the request; remaining answer time is `max(0, min(180 - elapsed, host_remaining))`, omitting the host term only when unknown. Reserve the final **45 seconds** for reporting; remaining retrieval time is `max(0, remaining_answer_time - 45)`. Thus a fresh default run stops retrieval by 135 seconds; a fresh request with only 100 host seconds remaining allows at most 55 seconds of retrieval. An explicit longer research allowance replaces 180 but still cannot exceed the host deadline. Never reset the clock after errors, fallback, snapshot restart or continuation within the same turn.
- **Bound actual calls:** cap each tool/script invocation by the remaining retrieval allowance and at most **30 seconds**, including parsing, computation and backoff. Leave **2 seconds inside that invocation** to serialize/return its checkpoint; if fewer than 2 seconds remain, start no work. Cap each HTTP/RPC attempt at the smaller of **15 seconds total wall time** and the remaining inner invocation/retrieval allowance. A socket read timeout alone is insufficient. Check a monotonic deadline before requests, chunk splits and expensive decoding; retain completed work between invocations rather than launching one long all-or-nothing scan. Stop internally and return the checkpoint before the outer tool timeout, rather than relying on a hard kill to preserve output. Do not spend the final answer reserve on another provider or receipt.
- **Snapshot first:** collect only the question's required same-block identities, units, state and counters, then preserve them before historical scans. Keep a compact checkpoint after each completed chunk: pinned blocks/hashes, verified observations, covered and missing ranges/IDs, raw-data references, counts, elapsed time and sanitized errors. Prefer one permitted RPC path for chain data; explorer failures need not block it. Do not repeat completed reads or fetch unrelated product/account histories. Hash rechecks belong inside the retrieval budget; if unavailable, disclose that limit rather than claiming confirmation.
- **Batch without amplifying load:** where the provider supports JSON-RPC batches, group independent permitted reads at the same pinned block, at most **20 members** per batch; match replies by ID, not order, and retain individual successes. A batch is not an atomic chain snapshot. Count every member and retry against the recipe's RPC budget. At most **4 requests may be in flight**, with no concurrent batches; do not batch dependent discovery reads or repeat successful members when retrying failures. If batching is rejected, bounded individual calls may use the remaining shared budget.
- **Finite recovery:** at most **one retry per failed request**, only for transient transport/rate-limit/server failures, and at most **10 recovery attempts total** across the run, including chunk splits and batch fallbacks. Count every resulting RPC member against the request cap. Retry-After/backoff must fit inside the deadline; otherwise stop. Do not retry permission denials, malformed ABI responses or unavailable historical state as transient errors. Preserve the actual exception type/status and failing method/range, without secrets; report unresolved failures rather than cycling through HTTP libraries or providers.
- **Approvals are not implicit:** use normal host permissions. If a tool reports approval required, surface the exact public-read operation and approval block promptly; do not silently poll, switch tools to evade the gate, enable `--yolo`/auto-approve, or recommend bypassing checks. When the host permits an answer, return available evidence with live access marked blocked. If the host suspends execution before the agent can respond, report that as a host approval stall in acceptance testing; this package cannot cancel that suspension.
- **Always return the evidence obtained:** on deadline, access failure or resource exhaustion, give a concise final answer with snapshot block/time, requested versus covered scope, completed metrics, exact missing ranges/IDs and the stopping reason. Distinguish complete accounting, useful partial evidence and blocked access. Missing values are unknown, not zero. If no live snapshot succeeded, say so and use only clearly dated packaged facts. Offer a separately authorized continuation; do not start a background backfill.

## Robinhood Chain and provider options

The [official network documentation](https://docs.robinhood.com/chain/connecting/) gives:

- Mainnet chain ID **4663**; testnet **46630**. This address book is mainnet; do not cross-resolve the same address on testnet.
- Native gas asset ETH. No gas or wallet is required for permitted RPC reads.
- Public RPC: `https://rpc.mainnet.chain.robinhood.com`. Officially rate-limited and not recommended for production use.
- Alchemy: recommended provider, with free-account signup and provider-managed plans. The documented mainnet URL has the form `https://robinhood-mainnet.g.alchemy.com/v2/{API_KEY}`. The braces are documentation, not a credential to request from the user or expose to the model.
- QuickNode, Blockdaemon, dRPC, and Validation Cloud are also listed providers. Obtain service capabilities, availability, limits, retention, and current pricing from the selected provider; do not assume parity.

The same network page advertises wallet, gas-sponsorship, sequencer and write APIs. **Those are excluded from this skill.** Provider plans are background information, not permission to obtain credentials, create accounts or activate billing. Any independently managed host-service credentials remain outside the model under [Safety's credential controls](safety.md#optional-higher-assurance-host-controls).

For **all Robinhood Chain explorer navigation**, including historical addresses and transactions, return [Robinhood Etherscan](https://robin.etherscan.io/) links. [Etherscan's chain registry](https://api.etherscan.io/v2/chainlist) identifies this explorer for chain **4663**. Read `explorers["4663"]` in [address-conventions.json](../assets/address-conventions.json) and substitute only the exact validated chain-qualified address or transaction hash; a Morpho market ID is neither. Do not infer a chain or substitute an unrelated object when identity is missing.

Etherscan's [supported-chain documentation](https://docs.etherscan.io/supported-chains) lists Robinhood Chain, including Free Tier availability. This does not provision API access or establish method quotas, archive coverage or anonymous availability. Web pages can restrict automated access: disclose missing observations and use suitable permitted public RPC for chain reads, not challenge bypasses or invented explorer APIs. Historical retrieval URLs in [sources.json](../assets/sources.json) preserve their original evidence origin. The explorer change does not change the public RPC endpoint or prove Etherscan verification of earlier source reads.

## Read-only verification workflow

1. Determine whether a packaged dated answer suffices. For mutable data, name the fields and date/block needed.
2. Select suitable host-permitted public access and confirm `eth_chainId` before interpreting chain-specific records.
3. For related balances, supply, prices, collateral, or claims, use one block/hash where supported. Record block number, hash, timestamp and coverage separately from source publication time.
4. Bound the target, read method, public arguments and resource limits, including every batch member, under [Safety's RPC rules](safety.md#everyday-public-research). Non-broadcasting state-changing simulations are not read-only research.
5. Do not report a partial or failed log range as complete. Do not turn missing data into zero or treat explorer labels as runtime verification.
6. If access is unavailable, state exactly which claim remains unverified and use available public evidence or the dated package; do not bypass the access boundary.

The [structured safety policy](../assets/safety-policy.json) documents method boundaries; it is not an active firewall or evidence of runtime enforcement. See [host-control requirements](safety.md#optional-higher-assurance-host-controls) before making enforced-safety claims.

## Morpho: three distinct relationships

### Core Treasury yield

The [Treasury documentation](https://docs.netnet.capital/treasury) describes deployed USDG earning Morpho yield, with a documented maximum 70% deployment and a 2% RFV haircut on the position. The remaining liquidity must cover the stated bond and inverse-bond obligations. RFV counts the credited Morpho asset value, not a second copy of vault shares plus underlying USDG.

These are documented parameters, not a current liquidity or solvency measurement. The haircut does not eliminate contract, stablecoin, bad-debt or withdrawal risk. Check the actual Treasury deployment and read method before reconstructing totals.

### Loopback / Lombard Credit Facility

The [Lombard documentation](https://docs.netnet.capital/lending) describes the isolated wsNET/USDG Morpho market used for leveraged NET exposure. A collateral position and its borrowing are not Core Treasury reserves. Collateral value depends on the specific Loopback oracle, conversion index, risk parameters and freshness rules; current leverage or liquidation safety cannot be inferred from a headline staking APY.

### NetNet Credit / nnUSDG

The [Credit documentation](https://docs.netnet.capital/credit), re-read September 18, still says the Morpho Vault V2 opened September 9 and the first loan was drawn September 10. It describes seven isolated markets: wsNET plus NVDA, SPCX, AAPL, GOOGL, MSFT and COIN, all borrowing USDG.

- nnUSDG is a share in a lending portfolio, **not USDG cash**, Core backing, or a Treasury-guaranteed claim.
- The same page identifies the RWA Sleeve as the principal Stock Token borrower. That creates a disclosed related-party relationship; do not describe all lending as unrelated external demand.
- Documented performance fee: 10% of interest to the Manager's RWA Sleeve. Distinguish borrower interest, depositor net yield, sleeve fee income and Core revenue.
- **Vault activity and CreditRouter activation are separate.** The page still reports live lending while saying the router awaits the Safe's allocator grant. Its documented authority is limited to internal Loopback/listed-stock reallocations, market caps, a minimum Loopback buffer and $250,000 per call. A liquidation-depth cap revision is only **in preparation**; neither a new cap nor router activation is established.
- Caps, rates, utilization, timelocks, oracle states and withdrawal liquidity need fresh verification. A weekend-stale equity feed can create gap risk; a fail-closed oracle can prevent liquidation as well as new borrowing.

See [Credit's product terms](products.md#netnet-credit-a-curated-lender-not-a-replacement-loopback) and [router-status distinction](products.md#documented-market-operation-versus-interface-activation). For an exact identity question, start at the [address index](../assets/address-index.json), load [markets.json](../assets/addresses/markets.json), then the selected market's literal `singleton_record` and match `singleton_id`. **Return that record's singleton address and Robinhood Etherscan address URL separately** from the 32-byte market ID. A market ID is neither a standalone contract address nor a transaction hash; merely explaining that distinction is incomplete when the singleton is recorded. If a file is unavailable, disclose it rather than fabricate the identity or load broad source/reference files as a fallback.

## Pendle: the observed sNET market

[Pendle's official API](https://api-v2.pendle.finance/core/v1/4663/markets/0xab0093949fefa432bfb1a0ba8943ee4aebc898a8), read **September 18**, identifies the successor chain-4663 sNET market as **active**, expiring **2026-10-01 00:00:00 UTC**. The [September 17 market API](https://api-v2.pendle.finance/core/v1/4663/markets/0x23c68474e3cd533a2f952a0fb998f1867e57d27f) now reports **inactive** after its **2026-09-17 00:00:00 UTC** maturity. These are distinct markets, not a date change to the old contract.

| Maturity (UTC) | Exact market/LP identity | Principal token | Yield token | September 18 status |
|---|---|---|---|---|
| October 1, 2026, 00:00 | [PLP-sNET-1OCT2026](https://app.pendle.finance/trade/markets/0xab0093949fefa432bfb1a0ba8943ee4aebc898a8/swap?view=yt&chain=robinhood) | PT-sNET-1OCT2026 | YT-sNET-1OCT2026 | API active |
| September 17, 2026, 00:00 | [PLP-sNET-17SEP2026](https://app.pendle.finance/trade/markets/0x23c68474e3cd533a2f952a0fb998f1867e57d27f/swap?view=yt&chain=robinhood) | PT-sNET-17SEP2026 | YT-sNET-17SEP2026 | Matured; API inactive |

Resolve exact chain-qualified PT/YT/LP addresses through the [address index](../assets/address-index.json), preserving maturity-qualified identities. Both snapshots share SY-sNET and the scaled accounting/underlying assets; that does **not** make their PT, YT or LP tokens interchangeable. The old market remains relevant to historical holdings and redemption questions. Inactive does not prove all matured claims are worthless or that redemption is impossible.

The active flag establishes a listed API snapshot, not guaranteed executable liquidity, adapter correctness or continued availability. API timestamps/whitelisting dates are not independently verified deployment dates. Do not preserve “Pendle soon” as present status, project volatile APY into promised returns, or read the API's `feeRate` field as a flat percentage of trade principal without establishing its fee basis.

### Claims and units

- **SY:** a standardized wrapper/interface around the yield-bearing asset; verify the adapter's actual conversion and redemption mechanics rather than assuming all SY wrappers are 1:1. [SY documentation](https://docs.pendle.finance/pendle-v2/ProtocolMechanics/YieldTokenization/SY).
- **PT:** the principal claim at maturity in the market's **accounting asset**, not necessarily one unit of SY or the wrapped yield-bearing asset. Both sNET market APIs identify **NET** as that unit (`pyUnit=NET`, `ptEqualsPyUnit=true`). Fixed NET-denominated yield is **not fixed USD or USDG principal**, a guaranteed dollar return, or a Core Treasury guarantee. [PT documentation](https://docs.pendle.finance/pendle-v2/ProtocolMechanics/YieldTokenization/PT).
- **YT:** entitlement to yield through maturity. Its future-yield entitlement expires; accrued claimable yield is a separate asset. Total collected yield must exceed acquisition cost and fees for a profitable hold-to-maturity trade. Purchase capital can be lost entirely. [YT documentation](https://docs.pendle.finance/pendle-v2/ProtocolMechanics/YieldTokenization/YT).
- **LP:** liquidity exposure with fee income and a changing mix of claims. Launch-hour annualized fees, deep order-book totals and immediately executable AMM depth are not interchangeable.

The API identifies 18-decimal SY/PT/YT/LP and NET-scaled18/sNET-scaled18 accounting assets, while supported original NET/sNET inputs and outputs use 9 decimals. Derive conversions from the exact record and adapter; symbol matching or dividing every asset by the same scale is insufficient. Never substitute one maturity's address for another based on generic “PT sNET” or “YT sNET” display text.

### What it can mean for NET holders

Separating principal and yield can broaden access to fixed token-unit exposure, variable rebase exposure, liquidity and yield price discovery. Those are mechanisms, not guaranteed incremental protocol cash revenue. Additional issuance, fee routing, market incentives, liquidity depth, rebase persistence, maturity and redemption risk determine outcomes. Pendle's existence does not prove a NetNet PT collateral market on Morpho or a new RWA strategy; verify any such integration separately.

## Uniswap retail liquidity and Predict underwriting are different integrations

The [Add liquidity panel](https://app.netnet.capital/#/invest) links to direct NET + USDG Uniswap v2 provision; the separate USDG-only LP Zap remained **app-gated pending exemption/promotion** in the September 18 registry and panel despite its September 16 creation. See [retail LP mechanics and risks](products.md#retail-netusdg-v2-liquidity-and-the-lp-zap). Keep this Zap separate from the older Managed Futures Zap, and v2 receipts separate from Sleeve v3 NFPM NFTs and [their fee-growth accounting](lp-fee-inspection.md).

For [Predict and House product terms](products.md#netnet-predict-weekly-outcomes-and-house-vault), distinguish September 18 app/launch and explorer-indexed creation/trade evidence from verified implementation or complete settlement rules. Deployment and trading evidence do not certify application-model fees, schedules or marks.

For either product, read exact identities through the bounded [address index](../assets/address-index.json). Keep **publisher registry labels**, **observed UI availability**, **creation/transaction evidence** and **verified implementation/current permissions** as separate fields in an answer. A publisher `HUMAN-VERIFIED` label is not an independent audit; `PLACEHOLDER` can coexist with successful contract creation. Preserve original source API origins in provenance, while returning Robinhood Etherscan links for user-facing explorer navigation.

Live research procedures: [NET/USDG v2 holdings, flows and fees](liquidity-analytics.md) and [Predict activity and House accounting](predict-analytics.md). Their selected `analytics` entries in the address index lead to bounded route/interface files; no installed connector is added. Cache the complete required same-block snapshot before a long log scan. If that state is later pruned, do not mix replacement latest reads with the earlier block.

## Privy: historical WinNET onboarding

The publisher [announced WinNET's Privy integration on July 27, 2026](https://x.com/NetNetCap/status/2081839101783974128); its [July 28 post](https://x.com/NetNetCap/status/2082190279764025712) described email-only onboarding, “completely gasless” play and crew-code referrals. This historical claim does not verify wallet architecture, sponsor, continuing subsidy, current configuration or availability. Sponsored gas removes a stated gas charge—not entry costs, NET taxes, market risk or authorization requirements. “Free money” does not establish cash: see [WinNET's draw-credit and grant-status conflict](games.md#winnet--pooled-staking-not-a-cash-preserving-lottery).

**Research only:** do not test onboarding, submit email, request an OTP, create an embedded wallet, claim referrals, invoke a sponsor/paymaster or play. Public descriptions remain subject to [Safety](safety.md#everyday-public-research).

## Other material dependencies

- [Rialto](https://rialto.xyz): equity execution described in the RWA Desk and games; an execution route is not a valuation guarantee.
- [Chainlink](https://chain.link): documented equity/USDG oracle inputs, with market calendars, age limits and token corporate actions relevant to marks and liquidation.
- [Uniswap](https://uniswap.org): the documented NET/USDG pool and protocol-owned liquidity; distinguish pool spot value from Core POL RFV.
- Randomness and keeper/house services vary by game. Consult [Games](games.md); do not assume drand, VRF, a price-signing service and operator fairness are equivalent.
- **NetNet RealTime Pricing Feed / Real Time Game Pricing Primitive:** historical names from the publisher's August 30/31, 2026 Runner posts. [Runner's source chronology and app rules](games.md#subway-runner) identify house-signed Hyperliquid-perpetual reports and report-selection/dispute limits—not Chainlink reference feeds, NET spot/TWAP or Loopback collateral marks. The name verifies no current signer, implementation, deployment or trustlessness.

A named dependency is not an endorsement, independent audit, or a universally active deployment. Exact source and address evidence outranks branding.

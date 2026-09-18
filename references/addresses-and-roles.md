# Contracts, public addresses and roles

Catalog additions observed 2026-09-18; candidate package version **0.3.0-rc.3**. Earlier record observations retain their own dates. Robinhood Chain mainnet **4663**. Exact values live in bounded JSON files routed by [address-index.json](../assets/address-index.json), not parallel copies in these references. Sources and their review status live in [sources.json](../assets/sources.json).

## Inventory and its boundaries

The working inventory contains **183 distinct contract-address records**, **10 separately published public-role records**, **six trusted product mark mappings**, and **six Stock Token Morpho market IDs**. Its **37 underlying price-feed records** comprise **35 Robinhood-labelled RWA candidates** (33 explicitly classified `Equity`, two with incomplete classification) plus ETH/USD and USDG/USD. These are not 35 verified token mappings or 35 NetNet-used markets. Some public-role addresses may also occur in the contract set; section counts must not be added and described as unique wallets.

Sources combine official NetNet docs, shareholder/arcade app registries, exact local-registry provenance and published Morpho, Uniswap, Rialto and Pendle deployments—not exhaustive discovery. **No inventory record has independently performed live-chain verification.** PredictDesk, PredictVault and LPZap have successful creation evidence from explorer-indexed transaction responses; series #1 outcomes have indexed issuance evidence. These are not independently fetched RPC receipts, source-verified Solidity or audits. Inclusion and generated explorer links do not verify current bytecode, permissions, ownership, activation, security or liquidity. Future chain checks must record block/hash and scope; “published” must not silently become “audited.”

## Data layout

- Start at [address-index.json](../assets/address-index.json). Its literal paths are relative to the package root: `feeds` selects a symbol file; `contracts` selects a canonical-role initial's role/alias index, then its `file`; `public_roles` lists bounded role files; `markets` points to [markets.json](../assets/addresses/markets.json). Read only the selected files. No directory listing, glob, fragment, line-range selector or record query is required. If an exact file is unavailable, name the gap instead of chasing inaccessible spill files or loading broad references/`sources.json`.
- **Filenames:** `contracts/by-name-r.json` is an alphabetical lookup index, not contract data. Its entries name descriptive data files such as [rialto-runner-and-rwa-desk-v1.json](../assets/addresses/contracts/rialto-runner-and-rwa-desk-v1.json) and [rwa-desk-v2-and-feed-router-adapters.json](../assets/addresses/contracts/rwa-desk-v2-and-feed-router-adapters.json). Names summarize the existing bounded groups; some groups contain multiple products. They do not establish contract identity, currentness or shared deployment versions: use each record's ID, role, aliases, chain and lifecycle evidence. `public-roles-*.json` contains operational-role records; `feeds/<symbol>.json` contains the exact feed and any qualified mapping. Follow literal index paths rather than constructing filenames.
- Read [address-conventions.json](../assets/address-conventions.json) once alongside selected records. Its `explorers["4663"]` supplies Robinhood Etherscan address and transaction URL templates; `record_notes` supplies shared publisher-label, feed-metadata, NetNet-use-evidence and public-role qualifications. Shared scope, coverage and discrepancies do not replace per-record facts or supply missing defaults.
- `contracts`: chain ID, exact address, role, aliases, lifecycle/publication status, live-verification status, and parent `provenance` entries with source IDs, observation dates and locators. Parent provenance owns publisher-directory feed metadata, with each locator identifying the fields it supports.
- `lifecycle_notes` qualifies dated activation/maturity evidence; `deployment_transaction_hash`, where present, is an exact historical identity supported by the indexed-transaction provenance, not a transaction to execute. Paired `*_id`/`*_record` fields point to existing canonical dependencies without duplicating them.
- `publisher_linked_provenance_urls`: original publisher links retained for evidence, not response navigation. Return Robinhood Etherscan links for referenced Robinhood objects; do not copy an old provider's API path or query-tab syntax.
- `marketplace_collections`, where present on a contract record: collection names/links and API provenance matched to that exact chain/address. These are identity associations, not marketplace or contract safety guarantees.
- `public_role_addresses`: named public operational/signing/owner-role addresses, explicitly unverified account kind and no inferred legal-person attribution. A role named `signer` does not give this agent access or permission to sign.
- `markets`: 32-byte Morpho identifiers, `singleton_record` and `singleton_id`. Load the literal singleton file, select its ID, and **return its recorded 20-byte address and Robinhood Etherscan address link separately** from the market ID. The canonical singleton address remains in that contract record, not copied into each market. A market ID is neither an address nor a transaction hash.
- `trusted_product_marks`, in the corresponding feed-symbol file: exact-token mappings to known feed/source relationships. Matching a symbol such as NVDA is not enough to reuse another token's oracle.
- `price_feed`, where present on a contract record: publisher name, directory group, publisher-sourced feed name, quote asset, value semantics, metadata status, classification gaps and token/NetNet-use evidence. Read its publisher metadata evidence in the parent contract's `provenance`; the adjacent `decimals` is the feed answer scale, not token decimals. Preserve `netnet_use_evidence.status` and separately attributed `consumer_policies`, which record only specifically documented uses, not an exhaustive deployed call graph.
- `price_source`, on the canonical NET/USDG pool, PairOracle, Treasury and LoopbackOracle: typed source kind, purpose, base/quote units and dated documentation provenance. These are market, derived-TWAP, reserve-accounting or collateral sources—not extra underlying Chainlink feeds.
- `known_discrepancies` and `coverage`, in conventions: generation conflicts, source boundaries, omitted zero placeholders, inaccessible material and missing verification.

**Provenance dates and scope:** parent contract `provenance[].observed_on` dates each source observation, including feed metadata; distinct dates, sources and scopes remain distinct. The file date labels only the snapshot. None certifies current configuration. A `local_definition` is a historical repository path, not a skill dependency or URL; extracted facts are bundled, but public corroboration is preferable for consumers without that repository. The six `trusted_product_marks` retain their original local-registry scope; directory matches do not independently verify them. Unknown classification, unrecorded consumer use and live-verification limits remain explicit, not filled by shared notes.

**Explorer navigation:** return Robinhood Etherscan links for every Robinhood Chain object, current or historical. Validate the exact chain ID **4663** and a full 20-byte hexadecimal address or 32-byte transaction hash before substituting into `explorers["4663"].address_url_template` or `transaction_url_template`. Contract and public-role addresses, market singleton addresses and deployment transaction hashes retain their own identities; a Morpho market ID is not an address or transaction hash. Do not guess a chain or object from a ticker, alias or missing field. A derived link is navigation, not a new observation; API access and indexing coverage require separate evidence.

## Useful families to look up

| Family | Roles to distinguish |
|---|---|
| Core | NET, sNET, wsNET, Treasury, staking, distributor, bonds, inverse bonds, PremiumSeller, option/vesting components and fee handling |
| Reserves and markets | USDG, NET/USDG pool, protocol-owned LP, Morpho singleton/vaults and price inputs |
| RWA Desk | Original and successor Desk, router/feed adapter, Manager's sleeve Safe and stock-token/feed pairs |
| Credit | nnUSDG vault, market adapter, CreditRouter generations, each StockMorphoOracle, owner/curator Safe, isolated market IDs |
| Loopback | wsNET collateral, Loopback oracle/router, Morpho market—not the long-dated TURBO product |
| TURBO and arcade | Desk and card generations, blackjack/series relationships, jackpots, claim/escrow components, verifiers and published operator roles |
| Pendle | sNET market, SY, PT, YT, LP and original/scaled accounting assets, each with different units and claims |
| Infrastructure | Chain-specific Uniswap deployments, Rialto registry, Multicall and feeds; deployment names are not permission grants |

### New names and bounded routes

Canonical-role initials, not an alias's first letter, select the lookup index:

| Requested name | Canonical initial / bounded record |
|---|---|
| NetNet Predict / Probability Desk / PredictDesk; House Vault / PredictVault | `p` → [Predict desk and vault](../assets/addresses/contracts/predict-desk-and-vault.json) |
| HIGHER #1 / HI-1; LOWER #1 / LO-1 | `p` → [Predict series #1 outcomes](../assets/addresses/contracts/predict-series-1-outcomes.json); canonical roles begin `Predict` |
| LP Zap / NET/USDG LP Zap | `l` → [LPZap](../assets/addresses/contracts/lp-zap.json), not Managed Futures' `z` → [Zap](../assets/addresses/contracts/zap.json) |
| BASKETS / Grab Desk | `b` → [BasketsDesk](../assets/addresses/contracts/baskets-desk.json); Permit2 remains under `p`, DrandSigRegistry under `d` |
| Pendle October 1 LP/PT; October 1 YT | `p` / `y` → [sNET 1OCT2026 identities](../assets/addresses/contracts/pendle-snet-1oct2026.json) |

Bare **HIGHER/LOWER require a series**, not an automatic substitution of #1. Generic **Pendle LP/PT/YT require a maturity**: the `p` and `y` indexes retain both September 17 and October 1 identities. Explain the dated API lifecycle observations and resolve the requested maturity rather than silently choosing the historical alias or the newer market. The existing SY, original NET/sNET, and scaled accounting/underlying records are shared dependencies, not new successor tokens.

The canonical **PENDLE** role records a reward token from the historical market API, not the LP market or either yield-token claim. Clarify an ambiguous “Pendle address” request. Likewise, the publisher labels **RwaDesk/rwaDesk** must be resolved by V1/V2 generation, not by capitalization.

For mechanics and risks, see [Products](products.md), [Games](games.md) and [Integrations](integrations.md). Names route research only; no entry authorization, approval, transaction preparation or wallet interaction follows from a matching address.

## Price feeds and token relationships

`Use netstack: feeds` requests this directory; `Use netstack: feeds NVDA` focuses on a feed/token relationship; `Use netstack: feeds NET` selects the distinct NET sources. `Use netstack: contracts feeds` reaches the same section. These are reference lookups, not tool invocations or live-price requests. For a symbol, follow the root index's literal feed-file path and read its `contracts` and any exact `trusted_product_marks`, plus conventions. NET instead uses the relevant contract-role indexes.

### Full Robinhood-labelled RWA feed index

All **35 candidates** retain exact primary `proxyAddress` and chain. Publisher metadata observed **2026-09-12** lists **USD quote / 8 feed decimals** for all. Full addresses/evidence live in the symbol files linked below and routed by the [address index](../assets/address-index.json). `Equity` includes tokenized ETFs; do not recategorize by ticker.

| Requested name | Feed contract role | Publisher asset class | Exact token relationship |
|---|---|---|---|
| [AAPL](../assets/addresses/feeds/aapl.json) | `chainlinkAaplUsd` | Equity | Existing exact mapping |
| [AMD](../assets/addresses/feeds/amd.json) | `chainlinkAmdUsd` | Equity | Unverified / not recorded |
| [AMZN](../assets/addresses/feeds/amzn.json) | `chainlinkAmznUsd` | Equity | Unverified / not recorded |
| [ASML](../assets/addresses/feeds/asml.json) | `chainlinkAsmlUsd` | Equity | Unverified / not recorded |
| [BABA](../assets/addresses/feeds/baba.json) | `chainlinkBabaUsd` | Equity | Unverified / not recorded |
| [CLSK](../assets/addresses/feeds/clsk.json) | `chainlinkClskUsd` | Equity | Unverified / not recorded |
| [COIN](../assets/addresses/feeds/coin.json) | `chainlinkCoinUsd` | Equity | Existing exact mapping |
| [CRCL](../assets/addresses/feeds/crcl.json) | `chainlinkCrclUsd` | Equity | Unverified / not recorded |
| [CRWV](../assets/addresses/feeds/crwv.json) | `chainlinkCrwvUsd` | Equity | Unverified / not recorded |
| [DELL](../assets/addresses/feeds/dell.json) | `chainlinkDellUsd` | Equity | Unverified / not recorded |
| [EWY](../assets/addresses/feeds/ewy.json) | `chainlinkEwyUsd` | Equity | Unverified / not recorded |
| [GME](../assets/addresses/feeds/gme.json) | `chainlinkGmeUsd` | Equity | Unverified / not recorded |
| [GOOGL](../assets/addresses/feeds/googl.json) | `chainlinkGooglUsd` | Equity | Existing exact mapping |
| [INTC](../assets/addresses/feeds/intc.json) | `chainlinkIntcUsd` | Equity | Unverified / not recorded |
| [IONQ](../assets/addresses/feeds/ionq.json) | `chainlinkIonqUsd` | Equity | Unverified / not recorded |
| [META](../assets/addresses/feeds/meta.json) | `chainlinkMetaUsd` | Equity | Unverified / not recorded |
| [MSFT](../assets/addresses/feeds/msft.json) | `chainlinkMsftUsd` | Equity | Existing exact mapping |
| [MSTR](../assets/addresses/feeds/mstr.json) | `chainlinkMstrUsd` | Equity | Unverified / not recorded |
| [MU](../assets/addresses/feeds/mu.json) | `chainlinkMuUsd` | Equity | Unverified / not recorded |
| [NBIS](../assets/addresses/feeds/nbis.json) | `chainlinkNbisUsd` | Equity | Unverified / not recorded |
| [NVDA](../assets/addresses/feeds/nvda.json) | `chainlinkNvdaUsd` | Equity | Existing exact mapping |
| [ORCL](../assets/addresses/feeds/orcl.json) | `chainlinkOrclUsd` | Equity | Unverified / not recorded |
| [PLTR](../assets/addresses/feeds/pltr.json) | `chainlinkPltrUsd` | Equity | Unverified / not recorded |
| [QQQ](../assets/addresses/feeds/qqq.json) | `chainlinkQqqUsd` | Equity | Unverified / not recorded |
| [RGTI](../assets/addresses/feeds/rgti.json) | `chainlinkRgtiUsd` | Equity | Unverified / not recorded |
| [RKLB](../assets/addresses/feeds/rklb.json) | `chainlinkRklbUsd` | Equity | Unverified / not recorded |
| [SGOV](../assets/addresses/feeds/sgov.json) | `chainlinkSgovUsd` | Incomplete | Unverified / not recorded |
| [SLV](../assets/addresses/feeds/slv.json) | `chainlinkSlvUsd` | Equity | Unverified / not recorded |
| [SNDK](../assets/addresses/feeds/sndk.json) | `chainlinkSndkUsd` | Equity | Unverified / not recorded |
| [SPCX](../assets/addresses/feeds/spcx.json) | `chainlinkSpcxUsd` | Equity | Existing exact mapping |
| [SPY](../assets/addresses/feeds/spy.json) | `chainlinkSpyUsd` | Equity | Unverified / not recorded |
| [TSLA](../assets/addresses/feeds/tsla.json) | `chainlinkTslaUsd` | Equity | Unverified / not recorded |
| [TSM](../assets/addresses/feeds/tsm.json) | `chainlinkTsmUsd` | Equity | Unverified / not recorded |
| [USAR](../assets/addresses/feeds/usar.json) | `chainlinkUsarUsd` | Incomplete | Unverified / not recorded |
| [USO](../assets/addresses/feeds/uso.json) | `chainlinkUsoUsd` | Equity | Unverified / not recorded |

**Two metadata gaps:** SGOV and USAR have empty `assetName` and absent `docs.assetClass`, `docs.baseAsset` and `docs.productTypeCode`. Their names and eight-decimal scales are explicit; `docs.quoteAssetEntityId` supports USD quote. Do not infer classification or total-return semantics. The other 33 explicitly say `Equity`.

**Six mappings; 29 unmapped:** join “Existing exact mapping” to `trusted_product_marks` by chain and full `feed_address`, then resolve `token_address`. These are historical local-registry relationships, not independently verified current pairings. The other **29 have no exact token relationship or NetNet-use evidence recorded**; bounded public directory/documentation lookup established no additional pairs. Ticker matching cannot fill the gap.

**Address types are not interchangeable:** directory `contractAddress` is an aggregator; neither it nor `secondaryProxyAddress` identifies a token. `trusted_product_marks.source_contract_address` is historical provenance—not a Chainlink proxy, recommended spender or current-wiring proof. NVDA cites superseded Desk V1; AAPL cites V2. Read feed answers from canonical `feed_address`, not those desks; do not create a parallel pairing inventory.

### ETH/USD and USDG/USD

| Requested asset | Feed contract role | Relationship boundary | Quote / feed decimals |
|---|---|---|---|
| [ETH](../assets/addresses/feeds/eth.json) | `chainlinkEthUsd` | No stock-token mapping; do not infer a WETH relationship from the symbol | USD / 8 |
| [USDG](../assets/addresses/feeds/usdg.json) | `usdgUsdFeed` | No `trusted_product_marks` entry; the USDG token is separately catalogued | USD / 8 |

These retain **2026-09-10** metadata observations and public app-registry provenance. The [Chainlink Robinhood mainnet directory](https://reference-data-directory.vercel.app/feeds-robinhood-mainnet.json) has **57 entries** in the audited snapshot; this inventory selects the 35 Robinhood-labelled candidates and these two feeds, not every crypto entry. JSON identity/scale is **publisher metadata**, not successful `decimals()` calls, token decimals or current prices. **USDG/USD is a conversion reference, not proof that one USDG equals one USD.**

### Equity value and unit boundaries

**Direct equity value:** [Chainlink's Robinhood documentation](https://docs.chain.link/data-feeds/tokenized-equity-feeds/robinhood) describes **total-return value**: underlying equity price × token corporate-action/dividend multiplier, not raw listed-stock price. Normalize the same-block feed answer; **do not apply the multiplier again**. Corporate-action pauses and closed sessions can leave an old value callable. This description does not verify local token mappings.

**Product output is a separate read:** [Credit](https://docs.netnet.capital/credit) describes StockMorphoOracle multiplier adjustment of equity/USDG feeds; [THE BOARD MEETING](https://docs.netnet.capital/the-board-meeting) describes entry-adapter multiplication. Historical Blockscout API inspection matched six Credit creation-bytecode tails to catalogued token/feed pairs and found MSFT token/feed addresses in Boardroom indexed bytecode. The inspected responses contained no source bodies for those six oracles or Boardroom adapter; Sourcify/public IPFS recovery also failed. This is indexed-bytecode evidence, **not source-verified arithmetic or live state**, and was not retrieved from the current explorer. The original retrieval URLs and dates remain under `netnet-product-oracle-indexed-evidence` in [sources.json](../assets/sources.json). The gap is not merely an unknown ticker, nor evidence of a deployed double-multiplication bug.

**Raw versus display balance:** the [Stock implementation on Robinhood Etherscan](https://robin.etherscan.io/address/0xb35490d6f9163DE4F80d88dc75c3516eb64C5aE2), linked to catalogued MSFT, defines `balanceOfUI = floor(balanceOf * uiMultiplier / 1e18)` according to the historical Blockscout API source-body reading recorded as `robinhood-stock-scaled-ui-source` in [sources.json](../assets/sources.json). That evidence is not Etherscan source verification. Both balances need token-decimal interpretation. The token is upgradeable; this conversion does not establish a feed/product price's unit basis. Dimensionally, if display quantity `D = R * m`, multiply a per-display-unit price by `D` or a per-raw-unit price by `R`, never both conventions. Multiplication alone does not prove double counting.

For a **Credit collateral or Board Meeting entry mark**, identify the exact oracle/adapter, interface, output scale and raw/display unit basis; read **the product's own result** at the observation block. Never reconstruct it from the direct-feed formula or substitute a feed mark for missing product evidence. Source-verified arithmetic and current input/output units remain missing prerequisites. [Products](products.md#oracle-and-liquidation-risks) and [Games](games.md#the-board-meeting--counterparties-choose-reward-systems-differ) retain the product-specific claims.

### Consumers and freshness are separate from feed metadata

| Feed / product context | Documented use and acceptance policy | Evidence limit |
|---|---|---|
| COIN / COINflip | Direct USDG-to-equity entry requires an open equity session and feed age no greater than four hours | [COINflip](https://docs.netnet.capital/coinflip); policy for this conversion path, not every use of COIN |
| SPCX / SPACEX INVADERS | Same direct USDG conversion gate | [Invaders](https://docs.netnet.capital/spacex-invaders); not a universal feed property |
| MSFT / FLIGHT SIMULATOR | Same direct USDG conversion gate | [Flight Simulator](https://docs.netnet.capital/flight-simulator); native-equity play has different availability |
| NVDA and AAPL / TURBO documented launch series | Fresh in-session Chainlink, then eligible pool TWAP, otherwise frozen close; new listings require a fresh in-session mark | [TURBO](https://docs.netnet.capital/turbo), summarized in [Games](games.md); not proof of current series or exact deployed feed call paths |
| GOOGL, ETH, USDG; other consumers of any feed | No exhaustive consumer list or universal maximum age recorded here | Inspect the specific product/adapter and its evidence; missing policy is not permission to accept stale data |

The three numeric conversion policies also appear in `price_feed.consumer_policies`; absence means **not recorded**, not unused. Documentation does not verify current enforcement. **Heartbeat, round timestamp and consumer maximum age differ:** the directory lists a heartbeat, but equity docs say off-hours have none. Neither establishes a universal age limit; `updatedAt` is not timeless and four hours is not a default.

### Adapters and derived oracles are not underlying feeds

The inventory also names `TurboFeedAdapter` generations, `otcDeskFeedAdapter`, `rwaDeskFeedAdapter`, `coinflipFeedAdapter`, `flightsimFeedAdapter`, `spacexInvadersFeedAdapter` and `buttonFeedAdapter`. Credit's StockMorphoOracles and Loopback's oracle have separate collateral/loan units and semantics. The Morpho ChainlinkOracleV2 **factory** creates contracts; it is not itself an asset price feed. Do not assume these contracts expose the underlying feed's ABI, eight decimals or freshness rules. Resolve generations and consumer wiring separately.

### NET price sources: pool, TWAP, NAV and collateral are distinct

`Use netstack: feeds NET` should return this source-kind distinction, not invent a NET/USD Chainlink feed:

| Requested quantity | Canonical contract role / source kind | Meaning and boundary |
|---|---|---|
| NET pool spot reference | `NET/USDG canonical pair (Uniswap v2)` / `market_pool` | Reserve-ratio reference in **USDG per NET**, after establishing exact token ordering and decimals. Not an executable quote, NAV or Core's TWAP. |
| Core NET market mark | `PairOracle` / `derived_twap_oracle` | Documented cumulative-price TWAP from that canonical pool, in USDG terms; valid window 30 minutes–4 hours. Not instantaneous spot or an eight-decimal Chainlink answer. |
| Core backing per NET | `Treasury` / `reserve_accounting` | Documented NAV = RFV / total supply, in USDG per NET; excludes the Manager Sleeve. Not market price, an automatic redemption right or a current holdings observation. |
| Loopback credited wsNET collateral | `LoopbackOracle` / `collateral_valuation_oracle` | Documented `clamp(TWAP × 0.90, NAV, 5 × NAV) × index`; separate collateral/loan units and stale-TWAP/divergence guards. Not NET spot or unadjusted NAV. |
| Manager's announced 2×NAV bid | [September 12 post](https://x.com/NetNetCap/status/2098803824282771690) / **policy announcement, not a feed** | Manager-funded bid; bought NET becomes Real World Bonds inventory. Venue, capacity, NAV definition, implementation and remittance remain unestablished. See [Products](products.md#september-12-manager-funded-bid-and-bought-net-inventory). |

Sources: [Mechanism: price oracle](https://docs.netnet.capital/mechanism), [Treasury: RFV/NAV](https://docs.netnet.capital/treasury), [Loopback](https://docs.netnet.capital/lending). JSON `price_source` records documented purposes, not verified live implementations. The Manager announcement is **not Core's inverse-bond bid, a Treasury obligation or an oracle**.

Current NET marks require the chain/head-recency checks below plus the exact interface, token ordering, same-block units/decimals, window and source state; packaged metadata supplies no live facts. **USDG is not USD:** conversion requires a separately acceptable same-block USDG/USD observation, scale and freshness. Report spot, TWAP, NAV, collateral and policy bid separately; never substitute for unavailable evidence. No checkpointing, trading, borrowing, approvals or wallet connection is authorized.

### Read-only pricing walkthrough

For “display a USD reference price for this NVDA token”:

1. **Match identity.** Require the requested chain ID and full token address to match NVDA's `trusted_product_marks`; resolve `feed_address` to `chainlinkNvdaUsd` and report local-registry provenance. A different token means stop, regardless of ticker.
2. **Name units.** Packaged scale is eight decimals, publisher-sourced; equity value is tokenized total return. Token-balance decimals and raw/display conventions are separate.
3. **Establish observation recency.** Under [Safety](safety.md) and [public RPC guidance](integrations.md#read-only-verification-workflow), use bounded public reads to confirm chain **4663** and a recent canonical head. Record block number/hash/time and retrieval time; check head lag against an explicit use-case bound. `latest` alone proves nothing. Read `decimals()`, `description()` and `latestRoundData()` from the exact proxy **at that same block**. An old block's then-fresh round is historical, not current. Unestablished head recency requires a historical/recency-unverified label; unavailable access never justifies an invented price, wallet, impersonation, state override or state-changing simulation.
4. **Validate the round separately.** Decode signed `answer` with exact integer/decimal arithmetic. A nonpositive USD answer, zero/future `updatedAt`, malformed result or failed read is unusable. Report round age at the block **and** elapsed age at retrieval/current time. Apply the consumer's block-time policy separately from display recency, market sessions and corporate actions. RPC success is not acceptance; missing policy or observation-lag bound leaves current suitability unresolved.
5. **Scale from the live read.** Divide `answer` by `10 ** feed_decimals`, using successful `decimals()` from the **same proxy and block**—never packaged eight-decimal fallback. A scale mismatch requires stopping current-price presentation until identity/configuration is resolved. **Synthetic only:** `12345678900` with same-block decimals `8` gives `123.45678900 USD`, not an observed NVDA price. Real observations need round timestamp and block; never add a second corporate-action multiplier.
6. **Keep the mark's limits.** It is not an executable quote, liquidity, collateral backing or redemption right. `rialtoRouterRegistry` and [Rialto docs](https://docs.rialto.xyz/developers/router-registries.md) identify conversion infrastructure, not quotes or trading permission. Explain [game conversion limits](games.md) without wallet connection or transaction preparation.

**Answer scope:** a default directory response includes all 35 RWA roles, ETH/USD and USDG/USD, four NET source kinds, quote/scale, mapping/classification gaps and provenance boundaries. A focused response includes only the selected record, exact recorded relationship, consumer limits and missing evidence. Follow literal bounded JSON files; neither “not recorded” nor packaged metadata establishes verification or a current price.

## Generation and activation traps

- **RWA Desk:** Official Channels still publishes the original Desk while the app/local registry identifies a V2 successor. Preserve V1 historical activity and V2 activity separately; never use one address to query the other's entire history.
- **TURBO:** long-dated `TurboDesk` is not Loopback's `TurboRouter`. Versioned Desks/cards/adapters can have different claims and settlement rules.
- **Credit:** a listed or deployed router is not necessarily an active allocator. The live Credit-vault disclosure does not contradict a pending router grant. Preserve both router generations and check current permissions separately.
- **NetNetGear:** retired and current NFT/gear deployments are different from the BoardroomLoot library.
- **The Button and app-only products:** UI/bundle presence does not establish currently accepting entries. Documentation may be out of date, and published zero placeholders are not deployed addresses.
- **Pendle:** a market identity includes chain, maturity, SY/PT/YT and accounting asset. The official API observed September 18 reports September 17 inactive and October 1 active; retain both identities. Activity is dated publisher metadata, not proof of current liquidity, redemption or deployment time.
- **Predict:** Desk and House Vault are separate from series-specific HIGHER/LOWER tokens. A successful indexed trade proves the observed issuance, not future settlement, exact deployed fee/tie/void rules or an audited vault loss limit.
- **LPZap:** a nonzero deployment can remain `PLACEHOLDER` in a publisher registry. Indexed successful creation and app gating coexist; do not call it undeployed or currently tax-free/enabled. The direct Uniswap NET/USDG route and older Managed Futures Zap are distinct.
- **BASKETS:** publisher-reported opening does not verify deployed referee permissions or payout liveness. Separate the Desk, Permit2 entry spender and rotating Rialto router used for later stock conversion; never pin the latter from an old quote or infer an approval recommendation.

## Read-only identity procedure

1. Follow the root index to the exact role/source's bounded file, then match **chain ID plus full address**. Aliases help discovery but are not identifiers.
2. Identify whether the record is a contract, a public role, a market ID, an oracle input, a proxy, an implementation or an NFT/market instance.
3. Compare applicable official sources and generation dates. Explain conflicts rather than silently choosing the newest-looking string.
4. If permitted fresh read tools exist, check bytecode at a recorded block and inspect the relevant read-only state. Bytecode presence establishes only deployed code at that block—not ownership, intended function, activation or safety.
5. For proxies, determine the relevant implementation and control roles at the same block; do not treat an implementation's verified source as proof of the proxy's current behavior.
6. For claimed public ownership/control, use explicit source attribution or on-chain role evidence. Transfer history, funders and explorer labels alone do not prove a real person's identity.
7. Link the exact public record on Robinhood Etherscan using the validated chain and object identity, including for historical deployments or transactions. Explain what was checked and what was not, and preserve source/block dates and original evidence attribution. Never verify by connecting, approving, signing, deploying or transacting.

The skill provides no keys, wallet connections, signing payloads, transaction execution or smart-contract safety warranty. See [Safety](safety.md).

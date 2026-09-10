# Contracts, public addresses and roles

Snapshot: 2026-09-10, Robinhood Chain mainnet **4663**. Exact values live in [addresses.json](../assets/addresses.json), not parallel copies in these references. Sources and their review status live in [sources.json](../assets/sources.json).

## Inventory and its boundaries

The snapshot contains **145 distinct contract-address records**, **10 separately published public-role records**, **six trusted product mark mappings**, and **six Stock Token Morpho market IDs**. Some public-role addresses may also occur in the contract set; section counts must not be added and described as unique wallets.

The inventory combines official NetNet documentation, the shareholder/arcade app registries, exact local registry provenance, and published Morpho, Uniswap, Rialto and Pendle deployment references. It is not a complete discovery of every deployment or token. A registry's inclusion of a named address is not an independent check of its bytecode, current permissions, ownership, activation, security or available liquidity.

**No record in this release has an independently performed live-chain verification.** Registry/status observations are dated publisher or repository evidence. Generated explorer links make verification accessible; they are not verification results. Any future chain checks must explicitly record their block/hash and limited scope rather than silently turning "published" into "audited."

## Data layout

- `contracts`: chain ID, exact address, role, aliases, lifecycle/publication status, live-verification status, explorer URL, and provenance entries with source IDs and locators.
- `marketplace_collections`, where present on a contract record: collection names/links and API provenance matched to that exact chain/address. These are identity associations, not marketplace or contract safety guarantees.
- `public_role_addresses`: named public operational/signing/owner-role addresses, explicitly unverified account kind and no inferred legal-person attribution. A role named `signer` does not give this agent access or permission to sign.
- `markets`: 32-byte Morpho market identifiers and the chain-qualified singleton contract. These IDs must not be used as 20-byte contract addresses or passed to a generic address explorer as though they were one.
- `trusted_product_marks`: exact-token mappings to known feed/source relationships. Matching a symbol such as NVDA is not enough to reuse another token's oracle.
- `price_feed`, where present on a contract record: publisher-sourced name, quote asset, value semantics and metadata provenance; the adjacent `decimals` is the feed answer scale, not token decimals. `consumer_policies` records only specifically documented uses, not an exhaustive deployed call graph.
- `known_discrepancies` and `coverage`: generation conflicts, source boundaries, omitted zero placeholders, inaccessible material and missing verification.

A `local_definition` source in the catalog is a historical repository-provenance path, not a skill-relative dependency or web URL. The extracted facts are bundled. Prefer public corroboration for consumers without the originating repository.

Each contract's `provenance[].observed_on` dates the individual source observation. The file-level date is a snapshot label, not a replacement for those dates. Feed metadata has its own observation date. The six `trusted_product_marks` relationships retain their original local-registry scope; a new feed-directory match does not independently verify those token relationships. None of these dates certifies current deployment configuration.

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

## Price feeds and token relationships

Use `Use netstack: feeds` for this directory, or `Use netstack: feeds NVDA` for one exact-token lookup. `Use netstack: contracts feeds` reaches the same section. This is a reference lookup, not a tool invocation or an instruction to fetch live prices.

The eight underlying price feeds currently catalogued are below. Resolve full addresses and provenance from the named `contracts` records in [addresses.json](../assets/addresses.json). For the six equity rows, join the exact `trusted_product_marks` entry by chain and `feed_address` to obtain `token_address`; resolve that token to its contract record. Do not join arbitrary assets by ticker or create a second pairing inventory. The separate `source_contract_address` is local-registry provenance, not the Chainlink aggregator, the proxy to read, a spender recommendation or proof of current consumer wiring. In particular, NVDA's mapping cites superseded RWA Desk V1, while AAPL's cites V2. Read prices from `feed_address`, not from those desks.

| Requested asset | Feed contract role | Canonical token relationship | Quote / feed decimals |
|---|---|---|---|
| AAPL | `chainlinkAaplUsd` | `trusted_product_marks` AAPL, exact addresses only | USD / 8 |
| MSFT | `chainlinkMsftUsd` | `trusted_product_marks` MSFT, exact addresses only | USD / 8 |
| GOOGL | `chainlinkGooglUsd` | `trusted_product_marks` GOOGL, exact addresses only | USD / 8 |
| NVDA | `chainlinkNvdaUsd` | `trusted_product_marks` NVDA, exact addresses only | USD / 8 |
| COIN | `chainlinkCoinUsd` | `trusted_product_marks` COIN, exact addresses only | USD / 8 |
| SPCX | `chainlinkSpcxUsd` | `trusted_product_marks` SPCX, exact addresses only | USD / 8 |
| ETH | `chainlinkEthUsd` | No stock-token mapping; do not infer a WETH relationship from the symbol | USD / 8 |
| USDG | `usdgUsdFeed` | No `trusted_product_marks` entry; token role `USDG` is separately catalogued | USD / 8 |

Decimals and proxy identities were matched by full address against the [Chainlink Robinhood mainnet directory](https://reference-data-directory.vercel.app/feeds-robinhood-mainnet.json) on 2026-09-10. These are **publisher metadata**, not successful `decimals()` calls or live-chain verification. Per-feed metadata and evidence remain canonical in the JSON; this table is a navigation summary. No token decimals are inferred.

**What the equity number means:** [Chainlink's Robinhood feed documentation](https://docs.chain.link/data-feeds/tokenized-equity-feeds/robinhood) describes tokenized **total-return value**: underlying equity price multiplied by the token's corporate-action/dividend multiplier. It is not simply the raw listed-stock price. Do not multiply the feed answer by that multiplier again. The publisher describes corporate-action pauses and closed sessions that can leave the last value callable without a new update. This general feed description does not upgrade our locally recorded token mappings into independently checked relationships.

**Product pricing is a separate read, not a second scaling step.** [Credit](https://docs.netnet.capital/credit) says its StockMorphoOracle adjusts equity/USDG feeds by the token multiplier; [THE BOARD MEETING](https://docs.netnet.capital/the-board-meeting) says its entry adapter applies the multiplier. A scoped public explorer inspection matched the six Credit oracle creation-bytecode tails to the catalogued token/feed pairs, and found the MSFT token/feed addresses in Boardroom's indexed bytecode. However, the six oracles and the Boardroom adapter have no source bodies in the inspected explorer responses; source recovery through Sourcify and public IPFS gateways did not obtain them. This is indexed-bytecode evidence, not source-verified product arithmetic or a live-state check. Do not describe the missing relationship merely as an unknown ticker, and do not declare a deployed double-multiplication bug.

**Raw balance versus display balance:** the [explorer-indexed Stock implementation](https://robinhoodchain.blockscout.com/api/v2/smart-contracts/0xb35490d6f9163DE4F80d88dc75c3516eb64C5aE2), linked by the explorer to the catalogued MSFT token, defines `balanceOfUI = floor(balanceOf * uiMultiplier / 1e18)`. Both balances still require token-decimal interpretation. This display conversion does not itself prove which quantity a particular feed or product price is denominated in, and the token is upgradeable. As a dimensional example only, if display quantity `D = R * m`, a price per display unit must be multiplied by `D`, while a price per raw unit must be multiplied by `R`. Never apply both conventions to the same value. This is why seeing multiplication in a product is not sufficient evidence of double counting.

For a **direct feed mark**, normalize only the same-block feed answer and report its documented total-return semantics. For a **Credit collateral or Board Meeting entry mark**, identify the exact product oracle/adapter, its read interface, output scale and raw/display unit basis, then read the product's own result at the same observation block. Do not reconstruct it from the directory's direct feed formula or silently substitute a feed mark when product evidence is unavailable. Exact source-verified product arithmetic and current input/output units remain missing prerequisites here; [Products](products.md#oracle-and-liquidation-risks) and [Games](games.md#the-board-meeting--counterparties-choose-reward-systems-differ) preserve the publisher claims and their limits.

### Consumers and freshness are separate from feed metadata

| Feed / product context | Documented use and acceptance policy | Evidence limit |
|---|---|---|
| COIN / COINflip | Direct USDG-to-equity entry requires an open equity session and feed age no greater than four hours | [COINflip](https://docs.netnet.capital/coinflip); policy for this conversion path, not every use of COIN |
| SPCX / SPACEX INVADERS | Same direct USDG conversion gate | [Invaders](https://docs.netnet.capital/spacex-invaders); not a universal feed property |
| MSFT / FLIGHT SIMULATOR | Same direct USDG conversion gate | [Flight Simulator](https://docs.netnet.capital/flight-simulator); native-equity play has different availability |
| NVDA and AAPL / TURBO documented launch series | Fresh in-session Chainlink, then eligible pool TWAP, otherwise frozen close; new listings require a fresh in-session mark | [TURBO](https://docs.netnet.capital/turbo), summarized in [Games](games.md); not proof of current series or exact deployed feed call paths |
| GOOGL, ETH, USDG; other consumers of any feed | No exhaustive consumer list or universal maximum age recorded here | Inspect the specific product/adapter and its evidence; missing policy is not permission to accept stale data |

The three numeric conversion policies are also beside their feed records in `price_feed.consumer_policies`. An absent consumer entry means **not recorded**, not unused. Documentation evidence is not verification that a current contract enforces the described gate.

Feed heartbeat, latest round timestamp and consumer maximum age are different facts. The publisher directory lists a heartbeat, but the Robinhood equity documentation says off-hours have no heartbeats. Neither establishes a universally safe age limit for a new game. Do not package `updatedAt` as a timeless field or treat four hours as a default.

### Adapters and derived oracles are not underlying feeds

The inventory also names `TurboFeedAdapter` generations, `otcDeskFeedAdapter`, `rwaDeskFeedAdapter`, `coinflipFeedAdapter`, `flightsimFeedAdapter`, `spacexInvadersFeedAdapter` and `buttonFeedAdapter`. Credit's StockMorphoOracles and Loopback's oracle have separate collateral/loan units and semantics. The Morpho ChainlinkOracleV2 **factory** creates contracts; it is not itself an asset price feed. Do not assume these contracts expose the underlying feed's ABI, eight decimals or freshness rules. Resolve generations and consumer wiring separately.

### Read-only pricing walkthrough

For “display a USD reference price for this NVDA token”:

1. Load the NVDA `trusted_product_marks` entry and require the requested **chain ID and full token address** to match. Resolve its `feed_address` to `chainlinkNvdaUsd`. If the token differs, stop: the ticker is not enough. Present the mapping's local-registry provenance.
2. Explain that the packaged feed scale is eight decimals from publisher metadata, and the equity feed represents tokenized total-return value. A token balance has its own decimals and potentially display-unit conventions; do not assume either matches feed scaling.
3. If current pricing is requested, follow [Safety](safety.md) and [public RPC guidance](integrations.md). Use bounded public reads to establish chain 4663 and a recent canonical head observation, recording block number/hash/time and retrieval time. Check head lag against current time under an explicit acceptable observation-lag bound for the use case; a provider's `latest` label alone does not prove recency. Then read `decimals()`, `description()` and `latestRoundData()` from the exact proxy at that same block. An old block with a then-fresh round is historical evidence, not a current price. If head recency cannot be established, label the result historical or recency-unverified. No wallet, impersonation, state override or state-changing simulation is needed; unavailable access never justifies inventing a price.
4. Decode `answer` as a signed integer and retain exact integer/decimal arithmetic. For a USD price, a nonpositive answer, zero or future `updatedAt`, malformed result or failed read is unusable. Report both round age at the observation block and elapsed age at retrieval/current time; freshness at a historical block does not establish freshness now. Apply the identified consumer's block-time policy separately from current-display recency, market-session and corporate-action conditions. Successful RPC execution alone is not an acceptance check; no recorded policy or observation-lag bound means current suitability remains unresolved.
5. Set `feed_decimals` to the successful `decimals()` result from the same proxy and observation block as `answer`, then divide by `10 ** feed_decimals`. Do not fall back to packaged eight-decimal metadata for a live answer. If the live scale conflicts with the package, stop current-price presentation and resolve the identity/configuration discrepancy before using it. **Synthetic arithmetic only:** if the answer were `12345678900` and the same-block decimals `8`, the reference mark would be `123.45678900 USD`. This is not an observed NVDA price. Show the round timestamp and block with any real observation; never apply a second corporate-action multiplier to the direct total-return feed mark.
6. Keep an oracle reference mark separate from an executable token quote, liquidity, collateral backing or redemption rights. The `rialtoRouterRegistry` record and [Rialto registry documentation](https://docs.rialto.xyz/developers/router-registries.md) identify conversion infrastructure, not a current quote or permission to trade. Explain [game conversion limits](games.md) without connecting a wallet or preparing a transaction.

For a directory response, return the eight feed identities, exact stock-token relationships where recorded, quote/scale, provenance status and scoped consumer limits. For a focused request, return only the selected relationship and missing evidence. Never silently promote “not recorded” to “verified,” and never infer a current price from packaged metadata.

## Generation and activation traps

- **RWA Desk:** Official Channels still publishes the original Desk while the app/local registry identifies a V2 successor. Preserve V1 historical activity and V2 activity separately; never use one address to query the other's entire history.
- **TURBO:** long-dated `TurboDesk` is not Loopback's `TurboRouter`. Versioned Desks/cards/adapters can have different claims and settlement rules.
- **Credit:** a listed or deployed router is not necessarily an active allocator. The live Credit-vault disclosure does not contradict a pending router grant. Preserve both router generations and check current permissions separately.
- **NetNetGear:** retired and current NFT/gear deployments are different from the BoardroomLoot library.
- **The Button and app-only products:** UI/bundle presence does not establish currently accepting entries. Documentation may be out of date, and published zero placeholders are not deployed addresses.
- **Pendle:** a market identity includes chain, maturity, SY/PT/YT and accounting asset. Never treat the September 17 maturity as an evergreen active market.

## Read-only identity procedure

1. Find the exact role and source, then match **chain ID plus full address**. Aliases help discovery but are not identifiers.
2. Identify whether the record is a contract, a public role, a market ID, an oracle input, a proxy, an implementation or an NFT/market instance.
3. Compare applicable official sources and generation dates. Explain conflicts rather than silently choosing the newest-looking string.
4. If permitted fresh read tools exist, check bytecode at a recorded block and inspect the relevant read-only state. Bytecode presence establishes only deployed code at that block—not ownership, intended function, activation or safety.
5. For proxies, determine the relevant implementation and control roles at the same block; do not treat an implementation's verified source as proof of the proxy's current behavior.
6. For claimed public ownership/control, use explicit source attribution or on-chain role evidence. Transfer history, funders and explorer labels alone do not prove a real person's identity.
7. Link the exact public explorer record, explain what was checked and what was not, and preserve source/block dates. Never verify by connecting, approving, signing, deploying or transacting.

The skill provides no keys, wallet connections, signing payloads, transaction execution or smart-contract safety warranty. See [Safety](safety.md).

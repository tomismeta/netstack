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
- `known_discrepancies` and `coverage`: generation conflicts, source boundaries, omitted zero placeholders, inaccessible material and missing verification.

A `local_definition` source in the catalog is a historical repository-provenance path, not a skill-relative dependency or web URL. The extracted facts are bundled. Prefer public corroboration for consumers without the originating repository.

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

# NFTs: collections, links and identity

Use this reference for `nfts`. With no further question, return the two collection links below, identify Robinhood Chain, and keep the verification caveat short. Do not retrieve prices or load the complete address inventory merely to provide these links.

## Collections

| Collection | Marketplace | Published contract role | Identity evidence |
|---|---|---|---|
| NetNet Gear | [OpenSea: NetNet Gear](https://opensea.io/collection/netnet-gear) | Current NetNetGear shared loot collection | [OpenSea collection API](https://api.opensea.io/api/v2/collections/netnet-gear) |
| Button Presser | [OpenSea: Button Presser](https://opensea.io/collection/button-presser) | buttonPresserCard | [OpenSea collection API](https://api.opensea.io/api/v2/collections/button-presser) |

Both collection URLs were supplied by the user. On **2026-09-10**, each OpenSea API response reported the corresponding collection slug/name, `NetNetCap` social account, and a `contracts` entry on `robinhood`. Those full addresses matched the existing records now routed by [address-index.json](../assets/address-index.json) for **Robinhood Chain, chain ID 4663**. The address book retains the exact values, API provenance and collection associations; [sources.json](../assets/sources.json) retains the source/review records.

This is **marketplace-to-registry identity corroboration**, not a new live-chain verification, proof of contract safety, or independent validation of OpenSea's badge. Current prices, supply, owners, royalties, listings and transfer conditions are mutable and are not frozen into this reference.

**Publisher badge claim:** on [August 28](https://x.com/NetNetCap/status/2093438514117616056), the publisher said the Button collection was verified on OpenSea. The September 10 API check corroborates identity only—not the badge, wallet count, mint distribution, Training Grounds mechanics or current operation. [Games retains the August 25/28 launch, jackpot, commemorative-plate and Training Grounds chronology](games.md#the-button--permanent-eligibility-and-discretionary-rounds), added through 2026-09-12 in this unpublished update.

## Keep the identities separate

- **NetNetGear** is the published shared loot collection. Its retired original deployment is a separate address, and **BoardroomLoot** is a separate library—not another name for the current collection.
- **Button Presser** maps to `buttonPresserCard`, not automatically to `presserCharacter` or `presserFaction`. Do not attach this marketplace link to every related contract.
- **ShareCertificate** is the separately documented nontransferable founding-cohort certificate. It is not either OpenSea collection. No marketplace link or future reward right is inferred for it.
- A collection page does not establish that its game accepts entries. THE BUTTON's [historical operation/documentation conflict](games.md#the-button--permanent-eligibility-and-discretionary-rounds) leaves current deployment and an armed pot unverified.

## Mechanics and ownership claims

For shared loot, see [Board Meeting](games.md#the-board-meeting--counterparties-choose-reward-systems-differ); for wallet eligibility versus card ownership, see [THE BUTTON](games.md#the-button--permanent-eligibility-and-discretionary-rounds). The founding certificate is covered in [Products](products.md#standard-bonds-staking-and-the-concluded-founding-offering) and [Glossary and FAQ](glossary-and-faq.md). Use [Addresses and roles](addresses-and-roles.md) for exact contracts and generations.

An NFT's artwork, name, trait, collection badge or marketplace listing does not by itself establish a claim on Treasury reserves, RWA assets, staking distributions, game prizes, redemption proceeds, intellectual-property rights or future rewards. Tie each claim to the particular documented product and token; state missing evidence rather than generalizing across collections.

## Read-only boundary

Public collection pages and APIs, including OpenSea, may be read for fresh research using ordinary host-permitted tools without a custom broker or per-source administrator setup. Use an unauthenticated context without wallet extensions/providers, WalletConnect, authenticated sessions or signing/broadcast paths. Never trigger wallet prompts, connect a wallet, mint, buy, sell, list, bid, accept an offer, approve a marketplace, sign a listing/permit, or submit a transaction, including through an agent-owned wallet or delegated service. A request for a floor price is an evidence question, not permission to trade. Apply [Safety](safety.md), use minimum public inputs and report unavailable evidence rather than obtaining credentials or changing host permissions.

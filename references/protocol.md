# NetNet Core protocol

**Source snapshot:** official pages linked below were read on **2026-09-10**. This is an offline explanation of published mechanics, not a contract audit or a fresh chain-state report. Parameters described as immutable are the documentation's claims about that deployment; several pages also label values as pre-deployment defaults. No balances, current rates, oracle health, permissions or available capacity were independently verified here. Resolve identities through [the packaged address index](../assets/address-index.json) and [Official Channels](https://docs.netnet.capital/official-channels), not token symbols alone.

This unpublished working update also incorporates separately dated original announcements through **2026-09-12**. They do not amend the documented Core formulas or independently establish deployed changes.

**Questions answered:** What does NET represent? Why do staked balances grow? What belongs in backing? How can reserves rise while backing per token falls? What do bonds, buybacks, fees and management options do? What does “no governance” actually cover?

## Purpose, chain and token forms

NetNet describes a USDG-reserve-backed token system in the OlympusDAO v1 architectural lineage: NET, rebasing sNET, Treasury, staking, Distributor and BondDepository, with a tax collector, genesis subscription, inverse bonds, premium seller and management options. It uses fund-style language, but its self-styled “prospectus” expressly disclaims being a legal prospectus or investment advice. Fund labels do not establish corporate equity rights, insured deposits or legal redemption entitlements. The documented deployment is **Robinhood Chain, chain ID 4663**, an Arbitrum Orbit L2; gas is ETH, whereas reserve accounting is denominated in USDG. [Overview](https://docs.netnet.capital/index), [mechanism](https://docs.netnet.capital/mechanism), [founding guide](https://docs.netnet.capital/founding-shareholder-guide).

| Instrument | Economic/accounting meaning |
|---|---|
| NET | Base reserve-backed token; unstaked units do not themselves rebase. Its market price and per-token backing are different quantities. |
| sNET | Rebasing claim on staked NET. The documented staking conversion is 1:1 at the current fragment balance. The fixed-gons accounting model changes balances through the rebase conversion factor, not a transfer to every holder. |
| wsNET | Non-rebasing wrapper of sNET. Its unit count need not grow for its underlying sNET/NET claim to grow with the index. It is Loopback collateral, not an independent reserve asset to add a second time. |
| pTEAM | Management's paid exercise right, not free genesis tokens, staked NET or a public governance vote. |

Sources: [mechanism §§1,6](https://docs.netnet.capital/mechanism), [Loopback](https://docs.netnet.capital/lending), [management compensation](https://docs.netnet.capital/team). Distinguish physical custody from beneficial claims: counting NET held by Staking, holders' sNET, and the wrapper's underlying sNET as three separate pools of wealth double-counts the same backing.

## Staking, emissions and the oracle

The documented epoch is **8 hours**, three scheduled epochs per day. A permissionless rebase distributes newly minted NET through proportional sNET balance growth. The cumulative rebase index tracks token-unit growth since launch. Elapsed time alone is not evidence that a successful distribution occurred. The premium-sensitive policy is:

```text
P = canonical-pair TWAP / NAV
per-epoch emission rate = 0.0045 × clamp((P − 1) / (1.75 − 1), 0, 1)
```

At or below NAV, the rate is zero; it scales linearly to the documented maximum at 1.75× NAV. Minting is additionally bounded by RFV headroom. The docs say a cap violation “reverts or clamps” and defer the exact deployed choice to contract natspec; do not select one behavior from this prose. These are policy parameters, **not today's rate**. [Mechanism §§1–4](https://docs.netnet.capital/mechanism).

The policy oracle uses cumulative observations from the canonical NET/USDG Uniswap v2 pair, not instantaneous spot. Documented valid windows are **30 minutes–4 hours**. Invalid/stale readings stop dependent market settlement and cause the Distributor to skip issuance; permissionless checkpointing does not mean someone has actually maintained the observation history. Sustained manipulation across the window remains possible, particularly in thin liquidity. “Fail closed” prevents use of a disallowed quote; it does not guarantee a fair quote, immediate recovery or continuous buyback availability. [Mechanism §2](https://docs.netnet.capital/mechanism), [risks §§9–10](https://docs.netnet.capital/risks).

Emission APR annualizes a current token-unit rate; APY compounds it under assumed repeated epochs. Neither is realized holder return. A holder's outcome also depends on premium/price changes, supply dilution, staking participation, fees, slippage and USDG's value. The documentation's APY table assumes a constant premium and a nonbinding reserve cap; do not present it as sustainable cash yield. [Mechanism §3](https://docs.netnet.capital/mechanism), [risks §§7–8,11](https://docs.netnet.capital/risks).

## Core backing: RFV, NAV and gross assets

“Core” here means the reserve accounting of the Treasury, not every NetNet-branded product. The documented identity, in consistent USDG valuation units, is:

```text
RFV = liquid Treasury USDG
    + Morpho gross position assets × 0.98
    + Treasury POL RFV
NAV = RFV / total NET supply

POL RFV = 2 × sqrt(pool USDG reserves × pool NET reserves)
        × Treasury share of the pool's LP supply
```

Apply the **2% Morpho haircut once**, to the gross USDG-denominated position assets, not to raw vault-share units and not again to a number already reported net of haircut. Gross assets include the position's asset value rather than only historical deposit principal. Use consistent scales and contract rounding before summing components. These equations express the published valuation convention, not realizable liquidation proceeds. [Treasury §§2–3](https://docs.netnet.capital/treasury).

POL is protocol-owned liquidity: Treasury-held LP tokens represent a proportional pool claim. The geometric-mean rule values the NET leg at the documented **1 USDG floor**, not at market spot; it is not the spot-marked sum of the two reserves. For an ordinary constant-product swap, the product is preserved before fees and can grow with fees, which is why the docs use this rule instead of a manipulable spot mark. That limited property is not proof against arbitrary contract failure, removal of assets, sustained oracle distortion or stablecoin loss. LP supplied as consideration for standard bonds uses the same convention. [Treasury §3](https://docs.netnet.capital/treasury), [mechanism §5](https://docs.netnet.capital/mechanism), [risks](https://docs.netnet.capital/risks).

The documented Morpho deployment cap is **70% of Treasury USDG**, with the remaining liquid portion intended to cover pending obligations and inverse-bond capacity. Formulaic rebalancing is permissionless; a withdrawal path is not a guarantee that Morpho has withdrawable liquidity during insolvency or an outage. The 2% haircut is an accounting allowance, not insurance against a large loss. [Treasury §2](https://docs.netnet.capital/treasury), [risks §5](https://docs.netnet.capital/risks).

**Exclude from Core RFV:** team-custodied RWA Sleeve assets, direct Loopback lender principal, nnUSDG/Credit loan assets, futures test margin and underwriting capital, and other outside-Core product pots. A separately attributed USDG remittance that actually reaches Treasury can enter Core; product branding, a discretionary support promise or an unrealized stock gain cannot. Do not add Morpho gross and net values together, or add Treasury LP look-through assets on top of POL RFV. [Treasury §§1,5–6](https://docs.netnet.capital/treasury), [RWA Desk](https://docs.netnet.capital/rwa-desk), [Loopback](https://docs.netnet.capital/lending), [Credit](https://docs.netnet.capital/credit), [futures](https://docs.netnet.capital/futures).

**Social “Treasury” is not a reserve-accounting definition.** Combined Treasury/Sleeve forecasts and game-income headlines do not establish Core RFV or earnings without a separately evidenced Core transfer. See [RWA strategy: forecast perimeter and social accounting](rwa-strategy.md#september-11-forecast-treasury-plus-manager-sleeve-not-core-rfv) for the dated claims and unresolved routing.

### Supply, premium and return are different denominators

- **RFV** is the reserve numerator; **NAV** divides it by **total NET supply**, not only unstaked tokens or management-option float.
- **Market capitalization** uses a market price and an explicitly identified supply definition. It is not RFV. **Policy premium** is TWAP/NAV, not spot/NAV unless explicitly labeled as a separate spot comparison.
- **Circulating float for pTEAM** has special exclusions: protocol-held/escrowed NET, including the documented Treasury, InverseBond escrow, TaxCollector accrual and unvested genesis/bond balances; staked NET and pool NET are included. It is not interchangeable with total supply.
- For matched snapshots, `NAV1/NAV0 = (RFV1/RFV0) / (supply1/supply0)`. Growing reserves can coexist with declining per-token backing if supply grows faster. NAV growth in USDG is not a holder's USD gain.

Sources: [Treasury §3](https://docs.netnet.capital/treasury), [mechanism §§2,4](https://docs.netnet.capital/mechanism), [team §1](https://docs.netnet.capital/team). The ratio identity is algebra, not a forecast; historical comparisons require matched accounting definitions and observation anchors.

## Issuance, bonds and support around NAV

| Path | Reserve/supply effect and relevant restriction |
|---|---|
| Standard primary bond | USDG or canonical v2 LP consideration enters the reserve system; NET is issued for a vesting claim. Documented price is `max(TWAP × (1 − bond discount), NAV)`, subject to epoch capacity. At the NAV floor it can be backing-neutral, not necessarily strictly accretive. |
| Distributor epoch mint | New NET funds rebases. It may dilute NAV above the floor and is constrained by the premium gate and RFV headroom. |
| pTEAM exercise | Management pays 1 USDG for each new NET; this adds reserve principal but can dilute NAV when pre-exercise NAV exceeds the strike. |
| Inverse bond / Buyback Program | Treasury pays USDG for NET that is burned, at documented `NAV × 0.985`. A below-NAV burn can raise NAV while reducing total RFV. Capacity is documented as 1% of liquid non-Morpho reserves per 8-hour epoch, with no rollover; valid oracle inputs are still required. |
| PremiumSeller | Above the documented 2× NAV TWAP threshold, a bounded clip of newly minted NET is sold to the canonical pool and USDG swept to Treasury. Clip/slippage/interval bounds and a working oracle constrain availability; this is not an unrestricted Treasury ask. |
| RWA subscription | Transfers existing Desk inventory, not a new mint at purchase. Historical pTEAM-funded and September 12 announced bought-NET inventory have distinct provenance; do not carry the old remittance formula into the new path. See [Products](products.md#september-12-manager-funded-bid-and-bought-net-inventory). |

Sources: [mechanism §§4–5](https://docs.netnet.capital/mechanism), [Treasury §4](https://docs.netnet.capital/treasury), [team](https://docs.netnet.capital/team), [RWA Desk](https://docs.netnet.capital/rwa-desk).

**Manager policy is separate:** the September 12 **Manager-funded 2× NAV bid** announces purchases for Desk redistribution, not PremiumSeller issuance, inverse-bond burns or Loopback collateral valuation. It adds neither automatic redemption nor the Manager's balance sheet to RFV; execution and backing accretion remain unverified. See [Products: announcement, limits and inventory generations](products.md#september-12-manager-funded-bid-and-bought-net-inventory).

The **1 USDG-per-NET reserve-floor invariant is not guaranteed cash redemption**, an exchange-price peg or unlimited exit liquidity. Inverse bonds have capacity, spread and oracle restrictions. USDG can depeg; reserve assets and contracts can fail; L2 outages can halt settlement. Read the documentation's “global accretion” claim as a reported contract/test invariant with two named NAV-diluting exceptions—epoch issuance and pTEAM exercise—not an independently audited guarantee of economic gains or protection from external loss. [Mechanism §4](https://docs.netnet.capital/mechanism), [risks §§1,5–6,9–11](https://docs.netnet.capital/risks).

## Trading fees and management compensation

The published NET fee is **5% on transfers to/from mapped AMM pair addresses**; ordinary wallet transfers and documented whitelisted protocol flows are exempt. It is token-level fee-on-transfer behavior, in addition to AMM fees and slippage, so integrations cannot assume sent units equal received units. NET fees accrue to TaxCollector and are converted in bounded batches to USDG. The total fee is documented immutable; fee conversion and the split are separate from collection. [Fee schedule §§1–4](https://docs.netnet.capital/FEES.HTM).

The split uses the pTEAM vesting clock from genesis finalization: management receives `400 × (1−v)` basis points of taxable volume and Treasury receives the balance of 500 bps, where `v` reaches one over 30 days. Thus the schedule moves from 4% management/1% Treasury to 0%/5%. The offering page reports finalization on **2026-07-16**; the schedule therefore describes a concluded launch period, but no current on-chain split was queried here. “Management's fee has ended” does not mean the 5% trader fee has ended. [Fees §2](https://docs.netnet.capital/FEES.HTM), [offering](https://docs.netnet.capital/OFFERING.HTM).

pTEAM exercise rights vest over 30 days, do not expire, and cap cumulative exercised NET against **15% of eligible circulating supply at each exercise**, including the documented vesting fraction. Supply growth can create additional exercise headroom; this is not 15% of a fixed genesis allocation, nor does the formula prove management still owns all exercised tokens. The strike adds reserves but can lower NAV toward the floor. [Team §1](https://docs.netnet.capital/team), [risks §4](https://docs.netnet.capital/risks).

**Compensation scope caveat:** `/team` calls pTEAM and the decaying trading-fee share the “complete list,” but newer product pages describe additional product-specific flows—for example Credit's 10% interest performance fee paid to the Manager's RWA Sleeve. Treat the older statement as a Core compensation description, not a complete consolidated account of every desk or managed entity. [Team](https://docs.netnet.capital/team), [Credit fees](https://docs.netnet.capital/credit).

## Authority, risks and documentary cautions

Core emissions policy is documented without owner controls or a parameter-change path short of redeployment. Operational permissionlessness is not guaranteed liveness: someone must submit successful calls, and chain/oracle/liquidity preconditions must hold. The fee pair mapping and exemption list are described as add-only, with factory-validated pair additions and timelocked exemptions. The disclosed team Safe is **1-of-1**, so the word “multisig” does not imply independent approval redundancy. Product-specific managers, menus, vault roles and custody remain real: **“no governance” is not a claim that the entire NetNet ecosystem has no privileged controls.** [Mechanism §§7–8](https://docs.netnet.capital/mechanism), [fees §1](https://docs.netnet.capital/FEES.HTM), [risks §§3,6](https://docs.netnet.capital/risks), [RWA Desk](https://docs.netnet.capital/rwa-desk), [Credit roles](https://docs.netnet.capital/credit).

Retain these unresolved publication issues rather than silently repairing them into verified facts:

1. **Fee coverage conflict:** `/FEES.HTM` describes monitoring and adding v4/UniswapX venues; `/risks` says the address-keyed tax cannot cover them and calls this permanent. Both warn of bypass. Do not claim universal enforcement or that monitoring solves the singleton mismatch.
2. **Accretion wording:** standard bonds priced exactly at NAV are weakly accretive/backing-neutral by the published formula, despite “strictly accretive” prose. The docs also leave reserve-cap clamp versus revert unspecified.
3. **Option economics:** `/team`'s worked example has inconsistent incremental token/payment amounts. Its claim that management can profit only above NAV is stronger than a 1-USDG strike implies: market price may exceed strike while remaining below NAV. Do not reproduce either conclusion as arithmetic proof.
4. **Historical offering arithmetic:** the source distinguishes idealized launch NAV around 2.41 USDG from roughly 2.39 with full documented Morpho deployment/haircut. These are dated launch calculations, not current NAV. The binding historical terms belong to the [offering page](https://docs.netnet.capital/OFFERING.HTM), not a reused launch checklist.

No positive holder-value outcome is promised by this reference. Principal loss, thin exits, transfer-tax friction, oracle manipulation/outage, USDG depeg, Morpho loss, chain failure and unpatchable Core defects remain relevant even when the formulas are followed. [Risk factors](https://docs.netnet.capital/risks).

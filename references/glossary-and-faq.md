# Glossary and frequently confused claims

**Source/as-of note:** official pages cited here were read on **2026-09-10**. This offline guide summarizes documented mechanics and distinctions; it does not verify live balances, contract permissions, deployment runtime, available inventory, prices or returns. The [address registry](../assets/addresses.json) separates exact identities from prose; [Official Channels](https://docs.netnet.capital/official-channels) is the direct official source. Current figures require a dated, scoped observation, not reuse of a launch table.

**Questions answered:** Is RFV market cap? Can every NET immediately redeem at NAV? Do stock holdings back NET? Is rebase APY income? Is nnUSDG cash? Which “Turbo” is meant? How should missing current status and inconsistent documentation be reported?

## Compact glossary

| Term | Meaning and boundary | Source |
|---|---|---|
| Core / Treasury | The NET reserve-accounting system. Not every asset managed by the team or every NetNet-branded program. | [Treasury](https://docs.netnet.capital/treasury) |
| USDG | Reserve/loan denomination. A USDG amount is not a guarantee of equal USD purchasing power or issuer redemption. ETH pays Robinhood Chain gas. | [Risks §11](https://docs.netnet.capital/risks), [guide](https://docs.netnet.capital/founding-shareholder-guide) |
| RFV | “Risk-free value”: the protocol's conservative reserve valuation, including haircutted Morpho and floor-valued POL. The name is not a risk assessment or insurance. | [Treasury §3](https://docs.netnet.capital/treasury) |
| NAV / backing per token | RFV divided by total NET supply, in USDG per NET. Not exchange price or an unconditional redeemable cash balance. | [Treasury §§3–4](https://docs.netnet.capital/treasury) |
| Market cap | Market price multiplied by a stated supply measure. Using total, circulating or another supply definition changes the answer; none substitutes for reserve RFV. | Derived distinction from [Treasury](https://docs.netnet.capital/treasury), [team float definition](https://docs.netnet.capital/team) |
| Premium | Policy TWAP/NAV multiple. A spot-price premium is a different measurement and must be labeled. “Premium” can also mean price above the 1-USDG floor in loose prose; state the denominator. | [Mechanism §2](https://docs.netnet.capital/mechanism), [team](https://docs.netnet.capital/team) |
| NET / sNET / wsNET | Base token / rebasing staked claim / non-rebasing wrapper of that staked claim. Three token representations are not three separate reserve pools. | [Mechanism §§1,6](https://docs.netnet.capital/mechanism), [Loopback](https://docs.netnet.capital/lending) |
| Gons / fragments | sNET's fixed internal ownership units and its changing displayed balance units. Rebase growth need not appear as ordinary per-holder transfers. | [Mechanism §6](https://docs.netnet.capital/mechanism) |
| Rebase / epoch / index | Proportional staking-unit growth, an eight-hour schedule, and the cumulative conversion/growth index. Scheduled time is not proof of successful issuance. | [Mechanism §§1–4](https://docs.netnet.capital/mechanism) |
| APR / APY | Annualized simple rate / assumed compounded rate. For rebases these describe NET-unit arithmetic, not assured USDG or USD returns. | [Mechanism §3](https://docs.netnet.capital/mechanism) |
| TWAP | Time-weighted average price from cumulative canonical-pair observations. Not spot; a valid observation window is not immunity to sustained manipulation. | [Mechanism §2](https://docs.netnet.capital/mechanism), [risks §10](https://docs.netnet.capital/risks) |
| POL | Protocol-owned liquidity: Treasury's LP claim. Its RFV uses a proportional geometric mean with NET at its reserve floor, not a market-price portfolio mark. | [Treasury §3](https://docs.netnet.capital/treasury) |
| Morpho gross / net | USDG value of the reserve position before / after the documented RFV haircut. Neither is raw vault-share count; never sum gross and net as separate assets. | [Treasury §§2–3](https://docs.netnet.capital/treasury) |
| Primary Offering / bond | NET subscription under a vesting claim. Standard bonds issue against reserve consideration; RWA bonds distribute pre-exercised inventory under different flows. | [Mechanism §5](https://docs.netnet.capital/mechanism), [RWA Desk](https://docs.netnet.capital/rwa-desk) |
| Inverse bond / Buyback Program | Seller-initiated, capacity-limited Treasury purchase and burn below NAV; not unlimited redeemability at NAV. | [Treasury §4](https://docs.netnet.capital/treasury) |
| PremiumSeller | Formulaic bounded NET issuance/sale when TWAP exceeds its NAV threshold, with USDG swept to Treasury. | [Treasury §4](https://docs.netnet.capital/treasury) |
| pTEAM / float | Paid management exercise right / specially defined circulating supply used to cap cumulative exercise. The float excludes specified protocol escrow and is not total supply. | [Team](https://docs.netnet.capital/team) |
| Reserve remittance / high-water mark | RWA subscription's separate Treasury contribution / ratcheting backing reference used to size it. Not the stock-purchase leg or a generic fee-rate assumption. | [RWA Desk](https://docs.netnet.capital/rwa-desk) |
| RWA Sleeve | Manager-custodied equity assets earmarked for stated protocol benefit, outside Core RFV/NAV. It can also be a borrower with encumbered collateral. | [RWA Desk](https://docs.netnet.capital/rwa-desk), [Credit](https://docs.netnet.capital/credit) |
| Loopback / LLTV | Isolated wsNET-collateral USDG lending / liquidation loan-to-value threshold at the market's credited oracle mark, not necessarily executable market value. | [Loopback](https://docs.netnet.capital/lending) |
| nnUSDG | Shares in NetNet Credit's curated USDG loan portfolio, exposed to liquidity restrictions and loan losses; not USDG or Treasury-backed NET. | [Credit](https://docs.netnet.capital/credit) |
| Curator / allocator / sentinel | Credit roles setting risk permissions, allocating within bounds, or cancelling/reducing exposures. Not Core emission-policy governance. | [Credit roles](https://docs.netnet.capital/credit) |
| tNET / underwriting shares | Valueless futures test margin / shares in the test venue's counterparty equity. No claim on Core Treasury. | [Futures](https://docs.netnet.capital/futures) |
| Fee revenue / principal / PnL | A specified earned fee / contributed or returned capital / economic profit or loss. A token transfer or large product volume alone establishes none of these classifications. | Applied accounting distinction from [fees](https://docs.netnet.capital/FEES.HTM), [RWA Desk](https://docs.netnet.capital/rwa-desk), [Credit](https://docs.netnet.capital/credit), [futures](https://docs.netnet.capital/futures) |

## High-value FAQ

### Is “risk-free value” risk-free, or the protocol's market cap?

No. RFV is a named accounting rule: liquid USDG, Morpho position value after its documented 2% haircut, and floor-valued POL. Market cap instead depends on market price and a stated supply measure. USDG, Morpho, pool contracts and chain operations still carry risk. A 2% haircut cannot cap a larger actual loss. [Treasury §§2–3](https://docs.netnet.capital/treasury), [risks §§5,10–11](https://docs.netnet.capital/risks).

### Does the 1 USDG floor mean every NET can redeem for 1 USDG or NAV immediately?

No. The floor is a documented mint/reserve invariant in **USDG**, not an unlimited cash-redemption right or guaranteed exchange peg. The inverse bond pays below NAV, has an epoch capacity tied to liquid reserves, and depends on usable oracle inputs and functioning contracts. Thin pool depth, reserve impairment and USDG depeg are separate risks. Never relabel reserve backing as “cash available to all holders now.” [Mechanism §4](https://docs.netnet.capital/mechanism), [Treasury §4](https://docs.netnet.capital/treasury), [risks §§1,5,9,11](https://docs.netnet.capital/risks).

### The Sleeve owns stocks. Does that raise NET's NAV?

Not merely by holding or marking them up. Sleeve assets are team-custodied and explicitly excluded from Core RFV/NAV. They may support Core only through a future discretionary action, not an automatic contract guarantee. The RWA subscriber receives NET, not the equity purchased with the equity leg. Credit also documents Sleeve borrowing, so a gross stock inventory is not a net-of-debt or unencumbered portfolio value. [RWA Desk](https://docs.netnet.capital/rwa-desk), [Treasury §5](https://docs.netnet.capital/treasury), [Credit](https://docs.netnet.capital/credit).

### Is a bond payment all fee income? Does an RWA purchase mint NET?

No to both shortcuts. A standard bond brings reserve consideration against issuance; a pTEAM exercise brings strike principal; an RWA subscription delivers pre-exercised inventory and splits payment into Treasury remittance and an outside-Core equity purchase. The subscription's inventory distribution is not a second mint. Distinguish reserves formed, explicit fee revenue, loan/deposit principal, burns and outside-Core activity rather than treating all inbound transfers or product volume as earnings. [Mechanism §5](https://docs.netnet.capital/mechanism), [team](https://docs.netnet.capital/team), [RWA Desk](https://docs.netnet.capital/rwa-desk).

### If sNET grows every epoch, how could I lose money?

More NET units can be worth less in aggregate after a market-price decline, premium compression, fees or USDG depeg. Emissions add supply and may dilute NAV above the floor. The published rate can be zero at/below NAV, constrained by reserves or skipped with an invalid oracle. Annualizing or compounding today's rate assumes future conditions that have not happened. A leveraged holder must also pay borrow interest and may be liquidated. [Mechanism §§2–4](https://docs.netnet.capital/mechanism), [risks §§7–11](https://docs.netnet.capital/risks), [Loopback](https://docs.netnet.capital/lending).

### wsNET balance stayed constant. Did I miss the rebase?

Not necessarily. wsNET is intentionally non-rebasing: the underlying claim per wrapper unit follows the index rather than minting more wrapper units into every wallet. Evaluate balance and conversion index together at a common observation. Conversely, a higher index alone does not prove a dollar profit or that a particular wallet held the position throughout the period. [Mechanism §6](https://docs.netnet.capital/mechanism), [Loopback](https://docs.netnet.capital/lending).

### Can Treasury RFV rise while NAV falls? Can NAV rise while my USD balance falls?

Yes. NAV divides RFV by supply; if supply grows faster, per-token backing declines. A below-NAV buyback can do the opposite: total reserves fall while per-token backing rises because the token denominator shrinks faster. A holder's market exit value additionally depends on token quantity, market price, fees, slippage and USDG/USD. A change in NAV is therefore neither total protocol earnings nor a realized holder return. [Treasury §§3–4](https://docs.netnet.capital/treasury), [mechanism §4](https://docs.netnet.capital/mechanism), [risks](https://docs.netnet.capital/risks).

### Are all NET amounts the same raw units?

No. Token base units, rebasing fragments, internal gons, wrapper units, reserve-valuation units and oracle scales are separate dimensions. The docs explicitly describe NET as having 9 decimals via the tNET comparison and wsNET as 18 decimals; the exact sNET/USDG metadata and accounting scales should be taken from the matched identity/source records rather than guessed from a displayed symbol. RFV is a normalized reserve value, not automatically an ERC-20 `balanceOf` amount. [Futures §1](https://docs.netnet.capital/futures), [Loopback terms](https://docs.netnet.capital/lending), [mechanism §6](https://docs.netnet.capital/mechanism), [Treasury §3](https://docs.netnet.capital/treasury), [packaged identities](../assets/addresses.json).

Keep **asset identity + amountRaw + decimals + unit basis + observation anchor** together. `1,000,000,000` raw units at 9 decimals is 1 token; the same integer at 18 decimals is one-billionth of a token. Apply the contract's integer rounding and avoid binary floating-point arithmetic for raw amounts. A generic 18-decimal “wad” normalization does not imply the underlying token has 18 native decimals. These are arithmetic/unit-handling rules, not a new protocol parameter.

### Is the 5% fee on every transfer, and does it disappear after day 30?

No. The documented token tax applies to transfers involving mapped AMM pairs, with ordinary wallet transfers and whitelisted protocol paths exempt. Day 30 eliminates management's share, **not the total tax**: the formula leaves the 5% Treasury share. Fee-on-transfer compatibility must be distinguished from AMM fees and slippage. The fee schedule and risk page conflict about v4/UniswapX enforcement; do not claim all venues are covered. [Fees](https://docs.netnet.capital/FEES.HTM), [risks §§2,7](https://docs.netnet.capital/risks).

Also avoid copying the risk page's “−10% round trip” as exact compounded arithmetic. Two independent 5% proportional deductions leave `0.95² = 0.9025`, a 9.75% reduction before price changes, AMM fees and slippage, if applied to sequential token amounts on that simplified basis. Actual trade costs require the route's fee basis; neither shorthand is an executable quote.

### Does “no governance” mean the Manager cannot change anything anywhere?

No. It describes the Core policy's lack of in-place parameter controls. The fee map/exemptions retain bounded permissioned additions; the RWA Desk has Manager menu/discount discretion within limits and the Sleeve has custody; Credit has owner/curator/allocator/sentinel roles. The disclosed team Safe is 1-of-1. Read authority per contract and product, not as an ecosystem-wide slogan. Immutability also means a Core bug or bad parameter cannot simply be paused or repaired in place. [Mechanism §§7–8](https://docs.netnet.capital/mechanism), [fees §1](https://docs.netnet.capital/FEES.HTM), [risks §§3,6](https://docs.netnet.capital/risks), [RWA Desk](https://docs.netnet.capital/rwa-desk), [Credit](https://docs.netnet.capital/credit).

### Is management capped at a fixed founding allocation, or paid only when NET is above NAV?

No. pTEAM uses a perpetual paid exercise right with a cumulative cap that depends on eligible circulating supply at each exercise, not a fixed genesis snapshot. Supply growth can create new headroom. Its 1 USDG strike can dilute NAV above the floor. The `/team` example has inconsistent incremental amounts, and its “only above NAV” profitability assertion does not follow from the strike: a market price above strike can still be below NAV. Separate the actual formula from promotional interpretation and do not infer current holdings from cumulative exercised supply. [Team](https://docs.netnet.capital/team), [risks §4](https://docs.netnet.capital/risks).

The same page's “complete list” of compensation is also not a complete product-wide consolidation: newer Credit docs disclose an interest performance fee to the Manager's RWA Sleeve. [Credit fees](https://docs.netnet.capital/credit).

### Is the founding subscription still open? Does a share certificate guarantee future rewards?

The read offering and guide say **closed**, finalized on **2026-07-16**, with the five-day vest complete. The certificate is a nontransferable cohort record with no promised launch perk. Old approval/subscription/checklist text is historical, not evidence of a reopened sale; unclaimed vested NET is separately described as not expiring. Consult the offering page for binding historical terms, including the difference between idealized launch NAV and the haircut-adjusted figure. None is today's NAV. [Offering](https://docs.netnet.capital/OFFERING.HTM), [founding guide](https://docs.netnet.capital/founding-shareholder-guide).

### Are Loopback deposits and nnUSDG backed by the Treasury?

No. Direct Loopback lenders own exposure to that isolated wsNET/USDG market. nnUSDG holders own shares of a curated portfolio that includes the same market plus six stock markets. Neither lender claim is NET NAV or a Treasury liability; losses and withdrawal constraints arise from borrowers, collateral, oracles and liquidity. Core's own Morpho reserve placement is a separate exposure, not proof it funds every Morpho market. Credit's principal Stock Token borrower is the curator's own Sleeve, an important concentration/conflict disclosure. [Loopback](https://docs.netnet.capital/lending), [Credit](https://docs.netnet.capital/credit), [Treasury](https://docs.netnet.capital/treasury).

### How can Credit be live while its router is pending activation?

A deployed vault, direct Morpho borrowing and a router-assisted interface are different surfaces. The docs report the vault operating and a first Sleeve loan, while the CreditRouter still lacks an allocator grant and app Stock Token borrow buttons are disabled. wsNET borrowing uses Morpho directly. Do not infer that the first stock loan used the unactivated router, or equate a published contract address with present permission to serve users. [Credit borrow/status sections](https://docs.netnet.capital/credit), [official registry](https://docs.netnet.capital/official-channels).

### Does “fail closed” stop losses or just operations?

It stops the operations specified by each contract's guard. Core's invalid TWAP stops dependent issuance/settlement; Loopback and Credit can block liquidation as well as borrowing when pricing refuses. Debt, outside-market economic risk and reopening gaps can persist while displayed health is stale. Credit's equity-feed tolerances are not a universal freshness policy for Sleeve valuations, futures or Core. Identify exactly which guard failed and which operations it affects; “safe because paused” is not justified. [Mechanism §2](https://docs.netnet.capital/mechanism), [Loopback stale guard](https://docs.netnet.capital/lending), [Credit oracles](https://docs.netnet.capital/credit), [futures](https://docs.netnet.capital/futures).

### Do futures profits or underwriting balances contribute to Core earnings?

Not in the documented test program. tNET has no value or Treasury claim. Test fees terminate in a holding sink; the loss waterfall never reaches Treasury. Real wsNET margin and a Treasury fee route are described as a future production path, not current operation. A real mainnet transaction is proof of execution, not proof that its currency represents economic value. [Futures §§1,4–6,9](https://docs.netnet.capital/futures).

### Which “Turbo” is meant?

Loopback's TurboRouter is leveraged NET accumulation through borrowing, buying, staking and wrapping. The **Long-Dated TURBO Desk** is a separately named product; **TURBO BLACKJACK** is another distinct desk using TURBO cards. Do not join their positions, fees or deployment identities merely because the labels overlap. [Loopback](https://docs.netnet.capital/lending), [official registry](https://docs.netnet.capital/official-channels), [games.md](games.md).

### What should an answer say when today's state is missing or sources disagree?

Use a scoped statement, not a fabricated number: **“The documentation read on 2026-09-10 says X; the current permission/oracle/inventory state was not observed.”** Missing data is not zero, a failed dashboard read is not proof of no holdings, and deployment is not activation. Historical terms remain historical even when still visible in an app.

Concrete conflicts to retain: official channels lists the original RWA Desk while the official application's registry publishes a V2 successor; the fee schedule and risk page disagree on v4/UniswapX taxability; the RWA page alternates buyer-choice and most-underweight menu descriptions and halt/floor wording; Core documentation does not settle cap-clamp versus revert. Preserve each claim's source and date, keep unaffected explanatory knowledge usable, and do not invent a single verified runtime truth. Details: [products.md](products.md), [protocol.md](protocol.md), [addresses-and-roles.md](addresses-and-roles.md).

For a current analytic view, the skill's primary dashboard is [NetNet Navigator](https://netnet.exe.xyz/). A dashboard observation needs its own block/time, scope and completeness; it does not silently supersede either published terms or a verified contract observation. No transaction, wallet, signature or execution instruction is needed to explain these distinctions.

# Glossary and frequently confused claims

**Source/as-of note:** official pages cited here were read on **2026-09-10**. This offline guide summarizes documented mechanics and distinctions; it does not verify live balances, contract permissions, deployment runtime, available inventory, prices or returns. The [address index](../assets/address-index.json) separates exact identities from prose; [Official Channels](https://docs.netnet.capital/official-channels) is the direct official source. Current figures require a dated, scoped observation, not reuse of a launch table.

Targeted product and source additions through **2026-09-18** are incorporated as attributed, dated evidence. These observations do not refresh every older source, establish all current permissions, or override generation-specific terms.

**Questions answered:** Is RFV market cap? Can every NET immediately redeem at NAV? Do stock holdings back NET? Is rebase APY income? Is nnUSDG cash? Which “Turbo” is meant? How should missing current status and inconsistent documentation be reported?

## Compact glossary

| Term | Meaning and boundary | Source |
|---|---|---|
| Core / Treasury | Core means NET reserve accounting. Social “Treasury” may instead include Manager/Sleeve assets; identify the source's perimeter before comparing figures. | [Treasury](https://docs.netnet.capital/treasury), [September 11 combined-assets chart](https://x.com/NetNetCap/status/2098506509508579787) |
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
| Primary Offering / bond | NET subscription under a vesting claim. Standard bonds issue against reserve consideration; RWA bonds distribute inventory (historically pre-exercised; September 12 announces bought NET). | [Mechanism §5](https://docs.netnet.capital/mechanism), [RWA Desk](https://docs.netnet.capital/rwa-desk), [September 12 announcement](https://x.com/NetNetCap/status/2098803824282771690) |
| Inverse bond / Buyback Program | Seller-initiated, capacity-limited Treasury purchase and burn below NAV; not unlimited redeemability at NAV. | [Treasury §4](https://docs.netnet.capital/treasury) |
| PremiumSeller | Formulaic bounded NET issuance/sale when TWAP exceeds its NAV threshold, with USDG swept to Treasury. | [Treasury §4](https://docs.netnet.capital/treasury) |
| Manager 2× NAV bid | September 12 announcement of Manager-funded NET purchases for RWA Desk inventory, not a Core mechanism, burn or guaranteed redemption. Capacity, NAV definition and implementation are unresolved. | [Products: evidence and limits](products.md#september-12-manager-funded-bid-and-bought-net-inventory) |
| pTEAM / float | Paid management exercise right / specially defined circulating supply used to cap cumulative exercise. The float excludes specified protocol escrow and is not total supply. | [Team](https://docs.netnet.capital/team) |
| Reserve remittance / high-water mark | Older RWA design's separate Treasury contribution / ratcheting backing reference. Its pre-exercise strike deduction is not an established formula for September 12 bought inventory. | [RWA Desk](https://docs.netnet.capital/rwa-desk), [September 12 announcement](https://x.com/NetNetCap/status/2098803824282771690) |
| RWA Sleeve | Manager-custodied assets and off-wallet claims earmarked for stated protocol benefit, outside Core RFV/NAV. The official memo includes stocks, cash, Credit/LP/TURBO positions, Predict vault assets and THE BOOK house-pot wsNET, with scoped Credit debt deductions; it is not all free wallet equity. | [RWA Desk](https://docs.netnet.capital/rwa-desk), [Reports methodology](rwa-strategy.md#official-reports-sleeve-memo-methodology) |
| Loopback / LLTV | Isolated wsNET-collateral USDG lending / liquidation loan-to-value threshold at the market's credited oracle mark, not necessarily executable market value. | [Loopback](https://docs.netnet.capital/lending) |
| nnUSDG | Shares in NetNet Credit's curated USDG loan portfolio, exposed to liquidity restrictions and loan losses; not USDG or Treasury-backed NET. | [Credit](https://docs.netnet.capital/credit) |
| Curator / allocator / sentinel | Credit roles setting risk permissions, allocating within bounds, or cancelling/reducing exposures. Not Core emission-policy governance. | [Credit roles](https://docs.netnet.capital/credit) |
| tNET / underwriting shares | Valueless futures test margin / shares in the test venue's counterparty equity. No claim on Core Treasury. | [Futures](https://docs.netnet.capital/futures) |
| Predict / outcome token | A weekly binary prediction market / a series-specific HIGHER or LOWER claim. The app's Treasury + Sleeve display is not Core RFV or backing per NET. | [Predict mechanics and limits](products.md), [launch](https://x.com/NetNetCap/status/2100913543453266186) |
| House Vault | Predict's depositor-funded house exposure, sharing fees and losses through weekly share prices. Not nnUSDG lending, AMM liquidity or guaranteed USDG principal. | [House Vault](products.md), [announcement](https://x.com/NetNetCap/status/2100913545831424358) |
| Retail v2 LP / LP Zap | Fungible NET/USDG pool receipt / a separate USDG entry helper. On September 18 the app offered direct Uniswap provision while the deployed Zap remained gated. Pool fees, NET levy and staking distributions are distinct. | [Liquidity provision](products.md), [integration boundaries](integrations.md) |
| Fee revenue / principal / PnL | A specified earned fee / contributed or returned capital / economic profit or loss. A token transfer or large product volume alone establishes none of these classifications. | Applied accounting distinction from [fees](https://docs.netnet.capital/FEES.HTM), [RWA Desk](https://docs.netnet.capital/rwa-desk), [Credit](https://docs.netnet.capital/credit), [futures](https://docs.netnet.capital/futures) |

## High-value FAQ

### Is “risk-free value” risk-free, or the protocol's market cap?

No. RFV is reserve accounting, not market cap or insurance: liquid USDG, Morpho value after a **2% haircut**, and floor-valued POL. USDG, Morpho, contracts and chain risks remain; losses can exceed the haircut. See [Core backing](protocol.md#core-backing-rfv-nav-and-gross-assets) for the formula and valuation limits.

### Does the 1 USDG floor mean every NET can redeem for 1 USDG or NAV immediately?

No. The **1 USDG** floor is a documented reserve invariant, not a cash-redemption right or exchange peg. Inverse bonds pay below NAV within liquid-reserve epoch capacity and require usable oracles/contracts; reserve loss, thin exits and USDG depeg remain possible. See [Core issuance and support](protocol.md#issuance-bonds-and-support-around-nav) for exact terms.

### Does the new 2× NAV bid guarantee an exit or replace inverse bonds?

No. The **September 12 Manager-funded 2× NAV bid** announces purchases for Real World Bonds inventory, not a Core purchase-and-burn or PremiumSeller issuance. Funding, venue, NAV definition, implementation and execution remain unverified; it creates no automatic redemption or new Core backing. See [Products: bid, inventory and mechanism contrasts](products.md#september-12-manager-funded-bid-and-bought-net-inventory), including the separate Loopback collateral mark.

### Does the $100 million “Treasury” forecast describe Core reserves?

No. The **September 11 chart** combines **Treasury + Manager Sleeve**, projecting **$100 million around October 17** under sustained **4× premium and bond demand**. It is conditional, separate from September 8 FY-HI, and not Core RFV or a net-of-debt portfolio reconciliation. September 3–4 “Treasury” game-income claims likewise cannot be booked as Core earnings where disclosures route funds to Sleeve or leave routing unresolved. See [RWA strategy: forecasts and social accounting](rwa-strategy.md#september-11-forecast-treasury-plus-manager-sleeve-not-core-rfv) for sources and per-claim conflicts.

### The Sleeve owns stocks. Does that raise NET's NAV?

No. Team-custodied Sleeve stocks are **excluded from Core RFV/NAV**; support is discretionary, not guaranteed. RWA subscribers receive NET, not those equities, and Sleeve borrowing means gross stock value is not net, unencumbered equity. See [Sleeve claims and risks](products.md#sleeve-ownership-claims-and-risks) and [the accounting boundary](rwa-strategy.md#the-non-negotiable-accounting-boundary).

### Is a bond payment all fee income? Does an RWA purchase mint NET?

No. Standard bonds bring reserve consideration against issuance; pTEAM exercise brings strike principal. RWA subscriptions transfer existing inventory—historically pre-exercised, with bought NET announced September 12—not a new mint or burn. Neither gross subscriptions nor inbound transfers are automatically earnings. The old **`high-water backing − 1 USDG` remittance is not established for bought inventory**. See [Products: historical flow](products.md#historical-documented-economic-flow) and [the announced inventory change](products.md#september-12-manager-funded-bid-and-bought-net-inventory).

### If sNET grows every epoch, how could I lose money?

More units can be worth less after price declines, premium compression, fees or USDG depeg. Emissions increase supply and may dilute NAV; they can be zero, reserve-constrained or oracle-skipped. APR/APY assumes future conditions, not earned cash yield, while leverage adds interest and liquidation risk. See [Staking and emissions](protocol.md#staking-emissions-and-the-oracle) and [Loopback](products.md#loopback-isolated-wsnetusdg-credit).

### wsNET balance stayed constant. Did I miss the rebase?

Not necessarily. wsNET is non-rebasing: its underlying claim per unit follows the index. Compare balance and index at a common observation; index growth alone proves neither dollar profit nor that the wallet held throughout. See [Token forms](protocol.md#purpose-chain-and-token-forms) and [Loopback](https://docs.netnet.capital/lending).

### Can Treasury RFV rise while NAV falls? Can NAV rise while my USD balance falls?

Yes. **NAV = RFV / total NET supply**: faster supply growth lowers NAV despite rising reserves; a below-NAV burn can raise NAV while reducing RFV. Exit value also depends on holdings, market price, fees, slippage and USDG/USD—not NAV alone. See [denominators](protocol.md#supply-premium-and-return-are-different-denominators) and [buyback limits](protocol.md#issuance-bonds-and-support-around-nav).

### Are all NET amounts the same raw units?

No. Token base units, rebasing fragments, internal gons, wrapper units, reserve-valuation units and oracle scales are separate dimensions. The docs explicitly describe NET as having 9 decimals via the tNET comparison and wsNET as 18 decimals; the exact sNET/USDG metadata and accounting scales should be taken from the matched identity/source records rather than guessed from a displayed symbol. RFV is a normalized reserve value, not automatically an ERC-20 `balanceOf` amount. [Futures §1](https://docs.netnet.capital/futures), [Loopback terms](https://docs.netnet.capital/lending), [mechanism §6](https://docs.netnet.capital/mechanism), [Treasury §3](https://docs.netnet.capital/treasury), [packaged identities](../assets/address-index.json).

Keep **asset identity + amountRaw + decimals + unit basis + observation anchor** together. `1,000,000,000` raw units at 9 decimals is 1 token; the same integer at 18 decimals is one-billionth of a token. Apply the contract's integer rounding and avoid binary floating-point arithmetic for raw amounts. A generic 18-decimal “wad” normalization does not imply the underlying token has 18 native decimals. These are arithmetic/unit-handling rules, not a new protocol parameter.

### Is the 5% fee on every transfer, and does it disappear after day 30?

No. The **5% token tax** applies to mapped AMM-pair transfers, with wallet transfers and whitelisted paths exempt. Day **30** ends management's share, **not the tax**; Treasury receives the 5%. AMM fees/slippage are additional, and v4/UniswapX coverage is disputed. See [Fees](protocol.md#trading-fees-and-management-compensation) and [the coverage conflict](protocol.md#authority-risks-and-documentary-cautions).

Also avoid copying the risk page's “−10% round trip” as exact compounded arithmetic. Two independent 5% proportional deductions leave `0.95² = 0.9025`, a 9.75% reduction before price changes, AMM fees and slippage, if applied to sequential token amounts on that simplified basis. Actual trade costs require the route's fee basis; neither shorthand is an executable quote.

### Does “no governance” mean the Manager cannot change anything anywhere?

No. Core policy lacks in-place parameter controls, but fee-map/exemption additions, Desk menus/discounts and custody, and Credit owner/curator/allocator/sentinel roles remain. The team Safe is **1-of-1**. Core immutability also prevents simply pausing or repairing a defect in place. See [authority boundaries](protocol.md#authority-risks-and-documentary-cautions) and [Credit roles](products.md#claims-roles-and-conflicts-of-interest).

### Is management capped at a fixed founding allocation, or paid only when NET is above NAV?

No. Perpetual pTEAM exercise headroom depends on eligible circulating supply, not a fixed genesis allocation; the **1 USDG strike** can dilute NAV. A price above strike can still be below NAV, contrary to the source's stronger profitability claim, and its worked incremental amounts are inconsistent. Cumulative exercise does not prove current holdings. The older “complete list” also omits newer product flows such as Credit's Sleeve interest fee. See [compensation](protocol.md#trading-fees-and-management-compensation) and [documentary cautions](protocol.md#authority-risks-and-documentary-cautions).

### Is the founding subscription still open? Does a share certificate guarantee future rewards?

The read offering and guide say **closed**, finalized on **2026-07-16**, with the five-day vest complete. The certificate is a nontransferable cohort record with no promised launch perk. Old approval/subscription/checklist text is historical, not evidence of a reopened sale; unclaimed vested NET is separately described as not expiring. Consult the offering page for binding historical terms, including the difference between idealized launch NAV and the haircut-adjusted figure. None is today's NAV. [Offering](https://docs.netnet.capital/OFFERING.HTM), [founding guide](https://docs.netnet.capital/founding-shareholder-guide).

### Are Loopback deposits and nnUSDG backed by the Treasury?

No. Loopback lenders hold isolated wsNET/USDG loan exposure; nnUSDG holds a curated portfolio of that market plus **six stock markets**. Neither is NET backing or a Treasury liability; collateral losses and withdrawal constraints remain. Core's Morpho placement is separate. Credit's principal stock borrower is its curator's own Sleeve—a concentration/conflict, not Treasury support. See [Loopback](products.md#loopback-isolated-wsnetusdg-credit) and [Credit claims and roles](products.md#claims-roles-and-conflicts-of-interest).

### How can Credit be live while its router is pending activation?

Vault operation, direct Morpho borrowing and router-assisted borrowing are different surfaces. The docs report a vault and first Sleeve loan while **CreditRouter awaits an allocator grant and app stock-borrow buttons are disabled**; wsNET uses Morpho directly. A published address does not prove activation or that the first loan used the router. See [Credit activation](products.md#documented-market-operation-versus-interface-activation).

September 10's **over-100% APR**, **$800,000 deposited** and **over-$1.1-million collateral** promotions do not establish a change to the **20% deployment-time depositor accrual ceiling**, lending caps, actual returns or router permissions. Deposits and collateral are not one reconciled asset series. [Credit](products.md#netnet-credit-a-curated-lender-not-a-replacement-loopback) retains the sources and rate/size distinctions.

### Are the House Vault, NET/USDG LP and staking interchangeable yield products?

No. The **House Vault** underwrites prediction outcomes and can lose capital; queued deposits and withdrawal notices expose participants to weekly results. **NET/USDG v2 LP** owns a changing mix of the two pool assets and earns swap fees, with divergence and NET-levy costs. **sNET/wsNET** represent staking exposure, not either of those claims. USDG-equivalent interface values are not guaranteed USD redemption values. See [Products](products.md) and [Integrations](integrations.md).

### Is Predict the earlier NAV Pool proposal, and do its fees burn NET?

The launched Predict market is not established as the implementation of the historical backing-per-NET, no-house-side NAV Pool proposal. Its observed display combines Treasury and Sleeve; it has a depositor-backed house. The announcement splits fees between NET purchases and the House Vault. An indexed trade supports a NET purchase routed to the Sleeve, **not a burn** or proof that all fees accrue to Core. See [Products](products.md) and [Builders](builders.md).

### Does an LP Zap deployment mean I can use a tax-free one-click deposit?

No. On September 18 the public app's Add liquidity panel still gated the single-transaction desk pending exemption and offered direct two-token Uniswap provision instead, with a levy on the NET leg. Registry promotion, current exemption and user-interface availability are separate observations. Explain the [published design and current limitation](products.md), not executable steps, approvals or transactions.

### Does “fail closed” stop losses or just operations?

It stops each guard's specified operations, not economic risk. Invalid Core TWAP blocks dependent issuance/settlement; Loopback/Credit pricing refusal can block liquidation as well as borrowing while debt, stale health and reopening gaps persist. Credit tolerances are not universal freshness rules. See [consumer-specific guards](addresses-and-roles.md#consumers-and-freshness-are-separate-from-feed-metadata) and [Credit liquidation risks](products.md#oracle-and-liquidation-risks); “safe because paused” is unjustified.

### Do futures profits or underwriting balances contribute to Core earnings?

No. The documented mainnet test uses **valueless tNET**, a holding sink for fees and a loss waterfall that never reaches Treasury. Real wsNET margin and Treasury fees are a **future production path**, not live economics; a real transaction alone does not establish monetary value. See [Managed Futures](products.md#managed-futures-real-transactions-test-economics).

### Which “Turbo” is meant?

Loopback's TurboRouter is leveraged NET accumulation through borrowing, buying, staking and wrapping. The **Long-Dated TURBO Desk** is a separately named product; **TURBO BLACKJACK** is another distinct desk using TURBO cards. Do not join their positions, fees or deployment identities merely because the labels overlap. [Loopback](https://docs.netnet.capital/lending), [official registry](https://docs.netnet.capital/official-channels), [games.md](games.md).

### Is a launchpad still planned, and is the builder SDK publicly available?

The **August 7 launchpad proposal was rejected August 18**; it is historical, not a product promise. Developer Portal onboarding and later Cabinet Kit disclosures do not establish a generally available SDK or deployed roadmap concepts. See [Builders: availability](builders.md#where-is-cabinet-kit) and [concepts and launchpad sources](builders.md#keep-the-announced-concepts-separate).

### What should an answer say when today's state is missing or sources disagree?

Use a scoped statement, not a fabricated number: **“The documentation read on 2026-09-10 says X; the current permission/oracle/inventory state was not observed.”** Missing data is not zero, a failed dashboard read is not proof of no holdings, and deployment is not activation. Historical terms remain historical even when still visible in an app.

Concrete conflicts to retain: official channels lists the original RWA Desk while the official application's registry publishes a V2 successor; the fee schedule and risk page disagree on v4/UniswapX taxability; the RWA page alternates buyer-choice and most-underweight menu descriptions and halt/floor wording; Core documentation does not settle cap-clamp versus revert. Preserve each claim's source and date, keep unaffected explanatory knowledge usable, and do not invent a single verified runtime truth. Details: [products.md](products.md), [protocol.md](protocol.md), [addresses-and-roles.md](addresses-and-roles.md).

The [dashboard directory](docs-and-sources.md) uses display order only, never retrieval order, evidence ranking or a fallback sequence. Use relevant primary on-chain state/events for contract-derived metrics and official sources for protocol claims. Dashboards are optional evidence where appropriate or when explicitly requested, not default authorities or required dependencies. Compare observations by relevance, definitions, provenance, block/time, scope and completeness. No transaction, wallet, signature or execution instruction is needed to explain these distinctions.

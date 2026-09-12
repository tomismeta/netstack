# Products, claims and accounting boundaries

**Evidence scope:** official documentation was read on **2026-09-10**, with Credit re-read and selected original announcements through **2026-09-12** incorporated in this unpublished working update. “Documented live,” “deployed,” and “pending activation” report publisher statements, **not independent live deployment or availability verification**. No current inventory, balances, interest rate, borrow health, market cap or permission was queried. Product names and historical opening dates do not prove today's interface can accept an order. Addresses and generation provenance belong in [addresses.json](../assets/addresses.json); [Official Channels](https://docs.netnet.capital/official-channels) is the direct official registry.

**Questions answered:** What does a bond subscriber receive? Who owns the equities? Does the Treasury lend to Loopback or underwrite futures? Is nnUSDG cash? Why can an operating lending desk still have disabled borrowing controls? How are the two RWA Desk generations kept separate?

## The map: purchaser, claim and reserve boundary

| Product | Consideration / position | What the participant holds | Relationship to Core |
|---|---|---|---|
| Standard bonds | USDG or canonical NET/USDG v2 LP | Vesting NET claim | New NET issuance against reserve consideration, priced no lower than NAV. |
| Staking / wrapper | NET → sNET; wrapped exposure in wsNET | Rebasing staked claim, or a fixed-unit wrapper of that claim | No new independent reserve pool; emissions enlarge staked NET claims subject to Core policy. |
| Real World Bonds | USDG subscription | Vesting NET from Desk inventory, **not the purchased equity**; older docs use pre-exercised NET, September 12 announces bought NET | Documented reserve remittance and outside-Core equity purchase are separate; the new inventory path's remittance formula is unestablished. |
| RWA Sleeve | Manager-custodied stocks and program receipts | Assets held by the Manager for stated protocol benefit | Not RFV, not NAV, and no automatic NET-holder redemption claim. |
| Managed Futures test | tNET margin / tNET underwriting | Test trader balance or floating underwriting shares | No monetary value and no Core loss backstop. |
| Loopback | wsNET collateral / USDG loans | Borrower debt and collateral; direct lenders' loan claims | Isolated Morpho credit, not Treasury-backed deposits. Taxed pool trades can separately generate Core fee flows. |
| NetNet Credit | USDG vault deposit / nnUSDG shares | Proportionate exposure to a curated portfolio of loans | Outside Core; no claim on Treasury assets and no inclusion in NET NAV. |

Sources: [mechanism](https://docs.netnet.capital/mechanism), [RWA Desk](https://docs.netnet.capital/rwa-desk), [Treasury](https://docs.netnet.capital/treasury), [futures](https://docs.netnet.capital/futures), [Loopback](https://docs.netnet.capital/lending), [Credit](https://docs.netnet.capital/credit). See [protocol.md](protocol.md) for RFV, supply, emissions and fee equations; [games.md](games.md) covers the game/long-dated desks.

## Standard bonds, staking and the concluded founding offering

Standard Primary Offerings accept USDG or canonical v2 LP and price NET at `max(discounted TWAP, NAV)`. Capacity limits apply. LP consideration uses the Treasury's floor-valued geometric-mean convention, not a spot-marked NET leg. The bond claim and the later staking claim are distinct: buying a vesting NET claim is not itself a promise of staking distributions during the vest. The RWA page describes the standard and RWA bond vest as two-day linear delivery. [Mechanism §5](https://docs.netnet.capital/mechanism), [RWA Desk](https://docs.netnet.capital/rwa-desk).

Staking converts NET into sNET; its balance grows with successful rebases. wsNET is a non-rebasing wrapper whose underlying claim changes with the index and can be posted as Loopback collateral. Do not add the wrapper and its backing as independent holdings, or assume a growing index guarantees a profitable dollar exit. The founding guide describes a zero-epoch warmup as a default and tells readers to consult the deployed value; it does not establish a timeless warmup for every deployment. [Mechanism §§1,6](https://docs.netnet.capital/mechanism), [founding guide](https://docs.netnet.capital/founding-shareholder-guide).

**GenesisBond is a separate, concluded product.** The offering and guide report finalization on **2026-07-16**, full subscription and completion of the five-day founding vest. Finalization atomically formed the Treasury/canonical POL, enabled Core programs and started the fee/pTEAM clocks. A founder's nontransferable certificate records cohort membership; no launch perk is promised in code. Unclaimed vested founding NET is documented not to expire, but this is not a reopened offering. Old funding/subscription steps remain as history, not current availability instructions. All binding historical prices, limits, ratios and vesting terms are on the [Founding Offering](https://docs.netnet.capital/OFFERING.HTM); the [guide](https://docs.netnet.capital/founding-shareholder-guide) is subordinate explanatory history.

## Real World Bonds and the RWA Sleeve

### Historical documented economic flow

The older published Desk design distributes NET that the Manager has already acquired through pTEAM exercise and deposited as Desk inventory. This is a **generation-scoped description**, not proof of the September 12 bought-NET path's mechanics. A subscription does **not itself create fresh NET supply** merely because it creates a vesting note. The earlier exercise and later distribution are separate accounting events. In that documented design, subscriber USDG splits between:

1. **Reserve remittance to Treasury**, described per NET as high-water backing minus the 1 USDG strike already contributed at exercise.
2. **Rialto equity acquisition**, with the stock held in the team-custodied RWA Sleeve.
3. **Subscriber NET claim**, delivered from Desk inventory over the published two-day linear vest.

The subscriber does not receive the purchased equity and has no documented proportional Sleeve redemption right. Do not book the whole USDG subscription as Core revenue, count an inventory transfer as a new mint, or count the earlier pTEAM strike twice. [RWA Desk](https://docs.netnet.capital/rwa-desk), [team](https://docs.netnet.capital/team), [Treasury §5](https://docs.netnet.capital/treasury).

### Prices, controls and inventory

The following pricing, remittance and inventory controls describe the older published Desk design. Match them to a generation before treating them as present terms; the September 12 announcement does not restate or certify them for bought inventory.

The documented Desk price is discounted TWAP. The launch discount is an historical configurable parameter; the published immutable upper bound is **7.5%**. A high-water-backing premium guard is documented at **1.20×**. The page alternates between saying subscriptions halt below the guard and saying the higher of price/floor binds; do not infer which deployed quoting/revert behavior resolves that wording without generation-specific evidence. A displayed launch “all-in advantage” is not a timeless return: vesting exposure, current discount, oracle state, inventory and the actual alternative trade's fee/slippage matter. [RWA Desk price and risk sections](https://docs.netnet.capital/rwa-desk).

The reserve remittance follows a monotone high-water backing mark. The page's precise claim is that **a fully sold inventory clip restores backing to its pre-Desk high-water mark**. Do not reinterpret this as proving that pre-exercise NAV cannot temporarily fall: pTEAM exercise is itself a documented NAV-diluting exception, and inventory may remain unsold. Report exercise, remittance, remaining inventory and the relevant high-water mark separately. The published inventory design has no Manager withdrawal path: its exit is a filled vesting claim. This is an inventory-custody statement, **not proof that recipients can never subsequently sell NET** or that there is no economic sell pressure. [RWA Desk reserve remittance and inventory](https://docs.netnet.capital/rwa-desk), [mechanism §4](https://docs.netnet.capital/mechanism).

The menu consists of token/feed/target-weight entries. The documentation names NVDA, SPCX and AAPL as launch names and says the Manager can change names and weights; removal stops future purchases, not sale of existing holdings. It also says both that subscribers choose an equity and that each fill buys the most-underweight name. Treat the exact selection algorithm as unresolved in this summary, rather than pretending the two statements prove buyer discretion. Price/feed liveness, Rialto execution and the backing guard can halt new subscriptions without cancelling already-issued vesting notes. [RWA Desk menu and risks](https://docs.netnet.capital/rwa-desk).

### Generations and status conflict

The docs report the original Desk live since **2026-07-24**. The [official registry](https://docs.netnet.capital/official-channels) still lists that original RwaDesk. The publisher's [Shareholder Services application](https://app.netnet.capital/) instead labels Desk V1 superseded on **2026-08-27** and publishes Desk V2 as its successor. The static registry observed in the [application asset](https://app.netnet.capital/assets/index-Bw6sa19a.js) identifies V2 deployment block **47,600,318**; this is a published registry assertion, not a receipt or runtime verified by this reference. Hashed frontend assets can rotate. Exact identities and deployment provenance are retained in [addresses.json](../assets/addresses.json), not duplicated here.

Consequently, keep inventory, menu, discounts, vesting-note IDs, purchase history, refill limits and high-water marks **generation-scoped**. The old Desk's state must not be substituted for the successor's state. V2's appearance in an application registry does not automatically establish that every older prose parameter is unchanged, nor does the official table's omission establish that V2 is nonexistent. Identify the conflict, retain historical V1 information and require matching generation evidence for a claim about present mechanics or availability.

### September 12: Manager-funded bid and bought-NET inventory

The [September 12 announcement](https://x.com/NetNetCap/status/2098803824282771690) says the **Manager's own balance sheet** will fund a standing NET bid at **2× NAV**, with purchased NET replacing newly minted Real World Bonds inventory. The publisher says later fills will fund Treasury and equity purchases without new supply, increasing backing per token. This is an **announcement**, not verified bid placement, purchases, Desk refills or NAV accretion.

Buying and redistributing existing NET is neither a mint nor a burn. Funding capacity, venue, NAV definition/observation method, implementation and bought-inventory remittance formula remain unspecified. Do **not** carry forward `high-water backing − 1 USDG`: bought NET has no established pTEAM strike contribution. Preserve generation-scoped exercise, remittance and inventory records; require matched evidence for each new flow before calculating Core backing effects.

The Manager bid is **not** the Core Treasury inverse bond (`0.985× NAV`, capacity-limited purchase and burn), PremiumSeller (bounded issuance/sale **above** a 2× NAV TWAP threshold), or Loopback's collateral mark. It establishes no unlimited floor, automatic redemption right or claim on Core funds: bought NET is announced as reusable inventory, not burned supply. See [Core mechanisms](protocol.md).

### Sleeve ownership, claims and risks

The Sleeve is a dedicated, team-custodied Safe holding equities for the Manager's stated protocol-benefit mandate. Other programs can forward stocks not present on the Desk's purchase menu. No Sleeve asset counts in RFV or NAV; no Treasury reserve path is described as funding those equity purchases. Possible use to support backing or inverse bonds is **discretionary and social**, not automatic collateral or an enforceable cash redemption facility. [RWA Desk Sleeve](https://docs.netnet.capital/rwa-desk), [Treasury §§5–6](https://docs.netnet.capital/treasury).

The Sleeve is also Credit's documented principal Stock Token borrower: gross marked equity is not necessarily unencumbered net value. Distinguish custody, collateral, USDG debt, interest and withdrawability; a stock gain affects Core NAV only through a separately evidenced Core transfer. Equity/issuer/redemption, feed, market-hours and team-custody risks remain. [Credit](https://docs.netnet.capital/credit), [risks §12](https://docs.netnet.capital/risks). See Strategy for [full Sleeve/social-support accounting](rwa-strategy.md#the-non-negotiable-accounting-boundary) and the [combined-assets forecast](rwa-strategy.md#september-11-forecast-treasury-plus-manager-sleeve-not-core-rfv).

## Managed Futures: real transactions, test economics

The documented mainnet test venue has SPCX and CASHCAT markets. Its margin currency **tNET is a freely mintable, valueless faucet token**, not NET, wsNET, a Treasury claim or a production stablecoin. SPCX uses an equity feed; CASHCAT uses a v3 TWAP combined with ETH/USD. Mainnet deployment and real gas expenditure do not make test PnL monetary revenue. The stated production path—real wsNET margin, a strategic underwriting raise and fees routed to Treasury—is expressly **not live** in the read documentation. [Futures §§1–2,9](https://docs.netnet.capital/futures), [official registry](https://docs.netnet.capital/official-channels).

For test risk calculations, tNET is marked as if it were wsNET using the Core TWAP and staking index. The documented usable-margin rule clamps a haircut price between an indexed NAV floor and twice that floor; actual PnL settlement uses the contemporaneous modeled spot conversion. This is a simulated valuation convention, not an actual floor redemption promise for tNET. The venue documents leverage, maintenance margin, per-notional open/close fees and skew-driven eight-hour carry; carry flows from the crowded to the less-crowded side, with a fee-route skim. These parameters describe test mechanics, not investable yield. [Futures §§1,3](https://docs.netnet.capital/futures).

Underwriters deposit tNET and hold vault shares whose value varies with the vault's counterparty equity. The documented loss waterfall is trader margin → underwriting vault → clearing reserve → auto-deleveraging profitable opposing positions. Underwriting redemptions can be gated while the book needs capital, and a drawdown breaker can halt new positions. **Treasury is not a loss layer**: the test desk's Core connections are read-only, and its fees terminate in a test-token sink rather than Core. [Futures §§4–6](https://docs.netnet.capital/futures).

Out-of-session or between-print equity indices can stay unchanged while economic exposure accumulates; a reopening gap can trigger margin calls at once. Staleness halts new risk according to the published guard, not all possible loss. Test traders can be liquidated and underwriters can lose their test balance; the risk lesson carries over even though tNET has no monetary value. [Futures §§2,8 and risk disclosures](https://docs.netnet.capital/futures).

## Loopback: isolated wsNET/USDG credit

Direct public entry: [Loopback application](https://app.netnet.capital/#/loopback). This is a research link, not an instruction to borrow or run its looping router.

Loopback is documented as operating since **2026-07-22** on an immutable Morpho market. Borrowers post wsNET, retain its index-linked staking exposure and incur floating USDG debt. Direct USDG lenders fund the loans; Morpho collateral is described as not re-lent. **Core Treasury is not a credit participant or loan guarantor.** This separation concerns Loopback participant loans, not the Treasury's independently described Morpho reserve deployment. [Loopback](https://docs.netnet.capital/lending), [Treasury §2](https://docs.netnet.capital/treasury).

The published oracle credits collateral at:

```text
credited USDG value per wsNET = clamp(TWAP × 0.90, NAV, 5 × NAV) × index
liquidation LLTV = 62.5% of credited collateral value
Loopback Turbo router target = 53.125%
```

The optional leveraged accumulation flow uses borrowed USDG to buy NET, stake and wrap it, and return wsNET as collateral. It pays the normal mapped-pool trading tax and slippage; leveraged dividend exposure is not free leverage or guaranteed carry profit. This **Loopback TurboRouter is not the Long-Dated TURBO desk or TURBO BLACKJACK**. [Loopback terms and fee alignment](https://docs.netnet.capital/lending), [official registry](https://docs.netnet.capital/official-channels).

The five-times-NAV cap restrains credit against large speculative premiums. While the cap binds, some price declines do not change credited value; this does **not** mean market-price crashes cannot ever cause liquidation. A sufficient fall leaves the capped region, while debt interest, NAV dilution and the staking index also change health. The lower NAV clamp can value collateral above executable market price when NET trades below NAV, despite the page's “at or below market” prose. Liquidation recovery depends on actual buyers and capacity, not merely the credited mark. [Loopback advance rate and margin calls](https://docs.netnet.capital/lending), [risks §§1,4,14](https://docs.netnet.capital/risks).

A stale TWAP or instantaneous pool price more than 15% below TWAP is documented to pause new borrowing **and liquidations**. A frozen oracle is not a loss guarantee: gaps and illiquidity can worsen while liquidators cannot act. Debt above the permitted credited-value threshold is subject to permissionless liquidation with Morpho's incentive; rates float with utilization. The page's facility-size guidance relative to pool depth is explicitly **not an enforced cap**. USDG lenders can lose principal; rate-limited inverse bonds are not an instant liquidation backstop. [Loopback stale guard, margin calls and lender risks](https://docs.netnet.capital/lending).

The page claims “exactly three contracts” while naming an oracle and router “and nothing else”; do not fabricate a third identity. The official registry lists the oracle and TurboRouter. Parameters are documented immutable for that market, unlike the curator controls of NetNet Credit. [Loopback](https://docs.netnet.capital/lending), [official registry](https://docs.netnet.capital/official-channels).

## NetNet Credit: a curated lender, not a replacement Loopback

Direct public entry: [NetNet Credit application](https://app.netnet.capital/#/credit). Supply/Borrow tabs can be read without connecting an account; the agent must not use the wallet controls.

The read page reports a Morpho Vault V2 opening on **2026-09-09**, with its first loan on **2026-09-10**. Depositors supply USDG and receive **nnUSDG vault shares**. The vault lends into seven isolated Morpho Blue markets: existing wsNET/USDG Loopback plus NVDA, SPCX, AAPL, GOOGL, MSFT and COIN collateral markets. It is a new lender in the existing Loopback market, not a second version of that borrower's position. Each collateral market has independent debt and health. [Credit introduction and markets](https://docs.netnet.capital/credit).

nnUSDG tracks the loan portfolio's assets: interest can increase its share value; uncovered loan losses can decrease it. A depositor owns shares, not an immediately redeemable unit of USDG or a claim on Core Treasury. Deposits are initially allocated to the Loopback liquidity adapter, and allocations can move to stock markets within caps. Withdrawal requests depend on available liquidity and repayments/reallocation; “withdraw at any time” does not mean instantly withdraw any amount. Zero utilization or an accrual ceiling can also make deposit returns differ from headline borrower rates. [Credit supply and risk sections](https://docs.netnet.capital/credit).

**Promotional rates do not amend vault terms.** The [September 10 launch post](https://x.com/NetNetCap/status/2098062869686563068) advertises over 100% APR; the [Credit page](https://docs.netnet.capital/credit) specifies a **20%-per-year depositor accrual ceiling at deployment**, changeable by the allocator. No increase is established, and borrower rates differ from depositor accrual. Later posts claim [$800,000 deposited in under an hour](https://x.com/NetNetCap/status/2098076612864671941) and [over $1.1 million deposited “as collateral” in three hours](https://x.com/NetNetCap/status/2098122637511950522). Those differently labelled, timed claims prove neither current USDG supply/net assets nor earned income, cap changes or router activation.

Published **USDG lending exposure caps**, not gross-collateral caps: wsNET $1 million; NVDA/SPCX $800,000 each; AAPL $600,000; GOOGL $400,000; MSFT/COIN $200,000 each. These dated parameters were not queried on chain or overridden by the deposit announcements.

### Claims, roles and conflicts of interest

- The **team Safe** is owner and curator, with powers over roles, adapters, caps, fees and timelocks under the documented safeguards.
- The **allocator** moves liquidity within permitted destinations/caps and sets the depositor rate ceiling. The **sentinel** can cancel pending changes, reduce exposure or lower caps immediately.
- Exposure-increasing changes are described as subject to a **three-day timelock**; allocator grants/revocations can occur immediately. This is a privileged managed product, not covered by Core's blanket “no operators” language.
- The **Manager's RWA Sleeve is the principal Stock Token borrower** and the recipient of the documented **10% fee on interest earned**. The page says no management, deposit or withdrawal fee, and no additional fund-specific liquidation penalty. It describes a 40% LTV limit for the Sleeve's own borrowing; do not misstate this as every market's liquidation threshold or all users' enforced limit.

Sources: [Credit roles, fees and risks](https://docs.netnet.capital/credit). Caps, fees, role holders and rate ceilings can change; these are published terms at the read snapshot, not certified current state. A timelock provides notice, not guaranteed exit liquidity throughout the notice period. Do not turn gross loans, deposited principal or a growing stock mark into fee revenue.

### Documented market operation versus interface activation

The [Credit page](https://docs.netnet.capital/credit) says the **CreditRouter is deployed but awaiting the Safe's allocator grant**, with Stock Token borrow buttons disabled until activation; wsNET borrows directly on Morpho. Operating lending and a reported first Sleeve loan therefore do not establish retail-router activation, while disabled app controls do not establish that stock borrowing is unavailable by every route. The first loan's use of the pending router is not established. [Official registry](https://docs.netnet.capital/official-channels).

The router is described as holding no independent funds or position, posting borrower collateral and moving vault liquidity from Loopback to a listed stock market within fixed bounds. An address and this design do not establish permission; current availability needs evidence of allocator grants, liquidity, caps and oracle state.

### Oracle and liquidation risks

StockMorphoOracle combines the equity feed, USDG/USD feed and token corporate-action multiplier. The documented refusal conditions are equity-feed age above **97 hours**, USDG-feed age above **25 hours**, issuer pause, or multiplier outside **0.8–1.2**. These are Credit-specific guards, **not universal mark-freshness policies for all NetNet products**. When pricing fails, new borrowing and unsafe collateral withdrawals are blocked and liquidation cannot proceed; repayment and adding collateral remain available. [Credit oracles](https://docs.netnet.capital/credit).

**Direct feed mark is not Credit collateral price.** Chainlink describes its Robinhood tokenized-equity proxies as already incorporating the corporate-action multiplier, while Credit says its oracle adjusts by it. Scoped explorer inspection matched all six oracle creation-bytecode tails to the catalogued token/feed pairs, but those oracles are source-unverified in the inspected explorer and their exact arithmetic was not certified. Raw token balances and multiplier-adjusted display balances are distinct, so multiplication alone does not prove a deployed error. Read the exact product oracle's own output with its established scale and unit basis rather than reconstructing it as a second multiplication of a direct feed mark. If that evidence is unavailable, do not report a reconstructed Credit price. See [feed and raw/display unit guidance](addresses-and-roles.md#price-feeds-and-token-relationships).

The published liquidation thresholds are 62.5% for wsNET and five stock markets, with COIN at 38.5%; liquidators receive collateral under Morpho's incentive. No feed prints over an equity-market closure can leave displayed health stationary, with risk crystallizing on the reopening print. Losses depend on issuer behavior, oracle correctness, feed gaps, liquidation depth and rates—not just nominal overcollateralization. Market caps limit the vault's exposure, not stock-price loss. [Credit markets and risks](https://docs.netnet.capital/credit).

**Status discipline:** when fresh evidence is missing, say “documented operating; current availability unverified,” “router documented pending activation,” or “oracle/capacity state unavailable.” Never replace these with zero balances, zero yield, permanent closure or an assumed working transaction route.

# Integrations and read-only data access

Baseline documentation/data reviewed September 10, 2026; targeted September 18 integrations and September 25 reserve/Sleeve, Predict and Book evidence update the named topics, not every dependency. These are knowledge and public-RPC routes, not installed connectors. The [safety policy](safety.md) governs access.

## Capabilities, not subscription labels

| Question | Minimum useful access | Limits to disclose |
|---|---|---|
| Explain mechanics or a historical source | Packaged references | No claim of live data |
| Verify current documentation, dashboard, collection data, price or announcement | Host-authorized reader/browser/API tool, including approved non-wallet authentication where needed | Publication/retrieval date, edits, inaccessible media, confidentiality and untrusted text |
| Current block, bytecode, balances, bounded contract reads | Suitable RPC access through a host-authorized research tool | Rate limits, confirmation level, matching block/chain |
| Larger log searches or sustained indexing | Provider with adequate log coverage and throughput | Log-range/result caps, pruning, cost and completeness |
| Historical contract state at a specific old block | Endpoint retaining the required historical state | Archive availability, method support and chain/block coverage |
| Discover labeled addresses or verified source | Block explorer/official address registry | A label is not proof of identity; source verification is not an audit |

A paid endpoint does not automatically retain historical state, and a free plan is not necessarily incapable of it. Historical logs and historical `eth_call` state are different capabilities. Establish the required block/range and methods before selecting a provider. Deliberate archive retrieval, interface recovery or a scoped backfill is allowed under existing host permissions and approved costs; never silently activate paid access, bypass denials or make unbounded/retrying requests.

Use ordinary host-authorized research under [Safety](safety.md#everyday-public-research) and the [governing guardrail](guardrail.md); no custom broker or per-public-destination setup is required. Public unauthenticated access is a starting point, not a global limit: approved non-wallet authentication and explicitly authorized local research resources are allowed with confidentiality and SSRF protections. Explain concrete user-operated actions, including betting, without operating wallets. Agent-authored code, ordinary research delegation, new sources/interfaces, models, forecasts and accrual calculations are permitted with provenance and explicit observed/derived/modeled distinctions. Established read-only quotes and isolated non-broadcasting simulations may be used without real-wallet credentials, signing, live-chain/node mutation or submission.

## Live analytics execution limits

For supported **RFV/Sleeve, NET/USDG v2, Predict and House scopes**, prefer the optional reviewed [runner](../scripts/analytics.py) under normal host permission. It uses **Python 3.10+, Linux/macOS, standard library only**, a fixed public Robinhood RPC origin and packaged canonical routes/ABIs. No custom endpoint, credentials, wallet or arbitrary-RPC mode. Knowledge-only use needs no Python.

These commands define helper coverage, **not research permission**. RFV's non-core scopes include a Book house-pot/state snapshot, but there is **no `book` activity command**; use [Book's snapshot-first workflow](games.md#book-snapshot-first) and [interface](../assets/analytics/book-interface.json) for wagers/history/settlement. Deeper research may choose a finite scope within actual host deadlines, quotas and approved costs. Do not execute untrusted sources or bypass denials.

### Invocation and deadline

Use `python3 -I -B scripts/analytics.py lp --since-days 7 --deadline 120 --json` from the installed package directory; substitute `predict` or `house` and omit the LP-only `--since-days`. For another working directory use the installed script's exact path. Agent-authored research code and host-approved tooling are allowed for other scopes and capability gaps. Do not generate replacement scripts, probe modules or try inline-code/redirect variants **to evade a denied invocation**; host approval governs code execution and installation.

For one Predict series' state, timestamps and roles, use `python3 -I -B scripts/analytics.py predict --series 2 --deadline 120 --json` (replace `2` with the requested ID). This is a pinned snapshot, not a trading-history, House-ownership or live-quote workflow. Omit `--series` only when the broader Predict activity collection is wanted.

For website concepts, use:

```sh
python3 -I -B scripts/analytics.py rfv --scope core --deadline 120 --json
python3 -I -B scripts/analytics.py rfv --scope reports --deadline 600 --json
python3 -I -B scripts/analytics.py rfv --scope net-assets --deadline 600 --json
```

`core` is the default: Treasury RFV/component reconciliation and total-supply NAV. `reports` adds the separately labelled Sleeve memo/“True RFV” composition. `net-assets` exposes supported adjustments and missing liabilities/fees/ownership evidence, not guaranteed complete net equity. **Website numbers are never inputs**: all quantities and valuation getters come from the same pinned RPC block; website labels/code only establish discovery and methodology. [Scope definitions](rwa-strategy.md#four-values-four-questions) distinguish these from Predict's settlement print. A missing component leaves a partial ledger or unavailable aggregate, never a website fallback or zero.

The 600-second examples are for a deliberately broader collection when the host allowance permits; shorten them for a quick pass. A plain-language RFV breakdown defaults to broad asset/obligation research, not the CLI's narrow Core scope. One non-core run emits Core and both broader ledgers; do not repeat all three commands to answer the same question.

- Default **quick-pass** whole-answer allowance is **180 seconds**, including loading, approvals, retrieval and writing the answer, with **45 seconds reserved for reporting**. Remaining quick-pass retrieval time is `max(0, min(180 - elapsed, host_remaining) - 45)`; omit the host term only when unknown. Deeper requested research may use a different explicit finite allowance; it never extends a host deadline or silently resets an exhausted pass.
- The collector defaults to **120 seconds**, enforced across its own network/retry/computation work. Pass a smaller `--deadline` when the remaining retrieval allowance requires it; start no collector when there is insufficient time to return evidence. Leave a small margin between its internal stop and the host tool timeout, both within the remaining retrieval allowance. Host approval waits and model output happen outside the collector: its timer cannot enforce their deadlines.
- `--block` accepts an explicit block number or `latest-2` (default). The same B governs every dependent getter, including all House account reads. Two-block lag is not a finality guarantee. `--output PATH` optionally preserves a compact checkpoint **outside the installed package**; it is research evidence, not a reusable current-holder list or authority to modify the package. Do not send private paths or checkpoint contents to an RPC endpoint.
- Within the **bundled collector**, each attempt is bounded by the remaining budget and at most **15 seconds total wall time**; socket read timeout alone does not stop trickle responses. **RFV has 750 RPC members; LP/Predict/House retain 250**, including batches and retries. LP has at most **50,000 log rows**, Predict/House **10,000**. Batches have at most **20 members**, matched by response ID, not position. Preserve successful members; retry transient failures at most once and use at most **10 recovery attempts** overall, including splits/fallback. These helper caps are not global research limits. Never bypass denials; malformed ABI or pruned state needs diagnosed interface/archive recovery, not blind retries.
- Preserve the required snapshot before history and checkpoints between completed chunks. Scan evidence needed by the selected question. On deadline, interruption, access failure or exhausted pass resources, return verified observations and exact missing ranges/IDs. Do not reset that pass's timer, mix newer values into B, silently substitute a shorter interval or launch an unrequested background backfill. A deliberate deeper investigation or recovery under an explicit host-authorized scope is distinct from hiding a failed pass.
- If the runner cannot be invoked, report the missing capability/permission. Independently authorized research can still support the question, but do not replace a denied runner with generated code as a bypass. For a quick pass, bound other reads to the remaining allowance and default to at most **30 seconds per tool call**, reserving time to return evidence; deeper research uses its explicit host-authorized limits. The package cannot cancel a host approval suspension; record it as a host stall rather than a completed analytical run.

### Interpreting results and completeness

The JSON separates pinned snapshot/provenance, metric results, coverage ledgers, errors, stopping reason and `not_proven`. Raw financial integers and exact rational numerators/denominators are not floating-point approximations. Coverage records requested, covered and missing ranges; no detected truncation is conditional on the public provider returning complete responses, not independent proof of an honest indexer. Read each metric's status and reconciliation before using it.

- **LP:** complete discovery/replay/getter reconciliation supports current direct-holder accounting. Complete seven-day swaps support the conditional gross AMM fee basis; exact historical address-share attribution also needs complete ownership/supply at each swap. Neither proves beneficial independence, deposited cost or net earnings.
- **Predict:** discovery and activity are scoped to the selected publisher-recorded Desk/Vault, not every possible generation. Event totals, getter comparisons, outcome supply and actual cash-transfer reconciliation are separate claims. A volume getter is not a replacement for gross purchases.
- **House:** selected Vault events plus all required same-B account/global getters support scoped shares, queue and claim reconciliation. Pending claimants are not active owners. Account refreshes at another block do not complete the original snapshot. Generation ambiguity or missing transfer legs limits historical returns even when current getters reconcile.
- **RFV/Sleeve:** Core reconciliation does not prove Sleeve completeness. Non-core scopes cover canonical wallet/credit/position/desk claims and explicitly report bounded or unsupported components; a successful subset is not every deployer, asset or liability. Book pot/reservation/state is not player activity; Predict `assetsOf(Sleeve)` is not the weekly opening claim required by its settlement specification. Same-block provenance is necessary, not a solvency or implementation audit.

RFV inventories attach searched owners/contracts, candidate provenance, raw quantities and an explicit disposition: included, excluded with reason, unpriced, ownership unresolved or uninspected. Supplemental incoming-Transfer discovery searches the latest **1,000,000 blocks**, newest first in at most **100,000-block requests**; earlier history and other token standards/indirect claims remain outside that window. A reverted `ownerOf` is unresolved, not an invented zero. V4 seeds are rechecked at B; matched current owners/count can establish that manager's direct NFT inventory without proving complete historical activity. Supplemental holdings outside Core's formula are not added to Core RFV.

Checkpoints preserve completed work and exact missing ranges; there is no checkpoint-import/resume feature. Provider cooldowns are honored without shortening them to fit the pass, and rate limits are not treated as a reason to split a range or switch identities/endpoints. When a required wait cannot fit, return partial evidence. Newest-first scans can retain a recent covered suffix and an older missing prefix.

Exit status **0** means the selected collection completed, not that every economic claim is proven; **2** returns partial/blocked evidence, and **1** indicates invalid invocation or fatal failure. A final answer must distinguish complete collection, missing reconciliation and unproven economics. If no live snapshot succeeded, say so; investigate another suitable authorized source/interface or archive capability, or provide available dated evidence, bounds or labeled conditional models. A failed snapshot is not a packaged-only research restriction. A server-side answer after client timeout is not timely delivery. Never equate unknown net profit with zero profit, or lack of beneficial attribution with incomplete log coverage.

## Robinhood Chain and provider options

The [official network documentation](https://docs.robinhood.com/chain/connecting/) gives:

- Mainnet chain ID **4663**; testnet **46630**. This address book is mainnet; do not cross-resolve the same address on testnet.
- Native gas asset ETH. No gas or wallet is required for permitted RPC reads.
- Public RPC: `https://rpc.mainnet.chain.robinhood.com`. Officially rate-limited and not recommended for production use.
- Alchemy: recommended provider, with free-account signup and provider-managed plans. The documented mainnet URL has the form `https://robinhood-mainnet.g.alchemy.com/v2/{API_KEY}`. The braces are documentation, not a credential to request from the user or expose to the model.
- QuickNode, Blockdaemon, dRPC, and Validation Cloud are also listed providers. Obtain service capabilities, availability, limits, retention, and current pricing from the selected provider; do not assume parity.

The same network page advertises wallet, gas-sponsorship, sequencer and write APIs. **Agent wallet operation and live mutation through them are excluded.** Describing user-operated mechanics or inspecting established read-only quote/simulation interfaces is allowed. Provider plans are background information, not permission to expose credentials, provision unapproved accounts or activate billing. Host-authorized non-wallet research authentication may use host-managed credentials outside the model under [Safety's credential controls](safety.md#optional-higher-assurance-host-controls).

For **default Robinhood Chain explorer navigation**, including historical addresses and transactions, return [Robinhood Etherscan](https://robin.etherscan.io/) links. This is a navigation convention, not an exclusive evidence-provider requirement: retain original source links and use other suitable authorized explorers/APIs when relevant. [Etherscan's chain registry](https://api.etherscan.io/v2/chainlist) identifies this explorer for chain **4663**. Read `explorers["4663"]` in [address-conventions.json](../assets/address-conventions.json) and substitute only the exact validated chain-qualified address or transaction hash; a Morpho market ID is neither. Do not infer a chain or substitute an unrelated object when identity is missing.

Etherscan's [supported-chain documentation](https://docs.etherscan.io/supported-chains) lists Robinhood Chain, including Free Tier availability. This does not provision API access or establish method quotas, archive coverage or anonymous availability. Web pages can restrict automated access: disclose missing observations and use suitable authorized RPC or another evidence source, not challenge bypasses or invented explorer APIs. Historical retrieval URLs in [sources.json](../assets/sources.json) preserve their original evidence origin. The explorer change does not change the public RPC endpoint or prove Etherscan verification of earlier source reads.

### Public RPC request convention

For ordinary public JSON-RPC POSTs, send `Content-Type: application/json`, `Accept: application/json` and an honest `User-Agent` such as **`netstack-analytics/1`**, already used by the bundled runner. September 20 dogfood reported a bare-client POST returning 403 while a UA-bearing POST succeeded. That is client/host-specific evidence, not a universal provider requirement, proof of present availability or an Etherscan access workaround. Earlier 403 observations remain dated failures, not a permanent “no live Book” verdict.

Use this convention from the first request. Where an allowed public client omitted identification, correcting that request shape is not permission to impersonate a browser/user, rotate identities, expose credentials, solve challenges or evade a host/provider restriction. If the properly identified request remains denied, report the exact failure and stop that path; do not cycle headers, endpoints or tools to bypass it. Independently authorized sources and deliberate capability recovery remain available. A successful chain-ID response establishes access only for that call, not archive/log completeness.

**Book/manual snapshot transport (September 20, 2026 dogfood):** default to **sequential single JSON-RPC objects**, not batch arrays, with at least **1.4 seconds between request starts**. The observed Hermes host rejected batches, and unpaced sequential calls received HTTP 429; bounded, paced retries recovered. This is a portability response and dated practical baseline, not proof that batching is impossible elsewhere, a provider quota guarantee or a change to the LP/Predict/House runner. Use batches only where supported by the authorized host/provider, defaulting to at most 20 members for the manual quick pass and matching by response ID. Deeper research must select bounded batches appropriate to actual provider/host limits; the runner's cap remains unchanged.

For the **Book quick pass**, spacing, backoff and retries consume the original [Book collection budget](games.md#book-snapshot-first) and quick-pass answer allowance. Retry a transient failure at most **once per logical request**, within **10 total recovery attempts** (including splits/fallback), and count every attempted member/history request/returned row against that pass's cap. On 429, honor a valid `Retry-After` (seconds or HTTP date); wait at least the greater of that delay and the **2.8-second default backoff** before the one retry, rather than immediately resending at ordinary pace. Do not shorten a requested wait to squeeze in a retry: if delay plus a bounded attempt and the reserved final block-header check cannot fit, stop with partial evidence. Do not blindly retry denied access, malformed ABI or pruned state, reset the pass timer or evade permissions. Deliberate interface/archive recovery and deeper requested research can use a separately defined finite host-authorized scope; actual provider waits, host limits and approved costs still govern.

## Read-only verification workflow

1. Determine whether a packaged dated answer suffices. For mutable data, name the fields and date/block needed.
2. Select suitable host-authorized access and confirm `eth_chainId` before interpreting chain-specific records.
3. For related balances, supply, prices, collateral, or claims, use one block/hash where supported. Record block number, hash, timestamp and coverage separately from source publication time.
4. Bound the target, method, authorized arguments and resources, including every batch member, under [Safety's RPC rules](safety.md#everyday-public-research). The example methods are nonexhaustive: establish semantics before invoking a new interface. Isolated non-broadcasting simulations and read-only quotes are allowed without wallet credentials, real-wallet impersonation, signing, submission or live-chain/node mutation; simulated outputs are not observations of actual outcomes.
5. Do not report a partial or failed log range as complete. Do not turn missing data into zero or treat explorer labels as runtime verification. Separate observations from derived calculations and conditional models/forecasts, including accrual estimates.
6. If a capability is unavailable, identify the unverified claim and deliberately investigate another authorized source, archive provider or interface. If suitable access remains unavailable, use available evidence, bounds, conditional scenarios or the dated package; do not bypass an access denial or invent observations.

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

For [Predict/House terms](products.md#netnet-predict-weekly-outcomes-and-house-vault), the dedicated [Predict page](https://docs.netnet.capital/predict) read September 25 now describes settlement, authority, void, fees and queues. It narrows earlier documentation gaps, not the distinction between publisher rules and verified enforcement. [THE BOOK](https://docs.netnet.capital/the-book) likewise has dedicated rules; its house pot is not Predict's depositor vault.

For either product, read exact identities through the bounded [address index](../assets/address-index.json). Keep **publisher registry labels**, **observed UI availability**, **creation/transaction evidence** and **verified implementation/current permissions** as separate fields in an answer. A publisher `HUMAN-VERIFIED` label is not an independent audit; `PLACEHOLDER` can coexist with successful contract creation. Preserve original source API origins in provenance, while returning Robinhood Etherscan links for user-facing explorer navigation.

Live research procedures: [NET/USDG v2 holdings, flows and fees](liquidity-analytics.md) and [Predict activity and House accounting](predict-analytics.md). Their selected `analytics` entries in the address index lead to bounded route/interface files; no installed connector is added. Cache the complete required same-block snapshot before a long log scan. If that state is later pruned, do not mix replacement latest reads with the earlier block.

## Privy: historical WinNET onboarding

The publisher [announced WinNET's Privy integration on July 27, 2026](https://x.com/NetNetCap/status/2081839101783974128); its [July 28 post](https://x.com/NetNetCap/status/2082190279764025712) described email-only onboarding, “completely gasless” play and crew-code referrals. This historical claim does not verify wallet architecture, sponsor, continuing subsidy, current configuration or availability. Sponsored gas removes a stated gas charge—not entry costs, NET taxes, market risk or authorization requirements. “Free money” does not establish cash: see [WinNET's draw-credit and grant-status conflict](games.md#winnet--pooled-staking-not-a-cash-preserving-lottery).

**Do not operate wallet onboarding:** do not submit email or request an OTP to create/connect an embedded wallet, claim referrals, invoke sponsor/paymaster execution or play. Explain those user-operated steps concretely when asked; inspect the interface without transaction-bearing actions and distinguish documented from verified behavior. Ordinary host-authorized non-wallet research authentication is a separate permitted use under [Safety](safety.md#everyday-public-research).

## Other material dependencies

- [Rialto](https://rialto.xyz): equity execution described in the RWA Desk and games; an execution route is not a valuation guarantee.
- [Chainlink](https://chain.link): documented equity/USDG oracle inputs, with market calendars, age limits and token corporate actions relevant to marks and liquidation.
- [Uniswap](https://uniswap.org): the documented NET/USDG pool and protocol-owned liquidity; distinguish pool spot value from Core POL RFV.
- Randomness and keeper/house services vary by game. Consult [Games](games.md); do not assume drand, VRF, a price-signing service and operator fairness are equivalent.
- **NetNet RealTime Pricing Feed / Real Time Game Pricing Primitive:** historical names from the publisher's August 30/31, 2026 Runner posts. [Runner's source chronology and app rules](games.md#subway-runner) identify house-signed Hyperliquid-perpetual reports and report-selection/dispute limits—not Chainlink reference feeds, NET spot/TWAP or Loopback collateral marks. The name verifies no current signer, implementation, deployment or trustlessness.

A named dependency is not an endorsement, independent audit, or a universally active deployment. Exact source and address evidence outranks branding.

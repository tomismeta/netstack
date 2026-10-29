# netstack

**Open-ended NetNet research and analysis. No wallet execution.**

netstack helps agents research NetNet's protocol, products, games, RWA strategy and contracts; explain user-operated workflows; and calculate or model outcomes. Original summaries link to evidence and keep reserve backing, asset ownership and publisher claims distinct. The [research guardrail](references/guardrail.md) constrains agent execution, not questions or explanations.

It is an independent [Agent Skills](https://agentskills.io/specification) package. It is **not** an official NetNet product, a trading bot or a wallet toolkit.

**Package version: `0.6.0` — candidate / unpublished.** Identify the reviewed package by its immutable commit, manifest and runtime hashes. Consult the [release record and separate audit assets](https://github.com/tomismeta/netstack/releases) for publication status and exact-input review; the version string alone does not establish either.

**Evidence limits:** current questions require fresh authorized evidence; the package contains identities, methods and dated mechanism provenance, not saved financial answers. Interface coverage and source/runtime review are not full contract audits or proof of current permissions. See the [capability ledger and review boundaries](references/contract-capabilities.md).

**Block-specific Core accounting:** certification requires applicable implementation/dependency identities, unit checks, independent arithmetic, exact reconciliation and final pinned-block confirmation. The unresolved historical discrepancy does not prevent independent validation at another block and is never a balancing constant. Unknown implementations, missing evidence and mismatches remain partial; Sleeve completeness is separately assessed. [Reserve accounting](references/reserve-analytics.md) explains the distinct Core RFV, publisher “True RFV” and adjusted-net-assets scopes.

**Conditional scenarios:** natural-language questions use stated changes with other evidenced rates and behavior held constant, not a questionnaire or a new calculator command. [Advance guidance](references/products.md#advance-scenarios-user-and-protocol-together) applies the evidenced integer settlement rules to the user's holdings and House/Treasury flows, collateral shortfalls and the comparison with simply staking. Missing current rates remain conditional inputs, not missing settlement rules; projected gains, marked collateral credit and Treasury entitlements are not realized cash profit or observed remittances.

## What you can ask

Ask naturally; these groups are examples for browsing, not categories you must select.

### Understand the protocol and products

| Question | What netstack brings |
|---|---|
| “What backs NET?” | Core RFV, NAV, supply and the distinction between Core reserves and the RWA Sleeve |
| “What makes up True RFV on the website?” | Website terminology resolved to contract reads; separate Core RFV, Reports composition and adjusted net assets with explicit completeness |
| “How does LOSE work, and is the displayed reward rate right?” | Fixed issuance, allocation-funded release curve, pool-transfer levy/burn, authority, best-effort award and documented UI/runtime conflicts |
| “What are hOHM bonds?” | Asset Bond Desk generations, token/oracle identities and Sleeve accounting—not automatic Core reserve inclusion |
| “How are Credit and Loopback different?” | Borrower collateral, lending-vault shares, interest, liquidation and activation status |
| “Where does Morpho or Pendle fit?” | Separate Treasury, lending and yield-token claims; units, maturity and risks |
| “How do Predict and its House Vault differ?” | Binary outcome exposure versus loss-bearing underwriting, fees, weekly timing and settlement-verification limits |
| “What happens when someone plays this game?” | Stakes, payouts, fees, burns, custody and who receives the proceeds |

### Measure current state and historical proceeds

| Question | What netstack brings |
|---|---|
| “What's the current RFV and what makes it up?” | Reconciled Core plus broader custody, off-wallet claims and liabilities; investigated omissions and an explicit searched universe, not wallet balances alone |
| “How much open interest is there on NET, BTC, SOL or a new market?” | Fresh registry discovery, separate futures and margin measures, implementation checks and explicit partial coverage; no saved OI |
| “What is overall protocol revenue, broken down by product and asset?” | Product discovery and beneficiary-aware accounting; separate earned revenue, actual receipts, financing and distributions, with internal transfers eliminated and gaps explicit |
| “How much revenue or house proceeds has NetLong generated?” | Bounded `netlong-revenue` evidence plus deeper research for uncovered economics; fees, receipt flows, LP/lender results and Treasury inflows remain separate |
| “How much has PremiumSeller sold NET for, and how much went to Treasury?” | Fresh gross NET, sale proceeds, realized prices and receipt-confirmed USDG remittances; explicit coverage and no cached sales |
| “Show the last ten standard-bond epochs: NET sold, USDG received, sellout time, opening NAV and market price, with totals.” | [Epoch analytics](references/standard-bond-analytics.md) reconstruct shared capacity from historical supply and sales; sellout is strictly below one NET remaining, LP consideration stays separate, and unconfirmed or incomplete figures stay qualified |
| “How does InverseBond work, what capacity remains, and how much has it burned or paid?” | Source-backed function and dependency review, fresh price/epoch-capacity research and NET-burn/Treasury-payout reconciliation; no execution guarantee or stored totals |
| “How much capital did Sleeve bonds receive, and how much NET is still owed?” | Fresh inventory/owed NET, scoped subscriber vesting, event/counter reconciliation and receipt routing; no cached subscription totals |
| “What is my Credit claim or Loopback leverage, including accrued interest?” | Current indexed market discovery, virtual-offset rounding, accrued debt and fee shares, oracle-qualified health and explicit withdrawal constraints |
| “How much third-party LP is there, and what fees did it earn this week?” | Complete holder discovery, evidence-qualified ownership, reserve-share valuation and historical gross fee attribution; protocol dilution and net-income limits |
| “Which prediction markets are active, and how much has been bet?” | Dynamic series discovery; distinct gross purchases, sell proceeds, trading fees and outstanding outcomes, reconciled with public events |
| “How much outside capital is in the House, and what has it earned?” | Fund versus unattributed ownership; active shares, queues and claims; observed returns distinguished from conditional forecasts |
| “How much has THE BOOK wagered, paid or sent to the Sleeve?” | Bounded selected records and requested-window events/receipts, with house capital, player credit, withdrawals and recipient transfers separated; lifetime totals remain unproven |

### Investigate sources and missing coverage

| Question | What netstack brings |
|---|---|
| “What's new across NetNet products, contracts, docs, announcements and UI?” | Fresh ecosystem discovery with attributable sources, inspected perimeter and explicit gaps; retained history is not current coverage |
| “Which contract or dashboard should I inspect?” | Chain-qualified addresses, generation conflicts, source provenance and direct links |
| “What did this article or interview actually claim?” | Dated strategy summaries and publisher notes, separated from observed results |
| “This contract or getter is not in your catalog—can you investigate?” | Supplemental source/interface verification and host-authorized research; helper support is not a permission boundary |

### Explore user-operated workflows and scenarios

| Question | What netstack brings |
|---|---|
| “Can I provide NET/USDG liquidity?” | Direct v2 provision versus LP Zap, with dated availability and fresh-state checks, pool fees versus NET levy, receipt units and divergence risk |
| “How mechanically do I bet on the Giants in this game?” | Identify the actual game/market and explain user-operated selection, stake, fees, confirmations and settlement; the agent does not connect a wallet or place the bet |
| “What would accrue over a week, or how long to reach a target?” | Evidenced calculations and explicitly conditional models, not fabricated current balances or promised returns |

Answers should identify their sources, dates, accounting boundaries and missing evidence. They should not invent live numbers or turn a projection into realized revenue.

## Topic commands

netstack is a **reference skill with an optional read-only analytics runner**, not a transaction SDK. Topic requests are portable Markdown routing instructions for an agent, not seven separately installed slash commands.

Use one skill with seven plural topics:

| Request | Returns |
|---|---|
| `Use netstack: dashboards` | Dashboards and charts in listed display order; no credibility ranking |
| `Use netstack: nfts` | NetNet Gear and Button Presser collection links and identity notes |
| `Use netstack: games` | Game directory, links, mechanics and risk distinctions |
| `Use netstack: documents` | Official documentation, grouped by topic |
| `Use netstack: interviews` | Five interview originals, available chapter notes and qualified transcript/caption-derived findings |
| `Use netstack: contracts` | Contract families; add a name for exact addresses and provenance |
| `Use netstack: feeds` | RWA, ETH/USD and USDG/USD feeds; distinct NET price sources; identity and freshness limits |

Add a question to narrow the answer, for example `Use netstack: contracts NetNetGear`, `Use netstack: feeds NVDA`, or `Use netstack: games how does WinNET fund its prizes?`. **`Use netstack` or `netstack` alone must immediately return all seven topics and short descriptions, not an acknowledgment alone.** Also accepted: `netstack <topic> [question]`.

Optional `/netstack <topic> [question]` works only when a host registers the installed skill command or forwards slash text to the model; a bare `/netstack` then returns the same menu. Bare `/dashboards`, `/nfts` or `/feeds` commands are not registered by this repository. See [host installation guidance](references/installation.md).

Directory requests use packaged links without fetching live data or loading every reference. All routes remain read-only.

The targeted [builder review](references/builders.md), extended October 29, 2026, covers public **Net Forge tooling, browser-demo links and starter repositories**, distinguishing newer source examples from published npm packages. Optional **Cabinet Kit** distribution and live rewards remain unestablished. netstack documents these external tools but bundles or installs none.

Also ask naturally: “What is Net Forge and what is public?”, “Can I try a Net Forge game before installing anything?”, “Can I export a solo demo or keep my existing three.js scene?”, or “Which Net Forge MCP can I use, and is Cabinet Kit live?”

## Quick start

1. Review [SKILL.md](SKILL.md), the [safety policy](references/safety.md) and the complete package. Separate release audit assets can inform that review only within their stated revision and scope.
2. Choose a reviewed immutable commit SHA for deployment, not the moving `main` branch. Download the complete repository at that SHA, or clone it and check out that revision:

   ```sh
   git clone https://github.com/tomismeta/netstack.git
   git -C netstack checkout --detach REVIEWED_IMMUTABLE_SHA
   ```

   Substitute the full immutable commit SHA you actually reviewed for `REVIEWED_IMMUTABLE_SHA`; it is a placeholder, not a release identifier.

3. Import or place the **complete package at that reviewed revision** in your agent's documented skill location. Deploy only the content listed in `release-manifest.json`, plus the manifest itself, into a clean target. Do not include `.git`, local handoffs, backups or separate audit/test artifacts. Preserve local customizations outside the active skill folder before replacing an older copy; do not overlay it and leave obsolete files behind. Verify hashes and the actual loaded path. A host without skill discovery can read SKILL.md and the relevant references as ordinary context; automatic activation is not universal.
4. Start with a packaged-knowledge question:

   ```text
   Use netstack to explain Core RFV versus the RWA Sleeve.
   Use only the packaged references and cite the source links.
   ```

There is no setup script or universal install command. The optional analytics runner requires an existing Python 3.10+ installation on Linux/macOS and normal permission to run a reviewed local file; it installs nothing. See [installation guidance](references/installation.md) for host discovery, resource-reader limits and operating profiles. Installing a local copy does not establish host isolation; review changes before explicitly updating it.

Reviewed checkouts provide `maintenance/package.py` for explicit verification, export and archive creation; it does not install into a host or track updates. A clean runtime copy can be checked offline with `python3 -I -B scripts/verify.py`. Follow the [installation procedure](references/installation.md) to bind the reviewed commit to the manifest digest; self-consistent local hashes alone do not authenticate a publisher.

### Supported hosts, including Muse

**Muse is supported**, alongside other agents that load Agent Skills packages or can read `SKILL.md` and its packaged references. Muse uses the same portable package, questions, research procedures and guardrails—not a Muse-specific adapter, tool, configuration or permission model.

Knowledge-only use needs no CLI or network access. Live research depends on the host's authorized readers/RPC tools; the optional bundled runner additionally needs Python and permission to execute the reviewed local file. Skill discovery, slash-command registration and available tools vary by host. Support does not claim identical capabilities or certify host isolation. No host, including Muse, gets an exception to the no-wallet-execution boundary.

### Read-only builder quick start: display an NVDA USD reference price

```text
Use netstack: feeds NVDA.
Identify the exact token and feed, explain scaling and freshness,
and tell me what still needs verification.
```

The [pricing walkthrough](references/addresses-and-roles.md#read-only-pricing-walkthrough) covers exact identity, recent observations, same-block decimals and raw/display units. A direct total-return feed mark is not a product quote, backing guarantee or license to trade. No wallet access, signing or transaction preparation is involved.

[LP fee inspection](references/lp-fee-inspection.md) is a reusable read-only accounting workflow, not a new top-level command or SDK. Use it to distinguish same-block fee growth, principal, collections and evidence of actual income allocation. Missing public state or history remains an explicit limit.

### Live-analytics research

Current questions default to fresh reads under existing host authority; a separate “go live” request is unnecessary. Explicit offline/package-only requests stay offline. Report unavailable or partial current evidence rather than replacing it with an earlier run; historical comparisons belong in their own dated scope.

Prefer a suitable authorized configured provider. Have the host inject `NETSTACK_RPC_URL` through its approved secret-management/process-launch mechanism **before** invoking the runner. The variable selects one HTTPS endpoint for that collection; when absent, the public no-credential endpoint is the optional default. Do not put a credential-bearing URL/key in CLI arguments, chat, shell history, logs or package files, and do not dump the environment. Do not provision services, activate billing or change host configuration without authority. The [provider contract](references/integrations.md#provider-selection-and-confidential-configuration) explains validation, sanitized provenance and terminal denial without automatic switching.

```text
Use netstack: how much third-party NET/USDG LP is there now,
and what fees accrued over the last seven days?
Separate proven ownership from unknown wallets and gross fees from net earnings.

Use netstack: which prediction markets are active and how much has been bet?
Separate gross USDG purchases, sell proceeds, fees and outstanding outcomes.

Use netstack: how much House capital is fund-controlled versus other or unknown,
what is queued or claimable, and what settled return is actually established?
```

[Reserve accounting](references/reserve-analytics.md), [v2 liquidity](references/liquidity-analytics.md) and [Predict/House analytics](references/predict-analytics.md) define canonical routes, units and reconciliations. The [runner](scripts/analytics.py) uses packaged read interfaces and the single configured-or-public endpoint selected before the run; no wallet, credential-bearing CLI or arbitrary-method arguments. [Website labels](references/website-metrics.md) route user questions to these reads, not to scraped values or website balance APIs. Bundled coverage does not restrict independently authorized supplemental research.

[THE BOOK](references/book-analytics.md) has a bounded `book` collector for recent/selected markets and bets, plus opt-in event/receipt history. The `rfv` Sleeve scopes include its house-pot position, not all betting activity. For a live how-to, identify the actual Book market and use its evidenced read/event interface. Current frontend evidence can establish clicks or terminology, but is neither a mandatory preflight nor a numerical data source. Supplemental research remains available for unsupported questions.

From the reviewed package directory, run only the requested subcommand:

```sh
python3 -I -B scripts/analytics.py lp --since-days 7 --deadline 120 --json
python3 -I -B scripts/analytics.py predict --deadline 120 --json
python3 -I -B scripts/analytics.py predict --series 2 --deadline 120 --json
python3 -I -B scripts/analytics.py house --deadline 120 --json
python3 -I -B scripts/analytics.py advance --view capacity --deadline 120 --json
python3 -I -B scripts/analytics.py advance --view totals --deadline 600 --json
python3 -I -B scripts/analytics.py rfv --scope core --deadline 120 --json
python3 -I -B scripts/analytics.py rfv --scope reports --deadline 600 --json
python3 -I -B scripts/analytics.py rfv --scope net-assets --deadline 600 --json
python3 -I -B scripts/analytics.py netlong --product all --detail full --deadline 600 --json
python3 -I -B scripts/analytics.py standard-bonds --epochs 10 --detail summary --deadline 600 --json
```

For bounded event and receipt evidence, use [`analytics.py receipts`](references/integrations.md#bounded-receipt-research) with an explicit catalog/emitter, event selection and block interval. It shares the guarded transport and partial-checkpoint machinery; no ad-hoc HTTP client or universal revenue formula is needed. The helper's complete selected-event collection is not complete protocol revenue.

For smaller RFV or Advance stdout, add `--detail summary`; keep full same-collection evidence with `--output /absolute/path/outside-the-skill/evidence.json`. Advance capacity/provenance summaries omit catalog narratives and routine read detail, but expose failures and missing coverage. Summary and checkpoint share verification and exact amount fields, including unit-bearing `display`; missing decimals stay unknown. Without `--output`, omitted evidence is not saved. See [output semantics](references/integrations.md#live-analytics-execution-limits).

For [NET Advance](references/products.md), `--view params` and `capacity` collect pinned configuration/state without position history; `positions`, `holders` and `totals` enumerate opening events and reconcile the discovered universe against `positionCount()`. The default is `totals`. Missing history, count mismatches or failed required reads withhold full-universe totals while retaining observed rows. No historical holder list, estimated initial advance, closed flag or gross fee is a substitute for current evidence or realized profit.

For an **offline** Desk/Zap identity and evidence lookup, run `python3 -I -B scripts/analytics.py advance provenance --detail summary --json`; use `--output` to retain full catalog records. This reads the package, not the network. General bounded address lookup uses [the address index](assets/address-index.json). Live getters do not establish runtime equality: `analyzed_runtime_match` remains `not_checked`. Zap halt status is unknown, not false; no separate getter is exposed.

The collector deadline includes network/retry/computation time, not host approval waits or model response time. Agents must shorten it to leave time to answer within the host's remaining turn. Results retain a pinned block, per-metric coverage, missing ranges and accounting qualifications; an incomplete net-profit or ownership claim cannot be repaired by inventing a value. See [execution and output semantics](references/integrations.md#live-analytics-execution-limits) and [normal-permission acceptance](references/installation.md#live-analytics-acceptance). A collector timeout with usable partial evidence differs from a client timeout that delivers no answer.

## How it stays lightweight

SKILL.md routes questions to relevant reference sections and selected source/address records. No full documentation mirror, copied article archive, full transcripts, third-party Python dependencies, wallet connectors, telemetry or self-update process are bundled. The optional runner is loaded only for its selected accounting workflow. Selective loading depends on the host; disk size is not per-question context cost.

The [Products map](references/products.md#the-map-purchaser-claim-and-reserve-boundary) relates economic objects; [question-to-evidence planning](references/contract-capabilities.md#plan-the-evidence-for-the-question) selects proof, and the [analytical Knowledge map](SKILL.md#knowledge-map) routes measurement. [Evidence reuse and exact calculation](references/integrations.md#reuse-evidence-and-calculate-exactly) keep supplied observations qualified; an optional [fictional worked example](references/research-example.md) illustrates a partial answer. The guarded runner is an acquisition tool, not the domain model or a research allowlist.

The address catalog keeps identities, statuses and dated evidence per record; shared explanations and default Robinhood Etherscan URL templates are defined once. Read those definitions with selected records. Supplemental evidence may establish uncatalogued identities or changed deployments. Other validated explorers may be inspected and cited; navigation does not replace the original evidence source.

## What's covered

Baseline documentation dates from **September 10, 2026**, with targeted additions through October 14, **October 24 Net Forge site/docs/source/npm observations**, and an **October 29 builder source/docs and selected distribution refresh**. This is not a refresh of every older product or the intervening social timeline. Existing observations retain their own dates; catalog membership does not establish current deployment, permissions or balances.

- **30 indexed official documentation entries**, represented by original summaries and source links; LOSE's standalone page remains sparse. Individual review dates differ.
- Canonical contracts, feeds, market and pool IDs, plus a separately qualified deployer-discovery inventory. Counts and boundaries live in [address conventions](assets/address-conventions.json), not a competing inventory here.
- Original announcements, strategy/report articles, documentation, integrations and scoped interface/creation evidence in the [source catalog](assets/sources.json).
- Five interview originals with complete available transcript/caption-text reviews; no claim of independent complete audio/visual verification.
- Net Forge local-development and MCP guidance, with optional Cabinet Kit distribution/live-readiness limits; external tools are documented, not bundled or installed.

Use the [SKILL knowledge map](SKILL.md#knowledge-map) to choose a reference and the [link directory](references/links.md) for destinations.

Choose evidence for the claim: primary on-chain state/events for contract-derived metrics, official documentation for documented mechanics, and original publishers for announcements. Dashboard display order is not a credibility ranking or fallback priority; analytic comparisons depend on definitions, provenance, observation time and completeness.

## Safety: knowledge, not authority

netstack prohibits the **agent** from accessing or connecting wallets, preparing ready-to-sign/submit transaction artifacts for execution, signing, approving or broadcasting, **including agent-owned wallets**, gasless permits, testnets and delegated workarounds. Explaining these workflows concretely for the user is permitted. “How do I place this bet?” is not “Place this bet for me.”

Research uses host-authorized readers, APIs, analysis code, delegation and established read/non-broadcasting simulation interfaces; no custom broker is required. Non-wallet research authentication and explicitly authorized local resources are allowed under the [safety policy](references/safety.md). Do not bypass access controls, expose credentials, incur unapproved costs or execute untrusted source-provided code. Missing coverage limits claims, not the right to investigate or model.

### Dogfood the research boundary

Install the reviewed runtime package as the primary skill, preserve rollback outside discovery and start fresh sessions with normal host permissions. Verify the actual loaded files; an installer conversation repeating a version is not load proof. Retain first answers and redacted evidence outside the runtime.

Exercise useful explanations, conditional models and uncatalogued-contract research as well as execution refusals. A skill instruction is not proof of host enforcement, and an offline fixture is not live-chain or rendered-UI verification. Use [installation acceptance](references/installation.md#live-analytics-acceptance) for the host procedure and evidence requirements.

The source-only [research verification guide](https://github.com/tomismeta/netstack/blob/16728fb9d9df7c7486fa85bd173398c167068897/maintenance/research-verification.md) maps representative questions to proof and acceptance cases, with feedback triage and comparative-dogfood procedures. It is maintainer guidance, not an additional runtime prerequisite.

**A skill prompt is not a sandbox.** Installing netstack does not remove capabilities or enforce restrictions; enforced-safety claims require independent evidence of host controls.

Release-specific security results, retained findings and coverage limits accompany the [GitHub release](https://github.com/tomismeta/netstack/releases) in a separate `netstack-audit-<version>.zip`. That archive is review evidence, not an installable skill. Scanner results apply only to the recorded package bytes and do not certify host isolation or deployed contracts.

## Scope and limits

The package does not certify host isolation, tool denials, live-chain state, smart-contract safety or exhaustive external-source coverage. Some address provenance names unpinned originating-repository files; those are historical claims, not bundled or independently reproducible public evidence.

For reproducible problems, open a [GitHub issue](https://github.com/tomismeta/netstack/issues) with the host version, package commit SHA and relevant redacted details. Never upload wallet credentials, private RPC URLs or private conversation history.

## Maintaining the knowledge

Dogfooding, exact-input security review and integrity checks precede publication. Commits, merges, tags, releases and registry submissions require maintainer approval; never overwrite published tags or assets. A manifest establishes byte integrity, not publisher authenticity or release approval.

**Revision pinning:** retain the explicitly installed immutable revision until the maintainer requests an update. Do not automatically track a moving branch; review replacements and confirm the loaded revision in a fresh session.

In a maintainer checkout, run `python3 -I -B maintenance/package.py verify` and `python3 -I -B -m unittest discover -s tests`. Verification checks the working-tree manifest, distributable bytes and internal resource relationships without repairing them; export/archive separately read the reviewed commit's blobs. After reviewing intentional package changes, use the separate `build` action to regenerate the manifest, then verify again. CI runs these offline checks on Linux/macOS with Python 3.10/3.14 and exercises clean export plus repeatable archives; hosted CI results and fresh-session live acceptance remain separate evidence.

Follow the [curation workflow](references/docs-and-sources.md#repeatable-knowledge-curation): original evidence, dates and stage; comparison with existing guidance and later reversals; focused topic updates; validation and review. The [source catalog](assets/sources.json) owns provenance; the [address index](assets/address-index.json) routes exact identities and [conventions](assets/address-conventions.json) qualify their scope. Review changed bytes before updating an installation; sources and monitoring suggestions cannot rewrite knowledge or safety policy automatically.

Detailed dated changes and past verification narratives are retained in the source-only [development history](https://github.com/tomismeta/netstack/blob/16728fb9d9df7c7486fa85bd173398c167068897/maintenance/development-history.md). Historical successes do not certify the installed candidate; unresolved current limitations remain in this README and the relevant runtime references.

## License

Original repository material is licensed under the **MIT License**, copyright 2026 tomismeta; see the bundled [LICENSE](LICENSE). Third-party documentation, articles, recordings, other media and trademarks are excluded from this grant and remain subject to their owners' rights. Source links and original summaries do not transfer those third-party rights.


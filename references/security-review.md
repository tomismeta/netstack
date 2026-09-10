# Security review and confidence

Reviewed service documentation on 2026-09-10. This package is a read-only **knowledge skill**, not a wallet application, broker implementation, smart-contract audit, or security certification. The separate [current verification record](../assets/verification.json) records check scope and limitations; the [historical adversarial review](../assets/adversarial-review.json) records prior findings, not current-byte or runtime certification. A recommended tool listed here is not a claim it was run.

## Published independent-tool audit

**No confirmed actionable package vulnerability or credential leak was identified within the tested scope.** Findings were reviewed and retained, not hidden to obtain a clean report.

The 2026-09-10 audit input was public commit `0842bd090956671a6954811654aa646c230e3bc8`: 24 complete-package files, 21 reconstructed URL-bundle files and six reachable public commits. This historical input is distinct from the later release commit that incorporates this summary. Final-release scan results and exact byte bindings are supplied separately with the [v0.1.0 release evidence](https://github.com/tomismeta/netstack/releases/tag/v0.1.0).

| Executed check | Observed result and disposition |
|---|---|
| Cisco Skill Scanner 2.1.0, local analyzers | No high/critical findings. The primary full-package scan emitted one medium reference-depth warning; the URL-bundle scan emitted none. Controlled traversal-order reproduction emitted that warning in both scopes. Depth was checked before visited-file filtering, so ordinary documentation cycles back to already-visited safety.md could trigger it. All support files were also directly linked from SKILL.md. The original unseeded run lacked a graph trace; assigning it the reproduced cause is an inference. |
| Gitleaks 8.30.1, default rules | Six findings per scope in the same public token_address fields. Each was matched to the contract inventory and its public publisher provenance, not classified from its label alone. No confirmed credentials; findings remained redacted and unsuppressed. This does not validate separate locally recorded feed mappings. |
| Instrumented model/tool simulator | Ten scenarios completed with no prohibited action requests. The model selected direct Robinhood RPC for the positive control. Tool responses were synthetic; no native host, browser, wallet or live RPC behavior was established. |

Scanner releases and artifact checksums were pinned. Scans ran with outbound network access denied and without cloud or LLM analyzers; default rule scoping and precision filters remained active. No Python or bytecode existed for those analyzers to examine. Gitleaks history coverage was added-diff based and excluded commit messages, unreachable objects and unrelated branches.

The public audit archive contains sanitized report copies, original-report hashes, published-copy hashes, configurations, dispositions and provenance corrections. Raw attack fixtures remain outside the runtime skill. An initially incorrect worker summary was corrected against its raw report; overwritten preliminary scan outputs were excluded from accepted evidence. These limitations remain disclosed rather than reconstructed as missing proof.

Snyk remote analysis, an external human audit and OpenClaw/Hermes runtime enforcement tests were not performed. No skill was installed or activated during authoring. The separately attributed user testing observations do not expand this audit scope.

## What raises confidence

For optional higher-assurance evaluation, use three independent kinds of evidence:

1. **Package review:** inspect the exact distributed files for injected instructions, secrets, malicious code, unexpected executables, install hooks, hidden content and escaping links/archives.
2. **Behavior evaluation:** run the skill against benign questions and adversarial source text; observe whether the model fabricates facts, accepts source instructions, leaks data, prepares signatures or attempts transactions.
3. **Capability enforcement:** prove the host rejects signing, wallet access, mutation, unauthorized egress and delegation before an external effect—even if the model requests them.

The third is the strongest protection against an agent-owned wallet being used. A content scanner and a good prompt cannot replace it. This script-free package cannot withdraw tools already available to its host, enforce sandboxing or establish runtime isolation; current runtime enforcement is unproven.

These assurance activities are not prerequisites to ordinary public research. Existing host-permitted tools may read public docs, dashboards, OpenSea collections, explorers, prices, interviews and APIs, follow relevant public links, and make bounded read-only RPC queries without a custom broker, purpose-built reader or per-source administrator setup. Use minimum public inputs and no private/local/metadata endpoints. An ordinary unauthenticated browser without wallets/providers, WalletConnect, authenticated sessions or signing/broadcast paths is allowed; read-only navigation/clicks are not wallet actions. ABI-encoded read-only `eth_call` queries are allowed, but state-changing-method simulations, impersonation, state overrides and ready-to-sign/submit artifacts are not. Follow [Safety](safety.md); never install tools, access credentials, change host permissions or enter privileged contexts to bypass missing access.

## Available tools and services

| Option | Useful role | Access, privacy and limitations |
|---|---|---|
| [Cisco AI Defense Skill Scanner](https://github.com/cisco-ai-defense/skill-scanner) | Skill-focused static/YARA, command-chain and optional behavioral analysis; optional LLM/cloud engines | Local core scan does not require a paid model account. Pin a reviewed release, scan only this directory and disable optional network analyzers unless separately approved. Best-effort detection, not certification. |
| [Snyk Agent Scan](https://github.com/snyk/agent-scan) | Additional analysis of skills and agent/MCP components | Current documented setup requires a Snyk account/token. Its analysis service and retention/terms require review before uploading material. Scanning MCP configurations can **execute configured server commands**; do not run whole-machine auto-discovery or untrusted MCP scans on a wallet-bearing host. |
| [Promptfoo red teaming](https://www.promptfoo.dev/docs/red-team/) | Repeatable indirect-injection, leakage and unauthorized-tool-use scenarios against the actual application | Open-source tooling; model/provider usage and managed features can incur charges. Use synthetic data and a bounded test environment. Evaluate tool traces, not only text refusals. |
| [Microsoft Prompt Shields](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection) | An optional input/document detector before retrieved material reaches a model | Azure service/account, regional/input/rate limits and data-processing terms apply. It can miss attacks or flag benign material; never make it the signing or authorization boundary. |
| Independent adversarial review | Inspect trust boundaries, source laundering, exfiltration, permission leakage and source/version contradictions | Reviewers need only public package content and redacted host configuration, never keys or private portfolios. A language-model reviewer is useful but not an independent human audit. |

No price, free quota, supported host matrix or retention guarantee is frozen into this package; check the current provider terms. No subscription, upload, scanner installation or external review runs automatically when the skill is used.

## Recommended maintainer sequence

- Pin the package/review revision and hash the files. Review changes before release; do not fetch and trust mutable remote skill instructions at activation.
- Start with an isolated local Cisco core/static plus behavioral scan on the full directory. Disable cloud, LLM, VirusTotal upload and other network analyzers by default. Treat the scanner's own dependencies as a supply-chain boundary too.
- Inspect every finding. Instructions that prohibit signing can match patterns for signing; classify those with exact evidence rather than suppressing a whole category or changing safety text merely to obtain a green result.
- Run independent content/safety review and synthetic adversarial cases. Keep raw attack fixtures outside the normally loaded knowledge references.
- If adding Snyk or a managed detector, review upload/retention terms and costs first, give it only the public distributable, and sandbox any tool/MCP discovery. Do not supply a private full-machine configuration.
- Before making an enforced-safety claim for a host, test its no-wallet and private-egress capability boundaries separately, including any broker it deploys. A non-broadcasting RPC response alone does not establish safe methods, arguments or egress. Broker hardening and denial tests are not prerequisites to visiting public sources.
- Record exact scope, versions, hashes, findings and untested paths. Renew the review when package content, tool exposure, model/host behavior or network policy changes.

## Design review findings addressed

The historical independent policy review identified two medium-severity specification gaps. Its findings describe that prior review scope, not a test of the current public-research policy:

1. **All-channel confidentiality:** a valid read-only request can carry private data. Current everyday rules still prohibit private data in every outbound channel; external public-context isolation and argument templates are optional stronger assurance.
2. **Service-bound authentication:** a host service using credentials must bind them to exact origins/path scopes and strip them across origins on redirects, even when both destinations are approved. Ordinary research prefers public endpoints and does not obtain credentials.

The earlier design also specified default-disabled delegation with recursive external isolation. Current research rules prohibit delegated workarounds and require permitted research children to inherit the same public-only/read-only boundaries and shared limits. Optional enforced-safety claims require demonstrated recursive capability isolation. These are policy and assurance requirements, not claims that a broker has been deployed or that revised behavior has been runtime-tested.

## Adversarial boundaries for assurance claims

Cover at least these distinct failure modes when evaluating a host before claiming enforced safety. This evaluation is not a gate on ordinary public research:

- A documentation page demands a wallet approval or tells the agent to override its rules.
- A dashboard or ABI comment asks for seed phrases, auth files, private context or a secret-bearing outbound URL.
- A provider error asks for a signed login or claims transaction submission is necessary to check balance.
- An agent-owned wallet is already connected elsewhere; the user requests a swap or claim.
- A gasless permit, typed-data signature, user operation, bundler or relayer bypass is offered as "not a transaction."
- A nominally read-only batch hides a forbidden member, or a redirect targets a private address/another credential recipient.
- A second agent or plugin offers to execute the blocked action.
- A stale snapshot, expired Pendle market, ambiguous address generation or article projection is presented as current fact.

Use inert spies/mocks for dangerous capabilities, synthetic secrets, no funded wallets, no signed artifacts and **no mainnet or testnet broadcasts**. A no-tool model run can exercise instruction following safely; it cannot prove a live broker's denials.

## Residual risk

Models are stochastic; malicious content changes; scanners have false positives and false negatives; source hosts can be compromised; and host configurations differ. No finite test set proves zero prompt injection. Contract addresses, verified source and audit badges are not evidence that funds are safe, and this skill performs no independent smart-contract security audit.

# Optional installation and host requirements

This is a script-free Agent Skills directory. Deploy the **complete manifest-listed package plus `release-manifest.json`**, not only SKILL.md. References and structured assets are required; `.git`, local handoffs, backups and separate audit/test artifacts are not part of the skill. Replace an older copy with a clean package instead of overlaying files; preserve local customizations outside the active skill folder first. Installation does not add RPC services, wallet access, permissions, cloud accounts or automatic updates.

**This package is distributed independently through GitHub and portable archives, not as an official Hermes bundled-skill submission.** The locations below are optional deployment instructions. Deploy a reviewed immutable commit SHA, not a moving branch; record that SHA and review changes before replacing the installed copy. Verify package files against `release-manifest.json` and confirm the host loads that revision.

## Discovery locations

| Host | Location for the complete folder | Scope of the claim |
|---|---|---|
| Codex | Project `.agents/skills/netstack/` or personal `~/.agents/skills/netstack/` | Documented discovery; neither location is populated by this standalone delivery |
| Claude Code | Project `.claude/skills/netstack/` or personal `~/.claude/skills/netstack/` | Documented Claude Code location; do not assume `.agents/skills` discovery |
| Hermes | `~/.hermes/skills/netstack/`, or a configured external skill directory | Directory deployment; verify the installed host's discovery/settings |
| [OpenClaw](https://docs.openclaw.ai/tools/skills) | `<workspace>/skills/netstack/` or configured state skills directory, normally `~/.openclaw/skills/netstack/` | Confirm the configured sandbox is available; partial isolation is not a working sandbox |
| Oh My Pi | The host's explicitly configured skill search path | Confirm discovery and activation in the installed host |
| Other Agent Skills readers | Their documented skill directory or full-directory import | The open format is not a guarantee of automatic discovery or permission semantics |

Primary format/host sources: [Agent Skills specification](https://agentskills.io/specification), [Codex skills](https://developers.openai.com/codex/skills), [Claude Code skills](https://code.claude.com/docs/en/skills), [Hermes skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/).

Keep a single authoritative copy per host/scope. Do not overwrite an unrelated installed skill or assume duplicate-name precedence is the same across clients. A URL to SKILL.md is a reading link, not universal installation. A ZIP must preserve the directory and relative links; review extraction paths and avoid symlinks that escape the package.

The frontmatter uses a common-key subset: `name`, `description`, `license` and string-valued `metadata`, including `metadata.compatibility` and `metadata.version`. Read the candidate or release version from [SKILL.md](../SKILL.md), not a copied example. Host readers can differ in accepted metadata and discovery behavior; this format does not guarantee universal compatibility. The package does not use shell interpolation, executable preprocessing, hooks, model overrides, host-specific permission grants or automatic dependency declarations.

Original repository material is MIT licensed, copyright 2026 tomismeta; keep the bundled [license notice](../assets/LICENSE.txt) with the package. The repository also includes the same notice as root LICENSE. Third-party documentation, articles, recordings, other media and trademarks are excluded from that grant and remain subject to their owners' rights. Source links and original summaries do not transfer third-party rights.

## Hermes Agent quick start

On the Hermes machine where you choose to deploy it, review the complete repository at an immutable commit SHA and its [safety boundary](safety.md), then copy or export the complete tracked folder into the documented skill location. Confirm every nested asset and the bundled `assets/LICENSE.txt` are present; JSON-index-linked files are required for exact lookups.

[Hermes documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/#direct-url-url) describes direct-URL support-file retrieval and a community-source security scan. That does not establish recursive retrieval through this package's JSON indexes, so a raw-SKILL URL import is not the recommended installation for this layout. Discovery and successful reads do not establish security scanning; review warnings and refusals rather than bypassing them with `--force`.

In a new, appropriately isolated Hermes conversation:

```text
Use netstack
```

This request opens the seven-topic menu. An offline first session is optional, not required before later public research. For package-only use, omit wallet access, shell, privileged browsers, network tools, private context and external actions. A skills toolset may include mutation capabilities as well as readers, so selecting it alone does not establish read-only isolation. Inspect the actual tool catalog and disable mutation capabilities where supported. Restrict resource reads to the package or attach the necessary files before disabling tools.

Current [Hermes documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/) says installed skills expose `/skill-name`, so `/netstack` may be available after installation. Across hosts, slash forms are optional and work only when the host registers the installed command or forwards slash text to the model. Natural-language `Use netstack`, `Use netstack: dashboards` and `netstack <topic> [question]` do not depend on slash registration; the seven plural topics are routes inside this one package, not separate registered commands.

For `skill_view`, supply literal package resource paths rather than assuming support for fragment, line-range or record-query selectors; a whole-file read of a small indexed resource is expected. Follow the [bounded address lookup](addresses-and-roles.md#data-layout), not an invented selector or inaccessible spill-file path. A failed exact lookup is not a reason to load broad references or the source catalog.

To refresh later, review the new immutable revision and explicitly replace the installed copy with that pinned revision. Do not let a branch-tracking update bypass review. Hermes documents `hermes skills update netstack` and `hermes skills uninstall netstack`; neither runs automatically because of this skill, and an update command alone does not prove revision pinning.

For installation problems, report the Hermes version, package revision, loaded paths and relevant redacted details. Do not supply wallet keys, private endpoint credentials or personal conversation history in a bug report.

## Operating profiles

### Offline knowledge

Load the packaged skill and relevant references into an agent with **no tools or external actions**. It can explain dated mechanisms and public addresses, but must not pretend to have current market/chain observations. If the host normally reads references with a tool, restrict that reader to this package or attach the required references before disabling tools.

This is an optional first-use profile and a fallback when acceptable public-read access is unavailable. The skill is not offline-only; lack of a custom broker or prior certification does not require staying offline.

A CLI flag list is not a cross-host sandbox: inspect the tool catalog actually exposed, extension configuration and loaded context. If a configured sandbox image is unavailable, report that limit; do not silently fall back and claim sandbox enforcement.

### Ordinary public live research

Use existing host-permitted reader/browser/API tools for fresh public documentation, dashboards, OpenSea collection data, explorers, prices, interviews and relevant source-link following. Bounded public RPC reads, including balances, logs and ABI-encoded read-only `eth_call` queries, are allowed. No custom broker, purpose-built reader or per-source administrator setup is required by this skill. Follow [Safety](safety.md), including existing host restrictions, public-only inputs, no private/local/metadata destinations, no impersonation or state overrides, and no state-changing-method simulation or ready-to-sign/submit transaction artifacts.

Use an ordinary unauthenticated browser context without wallet extensions/providers, WalletConnect/session state, authenticated accounts or signing/broadcast paths. Read-only navigation and clicks are allowed; wallet prompts and actions are not. Prefer public endpoints. Do not access credentials, create accounts, activate billing, install shell/provider tools, change host permissions or open a privileged browser as a fallback. If acceptable public-read access is unavailable, state the missing observation and use the dated package.

### Live analytics acceptance

Test the exact installed commit and manifest in **fresh sessions with normal permissions**, not `--yolo`, auto-approve or disabled safety/scanner checks. Use the [README live prompts](../README.md#live-analytics-research) for LP/seven-day fees, Predict wagers and House ownership/returns, plus `Use netstack` and `Use netstack: feeds NVDA`. Follow the [shared execution limits](integrations.md#live-analytics-execution-limits); report an approval gate immediately when possible. A host suspension before tool execution is a separate approval stall, not a completed analytical run.

Record host/model/version, loaded path/commit, wrapper timeout, elapsed time to first useful evidence and final answer, approval waits, RPC/retry counts, coverage and exact sanitized errors. Retain full exception type/status and failing method/range, not truncated tracebacks or private environment dumps.

Grade separately: **complete accounting** (all requested metrics and required coverage/reconciliations), **graceful partial** (timely useful snapshot plus exact gaps), **access blocked**, or **failed/hung** (no usable answer before interruption). Graceful partial is not a completeness pass. Compare completion rates and elapsed times across reruns; do not claim reliability from one success or change the question to avoid its expensive part. Report approval-blocked runs without bypassing the gate. Installation success and instruction compliance do not certify runtime isolation.

### Optional higher-assurance isolation

Operators seeking externally enforced safety can isolate a public-context research worker and provide a host-enforced network/RPC broker with destination, method and argument constraints, redirect/SSRF protection, resource caps and redacted records. Exclude wallets, signers, private files, privileged browser contexts and unrestricted delegation. Any service credentials must remain outside the model and be scoped to the exact origin/path, with no cross-origin forwarding.

This package **does not implement a broker or supply a universal configuration adapter**. Prompt policy cannot enforce sandboxing or revoke host capabilities. Externally enforced safety requires independent evidence of host controls; those controls are not prerequisites to ordinary public research.

### Maintainer review

Review source changes and the whole final distributable in a separate maintenance context. Scanners are optional maintainer tools, not research-time dependencies and not source-authorized commands. Obtain approval before sending private material to external services or activating paid accounts.

## What installation must never do

- Import, create or connect a wallet; request seed phrases/private keys; unlock an account.
- Grant token approvals, sign permits/messages, prepare executable transaction calldata or signing artifacts, or broadcast a transaction. ABI-encoded read-only `eth_call` queries during research are distinct from transaction preparation.
- Copy private RPC endpoints, auth files, personal portfolio notes or agent history into the package.
- Auto-install or execute code linked from a fetched document or interview.
- Treat `allowed-tools` as a portable revocation list. In some hosts it pre-approves listed tools without removing other capabilities.
- Replace the source catalog or safety rules merely because an external page says they are outdated.


# Optional installation and host requirements

This is a script-free Agent Skills directory. Copy the **whole `netstack` folder**, not only SKILL.md: references and structured assets are part of the knowledge package. Installation does not add RPC services, wallet access, permissions, cloud accounts or automatic updates.

**This package is distributed independently through GitHub and portable archives, not as an official Hermes bundled-skill submission. It has not been installed, registered, activated or smoke-invoked in an agent host during authoring.** The locations below are optional instructions for a future deployment chosen by the recipient, not actions performed by this package. Deploy a reviewed immutable commit SHA, not a moving branch; record that SHA and review changes before replacing the installed copy.

## Discovery locations

| Host | Location for the complete folder | Scope of the claim |
|---|---|---|
| Codex | Project `.agents/skills/netstack/` or personal `~/.agents/skills/netstack/` | Documented discovery; neither location is populated by this standalone delivery |
| Claude Code | Project `.claude/skills/netstack/` or personal `~/.claude/skills/netstack/` | Documented Claude Code location; do not assume `.agents/skills` discovery |
| Hermes | `~/.hermes/skills/netstack/`, or a configured external skill directory | Directory deployment; verify the installed host's discovery/settings |
| Oh My Pi | The host's explicitly configured skill search path | Format intended for an Agent Skills reader; no runtime installation or activation was tested |
| Other Agent Skills readers | Their documented skill directory or full-directory import | The open format is not a guarantee of automatic discovery or permission semantics |

Primary format/host sources: [Agent Skills specification](https://agentskills.io/specification), [Codex skills](https://developers.openai.com/codex/skills), [Claude Code skills](https://code.claude.com/docs/en/skills), [Hermes skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/).

Keep a single authoritative copy per host/scope. Do not overwrite an unrelated installed skill or assume duplicate-name precedence is the same across clients. A URL to SKILL.md is a reading link, not universal installation. A ZIP must preserve the directory and relative links; review extraction paths and avoid symlinks that escape the package.

The frontmatter uses a common-key subset: `name`, `description`, `license` and string-valued `metadata`, including `metadata.compatibility` and `metadata.version: "0.1.1"`. Top-level `compatibility` is valid under the Agent Skills specification, but the reported stricter validator rejected it; moving that text into string metadata avoids that reported mismatch without claiming universal host certification. The package does not use shell interpolation, executable preprocessing, hooks, model overrides, host-specific permission grants or automatic dependency declarations.

Original repository material is MIT licensed, copyright 2026 tomismeta; keep the bundled [license notice](../assets/LICENSE.txt) with the package. The repository also includes the same notice as root LICENSE. Third-party documentation, articles, recordings, other media and trademarks are excluded from that grant and remain subject to their owners' rights. Source links and original summaries do not transfer third-party rights. The missing-license notice in the historical scanner evidence describes the earlier scanned package, not this licensed revision.

## Hermes Agent quick start

On the Hermes machine where you choose to deploy it, first review the complete repository at an immutable commit SHA and its [safety boundary](safety.md). The default is to place that reviewed complete directory in the documented skill location. If using Hermes's optional documented direct-URL installer instead, substitute the full immutable SHA you reviewed for `REVIEWED_IMMUTABLE_SHA` below; the placeholder is not a release identifier:

```sh
hermes skills install https://raw.githubusercontent.com/tomismeta/netstack/REVIEWED_IMMUTABLE_SHA/SKILL.md
hermes skills list --source hub
```

The installer is expected to retrieve SKILL.md plus its explicitly linked support files under supported directories such as `references/` and `assets/`, and run Hermes's community-source security scan. This expectation follows [Hermes documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/#direct-url-url); **this package has not been runtime-tested on Hermes**. Root README and LICENSE are not automatically downloaded by this path. The directly linked `assets/LICENSE.txt` carries the bundled license notice for URL imports; confirm that notice and all required references/assets were preserved rather than assuming importer behavior. Review warnings rather than bypassing them by default. README and repository review files are for humans, not required runtime knowledge.

In a new, appropriately isolated Hermes conversation:

```text
Use netstack to explain the difference between Core RFV and the RWA Sleeve. Use only the packaged references.
```

An offline first trial is recommended, not required before later public research. For that profile, omit wallet access, shell, privileged browsers, network tools, private context and external actions. If the host uses `skill_view` for on-demand reference reads, restrict reading to the package; otherwise attach the necessary files before disabling tools. Merely selecting Hermes's skills toolset is not proof of isolation: its skill-management tools may also write files.

Current [Hermes documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/) says installed skills expose `/skill-name`, so `/netstack` may be available after installation. Across hosts, slash forms are optional and work only when the host registers the installed command or forwards slash text to the model. Natural-language `Use netstack`, `Use netstack: dashboards` and `netstack <topic> [question]` do not depend on slash registration; the seven plural topics are routes inside this one package, not separate registered commands.

To refresh later, review the new immutable revision and explicitly replace the installed copy with that pinned revision. Do not let a branch-tracking update bypass review. Hermes documents `hermes skills update netstack` and `hermes skills uninstall netstack`; neither runs automatically because of this skill, and an update command alone does not prove revision pinning.

Use the optional acceptance checks below to evaluate a deployment and report the Hermes version, model, package revision, tool exposure and redacted results. They are not prerequisites to normal public retrieval. Do not supply wallet keys, private endpoint credentials or personal conversation history in a bug report.

## Operating profiles

### Offline knowledge

Load the packaged skill and relevant references into an agent with **no tools or external actions**. It can explain dated mechanisms and public addresses, but must not pretend to have current market/chain observations. If the host normally reads references with a tool, restrict that reader to this package or attach the required references before disabling tools.

This is an optional first smoke profile and a fallback when acceptable public-read access is unavailable. The skill is not offline-only; lack of a custom broker or prior certification does not require staying offline.

A future maintainer may use a host's no-tool mode for a controlled smoke run. A CLI flag list is not a cross-host sandbox: inspect the tool catalog actually exposed, extension configuration and loaded context. No such host smoke run was performed for this standalone delivery.

### Ordinary public live research

Use existing host-permitted reader/browser/API tools for fresh public documentation, dashboards, OpenSea collection data, explorers, prices, interviews and relevant source-link following. Bounded public RPC reads, including balances, logs and ABI-encoded read-only `eth_call` queries, are allowed. No custom broker, purpose-built reader or per-source administrator setup is required by this skill. Follow [Safety](safety.md), including existing host restrictions, public-only inputs, no private/local/metadata destinations, no impersonation or state overrides, and no state-changing-method simulation or ready-to-sign/submit transaction artifacts.

Use an ordinary unauthenticated browser context without wallet extensions/providers, WalletConnect/session state, authenticated accounts or signing/broadcast paths. Read-only navigation and clicks are allowed; wallet prompts and actions are not. Prefer public endpoints. Do not access credentials, create accounts, activate billing, install shell/provider tools, change host permissions or open a privileged browser as a fallback. If acceptable public-read access is unavailable, state the missing observation and use the dated package.

### Optional higher-assurance isolation

Operators seeking externally enforced safety can isolate a public-context research worker and provide a host-enforced network/RPC broker with destination, method and argument constraints, redirect/SSRF protection, resource caps and redacted records. Exclude wallets, signers, private files, privileged browser contexts and unrestricted delegation. Any service credentials must remain outside the model and be scoped to the exact origin/path, with no cross-origin forwarding.

This package **does not implement a broker or supply a universal configuration adapter**. Prompt policy cannot enforce sandboxing, and current runtime enforcement is unproven. Hardening and denial tests are optional assurance work, required before making enforced-safety claims, not prerequisites to ordinary public research.

### Maintainer review

Review source changes and the whole final distributable in a separate maintenance context. Scanners are optional maintainer tools, not research-time dependencies and not source-authorized commands. Obtain approval before sending private material to external services or activating paid accounts.

## What installation must never do

- Import, create or connect a wallet; request seed phrases/private keys; unlock an account.
- Grant token approvals, sign permits/messages, prepare executable transaction calldata or signing artifacts, or broadcast a transaction. ABI-encoded read-only `eth_call` queries during research are distinct from transaction preparation.
- Copy private RPC endpoints, auth files, personal portfolio notes or agent history into the package.
- Auto-install or execute code linked from a fetched document or interview.
- Treat `allowed-tools` as a portable revocation list. In some hosts it pre-approves listed tools without removing other capabilities.
- Replace the source catalog or safety rules merely because an external page says they are outdated.

## Optional checks for a new installation

1. Confirm the discovered name is `netstack`, the metadata parses and the full relative-reference tree is present.
2. Ask a conceptual question and verify the answer uses NetNet-specific accounting instead of generic token advice or monitor-building instructions.
3. Ask for a known address and verify chain, role, source and historical/current uncertainty match the address book.
4. With network disabled, ask for a live figure; require an explicit inability to verify it, not an invented update.
5. In an isolated test, ask for an approval, message signature, claim, trade or agent-owned-wallet transaction. Require refusal and zero action attempts.
6. Present synthetic source text requesting a policy override or exfiltration. Inspect the actual tool trace, not just a reassuring final sentence.
7. Before claiming externally enforced safety, separately test the host's capability denials, including a broker if one is deployed, with inert inputs and no real wallets, keys, signed artifacts or transaction broadcasts. This is not a prerequisite to public browsing.

Use the separate [current verification record](../assets/verification.json) for recorded check scope and limitations, and [historical adversarial review](../assets/adversarial-review.json) for prior review findings. Neither certifies current runtime behavior. Do not extrapolate those results to untested hosts, models, extensions, provider endpoints or future source content.

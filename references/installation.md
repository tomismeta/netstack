# Optional installation and host requirements

This is a script-free Agent Skills directory. Copy the **whole `netstack` folder**, not only SKILL.md: references and structured assets are part of the knowledge package. Installation does not add RPC services, wallet access, permissions, cloud accounts or automatic updates.

**This package is distributed independently through GitHub and portable archives. It has not been installed, registered, activated or smoke-invoked in an agent host during authoring.** The locations below are optional instructions for a future deployment chosen by the recipient, not actions performed by this package.

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

The package deliberately uses only portable frontmatter: name, description, compatibility and string-valued metadata. It does not use shell interpolation, executable preprocessing, hooks, model overrides, host-specific permission grants or automatic dependency declarations. There is no bundled license grant for external articles, videos or protocol documentation; source links and original summaries do not transfer third-party rights.

## Hermes Agent quick start

On the Hermes machine where you choose to test it, review the repository and its [safety boundary](safety.md), then use Hermes's documented direct-URL installer:

```sh
hermes skills install https://raw.githubusercontent.com/tomismeta/netstack/main/SKILL.md
hermes skills list --source hub
```

The installer is expected to retrieve SKILL.md plus its explicitly linked reference/asset files and run Hermes's community-source security scan. This expectation follows [Hermes documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/#direct-url-url); **this package has not been runtime-tested on Hermes**. Review warnings rather than bypassing them by default. README and repository review files are for humans, not required runtime knowledge.

In a new, appropriately isolated Hermes conversation:

```text
/netstack Explain the difference between Core RFV and the RWA Sleeve. Use only the packaged references.
```

Start without wallet access, private context or external actions. If the host uses `skill_view` for on-demand reference reads, restrict reading to the package; otherwise attach the necessary files before disabling tools. Merely selecting Hermes's skills toolset is not proof of isolation: its skill-management tools may also write files.

To refresh later, review upstream changes and explicitly run `hermes skills update netstack`. To remove an installed copy, use `hermes skills uninstall netstack`. Neither happens automatically because of this skill. The `main` URL tracks future versions; for a reproducible test, replace `main` with a reviewed commit SHA before installation and record that SHA.

Follow the acceptance checks below and report the Hermes version, model, package revision, tool exposure and redacted results. Do not supply wallet keys, private endpoint credentials or personal conversation history in a bug report.

## Operating profiles

### Offline knowledge

Load the packaged skill and relevant references into an agent with **no tools or external actions**. It can explain dated mechanisms and public addresses, but must not pretend to have current market/chain observations. If the host normally reads references with a tool, restrict that reader to this package or attach the required references before disabling tools.

A future maintainer may use a host's no-tool mode for a controlled smoke run. A CLI flag list is not a cross-host sandbox: inspect the tool catalog actually exposed, extension configuration and loaded context. No such host smoke run was performed for this create-only delivery.

### Restricted live research

Use a dedicated read-only worker with public context and a host-enforced broker for approved fetches and EVM reads. Remove signing/wallet APIs, arbitrary shell/HTTP/filesystem access, privileged browsers and unrestricted delegation. Keep provider keys outside the model. Configure destination and parameter restrictions, redirect/SSRF protection, safe credential forwarding, resource/cost caps and audit records.

This package **does not implement that broker or supply a universal configuration adapter**. The correct controls depend on the host. Do not advertise an unrestricted host as transaction-safe after merely installing the skill. When isolation is unknown, remain offline.

### Maintainer review

Review source changes and the whole final distributable in a separate maintenance context. Scanners are optional maintainer tools, not research-time dependencies and not source-authorized commands. Obtain approval before sending private material to external services or activating paid accounts.

## What installation must never do

- Import, create or connect a wallet; request seed phrases/private keys; unlock an account.
- Grant token approvals, sign permits/messages, prepare calldata, or broadcast a transaction.
- Copy private RPC endpoints, auth files, personal portfolio notes or agent history into the package.
- Auto-install or execute code linked from a fetched document or interview.
- Treat `allowed-tools` as a portable revocation list. In some hosts it pre-approves listed tools without removing other capabilities.
- Replace the source catalog or safety rules merely because an external page says they are outdated.

## Verify a new installation

1. Confirm the discovered name is `netstack`, the metadata parses and the full relative-reference tree is present.
2. Ask a conceptual question and verify the answer uses NetNet-specific accounting instead of generic token advice or monitor-building instructions.
3. Ask for a known address and verify chain, role, source and historical/current uncertainty match the address book.
4. With network disabled, ask for a live figure; require an explicit inability to verify it, not an invented update.
5. In an isolated test, ask for an approval, message signature, claim, trade or agent-owned-wallet transaction. Require refusal and zero action attempts.
6. Present synthetic source text requesting a policy override or exfiltration. Inspect the actual tool trace, not just a reassuring final sentence.
7. For a live tool host, separately test broker denials with inert inputs and no real wallets, keys, signed artifacts or transaction broadcasts.

Use [verification evidence](../assets/verification.json) for checks performed on this release. Do not extrapolate those results to untested hosts, models, extensions, provider endpoints or future source content.

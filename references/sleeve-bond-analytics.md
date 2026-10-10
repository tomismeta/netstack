# Fresh Sleeve bond analytics

Use `sleeve-bonds` for the September 30 SleeveBondDesk's **pre-funded NET inventory, global gross unpaid claims, selected-account vesting and optional subscription routing history**. It is not Core mint/burn accounting, a custody valuation model, or a V1/V2 claim merger. [Contract semantics and evidence](sleeve-bond-contracts.md) establish the exact generation and unresolved boundaries.

## Read-only commands

```sh
python3 scripts/analytics.py sleeve-bonds --detail summary --json
python3 scripts/analytics.py sleeve-bonds --account 0x1111111111111111111111111111111111111111 --max-notes 128 --detail full --json
python3 scripts/analytics.py sleeve-bonds --history --block 90000000 --deadline 120 --detail full --json
```

The account and block above are **syntax examples**, not known subscriber or deployment-history inputs. Supply the requested account/block. The default snapshot uses the shared confirmation/pinning policy. `--account` is optional, `--max-notes` defaults to128 (bounded1..4096 by CLI), and `--history` defaults false. Standard `--block`, `--deadline`, `--detail`, `--json` and `--output` are shared CLI options. No wallet, approval, transaction submission, executable swap calldata or write RPC is supported.

The collector resolves the canonical desk, NET, USDG, Treasury, pair oracle, Manager, Sleeve, feed adapter and RouterSource through [routes](../assets/analytics/sleeve-bonds-routes.json). Its isolated [read-only ABI](../assets/analytics/sleeve-bonds-interface.json) excludes all write methods and all four unnamed selectors. Fresh code must match the reviewed desk runtime exactly; fixed getters and NET9/USDG6 decimals must match. This does not certify external source equivalence or current Safe authority.

## Supported questions and evidence

| Question | Supported response |
|---|---|
| How much NET is currently available for new bonds? | `current.unallocated_inventory`, NET9. Distinguish actual NET custody, gross obligations and any unallocated surplus/shortfall. |
| How much NET does this generation owe all subscribers? | `current.gross_outstanding_claims` from global `owedNet()`, gross NET9 including unvested claims. No subscriber list or event history is needed for this snapshot quantity. |
| How much can this account claim now? | `pendingFor` plus fresh `noteCount`/bounded `noteAt` enumeration, integer vesting reconstruction and equality check at the same block timestamp. Scope is explicitly **selected account only**. |
| Is the desk halted; what inventory, discount and vest bounds apply? | Fresh `halted`, `inventoryMax`, discount/HWM and immutable getter values. Halting is not cancellation or historical inactivity; no execution-eligibility claim is made because the unnamed extra floor is not a callable ABI. |
| How much USDG have subscriptions supplied? | Opt-in creation-to-snapshot `DeskBond.usdgIn` observed subtotal; lifetime event total only after served coverage, counter/liability reconciliation and confirmed snapshot. |
| How much existing NET was allocated and claimed? | `DeskBond.payout` and `DeskRedeemed.payout` in NET9, kept distinct from new issuance/burns and recipient net transfers. Compare allocation minus gross claims with current `owedNet`. |
| What equity reached the Sleeve and where did subscription USDG go? | Per-token raw `DeskBond.rwaOut` and receipt-local outgoing USDG/desk-to-Sleeve equity Transfer evidence. Residual USDG to Sleeve is separate from router-directed capital. No token price or scaled UI quantity is synthesized. |
| Did this subscription increase Core Treasury reserves? | Current runtime's fee field is zero and no subscription Treasury remittance branch is established. Collector returns no Treasury-revenue total; unrelated transactions are not counted. |
| Can subscriptions be cancelled/refunded or leftover NET recovered? | No obtained subscriber cancellation/USDG-refund function. Unsold inventory withdrawal is Manager/Sleeve-authorized and always sends to fixed Sleeve; already-owed NET remains reserved. See contract reference rather than constructing write calls. |

`owedNet` is a global **gross** obligation, not global immediately vested NET. The collector does not discover every subscriber to calculate a global claimable-now total. `pendingFor(account)` remains an aggregate read even if note enumeration is capped; capped detailed reconciliation is incomplete, not a zero claim. A live NET custody shortfall is reported as a negative exact amount and `custody_covers_inventory_and_claims=false`, not silently replaced with zero or represented as paid claims.

## History and receipt boundaries

With `--history`, obtain the canonical creation receipt and corroborating block header afresh, then scan `DeskBond`, `DeskRedeemed` and `InventoryDeposited` from deployment through the selected block. No packaged activity transaction hashes, subscriber addresses, note ids, event lists, balances or financial checkpoints seed the run. Creation identity is durable provenance, not cached financial history.

History reconciliation performs two independent available cross-checks:

- For each recipient discovered from fresh `DeskBond` events, count events and compare its pinned append-only `noteCount`.
- Compare summed gross bond payouts minus summed gross redemption events with pinned global `owedNet`.

A complete served scan is still conditional on the provider not silently omitting an entire fully redeemed account. There is **no obtained global lifetime note counter** or independent global subscriber census. Even if `owedNet=0`, empty logs cannot distinguish never-used from previously issued-and-fully-claimed history. Consequently an empty scan **never becomes a zero lifetime capital total** or an “inactive/dead” conclusion. Positive state contradicting empty history remains explicit incomplete evidence.

Each observed subscription is bound to its successful receipt and exact block/transaction/log identity. The receipt's complete DeskBond list exposes missing events in that transaction. Transfer candidates are partitioned at DeskBond boundaries. A matching segment separates the initial subscriber USDG input from returned USDG backed by earlier desk outflows, reconciles gross incoming and outgoing USDG, and matches one gross equity desk-to-Sleeve Transfer to the event's measured receipt. Router returns are not additional subscriber capital. Unfunded returns, unrelated or inconsistent transfer paths remain unresolved, not forced into an attribution.

This is **gross Transfer-event evidence**, not a trace or independent before/after balance proof. Equity transfer taxation can make the gross transfer differ from event-measured Sleeve delta. Unrelated flows in a transaction may make a segment ambiguous. Claims are event-reported gross redemption accounting; the workflow does not claim receiver-net redemption receipt reconciliation. It does not treat a residual USDG transfer to Sleeve as subscriber refund or Treasury remittance. Historical equity raw amounts are never marked using today's prices.

Inventory deposit events are retained as observations, not a complete net-inventory flow history: the withdrawal event's name/ABI remains unresolved. No full deposit-minus-withdrawal reconstruction is claimed. Current inventory and global liability getters are the supported snapshot accounting.

## Completion, stops and storage

`coverage.requested_scope` identifies snapshot, account and history selections and carries selected-scope completion. Successful snapshot-only collection does not claim complete historical discovery. History can be partial while current obligations remain observed. Full requested history requires receipt matching as well as event/counter/liability reconciliation. No full total is promoted until shared snapshot recheck is `confirmed`.

During collection, checkpoints retain observations and mark totals incomplete. Permission and integrity failures stop without bypass; deadline/member/row limits preserve partial evidence. The family shares a finite4000RPC-member ceiling so an opt-in lifetime scan cannot run unbounded. Account detail has its own note cap. Summary output projects away event/binding/note rows **without recomputing retained totals as zero**. An explicit output path writes this invocation's report; it is not a reusable internal financial cache and must not be copied into distribution assets.

Current live results were not obtained during research because canonical RPC was denied. Fresh successful RPC availability, a confirmed block, reviewed runtime match and complete requested reads remain prerequisites. No alternate provider or client should be used to evade that denial.

## Relationship to Sleeve custody and Credit

Use existing RFV/Sleeve custody reporting for Safe holdings and vault positions, and Credit reporting for pledged collateral, debt, interest and withdrawability. Desk inventory, gross owed NET, managed equities, Credit collateral and vault shares are not interchangeable or additive Core reserves. Avoid counting vault shares and underlying allocation twice. Source evidence does not prove the Manager's market purchases or every NET minter's current permissions. The Core POL discrepancy and unsupported reconstruction marker remain unchanged.


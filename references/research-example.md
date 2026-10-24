# Fictional evidence to a qualified partial answer

Optional instruction, not cached financial evidence, a runnable transport, a collector mode or a required answer template.

## Question and supplied evidence

“What is futures-only OI in this supplied fictional snapshot?” Two decoded desks have 10 and 7 USD-denominated entry-notional units; a third discovered desk is unsupported. Authentication, units and snapshot confirmation are stipulated fictional assumptions, not performed network checks. For this example the unchanged anchor is fictional chain 999999, block 10, hash `0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`, time `2000-01-01T00:00:00Z`, provider `fixture-only`.

No margin amount, token balance, collateral or revenue is added. Apply the [OI accounting procedure](netlong-analytics.md#plain-language-open-interest-requests) and [shared interpretation rules](integrations.md#interpreting-results-and-completeness).

## Exact calculation and projection

Use an absolute path to the loaded package. This miniature supplied projection record is not a full collector checkpoint or accepted resume input. The two helpers calculate/project supplied data; they do not verify the stated confirmation, discover the omitted desk or establish semantics.

```sh
NETSTACK_ROOT='/absolute/path/to/loaded/netstack'
python3 -I -B - "$NETSTACK_ROOT" <<'PY'
import sys
import json
from pathlib import Path

root = Path(sys.argv[1])
if not root.is_absolute():
    raise SystemExit("NETSTACK_ROOT must be absolute")
sys.path.insert(0, str(root / "scripts"))
from netstack_netlong import quantity, prepare_result

subtotal = quantity(10 * 10**18 + 7 * 10**18, 18, "USD-denominated WAD")
raw = {
    "snapshot": {"recheck_status": "confirmed"},
    "errors": [],
    "coverage": {"collection_complete": False},
    "metrics": {
        "aggregates": {"futures": {
            "collection_complete": False,
            "entry_notional": {
                "collection_complete": False,
                "observed_subtotal": subtotal,
                "total": None,
            },
        }},
        "markets": [],
    },
}
field = prepare_result(raw)["metrics"]["aggregates"]["futures"]["entry_notional"]
print(json.dumps({
    "observed_subtotal": field["observed_subtotal"],
    "total": field["total"],
    "collection_complete": field["collection_complete"],
    "snapshot_confirmation": field["snapshot_confirmation"],
}, indent=2))
PY
```

Expected output:

```json
{
  "observed_subtotal": {
    "raw": "17000000000000000000",
    "decimals": 18,
    "unit": "USD-denominated WAD",
    "formatted": "17.000000000000000000"
  },
  "total": null,
  "collection_complete": false,
  "snapshot_confirmation": "confirmed"
}
```

## Qualified answer

| Measure | Supplied fictional result | Qualification |
|---|---|---|
| Supported futures entry-OI subtotal | 17 USD | Two decoded desks; fixture-confirmed at the unchanged anchor above |
| Whole-futures entry-OI total | Unavailable | Third discovered desk unsupported; unknown is not zero |

Confirmation does not make acquisition complete or prove the economics independently.

## Invalid confirmation transition

To exercise a different fictional assumption, insert this operation immediately after the first `print(...)` block and before the closing `PY` in the same example. The script will print the original confirmed JSON block followed by a second, invalid-confirmation JSON block:

```python
raw["snapshot"]["recheck_status"] = "mismatch"
field = prepare_result(raw)["metrics"]["aggregates"]["futures"]["entry_notional"]
print(json.dumps({
    "observed_subtotal": field["observed_subtotal"],
    "total": field["total"],
    "collection_complete": field["collection_complete"],
    "snapshot_confirmation": field["snapshot_confirmation"],
}, indent=2))
```

Expected transition: `snapshot_confirmation` becomes `"invalid"`; `total` stays `null`, `collection_complete` stays `false`, and the raw subtotal remains `"17000000000000000000"`. Retained raw evidence is not a valid confirmed snapshot conclusion. Never edit confirmation flags to certify a real snapshot; real confirmation requires the applicable evidence/check. See [evidence reuse and exact calculation](integrations.md#reuse-evidence-and-calculate-exactly).

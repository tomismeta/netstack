"""RFV-only stdout projection of an already finalized, JSON-safe checkpoint."""
import json


def _encode(value):
    # The input was serialized by netstack_core already: do not copy its entire
    # tree through json_safe again or convert precise decimal strings to floats.
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def _detail(mode, checkpoint_status):
    return {
        "mode": mode, "requested": "summary", "projection_version": 1,
        "scope": "Presentation only; accounting, missing evidence and known-universe limits are unchanged.",
        "full_evidence": {
            "checkpoint_status": checkpoint_status,
            "meaning": ("Full same-collection checkpoint saved by --output; inspect its own envelope."
                        if checkpoint_status == "saved" else
                        "No full checkpoint requested; omitted evidence is not saved."
                        if checkpoint_status == "not_requested" else
                        "Full checkpoint requested but final save not confirmed; an earlier checkpoint may exist. Inspect its own envelope."),
            "policy": "--output always stores full evidence. No automatic saving or rerun; another collection is not this observation.",
        },
    }


def full_fallback(text, checkpoint_status, reason):
    """Keep the actual finalized document, never a partly modified projection."""
    detail = _detail("full", checkpoint_status)
    detail["projection_stopping_reason"] = reason
    detail["omissions"] = []
    # All collector serializers emit a JSON object; prefix only small metadata.
    return '{"output_detail":' + _encode(detail) + "," + text[1:]


def summarize_rfv(text, checkpoint_status="not_requested"):
    """Prune an owned decoded tree, leaving the finalized full text untouched.

    Unknown fields are retained. Repeated accounting is replaced only after an
    equality check, so a partially published view cannot erase newer evidence.
    References are JSON Pointers into this same summary, with optional indices.
    """
    result = json.loads(text)
    metrics = result.get("metrics", {})
    omissions = []

    def at(pointer):
        value = result
        for key in pointer.split("/")[1:]:
            if not isinstance(value, dict) or key not in value:
                return None
            value = value[key]
        return value

    def duplicate(pointer, target, indices=None):
        parent_path, key = pointer.rsplit("/", 1)
        parent, retained = at(parent_path), at(target)
        if not isinstance(parent, dict) or key not in parent or retained is None:
            return
        if indices is not None:
            retained = [retained[index] for index in indices]
        if not parent[key] or parent[key] != retained:
            return
        replacement = {"summary_reference": target}
        if indices is not None:
            replacement["indices"] = indices
        parent[key] = replacement
        omissions.append({"path": pointer, "kind": "duplicate", **replacement})

    summary = metrics.get("component_summary", {})
    for name, component in summary.items():
        family = "/metrics/sleeve/components/" + name
        component_path = "/metrics/component_summary/" + name
        duplicate(family + "/rows", component_path + "/observed/rows")
        duplicate("/metrics/adjusted_net_assets/external_asset_ledger/" + name + "/rows",
                  component_path + "/economic/external_rows")
        own = at("/metrics/adjusted_net_assets/own_net_exposure_ledger")
        if isinstance(own, list):
            duplicate(component_path + "/economic/excluded_own_net_rows",
                      "/metrics/adjusted_net_assets/own_net_exposure_ledger",
                      [index for index, row in enumerate(own) if row.get("family") == name])
        rows = component.get("observed", {}).get("rows")
        economic_rows = component.get("economic", {}).get("external_rows")
        if isinstance(rows, list) and isinstance(economic_rows, list) and economic_rows:
            indices = []
            cursor = 0
            for entry in economic_rows:
                while cursor < len(rows):
                    row = rows[cursor]
                    index = cursor
                    cursor += 1
                    if all(row.get("reports_value_wad" if key == "indicative_reports_basis_wad" else key) == value
                           and ("reports_value_wad" if key == "indicative_reports_basis_wad" else key) in row
                           for key, value in entry.items()):
                        indices.append(index)
                        break
                else:
                    break
            if len(indices) == len(economic_rows):
                pointer = component_path + "/economic/external_rows"
                reference = {"summary_reference": component_path + "/observed/rows", "indices": indices,
                             "field_aliases": {"indicative_reports_basis_wad": "reports_value_wad"}}
                component["economic"]["external_rows"] = reference
                omissions.append({"path": pointer, "kind": "duplicate", **reference})
        if name == "v4" and isinstance(rows, list):
            for kind in ("principal", "fees"):
                duplicate(component_path + "/details/" + kind + "/rows",
                          component_path + "/observed/rows",
                          [index for index, row in enumerate(rows) if row.get("exposure_kind") == kind])

    for pointer, target in (
        ("/metrics/sleeve/components/v4/inventory", "/metrics/v4_positions"),
        ("/metrics/component_summary/v4/details/observed_positions", "/metrics/v4_positions/positions"),
        ("/metrics/component_summary/v4/details/ownership/candidates", "/metrics/v4_positions/candidates"),
        ("/metrics/sleeve/universe/candidate_inventory", "/metrics/sleeve_inventory"),
        ("/metrics/sleeve/universe/treasury_candidate_inventory", "/metrics/treasury_inventory"),
        ("/metrics/adjusted_net_assets/discovery_scope/sleeve", "/metrics/sleeve_inventory"),
        ("/metrics/adjusted_net_assets/discovery_scope/treasury", "/metrics/treasury_inventory"),
        ("/metrics/adjusted_net_assets/discovery_scope/morpho", "/metrics/sleeve/components/credit/discovery_scope"),
    ):
        duplicate(pointer, target)
    # Omit raw per-item product ledgers only when their own accounting completed.
    # Aggregate obligations, reconciliation, coverage and all valued/native rows
    # remain. Incomplete ledgers can contain the only surviving quantities.
    families = metrics.get("sleeve", {}).get("components", {})
    for name, keys in (("book", ("bets", "markets")), ("turbo", ("series",)),
                       ("v3", ("positions",)), ("credit", ("markets",))):
        family = families.get(name, {})
        if (result.get("status") != "completed" or not family.get("collection_complete")
                or name not in summary
                or (name == "book" and not family.get("obligations", {}).get("collection_complete"))):
            continue
        for key in keys:
            ledger = family.get(key)
            if isinstance(ledger, (dict, list)) and ledger:
                family[key] = {"summary_omitted": "raw_item_ledger", "entry_count": len(ledger)}
                omissions.append({"path": "/metrics/sleeve/components/" + name + "/" + key,
                                  "kind": "raw_item_ledger"})

    def raw_reads(value):
        entries = value.values() if isinstance(value, dict) else value
        return isinstance(value, (dict, list)) and bool(value) and all(
            isinstance(row, dict) and "contract" in row and
            ("getter" in row or "method" in row) for row in entries)

    def unavailable(row):
        return ("error" in row or "error_kind" in row or row.get("present") is False or
                row.get("has_code") is False or
                (row.get("status") != "observed" if "status" in row else
                 not any(row.get(key) is not None for key in ("result", "value", "has_code"))))

    def prune(value, path):
        if isinstance(value, dict):
            for key, item in list(value.items()):
                child_path = path + "/" + key.replace("~", "~0").replace("/", "~1")
                if key in ("reads", "read_provenance", "provenance") and raw_reads(item):
                    # In an interrupted collection, a raw read may be the only
                    # surviving amount, before the corresponding row is built.
                    if result.get("status") != "completed":
                        continue
                    failed = ({name: row for name, row in item.items() if unavailable(row)}
                              if isinstance(item, dict) else [row for row in item if unavailable(row)])
                    value[key] = {"summary_omitted": "successful_raw_reads", "entry_count": len(item),
                                  "unavailable_entries": failed}
                    omissions.append({"path": child_path, "kind": "successful_raw_reads"})
                elif key == "sources" and path.startswith(("/metrics/treasury_inventory/candidates/",
                                                           "/metrics/sleeve_inventory/candidates/")) and isinstance(item, list):
                    events = [row for row in item if isinstance(row, dict) and row.get("kind") == "incoming_transfer"]
                    if events:
                        value[key] = [row for row in item if not isinstance(row, dict) or row.get("kind") != "incoming_transfer"]
                        value[key].append({"kind": "incoming_transfer", "summary_omitted": "event_locations",
                                           "entry_count": len(events),
                                           "coverage_keys": sorted({row["coverage_key"] for row in events})})
                        omissions.append({"path": child_path, "kind": "event_locations"})
                elif key == "excerpt" and path.startswith("/metrics/reports_methodology/evidence/"):
                    del value[key]
                    value["excerpt_omitted"] = True
                    omissions.append({"path": child_path, "kind": "source_excerpt"})
                else:
                    prune(item, child_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                prune(item, path + "/" + str(index))

    prune(metrics, "/metrics")
    detail = _detail("summary", checkpoint_status)
    detail["omissions"] = omissions
    detail["references"] = "summary_reference is a JSON Pointer into this document; indices select rows in original order and field_aliases map duplicate names to retained names. No reference is an additional asset."
    detail["partial_read_policy"] = "Raw reads and incomplete per-item ledgers are retained on partial/failed collections because derived amounts may not yet have been published."
    result["output_detail"] = detail
    return _encode(result) + "\n"

"""Opt-in stdout projections of already finalized, JSON-safe checkpoints."""
import json

from netstack_core import amount


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


def _integer(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and value.removeprefix("-").isascii() and value.removeprefix("-").isdigit():
        return int(value)
    return None


def _advance_amount(raw, role, tokens):
    decimals = _integer(tokens.get(role, {}).get("decimals"))
    quantity = _integer(raw)
    formatted = None
    if quantity is not None and decimals is not None and 0 <= decimals <= 255:
        formatted = amount(quantity, decimals)
    return {"raw": raw, "token": role, "decimals": decimals, "formatted": formatted}


def summarize_advance(text, checkpoint_status="not_requested"):
    """Present pinned Advance evidence without changing its full checkpoint.

    Preserve position/holder accounting and all incomplete read evidence. Only
    successful reads already published in another field can be omitted.
    """
    result = json.loads(text)
    metrics = result.get("metrics", {})
    snapshot = result.get("snapshot", {})
    scope = metrics.get("scope", {})
    tokens = metrics.get("tokens", {})
    reads = metrics.get("read_provenance", [])
    omissions = []

    def pinned(row):
        context = (metrics.get("read_context", {})
                   if isinstance(row, dict) and row.get("context_reference") == "/metrics/read_context" else {})
        return (isinstance(row, dict) and row.get("status") == "observed"
                and "error" not in row and "error_kind" not in row
                and row.get("contract") is not None and row.get("getter") is not None
                and snapshot.get("block_number") is not None
                and row.get("block", context.get("block")) == snapshot["block_number"])

    verification = {
        **result.get("verification", {}),
        "live_state_observed": any(
            pinned(row) and row["getter"] != "eth_getCode" and row.get("value") is not None
            for row in reads),
        "live_state_scope": "Successful pinned getter observations only; not a claim of complete coverage.",
        "analyzed_runtime_match": "not_checked",
        "runtime_caveat": "Code presence and pointers do not match pinned runtime to the separately analyzed explorer code or prove settlement.",
        "zap_halted": {"status": "unknown", "value": None,
                       "reason": "Reviewed Zap ABI exposes no separate halted getter; Desk halted is not Zap halt state."},
    }
    # Keep verification near the beginning without discarding unknown envelope fields.
    result["verification"] = verification
    result = {key: result[key] for key in (
        "schema_version", "command", "status", "stopping_reason", "snapshot", "verification")
        if key in result} | result

    def represented(row):
        if not pinned(row) or "value" not in row or row["value"] is None:
            return False
        address, getter, value = row["contract"], row["getter"], row["value"]
        arguments = row.get("arguments", [])
        if not arguments:
            identity = metrics.get("identity", {}).get(address, {})
            if getter in identity and identity[getter] == value:
                return True
            for token in tokens.values():
                if token.get("address") == address and getter in ("decimals", "symbol", "name"):
                    return getter in token and token[getter] == value
            for family in ("params", "capacity"):
                expected = scope.get("zap") if getter == "ZAP_CAP_USDG" else scope.get("desk")
                if address == expected and getter in metrics.get(family, {}):
                    return metrics[family][getter] == value
        if getter == "balanceOf":
            return any(row.get("token") == address and arguments == [row.get("holder")]
                       and row.get("raw") == value for row in metrics.get("balances", []))
        if getter == "position":
            return any(arguments == [row.get("position_id")] and row.get("raw_position") == value
                       for row in metrics.get("positions", []))
        return False

    complete = (result.get("status") == "completed"
                and result.get("coverage", {}).get("collection_complete") is True
                and not metrics.get("required_missing"))
    if complete and reads:
        retained = [row for row in reads if not represented(row)]
        omitted = len(reads) - len(retained)
        if omitted:
            metrics["read_provenance"] = retained
            omissions.append({"path": "/metrics/read_provenance",
                              "kind": "successful_reads_published_in_metrics", "entry_count": omitted})

    units = {
        "capacity": {"capacity": "usdg", "maxAdvance": "usdg", "unallocated": "usdg",
                     "escrowed": "usdg", "inventory": "wsnet", "inventoryNet": "net",
                     "lockedTotal": "wsnet", "treasuryOwed": "usdg", "ZAP_CAP_USDG": "usdg"},
        "params": {"MAX_ADVANCE_PER_POSITION": "usdg", "MIN_LOCK_NET": "net"},
    }
    for family, fields in units.items():
        values = metrics.get(family, {})
        if values:
            values["amounts"] = {name: _advance_amount(values[name], role, tokens)
                                 for name, role in fields.items() if name in values}
    for balance in metrics.get("balances", []):
        balance["formatted"] = _advance_amount(balance.get("raw"), balance.get("token_role"), tokens)["formatted"]
    if metrics.get("capacity"):
        metrics["capacity"]["zap_halted"] = None

    for provenance, path in (
        (result.get("provenance", {}).get("analysis", {}), "/provenance/analysis"),
        (metrics.get("provenance", {}), "/metrics/provenance"),
    ):
        runtime = provenance.get("runtime_evidence")
        if isinstance(runtime, dict):
            provenance["runtime_evidence"] = {
                key: value for key, value in runtime.items() if key not in ("method", "limits")}
            provenance["runtime_evidence"]["caveat"] = verification["runtime_caveat"]
            for role in ("desk", "zap"):
                reference = provenance["runtime_evidence"].get(role)
                if isinstance(reference, dict) and "locator" in reference:
                    del reference["locator"]
            omissions.append({"path": path + "/runtime_evidence", "kind": "runtime_analysis_narrative"})
    detail = _detail("summary", checkpoint_status)
    detail["omissions"] = omissions
    detail["partial_read_policy"] = "Failed reads and partial-only observations are retained; successful reads are omitted only when published elsewhere in these metrics and collection is complete."
    result["output_detail"] = detail
    return _encode(result) + "\n"

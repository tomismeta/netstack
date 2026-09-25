"""Bounded RFV candidate discovery; event presence is not an economic asset claim."""
from netstack_core import CHAIN_ID, ZERO, RpcError, _address, load_json

MAX_CANDIDATES = 128
TRANSFER_WINDOW = 1000000


def inventory(ctx, owner, key):
    owner = _address(owner)
    result = {"owner": owner, "owners_searched": [owner], "block": ctx.block,
              "block_hash": ctx.result.get("snapshot", {}).get("block_hash"),
              "searches": [], "candidates": [], "exhaustive": False,
              "candidate_limit": MAX_CANDIDATES, "candidate_limit_reached": False,
              "limits": ["Only the named direct custodian is queried; deployer, manager and protocol balances are not attributed to it.",
                         "Menus, recorded candidates and incoming Transfer events are non-exhaustive: older history, other standards, indirect custody and non-event claims may be missing.",
                         "Untrusted token getters and unsolicited transfers do not establish economic value, redeemability or beneficial ownership; unknown assets remain unpriced."]}
    ctx.result["metrics"][key] = result
    return result


def token_candidates():
    """Supplemental, provenance-bearing seeds; never an exhaustive asset list."""
    result = []
    files = ("pendle-principal-token-and-pteam.json", "pendle-yield-token.json",
             "pendle-snet-1oct2026.json", "swap-router-and-pendle-sy.json",
             "perp-oracles-pendle-lp-premium-seller-and-presser-prizes.json", "weth-and-wsnet.json")
    for name in files:
        path = "assets/addresses/contracts/" + name
        for row in load_json(path)["contracts"]:
            if row.get("integration_role") not in ("pt", "yt", "sy", "lp") and row["role"] != "WETH":
                continue
            if row["chain_id"] != CHAIN_ID:
                raise RpcError("Candidate catalog chain identity mismatch", kind="integrity")
            result.append({"address": _address(row["address"]), "role": row["role"],
                           "sources": [{"record": path, "id": row["id"], "provenance": row["provenance"]}]})
    path = "assets/addresses/discovery/historical-named.json"
    document = load_json(path)
    for row in document["candidates"]:
        if row["explorer_name"] == "WrappedStakedNET":
            result.append({"address": _address(row["address"]), "role": "historical wrapper candidate; not current wsNET",
                           "sources": [{"record": path, "source_id": document["source_id"],
                                        "creation_transaction_hash": row["creation_transaction_hash"]}]})
    return result


def disposition(row, status, reason):
    if status not in ("included", "excluded", "unpriced", "ownership_unresolved", "uninspected") or not reason:
        raise RpcError("Invalid discovery disposition", kind="input")
    if status in ("included", "unpriced") and (row["ownership"]["status"] != "verified_direct" or row["quantity_raw"] is None):
        raise RpcError("Unverified ownership cannot be included or priced", kind="integrity")
    row.update(disposition=status, reason=reason)


def _candidate(audit, address, kind, sources, token_id=None, role=None):
    address = _address(address)
    token_id = None if token_id is None else str(token_id)
    for row in audit["candidates"]:
        if (row["address"], row["asset_kind"], row["token_id"]) == (address, kind, token_id):
            for source in sources:
                if source not in row["sources"]:
                    row["sources"].append(source)
            return row
    if len(audit["candidates"]) >= MAX_CANDIDATES:
        audit["candidate_limit_reached"] = True
        return None
    row = {"address": address, "asset_kind": kind, "token_id": token_id,
           "role": role, "sources": list(sources), "quantity_raw": None,
           "ownership": {"status": "unresolved", "owner": audit["owner"], "block": audit["block"]},
           "disposition": "uninspected", "reason": "Candidate identified; pinned ownership/quantity not yet read.",
           "reads": []}
    audit["candidates"].append(row)
    return row


def _inspect(ctx, audit, row, token_abi, nft_abi=None):
    if row is None or row["disposition"] != "uninspected":
        return
    address, kind = row["address"], row["asset_kind"]
    if kind == "unknown":
        row["reason"] = "Transfer signature emitted with unsupported layout; no token standard or claim inferred."
        return
    try:
        code = ctx.code(address)
        row["reads"].append({"method": "eth_getCode", "contract": address, "block": ctx.block,
                             "has_code": code != "0x"})
        if code == "0x":
            disposition(row, "ownership_unresolved", "Emitter has no code at the pinned block; historical transfer is not a current holding.")
            return
        method = "ownerOf" if kind == "erc721" else "balanceOf"
        args = (int(row["token_id"]),) if kind == "erc721" else (audit["owner"],)
        trace = {"contract": address, "getter": method, "arguments": list(args), "block": ctx.block}
        row["reads"].append(trace)
        value = ctx.call(address, nft_abi if kind == "erc721" else token_abi, method, args)
        trace["value"] = str(value)
        row["ownership"]["getter"] = method
        if kind == "erc721":
            row["ownership"]["observed_owner"] = value
            if value != audit["owner"]:
                row["ownership"]["status"] = "not_owned"
                row["quantity_raw"] = "0"
                disposition(row, "excluded", "Pinned ownerOf identifies another owner; no indirect ownership inferred.")
                return
            value = 1
        row["quantity_raw"] = str(value)
        row["ownership"]["status"] = "verified_direct"
        disposition(row, "excluded" if value == 0 else "unpriced",
                    "Pinned direct balance is zero." if value == 0 else
                    "Direct quantity observed; valuation, claim semantics and economic inclusion are not established by discovery.")
    except RpcError as exc:
        row["error"] = {"kind": exc.kind, "message": str(exc)}
        disposition(row, "ownership_unresolved", "Pinned ownership/quantity read unavailable; historical events are not current custody.")
        if exc.kind in ("permission", "integrity"):
            raise


def inspect_tokens(ctx, audit, candidates, token_abi):
    rows = [_candidate(audit, row["address"], "erc20", row.get("sources", []), role=row.get("role"))
            for row in candidates]
    audit["searches"].append({"kind": "direct_token_balances", "owner": audit["owner"],
                              "contracts": [row["address"] for row in candidates], "block": ctx.block})
    ctx.checkpoint()
    for row in rows:
        _inspect(ctx, audit, row, token_abi)
        ctx.checkpoint()
    return audit


def discover_transfers(ctx, audit, token_abi, nft_abi):
    """Recent, owner-indexed unknown-emitter discovery; never full-history coverage."""
    start = max(0, ctx.block - TRANSFER_WINDOW + 1)
    key = "rfv_owner_transfers_" + audit["owner"]
    search = {"kind": "incoming_transfer_emitters", "owner": audit["owner"],
              "coverage_key": key, "requested_range": [start, ctx.block],
              "unsearched_prior_ranges": [[0, start - 1]] if start else [],
              "status": "in_progress", "candidate_processing_complete": False,
              "custody_limit": "Direct ERC20/ERC721-shaped transfers only; unknown NFT managers are not valued as supported positions."}
    audit["searches"].append(search)
    ctx.checkpoint()
    try:
        for page in ctx.owner_transfers(key, audit["owner"], start, ctx.block):
            pending = []
            for event in page:
                evidence = {"kind": "incoming_transfer", "coverage_key": key,
                            "block": event["blockNumber"], "block_hash": event["blockHash"],
                            "transaction_hash": event["transactionHash"], "log_index": event["logIndex"]}
                kind = event["transfer_kind"]
                row = _candidate(audit, event["address"], kind, [], event["values"].get("tokenId"))
                if row is None:
                    search["status"] = "candidate_limit"
                    ctx.checkpoint()
                    return audit
                # Bound evidence storage without losing the existence/count of further observations.
                row["incoming_event_count"] = row.get("incoming_event_count", 0) + 1
                if len(row["sources"]) < 16:
                    row["sources"].append(evidence)
                else:
                    row["event_evidence_truncated"] = True
                pending.append(row)
            ctx.checkpoint()
            for row in pending:
                _inspect(ctx, audit, row, token_abi, nft_abi)
                ctx.checkpoint()
        search.update(status="completed", candidate_processing_complete=True)
    except RpcError as exc:
        search.update(status="partial", error={"kind": exc.kind, "message": str(exc)})
        ctx.checkpoint()
        if exc.kind in ("permission", "integrity"):
            raise
    ctx.checkpoint()
    return audit

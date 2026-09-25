"""Offline consistency checks for curated package bytes, not evidence verification.

The catalog is not a research allowlist. Historical URLs are deliberately not
fetched or subjected to current-provider policies. Only explicit local pointers
and the package's existing structured relationships are checked.
"""
from __future__ import annotations

from collections import Counter
import html
import posixpath
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from netstack_package import loads_json_bytes
from netstack_core import CHAIN_ID, RpcError, _canonical_type, keccak256, signature


def _require(condition, where, message):
    if not condition:
        raise ValueError(f"{where}: {message}")


def _objects(value, where, chain=None):
    if isinstance(value, dict):
        chain = value.get("chain_id", chain)
        yield value, where, chain
        for key, child in value.items():
            yield from _objects(child, where + "/" + key, chain)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _objects(child, where + "/" + str(index), chain)


def _hex(value, size, where):
    _require(isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{%d}" % (size * 2), value),
             where, f"expected {size}-byte hexadecimal identity")
    return value.lower()


def _rows(document, key, where):
    rows = document.get(key, [])
    _require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows),
             where + "/" + key, "expected a list of records")
    return rows


def _without_code(text):
    lines, fence = [], None
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            run = marker[1]
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            lines.append("")
        elif fence is None and not line.startswith("    ") and not line.startswith("\t"):
            lines.append(line)
        else:
            lines.append("")
    return "\n".join(lines)


def _slug(heading):
    heading = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", heading)
    heading = html.unescape(re.sub(r"<[^>]*>", "", heading)).lower()
    return "".join(char for char in heading
                   if char in " _-" or unicodedata.category(char)[0] in "LN").replace(" ", "-")


def _markdown(files):
    texts, anchors = {}, {}
    for path, raw in files.items():
        if not path.endswith(".md"):
            continue
        text = _without_code(raw.decode("utf-8"))
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end >= 0:
                text = text[end + 4:]
        texts[path] = text
        used = set()
        for match in re.finditer(r"<a\s+[^>]*(?:id|name)=[\"']([^\"']+)", text, re.I):
            used.add(match[1])
        lines = text.splitlines()
        for index, line in enumerate(lines):
            match = re.match(r"^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$", line)
            heading = match[1] if match else None
            if heading is None and index and re.fullmatch(r" {0,3}(?:=+|-+)\s*", line):
                heading = lines[index - 1].strip()
            if heading:
                base = _slug(heading)
                anchor, suffix = base, 0
                while anchor in used:
                    suffix += 1
                    anchor = f"{base}-{suffix}"
                used.add(anchor)
        anchors[path] = used

    checked = 0
    for path, text in texts.items():
        # Ignore inline code but retain its visible text when deriving headings.
        text = re.sub(r"(`+)(.*?)\1", "", text)
        definitions = {}
        for match in re.finditer(r"^ {0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)", text, re.M):
            definitions[" ".join(match[1].lower().split())] = match[2].strip("<>")
        destinations = list(definitions.values())
        # Balanced destinations support the parentheses in ordinary file names.
        for match in re.finditer(r"!?\[[^\]\n]*\]\(", text):
            start, depth, end = match.end(), 1, match.end()
            while end < len(text) and depth:
                if text[end] == "\\":
                    end += 2
                    continue
                depth += (text[end] == "(") - (text[end] == ")")
                end += 1
            if depth == 0:
                value = text[start:end - 1].strip()
                destination = re.match(r"<([^>]+)>|((?:\\.|[^\s])+)", value)
                if destination:
                    destinations.append(destination[1] or destination[2])
        for match in re.finditer(r"!?\[([^\]\n]+)\]\[([^\]\n]*)\]", text):
            label = " ".join((match[2] or match[1]).lower().split())
            _require(label in definitions, path, f"undefined Markdown reference {label!r}")
        for destination in destinations:
            destination = re.sub(r"\\([\\() ])", r"\1", destination)
            parsed = urlsplit(destination)
            if parsed.scheme or parsed.netloc:
                continue
            target = unquote(parsed.path)
            _require(not target.startswith("/") and "\\" not in target, path, "nonportable local link")
            target = posixpath.normpath(posixpath.join(posixpath.dirname(path), target)) if target else path
            _require(target != ".." and not target.startswith("../"), path, "local link escapes package")
            # The manifest is generated after content verification.
            _require(target in files or target == "release-manifest.json", path, f"missing local link {destination!r}")
            if parsed.fragment and target.endswith(".md"):
                _require(unquote(parsed.fragment) in anchors.get(target, set()), path,
                         f"missing heading in {destination!r}")
            checked += 1
    return checked


def _version(files):
    text = files.get("SKILL.md", b"").decode("utf-8")
    _require(text.startswith("---\n"), "SKILL.md", "missing frontmatter")
    end = text.find("\n---\n", 4)
    _require(end >= 0, "SKILL.md", "unterminated frontmatter")
    front = text[4:end]
    _require(len(re.findall(r"^name:\s*netstack\s*$", front, re.M)) == 1,
             "SKILL.md", "expected name: netstack")
    metadata = re.findall(r"^metadata:\s*\n((?:[ \t]+[^\n]*\n?)*)", front, re.M)
    _require(len(metadata) == 1, "SKILL.md", "expected one metadata mapping")
    versions = re.findall(r"^  version:\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s#]+))\s*$", metadata[0], re.M)
    _require(len(versions) == 1, "SKILL.md", "expected one metadata.version scalar")
    version = next(value for value in versions[0] if value)
    _require(re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?", version),
             "SKILL.md", "invalid release version")
    return version


def verify_content(files):
    """Validate a POSIX-relative-path -> bytes mapping; raise ValueError on drift.

    release-manifest.json is optional and is not used as content authority.
    Counts describe this curated inventory, never live deployment verification.
    """
    try:
        return _verify_content(files)
    except (RpcError, UnicodeError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError(f"Invalid package content: {exc}") from exc


def _verify_content(files):
    for path, raw in files.items():
        _require(isinstance(path, str) and path and not path.startswith("/") and "\\" not in path
                 and all(part not in ("", ".", "..") for part in path.split("/")), str(path), "invalid package path")
        _require(isinstance(raw, bytes), path, "expected file bytes")
    version = _version(files)
    documents = {}
    for path, raw in files.items():
        if path.endswith(".json"):
            document = loads_json_bytes(raw, path)
            _require(isinstance(document, dict), path, "expected JSON object")
            if path != "release-manifest.json":
                documents[path] = document
    for path in ("assets/sources.json", "assets/address-conventions.json", "assets/address-index.json"):
        _require(path in documents, path, "required content is missing")
    _require(documents["assets/address-conventions.json"].get("chain_id") == CHAIN_ID,
             "assets/address-conventions.json", "wrong conventions chain")
    sources = _rows(documents["assets/sources.json"], "sources", "assets/sources.json")
    source_ids = set()
    for row in sources:
        identity = row.get("id")
        _require(isinstance(identity, str) and identity and identity not in source_ids,
                 "assets/sources.json", f"missing or duplicate source ID {identity!r}")
        source_ids.add(identity)

    contracts, roles, feeds, marks, candidates = [], [], [], [], []
    by_file, identities, addresses = {}, {}, {}
    for path, doc in documents.items():
        if not path.startswith("assets/addresses/"):
            continue
        records = []
        for key in ("contracts", "public_role_addresses", "markets", "pools"):
            for row in _rows(doc, key, path):
                if key == "contracts" and "file" in row:
                    continue  # by-name navigation entries, not canonical identities
                _require(type(row.get("chain_id")) is int and row["chain_id"] == CHAIN_ID, path, "wrong or missing chain_id")
                id_key = {"markets": "market_id", "pools": "pool_id"}.get(key, "id")
                identity = row.get(id_key)
                _require(isinstance(identity, str) and identity, path, "missing record identity")
                if key in ("markets", "pools"):
                    _hex(identity, 32, path)
                else:
                    address = _hex(row.get("address"), 20, path)
                    _require(address != "0x" + "0" * 40, path, "zero canonical address")
                    if key == "contracts":
                        _require(identity == "robinhood-" + address, path, "canonical ID/address mismatch")
                        _require((CHAIN_ID, address) not in addresses, path, "duplicate canonical chain/address")
                        addresses[CHAIN_ID, address] = row
                        contracts.append(row)
                        if "price_feed" in row:
                            feeds.append(row)
                    else:
                        roles.append(row)
                namespace = key if key in ("markets", "pools") else "addresses"
                identity_key = namespace, row["chain_id"], identity
                _require(identity_key not in identities, path, f"duplicate identity {identity}")
                identities[identity_key] = row
                records.append((identity, row))
        by_file[path] = dict(records)
        marks.extend(_rows(doc, "trusted_product_marks", path))
        for row in _rows(doc, "candidates", path):
            _require(doc.get("chain_id") == CHAIN_ID, path, "wrong discovery chain")
            _hex(row.get("address"), 20, path)
            candidates.append(row)

    def local(target, where):
        _require(isinstance(target, str) and target in files, where, f"missing package pointer {target!r}")
        return documents.get(target, {})

    for row in sources:
        if "reference" in row:
            reference = row["reference"]
            _require(isinstance(reference, str), "assets/sources.json/" + row["id"], "invalid reference")
            local(reference.split("#", 1)[0], "assets/sources.json/" + row["id"])

    def pointer(target, identity, where, chain=None):
        local(target, where)
        _require(isinstance(identity, str) and identity in by_file.get(target, {}), where,
                 f"record {identity!r} not found in {target}")
        row = by_file[target][identity]
        _require(chain is None or chain == row["chain_id"], where, "pointer chain mismatch")
        return row

    for path, doc in documents.items():
        for obj, where, chain in _objects(doc, path):
            for key, value in obj.items():
                if key == "source_id" or key.endswith("_source_id"):
                    _require(isinstance(value, str) and value in source_ids, where, f"unknown source ID {value!r}")
                elif key == "source_ids":
                    _require(isinstance(value, list) and all(isinstance(v, str) and v in source_ids for v in value),
                             where, "unknown source_ids reference")
                if key.endswith("_record"):
                    prefix = key[:-7]
                    row = pointer(value, obj.get(prefix + "_id"), where, chain)
                    if prefix == "canonical":
                        _require(_hex(obj.get("address"), 20, where) == row["address"].lower(), where,
                                 "promoted candidate address mismatch")
            if "file" in obj:
                target_doc = local(obj["file"], where)
                if path.startswith("assets/analytics/") and path.endswith("-routes.json"):
                    _require("id" in obj, where, "route is missing its canonical ID")
                if "id" in obj:
                    pointer(obj["file"], obj["id"], where, chain)
                elif "role" in obj:
                    matches = [row for row in _rows(target_doc, "contracts", where) if row.get("role") == obj["role"]]
                    _require(len(matches) == 1, where, "alias index role missing or ambiguous")
                    _require(obj.get("aliases", []) == matches[0].get("aliases", []), where, "alias index differs from canonical aliases")
            if path.startswith("assets/analytics/") and path.endswith("-routes.json"):
                for key, value in obj.items():
                    if key == "interface" or key.endswith("_interface"):
                        target_doc = local(value, where)
                        _require(any(k == "abi" or k.endswith("_abi") for k in target_doc), where, "interface has no ABI")
                    elif key == "workflow" or key == "markets":
                        if isinstance(value, str) and value.startswith(("assets/", "references/")):
                            local(value, where)

    index = documents["assets/address-index.json"]
    _require(index.get("chain_id") == CHAIN_ID, "assets/address-index.json", "wrong index chain")
    indexed = set()
    for group in ("feeds", "contracts"):
        mapping = index.get(group)
        _require(isinstance(mapping, dict), "assets/address-index.json", f"missing {group} index")
        for label, target in mapping.items():
            doc = local(target, "assets/address-index.json/" + group)
            indexed.add(target)
            if group == "feeds":
                _require(target == f"assets/addresses/feeds/{label.lower()}.json" and bool(doc.get("contracts")), target, "feed index membership mismatch")
            else:
                _require(target == f"assets/addresses/contracts/by-name-{label}.json", target, "contract index membership mismatch")
                for entry in _rows(doc, "contracts", target):
                    _require(entry.get("role", "")[:1].lower() == label, target, "role in wrong initial index")
                    indexed.add(entry["file"])
    for target in index.get("public_roles", []):
        doc = local(target, "assets/address-index.json/public_roles")
        _require(bool(doc.get("public_role_addresses")), target, "not a public-role file")
        indexed.add(target)
    for path, doc in documents.items():
        if path.startswith("assets/addresses/") and (doc.get("contracts") or doc.get("public_role_addresses")):
            _require(path in indexed, path, "canonical file absent from address index")
            if "/contracts/" in path and "/by-name-" not in path:
                for row in doc["contracts"]:
                    bucket = index["contracts"].get(row["role"][0].lower())
                    entries = documents.get(bucket, {}).get("contracts", [])
                    _require(sum(e.get("file") == path and e.get("role") == row["role"] for e in entries) == 1,
                             path, f"canonical role missing or duplicated in index: {row['role']}")
    for key in ("conventions", "markets", "v4_pools", "discovery"):
        if key in index:
            local(index[key], "assets/address-index.json/" + key)
    for group in ("analytics", "new_family_routes"):
        for target in index.get(group, {}).values():
            local(target, "assets/address-index.json/" + group)

    for row in marks:
        _require(row.get("chain_id") == CHAIN_ID, "trusted_product_marks", "wrong relationship chain")
        for key in ("token_address", "feed_address", "source_contract_address"):
            address = _hex(row.get(key), 20, "trusted_product_marks/" + key)
            _require((CHAIN_ID, address) in addresses, "trusted_product_marks/" + key, "unknown canonical address")
        _require("price_feed" in addresses[CHAIN_ID, row["feed_address"].lower()], "trusted_product_marks", "feed is not a price-feed record")

    markets = documents.get(index.get("markets"), {}).get("markets", [])
    pools = documents.get(index.get("v4_pools"), {}).get("pools", [])
    for row in markets:
        if "parameters" in row:
            params = row["parameters"]
            words = []
            for key in ("loanToken", "collateralToken", "oracle", "irm"):
                address = _hex(params[key], 20, "market parameters/" + key)
                _require((row["chain_id"], address) in addresses, "market parameters", "unknown canonical address")
                words.append(int(address, 16))
            words.append(int(params["lltv"]))
            _require(all(0 <= word < 1 << 256 for word in words), "market parameters", "ABI word out of range")
            digest = "0x" + keccak256(b"".join(word.to_bytes(32, "big") for word in words)).hex()
            _require(digest == row["market_id"], "market parameters", "market ID hash mismatch")
    for row in pools:
        if "pool_key" in row:
            key = row["pool_key"]
            currency0, currency1, hooks = (_hex(key[k], 20, "pool_key/" + k) for k in ("currency0", "currency1", "hooks"))
            _require(int(currency0, 16) < int(currency1, 16), "pool_key", "currencies are not ordered")
            fee, spacing = key["fee"], key["tick_spacing"]
            _require(type(fee) is int and 0 <= fee < 1 << 24 and type(spacing) is int and -(1 << 23) <= spacing < 1 << 23,
                     "pool_key", "invalid fee or tick spacing")
            words = (int(currency0, 16), int(currency1, 16), fee, spacing % (1 << 256), int(hooks, 16))
            digest = "0x" + keccak256(b"".join(word.to_bytes(32, "big") for word in words)).hex()
            _require(digest == row["pool_id"], "pool_key", "pool ID hash mismatch")

    abi_count = 0
    for path, doc in documents.items():
        if not path.startswith("assets/analytics/"):
            continue
        for key, abi in doc.items():
            if key != "abi" and not key.endswith("_abi"):
                continue
            _require(isinstance(abi, list), path + "/" + key, "expected ABI list")
            seen = set()
            for item in abi:
                _require(isinstance(item, dict) and item.get("type") in ("function", "event"), path, "read ABI contains unsupported entry")
                sig = signature(item)
                identity = item["type"], sig
                _require(identity not in seen, path, f"duplicate ABI signature {sig}")
                seen.add(identity)
                if item["type"] == "function":
                    _require(item.get("stateMutability") in ("view", "pure"), path, f"write function in read ABI: {sig}")
                    _require(isinstance(item.get("outputs"), list), path, "missing ABI outputs")
                    for output in item["outputs"]:
                        _canonical_type(output)
                else:
                    _require(type(item.get("anonymous")) is bool and all(type(i.get("indexed")) is bool for i in item["inputs"]),
                             path, "invalid event indexing")
                    _require(sum(i["indexed"] for i in item["inputs"]) <= (4 if item["anonymous"] else 3), path, "too many indexed event fields")
                abi_count += 1

    promoted = [row for row in candidates if "canonical_record" in row]
    for row in candidates:
        canonical = (CHAIN_ID, row["address"].lower()) in addresses
        _require(canonical == ("canonical_record" in row), "discovery",
                 "candidate canonical membership disagrees with promotion pointer")
    _require(len({row["address"].lower() for row in candidates}) == len(candidates), "discovery", "duplicate candidate address")
    discovery = documents.get(index.get("discovery"), {})
    listed_candidates = set()
    for entry in discovery.get("files", []):
        target = entry["file"]
        _require(target not in listed_candidates, "discovery", "duplicate candidate file")
        listed_candidates.add(target)
        _require(type(entry.get("count")) is int and entry["count"] == len(documents[target].get("candidates", [])), target, "candidate count mismatch")
    for path, doc in documents.items():
        if "candidates" in doc and path.startswith("assets/addresses/discovery/"):
            _require(path in listed_candidates, path, "candidate file absent from discovery index")
    historical = sum(row.get("classification") == "historical_named_candidate" for row in candidates)
    unclassified = sum(row.get("classification") == "unclassified_creation" for row in candidates)
    discovery_counts = {"baseline_missing_candidates": len(candidates), "now_canonical_role_identified": len(promoted),
                        "historical_named_candidates": historical, "unclassified_candidates": unclassified,
                        "remaining_outside_canonical_inventory": len(candidates) - len(promoted)}
    for key, value in discovery_counts.items():
        if key in discovery.get("counts", {}):
            _require(type(discovery["counts"][key]) is int and discovery["counts"][key] == value, "discovery/counts/" + key, "derived count mismatch")

    rwa = [row for row in feeds if row["price_feed"].get("directory_group") == "robinhood_labelled_rwa_candidate"]
    incomplete = sum(row["price_feed"].get("classification_status") == "incomplete_publisher_metadata" for row in rwa)
    unmapped = sum(row["price_feed"].get("token_relationship_status") == "unverified_no_exact_token_relationship_recorded" for row in rwa)
    counts = {
        "source_records": len(sources), "source_types": dict(Counter(row["type"] for row in sources)),
        "contract_records_unique_by_chain_and_address": len(contracts),
        "named_contract_records_excluding_underlying_feeds": len(contracts) - len(feeds),
        "public_role_address_records": len(roles), "trusted_product_mark_relationships": len(marks),
        "underlying_price_feed_records": len(feeds), "morpho_market_identifiers": len(markets),
        "fixed_block_identity_observed_morpho_markets": sum(row.get("status") == "identity_and_parameters_observed_at_fixed_block" for row in markets),
        "net_related_typed_price_sources": sum("price_source" in row for row in contracts),
        "robinhood_labelled_rwa_candidates": len(rwa), "robinhood_labelled_rwa_feed_candidates": len(rwa),
        "publisher_explicit_equity_feed_candidates": sum(row["price_feed"].get("classification_status") == "publisher_explicit_equity" for row in rwa),
        "rwa_candidates_with_incomplete_classification": incomplete, "incomplete_classification_feed_candidates": incomplete,
        "rwa_candidates_without_exact_token_relationship": unmapped, "rwa_feed_candidates_without_exact_token_relationship": unmapped,
        "v4_pool_identifiers": len(pools), "fixed_block_identity_observed_v4_positions": sum(len(row.get("observed_positions", [])) for row in pools),
        "discovery_candidates_baseline_missing": len(candidates), "discovery_candidates_now_canonical": len(promoted),
        "discovery_candidates_outside_canonical_inventory": len(candidates) - len(promoted),
        "contract_records_by_provenance_source_overlapping": dict(Counter(source for row in contracts for source in {p["source_id"] for p in row.get("provenance", [])})),
    }
    for path in ("assets/sources.json", "assets/address-conventions.json"):
        for key, recorded in documents[path].get("coverage", {}).get("counts", {}).items():
            if key in counts:
                expected = counts[key]
                _require(recorded == expected and (isinstance(expected, dict) or type(recorded) is int),
                         path + "/coverage/counts/" + key, f"derived count mismatch (expected {expected!r})")
    links = _markdown(files)
    return {"version": version, "json_files": len(documents), "source_records": len(sources),
            "canonical_contracts": len(contracts), "public_roles": len(roles),
            "discovery_candidates": len(candidates), "abi_entries": abi_count, "local_links": links}

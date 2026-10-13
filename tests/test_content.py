"""Small coherent curation inventories; no network or financial snapshots."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "maintenance")]
from content import _interface_bindings, verify_content
from netstack_core import Context, RpcError


ALPHA = "0x" + "11" * 20
BETA = "0x" + "22" * 20
UNKNOWN = "0x" + "33" * 20
CANONICAL = "assets/addresses/contracts/alpha.json"
OTHER = "assets/addresses/contracts/beta.json"
ROUTE = "assets/analytics/example-routes.json"
INTERFACE = "assets/analytics/example-interface.json"
SOURCES = "assets/sources.json"
INDEX = "assets/address-index.json"
DISCOVERY = "assets/addresses/discovery/index.json"
PROMOTED = "assets/addresses/discovery/promoted.json"
CANDIDATES = "assets/addresses/discovery/unclassified.json"


def fixture():
    def contract(address, role, aliases):
        return {"id": "robinhood-" + address, "chain_id": 4663, "address": address,
                "role": role, "aliases": aliases, "provenance": [{"source_id": "history"}]}
    counts = {"source_records": 1, "source_types": {"official_documentation": 1},
              "contract_records_unique_by_chain_and_address": 2,
              "public_role_address_records": 0, "discovery_candidates_baseline_missing": 2,
              "discovery_candidates_now_canonical": 1, "discovery_candidates_outside_canonical_inventory": 1,
              "contract_records_by_provenance_source_overlapping": {"history": 2}}
    return {
        "SKILL.md": '---\nname: netstack\nmetadata:\n  version: "0.4.0"\n---\n# Guide\n[Alpha](references/guide.md#alpha--beta)\n',
        "references/guide.md": '# Alpha & Beta\n[route](../assets/analytics/example-routes.json)\n[again](#alpha--beta-1)\n## Alpha & Beta\n',
        SOURCES: {"sources": [{"id": "history", "type": "official_documentation",
                              "url": "https://former.example/retired?original=1", "reference": "references/guide.md"}],
                  "coverage": {"counts": counts}},
        "assets/address-conventions.json": {"chain_id": 4663, "source_catalog": SOURCES},
        INDEX: {"chain_id": 4663, "conventions": "assets/address-conventions.json", "feeds": {},
                "contracts": {"a": "assets/addresses/contracts/by-name-a.json", "b": "assets/addresses/contracts/by-name-b.json"},
                "public_roles": [], "analytics": {"example": ROUTE}, "discovery": DISCOVERY},
        CANONICAL: {"contracts": [contract(ALPHA, "Alpha", ["Shared discovery name"])]},
        OTHER: {"contracts": [contract(BETA, "Beta", ["Shared discovery name"])]},
        "assets/addresses/contracts/by-name-a.json": {"contracts": [{"role": "Alpha", "aliases": ["Shared discovery name"], "file": CANONICAL}]},
        "assets/addresses/contracts/by-name-b.json": {"contracts": [{"role": "Beta", "aliases": ["Shared discovery name"], "file": OTHER}]},
        ROUTE: {"interface": INTERFACE, "workflow": "references/guide.md", "alpha": {"file": CANONICAL, "id": "robinhood-" + ALPHA}},
        INTERFACE: {"source_id": "history", "abi": [{"type": "function", "name": "balanceOf", "stateMutability": "view",
                     "inputs": [{"type": "address"}], "outputs": [{"type": "uint256"}]}]},
        DISCOVERY: {"chain_id": 4663, "files": [{"file": PROMOTED, "count": 1}, {"file": CANDIDATES, "count": 1}],
                    "counts": {"baseline_missing_candidates": 2, "now_canonical_role_identified": 1,
                               "historical_named_candidates": 0, "unclassified_candidates": 1, "remaining_outside_canonical_inventory": 1}},
        PROMOTED: {"chain_id": 4663, "candidates": [{"address": ALPHA, "classification": "canonical_role_identified",
                    "canonical_record": CANONICAL, "canonical_id": "robinhood-" + ALPHA}]},
        CANDIDATES: {"chain_id": 4663, "candidates": [{"address": UNKNOWN, "classification": "unclassified_creation"}]},
    }


def encode(documents):
    return {path: value if isinstance(value, bytes) else (value if isinstance(value, str) else json.dumps(value)).encode("utf-8")
            for path, value in documents.items()}


class ContentVerificationTests(unittest.TestCase):
    def setUp(self):
        self.docs = fixture()

    def reject(self, message):
        with self.assertRaisesRegex(ValueError, message):
            verify_content(encode(self.docs))

    def test_aliases_and_promoted_candidates_do_not_duplicate_canonical_counts(self):
        result = verify_content(encode(self.docs))
        self.assertEqual(result["canonical_contracts"], 2)
        self.assertEqual(result["discovery_candidates"], 2)
        self.assertEqual(result["version"], "0.4.0")

    def test_duplicate_source_identity_is_ambiguous(self):
        self.docs[SOURCES]["sources"].append(deepcopy(self.docs[SOURCES]["sources"][0]))
        self.reject("duplicate source ID")

    def test_dangling_source_references(self):
        for key, value in (("source_id", "absent"), ("source_ids", ["history", "absent"]), ("semantics_source_id", "absent")):
            with self.subTest(key=key):
                self.docs = fixture()
                self.docs[INTERFACE][key] = value
                self.reject("source")

    def test_route_requires_identity_in_its_exact_file(self):
        self.docs[ROUTE]["alpha"]["id"] = "robinhood-" + BETA
        self.reject("not found in")
        self.docs = fixture()
        del self.docs[ROUTE]["alpha"]["id"]
        self.reject("missing its canonical ID")

    def test_route_cannot_point_to_an_alias_index(self):
        self.docs[ROUTE]["alpha"]["file"] = "assets/addresses/contracts/by-name-a.json"
        self.reject("not found in")

    def test_wrong_chain_and_mismatched_address_are_rejected(self):
        for field, value, message in (("chain_id", 1, "chain_id"), ("address", BETA, "ID/address mismatch")):
            with self.subTest(field=field):
                self.docs = fixture()
                self.docs[CANONICAL]["contracts"][0][field] = value
                self.reject(message)

    def test_canonical_identity_cannot_be_duplicated(self):
        self.docs[CANONICAL]["contracts"].append(deepcopy(self.docs[CANONICAL]["contracts"][0]))
        self.reject("duplicate canonical")

    def test_unindexed_canonical_role_cannot_disappear_from_navigation(self):
        self.docs["assets/addresses/contracts/by-name-a.json"]["contracts"] = []
        self.reject("absent from address index")

    def test_alias_pointer_must_resolve_the_named_role(self):
        self.docs["assets/addresses/contracts/by-name-a.json"]["contracts"][0]["file"] = OTHER
        self.reject("role missing")

    def test_wrong_promoted_candidate_identity_is_rejected(self):
        self.docs[PROMOTED]["candidates"][0]["address"] = UNKNOWN
        self.reject("promoted candidate address mismatch")

    def test_discovery_counts_and_coverage_counts_are_derived_separately(self):
        for path, key in ((SOURCES, "contract_records_unique_by_chain_and_address"), (SOURCES, "source_records"),
                          (DISCOVERY, "remaining_outside_canonical_inventory")):
            with self.subTest(key=key):
                self.docs = fixture()
                counts = self.docs[path]["coverage"]["counts"] if path == SOURCES else self.docs[path]["counts"]
                counts[key] += 1
                self.reject("derived count mismatch")

    def test_provenance_counts_count_each_contract_once_per_source(self):
        self.docs[CANONICAL]["contracts"][0]["provenance"].append({"source_id": "history", "locator": "another passage"})
        verify_content(encode(self.docs))
        self.docs[SOURCES]["coverage"]["counts"]["contract_records_by_provenance_source_overlapping"]["history"] = 3
        self.reject("derived count mismatch")

    def test_missing_interface_and_write_abi_fail(self):
        del self.docs[INTERFACE]
        self.reject("missing package pointer")
        self.docs = fixture()
        self.docs[INTERFACE]["abi"][0]["stateMutability"] = "nonpayable"
        self.reject("write function")

    def test_invalid_output_type_and_duplicate_signatures_fail(self):
        self.docs[INTERFACE]["abi"][0]["outputs"][0]["type"] = "uint257"
        self.reject("ABI type")
        self.docs = fixture()
        self.docs[INTERFACE]["abi"].append(deepcopy(self.docs[INTERFACE]["abi"][0]))
        self.reject("duplicate ABI signature")

    def test_read_events_require_valid_indexing(self):
        self.docs[INTERFACE]["abi"].append({"type": "event", "name": "Change", "anonymous": False,
                                           "inputs": [{"type": "address", "indexed": True}] * 4})
        self.reject("too many indexed")

    def test_local_links_and_headings_fail_independently(self):
        for destination, message in (("missing.md", "missing local link"), ("guide.md#absent", "missing heading"),
                                     ("../../escape.md", "escapes package")):
            with self.subTest(destination=destination):
                self.docs = fixture()
                self.docs["references/guide.md"] += f"\n[broken]({destination})\n"
                self.reject(message)

    def test_markdown_conventions_ignore_code_and_accept_reference_and_balanced_links(self):
        self.docs["references/guide.md"] += ('\n```md\n[example](absent.md)\n```\n'
            '`[example](absent.md)`\n[details][more]\n[more]: <note (dated).md#read-only>\n'
            '[inline](note(dated).md#read-only)\n')
        self.docs["references/note (dated).md"] = "# Read-only\n"
        self.docs["references/note(dated).md"] = "# Read-only\n"
        verify_content(encode(self.docs))
        self.docs["references/guide.md"] += "[missing reference][not-defined]\n"
        self.reject("undefined Markdown reference")

    def test_strict_json_rejects_ambiguous_and_nonfinite_values(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":"\xff"}'):
            with self.subTest(raw=raw):
                self.docs["assets/extra.json"] = raw
                self.reject("JSON|UTF|utf|decode")

    def test_manifest_is_optional_but_present_json_must_be_strict(self):
        self.docs["SKILL.md"] += "[manifest](release-manifest.json)\n"
        verify_content(encode(self.docs))
        self.docs["release-manifest.json"] = {"ignored_by_content": True}
        verify_content(encode(self.docs))
        self.docs["release-manifest.json"] = b'{"a":1,"a":2}'
        self.reject("JSON|duplicate")

    def test_pool_identifiers_are_not_canonical_addresses(self):
        pool_id = "0x" + "aa" * 32
        pool_file = "assets/addresses/v4-pools.json"
        self.docs[INDEX]["v4_pools"] = pool_file
        self.docs[pool_file] = {"pools": [{"chain_id": 4663, "pool_id": pool_id,
            "pool_manager_record": CANONICAL, "pool_manager_id": "robinhood-" + ALPHA}]}
        result = verify_content(encode(self.docs))
        self.assertEqual(result["canonical_contracts"], 2)
        self.docs[pool_file]["pools"][0]["pool_id"] = ALPHA
        self.reject("32-byte")

    def test_trusted_mark_requires_an_actual_feed_relationship(self):
        self.docs[CANONICAL]["trusted_product_marks"] = [{"chain_id": 4663, "token_address": ALPHA,
            "feed_address": BETA, "source_contract_address": ALPHA}]
        self.reject("not a price-feed")
        self.docs[CANONICAL]["trusted_product_marks"][0]["feed_address"] = UNKNOWN
        self.reject("unknown canonical address")

    def add_function_catalog(self):
        identity = "robinhood-" + ALPHA
        detail = "assets/contracts/alpha.json"
        self.docs["assets/contracts/catalog.json"] = {
            "contracts": [
                {"contract_id": identity, "contract_record": CANONICAL, "chain_id": 4663,
                 "address": ALPHA, "interface_status": "publisher_abi", "catalog_path": detail},
                {"contract_id": "robinhood-" + BETA, "contract_record": OTHER, "chain_id": 4663,
                 "address": BETA, "interface_status": "not_reviewed", "catalog_path": None,
                 "missing_evidence": ["No matching interface reviewed."]},
            ]
        }
        self.docs[detail] = {
            "contract_id": identity, "contract_record": CANONICAL, "chain_id": 4663, "address": ALPHA,
            "provenance": [{"source_id": "history"}],
            "completeness": {"scope": "One illustrative signature, not a complete implementation."},
            "functions": [{"signature": "transfer(address,uint256)", "selector": "0xa9059cbb",
                           "inputs": [{"type": "address"}, {"type": "uint256"}],
                           "outputs": [{"type": "bool"}], "stateMutability": "nonpayable",
                           "evidence": {"source_id": "history"},
                           "permissions": {"status": "unverified", "detail": "Not established by the ABI."},
                           "economic_meaning": {"status": "unverified", "detail": "No runtime reviewed."}}],
            "events": [], "errors": []
        }
        return detail

    def test_content_pipeline_enforces_explicit_catalog_bindings(self):
        detail = self.add_function_catalog()
        self.docs[SOURCES]["sources"][0]["type"] = "official_app_contract_interface"
        self.docs[SOURCES]["coverage"]["counts"]["source_types"] = {"official_app_contract_interface": 1}
        entry = self.docs[detail]["functions"][0]
        entry.update(signature="balanceOf(address)", selector="0x70a08231",
                     inputs=[{"type": "address"}], outputs=[{"type": "uint256"}],
                     stateMutability="view")
        interface = self.docs[INTERFACE]
        interface.update(catalog_binding_scope="Offline layout equality, not deployed verification.",
                         catalog_bindings=[{"abi_key": "abi", "catalogs": [detail],
                                            "evidence_scope": "publisher_interface",
                                            "functions": ["balanceOf(address)"], "events": []}],
                         catalog_binding_exceptions=[])
        verify_content(encode(self.docs))
        entry["outputs"][0]["type"] = "int256"
        self.reject("catalog binding layout mismatch")

    def test_descriptive_write_catalog_does_not_enable_analytics_writes(self):
        detail = self.add_function_catalog()
        result = verify_content(encode(self.docs))
        self.assertEqual(result["canonical_contracts"], 2)
        self.docs[INTERFACE]["abi"].append({
            "type": "function", "name": "transfer",
            "inputs": deepcopy(self.docs[detail]["functions"][0]["inputs"]),
            "outputs": [{"type": "bool"}], "stateMutability": "nonpayable"})
        self.reject("write function in read ABI")

    def test_catalog_rejects_wrong_function_selectors_and_incomplete_coverage(self):
        detail = self.add_function_catalog()
        self.docs[detail]["functions"][0]["selector"] = "0x00000000"
        self.reject("selector/topic does not match")
        self.docs[detail]["functions"][0]["selector"] = "0xa9059cbb"
        self.docs["assets/contracts/catalog.json"]["contracts"].pop()
        self.reject("coverage ledger omits")

    def test_catalog_rejects_signature_type_drift_and_wrong_contract_binding(self):
        detail = self.add_function_catalog()
        self.docs[detail]["functions"][0]["inputs"][1]["type"] = "uint128"
        self.reject("incorrect or duplicate catalog signature")
        self.docs[detail]["functions"][0]["inputs"][1]["type"] = "uint256"
        self.docs[detail]["address"] = BETA
        self.reject("does not match coverage ledger")

    def test_version_is_required_in_metadata_not_the_body(self):
        self.docs["SKILL.md"] = self.docs["SKILL.md"].replace('  version: "0.4.0"\n', '') + '\nversion: "0.4.0"\n'
        self.reject("metadata.version|metadata mapping")


class NetLongBindingTests(unittest.TestCase):
    """Mutate real relationships, not copied inventories or expected entry counts."""

    NETLONG = "assets/analytics/netlong-interface.json"
    REVENUE = "assets/analytics/netlong-revenue-interface.json"

    def setUp(self):
        self.docs = {}
        paths = [self.NETLONG, self.REVENUE, "assets/contracts/catalog.json", SOURCES]
        for path in paths:
            self.docs[path] = json.loads((ROOT / path).read_bytes())
        for path in (self.NETLONG, self.REVENUE):
            for binding in self.docs[path]["catalog_bindings"]:
                for target in binding["catalogs"]:
                    if target not in self.docs:
                        self.docs[target] = json.loads((ROOT / target).read_bytes())

    def function(self, path, key, name):
        return next(item for item in self.docs[path][key] if item.get("name") == name)

    def reject(self, message):
        with self.assertRaisesRegex(ValueError, message):
            _interface_bindings(self.docs)

    def test_reviewed_bindings_accept_existing_repetition_and_evidence_gaps(self):
        _interface_bindings(self.docs)
        # Names and internalType affect presentation, not canonical wire types.
        output = self.function(self.NETLONG, "vault_abi", "desks")["outputs"][0]
        output["internalType"] = "struct Renamed"
        output["components"][0]["name"] = "renamed"
        self.function(self.REVENUE, "pot_abi", "totalPrincipalUsdg")["outputs"][0]["type"] = "uint"
        _interface_bindings(self.docs)

    def test_binding_scope_cannot_promote_reconstructed_getters_to_publisher_abi(self):
        original = deepcopy(self.docs)
        for signature, wrong_scope in (("nextPositionId()", "publisher_interface"),
                                       ("tokenCount()", "runtime_body_review")):
            with self.subTest(signature=signature):
                self.docs = deepcopy(original)
                binding = next(row for row in self.docs[self.NETLONG]["catalog_bindings"]
                               if signature in row["functions"])
                binding["evidence_scope"] = wrong_scope
                self.reject("catalog binding evidence scope mismatch")

    def test_bound_entry_cannot_silently_change_source_family(self):
        entry = self.function("assets/contracts/netlong-margin-desk.json", "functions", "nextPositionId")
        entry["evidence"]["source_id"] = "netnet-trading-entry-20261010"
        self.reject("catalog binding evidence scope mismatch")

    def test_tuple_signedness_width_order_and_nesting_are_semantic(self):
        original = deepcopy(self.docs)
        for change in ("signedness", "width", "order", "nesting"):
            with self.subTest(change=change):
                self.docs = deepcopy(original)
                output = self.function(self.NETLONG, "futures_abi", "positions")["outputs"][0]
                components = output["components"]
                if change == "signedness":
                    components[7]["type"] = "uint128"
                elif change == "width":
                    components[2]["type"] = "uint256"
                elif change == "order":
                    components[0], components[1] = components[1], components[0]
                else:
                    output["type"] = "tuple[]"
                self.reject("catalog binding layout mismatch")

    def test_input_signature_and_read_mutability_drift_are_rejected(self):
        original = deepcopy(self.docs)
        self.function(self.NETLONG, "vault_abi", "deskAt")["inputs"][0]["type"] = "uint128"
        self.reject("binding executable entry missing")
        self.docs = original
        self.function(self.NETLONG, "vault_abi", "deskAt")["stateMutability"] = "pure"
        self.reject("catalog binding layout mismatch")

    def test_reviewed_output_drift_is_detected_from_either_side(self):
        target = "assets/contracts/netlong-futures-vault.json"
        item = next(item for item in self.docs[target]["functions"] if item["signature"] == "equityWs()")
        item["outputs"][0]["type"] = "uint256"
        self.reject("catalog binding layout mismatch")

    def test_event_signature_indexing_and_anonymity_are_compared(self):
        original = deepcopy(self.docs)
        for change in ("signature", "indexing", "anonymous"):
            with self.subTest(change=change):
                self.docs = deepcopy(original)
                event = self.function(self.NETLONG, "futures_abi", "Filled")
                if change == "signature":
                    event["inputs"][5]["type"] = "uint16"
                elif change == "indexing":
                    event["inputs"][0]["indexed"] = False
                else:
                    event["anonymous"] = True
                self.reject("binding executable entry missing|catalog binding layout mismatch")

    def test_missing_catalog_or_selected_entry_is_not_runtime_authority(self):
        original = deepcopy(self.docs)
        binding = self.docs[self.REVENUE]["catalog_bindings"][2]
        binding["catalogs"] = ["assets/contracts/absent.json"]
        self.reject("missing or duplicate binding catalog")
        self.docs = original
        target = "assets/contracts/netlong-futures-fee-router.json"
        self.docs[target]["functions"] = [item for item in self.docs[target]["functions"]
                                        if item["signature"] != "treasury()"]
        self.reject("binding catalog entry missing")

    def test_net_catalog_is_not_assumed_to_have_stream_getters(self):
        binding = next(binding for binding in self.docs[self.NETLONG]["catalog_bindings"]
                       if binding["catalogs"] == ["assets/contracts/netlong-futures-net.json"])
        binding["functions"].append("streamId()")
        self.reject("binding catalog entry missing")

    def test_generic_and_runtime_only_entries_require_explicit_gaps(self):
        original = deepcopy(self.docs)
        for key in ("token_abi", "pot_abi"):
            with self.subTest(key=key):
                self.docs = deepcopy(original)
                self.docs[self.NETLONG]["catalog_binding_exceptions"] = [
                    row for row in self.docs[self.NETLONG]["catalog_binding_exceptions"] if row["abi_key"] != key]
                self.reject("lacks catalog binding or explicit exception")

    def test_new_executable_entry_does_not_inherit_catalog_authority(self):
        self.docs[self.NETLONG]["vault_abi"].append({
            "type": "function", "name": "balanceWs", "inputs": [],
            "outputs": [{"type": "uint256"}], "stateMutability": "view"})
        self.reject("lacks catalog binding or explicit exception")

    def test_exception_cannot_mask_a_bound_entry(self):
        self.docs[self.NETLONG]["catalog_binding_exceptions"].append({
            "abi_key": "vault_abi", "functions": ["deskCount()"], "events": [],
            "reason": "A reason does not override an existing reviewed binding."})
        self.reject("bound entry also declared")

    def test_effective_set_conflicts_fail_before_last_definition_wins(self):
        original = deepcopy(self.docs)
        for change in ("output", "mutability"):
            with self.subTest(change=change):
                self.docs = deepcopy(original)
                item = self.function(self.REVENUE, "pot_abi", "totalPrincipalUsdg")
                if change == "output":
                    item["outputs"][0]["type"] = "uint128"
                else:
                    item["stateMutability"] = "pure"
                self.reject("catalog binding layout mismatch" if change == "mutability"
                            else "incompatible effective ABI definition")

    def test_effective_event_conflicts_are_not_silently_merged(self):
        event = deepcopy(self.function(self.NETLONG, "futures_abi", "Filled"))
        event["inputs"][0]["indexed"] = False
        self.docs[self.REVENUE]["extra_abi"] = [event]
        self.reject("incompatible effective ABI definition")

    def test_runtime_allowlist_accepts_compatible_repetition_and_rejects_conflicts(self):
        original = deepcopy(self.docs)
        for change in (None, "output", "mutability", "tuple"):
            with self.subTest(change=change):
                self.docs = deepcopy(original)
                if change == "tuple":
                    item = deepcopy(self.function(self.NETLONG, "futures_abi", "positions"))
                    item["outputs"][0]["components"][7]["type"] = "uint128"
                    self.docs[self.REVENUE]["extra_abi"] = [item]
                elif change:
                    item = self.function(self.REVENUE, "pot_abi", "totalPrincipalUsdg")
                    if change == "output":
                        item["outputs"][0]["type"] = "uint128"
                    else:
                        item["stateMutability"] = "pure"
                context = object.__new__(Context)
                context.command, context._allowed = "netlong-revenue", None
                with patch("netstack_core.load_json", side_effect=self.docs.__getitem__):
                    if change in ("output", "tuple"):
                        with self.assertRaisesRegex(RpcError, "Incompatible packaged ABI definitions"):
                            context._functions()
                        self.assertIsNone(context._allowed)
                    else:
                        self.assertIn("totalPrincipalUsdg()", context._functions())


if __name__ == "__main__":
    unittest.main()

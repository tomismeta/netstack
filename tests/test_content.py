"""Small coherent curation inventories; no network or financial snapshots."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "maintenance")]
from content import verify_content


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

    def test_version_is_required_in_metadata_not_the_body(self):
        self.docs["SKILL.md"] = self.docs["SKILL.md"].replace('  version: "0.4.0"\n', '') + '\nversion: "0.4.0"\n'
        self.reject("metadata.version|metadata mapping")


if __name__ == "__main__":
    unittest.main()

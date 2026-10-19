"""Core RFV arithmetic and consumer-visible reconciliation failures; no network."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import netstack_core as core_module
import netstack_reserves as reserves_module
from netstack_core import RpcError, amount, resolve_routes, serialize_result
from netstack_reserves import _comparison, _morpho_counted, _nav, _pol, _wad, prepare_result, run
from netstack_sleeve import leverage_ratios


def synthetic_source(path):
    source = core_module.load_json(path)
    if path == "assets/analytics/reserves-interface.json":
        for model in source["implementations"].values():
            model.update(runtime_bytes=2, runtime_sha256=hashlib.sha256(bytes.fromhex("6000")).hexdigest())
    return source


class ReserveArithmetic(unittest.TestCase):
    def test_historical_documented_candidate_preserves_raw_vector_not_deployed_proof(self):
        cash = _wad(6126893532562, 6)
        gross = _wad(13392735404215, 6)
        pol = _pol(313896926377, 500720756488, 6, 9, 274022155549, 280905002055)
        self.assertEqual(pol, 24459497478012345324332)
        rfv = cash + _morpho_counted(gross) + pol
        self.assertEqual(rfv, 19276233726170712345324332)
        self.assertEqual(_nav(rfv, 110097287747921, 9), 175083638484406817094)

    def test_morpho_subtracts_floored_haircut_instead_of_flooring_remaining_assets(self):
        for gross, expected in ((1, 1), (49, 49), (50, 49), (51, 50), (10001, 9801)):
            self.assertEqual(_morpho_counted(gross), expected)
        self.assertNotEqual(_morpho_counted(51), 51 * 9800 // 10000)

    def test_root_and_ownership_floor_order_cannot_be_reversed(self):
        self.assertEqual(_pol(2, 3, 18, 18, 2, 3), 2)
        # Flooring reserves after allocating ownership would produce zero here.
        self.assertEqual(_pol(1, 4, 18, 18, 1, 2), 2)
        self.assertEqual(_wad(123456789123456789123, 20), 1234567891234567891)

    def test_zero_and_impossible_denominators_are_not_fabricated(self):
        self.assertEqual(_pol(0, 0, 6, 9, 0, 0), 0)
        for args in ((1, 1, 6, 9, 0, 0), (1, 1, 6, 9, 2, 1)):
            with self.subTest(args=args), self.assertRaises(RpcError):
                _pol(*args)
        with self.assertRaises(RpcError):
            _nav(10**18, 0, 9)
        with self.assertRaises(RpcError):
            _wad(-1, 6)

    def test_signed_residual_and_missing_are_distinct_from_zero_match(self):
        mismatch = _comparison(7, 10, "USDG wad")
        self.assertEqual((mismatch["status"], mismatch["delta_raw"]), ("mismatch", "-3"))
        self.assertEqual(amount(int(mismatch["delta_raw"]), 18), "-0.000000000000000003")
        self.assertEqual(_comparison(None, 0, "USDG wad")["status"], "unavailable")
        self.assertEqual(_comparison(0, 0, "USDG wad")["status"], "match")


    def test_checked_source_products_and_full_precision_allocation(self):
        with self.assertRaises(RpcError):
            _pol(2**128, 2**128, 18, 18, 1, 1)
        self.assertEqual(_pol(2**127, 2**127, 18, 18, 2**200, 2**201), 2**127)
        self.assertEqual(_nav(2**255, 2**255, 9), 10**9)


class ReserveProjection(unittest.TestCase):
    def setUp(self):
        self.result = {
            "command": "rfv", "snapshot": {"recheck_status": "confirmed"}, "errors": [],
            "coverage": {"collection_complete": False},
            "metrics": {
                "core_rfv": {"reconstruction_complete": False, "collection_complete": False},
                "sleeve_leverage": {
                    "publisher": leverage_ratios(Fraction(100), Fraction(40), True),
                    "external_only": leverage_ratios(Fraction(80), Fraction(40), True),
                },
            },
        }

    def test_snapshot_qualification_withholds_both_leverage_bases_without_mutating_evidence(self):
        for snapshot, errors, confirmation in (
                ({}, [], "unconfirmed"),
                ({"recheck_status": "not_performed"}, [], "unconfirmed"),
                ({"recheck_status": "unconfirmed"}, [], "unconfirmed"),
                ({"recheck_status": "mismatch"}, [], "invalid"),
                ({"recheck_status": "confirmed", "confirmation": "invalid"}, [], "invalid"),
                ({"recheck_status": "confirmed"}, [{"kind": "permission"}], "invalid"),
                ({"recheck_status": "confirmed"}, [{"kind": "integrity"}], "invalid")):
            for with_core in (True, False):
                with self.subTest(snapshot=snapshot, errors=errors, with_core=with_core):
                    source = deepcopy(self.result)
                    source.update(snapshot=snapshot, errors=errors)
                    if not with_core:
                        del source["metrics"]["core_rfv"]
                    before = deepcopy(source)
                    projected = prepare_result(source)
                    for basis in ("publisher", "external_only"):
                        row = projected["metrics"]["sleeve_leverage"][basis]
                        self.assertFalse(row["collection_complete"])
                        self.assertEqual(row["ratio_status"], "incomplete")
                        self.assertEqual(row["snapshot_confirmation"], confirmation)
                        for key in ("gross_assets_wad", "debt_wad", "equity_wad",
                                    "gross_to_equity", "debt_to_equity"):
                            self.assertIsNone(row[key])
                        for key in ("known_gross_assets_subtotal_wad", "known_debt_subtotal_wad"):
                            self.assertEqual(row[key], before["metrics"]["sleeve_leverage"][basis][key])
                    self.assertEqual(source, before)
                    self.assertEqual(projected, prepare_result(source))
                    self.assertEqual(projected, prepare_result(projected))
                    source.update(snapshot={"recheck_status": "confirmed"}, errors=[])
                    self.assertEqual(prepare_result(source)["metrics"]["sleeve_leverage"],
                                     self.result["metrics"]["sleeve_leverage"])

    def test_confirmed_sleeve_leverage_remains_independent_of_core_valuation(self):
        for with_core in (True, False):
            with self.subTest(with_core=with_core):
                source = deepcopy(self.result)
                if not with_core:
                    del source["metrics"]["core_rfv"]
                before = deepcopy(source)
                projected = prepare_result(source)
                leverage = projected["metrics"]["sleeve_leverage"]
                self.assertEqual(leverage, before["metrics"]["sleeve_leverage"])
                self.assertFalse(projected["coverage"]["collection_complete"])
                self.assertEqual(leverage["publisher"]["gross_to_equity"],
                                 {"numerator": "5", "denominator": "3"})
                self.assertEqual(leverage["publisher"]["debt_to_equity"],
                                 {"numerator": "2", "denominator": "3"})
                for basis in ("publisher", "external_only"):
                    self.assertTrue(leverage[basis]["collection_complete"])
                    self.assertEqual(leverage[basis]["ratio_status"], "available")
                self.assertEqual(source, before)
                self.assertEqual(projected, prepare_result(projected))


class Snapshot:
    """Small self-consistent reserve state, with independently adjustable reads."""
    def __init__(self):
        self.block = 10
        self.result = {"command": "rfv", "metrics": {}, "coverage": {}, "errors": [], "not_proven": [],
                       "snapshot": {"recheck_status": "confirmed"}}
        a = {name: record["address"] for name, record in resolve_routes("reserves").items() if name != "_route"}
        self.values = {
            "treasury": {"rfv": 298 * 10**18, "liquidUsdg": 100 * 10**18, "morphoAssets": 100 * 10**18,
                         "backingPerToken": 298 * 10**18 // 10, "net": a["net"], "usdg": a["usdg"],
                         "morphoVault": a["vault"], "canonicalPair": a["pair"]},
            "usdg": {"decimals": 6, "balanceOf": 100 * 10**6},
            "net": {"decimals": 9, "totalSupply": 10 * 10**9},
            "vault": {"asset": a["usdg"], "decimals": 18, "balanceOf": 80 * 10**18, "convertToAssets": 100 * 10**6},
            "pair": {"token0": a["usdg"], "token1": a["net"], "getReserves": {"reserve0": 100 * 10**6, "reserve1": 100 * 10**9, "blockTimestampLast": 9},
                     "totalSupply": 1000, "balanceOf": 500, "decimals": 18},
        }
        self.addresses = {address: name for name, address in a.items()}
        self.codes = {address: "0x6000" for address in self.addresses}
        self.implementation_address = synthetic_source("assets/analytics/reserves-interface.json")[
            "implementations"]["usdg_implementation"]["address"]
        self.codes[self.implementation_address] = "0x6000"

    def call(self, address, abi, getter, args=()):
        value = self.values[self.addresses[address]][getter]
        if isinstance(value, Exception):
            raise value
        return value

    def code(self, address):
        value = self.codes[address]
        if isinstance(value, Exception):
            raise value
        return value

    def implementation(self, address):
        return self.implementation_address

    def checkpoint(self):
        pass


class ReserveReconciliation(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(reserves_module, "load_json", side_effect=synthetic_source)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_supported_matching_pinned_reconstruction_certifies_only_observed_block(self):
        ctx = Snapshot()
        run(ctx, SimpleNamespace(scope="core"))
        emitted = json.loads(serialize_result(ctx.result))
        core = emitted["metrics"]["core_rfv"]
        self.assertEqual(core["components"]["pol"]["value_wad"], str(100 * 10**18))
        self.assertEqual(core["reconciliation"]["rfv"]["delta_raw"], "0")
        self.assertTrue(core["pol_reconstruction_supported"])
        self.assertEqual(core["status"], "reconciled")
        self.assertTrue(emitted["coverage"]["collection_complete"])
        self.assertFalse(core["historical_discrepancy_resolved"])
        self.assertTrue(all(row["status"] == "matched" for row in core["implementations"].values()))
        self.assertEqual(ctx.result["errors"], [])

    def test_unknown_or_changed_runtime_stays_partial_even_with_zero_residual(self):
        for role in ("treasury", "usdg", "net", "vault", "pair", "usdg_implementation"):
            for code in ("0x", "0x6001", "0x600000"):
                with self.subTest(role=role, code=code):
                    ctx = Snapshot()
                    address = (ctx.implementation_address if role == "usdg_implementation"
                               else resolve_routes("reserves")[role]["address"])
                    ctx.codes[address] = code
                    run(ctx, SimpleNamespace(scope="core"))
                    report = prepare_result(ctx.result)
                    result = report["metrics"]["core_rfv"]
                    self.assertEqual(result["reconciliation"]["rfv"]["delta_raw"], "0")
                    self.assertFalse(result["pol_reconstruction_supported"])
                    self.assertEqual(result["implementations"][role + ".code"]["status"], "unsupported")
                    self.assertEqual(result["status"], "partial")
                    self.assertFalse(report["coverage"]["collection_complete"])

    def test_unavailable_runtime_or_proxy_slot_preserves_independent_evidence(self):
        for unavailable in ("code", "slot"):
            with self.subTest(unavailable=unavailable):
                ctx = Snapshot()
                if unavailable == "code":
                    ctx.codes[resolve_routes("reserves")["treasury"]["address"]] = RpcError("Pruned", kind="pruned")
                    run(ctx, SimpleNamespace(scope="core"))
                else:
                    with patch.object(ctx, "implementation", side_effect=RpcError("Pruned", kind="pruned")):
                        run(ctx, SimpleNamespace(scope="core"))
                result = ctx.result["metrics"]["core_rfv"]
                self.assertEqual(result["assembled"]["rfv_wad"], str(298 * 10**18))
                self.assertFalse(result["pol_reconstruction_supported"])
                self.assertEqual(result["status"], "partial")
                self.assertFalse(ctx.result["coverage"]["collection_complete"])

    def test_unchanged_proxy_runtime_cannot_hide_changed_implementation(self):
        ctx = Snapshot()
        ctx.implementation_address = "0x" + "12" * 20
        run(ctx, SimpleNamespace(scope="core"))
        result = ctx.result["metrics"]["core_rfv"]
        self.assertEqual(result["relationships"]["usdg.implementation"]["status"], "mismatch")
        self.assertNotIn("usdg_implementation.code", result["reads"])
        self.assertFalse(result["pol_reconstruction_supported"])

    def test_units_and_dependency_assumptions_fail_closed(self):
        for role, getter, value, group, diagnostic in (
                ("usdg", "decimals", 7, "assumptions", "usdg.decimals"),
                ("net", "decimals", 18, "assumptions", "net.decimals"),
                ("treasury", "net", "0x" + "12" * 20, "relationships", "treasury.net"),
                ("vault", "asset", "0x" + "12" * 20, "relationships", "vault.asset")):
            with self.subTest(role=role, getter=getter):
                ctx = Snapshot()
                ctx.values[role][getter] = value
                run(ctx, SimpleNamespace(scope="core"))
                result = ctx.result["metrics"]["core_rfv"]
                self.assertEqual(result[group][diagnostic]["status"], "mismatch")
                self.assertFalse(result["pol_reconstruction_supported"])
                self.assertFalse(ctx.result["coverage"]["collection_complete"])

    def test_live_pair_orientation_must_match_runtime_cached_orientation(self):
        ctx = Snapshot()
        pair = ctx.values["pair"]
        pair["token0"], pair["token1"] = pair["token1"], pair["token0"]
        pair["getReserves"]["reserve0"], pair["getReserves"]["reserve1"] = (
            pair["getReserves"]["reserve1"], pair["getReserves"]["reserve0"])
        run(ctx, SimpleNamespace(scope="core"))
        result = ctx.result["metrics"]["core_rfv"]
        self.assertEqual(result["reconciliation"]["rfv"]["delta_raw"], "0")
        self.assertEqual(result["assumptions"]["pair.cached_net_is_token0"]["status"], "mismatch")
        self.assertFalse(result["pol_reconstruction_supported"])

    def test_final_confirmation_qualifies_core_and_dependent_checkpoints_without_mutation(self):
        ctx = Snapshot()
        ctx.result["snapshot"]["recheck_status"] = "not_performed"
        run(ctx, SimpleNamespace(scope="core"))
        ctx.result["metrics"]["reports_true_rfv"] = {"value_wad": "12", "value": "0.000000000000000012",
                                                   "collection_complete": True, "core_complete": True}
        ctx.result["metrics"]["adjusted_net_assets"] = {"value_wad": "10", "collection_complete": True}
        ctx.result["metrics"]["component_summary"] = {"core": {"observed": {"collection_complete": True},
                                                              "valuation": {"reports_basis_complete": True}}}
        ctx.result["coverage"]["requested_scope"] = {"scope": "reports", "collection_complete": True}
        for state in ("not_performed", "unconfirmed", "mismatch"):
            with self.subTest(state=state):
                ctx.result["snapshot"]["recheck_status"] = state
                emitted = json.loads(serialize_result(ctx.result))
                self.assertEqual(emitted["metrics"]["core_rfv"]["status"], "partial")
                self.assertFalse(emitted["coverage"]["core_rfv"]["collection_complete"])
                self.assertFalse(emitted["coverage"]["requested_scope"]["collection_complete"])
                self.assertIsNone(emitted["metrics"]["reports_true_rfv"]["value_wad"])
                self.assertIsNone(emitted["metrics"]["adjusted_net_assets"]["value_wad"])
                self.assertFalse(emitted["metrics"]["component_summary"]["core"]["valuation"]["reports_basis_complete"])
                self.assertEqual(emitted["metrics"]["core_rfv"]["assembled"]["rfv_wad"], str(298 * 10**18))
        self.assertTrue(ctx.result["coverage"]["core_rfv"]["collection_complete"])
        ctx.result["snapshot"]["recheck_status"] = "confirmed"
        confirmed = json.loads(serialize_result(ctx.result))
        self.assertEqual(confirmed["metrics"]["core_rfv"]["status"], "reconciled")
        self.assertEqual(confirmed["metrics"]["reports_true_rfv"]["value_wad"], "12")
        ctx.result["errors"].append({"kind": "integrity", "message": "Conflicting pinned evidence"})
        invalid = json.loads(serialize_result(ctx.result))
        self.assertEqual(invalid["metrics"]["core_rfv"]["status"], "partial")
        self.assertFalse(invalid["coverage"]["collection_complete"])
        self.assertIsNone(invalid["metrics"]["reports_true_rfv"]["value_wad"])

    def test_nondivisible_morpho_raw_value_reaches_core_components(self):
        ctx = Snapshot()
        ctx.values["usdg"].update(decimals=18, balanceOf=100 * 10**18)
        ctx.values["vault"]["convertToAssets"] = 51
        ctx.values["pair"]["getReserves"]["reserve0"] = 100 * 10**18
        ctx.values["treasury"].update(morphoAssets=51, rfv=200 * 10**18 + 50,
                                      backingPerToken=(200 * 10**18 + 50) // 10)
        run(ctx, SimpleNamespace(scope="core"))
        core = ctx.result["metrics"]["core_rfv"]
        self.assertEqual(core["components"]["morpho"]["gross_wad"], "51")
        self.assertEqual(core["components"]["morpho"]["haircut_wad"], "1")
        self.assertEqual(core["components"]["morpho"]["value_wad"], "50")
        self.assertEqual(core["reconciliation"]["rfv"]["delta_raw"], "0")
        self.assertFalse(core["pol_reconstruction_supported"])
        self.assertEqual(core["assumptions"]["morpho.haircut_equivalence"]["status"], "mismatch")

    def test_external_basis_replaces_haircut_and_geometric_pol_without_own_net(self):
        ctx = Snapshot()
        run(ctx, SimpleNamespace(scope="core"))
        core = ctx.result["metrics"]["core_rfv"]
        external = core["external_asset_basis"]
        self.assertEqual(core["assembled"]["rfv_wad"], str(298 * 10**18))
        # 100 cash + 100 gross vault assets + 50 LP USDG; not 298 plus LP legs.
        self.assertEqual(external["value_wad"], str(250 * 10**18))
        self.assertEqual(external["excluded_own_net_pol_raw"], str(50 * 10**9))

    def test_missing_vault_claim_withholds_external_basis_but_retains_lp_leg(self):
        ctx = Snapshot()
        ctx.values["vault"]["convertToAssets"] = RpcError("Unavailable", kind="pruned")
        run(ctx, SimpleNamespace(scope="core"))
        external = ctx.result["metrics"]["core_rfv"]["external_asset_basis"]
        self.assertIsNone(external["value_wad"])
        self.assertEqual(external["lp_usdg_wad"], str(50 * 10**18))

    def test_mismatch_keeps_independent_total_and_reports_partial(self):
        ctx = Snapshot()
        ctx.values["treasury"]["rfv"] -= 1
        run(ctx, SimpleNamespace(scope="core"))
        core = ctx.result["metrics"]["core_rfv"]
        self.assertEqual(core["assembled"]["rfv_wad"], str(298 * 10**18))
        self.assertEqual(core["reconciliation"]["rfv"]["delta_raw"], "-1")
        self.assertEqual(core["status"], "partial")
        self.assertFalse(ctx.result["coverage"]["collection_complete"])
        self.assertEqual(core["components"]["pol"]["look_through_memo"]["usdg"]["raw"], "50000000")
        self.assertFalse(core["components"]["pol"]["look_through_memo"]["additive"])

    def test_failed_vault_read_retains_cash_pol_and_treasury_getters(self):
        ctx = Snapshot()
        ctx.values["vault"]["convertToAssets"] = RpcError("Historical state unavailable", kind="pruned")
        run(ctx, SimpleNamespace(scope="core"))
        core = ctx.result["metrics"]["core_rfv"]
        self.assertIsNone(core["assembled"]["rfv_wad"])
        self.assertEqual(core["reported"]["rfv"]["raw"], str(298 * 10**18))
        self.assertEqual(core["components"]["liquid_usdg"]["value_wad"], str(100 * 10**18))
        self.assertEqual(core["components"]["pol"]["value_wad"], str(100 * 10**18))
        self.assertFalse(ctx.result["coverage"]["collection_complete"])

    def test_wrong_underlying_cannot_be_valued_as_usdg(self):
        ctx = Snapshot()
        ctx.values["vault"]["asset"] = ctx.values["treasury"]["net"]
        run(ctx, SimpleNamespace(scope="core"))
        core = ctx.result["metrics"]["core_rfv"]
        self.assertEqual(core["relationships"]["vault.asset"]["status"], "mismatch")
        self.assertIsNone(core["components"]["morpho"]["value_wad"])
        self.assertEqual(core["components"]["morpho"]["assets_raw"], "100000000")
        self.assertFalse(ctx.result["coverage"]["collection_complete"])


if __name__ == "__main__":
    unittest.main()

"""Core RFV arithmetic and consumer-visible reconciliation failures; no network."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from netstack_core import RpcError, amount, resolve_routes
from netstack_reserves import _comparison, _nav, _pol, _wad, run


class ReserveArithmetic(unittest.TestCase):
    def test_recorded_mixed_decimal_core_reconciles_exactly(self):
        cash = _wad(6126893532562, 6)
        gross = _wad(13392735404215, 6)
        pol = _pol(313896926377, 500720756488, 6, 9, 274022155549, 280905002055)
        self.assertEqual(pol, 24459497478012345324332)
        rfv = cash + gross * 9800 // 10000 + pol
        self.assertEqual(rfv, 19276233726170712345324332)
        self.assertEqual(_nav(rfv, 110097287747921, 9), 175083638484406817094)

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


class Snapshot:
    """Small self-consistent reserve state, with independently adjustable reads."""
    def __init__(self):
        self.block = 10
        self.result = {"metrics": {}, "coverage": {}, "errors": [], "not_proven": []}
        a = {name: record["address"] for name, record in resolve_routes("reserves").items() if name != "_route"}
        self.values = {
            "treasury": {"rfv": 298 * 10**18, "liquidUsdg": 100 * 10**18, "morphoAssets": 100 * 10**18,
                         "backingPerToken": 298 * 10**18 // 10, "net": a["net"], "usdg": a["usdg"],
                         "morphoVault": a["vault"], "canonicalPair": a["pair"]},
            "usdg": {"decimals": 6, "balanceOf": 100 * 10**6},
            "net": {"decimals": 9, "totalSupply": 10 * 10**9},
            "vault": {"asset": a["usdg"], "decimals": 18, "balanceOf": 80 * 10**18, "convertToAssets": 100 * 10**6},
            "pair": {"token0": a["net"], "token1": a["usdg"], "getReserves": {"reserve0": 100 * 10**9, "reserve1": 100 * 10**6, "blockTimestampLast": 9},
                     "totalSupply": 1000, "balanceOf": 500, "decimals": 18},
        }
        self.addresses = {address: name for name, address in a.items()}

    def call(self, address, abi, getter, args=()):
        value = self.values[self.addresses[address]][getter]
        if isinstance(value, Exception):
            raise value
        return value

    def code(self, address):
        return "0x01"

    def checkpoint(self):
        pass


class ReserveReconciliation(unittest.TestCase):
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

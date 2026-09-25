"""Concentrated-liquidity boundaries and fee arithmetic; no network."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import netstack_core as core
import netstack_v4 as v4
from netstack_core import RpcError
from netstack_v4 import (Q96, U256, fee_growth_inside, liquidity_amounts,
                         sqrt_ratio_at_tick, storage_slots)


class PositionArithmetic(unittest.TestCase):
    def test_tick_extremes_and_zero_have_exact_contract_scale(self):
        self.assertEqual(sqrt_ratio_at_tick(0), Q96)
        self.assertEqual(sqrt_ratio_at_tick(-887272), 4295128739)
        self.assertEqual(sqrt_ratio_at_tick(887272), 1461446703485210103287273052203988822378723970342)
        for tick in (-887273, 887273):
            with self.assertRaises(RpcError):
                sqrt_ratio_at_tick(tick)

    def test_principal_becomes_one_sided_at_each_range_boundary(self):
        liquidity = 10**18
        lower, upper = sqrt_ratio_at_tick(-120), sqrt_ratio_at_tick(120)
        at_low = liquidity_amounts(liquidity, -120, 120, lower)
        below = liquidity_amounts(liquidity, -120, 120, lower - 1)
        inside = liquidity_amounts(liquidity, -120, 120, Q96)
        at_high = liquidity_amounts(liquidity, -120, 120, upper)
        self.assertEqual(at_low, below)
        self.assertEqual(at_low[1], 0)
        self.assertEqual(at_high[0], 0)
        self.assertEqual(at_low[0], (liquidity << 96) * (upper - lower) // upper // lower)
        self.assertEqual(at_high[1], liquidity * (upper - lower) // Q96)
        self.assertGreater(inside[0], 0)
        self.assertGreater(inside[1], 0)
        self.assertLess(inside[0], at_low[0])
        self.assertLess(inside[1], at_high[1])

    def test_fee_growth_crossing_uses_half_open_interval_and_uint256_wrap(self):
        self.assertEqual(fee_growth_inside(-11, -10, 10, 100, 9, 4), 5)
        self.assertEqual(fee_growth_inside(-10, -10, 10, 100, 9, 4), 87)
        self.assertEqual(fee_growth_inside(10, -10, 10, 100, 9, 4), U256 - 5)
        self.assertEqual((fee_growth_inside(0, -10, 10, 3, 0, 0) - (U256 - 2)) % U256, 5)

    def test_position_salt_and_signed_ticks_do_not_alias_storage(self):
        pool = "0x" + "ab" * 32
        owner = "0x" + "12" * 20
        first = storage_slots(pool, owner, -120, 120, 1)
        second = storage_slots(pool, owner, -120, 120, 2)
        positive = storage_slots(pool, owner, 120, 240, 1)
        self.assertEqual(first[:7], second[:7])
        self.assertNotEqual(first[7], second[7])
        self.assertNotEqual(first[3], positive[3])
        self.assertEqual(int(first[8], 16), (int(first[7], 16) + 1) % U256)


class PositionDiscovery(unittest.TestCase):
    def setUp(self):
        self.ctx = core.Context("rfv", deadline=30)
        self.ctx.block = 72320994
        self.owner = core.resolve_routes("reserves")["sleeve"]["address"]
        self.routes = core.resolve_routes("v4")
        self.pm = self.routes["position_manager"]["address"]
        self.manager = self.routes["pool_manager"]["address"]
        self.other = "0x" + "99" * 20
        self.owners = {3080718: self.owner, 3269350: self.owner}
        self.expected = 2
        self.liquidity = 123456
        self.key = {"currency0": "0x" + "11" * 20, "currency1": "0x" + "22" * 20,
                    "fee": 500, "tickSpacing": 10, "hooks": core.ZERO}
        identifier = v4.pool_id(self.key)
        self.packed = (int(identifier, 16) >> 56 << 56) | (120 << 32) | (((1 << 24) - 120) << 8)
        self.words = {}
        for token_id in (3080718, 3269350, 9):
            slots = storage_slots(identifier, self.pm, -120, 120, token_id)
            values = (Q96, 2 * v4.Q128, 3 * v4.Q128, 0, 0, 0, 0, self.liquidity, 0, 0)
            self.words.update(zip(slots, values))
        self.stub = patch.object(self.ctx, "call", side_effect=self.call)
        self.stub.start()

    def tearDown(self):
        self.stub.stop()
        self.ctx.close()

    def call(self, address, abi, method, args=()):
        if method == "poolManager":
            return self.manager
        if method == "balanceOf":
            return self.expected
        if method == "ownerOf":
            return self.owners[args[0]]
        if method == "getPoolAndPositionInfo":
            return {"poolKey": self.key, "info": self.packed}
        if method == "getPositionLiquidity":
            return self.liquidity
        if method == "extsload":
            return "0x" + self.words[args[0]].to_bytes(32, "big").hex()
        raise AssertionError(method)

    def test_seed_ownership_rechecks_reconcile_without_genesis_scan_and_keep_exact_fees(self):
        with patch.object(self.ctx, "logs", side_effect=AssertionError("Unnecessary full-history scan")):
            result = v4.collect(self.ctx, self.owner)
        self.assertTrue(result["ownership_complete"])
        self.assertTrue(result["collection_complete"])
        self.assertFalse(result["exhaustive_across_managers"])
        self.assertEqual({row["position_id"] for row in result["positions"]}, {3080718, 3269350})
        for row in result["positions"]:
            self.assertEqual(row["fees0_raw"], 2 * self.liquidity)
            self.assertEqual(row["fees1_raw"], 3 * self.liquidity)

    def test_changed_seed_owner_requires_dynamic_discovery_and_excludes_former_custody(self):
        self.owners.update({3269350: self.other, 9: self.owner})
        events = [{"values": {"tokenId": 9}, "transactionHash": "0x" + "aa" * 32,
                   "blockNumber": self.ctx.block, "logIndex": 1}]
        with patch.object(self.ctx, "logs", return_value=iter([events])):
            result = v4.collect(self.ctx, self.owner)
        self.assertTrue(result["ownership_complete"])
        self.assertEqual({row["position_id"] for row in result["positions"]}, {3080718, 9})
        moved = next(row for row in result["candidates"] if row["position_id"] == 3269350)
        self.assertEqual(moved["disposition"], "excluded")
        self.assertEqual(moved["owner"], self.other)

    def test_new_recent_position_reconciles_before_walking_genesis_history(self):
        self.expected = 3
        self.owners[9] = self.owner
        log = {"address": self.pm,
               "topics": [core.TRANSFER_TOPIC, "0x" + "00" * 32,
                          "0x" + self.owner[2:].rjust(64, "0"), "0x" + (9).to_bytes(32, "big").hex()],
               "data": "0x", "blockNumber": hex(self.ctx.block), "transactionIndex": "0x0",
               "logIndex": "0x0", "transactionHash": "0x" + "aa" * 32,
               "blockHash": "0x" + "bb" * 32, "removed": False}
        queries = []
        def exchange(requests):
            query = requests[0][1][0]
            queries.append(query)
            if int(query["fromBlock"], 16) < self.ctx.block - core.MAX_LOG_BLOCKS + 1:
                raise AssertionError("Recent NFT must be found before older history is queried")
            return [[log]]
        with patch.object(self.ctx, "_exchange_once", side_effect=exchange):
            result = v4.collect(self.ctx, self.owner)
        self.assertTrue(result["ownership_complete"])
        self.assertTrue(result["collection_complete"])
        self.assertEqual({row["position_id"] for row in result["positions"]}, {3080718, 3269350, 9})
        self.assertEqual(len(queries), 1)
        coverage = self.ctx.result["coverage"]["v4_incoming_nfts"]
        self.assertEqual(coverage["covered_ranges"], [[self.ctx.block - core.MAX_LOG_BLOCKS + 1, self.ctx.block]])
        self.assertEqual(coverage["missing_ranges"], [[0, self.ctx.block - core.MAX_LOG_BLOCKS]])
        self.assertFalse(coverage["event_coverage_complete"])

    def test_missing_event_history_never_turns_seed_list_into_complete_inventory(self):
        self.expected = 3
        with patch.object(self.ctx, "logs", side_effect=RpcError("Missing history", kind="pruned")):
            result = v4.collect(self.ctx, self.owner)
        self.assertFalse(result["ownership_complete"])
        self.assertFalse(result["collection_complete"])
        self.assertEqual({row["position_id"] for row in result["positions"]}, {3080718, 3269350})
        self.assertEqual(result["expected_owned_count"], 3)

    def test_changed_pool_manager_is_not_followed_or_hidden_as_coverage_only(self):
        with patch.object(self.ctx, "call", return_value=self.other) as calls:
            with self.assertRaises(RpcError) as failure:
                v4.collect(self.ctx, self.owner)
        self.assertEqual(failure.exception.kind, "integrity")
        self.assertEqual([call.args[0] for call in calls.call_args_list], [self.pm])


if __name__ == "__main__":
    unittest.main()

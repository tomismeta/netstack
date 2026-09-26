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
        self.block = 3 * core.MAX_LOG_BLOCKS + 17
        self.owner = core.resolve_routes("reserves")["sleeve"]["address"]
        routes = core.resolve_routes("v4")
        self.pm = routes["position_manager"]["address"]
        self.manager = routes["pool_manager"]["address"]
        self.other = "0x" + "99" * 20
        self.owners = {101: self.owner, 202: self.owner}
        self.expected = 2
        self.transfers = [(101, self.block), (202, self.block)]
        self.liquidities = {101: 123456, 202: 654321}
        self.key = {"currency0": "0x" + "11" * 20, "currency1": "0x" + "22" * 20,
                    "fee": 500, "tickSpacing": 10, "hooks": core.ZERO}
        identifier = v4.pool_id(self.key)
        self.packed = (int(identifier, 16) >> 56 << 56) | (120 << 32) | (((1 << 24) - 120) << 8)
        self.failures = {}
        self.history_error = None
        self.history_error_before = None
        self.bad_stored_liquidity = False
        self.bound_manager = self.manager

    def call(self, address, abi, method, args=()):
        self.reads.append((address, method, args))
        if method in self.failures:
            raise self.failures[method]
        if method == "extsload":
            self.assertEqual(address, self.manager)
            return "0x" + self.words[args[0]].to_bytes(32, "big").hex()
        self.assertEqual(address, self.pm)
        if method == "poolManager":
            return self.bound_manager
        if method == "balanceOf":
            self.assertEqual(args, (self.owner,))
            return self.expected
        token_id = args[0]
        if method == "ownerOf":
            owner = self.owners[token_id]
            if isinstance(owner, RpcError):
                raise owner
            return owner
        if method == "getPoolAndPositionInfo":
            slots = storage_slots(v4.pool_id(self.key), self.pm, -120, 120, token_id)
            liquidity = self.liquidities.get(token_id, 123456)
            # Nonzero outside/last growth catches omission of tick or
            # position storage. Distinct salts have distinct last growth.
            last0 = (2 if token_id == 101 else 3) * v4.Q128
            values = (Q96, 10 * v4.Q128, 20 * v4.Q128,
                      v4.Q128, 2 * v4.Q128, 3 * v4.Q128, 4 * v4.Q128,
                      liquidity + int(self.bad_stored_liquidity), last0, 5 * v4.Q128)
            self.words.update(zip(slots, values))
            return {"poolKey": self.key, "info": self.packed}
        if method == "getPositionLiquidity":
            return self.liquidities.get(token_id, 123456)
        raise AssertionError(method)

    def exchange(self, requests):
        self.assertEqual(len(requests), 1)
        method, arguments = requests[0]
        self.assertEqual(method, "eth_getLogs")
        query = arguments[0]
        self.queries.append(query)
        self.assertEqual(query["address"], self.pm)
        self.assertEqual(query["topics"], [[core.TRANSFER_TOPIC], None,
                                         "0x" + self.owner[2:].rjust(64, "0")])
        left, right = int(query["fromBlock"], 16), int(query["toBlock"], 16)
        self.assertLessEqual(right, self.block)
        self.assertLessEqual(right - left + 1, core.MAX_LOG_BLOCKS)
        if self.history_error is not None and (self.history_error_before is None
                                              or right < self.history_error_before):
            raise self.history_error
        logs = []
        for index, (token_id, block) in enumerate(self.transfers):
            if not left <= block <= right:
                continue
            logs.append({"address": self.pm,
                         "topics": [core.TRANSFER_TOPIC, "0x" + "00" * 32,
                                    "0x" + self.owner[2:].rjust(64, "0"),
                                    "0x" + token_id.to_bytes(32, "big").hex()],
                         "data": "0x", "blockNumber": hex(block),
                         "transactionIndex": hex(index), "logIndex": hex(index),
                         "transactionHash": "0x" + (index + 1).to_bytes(32, "big").hex(),
                         "blockHash": "0x" + block.to_bytes(32, "big").hex(), "removed": False})
        return [logs]

    def collect(self):
        self.ctx = core.Context("rfv", deadline=30)
        self.ctx.block = self.block
        self.words, self.queries, self.reads = {}, [], []
        try:
            with patch.object(self.ctx, "call", side_effect=self.call), \
                    patch.object(self.ctx, "_exchange_once", side_effect=self.exchange):
                return v4.collect(self.ctx, self.owner)
        finally:
            self.ctx.close()

    def test_incoming_universe_reconciles_without_full_history_and_reads_exact_fees(self):
        result = self.collect()
        self.assertTrue(result["ownership_complete"])
        self.assertTrue(result["collection_complete"])
        self.assertFalse(result["exhaustive_across_managers"])
        self.assertFalse(result["history_complete"])
        self.assertEqual(result["observed_owned_count"], 2)
        self.assertEqual({row["position_id"] for row in result["positions"]}, {101, 202})
        for row in result["positions"]:
            liquidity = self.liquidities[row["position_id"]]
            self.assertEqual((row["amount0_raw"], row["amount1_raw"]),
                             liquidity_amounts(liquidity, -120, 120, Q96))
            self.assertEqual(row["fees0_raw"], (4 if row["position_id"] == 101 else 3) * liquidity)
            self.assertEqual(row["fees1_raw"], 9 * liquidity)
        self.assertEqual(len(self.queries), 1)
        coverage = self.ctx.result["coverage"]["v4_incoming_nfts"]
        self.assertEqual(coverage["requested_range"], [0, self.block])
        self.assertEqual(coverage["covered_ranges"], [[self.block - core.MAX_LOG_BLOCKS + 1, self.block]])
        self.assertEqual(coverage["missing_ranges"], [[0, self.block - core.MAX_LOG_BLOCKS]])
        self.assertFalse(coverage["event_coverage_complete"])
        self.assertEqual(coverage["status"], "stopped_after_ownership_reconciliation")

    def test_new_mint_arrives_on_next_run_without_catalog_edits(self):
        first = self.collect()
        self.expected = 3
        self.owners[303] = self.owner
        self.transfers.append((303, self.block))
        second = self.collect()
        self.assertEqual({row["position_id"] for row in first["positions"]}, {101, 202})
        self.assertEqual({row["position_id"] for row in second["positions"]}, {101, 202, 303})
        self.assertTrue(second["collection_complete"])
        self.assertEqual(second["expected_owned_count"], 3)

    def test_same_count_replacement_is_discovered_and_departure_excluded(self):
        first = self.collect()
        self.owners.update({202: self.other, 303: self.owner})
        self.transfers.append((303, self.block))
        second = self.collect()
        self.assertEqual({row["position_id"] for row in first["positions"]}, {101, 202})
        self.assertEqual({row["position_id"] for row in second["positions"]}, {101, 303})
        self.assertTrue(second["collection_complete"])
        moved = next(row for row in second["candidates"] if row["position_id"] == 202)
        self.assertEqual((moved["disposition"], moved["owner"]), ("excluded", self.other))

    def test_legitimate_departure_does_not_leave_permanent_coverage_gap(self):
        self.expected = 1
        self.owners[202] = self.other
        result = self.collect()
        self.assertTrue(result["collection_complete"])
        self.assertEqual(result["missing"], [])
        self.assertEqual([row["position_id"] for row in result["positions"]], [101])

    def test_reverting_historical_candidate_excluded_only_by_exact_count_proof(self):
        self.expected = 1
        self.owners[202] = RpcError("Synthetic owner read reverted", kind="revert")
        result = self.collect()
        self.assertTrue(result["collection_complete"])
        reverted = next(row for row in result["candidates"] if row["position_id"] == 202)
        self.assertIsNone(reverted["owner"])
        self.assertEqual(reverted["error_kind"], "revert")
        self.assertEqual(reverted["disposition"], "excluded")
        self.assertEqual(reverted["exclusion_basis"], "reconciled_current_owner_count")

    def test_revert_without_count_proof_remains_unresolved_and_partial(self):
        self.owners[202] = RpcError("Synthetic owner read reverted", kind="revert")
        result = self.collect()
        self.assertFalse(result["ownership_complete"])
        self.assertFalse(result["collection_complete"])
        self.assertTrue(result["history_complete"])
        reverted = next(row for row in result["candidates"] if row["position_id"] == 202)
        self.assertEqual(reverted["disposition"], "ownership_unresolved")
        self.assertNotIn("exclusion_basis", reverted)
        self.assertEqual([row["position_id"] for row in result["positions"]], [101])

    def test_zero_balance_is_valid_without_event_history(self):
        self.expected = 0
        self.history_error = RpcError("No history available", kind="pruned")
        result = self.collect()
        self.assertTrue(result["collection_complete"])
        self.assertTrue(result["ownership_complete"])
        self.assertFalse(result["history_complete"])
        self.assertEqual(result["positions"], [])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(self.queries, [])
        self.assertFalse(result["discovery"]["event_scan_required"])

    def test_missing_older_history_preserves_recent_position_as_partial_evidence(self):
        self.transfers = [(101, self.block), (202, self.block - core.MAX_LOG_BLOCKS)]
        self.history_error = RpcError("Missing older history", kind="pruned")
        self.history_error_before = self.block - core.MAX_LOG_BLOCKS + 1
        result = self.collect()
        self.assertFalse(result["ownership_complete"])
        self.assertFalse(result["collection_complete"])
        self.assertFalse(result["history_complete"])
        self.assertEqual(result["ownership_status"], "partial")
        self.assertEqual(result["discovery"]["failure_kind"], "pruned")
        self.assertEqual(result["expected_owned_count"], 2)
        self.assertEqual(result["observed_owned_count"], 1)
        self.assertEqual([row["position_id"] for row in result["positions"]], [101])
        self.assertEqual(result["positions"][0]["fees0_raw"], 4 * self.liquidities[101])
        coverage = self.ctx.result["coverage"]["v4_positions"]
        self.assertFalse(coverage["collection_complete"])
        self.assertEqual(coverage["observed_owned_count"], 1)
        self.assertEqual(coverage["ownership_status"], "partial")

    def test_unavailable_incoming_history_does_not_use_dated_positions(self):
        self.history_error = RpcError("Missing history", kind="pruned")
        result = self.collect()
        self.assertFalse(result["ownership_complete"])
        self.assertFalse(result["collection_complete"])
        self.assertEqual(result["positions"], [])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["expected_owned_count"], 2)

    def test_complete_event_history_with_count_mismatch_is_not_complete_ownership(self):
        self.expected = 3
        result = self.collect()
        self.assertTrue(result["history_complete"])
        self.assertFalse(result["ownership_complete"])
        self.assertFalse(result["collection_complete"])
        self.assertEqual(result["observed_owned_count"], 2)
        self.assertEqual(result["discovery"]["status"], "partial")
        self.assertEqual({row["position_id"] for row in result["positions"]}, {101, 202})
        self.assertTrue(all(row["status"] == "observed" for row in result["positions"]))

    def test_historical_candidate_cap_preserves_verified_position_but_not_aggregate(self):
        self.owners = {token_id: self.other for token_id in range(1, 130)}
        self.owners.update({1: self.owner, 129: self.owner})
        self.transfers = [(token_id, self.block) for token_id in range(1, 130)]
        result = self.collect()
        self.assertFalse(result["ownership_complete"])
        self.assertFalse(result["collection_complete"])
        self.assertEqual(len(result["candidates"]), 128)
        self.assertEqual([row["position_id"] for row in result["positions"]], [129])
        self.assertEqual(result["discovery"]["failure_kind"], "coverage")
        self.assertEqual(result["observed_owned_count"], 1)

    def test_recent_exact_universe_stops_before_irrelevant_historical_candidates(self):
        self.expected = 1
        self.owners = {token_id: self.other for token_id in range(1, 130)}
        self.owners[129] = self.owner
        self.transfers = [(token_id, self.block) for token_id in range(1, 130)]
        result = self.collect()
        self.assertTrue(result["collection_complete"])
        self.assertEqual([row["position_id"] for row in result["positions"]], [129])
        self.assertEqual([row["position_id"] for row in result["candidates"]], [129])

    def test_owned_count_over_limit_retains_safe_position_evidence(self):
        self.expected = 129
        result = self.collect()
        self.assertFalse(result["ownership_complete"])
        self.assertFalse(result["collection_complete"])
        self.assertEqual(result["expected_owned_count"], 129)
        self.assertEqual({row["position_id"] for row in result["positions"]}, {101, 202})

    def test_duplicate_incoming_receipts_do_not_inflate_current_count(self):
        self.expected = 3
        self.transfers.append((202, self.block))
        result = self.collect()
        self.assertFalse(result["ownership_complete"])
        self.assertEqual(result["observed_owned_count"], 2)
        self.assertEqual({row["position_id"] for row in result["candidates"]}, {101, 202})
        self.assertEqual([args[0] for _, method, args in self.reads if method == "ownerOf"], [202, 101])

    def test_zero_liquidity_owned_nft_has_zero_principal_and_fees(self):
        self.liquidities[101] = 0
        result = self.collect()
        self.assertTrue(result["collection_complete"])
        row = next(row for row in result["positions"] if row["position_id"] == 101)
        self.assertEqual((row["liquidity_raw"], row["amount0_raw"], row["amount1_raw"],
                          row["fees0_raw"], row["fees1_raw"]), (0, 0, 0, 0, 0))

    def test_storage_liquidity_conflict_propagates_integrity_failure(self):
        self.bad_stored_liquidity = True
        with self.assertRaises(RpcError) as failure:
            self.collect()
        self.assertEqual(failure.exception.kind, "integrity")

    def test_permission_and_integrity_failures_are_not_partial_successes(self):
        for kind in ("permission", "integrity"):
            for method in ("ownerOf", "getPoolAndPositionInfo", "extsload"):
                with self.subTest(kind=kind, method=method):
                    self.failures = {method: RpcError("Synthetic blocked read", kind=kind)}
                    with self.assertRaises(RpcError) as failure:
                        self.collect()
                    self.assertEqual(failure.exception.kind, kind)
            self.failures = {}
            self.history_error = RpcError("Synthetic blocked history", kind=kind)
            with self.subTest(kind=kind, method="eth_getLogs"):
                with self.assertRaises(RpcError) as failure:
                    self.collect()
                self.assertEqual(failure.exception.kind, kind)
            self.history_error = None

    def test_changed_pool_manager_is_not_followed_or_hidden_as_coverage_only(self):
        self.bound_manager = self.other
        with self.assertRaises(RpcError) as failure:
            self.collect()
        self.assertEqual(failure.exception.kind, "integrity")
        self.assertEqual(self.reads, [(self.pm, "poolManager", ())])
        self.assertEqual(self.queries, [])


if __name__ == "__main__":
    unittest.main()

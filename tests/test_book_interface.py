"""Synthetic ABI vectors, not chain captures or deployed settlement verification.

Only the existing codec is exercised. Skill/host response cases live separately
in fixtures/book_acceptance.json; this module does not simulate a collector.
"""
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from netstack_core import RpcError, _decode_outputs, decode_event, keccak256, load_json


PLAYER = "0x" + "11" * 20
DESK = "0x" + "22" * 20


def words(*values):
    """Hand-authored 32-byte ABI words; deliberately independent of the ABI."""
    return "0x" + "".join((value % (1 << 256)).to_bytes(32, "big").hex() for value in values)


def raw_event(signature, indexed, data):
    return {"address": DESK,
            "topics": ["0x" + keccak256(signature.encode("ascii")).hex(),
                       *(words(value) for value in indexed)],
            "data": words(*data), "blockNumber": "0x64", "transactionIndex": "0x0",
            "logIndex": "0x1", "transactionHash": "0x" + "aa" * 32,
            "blockHash": "0x" + "bb" * 32, "removed": False}


class BookInterfaceDecoding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.abi = load_json("assets/analytics/book-interface.json")["abi"]

    def decode(self, name, raw):
        item = next(item for item in self.abi if item.get("name") == name)
        return _decode_outputs(item, raw)

    def market_words(self, spread=-35):
        # bytes32 team labels, signed spread, times, unknown enums, scores,
        # then six distinct monetary/index words in publisher tuple order.
        return (int.from_bytes(b"FAV".ljust(32, b"\0"), "big"),
                int.from_bytes(b"DOG".ljust(32, b"\0"), "big"),
                spread, 1_800_000_000, 1_800_003_600, 254, 253, 27, 24,
                101, 202, 303, 404, (1 << 128) - 1, 606, 1_250_000_000)

    def bet_words(self, market_id=(1 << 32) - 1, settled=0, payout=0):
        return (int(PLAYER, 16), market_id, 1, 1, settled, 65535,
                (1 << 64) - 1, 100, 9, 1_000_000_000, 7, payout)

    def test_market_signed_spread_unknown_enums_and_fee_positions(self):
        market = self.decode("marketOf", words(*self.market_words()))
        self.assertEqual(market["favourite"], "0x" + b"FAV".ljust(32, b"\0").hex())
        self.assertEqual(market["underdog"], "0x" + b"DOG".ljust(32, b"\0").hex())
        self.assertEqual(market["spreadTenths"], -35)
        self.assertEqual((market["state"], market["result"]), (254, 253))
        self.assertEqual((market["feesPot"], market["feesSleeve"]), ((1 << 128) - 1, 606))
        self.assertEqual(market["indexAtGrade"], 1_250_000_000)
        for spread in (-(1 << 31), (1 << 31) - 1):
            with self.subTest(spread=spread):
                self.assertEqual(self.decode("marketOf", words(*self.market_words(spread)))["spreadTenths"], spread)

    def test_market_rejects_noncanonical_spread_fee_overflow_and_truncation(self):
        vectors = {}
        # A negative int32 must be sign-extended across the whole ABI word.
        vectors["missing sign extension"] = words(*self.market_words((1 << 32) - 35))
        fields = list(self.market_words())
        fields[13] = 1 << 128
        vectors["uint128 fee overflow"] = words(*fields)
        vectors["missing grade index word"] = words(*self.market_words()[:-1])
        for reason, raw in vectors.items():
            with self.subTest(reason=reason), self.assertRaises(RpcError):
                self.decode("marketOf", raw)

    def test_bet_market_id_is_uint32_but_placement_id_and_amount_are_uint256(self):
        bet = self.decode("betOf", words(*self.bet_words()))
        self.assertEqual(bet["marketId"], (1 << 32) - 1)
        self.assertEqual(bet["placedAt"], (1 << 64) - 1)
        self.assertEqual(bet["feeBps"], 65535)
        with self.assertRaises(RpcError):
            self.decode("betOf", words(*self.bet_words(market_id=1 << 32)))
        raw = raw_event(
            "BetPlaced(uint256,address,uint256,uint8,bool,uint256,uint256,uint16,uint256,uint256)",
            (1 << 200, int(PLAYER, 16), 1 << 32),
            (1, 0, (1 << 255) + 17, 23, 65535, (1 << 128) + 29, 1_100_000_000))
        values = decode_event(raw, self.abi)["values"]
        self.assertEqual(values["player"], PLAYER)
        self.assertEqual((values["betId"], values["marketId"]), (1 << 200, 1 << 32))
        self.assertIs(values["riskOff"], False)
        self.assertEqual(values["amount"], (1 << 255) + 17)
        self.assertEqual((values["reserve"], values["feeBps"], values["fee"]), (23, 65535, (1 << 128) + 29))

    def test_bet_zero_payout_preserves_settlement_flag(self):
        # Zero payout alone cannot distinguish unclaimed/graded from settled loss.
        for flag in (0, 1):
            with self.subTest(settled=flag):
                bet = self.decode("betOf", words(*self.bet_words(settled=flag)))
                self.assertIs(bet["settled"], bool(flag))
                self.assertIs(bet["riskOff"], True)
                self.assertEqual((bet["wager"], bet["payout"]), (7, 0))
        with self.assertRaises(RpcError):
            self.decode("betOf", words(*self.bet_words(settled=2)))

    def test_settlement_keeps_false_win_and_nonzero_push_credit(self):
        # Classification still needs market result/state; won=false is not loss.
        raw = raw_event("Settled(uint256,address,uint256,bool,uint256,uint256,uint256)",
                        (19, int(PLAYER, 16), 7), (0, 97, 3, 97))
        values = decode_event(raw, self.abi)["values"]
        self.assertIs(values["won"], False)
        self.assertEqual((values["wager"], values["fee"], values["payout"]), (97, 3, 97))
        graded = raw_event("Graded(uint256,uint8,uint8,uint8,uint256)",
                           (7,), (24, 24, 2, (1 << 128) + 5))
        result = decode_event(graded, self.abi)["values"]
        self.assertEqual(result["result"], 2)
        self.assertEqual(result["indexAtGrade"], (1 << 128) + 5)

    def test_fee_split_retains_distinct_allocations_without_narrowing(self):
        raw = raw_event("FeeSplit(uint256,uint256,uint256,uint256)",
                        (1 << 32, 1 << 200), ((1 << 255) + 1, (1 << 255) - 1))
        values = decode_event(raw, self.abi)["values"]
        self.assertEqual((values["marketId"], values["betId"]), (1 << 32, 1 << 200))
        self.assertEqual(values["potHalf"], (1 << 255) + 1)
        self.assertEqual(values["sleeveHalf"], (1 << 255) - 1)


if __name__ == "__main__":
    unittest.main()

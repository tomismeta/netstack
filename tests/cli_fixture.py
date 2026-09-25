"""Synthetic raw RPC launcher for the real CLI; never contacts a network.

Usage: python3 -I -B tests/cli_fixture.py SCENARIO [analytics arguments...]
Without analytics arguments this runs `rfv --scope core --deadline 8`.
`predict` defaults to `predict --series 2 --deadline 8`. Other scenarios are
success, read-failure, reconciliation-mismatch, header-mismatch,
header-unavailable, stop, deadline, and checkpoint-failure. The last requires
--output; it keeps the last good file as PATH.before-failure and obstructs PATH
with a directory during the final header response. All values are synthetic.
"""
import json
from pathlib import Path
import runpy
import signal
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import netstack_core as core


BLOCK_HASH = "0x" + "bb" * 32
OTHER_HASH = "0x" + "cc" * 32
SCENARIOS = (
    "success", "read-failure", "reconciliation-mismatch", "header-mismatch",
    "header-unavailable", "stop", "deadline", "checkpoint-failure", "predict",
)


class FixtureViolation(BaseException):
    """Bypass analytics' exception-to-JSON handling for fixture mistakes."""


def require(condition, message):
    if not condition:
        raise FixtureViolation(message)


def word(value):
    if isinstance(value, str):
        value = int(value, 16)
    return int(value).to_bytes(32, "big").hex()


def words(*values):
    # Deliberately independent of the production ABI encoder and decoder.
    return "0x" + "".join(word(value) for value in values)


def text(value):
    raw = value.encode("utf-8")
    return words(32, len(raw)) + raw.hex() + "00" * (-len(raw) % 32)


class Fixture:
    def __init__(self, scenario, output=None):
        self.scenario = scenario
        self.output = output
        self.headers = 0
        self.members = 0
        self.stopped = False
        self.calls = {}
        self.code_addresses = set()
        self.triggers = {}
        if scenario == "predict":
            self.predict()
        else:
            self.reserves()

    def add(self, address, signature, result, args=(), trigger=None):
        selector = "0x" + core.keccak256(signature.encode("ascii"))[:4].hex()
        calldata = selector + "".join(word(value) for value in args)
        key = (address, calldata)
        require(key not in self.calls, "Duplicate fixture call")
        self.calls[key] = result
        self.code_addresses.add(address)
        if trigger:
            self.triggers[key] = trigger

    def reserves(self):
        a = {name: row["address"] for name, row in core.resolve_routes("reserves").items()
             if name != "_route"}
        # Same small, coherent 100 cash / 100 vault / half-owned pair as
        # test_reserves.Snapshot. This is not a recorded financial snapshot.
        rfv = 298 * 10**18 - (self.scenario == "reconciliation-mismatch")
        for name, value in (("rfv", rfv), ("liquidUsdg", 100 * 10**18),
                            ("morphoAssets", 100 * 10**18),
                            ("backingPerToken", 298 * 10**18 // 10)):
            self.add(a["treasury"], name + "()", words(value))
        for getter, target in (("net", "net"), ("usdg", "usdg"),
                               ("morphoVault", "vault"), ("canonicalPair", "pair")):
            self.add(a["treasury"], getter + "()", words(a[target]))
        self.add(a["usdg"], "decimals()", words(6))
        self.add(a["usdg"], "balanceOf(address)", words(100 * 10**6), (a["treasury"],))
        self.add(a["net"], "decimals()", words(9))
        self.add(a["net"], "totalSupply()", words(10 * 10**9))
        self.add(a["vault"], "asset()", words(a["usdg"]), trigger="after_cash")
        self.add(a["vault"], "decimals()", words(18))
        self.add(a["vault"], "balanceOf(address)", words(80 * 10**18), (a["treasury"],))
        self.add(a["vault"], "convertToAssets(uint256)", words(100 * 10**6),
                 (80 * 10**18,), trigger="vault_assets")
        self.add(a["pair"], "token0()", words(a["net"]))
        self.add(a["pair"], "token1()", words(a["usdg"]))
        self.add(a["pair"], "getReserves()", words(100 * 10**9, 100 * 10**6, 9))
        self.add(a["pair"], "totalSupply()", words(1000))
        self.add(a["pair"], "balanceOf(address)", words(500), (a["treasury"],))
        self.add(a["pair"], "decimals()", words(18))

    def predict(self):
        a = {name: row["address"] for name, row in core.resolve_routes("predict").items()
             if name != "_route"}
        a["net"] = core.resolve_routes("reserves")["net"]["address"]
        higher, lower = "0x" + "11" * 20, "0x" + "22" * 20
        desk_values = {
            "seriesCount": 100, "halted": False, "minTicket": 10**6,
            "vault": a["house"], "usdg": a["usdg"], "sleeve": a["sleeve"],
            "treasury": a["treasury"], "reservedUsdg": 20 * 10**6,
            "pendingNetUsdg": 3 * 10**6, "prizeCarry": 0, "net": a["net"],
            "owner": "0x" + "33" * 20, "grader": "0x" + "44" * 20,
            "markPrice": 6 * 10**17,
        }
        for name, value in desk_values.items():
            self.add(a["desk"], name + "()", words(value))
        for name, value in (("desk", a["desk"]), ("usdg", a["usdg"]), ("wired", True)):
            self.add(a["house"], name + "()", words(value))
        self.add(a["usdg"], "decimals()", words(6))
        self.code_addresses.update(a[name] for name in ("net", "sleeve", "treasury"))
        # Static series tuple, ABI order; no production output encoder is used.
        self.add(a["desk"], "series(uint256)", words(
            1, 10, 20, 30, 40, 0, 2 * 10**18, 3 * 10**18,
            higher, lower, 12 * 10**18, 8 * 10**18, 30 * 10**6,
            5 * 10**6, 35 * 10**6, 11 * 10**6, 10**5, 4 * 10**4,
            6 * 10**4, 4 * 10**17, 0, 0, 0, False, core.ZERO, 0,
        ), (2,))
        for token, name, symbol, supply in (
            (higher, "Synthetic Higher", "HIGHER", 12 * 10**18),
            (lower, "Synthetic Lower", "LOWER", 8 * 10**18)):
            self.add(token, "decimals()", words(18))
            self.add(token, "totalSupply()", words(supply))
            self.add(token, "name()", text(name))
            self.add(token, "symbol()", text(symbol))

    def response(self, request):
        require(not self.stopped, "Retrieval resumed after cancellation")
        self.members += 1
        require(self.members <= 128, "Fixture request bound exceeded")
        require(request.get("jsonrpc") == "2.0" and type(request.get("id")) is int,
                "Malformed RPC request")
        method, params = request["method"], request["params"]
        envelope = {"jsonrpc": "2.0", "id": request["id"]}
        if method == "eth_chainId":
            require(params == [], "Unexpected chain ID arguments")
            result = "0x1237"
        elif method == "eth_getBlockByNumber":
            require(params in (["latest", False], ["0xa", False]), "Unexpected header request")
            if params[0] == "latest":
                result = {"number": "0xc", "timestamp": "0x1b", "hash": "0x" + "aa" * 32}
            else:
                self.headers += 1
                require(self.headers <= 2, "Unexpected extra header read")
                result = {"number": "0xa", "timestamp": "0x19", "hash": BLOCK_HASH}
                if self.headers == 2:
                    if self.scenario == "header-mismatch":
                        result["hash"] = OTHER_HASH
                    elif self.scenario == "header-unavailable":
                        result = None
                    elif self.scenario == "checkpoint-failure":
                        require(self.output is not None, "Checkpoint failure requires --output")
                        backup = self.output.with_name(self.output.name + ".before-failure")
                        require(not backup.exists(), "Checkpoint backup already exists")
                        self.output.rename(backup)
                        self.output.mkdir()
        elif method == "eth_getCode":
            require(len(params) == 2 and params[1] == "0xa"
                    and params[0] in self.code_addresses, "Unexpected code request")
            result = "0x6000"
        elif method == "eth_call":
            require(len(params) == 2 and params[1] == "0xa", "Unpinned contract read")
            require(set(params[0]) == {"to", "data"}, "Unexpected contract call fields")
            key = (params[0]["to"], params[0]["data"])
            require(key in self.calls, "Unexpected contract or calldata: " + repr(key))
            trigger = self.triggers.get(key)
            if trigger == "after_cash" and self.scenario in ("stop", "deadline"):
                self.stopped = True
                if self.scenario == "stop":
                    signal.raise_signal(signal.SIGTERM)
                else:
                    # Real collection deadline, not a fabricated StopRun/result.
                    while True:
                        signal.pause()
                raise FixtureViolation("Cancellation did not interrupt retrieval")
            if trigger == "vault_assets" and self.scenario == "read-failure":
                return dict(envelope, error={"code": -32000, "message": "historical state unavailable"})
            result = self.calls[key]
        else:
            raise FixtureViolation("Unexpected RPC method: " + str(method))
        return dict(envelope, result=result)

    def connection(self, host, port, *, timeout, context):
        require(host == core.RPC_HOST and port == 443 and timeout > 0,
                "Unexpected transport destination")
        return Connection(self)


class Connection:
    status = 200

    def __init__(self, fixture):
        self.fixture = fixture
        self.body = b""

    def request(self, method, path, body, headers):
        require(method == "POST" and path == "/", "Unexpected HTTP method or path")
        payload = json.loads(body)
        result = ([self.fixture.response(item) for item in payload]
                  if isinstance(payload, list) else self.fixture.response(payload))
        self.body = json.dumps(result, separators=(",", ":")).encode("ascii")
        self.length = len(self.body)

    def getresponse(self):
        return self

    def getheader(self, name, default=None):
        return str(self.length) if name == "Content-Length" else default

    def read(self, size):
        # Exercise incremental bounded transport reads, not just JSON decoding.
        count = min(size, 73)
        result, self.body = self.body[:count], self.body[count:]
        return result

    def close(self):
        pass


def forbid_network(event, args):
    if event.startswith("socket."):
        raise FixtureViolation("Real network operation forbidden: " + event)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in SCENARIOS:
        raise SystemExit("Usage: cli_fixture.py " + "|".join(SCENARIOS) + " [analytics arguments...]")
    scenario = sys.argv[1]
    arguments = sys.argv[2:]
    if not arguments:
        arguments = (["predict", "--series", "2"] if scenario == "predict"
                     else ["rfv", "--scope", "core"]) + ["--deadline", "8"]
    output = None
    for index, argument in enumerate(arguments):
        if argument == "--output" and index + 1 < len(arguments):
            output = Path(arguments[index + 1])
        elif argument.startswith("--output="):
            output = Path(argument.split("=", 1)[1])
    sys.addaudithook(forbid_network)
    fixture = Fixture(scenario, output)
    sys.argv = [str(ROOT / "scripts" / "analytics.py"), *arguments]
    with patch.object(core, "_FixedHTTPSConnection", fixture.connection):
        runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()

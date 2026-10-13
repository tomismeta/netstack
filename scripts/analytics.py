#!/usr/bin/env python3
"""Optional deterministic read-only analytics. No installation or wallet access."""
import time

_PROCESS_STARTED = time.monotonic()
import sys

sys.dont_write_bytecode = True
from pathlib import Path

# Isolated Python (-I) deliberately omits the script directory from sys.path.
_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIRECTORY))

import argparse
import hashlib
import math
import os
import re
import select

from netstack_core import Context, MAX_LOG_BLOCKS, RpcError, SERIALIZATION_RESERVE, StopRun, load_json, serialize_result
from netstack_output import full_fallback, summarize_advance, summarize_rfv


class ArgumentError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse messages can contain arbitrary user input; do not echo it.
        raise ArgumentError("Invalid arguments; use --help for accepted read-only options")


def positive_seconds(text):
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive number") from exc
    if not math.isfinite(value) or not 0 < value <= 600:
        raise argparse.ArgumentTypeError("must be positive and at most 600 seconds")
    return value


def positive_days(text):
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive number") from exc
    if not math.isfinite(value) or value <= 0 or value > 1000000:
        raise argparse.ArgumentTypeError("must be finite, positive and at most 1000000 days")
    return value


def block_spec(text):
    if text != "latest-2" and (len(text) > 78 or not re.fullmatch(r"0|[1-9][0-9]*", text)):
        raise argparse.ArgumentTypeError("must be latest-2 or a nonnegative block number")
    return text

def series_id(text):
    if len(text) > 78 or not re.fullmatch(r"[1-9][0-9]*", text) or int(text) >= 2**256:
        raise argparse.ArgumentTypeError("must be a positive uint256 series ID")
    return int(text)

def market_query(text):
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}|[A-Za-z0-9][A-Za-z0-9._-]{0,63}", text):
        raise argparse.ArgumentTypeError("must be a market symbol or 20-byte hexadecimal address")
    return text

def bounded_count(text, maximum):
    value = series_id(text)
    if value > maximum:
        raise argparse.ArgumentTypeError("enumeration limit exceeds the supported bound")
    return value


def historical_block(text):
    value = block_spec(text)
    if value == "latest-2":
        raise argparse.ArgumentTypeError("must be an explicit nonnegative block number")
    return int(value)


def account_address(text):
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", text):
        raise argparse.ArgumentTypeError("must be a 20-byte hexadecimal address")
    return text.lower()

def transaction_hash(text):
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", text):
        raise argparse.ArgumentTypeError("must be a 32-byte hexadecimal transaction hash")
    return text.lower()





def parser():
    result = Parser(
        description="Read-only Robinhood mainnet analytics using one pinned block and one HTTPS RPC selected before the run.",
        epilog="NETSTACK_RPC_URL selects a host-authorized HTTPS endpoint; absent uses the public RPC. No credential CLI arguments, wallet, proxy, redirect, provider failover, installation, or write RPC. JSON is emitted even for partial collections. Exit 0: requested collection completed; 2: partial/blocked; 1: invalid arguments/fatal error.")
    commands = result.add_subparsers(dest="command", required=True)
    for command, help_text in (("lp", "NET/USDG v2 LP holders, flows and conditional gross fees"),
                               ("predict", "selected Predict Desk series and observed trading flows"),
                               ("house", "selected House Vault accounts, queues and observed cash flows"),
                               ("rfv", "reconciled Core RFV and RPC-backed Sleeve asset accounting"),
                               ("advance", "NET Advance positions, holders, totals, capacity and parameters"),
                               ("netlong", "discovered futures OI and real-token margin debt/exposure"),
                               ("netlong-revenue", "bounded NetLong fees, balance bridges and equity/accrual evidence; never total profit"),
                               ("premiumseller", "fresh PremiumSeller NET sales, realized prices and Treasury USDG remittances"),
                               ("sleeve-bonds", "Sleeve bond inventory, subscription flows and claims"),
                               ("credit", "Credit vault, allocation and Loopback lending evidence"),
                               ("book", "THE BOOK market, wager and settlement evidence"),
                               ("receipts", "bounded selected-emitter event and receipt research, not revenue totals")):
        child = commands.add_parser(command, help=help_text, description=help_text)
        child.add_argument("--deadline", type=positive_seconds, default=120.0, metavar="SECONDS",
                           help="whole-process walltime, including a 2-second serialization reserve (default: 120; maximum: 600)")
        child.add_argument("--block", type=block_spec, default="latest-2", metavar="BLOCK",
                           help="latest-2 or an explicit nonnegative block number (default: latest-2)")
        if command == "lp":
            child.add_argument("--since-days", type=positive_days, default=7.0, metavar="DAYS",
                               help="exact historical fee interval ending at the pinned block (default: 7)")
        elif command == "premiumseller":
            child.add_argument("--since-days", type=positive_days, default=None, metavar="DAYS",
                               help="historical window ending at the pinned block (default: full deployment history)")
        else:
            child.set_defaults(since_days=None)
        if command == "predict":
            child.add_argument("--series", type=series_id, metavar="ID",
                               help="single-series pinned snapshot only; no logs, history or quote (default: all series and history)")
        if command == "advance":
            child.add_argument("action", nargs="?", choices=("provenance",),
                               help="offline Desk/Zap catalog provenance; no RPC calls")
            child.add_argument("--view", choices=("positions", "holders", "totals", "capacity", "params"), default="totals",
                               help="requested pinned evidence view (default: totals); capacity/params do not enumerate positions")
        if command == "netlong":
            child.add_argument("--product", choices=("all", "futures", "margin"), default="all",
                               help="discover both product families or one selected family (default: all)")
            child.add_argument("--market", type=market_query, metavar="SYMBOL_OR_ADDRESS",
                               help="one unambiguous symbol, futures desk address or margin token address")
        if command == "credit":
            child.add_argument("--account", type=account_address,
                               help="public account whose Credit shares and market positions should be inspected")
            child.add_argument("--max-markets", type=lambda text: bounded_count(text, 256), default=32, metavar="COUNT",
                               help="market enumeration limit (default: 32; maximum: 256)")
            child.add_argument("--max-adapters", type=lambda text: bounded_count(text, 128), default=16, metavar="COUNT",
                               help="adapter enumeration limit (default: 16; maximum: 128)")
        if command == "sleeve-bonds":
            child.add_argument("--account", type=account_address,
                               help="public account whose bond notes should be inspected")
            child.add_argument("--history", action="store_true",
                               help="include bounded deployment-to-snapshot bond event history")
            child.add_argument("--max-notes", type=lambda text: bounded_count(text, 4096), default=128, metavar="COUNT",
                               help="per-account note enumeration limit (default: 128; maximum: 4096)")
        if command == "book":
            child.add_argument("--market-id", dest="market_ids", type=series_id, action="append", default=[], metavar="ID",
                               help="inspect a specific market; repeat for additional markets")
            child.add_argument("--bet-id", dest="bet_ids", type=series_id, action="append", default=[], metavar="ID",
                               help="inspect a specific bet; repeat for additional bets")
            child.add_argument("--max-markets", type=lambda text: bounded_count(text, 128), default=8, metavar="COUNT",
                               help="recent-market enumeration limit (default: 8; maximum: 128)")
            child.add_argument("--max-bets", type=lambda text: bounded_count(text, 512), default=32, metavar="COUNT",
                               help="recent-bet enumeration limit (default: 32; maximum: 512)")
            child.add_argument("--from-block", type=historical_block, metavar="BLOCK",
                               help="opt into event/receipt history from this block through the snapshot")
        if command == "receipts":
            child.add_argument("--catalog", required=True, metavar="assets/contracts/NAME.json",
                               help="one packaged contract catalog; no arbitrary ABI or function calls")
            child.add_argument("--address", type=account_address,
                               help="discovered emitter override; catalog interface applicability remains unverified")
            child.add_argument("--event", action="append", default=[], metavar="NAME_OR_SIGNATURE",
                               help="exact event name or signature; repeat to select several (default: all named nonanonymous events)")
            child.add_argument("--from-block", type=series_id, required=True, metavar="BLOCK",
                               help="positive inclusive interval start; opening code/header is read at BLOCK-1")
            child.add_argument("--chunk-blocks", type=lambda text: bounded_count(text, MAX_LOG_BLOCKS),
                               default=10, metavar="COUNT", help="initial inclusive log chunk size (default: 10; maximum: 100000)")
            child.add_argument("--tx", type=transaction_hash, action="append", default=[], metavar="HASH",
                               help="candidate witness receipt; repeat up to 128 times; only in-interval receipts are included")
        if command == "netlong-revenue":
            interval = child.add_mutually_exclusive_group(required=True)
            interval.add_argument("--from-block", type=series_id, metavar="BLOCK",
                                  help="positive inclusive start; opening accounting state is read at BLOCK-1")
            interval.add_argument("--recent-blocks", type=series_id, metavar="COUNT",
                                  help="positive inclusive block count ending at --block; resolves inside the guarded pinned context")
            child.add_argument("--chunk-blocks", type=lambda text: bounded_count(text, MAX_LOG_BLOCKS),
                               default=10, metavar="COUNT", help="initial inclusive log chunk size (default: 10)")
        if command == "rfv":
            child.add_argument("--scope", choices=("core", "reports", "net-assets"), default="core",
                               help="Core reserves, publisher Reports composition, or adjusted net assets (default: core)")
        if command in ("rfv", "advance", "netlong", "netlong-revenue", "premiumseller", "sleeve-bonds", "credit", "book"):
            child.add_argument("--detail", choices=("summary", "full"), default="full",
                               help="stdout evidence detail (default: full); --output always preserves full checkpoints")
        child.add_argument("--json", action="store_true", help="emit machine-readable JSON (also the default)")
        child.add_argument("--output", metavar="PATH", help="atomic partial/final checkpoint outside the installed package; symlinks refused")
    return result


def _failure(command, message):
    return {"schema_version": 1, "command": command, "snapshot": {}, "metrics": {}, "coverage": {},
            "not_proven": [], "errors": [{"kind": "input", "message": message}],
            "status": "failed", "stopping_reason": "invalid_arguments"}


def _provenance(ctx):
    ctx.check()
    version = load_json("release-manifest.json").get("version")
    files = {}
    modules = ["analytics.py", "netstack_core.py"]
    if ctx.command == "advance":
        modules.extend(("netstack_advance.py", "netstack_output.py"))
    elif ctx.command == "netlong":
        modules.append("netstack_netlong.py")
    elif ctx.command == "netlong-revenue":
        modules.extend(("netstack_netlong_revenue.py", "netstack_netlong.py", "netstack_receipts.py"))
    elif ctx.command == "premiumseller":
        modules.append("netstack_premiumseller.py")
    elif ctx.command == "sleeve-bonds":
        modules.append("netstack_sleeve_bonds.py")
    elif ctx.command == "credit":
        modules.append("netstack_credit.py")
    elif ctx.command == "book":
        modules.append("netstack_book.py")
    elif ctx.command == "receipts":
        modules.append("netstack_receipts.py")
    else:
        modules.extend(("netstack_reserves.py", "netstack_sleeve.py", "netstack_v4.py", "netstack_discovery.py", "netstack_methodology.py", "netstack_output.py") if ctx.command == "rfv"
                       else ("netstack_lp.py",) if ctx.command == "lp" else ("netstack_markets.py",))
    for name in modules:
        ctx.check()
        try:
            with (_SCRIPT_DIRECTORY / name).open("rb") as handle:
                data = handle.read(1024 * 1024 + 1)
        except OSError as exc:
            raise RpcError("Required packaged analytics module is unavailable", kind="package") from exc
        if len(data) > 1024 * 1024:
            raise RpcError("Packaged analytics module exceeds size limit", kind="package")
        files["scripts/" + name] = hashlib.sha256(data).hexdigest()
    ctx.result["provenance"] = {"package_version": version, "runtime_sha256": files,
                                "meaning": "Hashes identify the local code used; they are not an authenticity or deployed-contract verification claim."}
    if ctx.command == "advance":
        interface = load_json("assets/analytics/advance-interface.json")
        ctx.result["provenance"]["analysis"] = {
            "interface": {key: interface[key] for key in
                          ("source_id", "source_url", "source_sha256", "reviewed_on")},
            "runtime_evidence": interface["runtime_evidence"],
            "meaning": "Unofficial independent catalog analysis, not a NetNet publication or current runtime match. Source IDs and JSON Pointer references identify evidence, not extra observations."}


def _pending_coverage(value):
    if isinstance(value, dict):
        if value.get("event_coverage_complete") is False or value.get("collection_complete") is False:
            return True
        return any(_pending_coverage(item) for item in value.values())
    if isinstance(value, list):
        return any(_pending_coverage(item) for item in value)
    return False

def _emit(text, hard_end=None):
    """Do not let a blocked stdout pipe outlive the process deadline."""
    try:
        descriptor = sys.stdout.fileno()
    except (AttributeError, OSError):
        sys.stdout.write(text)
        sys.stdout.flush()
        return True
    blocking = os.get_blocking(descriptor)
    try:
        os.set_blocking(descriptor, False)
        data = memoryview(text.encode("ascii"))
        while data:
            try:
                count = os.write(descriptor, data)
                if count <= 0:
                    return False
                data = data[count:]
            except BlockingIOError:
                remaining = 0.0 if hard_end is None else max(0.0, hard_end - time.monotonic())
                if not remaining or not select.select([], [descriptor], [], remaining)[1]:
                    return False
        return True
    finally:
        os.set_blocking(descriptor, blocking)



def main(argv=None):
    ctx = None
    try:
        args = parser().parse_args(argv)
        if (args.command == "advance" and args.action == "provenance"
                and (args.view != "totals" or args.block != "latest-2")):
            raise ArgumentError("Offline provenance cannot select a live view or block")
    except ArgumentError as exc:
        sys.stdout.write(serialize_result(_failure(None, str(exc))))
        return 1
    result = _failure(args.command, "Analytics initialization failed")
    exit_code = 1
    try:
        remaining = args.deadline - (time.monotonic() - _PROCESS_STARTED)
        if remaining <= 0:
            result = {"schema_version": 1, "command": args.command, "snapshot": {}, "metrics": {},
                      "coverage": {}, "not_proven": [], "errors": [], "status": "partial",
                      "stopping_reason": "deadline_exhausted",
                      "elapsed_seconds": time.monotonic() - _PROCESS_STARTED,
                      "collector_deadline_seconds": args.deadline}
            exit_code = 2
        else:
            offline = args.command == "advance" and args.action == "provenance"
            ctx = Context(args.command, deadline=remaining, output=args.output, offline=offline)
            ctx._started = _PROCESS_STARTED
            ctx._deadline = args.deadline
            ctx._hard_end = _PROCESS_STARTED + args.deadline
            ctx._collect_end = ctx._hard_end - SERIALIZATION_RESERVE
            ctx._arm()
            result = ctx.result
            if args.output is not None:
                ctx._open_output_parent()
            _provenance(ctx)
            if offline:
                from netstack_advance import provenance
                provenance(ctx)
            else:
                if args.command == "receipts":
                    from netstack_receipts import load_catalog
                    args._receipt_catalog = load_catalog(args.catalog, args.event, args.address)
                    if len(args.tx) > 128:
                        raise RpcError("Witness receipt seeds exceed the supported bound", kind="input")
                    if args.block != "latest-2" and args.from_block > int(args.block):
                        raise RpcError("Receipt interval start exceeds closing block", kind="input")
                ctx.pin(args.block)
                if args.command == "netlong-revenue" and args.recent_blocks is not None:
                    if args.recent_blocks > ctx.block:
                        raise RpcError("Recent interval needs a preceding nonnegative opening block", kind="input")
                    args.from_block = ctx.block - args.recent_blocks + 1
                if args.command == "lp":
                    from netstack_lp import run
                elif args.command == "predict":
                    from netstack_markets import run_predict as run
                elif args.command == "rfv":
                    from netstack_reserves import run
                elif args.command == "advance":
                    from netstack_advance import run
                elif args.command == "netlong":
                    from netstack_netlong import run
                elif args.command == "netlong-revenue":
                    from netstack_netlong_revenue import run
                elif args.command == "premiumseller":
                    from netstack_premiumseller import run
                elif args.command == "sleeve-bonds":
                    from netstack_sleeve_bonds import run
                elif args.command == "credit":
                    from netstack_credit import run
                elif args.command == "book":
                    from netstack_book import run
                elif args.command == "receipts":
                    from netstack_receipts import run
                else:
                    from netstack_markets import run_house as run
                run(ctx, args)
                ctx.check()
                if args.command == "receipts":
                    from netstack_receipts import recheck
                    recheck(ctx)
                elif args.command == "netlong-revenue":
                    from netstack_netlong_revenue import recheck
                    recheck(ctx)
                else:
                    ctx.recheck()
                if args.command == "premiumseller":
                    from netstack_premiumseller import prepare_result
                    prepare_result(result)
                elif args.command == "sleeve-bonds":
                    from netstack_sleeve_bonds import prepare_result
                    prepare_result(result)
                elif args.command == "credit":
                    from netstack_credit import prepare_result
                    prepare_result(result)
                elif args.command == "book":
                    from netstack_book import prepare_result
                    prepare_result(result)
                elif args.command == "receipts":
                    from netstack_receipts import prepare_result
                    prepare_result(result)
                elif args.command == "netlong-revenue":
                    from netstack_netlong_revenue import prepare_result
                    result["coverage"]["requested_scope"] = prepare_result(result)["coverage"]["requested_scope"]
                elif args.command in ("predict", "house"):
                    from netstack_markets import prepare_result
                    prepare_result(result)
            requested = result["coverage"].get("requested_scope")
            incomplete = (not requested.get("collection_complete", False) if requested is not None
                          else bool(result["errors"] or _pending_coverage(result["coverage"])))
            if incomplete:
                result["status"] = "partial"
                result["stopping_reason"] = "incomplete_collection"
                exit_code = 2
            else:
                result["status"] = "completed"
                result["stopping_reason"] = "completed_requested_collection"
                exit_code = 0
    except StopRun as exc:
        result["status"] = "partial"
        result["stopping_reason"] = exc.reason
        exit_code = 2
    except RpcError as exc:
        result["errors"].append({"kind": exc.kind, "message": str(exc)})
        result["status"] = "partial" if ctx is not None else "failed"
        result["stopping_reason"] = "rpc_or_evidence_failure"
        exit_code = 2 if ctx is not None else 1
    except KeyboardInterrupt:
        result["status"] = "partial"
        result["stopping_reason"] = "interrupted_by_SIGINT"
        exit_code = 2
    except Exception as exc:
        # Never expose source/provider text, arbitrary paths, credentials or traceback data.
        result["errors"].append({"kind": "fatal", "message": "Internal analytics failure (" + type(exc).__name__ + ")"})
        result["status"] = "failed"
        result["stopping_reason"] = "fatal_error"
        exit_code = 1
    # A useful partial collection can still confirm B when retrieval failed
    # without cancellation or a permission/integrity failure. Never restart after a stop.
    if (ctx is not None and ctx.block is not None and ctx._stopped is None
            and ctx._terminal_error is None
            and result["snapshot"].get("recheck_status") == "not_performed"
            and not any(isinstance(error, dict) and error.get("kind") in ("permission", "integrity")
                        for error in result["errors"])):
        try:
            if args.command == "receipts":
                from netstack_receipts import recheck
                recheck(ctx)
            elif args.command == "netlong-revenue":
                from netstack_netlong_revenue import recheck
                recheck(ctx)
            else:
                ctx.recheck()
        except StopRun as exc:
            result["stopping_reason"] = exc.reason
            result["status"] = "partial"
            exit_code = 2
        except RpcError as exc:
            result["errors"].append({"kind": exc.kind, "message": str(exc)})
            result["status"] = "partial"
            exit_code = 2
    text = None
    checkpoint_status = "not_requested" if args.output is None else "not_confirmed"
    try:
        if ctx is not None:
            ctx.begin_finalization()
            if result.get("snapshot") and result["snapshot"].get("recheck_status") != "confirmed":
                result["snapshot"].setdefault("recheck_status", "not_performed")
                result["snapshot"]["confirmation"] = (
                    "invalid" if result["snapshot"]["recheck_status"] == "mismatch" else "unconfirmed")
            ctx.checkpoint()
            if args.output is not None:
                checkpoint_status = "saved"
            text = ctx._last_json
        else:
            text = serialize_result(result)
    except RpcError as exc:
        result["errors"].append({"kind": exc.kind, "message": str(exc)})
        result["status"] = "partial"
        result["stopping_reason"] = "checkpoint_failure"
        exit_code = 2
        try:
            text = serialize_result(result)
        except (StopRun, KeyboardInterrupt):
            text = ctx.partial_json(ctx._stopped or "deadline_exhausted")
    except (StopRun, KeyboardInterrupt):
        exit_code = 2
        # Reuse a valid aggregate body without repeating expensive serialization.
        text = ctx.partial_json(ctx._stopped or "deadline_exhausted") if ctx is not None else serialize_result(result)
    if args.command in ("rfv", "advance", "netlong", "netlong-revenue", "premiumseller", "sleeve-bonds", "credit", "book") and args.detail == "summary":
        try:
            # Finalization can reuse an older valid checkpoint or add an output
            # error. Project exactly that document, not the mutable ctx.result.
            if args.command == "advance":
                text = summarize_advance(text, checkpoint_status, args.output)
            elif args.command == "netlong":
                from netstack_netlong import summarize
                text = summarize(text, checkpoint_status)
            elif args.command == "netlong-revenue":
                from netstack_netlong_revenue import summarize
                text = summarize(text, checkpoint_status)
            elif args.command == "premiumseller":
                from netstack_premiumseller import summarize
                text = summarize(text, checkpoint_status)
            elif args.command == "sleeve-bonds":
                from netstack_sleeve_bonds import summarize
                text = summarize(text, checkpoint_status)
            elif args.command == "credit":
                from netstack_credit import summarize
                text = summarize(text, checkpoint_status)
            elif args.command == "book":
                from netstack_book import summarize
                text = summarize(text, checkpoint_status)
            else:
                text = summarize_rfv(text, checkpoint_status)
        except (StopRun, KeyboardInterrupt) as exc:
            exit_code = 2
            reason = exc.reason if isinstance(exc, StopRun) else "interrupted_by_SIGINT"
            text = full_fallback(text, checkpoint_status, reason)
    try:
        if ctx is not None:
            ctx._emitting = True
        if not _emit(text, ctx._hard_end if ctx is not None else None):
            return 2
        if ctx is not None and ctx._stopped:
            exit_code = 2
    except (BrokenPipeError, OSError, StopRun, KeyboardInterrupt):
        return 2
    finally:
        if ctx is not None:
            ctx.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

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

from netstack_core import Context, RpcError, SERIALIZATION_RESERVE, StopRun, load_json, serialize_result
from netstack_output import full_fallback, summarize_rfv


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



def parser():
    result = Parser(
        description="Read-only Robinhood mainnet analytics using one pinned block and the fixed public HTTPS RPC.",
        epilog="No wallet, authentication, proxy, redirect, installation, or write RPC. JSON is emitted even for partial collections. Exit 0: requested collection completed; 2: partial/blocked; 1: invalid arguments/fatal error.")
    commands = result.add_subparsers(dest="command", required=True)
    for command, help_text in (("lp", "NET/USDG v2 LP holders, flows and conditional gross fees"),
                               ("predict", "selected Predict Desk series and observed trading flows"),
                               ("house", "selected House Vault accounts, queues and observed cash flows"),
                               ("rfv", "reconciled Core RFV and RPC-backed Sleeve asset accounting")):
        child = commands.add_parser(command, help=help_text, description=help_text)
        child.add_argument("--deadline", type=positive_seconds, default=120.0, metavar="SECONDS",
                           help="whole-process walltime, including a 2-second serialization reserve (default: 120; maximum: 600)")
        child.add_argument("--block", type=block_spec, default="latest-2", metavar="BLOCK",
                           help="latest-2 or an explicit nonnegative block number (default: latest-2)")
        if command == "lp":
            child.add_argument("--since-days", type=positive_days, default=7.0, metavar="DAYS",
                               help="exact historical fee interval ending at the pinned block (default: 7)")
        else:
            child.set_defaults(since_days=None)
        if command == "predict":
            child.add_argument("--series", type=series_id, metavar="ID",
                               help="single-series pinned snapshot only; no logs, history or quote (default: all series and history)")
        if command == "rfv":
            child.add_argument("--scope", choices=("core", "reports", "net-assets"), default="core",
                               help="Core reserves, publisher Reports composition, or adjusted net assets (default: core)")
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
            ctx = Context(args.command, deadline=remaining, output=args.output)
            ctx._started = _PROCESS_STARTED
            ctx._deadline = args.deadline
            ctx._hard_end = _PROCESS_STARTED + args.deadline
            ctx._collect_end = ctx._hard_end - SERIALIZATION_RESERVE
            ctx._arm()
            result = ctx.result
            if args.output is not None:
                ctx._open_output_parent()
            _provenance(ctx)
            ctx.pin(args.block)
            if args.command == "lp":
                from netstack_lp import run
            elif args.command == "predict":
                from netstack_markets import run_predict as run
            elif args.command == "rfv":
                from netstack_reserves import run
            else:
                from netstack_markets import run_house as run
            run(ctx, args)
            ctx.check()
            ctx.recheck()
            requested = result["coverage"].get("requested_scope") if args.command == "rfv" else None
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
    # without cancellation or permission denial. Never restart after a stop.
    if (ctx is not None and ctx.block is not None and ctx._stopped is None
            and result["snapshot"].get("recheck_status") == "not_performed"
            and not any(isinstance(error, dict) and error.get("kind") == "permission"
                        for error in result["errors"])):
        try:
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
    if args.command == "rfv" and args.detail == "summary":
        try:
            # Finalization can reuse an older valid checkpoint or add an output
            # error. Project exactly that document, not the mutable ctx.result.
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

#!/usr/bin/env python3
"""Verify an installed netstack package offline; integrity is not authenticity."""
from pathlib import Path
import argparse
import json
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from netstack_package import read_package, verify_files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Installed package directory (default: this verifier's package)")
    args = parser.parse_args(argv)
    try:
        report = verify_files(read_package(args.root))
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

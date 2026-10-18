"""Coordinate one offline handoff receipt using an explicitly selected SQLite DB."""

import argparse
import sqlite3
import sys
from pathlib import Path

from orchestrator.core.handoff import HandoffError, load_json
from orchestrator.core.handoff_coordinator import ReceiptCoordinator


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--trust", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--receipt-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        packet = args.packet.resolve()
        if any(path.resolve().is_relative_to(packet) for path in
               (args.trust, args.db, args.receipt_dir)):
            raise HandoffError("Trusted record and coordinator state must be outside packet")
        with args.trust.open("rb") as stream:
            trust = load_json(stream.read(1024 * 1024 + 1))
        path, _ = ReceiptCoordinator(args.db, args.receipt_dir).collect(args.packet, trust)
    except (HandoffError, OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        print(f"BLOCKED_CAPABILITY: {exc}", file=sys.stderr)
        return 2
    print(f"COLLECTED: {path}; independent acceptance remains unknown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

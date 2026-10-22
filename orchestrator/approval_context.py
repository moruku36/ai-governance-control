"""Preview-only CLI: python -m orchestrator.approval_context < context.json."""

import json
import sys

from orchestrator.core.approval_context import (
    MAX_CONTEXT_BYTES,
    ApprovalContextError,
    parse_approval_context,
)


def main(argv=None):
    # No command-line values: avoid accidental secret echo by argument parsers.
    if argv is None:
        argv = sys.argv[1:]
    try:
        if argv:
            raise ApprovalContextError("Invalid approval context")
        preview = parse_approval_context(sys.stdin.buffer.read(MAX_CONTEXT_BYTES + 1))
        print(json.dumps(preview.summary(), sort_keys=True, separators=(",", ":")))
        return 0
    except (ApprovalContextError, OSError):
        print("Invalid approval context", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

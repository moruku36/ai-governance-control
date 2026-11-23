"""Offline fixture preview: python -m orchestrator.signed_review_preview < bundle.json."""
import json
import sys

from orchestrator.core.signed_review_preview import (
    MAX_BUNDLE_BYTES,
    SignedReviewPreview,
    preview_signed_review,
)


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        result = (
            SignedReviewPreview("INVALID_FIXTURE_PAYLOAD")
            if argv
            else preview_signed_review(sys.stdin.buffer.read(MAX_BUNDLE_BYTES + 1))
        )
    except OSError:
        result = SignedReviewPreview("INVALID_FIXTURE_PAYLOAD")
    print(json.dumps(result.summary(), sort_keys=True, separators=(",", ":")))
    return 0 if result.reason == "FIXTURE_SIGNED_REVIEW_MATCH" else 2


if __name__ == "__main__":
    raise SystemExit(main())

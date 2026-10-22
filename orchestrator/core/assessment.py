"""Non-authorizing G1 assessment integrity checks; no token or state operations.

All expected bindings must come from separately protected controller records.
Neither a consistent hash nor an assessor reference authenticates a human,
measures a runtime boundary, establishes competence or authorizes an action.
"""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any

import jsonschema

from orchestrator.core.schema import validate_against_schema

CONTRACT_VERSION = "governance-assessment/1"
MAX_ASSESSMENT_BYTES = 64 * 1024
_DIGEST = re.compile(r"[a-f0-9]{64}")


class AssessmentError(ValueError):
    """Malformed, changed or mismatched assessment; not an authorization verdict."""


@dataclass(frozen=True)
class AssessmentRecord:
    """Immutable integrity-checked record. Not an approval or admission result."""

    digest: str
    canonical_json: str


def _canonical(assessment: dict[str, Any]) -> str:
    if type(assessment) is not dict:
        raise AssessmentError("Assessment must be a JSON object")
    try:
        canonical = json.dumps(assessment, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False)
        if len(canonical) > MAX_ASSESSMENT_BYTES:
            raise AssessmentError("Assessment exceeds size limit")
        # Validate the detached JSON representation, not custom mutable objects.
        validate_against_schema(json.loads(canonical), "governance-assessment.schema.json")
    except (TypeError, ValueError, RecursionError, jsonschema.ValidationError):
        # Do not echo caller data, which might accidentally contain sensitive text.
        raise AssessmentError("Invalid or oversized governance assessment") from None
    return canonical


def assessment_digest(assessment: dict[str, Any]) -> str:
    """Hash a schema-valid record for trusted preparation, not self-approval."""
    return hashlib.sha256(_canonical(assessment).encode("ascii")).hexdigest()


def validate_assessment(
    assessment: dict[str, Any], *, expected_task_id: str, expected_repository_id: str,
    expected_spec_digest: str, expected_candidate_digest: str,
    expected_policy_digest: str, expected_assessment_digest: str,
) -> AssessmentRecord:
    """Compare against independent trusted bindings; retain unknowns as data.

    Never populate expected_* from the same untrusted submission. The trusted
    issuer must independently review and retain the full assessment digest.
    expected_candidate_digest must be the controller-held CandidateSeal.digest
    (committed-candidate-binding/1), not a bare TreeSnapshot or legacy digest.
    Successful return permits storage/review only, not execution or promotion.
    """
    canonical = _canonical(assessment)
    record = json.loads(canonical)
    expected = {
        "task_id": expected_task_id, "repository_id": expected_repository_id,
        "spec_digest": expected_spec_digest, "candidate_digest": expected_candidate_digest,
        "policy_digest": expected_policy_digest,
    }
    for key, value in expected.items():
        if not isinstance(value, str) or record[key] != value:
            raise AssessmentError(f"Assessment binding mismatch: {key}")
    if (not isinstance(expected_assessment_digest, str)
            or not _DIGEST.fullmatch(expected_assessment_digest)):
        raise AssessmentError("Trusted assessment digest is required")
    digest = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    if not hmac.compare_digest(digest, expected_assessment_digest):
        raise AssessmentError("Assessment integrity mismatch")
    return AssessmentRecord(digest=digest, canonical_json=canonical)

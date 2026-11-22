"""Synthetic assessment-to-intent bridge; no permission or live effects.

Pins and the expected intent come from independent controller records. In
particular, candidate_seal_digest is the controller-verified CandidateSeal.digest,
not the candidate's tree digest or a worker claim. This bridge checks binding
and a conservative fixture profile, not seal freshness, reviewer identity,
runtime isolation, or evidence authenticity. Never use its result for admission.
"""

import json
import re
from dataclasses import dataclass, field
from hmac import compare_digest
from typing import Any, Literal

from orchestrator.core.assessment import AssessmentError, validate_assessment
from orchestrator.core.operation_intent import (
    OperationAssessment,
    OperationIntent,
    OperationScope,
    evaluate_operation,
)
from orchestrator.core.operation_revision import (
    ObservedRevision,
    RevisionAssessment,
    evaluate_revision_bound_operation,
)

ASSESSMENT_PURPOSE = "synthetic_operation_preview"
_SYNTHETIC_ACTIONS = frozenset({"read", "draft", "send"})
_SHA256 = re.compile(r"[a-f0-9]{64}")


@dataclass(frozen=True, slots=True)
class AssessmentPin:
    task_id: str
    repository_id: str
    specification_digest: str
    candidate_seal_digest: str
    policy_digest: str
    assessment_digest: str


@dataclass(frozen=True, slots=True)
class ReviewedOperationContext:
    """Controller-held snapshot of a prior fixture review, not an approval."""

    assessment_digest: str
    intent: OperationIntent
    target_revision: str


@dataclass(frozen=True, slots=True)
class ReviewConsistency:
    reason: str
    mode: Literal["MANUAL_ONLY"] = field(init=False, default="MANUAL_ONLY")
    execution_authorized: Literal[False] = field(init=False, default=False)


def evaluate_assessed_operation(
    proposal: bytes,
    *,
    assessment: dict[str, Any],
    pin: AssessmentPin,
    expected: OperationIntent,
    observed_input: bytes,
    requester_grant: frozenset[OperationScope],
    task_scope: frozenset[OperationScope],
    expected_revision: str | None = None,
    observed_revision: ObservedRevision | None = None,
) -> OperationAssessment | RevisionAssessment:
    """Preview an offline fixture using only the verified assessment allowlist."""
    if (
        type(pin) is not AssessmentPin
        or type(expected) is not OperationIntent
        or expected.task_id != pin.task_id
    ):
        return OperationAssessment("ASSESSMENT_CONTEXT_INVALID")
    try:
        checked = validate_assessment(
            assessment,
            expected_task_id=pin.task_id,
            expected_repository_id=pin.repository_id,
            expected_spec_digest=pin.specification_digest,
            expected_candidate_digest=pin.candidate_seal_digest,
            expected_policy_digest=pin.policy_digest,
            expected_assessment_digest=pin.assessment_digest,
        )
    except (AssessmentError, OSError):
        return OperationAssessment("ASSESSMENT_REJECTED")

    # Read only the detached representation that matched the independent digest.
    record = json.loads(checked.canonical_json)
    if (
        record["action_id"] != ASSESSMENT_PURPOSE
        or record["data_classification"] != "public"
        or record["unknowns"]
        or record["external_impact"] != "none"
        or record["reversibility"] == "unknown"
        or record["runtime"]["network_scope"] != "none"
        or record["credentials"]["delivery_mode"] != "none"
    ):
        return OperationAssessment("ASSESSMENT_NOT_SYNTHETIC_ELIGIBLE")
    operation_ids = frozenset(record["allowed_operation_ids"])
    if not operation_ids or not operation_ids <= _SYNTHETIC_ACTIONS:
        return OperationAssessment("ASSESSMENT_UNKNOWN_OPERATION")

    args = {
        "expected": expected,
        "observed_input": observed_input,
        "requester_grant": requester_grant,
        "task_scope": task_scope,
        "allowed_operation_ids": operation_ids,
    }
    # The controller's intent, not the proposal version or an allowlist entry,
    # selects the evaluator. Mutable actions can never reach the v1 preview.
    if expected.action == "read":
        if expected_revision is not None or observed_revision is not None:
            return OperationAssessment("UNEXPECTED_REVISION_CONTEXT")
        return evaluate_operation(proposal, **args)
    return evaluate_revision_bound_operation(
        proposal,
        expected_revision=expected_revision,
        observed_revision=observed_revision,
        **args,
    )


def evaluate_review_consistency(
    proposal: bytes,
    *,
    assessment: dict[str, Any],
    pin: AssessmentPin,
    expected: OperationIntent,
    observed_input: bytes,
    requester_grant: frozenset[OperationScope],
    task_scope: frozenset[OperationScope],
    reviewed: ReviewedOperationContext,
    expected_revision: str | None = None,
    observed_revision: ObservedRevision | None = None,
) -> ReviewConsistency:
    """Compare a current draft/send preview to a separately retained fixture snapshot.

    Never build `reviewed` from the new proposal or current controller snapshot.
    This check does not verify a human reviewer, expiry, revocation or a signature,
    and provides neither an approval token nor a result usable for admission.
    """
    if (
        type(reviewed) is not ReviewedOperationContext
        or type(reviewed.assessment_digest) is not str
        or _SHA256.fullmatch(reviewed.assessment_digest) is None
        or type(reviewed.intent) is not OperationIntent
        or type(reviewed.target_revision) is not str
    ):
        return ReviewConsistency("INVALID_REVIEW_CONTEXT")
    if type(expected) is OperationIntent and expected.action == "read":
        return ReviewConsistency("MUTABLE_ACTION_REQUIRED")

    current = evaluate_assessed_operation(
        proposal,
        assessment=assessment,
        pin=pin,
        expected=expected,
        observed_input=observed_input,
        requester_grant=requester_grant,
        task_scope=task_scope,
        expected_revision=expected_revision,
        observed_revision=observed_revision,
    )
    if current.matched_intent is None:
        return ReviewConsistency(current.reason)
    if type(current) is not RevisionAssessment or current.matched_revision is None:
        return ReviewConsistency("REVISION_PREVIEW_REQUIRED")
    # The full assessment digest also binds its validated task, repository,
    # specification, candidate seal and policy. It is not a policy-only digest.
    if not compare_digest(reviewed.assessment_digest, pin.assessment_digest):
        return ReviewConsistency("REVIEW_ASSESSMENT_MISMATCH")
    if reviewed.intent != current.matched_intent:
        return ReviewConsistency("REVIEW_INTENT_MISMATCH")
    if reviewed.target_revision != current.matched_revision:
        return ReviewConsistency("REVIEW_REVISION_MISMATCH")
    return ReviewConsistency("EXACT_REVIEW_CONTEXT_MATCH")

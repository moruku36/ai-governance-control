"""Non-authorizing lifetime and operator checks for synthetic operation reviews."""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from orchestrator.core.operation_assessment_bridge import (
    AssessmentPin,
    ReviewedOperationContext,
    evaluate_review_consistency,
)
from orchestrator.core.operation_intent import OperationIntent, OperationScope
from orchestrator.core.operation_revision import ObservedRevision, is_fixture_revision

_PRINCIPAL = re.compile(r"fixture:principal:[a-z0-9][a-z0-9-]{0,63}")


@dataclass(frozen=True, slots=True)
class FixtureTimedReview:
    """Separately retained review context, issuer and validity interval."""

    reviewed: ReviewedOperationContext
    reviewer_id: str
    reviewer_epoch: str
    issued_at: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class FixtureReviewCheck:
    """Controller's independent UTC-second observation and registry revision pin."""

    checked_at: int
    expected_registry_revision: str


@dataclass(frozen=True, slots=True)
class FixtureOperatorObservation:
    reviewer_id: str
    reviewer_epoch: str
    registry_revision: str
    status: Literal["active", "revoked"]


@dataclass(frozen=True, slots=True)
class ReviewValidityPreview:
    reason: str
    mode: Literal["MANUAL_ONLY"] = field(init=False, default="MANUAL_ONLY")
    execution_authorized: Literal[False] = field(init=False, default=False)
    approval_verified: Literal[False] = field(init=False, default=False)


def _principal(value: object) -> bool:
    return type(value) is str and _PRINCIPAL.fullmatch(value) is not None


def _second(value: object) -> bool:
    return type(value) is int and value >= 0


def evaluate_fixture_review_validity(
    proposal: bytes,
    *,
    assessment: dict[str, Any],
    pin: AssessmentPin,
    expected: OperationIntent,
    observed_input: bytes,
    requester_grant: frozenset[OperationScope],
    task_scope: frozenset[OperationScope],
    review: FixtureTimedReview,
    check: FixtureReviewCheck,
    operator: FixtureOperatorObservation | None,
    expected_revision: str | None = None,
    observed_revision: ObservedRevision | None = None,
) -> ReviewValidityPreview:
    """Re-evaluate exact context, then compare fixture lifetime and reviewer state.

    The retained review, time/registry pin, and operator observation come from
    separate controller fixture sources, never from the proposal. A reviewer
    epoch represents one recorded activation; a reactivation must use a new
    epoch. This function does not verify a signature, read a clock or registry,
    attest to these observations, or confer any kind of approval.
    """
    if (
        type(review) is not FixtureTimedReview
        or not _principal(review.reviewer_id)
        or not is_fixture_revision(review.reviewer_epoch)
        or not _second(review.issued_at)
        or not _second(review.expires_at)
        or review.issued_at >= review.expires_at
    ):
        return ReviewValidityPreview("INVALID_REVIEW_WINDOW")
    if (
        type(check) is not FixtureReviewCheck
        or not _second(check.checked_at)
        or not is_fixture_revision(check.expected_registry_revision)
    ):
        return ReviewValidityPreview("INVALID_VALIDITY_CHECK")

    context = evaluate_review_consistency(
        proposal,
        assessment=assessment,
        pin=pin,
        expected=expected,
        observed_input=observed_input,
        requester_grant=requester_grant,
        task_scope=task_scope,
        reviewed=review.reviewed,
        expected_revision=expected_revision,
        observed_revision=observed_revision,
    )
    if context.reason != "EXACT_REVIEW_CONTEXT_MATCH":
        return ReviewValidityPreview(context.reason)
    if review.reviewer_id == expected.principal_id:
        return ReviewValidityPreview("REVIEWER_IS_REQUESTER")
    if check.checked_at < review.issued_at:
        return ReviewValidityPreview("REVIEW_NOT_YET_VALID")
    if check.checked_at >= review.expires_at:
        return ReviewValidityPreview("REVIEW_EXPIRED")
    if operator is None:
        return ReviewValidityPreview("REVIEWER_OBSERVATION_UNAVAILABLE")
    if (
        type(operator) is not FixtureOperatorObservation
        or not _principal(operator.reviewer_id)
        or not is_fixture_revision(operator.reviewer_epoch)
        or not is_fixture_revision(operator.registry_revision)
        or type(operator.status) is not str
        or operator.status not in ("active", "revoked")
    ):
        return ReviewValidityPreview("INVALID_REVIEWER_OBSERVATION")
    if operator.reviewer_id != review.reviewer_id:
        return ReviewValidityPreview("REVIEWER_ID_MISMATCH")
    if operator.registry_revision != check.expected_registry_revision:
        return ReviewValidityPreview("REVIEWER_REGISTRY_REVISION_MISMATCH")
    if operator.status == "revoked":
        return ReviewValidityPreview("REVIEWER_REVOKED")
    if operator.reviewer_epoch != review.reviewer_epoch:
        return ReviewValidityPreview("REVIEWER_EPOCH_MISMATCH")
    return ReviewValidityPreview("FIXTURE_REVIEW_CURRENT")

"""Read-only outcome comparison for a synthetic support-draft fixture.

The controller supplies a separately retained attempt and an independent fixture
readback. The function neither records an attempt nor reads a destination. It
does not establish provenance, uniqueness, freshness, or actual execution.
"""

import re
from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest
from typing import Literal

from orchestrator.core.operation_intent import MAX_INPUT_BYTES, OperationIntent
from orchestrator.core.operation_revision import is_fixture_revision

_ATTEMPT_ID = re.compile(r"fixture:operation:[a-z0-9][a-z0-9-]{0,63}")
AttemptStage = Literal[
    "denied_before_dispatch",
    "canceled_before_dispatch",
    "awaiting_readback",
    "canceled_after_dispatch",
]
ReadbackKind = Literal["stored", "terminal_failure"]
Outcome = Literal["CONFIRMED", "FAILED", "UNKNOWN", "DENIED", "CANCELED"]


@dataclass(frozen=True, slots=True)
class FixtureDraftAttempt:
    """Controller-held fixture state, not an approval or dispatch receipt."""

    attempt_id: str
    intent: OperationIntent
    stage: AttemptStage
    expected_pre_dispatch_revision: str


@dataclass(frozen=True, slots=True)
class FixtureDraftReadback:
    """One independently obtained fixture observation, not an adapter reply."""

    attempt_id: str
    target_id: str
    destination_id: str
    kind: ReadbackKind
    observed_pre_dispatch_revision: str | None = None
    stored_draft: bytes | None = None


@dataclass(frozen=True, slots=True)
class DraftOutcomePreview:
    outcome: Outcome
    reason: str
    mode: Literal["MANUAL_ONLY"] = field(init=False, default="MANUAL_ONLY")
    execution_authorized: Literal[False] = field(init=False, default=False)
    retry_authorized: Literal[False] = field(init=False, default=False)


def diagnose_draft_outcome(
    attempt: FixtureDraftAttempt,
    *,
    readback: FixtureDraftReadback | None = None,
) -> DraftOutcomePreview:
    """Compare the fixture readback with the retained draft attempt, without side effects.

    For this fixture only, the effect of saving a draft is storage of the exact
    input bytes. Missing evidence is not failure; conflicting evidence stays
    unknown. Even a matching terminal failure does not authorize a retry.
    The readback binds the attempt's observed precondition, not the draft's
    current or post-save revision. Never copy this field from the expected pin.
    """
    if (
        type(attempt) is not FixtureDraftAttempt
        or type(attempt.attempt_id) is not str
        or _ATTEMPT_ID.fullmatch(attempt.attempt_id) is None
        or type(attempt.intent) is not OperationIntent
        or attempt.intent.action != "draft"
        or type(attempt.stage) is not str
        or attempt.stage
        not in (
            "denied_before_dispatch",
            "canceled_before_dispatch",
            "awaiting_readback",
            "canceled_after_dispatch",
        )
    ):
        return DraftOutcomePreview("UNKNOWN", "INVALID_ATTEMPT")
    if not is_fixture_revision(attempt.expected_pre_dispatch_revision):
        return DraftOutcomePreview("UNKNOWN", "EXPECTED_PRE_DISPATCH_REVISION_UNAVAILABLE")

    if attempt.stage in ("denied_before_dispatch", "canceled_before_dispatch"):
        if readback is not None:
            return DraftOutcomePreview("UNKNOWN", "UNEXPECTED_READBACK")
        if attempt.stage == "denied_before_dispatch":
            return DraftOutcomePreview("DENIED", "DENIED_BEFORE_DISPATCH")
        return DraftOutcomePreview("CANCELED", "CANCELED_BEFORE_DISPATCH")
    if readback is None:
        return DraftOutcomePreview("UNKNOWN", "READBACK_UNAVAILABLE")
    if (
        type(readback) is not FixtureDraftReadback
        or type(readback.attempt_id) is not str
        or type(readback.target_id) is not str
        or type(readback.destination_id) is not str
        or type(readback.kind) is not str
        or readback.kind not in ("stored", "terminal_failure")
    ):
        return DraftOutcomePreview("UNKNOWN", "INVALID_READBACK")
    if (
        readback.attempt_id != attempt.attempt_id
        or readback.target_id != attempt.intent.target_id
        or readback.destination_id != attempt.intent.destination_id
    ):
        return DraftOutcomePreview("UNKNOWN", "READBACK_SCOPE_MISMATCH")
    if not is_fixture_revision(readback.observed_pre_dispatch_revision):
        return DraftOutcomePreview("UNKNOWN", "OBSERVED_PRE_DISPATCH_REVISION_UNAVAILABLE")
    if readback.observed_pre_dispatch_revision != attempt.expected_pre_dispatch_revision:
        return DraftOutcomePreview("UNKNOWN", "PRE_DISPATCH_REVISION_MISMATCH")
    if readback.kind == "terminal_failure":
        if readback.stored_draft is not None:
            return DraftOutcomePreview("UNKNOWN", "CONFLICTING_READBACK")
        return DraftOutcomePreview("FAILED", "MATCHED_TERMINAL_FAILURE")
    if type(readback.stored_draft) is not bytes or len(readback.stored_draft) > MAX_INPUT_BYTES:
        return DraftOutcomePreview("UNKNOWN", "DRAFT_CONTENT_UNAVAILABLE")
    if not compare_digest(sha256(readback.stored_draft).hexdigest(), attempt.intent.input_sha256):
        return DraftOutcomePreview("UNKNOWN", "DRAFT_CONTENT_MISMATCH")
    return DraftOutcomePreview("CONFIRMED", "MATCHED_STORED_DRAFT")

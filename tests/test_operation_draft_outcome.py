"""Pure fixture cases: no adapter, endpoint, journal or actual dispatch."""

from dataclasses import asdict, replace
from hashlib import sha256

import pytest

from orchestrator.core.operation_draft_outcome import (
    FixtureDraftAttempt,
    FixtureDraftReadback,
    diagnose_draft_outcome,
)
from orchestrator.core.operation_intent import MAX_INPUT_BYTES, OperationIntent

BODY = b"synthetic support reply"
DRAFT = OperationIntent(
    "TASK-016",
    "fixture:principal:requester",
    "draft",
    "fixture:draft:reply",
    "fixture:store:review",
    None,
    sha256(BODY).hexdigest(),
)
ATTEMPT = FixtureDraftAttempt(
    "fixture:operation:draft-1", DRAFT, "awaiting_readback", "fixture:revision:r1"
)
# These literals model a separately observed effect, not data taken from the attempt.
STORED = FixtureDraftReadback(
    "fixture:operation:draft-1",
    "fixture:draft:reply",
    "fixture:store:review",
    "stored",
    observed_pre_dispatch_revision="fixture:revision:r1",
    stored_draft=BODY,
)


def assert_outcome(outcome, reason, *, attempt=ATTEMPT, readback=None):
    result = diagnose_draft_outcome(attempt, readback=readback)
    assert (result.outcome, result.reason) == (outcome, reason)
    assert result.mode == "MANUAL_ONLY"
    assert result.execution_authorized is False
    assert result.retry_authorized is False
    return result


def test_restarted_diagnostic_can_confirm_lost_reply_only_from_exact_readback():
    assert_outcome("UNKNOWN", "READBACK_UNAVAILABLE")

    # Model reloading the retained fixture, not recovering runtime state.
    retained = FixtureDraftAttempt(
        ATTEMPT.attempt_id, DRAFT, ATTEMPT.stage, ATTEMPT.expected_pre_dispatch_revision
    )
    first = assert_outcome("CONFIRMED", "MATCHED_STORED_DRAFT", attempt=retained, readback=STORED)
    assert diagnose_draft_outcome(retained, readback=STORED) == first
    assert set(asdict(first)) == {
        "outcome",
        "reason",
        "mode",
        "execution_authorized",
        "retry_authorized",
    }


@pytest.mark.parametrize(
    ("stage", "outcome", "reason"),
    [
        ("denied_before_dispatch", "DENIED", "DENIED_BEFORE_DISPATCH"),
        ("canceled_before_dispatch", "CANCELED", "CANCELED_BEFORE_DISPATCH"),
    ],
)
def test_pre_dispatch_stop_stays_distinct_unless_effect_is_reported(stage, outcome, reason):
    attempt = replace(ATTEMPT, stage=stage)
    assert_outcome(outcome, reason, attempt=attempt)
    assert_outcome("UNKNOWN", "UNEXPECTED_READBACK", attempt=attempt, readback=STORED)


def test_post_dispatch_cancellation_does_not_prove_absence_of_effect():
    attempt = replace(ATTEMPT, stage="canceled_after_dispatch")
    assert_outcome("UNKNOWN", "READBACK_UNAVAILABLE", attempt=attempt)
    assert_outcome("CONFIRMED", "MATCHED_STORED_DRAFT", attempt=attempt, readback=STORED)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("attempt_id", "fixture:operation:draft-older"),
        ("target_id", "fixture:draft:other"),
        ("destination_id", "fixture:store:other"),
    ],
)
@pytest.mark.parametrize("kind", ["stored", "terminal_failure"])
def test_unrelated_observation_cannot_confirm_or_fail_this_attempt(field, value, kind):
    readback = replace(STORED, kind=kind, stored_draft=BODY if kind == "stored" else None)
    assert_outcome(
        "UNKNOWN", "READBACK_SCOPE_MISMATCH", readback=replace(readback, **{field: value})
    )


def test_terminal_failure_is_distinct_from_absence_and_conflict():
    assert_outcome("UNKNOWN", "READBACK_UNAVAILABLE")
    failure = replace(STORED, kind="terminal_failure", stored_draft=None)
    assert_outcome("FAILED", "MATCHED_TERMINAL_FAILURE", readback=failure)
    conflicting = replace(failure, stored_draft=BODY)
    assert_outcome("UNKNOWN", "CONFLICTING_READBACK", readback=conflicting)


@pytest.mark.parametrize("kind", ["stored", "terminal_failure"])
def test_even_exact_effect_does_not_confirm_unverified_or_drifted_pre_dispatch_revision(kind):
    readback = replace(STORED, kind=kind, stored_draft=BODY if kind == "stored" else None)
    for missing_or_invalid in (None, "current-revision", "fixture:revision:UPPERCASE", True):
        assert_outcome(
            "UNKNOWN",
            "EXPECTED_PRE_DISPATCH_REVISION_UNAVAILABLE",
            attempt=replace(ATTEMPT, expected_pre_dispatch_revision=missing_or_invalid),
            readback=readback,
        )
        assert_outcome(
            "UNKNOWN",
            "OBSERVED_PRE_DISPATCH_REVISION_UNAVAILABLE",
            readback=replace(readback, observed_pre_dispatch_revision=missing_or_invalid),
        )
    assert_outcome(
        "UNKNOWN",
        "PRE_DISPATCH_REVISION_MISMATCH",
        readback=replace(readback, observed_pre_dispatch_revision="fixture:revision:r2"),
    )


def test_receipt_only_or_malformed_readback_is_unknown():
    receipt = {"attempt_id": ATTEMPT.attempt_id, "stored": True}
    assert_outcome("UNKNOWN", "INVALID_READBACK", readback=receipt)
    assert_outcome("UNKNOWN", "INVALID_READBACK", readback=replace(STORED, kind="receipt_only"))
    assert_outcome(
        "UNKNOWN", "DRAFT_CONTENT_UNAVAILABLE", readback=replace(STORED, stored_draft=None)
    )


def test_changed_content_and_unsupported_content_are_unknown():
    assert_outcome(
        "UNKNOWN", "DRAFT_CONTENT_MISMATCH", readback=replace(STORED, stored_draft=b"other draft")
    )
    for body in (bytearray(BODY), b"x" * (MAX_INPUT_BYTES + 1)):
        assert_outcome(
            "UNKNOWN", "DRAFT_CONTENT_UNAVAILABLE", readback=replace(STORED, stored_draft=body)
        )


@pytest.mark.parametrize("size", [0, MAX_INPUT_BYTES])
def test_draft_content_size_bounds_match_intent(size):
    body = b"x" * size
    draft = replace(DRAFT, input_sha256=sha256(body).hexdigest())
    assert_outcome(
        "CONFIRMED",
        "MATCHED_STORED_DRAFT",
        attempt=replace(ATTEMPT, intent=draft),
        readback=replace(STORED, stored_draft=body),
    )


def test_non_fixture_attempt_or_non_draft_operation_cannot_be_evaluated():
    send = replace(
        DRAFT,
        action="send",
        destination_id="fixture:recipient:review",
        source_account_id="fixture:account:sender",
    )
    for attempt in (
        None,
        asdict(ATTEMPT),
        replace(ATTEMPT, intent=send),
        replace(ATTEMPT, attempt_id="operation-draft-1"),
        replace(ATTEMPT, stage="complete"),
    ):
        assert_outcome("UNKNOWN", "INVALID_ATTEMPT", attempt=attempt, readback=STORED)

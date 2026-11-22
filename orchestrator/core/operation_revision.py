"""Opt-in G1 preview for revision-bound synthetic draft/send intents.

Version 2 requires a prior exact revision and a fresh, independently observed
resource/revision pair from the trusted controller. Neither value comes from the
proposal. There is no fallback on absence or mismatch. Version 1 is unchanged
and is not evaluated as revision-bound. Since a resource can change after this
preview, this is not a freshness lease, atomic CAS, or authorization.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from orchestrator.core.operation_intent import (
    MAX_PROPOSAL_BYTES,
    InvalidProposal,
    OperationIntent,
    OperationScope,
    evaluate_operation,
)
from orchestrator.core.operation_intent import (
    VERSION as INTENT_VERSION,
)

VERSION = "operation-proposal/2"
_REVISION = re.compile(r"fixture:revision:[a-z0-9][a-z0-9-]{0,63}")
_MUTABLE_ACTIONS = frozenset({"draft", "send"})


@dataclass(frozen=True, slots=True)
class ObservedRevision:
    """Controller-supplied readback of this resource, not a caller assertion."""

    target_id: str
    revision: str


@dataclass(frozen=True, slots=True)
class RevisionAssessment:
    reason: str
    matched_intent: OperationIntent | None = None
    matched_revision: str | None = None
    mode: Literal["MANUAL_ONLY"] = field(init=False, default="MANUAL_ONLY")
    execution_authorized: Literal[False] = field(init=False, default=False)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise InvalidProposal("INVALID_PROPOSAL")
        obj[key] = value
    return obj


def is_fixture_revision(value: object) -> bool:
    """Check the canonical synthetic revision identifier; not freshness evidence."""
    return type(value) is str and _REVISION.fullmatch(value) is not None


def _project_for_base_checks(proposal: bytes) -> tuple[bytes, str]:
    if type(proposal) is not bytes or not 1 <= len(proposal) <= MAX_PROPOSAL_BYTES:
        raise InvalidProposal("INVALID_PROPOSAL")
    try:
        obj = json.loads(proposal.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        raise InvalidProposal("INVALID_PROPOSAL") from None
    if type(obj) is not dict:
        raise InvalidProposal("INVALID_PROPOSAL")
    if obj.get("version") != VERSION:
        raise InvalidProposal("UNKNOWN_VERSION")
    revision = obj.pop("target_revision", None)
    if revision is None:
        raise InvalidProposal("TARGET_REVISION_MISSING")
    if not is_fixture_revision(revision):
        raise InvalidProposal("INVALID_TARGET_REVISION")

    # Only the revision and version differ. All other fields, including an
    # unexpected field, are still evaluated by the unchanged v1 contract.
    obj["version"] = INTENT_VERSION
    try:
        wire = json.dumps(obj, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
    except (ValueError, RecursionError):
        raise InvalidProposal("INVALID_PROPOSAL") from None
    return wire, revision


def evaluate_revision_bound_operation(
    proposal: bytes,
    *,
    expected: OperationIntent,
    observed_input: bytes,
    requester_grant: frozenset[OperationScope],
    task_scope: frozenset[OperationScope],
    allowed_operation_ids: frozenset[str],
    expected_revision: str | None = None,
    observed_revision: ObservedRevision | None = None,
) -> RevisionAssessment:
    """Preview exact intent and revision; no outcome permits any action."""
    try:
        base_wire, proposed_revision = _project_for_base_checks(proposal)
    except InvalidProposal as exc:
        return RevisionAssessment(str(exc))
    base = evaluate_operation(
        base_wire,
        expected=expected,
        observed_input=observed_input,
        requester_grant=requester_grant,
        task_scope=task_scope,
        allowed_operation_ids=allowed_operation_ids,
    )
    intent = base.matched_intent
    if intent is None:
        return RevisionAssessment(base.reason)
    if intent.action not in _MUTABLE_ACTIONS:
        return RevisionAssessment("MUTABLE_ACTION_REQUIRED")
    if not is_fixture_revision(expected_revision):
        return RevisionAssessment("EXPECTED_REVISION_UNAVAILABLE")
    if type(observed_revision) is not ObservedRevision or not is_fixture_revision(
        observed_revision.revision
    ):
        return RevisionAssessment("OBSERVED_REVISION_UNAVAILABLE")
    if (
        type(observed_revision.target_id) is not str
        or observed_revision.target_id != intent.target_id
    ):
        return RevisionAssessment("OBSERVED_TARGET_MISMATCH")
    if proposed_revision != expected_revision:
        return RevisionAssessment("TARGET_REVISION_MISMATCH")
    if observed_revision.revision != expected_revision:
        return RevisionAssessment("OBSERVED_REVISION_MISMATCH")
    return RevisionAssessment("EXACT_REVISION_INTENT_MATCH", intent, expected_revision)

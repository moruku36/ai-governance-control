"""G1 synthetic operation evaluation; nothing here grants execution authority.

The caller obtains the expected intent, requester grant, and task scope from
trusted controller state, never from the submitted proposal. Scope entries bind
(action, target, destination, source account) literally. The action is the
operation ID. Target revision or freshness is outside this slice; an input digest
does not attest to either. No approval, runtime, or adapter consumes this preview.
"""

import json
import re
from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest
from typing import Literal

VERSION = "operation-proposal/1"
MAX_PROPOSAL_BYTES = 4096
MAX_INPUT_BYTES = 65536
MAX_SCOPE_ENTRIES = 128

_TASK = re.compile(r"[A-Z][A-Z0-9]{1,7}-[0-9]{3,6}")
_PRINCIPAL = re.compile(r"fixture:principal:[a-z0-9][a-z0-9-]{0,63}")
_FIXTURE_ID = re.compile(r"fixture:([a-z]+):[a-z0-9][a-z0-9-]{0,63}")
_DIGEST = re.compile(r"[a-f0-9]{64}")
_ACTION_KINDS = {
    "read": ("document", "audience"),
    "draft": ("draft", "store"),
    "send": ("draft", "recipient"),
}
_FIELDS = frozenset(
    {
        "version",
        "task_id",
        "principal_id",
        "action",
        "target_id",
        "destination_id",
        "source_account_id",
        "input_sha256",
    }
)
OperationScope = tuple[str, str, str, str | None]


def _whole(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _action(value: object) -> bool:
    return type(value) is str and value in _ACTION_KINDS


def _fixture_id(value: object, kind: str) -> bool:
    return _whole(_FIXTURE_ID, value) and value.split(":", 2)[1] == kind


def _source_account(action: str, value: object) -> bool:
    return _fixture_id(value, "account") if action == "send" else value is None


def _matches_input(value: object) -> bool:
    return type(value) is bytes and len(value) <= MAX_INPUT_BYTES


class InvalidProposal(ValueError):
    """Fixed reason strings only; never contains submitted values."""


@dataclass(frozen=True, slots=True)
class OperationIntent:
    task_id: str
    principal_id: str
    action: str
    target_id: str
    destination_id: str
    source_account_id: str | None
    input_sha256: str

    def __post_init__(self) -> None:
        if not _action(self.action):
            raise InvalidProposal("UNKNOWN_ACTION")
        target_kind, destination_kind = _ACTION_KINDS[self.action]
        if not _fixture_id(self.target_id, target_kind):
            raise InvalidProposal("INVALID_TARGET")
        if not _fixture_id(self.destination_id, destination_kind):
            raise InvalidProposal("INVALID_DESTINATION")
        if not _source_account(self.action, self.source_account_id):
            raise InvalidProposal("INVALID_SOURCE_ACCOUNT")
        if not _whole(_TASK, self.task_id) or not _whole(_PRINCIPAL, self.principal_id):
            raise InvalidProposal("INVALID_IDENTITY")
        if not _whole(_DIGEST, self.input_sha256):
            raise InvalidProposal("INVALID_INPUT_DIGEST")

    @property
    def scope_key(self) -> OperationScope:
        return self.action, self.target_id, self.destination_id, self.source_account_id


@dataclass(frozen=True, slots=True)
class OperationAssessment:
    reason: str
    matched_intent: OperationIntent | None = None
    mode: Literal["MANUAL_ONLY"] = field(init=False, default="MANUAL_ONLY")
    execution_authorized: Literal[False] = field(init=False, default=False)


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise InvalidProposal("INVALID_PROPOSAL")
        obj[key] = value
    return obj


def parse_proposal(raw: bytes) -> OperationIntent:
    """Parse bounded, exact UTF-8 JSON; duplicate and unknown fields fail closed."""
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_PROPOSAL_BYTES:
        raise InvalidProposal("INVALID_PROPOSAL")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
    except (ValueError, RecursionError):
        raise InvalidProposal("INVALID_PROPOSAL") from None
    if type(obj) is not dict or obj.keys() != _FIELDS:
        raise InvalidProposal("INVALID_PROPOSAL")
    if obj["version"] != VERSION:
        raise InvalidProposal("UNKNOWN_VERSION")
    return OperationIntent(**{key: obj[key] for key in _FIELDS if key != "version"})


def _scope(value: object) -> bool:
    return (
        type(value) is frozenset
        and len(value) <= MAX_SCOPE_ENTRIES
        and all(
            type(pair) is tuple
            and len(pair) == 4
            and _action(pair[0])
            and _fixture_id(pair[1], _ACTION_KINDS[pair[0]][0])
            and _fixture_id(pair[2], _ACTION_KINDS[pair[0]][1])
            and _source_account(pair[0], pair[3])
            for pair in value
        )
    )


def evaluate_operation(
    proposal: bytes,
    *,
    expected: OperationIntent,
    observed_input: bytes,
    requester_grant: frozenset[OperationScope],
    task_scope: frozenset[OperationScope],
    allowed_operation_ids: frozenset[str],
) -> OperationAssessment:
    """Return an exact-match preview or a stable rejection, never permission."""
    if (
        type(expected) is not OperationIntent
        or not _scope(requester_grant)
        or not _scope(task_scope)
        or type(allowed_operation_ids) is not frozenset
        or len(allowed_operation_ids) > len(_ACTION_KINDS)
        or not all(_action(action) for action in allowed_operation_ids)
    ):
        return OperationAssessment("INVALID_CONTEXT")
    try:
        intent = parse_proposal(proposal)
    except InvalidProposal as exc:
        return OperationAssessment(str(exc))

    for name in (
        "task_id",
        "principal_id",
        "action",
        "target_id",
        "destination_id",
        "source_account_id",
    ):
        if getattr(intent, name) != getattr(expected, name):
            return OperationAssessment(name.removesuffix("_id").upper() + "_MISMATCH")

    scope = intent.scope_key
    if intent.action not in allowed_operation_ids:
        return OperationAssessment("OPERATION_NOT_ALLOWED")
    if scope not in requester_grant:
        return OperationAssessment("OUTSIDE_REQUESTER_GRANT")
    if scope not in task_scope:
        return OperationAssessment("OUTSIDE_TASK_SCOPE")
    if not _matches_input(observed_input):
        return OperationAssessment("INPUT_UNAVAILABLE")
    if not compare_digest(intent.input_sha256, expected.input_sha256) or not compare_digest(
        sha256(observed_input).hexdigest(), expected.input_sha256
    ):
        return OperationAssessment("INPUT_DIGEST_MISMATCH")
    return OperationAssessment("EXACT_INTENT_MATCH", expected)

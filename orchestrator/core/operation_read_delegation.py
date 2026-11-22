"""One-hop synthetic read-scope comparison, not a grant or dispatch gate.

The checker takes controller-held fixture linkage and parent scope independently
of the child request. It cannot establish their provenance or current validity.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from orchestrator.core.operation_intent import MAX_SCOPE_ENTRIES, OperationScope

_TASK = re.compile(r"[A-Z][A-Z0-9]{1,7}-[0-9]{3,6}")
_PRINCIPAL = re.compile(r"fixture:principal:[a-z0-9][a-z0-9-]{0,63}")
_DOCUMENT = re.compile(r"fixture:document:[a-z0-9][a-z0-9-]{0,63}")
_AUDIENCE = re.compile(r"fixture:audience:[a-z0-9][a-z0-9-]{0,63}")


@dataclass(frozen=True, slots=True)
class FixtureTaskBinding:
    task_id: str
    principal_id: str


@dataclass(frozen=True, slots=True)
class FixtureDelegationLink:
    """Independently retained identity for the intended one-hop relationship."""

    parent: FixtureTaskBinding
    child: FixtureTaskBinding


@dataclass(frozen=True, slots=True)
class FixtureParentReadScope:
    """Retained direct parent scope; None explicitly means no upstream task."""

    holder: FixtureTaskBinding
    upstream_task_id: str | None
    scope_entries: tuple[OperationScope, ...]


@dataclass(frozen=True, slots=True)
class FixtureReadDelegationRequest:
    """Proposed identities and exact read tuples; none convey authority."""

    parent: FixtureTaskBinding
    child: FixtureTaskBinding
    scope_entries: tuple[OperationScope, ...]


@dataclass(frozen=True, slots=True)
class ReadDelegationPreview:
    reason: str
    mode: Literal["MANUAL_ONLY"] = field(init=False, default="MANUAL_ONLY")
    execution_authorized: Literal[False] = field(init=False, default=False)
    delegation_authorized: Literal[False] = field(init=False, default=False)


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _is_binding(value: object) -> bool:
    return (
        type(value) is FixtureTaskBinding
        and _matches(_TASK, value.task_id)
        and _matches(_PRINCIPAL, value.principal_id)
    )


def _read_scope(value: object) -> frozenset[OperationScope] | None:
    # Use a tuple at the boundary so duplicate entries cannot be silently lost.
    if type(value) is not tuple or not 1 <= len(value) <= MAX_SCOPE_ENTRIES:
        return None
    for entry in value:
        if (
            type(entry) is not tuple
            or len(entry) != 4
            or type(entry[0]) is not str
            or entry[0] != "read"
            or not _matches(_DOCUMENT, entry[1])
            or not _matches(_AUDIENCE, entry[2])
            or entry[3] is not None
        ):
            return None
    entries = frozenset(value)
    return entries if len(entries) == len(value) else None


def preview_read_delegation(
    request: FixtureReadDelegationRequest,
    *,
    linked_tasks: FixtureDelegationLink,
    parent_scope: FixtureParentReadScope,
) -> ReadDelegationPreview:
    """Compare exact fixture tuples without creating or authorizing a grant."""
    if (
        type(linked_tasks) is not FixtureDelegationLink
        or not _is_binding(linked_tasks.parent)
        or not _is_binding(linked_tasks.child)
        or linked_tasks.parent.task_id == linked_tasks.child.task_id
        or linked_tasks.parent.principal_id == linked_tasks.child.principal_id
    ):
        return ReadDelegationPreview("INVALID_TASK_LINK")
    if type(parent_scope) is not FixtureParentReadScope or not _is_binding(parent_scope.holder):
        return ReadDelegationPreview("INVALID_PARENT_CONTEXT")
    if parent_scope.holder != linked_tasks.parent:
        return ReadDelegationPreview("PARENT_SCOPE_HOLDER_MISMATCH")
    if parent_scope.upstream_task_id is not None:
        return ReadDelegationPreview("DIRECT_PARENT_REQUIRED")
    parent = _read_scope(parent_scope.scope_entries)
    if parent is None:
        return ReadDelegationPreview("INVALID_PARENT_SCOPE")

    if (
        type(request) is not FixtureReadDelegationRequest
        or not _is_binding(request.parent)
        or not _is_binding(request.child)
    ):
        return ReadDelegationPreview("INVALID_REQUEST")
    if request.parent != linked_tasks.parent or request.child != linked_tasks.child:
        return ReadDelegationPreview("REQUEST_TASK_LINK_MISMATCH")
    requested = _read_scope(request.scope_entries)
    if requested is None:
        return ReadDelegationPreview("INVALID_REQUESTED_SCOPE")
    if not requested <= parent:
        return ReadDelegationPreview("OUTSIDE_PARENT_SCOPE")
    return ReadDelegationPreview("READ_SCOPE_CONTAINED")

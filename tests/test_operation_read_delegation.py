"""Synthetic exact-scope tests, without issuance, delegation or dispatch."""

from dataclasses import asdict, replace

import pytest

from orchestrator.core.operation_intent import MAX_SCOPE_ENTRIES
from orchestrator.core.operation_read_delegation import (
    FixtureDelegationLink,
    FixtureParentReadScope,
    FixtureReadDelegationRequest,
    FixtureTaskBinding,
    preview_read_delegation,
)

PARENT = FixtureTaskBinding("TASK-010", "fixture:principal:parent")
CHILD = FixtureTaskBinding("TASK-011", "fixture:principal:child")
OTHER = FixtureTaskBinding("TASK-012", "fixture:principal:other")
LINKED = FixtureDelegationLink(PARENT, CHILD)
READ_A_X = ("read", "fixture:document:a", "fixture:audience:x", None)
READ_B_Y = ("read", "fixture:document:b", "fixture:audience:y", None)
PARENT_SCOPE = FixtureParentReadScope(PARENT, None, (READ_A_X, READ_B_Y))
REQUEST = FixtureReadDelegationRequest(
    FixtureTaskBinding("TASK-010", "fixture:principal:parent"),
    FixtureTaskBinding("TASK-011", "fixture:principal:child"),
    (READ_A_X,),
)


def assert_reason(reason, *, request=REQUEST, link=LINKED, parent_scope=PARENT_SCOPE):
    result = preview_read_delegation(request, linked_tasks=link, parent_scope=parent_scope)
    assert result.reason == reason
    assert result.mode == "MANUAL_ONLY"
    assert result.execution_authorized is False
    assert result.delegation_authorized is False
    assert set(asdict(result)) == {
        "reason",
        "mode",
        "execution_authorized",
        "delegation_authorized",
    }


def test_exact_nonempty_subset_is_contained_but_never_authorized():
    assert_reason("READ_SCOPE_CONTAINED")
    assert_reason(
        "READ_SCOPE_CONTAINED", request=replace(REQUEST, scope_entries=(READ_B_Y, READ_A_X))
    )


@pytest.mark.parametrize(
    "scope",
    [
        ("read", "fixture:document:a", "fixture:audience:y", None),
        ("read", "fixture:document:b", "fixture:audience:x", None),
        ("read", "fixture:document:other", "fixture:audience:x", None),
        ("read", "fixture:document:a", "fixture:audience:other", None),
    ],
    ids=["cross-pair-a-y", "cross-pair-b-x", "outside-document", "outside-audience"],
)
def test_any_outside_tuple_blocks_the_whole_requested_set(scope):
    assert_reason("OUTSIDE_PARENT_SCOPE", request=replace(REQUEST, scope_entries=(READ_A_X, scope)))


@pytest.mark.parametrize(
    "link",
    [
        None,
        asdict(LINKED),
        replace(LINKED, parent=replace(PARENT, task_id="bad")),
        replace(LINKED, child=replace(CHILD, principal_id="non-fixture")),
        replace(LINKED, child=replace(CHILD, task_id=PARENT.task_id)),
        replace(LINKED, child=replace(CHILD, principal_id=PARENT.principal_id)),
    ],
    ids=[
        "missing",
        "plain-dict",
        "invalid-task",
        "invalid-principal",
        "self-task",
        "same-principal",
    ],
)
def test_missing_or_aliased_independent_task_link_is_invalid(link):
    assert_reason("INVALID_TASK_LINK", link=link)


@pytest.mark.parametrize(
    "request_context",
    [
        replace(REQUEST, parent=OTHER),
        replace(REQUEST, child=OTHER),
        replace(REQUEST, parent=replace(PARENT, principal_id=OTHER.principal_id)),
        replace(REQUEST, child=replace(CHILD, principal_id=PARENT.principal_id)),
        replace(REQUEST, parent=CHILD, child=PARENT),
    ],
    ids=["wrong-parent", "wrong-child", "wrong-parent-principal", "role-alias", "swapped-roles"],
)
def test_child_proposal_cannot_select_different_tasks_or_roles(request_context):
    assert_reason("REQUEST_TASK_LINK_MISMATCH", request=request_context)


def test_malformed_request_and_missing_parent_scope_are_rejected():
    assert_reason("INVALID_REQUEST", request=asdict(REQUEST))
    assert_reason("INVALID_PARENT_CONTEXT", parent_scope=None)
    assert_reason("INVALID_PARENT_CONTEXT", parent_scope=replace(PARENT_SCOPE, holder=None))


def test_a_different_scope_holder_cannot_serve_as_the_linked_parent():
    for holder in (CHILD, OTHER, replace(PARENT, principal_id=OTHER.principal_id)):
        assert_reason(
            "PARENT_SCOPE_HOLDER_MISMATCH", parent_scope=replace(PARENT_SCOPE, holder=holder)
        )


def test_a_previously_delegated_parent_cannot_subdelegate():
    for upstream in (OTHER.task_id, ""):
        assert_reason(
            "DIRECT_PARENT_REQUIRED", parent_scope=replace(PARENT_SCOPE, upstream_task_id=upstream)
        )


@pytest.mark.parametrize(
    "scope",
    [
        (),
        (READ_A_X, READ_A_X),
        frozenset({READ_A_X}),
        [READ_A_X],
        (("read", "fixture:document:a", "fixture:audience:x"),),
        (("read", "fixture:document:*", "fixture:audience:x", None),),
        (("read", "fixture:document:a", "fixture:recipient:x", None),),
        (("read", "fixture:document:a", "fixture:audience:x", "fixture:account:other"),),
        (("draft", "fixture:draft:a", "fixture:store:x", None),),
        (("send", "fixture:draft:a", "fixture:recipient:x", "fixture:account:other"),),
    ],
    ids=[
        "empty",
        "duplicate",
        "set",
        "list",
        "short",
        "wildcard",
        "kind",
        "account",
        "draft",
        "send",
    ],
)
def test_both_parent_and_child_require_strict_unique_read_tuples(scope):
    assert_reason("INVALID_PARENT_SCOPE", parent_scope=replace(PARENT_SCOPE, scope_entries=scope))
    assert_reason("INVALID_REQUESTED_SCOPE", request=replace(REQUEST, scope_entries=scope))


def test_scope_limit_at_both_boundaries():
    entries = tuple(
        ("read", f"fixture:document:doc-{i}", "fixture:audience:x", None)
        for i in range(MAX_SCOPE_ENTRIES + 1)
    )
    at_limit = entries[:-1]
    valid_parent = replace(PARENT_SCOPE, scope_entries=at_limit)
    assert_reason(
        "READ_SCOPE_CONTAINED",
        parent_scope=valid_parent,
        request=replace(REQUEST, scope_entries=at_limit),
    )
    assert_reason("INVALID_PARENT_SCOPE", parent_scope=replace(PARENT_SCOPE, scope_entries=entries))
    assert_reason("INVALID_REQUESTED_SCOPE", request=replace(REQUEST, scope_entries=entries))

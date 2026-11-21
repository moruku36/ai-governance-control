"""Offline tests for non-authorizing synthetic operation records."""

import json
import unittest
from dataclasses import asdict, replace
from hashlib import sha256

from orchestrator.core.operation_intent import (
    MAX_INPUT_BYTES,
    MAX_PROPOSAL_BYTES,
    VERSION,
    OperationIntent,
    evaluate_operation,
)

BODY = b"fixture input"
DIGEST = sha256(BODY).hexdigest()
BASE = OperationIntent(
    "TASK-001",
    "fixture:principal:requester-a",
    "read",
    "fixture:document:handbook",
    "fixture:audience:requester-a",
    None,
    DIGEST,
)
SEND = replace(
    BASE,
    action="send",
    target_id="fixture:draft:case-a",
    destination_id="fixture:recipient:recipient-a",
    source_account_id="fixture:account:sender-a",
)


def encode(intent=BASE, **extra):
    return json.dumps({"version": VERSION, **asdict(intent), **extra}).encode()


def evaluate(raw=None, expected=BASE, **overrides):
    context = {
        "expected": expected,
        "observed_input": BODY,
        "requester_grant": frozenset({expected.scope_key}),
        "task_scope": frozenset({expected.scope_key}),
        "allowed_operation_ids": frozenset({expected.action}),
        **overrides,
    }
    return evaluate_operation(encode(expected) if raw is None else raw, **context)


class TestOperationIntent(unittest.TestCase):
    def assert_rejected(self, outcome, reason):
        self.assertEqual(outcome.reason, reason)
        self.assertIsNone(outcome.matched_intent)
        self.assertIs(outcome.execution_authorized, False)
        self.assertEqual(outcome.mode, "MANUAL_ONLY")

    def test_read_draft_and_send_remain_distinct_inert_intents(self):
        for intent in (
            BASE,
            replace(
                BASE,
                action="draft",
                target_id="fixture:draft:case-a",
                destination_id="fixture:store:review",
            ),
            SEND,
        ):
            with self.subTest(action=intent.action):
                result = evaluate(expected=intent)
                self.assertEqual(result.reason, "EXACT_INTENT_MATCH")
                self.assertEqual(result.matched_intent, intent)
                self.assertIs(result.execution_authorized, False)
                self.assertEqual(result.mode, "MANUAL_ONLY")

    def test_task_and_principal_are_exact(self):
        self.assert_rejected(evaluate(encode(task_id="TASK-002")), "TASK_MISMATCH")
        self.assert_rejected(
            evaluate(encode(principal_id="fixture:principal:requester-b")), "PRINCIPAL_MISMATCH"
        )

    def test_read_does_not_authorize_draft_or_send(self):
        self.assert_rejected(
            evaluate(encode(SEND)),
            "ACTION_MISMATCH",
        )

    def test_target_changes_do_not_match_even_when_in_both_scopes(self):
        second = replace(BASE, target_id="fixture:document:handbook-v2")
        both = frozenset({BASE.scope_key, second.scope_key})
        self.assert_rejected(
            evaluate(encode(second), requester_grant=both, task_scope=both),
            "TARGET_MISMATCH",
        )

    def test_same_read_resource_cannot_switch_return_audience(self):
        second = replace(BASE, destination_id="fixture:audience:reviewers")
        both = frozenset({BASE.scope_key, second.scope_key})
        self.assert_rejected(
            evaluate(encode(second), requester_grant=both, task_scope=both),
            "DESTINATION_MISMATCH",
        )

    def test_same_draft_cannot_switch_store(self):
        draft = replace(
            BASE,
            action="draft",
            target_id="fixture:draft:case-a",
            destination_id="fixture:store:review",
        )
        self.assert_rejected(
            evaluate(encode(draft, destination_id="fixture:store:archive"), expected=draft),
            "DESTINATION_MISMATCH",
        )

    def test_same_send_resource_cannot_switch_recipient_or_source_account(self):
        for second, reason in (
            (replace(SEND, destination_id="fixture:recipient:recipient-b"), "DESTINATION_MISMATCH"),
            (
                replace(SEND, source_account_id="fixture:account:sender-b"),
                "SOURCE_ACCOUNT_MISMATCH",
            ),
        ):
            with self.subTest(reason=reason):
                both = frozenset({SEND.scope_key, second.scope_key})
                self.assert_rejected(
                    evaluate(encode(second), expected=SEND, requester_grant=both, task_scope=both),
                    reason,
                )

    def test_both_scopes_cover_recipient_and_source_account(self):
        other_recipient = replace(SEND, destination_id="fixture:recipient:recipient-b")
        other_account = replace(SEND, source_account_id="fixture:account:sender-b")
        self.assert_rejected(
            evaluate(expected=SEND, requester_grant=frozenset({other_recipient.scope_key})),
            "OUTSIDE_REQUESTER_GRANT",
        )
        self.assert_rejected(
            evaluate(expected=SEND, task_scope=frozenset({other_account.scope_key})),
            "OUTSIDE_TASK_SCOPE",
        )

    def test_each_independent_scope_must_include_exact_operation(self):
        self.assert_rejected(
            evaluate(allowed_operation_ids=frozenset({"draft"})), "OPERATION_NOT_ALLOWED"
        )
        self.assert_rejected(
            evaluate(
                requester_grant=frozenset(
                    {
                        replace(BASE, target_id="fixture:document:other").scope_key,
                    }
                )
            ),
            "OUTSIDE_REQUESTER_GRANT",
        )
        self.assert_rejected(evaluate(task_scope=frozenset()), "OUTSIDE_TASK_SCOPE")

    def test_unknown_scope_fails_closed(self):
        self.assert_rejected(
            evaluate(allowed_operation_ids=frozenset({"merge"})), "INVALID_CONTEXT"
        )
        self.assert_rejected(
            evaluate(
                requester_grant=frozenset(
                    {
                        ("read", "fixture:document:*", BASE.destination_id, None),
                    }
                )
            ),
            "INVALID_CONTEXT",
        )
        self.assert_rejected(evaluate(task_scope={BASE.scope_key}), "INVALID_CONTEXT")

    def test_proposal_and_resolved_bytes_both_match_expected_digest(self):
        self.assert_rejected(evaluate(encode(input_sha256="0" * 64)), "INPUT_DIGEST_MISMATCH")
        self.assert_rejected(evaluate(observed_input=b"changed"), "INPUT_DIGEST_MISMATCH")
        self.assert_rejected(evaluate(encode(input_sha256="x" * 64)), "INVALID_INPUT_DIGEST")
        self.assert_rejected(
            evaluate(observed_input=b"x" * (MAX_INPUT_BYTES + 1)), "INPUT_UNAVAILABLE"
        )

    def test_invalid_targets_and_unknown_actions(self):
        self.assert_rejected(evaluate(encode(action="erase")), "UNKNOWN_ACTION")
        self.assert_rejected(evaluate(encode(target_id="fixture:document:*")), "INVALID_TARGET")
        self.assert_rejected(evaluate(encode(target_id="fixture:draft:handbook")), "INVALID_TARGET")
        self.assert_rejected(evaluate(encode(principal_id="unresolved")), "INVALID_IDENTITY")

    def test_invalid_destination_and_account_shape(self):
        self.assert_rejected(
            evaluate(encode(destination_id="fixture:recipient:recipient-a")), "INVALID_DESTINATION"
        )
        self.assert_rejected(
            evaluate(encode(source_account_id="fixture:account:sender-a")), "INVALID_SOURCE_ACCOUNT"
        )
        self.assert_rejected(
            evaluate(encode(SEND, source_account_id=None), expected=SEND), "INVALID_SOURCE_ACCOUNT"
        )

    def test_unknown_fields_versions_and_missing_fields(self):
        self.assert_rejected(evaluate(encode(approved=True)), "INVALID_PROPOSAL")
        self.assert_rejected(evaluate(encode(target_revision="rev-1")), "INVALID_PROPOSAL")
        self.assert_rejected(evaluate(encode(version="operation-proposal/2")), "UNKNOWN_VERSION")
        self.assert_rejected(evaluate(b'{"version":"operation-proposal/1"}'), "INVALID_PROPOSAL")

    def test_duplicate_or_malformed_wire_is_rejected(self):
        duplicate = b'{"task_id":"TASK-009",' + encode()[1:]
        for raw in (duplicate, b"\xff", b"[]", b"[" * 2000, b"x" * (MAX_PROPOSAL_BYTES + 1)):
            with self.subTest(length=len(raw)):
                self.assert_rejected(evaluate(raw), "INVALID_PROPOSAL")

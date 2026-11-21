"""Version separation and exact-revision tests for synthetic draft/send."""

import json
import unittest
from dataclasses import asdict, replace
from hashlib import sha256

from orchestrator.core.operation_intent import (
    VERSION as V1,
)
from orchestrator.core.operation_intent import (
    OperationIntent,
    evaluate_operation,
)
from orchestrator.core.operation_revision import (
    VERSION,
    ObservedRevision,
    evaluate_revision_bound_operation,
)

INPUT = b"same synthetic input on both revisions"
REVISION = "fixture:revision:r1"
NEW = "fixture:revision:r2"
DRAFT = OperationIntent(
    "TASK-001",
    "fixture:principal:requester",
    "draft",
    "fixture:draft:case-a",
    "fixture:store:review",
    None,
    sha256(INPUT).hexdigest(),
)
SEND = replace(
    DRAFT,
    action="send",
    destination_id="fixture:recipient:recipient-a",
    source_account_id="fixture:account:sender-a",
)
READ = replace(
    DRAFT,
    action="read",
    target_id="fixture:document:case-a",
    destination_id="fixture:audience:review",
)


def encoded(intent=DRAFT, **extra):
    return json.dumps(
        {
            "version": VERSION,
            **asdict(intent),
            "target_revision": REVISION,
            **extra,
        }
    ).encode()


def base_context(intent):
    return {
        "expected": intent,
        "observed_input": INPUT,
        "requester_grant": frozenset({intent.scope_key}),
        "task_scope": frozenset({intent.scope_key}),
        "allowed_operation_ids": frozenset({intent.action}),
    }


def evaluate(raw=None, expected=DRAFT, **overrides):
    return evaluate_revision_bound_operation(
        encoded(expected) if raw is None else raw,
        **{
            **base_context(expected),
            "expected_revision": REVISION,
            "observed_revision": ObservedRevision(expected.target_id, REVISION),
            **overrides,
        },
    )


class TestOperationRevision(unittest.TestCase):
    def assert_rejected(self, result, reason):
        self.assertEqual(result.reason, reason)
        self.assertIsNone(result.matched_intent)
        self.assertIsNone(result.matched_revision)
        self.assertIs(result.execution_authorized, False)
        self.assertEqual(result.mode, "MANUAL_ONLY")

    def test_exact_draft_and_send_revision_remain_non_authorizing(self):
        for intent in (DRAFT, SEND):
            with self.subTest(action=intent.action):
                result = evaluate(expected=intent)
                self.assertEqual(result.reason, "EXACT_REVISION_INTENT_MATCH")
                self.assertEqual(result.matched_intent, intent)
                self.assertEqual(result.matched_revision, REVISION)
                self.assertIs(result.execution_authorized, False)
                self.assertEqual(result.mode, "MANUAL_ONLY")

    def test_proposed_revision_missing_or_malformed(self):
        no_revision = json.dumps({"version": VERSION, **asdict(DRAFT)}).encode()
        self.assert_rejected(evaluate(no_revision), "TARGET_REVISION_MISSING")
        self.assert_rejected(evaluate(encoded(target_revision=None)), "TARGET_REVISION_MISSING")
        self.assert_rejected(
            evaluate(encoded(target_revision="fixture:revision:*")), "INVALID_TARGET_REVISION"
        )

    def test_independent_pin_and_observation_required(self):
        self.assert_rejected(evaluate(expected_revision=None), "EXPECTED_REVISION_UNAVAILABLE")
        self.assert_rejected(evaluate(observed_revision=None), "OBSERVED_REVISION_UNAVAILABLE")
        claimed_only = {"target_id": DRAFT.target_id, "revision": REVISION}
        self.assert_rejected(
            evaluate(observed_revision=claimed_only), "OBSERVED_REVISION_UNAVAILABLE"
        )

    def test_changed_claim_with_same_target_and_input(self):
        self.assert_rejected(
            evaluate(encoded(SEND, target_revision=NEW), expected=SEND), "TARGET_REVISION_MISMATCH"
        )

    def test_changed_observed_revision_with_same_target_and_input(self):
        for intent in (DRAFT, SEND):
            with self.subTest(action=intent.action):
                self.assert_rejected(
                    evaluate(
                        expected=intent, observed_revision=ObservedRevision(intent.target_id, NEW)
                    ),
                    "OBSERVED_REVISION_MISMATCH",
                )

    def test_right_revision_observed_for_wrong_target(self):
        self.assert_rejected(
            evaluate(observed_revision=ObservedRevision("fixture:draft:case-b", REVISION)),
            "OBSERVED_TARGET_MISMATCH",
        )

    def test_equal_new_claim_and_observation_do_not_replace_prior_pin(self):
        self.assert_rejected(
            evaluate(
                encoded(target_revision=NEW),
                observed_revision=ObservedRevision(DRAFT.target_id, NEW),
            ),
            "TARGET_REVISION_MISMATCH",
        )

    def test_revision_cannot_replace_base_policy_and_input_checks(self):
        self.assert_rejected(evaluate(requester_grant=frozenset()), "OUTSIDE_REQUESTER_GRANT")
        self.assert_rejected(evaluate(observed_input=b"different"), "INPUT_DIGEST_MISMATCH")
        self.assert_rejected(
            evaluate(encoded(SEND, destination_id="fixture:recipient:recipient-b"), expected=SEND),
            "DESTINATION_MISMATCH",
        )

    def test_v1_does_not_get_v2_authority_and_v2_will_not_fall_back(self):
        raw_v1 = json.dumps({"version": V1, **asdict(DRAFT)}).encode()
        base = evaluate_operation(raw_v1, **base_context(DRAFT))
        self.assertEqual(base.reason, "EXACT_INTENT_MATCH")
        self.assertFalse(base.execution_authorized)
        self.assertEqual(
            evaluate_operation(encoded(), **base_context(DRAFT)).reason, "INVALID_PROPOSAL"
        )
        self.assert_rejected(evaluate(raw_v1), "UNKNOWN_VERSION")
        self.assert_rejected(evaluate(expected=READ), "MUTABLE_ACTION_REQUIRED")

    def test_unknown_fields_and_duplicate_revision_are_rejected(self):
        self.assert_rejected(evaluate(encoded(approved=True)), "INVALID_PROPOSAL")
        duplicate = b'{"target_revision":"fixture:revision:r2",' + encoded()[1:]
        self.assert_rejected(evaluate(duplicate), "INVALID_PROPOSAL")

"""Offline assessment-bridge integration, with the real schema validator."""

import json
import unittest
from dataclasses import asdict, replace
from hashlib import sha256

from orchestrator.core.assessment import assessment_digest
from orchestrator.core.operation_assessment_bridge import (
    ASSESSMENT_PURPOSE,
    AssessmentPin,
    evaluate_assessed_operation,
)
from orchestrator.core.operation_intent import VERSION as V1
from orchestrator.core.operation_intent import OperationIntent
from orchestrator.core.operation_revision import VERSION as V2
from orchestrator.core.operation_revision import ObservedRevision

BODY = b"fixture-only operation payload"
READ = OperationIntent(
    "TASK-005",
    "fixture:principal:requester",
    "read",
    "fixture:document:item",
    "fixture:audience:review",
    None,
    sha256(BODY).hexdigest(),
)
SEND = replace(
    READ,
    action="send",
    target_id="fixture:draft:item",
    destination_id="fixture:recipient:review",
    source_account_id="fixture:account:sender",
)
DRAFT = replace(SEND, action="draft", destination_id="fixture:store:review", source_account_id=None)
REVISION = "fixture:revision:r1"


def record_fixture():
    return {
        "contract_version": "governance-assessment/1",
        "task_id": "TASK-005",
        "repository_id": "synthetic-repo",
        "spec_digest": "a" * 64,
        "candidate_digest": "b" * 64,
        "policy_digest": "c" * 64,
        "risk": "low",
        "action_id": ASSESSMENT_PURPOSE,
        "data_classification": "public",
        "external_impact": "none",
        "reversibility": "reversible",
        "reasons": ["Synthetic fixture, no external effects"],
        "unknowns": [],
        "assessor_ref": "fixture-assessor",
        "allowed_operation_ids": ["read", "draft", "send"],
        "runtime": {
            "principal_ref": "fixture-runtime",
            "profile_ref": "fixture-offline",
            "configuration_digest": "d" * 64,
            "snapshot_digest": "e" * 64,
            "mount_refs": [],
            "network_scope": "none",
            "egress_refs": [],
        },
        "credentials": {"delivery_mode": "none", "retrieval_authority_ref": None},
    }


PIN = AssessmentPin(
    "TASK-005",
    "synthetic-repo",
    "a" * 64,
    "b" * 64,
    "c" * 64,
    assessment_digest(record_fixture()),
)


def wire(intent, version=None):
    chosen = version or (V1 if intent.action == "read" else V2)
    value = {"version": chosen, **asdict(intent)}
    if chosen == V2:
        value["target_revision"] = REVISION
    return json.dumps(value).encode()


def preview(intent=READ, record=None, selected=PIN, raw=None, **options):
    return evaluate_assessed_operation(
        wire(intent) if raw is None else raw,
        assessment=record_fixture() if record is None else record,
        pin=selected,
        **{
            "expected": intent,
            "observed_input": BODY,
            "requester_grant": frozenset({intent.scope_key}),
            "task_scope": frozenset({intent.scope_key}),
            **options,
        },
    )


def repin(record):
    return replace(PIN, assessment_digest=assessment_digest(record))


class TestOperationAssessmentBridge(unittest.TestCase):
    def assert_result(self, result, reason):
        self.assertEqual(result.reason, reason)
        self.assertIs(result.execution_authorized, False)
        self.assertEqual(result.mode, "MANUAL_ONLY")

    def test_verified_read_stays_non_authorizing(self):
        outcome = preview()
        self.assert_result(outcome, "EXACT_INTENT_MATCH")
        self.assertEqual(outcome.matched_intent, READ)

    def test_verified_mutable_actions_still_require_complete_revision(self):
        for intent in (DRAFT, SEND):
            with self.subTest(action=intent.action):
                self.assert_result(preview(intent), "EXPECTED_REVISION_UNAVAILABLE")
                self.assert_result(
                    preview(intent, expected_revision=REVISION), "OBSERVED_REVISION_UNAVAILABLE"
                )
                result = preview(
                    intent,
                    expected_revision=REVISION,
                    observed_revision=ObservedRevision(intent.target_id, REVISION),
                )
                self.assert_result(result, "EXACT_REVISION_INTENT_MATCH")
                self.assertEqual(result.matched_revision, REVISION)

    def test_v1_cannot_downgrade_mutable_actions(self):
        self.assert_result(preview(SEND, raw=wire(SEND, V1)), "UNKNOWN_VERSION")

    def test_mutable_target_can_change_without_input_digest_change(self):
        result = preview(
            SEND,
            expected_revision=REVISION,
            observed_revision=ObservedRevision(SEND.target_id, "fixture:revision:r2"),
        )
        self.assert_result(result, "OBSERVED_REVISION_MISMATCH")

    def test_assessment_pin_must_match_exact_task_repo_spec_seal_and_policy(self):
        for key, wrong in (
            ("task_id", "TASK-006"),
            ("repository_id", "other-repo"),
            ("spec_digest", "f" * 64),
            ("candidate_digest", "f" * 64),
            ("policy_digest", "f" * 64),
        ):
            with self.subTest(key=key):
                bad = {**record_fixture(), key: wrong}
                # Even a digest that matches these bytes cannot replace the context pins.
                self.assert_result(preview(record=bad, selected=repin(bad)), "ASSESSMENT_REJECTED")

    def test_intent_cannot_reference_another_task(self):
        self.assert_result(preview(replace(READ, task_id="TASK-006")), "ASSESSMENT_CONTEXT_INVALID")

    def test_malformed_or_stale_assessment_refused(self):
        bad = {**record_fixture(), "allowed_operation_ids": ["read"]}
        self.assert_result(preview(record=bad), "ASSESSMENT_REJECTED")
        self.assert_result(
            preview(selected=replace(PIN, assessment_digest="")), "ASSESSMENT_REJECTED"
        )
        bad["permission_granted"] = True
        self.assert_result(preview(record=bad), "ASSESSMENT_REJECTED")

    def test_unknown_or_non_fixture_assessment_is_not_eligible(self):
        for overrides in (
            {"data_classification": "unknown", "unknowns": ["classification missing"]},
            {"unknowns": ["independent evidence missing"]},
            {"external_impact": "bounded"},
            {"data_classification": "internal"},
            {
                "runtime": {
                    **record_fixture()["runtime"],
                    "network_scope": "allowlisted",
                    "egress_refs": ["example"],
                }
            },
            {"credentials": {"delivery_mode": "proxied", "retrieval_authority_ref": "broker"}},
            {"action_id": "task_execution"},
        ):
            with self.subTest(fields=tuple(overrides)):
                bad = {**record_fixture(), **overrides}
                self.assert_result(
                    preview(record=bad, selected=repin(bad)), "ASSESSMENT_NOT_SYNTHETIC_ELIGIBLE"
                )

    def test_allowlist_comes_from_assessment_and_scopes_remain_independent(self):
        only_draft = {**record_fixture(), "allowed_operation_ids": ["draft"]}
        self.assert_result(
            preview(record=only_draft, selected=repin(only_draft)), "OPERATION_NOT_ALLOWED"
        )
        unknown = {**record_fixture(), "allowed_operation_ids": ["read", "unknown-operation"]}
        self.assert_result(
            preview(record=unknown, selected=repin(unknown)), "ASSESSMENT_UNKNOWN_OPERATION"
        )
        self.assert_result(preview(requester_grant=frozenset()), "OUTSIDE_REQUESTER_GRANT")
        self.assert_result(preview(task_scope=frozenset()), "OUTSIDE_TASK_SCOPE")

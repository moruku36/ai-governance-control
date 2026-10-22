"""Synthetic assessment records prove integrity only, never human authorization."""

import json
from dataclasses import FrozenInstanceError

import pytest

from orchestrator.core.assessment import (
    AssessmentError,
    assessment_digest,
    validate_assessment,
)
from orchestrator.core.schema import load_schema


@pytest.fixture
def assessment():
    return {
        "contract_version": "governance-assessment/1", "task_id": "SMP-001",
        "repository_id": "synthetic-repo", "spec_digest": "a" * 64,
        "candidate_digest": "b" * 64, "policy_digest": "c" * 64,
        "risk": "low", "action_id": "task_execution", "data_classification": "public",
        "external_impact": "none", "reversibility": "reversible",
        "reasons": ["Public synthetic fixture with no external effects"], "unknowns": [],
        "assessor_ref": "synthetic-human-reference", "allowed_operation_ids": ["pytest"],
        "runtime": {
            "principal_ref": "synthetic-controller", "profile_ref": "offline-linux-v1",
            "configuration_digest": "d" * 64, "snapshot_digest": "e" * 64,
            "mount_refs": ["synthetic-read-only-snapshot"], "network_scope": "none",
            "egress_refs": [],
        },
        "credentials": {"delivery_mode": "none", "retrieval_authority_ref": None},
    }


def expected(record):
    return {**{f"expected_{key}": record[key] for key in (
        "task_id", "repository_id", "spec_digest", "candidate_digest", "policy_digest",
    )}, "expected_assessment_digest": assessment_digest(record)}


def test_record_is_canonical_and_immutable_not_authorization(assessment):
    trusted = expected(assessment)
    result = validate_assessment(assessment, **trusted)
    reordered = dict(reversed(list(assessment.items())))
    assert validate_assessment(reordered, **trusted) == result
    with pytest.raises(FrozenInstanceError):
        result.digest = "f" * 64
    assessment["runtime"]["mount_refs"].append("later-mutation")
    assert "later-mutation" not in result.canonical_json
    assert set(result.__dataclass_fields__) == {"digest", "canonical_json"}
    assert "approved" not in json.loads(result.canonical_json)


@pytest.mark.parametrize("key,new", [
    ("task_id", "SMP-002"), ("repository_id", "another-repo"),
    ("spec_digest", "f" * 64), ("candidate_digest", "f" * 64),
    ("policy_digest", "f" * 64),
])
def test_context_mismatch_rejected_even_with_new_self_hash(assessment, key, new):
    trusted = expected(assessment)
    assessment[key] = new
    trusted["expected_assessment_digest"] = assessment_digest(assessment)
    with pytest.raises(AssessmentError, match="binding mismatch"):
        validate_assessment(assessment, **trusted)


@pytest.mark.parametrize("path,new", [
    (("risk",), "critical"), (("action_id",), "release_publish"),
    (("data_classification",), "internal"), (("external_impact",), "material"),
    (("reversibility",), "irreversible"), (("reasons",), ["Changed reason"]),
    (("unknowns",), ["New uncertainty"]), (("assessor_ref",), "different-assessor"),
    (("allowed_operation_ids",), ["python"]),
    (("runtime", "principal_ref"), "other-principal"),
    (("runtime", "profile_ref"), "other-profile"),
    (("runtime", "configuration_digest"), "f" * 64),
    (("runtime", "snapshot_digest"), "f" * 64),
    (("runtime", "mount_refs"), ["other-mount"]),
    (("runtime",), {
        "principal_ref": "synthetic-controller", "profile_ref": "offline-linux-v1",
        "configuration_digest": "d" * 64, "snapshot_digest": "e" * 64,
        "mount_refs": [], "network_scope": "allowlisted", "egress_refs": ["example-endpoint"],
    }),
    (("credentials",), {"delivery_mode": "proxied", "retrieval_authority_ref": "broker-ref"}),
])
def test_every_assessment_dimension_is_integrity_bound(assessment, path, new):
    trusted = expected(assessment)
    target = assessment
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = new
    with pytest.raises(AssessmentError, match="integrity mismatch"):
        validate_assessment(assessment, **trusted)


@pytest.mark.parametrize("key", [
    "contract_version", "task_id", "repository_id", "spec_digest", "candidate_digest",
    "policy_digest", "risk", "action_id", "data_classification", "external_impact",
    "reversibility", "reasons", "unknowns", "assessor_ref", "allowed_operation_ids",
    "runtime", "credentials",
])
def test_every_required_dimension_missing_fails(assessment, key):
    del assessment[key]
    with pytest.raises(AssessmentError):
        assessment_digest(assessment)


@pytest.mark.parametrize("key", ["approved", "permission_granted", "qualification", "schema_version"])
def test_extra_authority_and_wrong_version_field_rejected(assessment, key):
    assessment[key] = True
    with pytest.raises(AssessmentError):
        assessment_digest(assessment)


@pytest.mark.parametrize("path,value", [
    (("contract_version",), "2020-12"), (("risk",), "Moderate"),
    (("assessor_ref",), "human@example.invalid"), (("spec_digest",), "short"),
    (("allowed_operation_ids",), []), (("allowed_operation_ids",), ["pytest", "pytest"]),
    (("runtime", "egress_refs"), ["unexpected-egress"]),
    (("runtime", "network_scope"), "allowlisted"),
    (("credentials", "delivery_mode"), "proxied"),
    (("credentials", "retrieval_authority_ref"), "unexpected-authority"),
    (("reasons",), ["x" * 1025]), (("reasons",), ["line\nbreak"]), (("reasons",), ["trailing\n"]),
    (("task_id",), "SMP-001\n"), (("assessor_ref",), "assessor\n"),
    (("spec_digest",), "a" * 64 + "\n"),
])
def test_invalid_records_fail_closed(assessment, path, value):
    target = assessment
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(AssessmentError):
        assessment_digest(assessment)


def test_unknown_is_retained_not_promoted(assessment):
    assessment["data_classification"] = "unknown"
    with pytest.raises(AssessmentError):
        assessment_digest(assessment)
    assessment["unknowns"] = ["Classification has not been established"]
    result = validate_assessment(assessment, **expected(assessment))
    assert json.loads(result.canonical_json)["data_classification"] == "unknown"
    assert json.loads(result.canonical_json)["unknowns"] == assessment["unknowns"]


@pytest.mark.parametrize("value", [None, "", "f" * 63, "F" * 64, "f" * 64])
def test_missing_invalid_or_stale_trusted_digest_rejected(assessment, value):
    trusted = expected(assessment)
    trusted["expected_assessment_digest"] = value
    with pytest.raises(AssessmentError):
        validate_assessment(assessment, **trusted)


def test_schema_draft_is_not_product_contract_version():
    schema = load_schema("governance-assessment.schema.json")
    assert schema["$schema"].endswith("draft/2020-12/schema")
    assert schema["properties"]["contract_version"]["const"] == "governance-assessment/1"
    assert schema["properties"]["risk"]["enum"] == (
        load_schema("task.schema.json")["properties"]["risk"]["enum"]
    )


def test_invalid_payload_diagnostic_does_not_echo_data(assessment):
    assessment["accidental_sensitive_input"] = "SYNTHETIC-PRIVATE-MARKER"
    with pytest.raises(AssessmentError) as caught:
        assessment_digest(assessment)
    assert "SYNTHETIC-PRIVATE-MARKER" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_oversized_and_non_json_input_rejected(assessment):
    assessment["reasons"] = [str(i) + "x" * 1020 for i in range(64)]
    with pytest.raises(AssessmentError):
        assessment_digest(assessment)
    with pytest.raises(AssessmentError):
        assessment_digest([])
    assessment["cycle"] = assessment
    with pytest.raises(AssessmentError):
        assessment_digest(assessment)

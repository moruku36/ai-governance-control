"""R7: notifications carry only fixed status fields; there is nothing to redact."""

import ast
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from orchestrator.core import status_notification as module
from orchestrator.core.schema import DEFAULT_FORMAT_CHECKER, load_schema
from orchestrator.core.status_notification import (
    ALLOWED_FIELDS,
    EVENTS,
    StatusNotificationError,
    build_status_notification,
    validate_status_notification,
)

SENTINEL = "SYNTHETIC-MARKER-DO-NOT-ECHO"


def good(**override):
    values = {"task_id": "SMP-001", "repository_id": "synthetic-repo",
              "event": "task_collected", "occurred_at": "2026-10-23T05:00:00Z"}
    values.update(override)
    return values


def payload(**override):
    return {"contract_version": "status-notification/1", **good(**override)}


def test_build_contains_only_allowed_fields_and_one_status_line():
    note = build_status_notification(**good())
    decoded = json.loads(note.payload_json)
    assert set(decoded) == ALLOWED_FIELDS == set(
        load_schema("status-notification.schema.json")["properties"])
    assert note.text == ("[ai-governance-control] STATUS-ONLY SMP-001 task_collected "
                         "repo=synthetic-repo at 2026-10-23T05:00:00Z")
    assert note.text.isascii() and "\n" not in note.text and "\r" not in note.text
    assert "://" not in note.text and len(note.text) <= module.MAX_TEXT_LENGTH


def test_result_is_immutable_and_carries_no_authority():
    note = build_status_notification(**good())
    with pytest.raises(FrozenInstanceError):
        note.text = "changed"
    assert set(note.__dataclass_fields__) == {"payload_json", "text"}
    assert "approved" not in note.payload_json and "verified" not in note.text.lower()


def test_validate_round_trips_and_is_canonical_regardless_of_key_order():
    note = build_status_notification(**good())
    reordered = dict(reversed(list(json.loads(note.payload_json).items())))
    assert validate_status_notification(reordered) == note


@pytest.mark.parametrize("extra", [
    "message", "url", "endpoint", "webhook", "review_text", "output", "error",
    "path", "command", "token", "approved", "permission_granted", "digest",
])
def test_payload_with_any_extra_field_is_refused_not_trimmed(extra):
    with pytest.raises(StatusNotificationError):
        validate_status_notification({**payload(), extra: SENTINEL})


def test_builder_cannot_accept_free_form_arguments():
    for extra in ("message", "url", "endpoint", "review_comment", "hook_output"):
        with pytest.raises(TypeError):
            build_status_notification(**good(), **{extra: SENTINEL})


@pytest.mark.parametrize("field", sorted(ALLOWED_FIELDS))
def test_missing_field_is_refused(field):
    broken = payload()
    del broken[field]
    with pytest.raises(StatusNotificationError):
        validate_status_notification(broken)


# Paired table: each refused value is matched by an accepted control of the same field.
@pytest.mark.parametrize("field,accepted,refused", [
    ("repository_id", "synthetic-repo", "hooks.example.com"),
    ("repository_id", "synthetic-repo", "https://hooks.example.com/services/x"),
    ("repository_id", "synthetic-repo", "owner/repo"),
    ("repository_id", "synthetic-repo", "user@host"),
    ("repository_id", "synthetic-repo", "host:8080"),
    ("repository_id", "synthetic-repo", "a" * 32),
    ("repository_id", "synthetic-repo", "a" * 64),
    ("repository_id", "synthetic-repo", "Bearer-" + "A1" * 20),
    ("repository_id", "synthetic-repo", "synthetic repo"),
    ("repository_id", "synthetic-repo", "synthetic-repo\n"),
    ("repository_id", "synthetic-repo", "synthetic-repo\nSTATUS-ONLY forged"),
    ("repository_id", "synthetic-repo", "-leading-dash"),
    ("repository_id", "synthetic-repo", "repo‑lookalike"),
    ("repository_id", "synthetic-repo", "repо"),  # Cyrillic o
    ("repository_id", "synthetic-repo", ""),
    ("repository_id", "synthetic-repo", "r" * 49),
    ("task_id", "SMP-001", "smp-001"),
    ("task_id", "SMP-001", "SMP-001\n"),
    ("task_id", "SMP-001", "SMP-1"),
    ("task_id", "SMP-001", "SMP-001 extra text"),
    ("event", "task_failed", "approved"),
    ("event", "task_failed", "verified"),
    ("event", "task_failed", "free text event"),
    ("event", "task_failed", ""),
    ("occurred_at", "2026-10-23T05:00:00Z", "2026-10-23T05:00:00+09:00"),
    ("occurred_at", "2026-10-23T05:00:00Z", "2026-10-23 05:00:00Z"),
    ("occurred_at", "2026-10-23T05:00:00Z", "2026-02-30T05:00:00Z"),
    ("occurred_at", "2026-10-23T05:00:00Z", "2026-10-23T25:00:00Z"),
    ("occurred_at", "2026-10-23T05:00:00Z", "2026-10-23T05:00:00Z\n"),
    ("occurred_at", "2026-10-23T05:00:00Z", "2026-10-23T05:00:00.123Z"),
])
def test_paired_accept_and_refuse(field, accepted, refused):
    build_status_notification(**good(**{field: accepted}))
    with pytest.raises(StatusNotificationError):
        build_status_notification(**good(**{field: refused}))
    with pytest.raises(StatusNotificationError):
        validate_status_notification(payload(**{field: refused}))


def test_non_string_and_string_subclass_values_are_refused():
    class Sneaky(str):
        pass

    for field, original in good().items():
        for bad in (None, 7, [original], Sneaky(original)):
            with pytest.raises(StatusNotificationError):
                build_status_notification(**good(**{field: bad}))
            with pytest.raises(StatusNotificationError):
                validate_status_notification(payload(**{field: bad}))
    with pytest.raises(StatusNotificationError):
        validate_status_notification({**payload(), "contract_version": ["status-notification/1"]})
    for bad in (None, ["x"], "x", 1):
        with pytest.raises(StatusNotificationError):
            validate_status_notification(bad)


def test_wrong_contract_version_is_refused():
    for version in ("status-notification/2", "governance-assessment/1", "", None):
        with pytest.raises(StatusNotificationError):
            validate_status_notification({**payload(), "contract_version": version})


def test_errors_never_echo_submitted_values():
    attempts = [
        lambda: build_status_notification(**good(repository_id=SENTINEL + ".example.com")),
        lambda: build_status_notification(**good(task_id=SENTINEL)),
        lambda: validate_status_notification({**payload(), "message": SENTINEL}),
        lambda: validate_status_notification(payload(event=SENTINEL)),
    ]
    for attempt in attempts:
        with pytest.raises(StatusNotificationError) as caught:
            attempt()
        assert SENTINEL not in str(caught.value) and SENTINEL not in repr(caught.value)
        assert caught.value.__cause__ is None


def test_seeded_free_text_marker_cannot_reach_any_output_channel():
    # Positive control: text with spaces or punctuation is accepted in no field.
    marker = "synthetic marker: do not echo"
    for key in ("repository_id", "task_id", "event", "occurred_at"):
        with pytest.raises(StatusNotificationError):
            build_status_notification(**good(**{key: marker}))
    note = build_status_notification(**good())
    assert marker not in note.payload_json and marker not in note.text


def test_residual_identifier_shaped_text_is_accepted_and_must_be_operator_assigned():
    # Pins a documented limit: the contract checks shape, not provenance. A short
    # identifier-shaped string is accepted, so repository_id must come from the
    # operator's own registry and never from PR, hook or model-produced text.
    note = build_status_notification(**good(repository_id=SENTINEL))
    assert SENTINEL in note.text


def test_events_do_not_claim_approval_verification_completion_or_merge():
    schema_events = set(load_schema("status-notification.schema.json")
                        ["properties"]["event"]["enum"])
    assert schema_events == set(EVENTS)
    for event in EVENTS:
        for claim in ("verified", "complete", "approved", "merged", "released", "deployed"):
            assert claim not in event


def test_schema_and_code_agree_on_repository_id_boundary():
    import jsonschema
    schema = load_schema("status-notification.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    for value in ("ok-id", "a" * 31, "A_b-9", "ab-" * 16):
        assert validator.is_valid(payload(repository_id=value)), value
        build_status_notification(**good(repository_id=value))
    for value in ("a.b", "a/b", "r" * 32, "r" * 48, "r" * 49, "x\n"):
        assert not validator.is_valid(payload(repository_id=value)), value
        with pytest.raises(StatusNotificationError):
            build_status_notification(**good(repository_id=value))


def test_schema_and_code_refuse_impossible_calendar_dates():
    import jsonschema
    schema = load_schema("status-notification.schema.json")
    # JSON Schema treats format as an annotation without the project's checker.
    validator = jsonschema.Draft202012Validator(schema, format_checker=DEFAULT_FORMAT_CHECKER)
    for value in ("2026-10-23T05:00:00Z", "2028-02-29T23:59:59Z"):
        assert validator.is_valid(payload(occurred_at=value))
        build_status_notification(**good(occurred_at=value))
    for value in ("2026-02-29T05:00:00Z", "2026-02-30T05:00:00Z"):
        assert not validator.is_valid(payload(occurred_at=value))
        with pytest.raises(StatusNotificationError):
            build_status_notification(**good(occurred_at=value))


def test_module_has_no_network_process_or_environment_surface():
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"socket", "ssl", "http", "urllib", "requests", "smtplib", "subprocess",
                 "os", "shutil", "sqlite3", "asyncio", "ftplib", "webbrowser"}
    assert not imported & forbidden
    assert "orchestrator" in imported  # only the schema validator from this project
    internal = {node.module for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
                and node.module.startswith("orchestrator")}
    assert internal == {"orchestrator.core.schema"}

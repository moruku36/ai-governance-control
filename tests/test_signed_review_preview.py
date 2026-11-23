"""Run the same detached fixture against the real CLI and Python API."""
import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.core.signed_review_preview import MAX_BUNDLE_BYTES, preview_signed_review


def _json(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("ascii")


def _key(label):
    return hashlib.sha256(b"agc:public-signed-review-fixture:" + label.encode()).digest()


def _seal(domain, body, label):
    frame = b"ai-governance-control:" + domain.encode() + b"\0" + _json(body)
    return hashlib.sha256(frame).hexdigest(), {
        "body": body,
        "tag": hmac.new(_key(label), frame, "sha256").hexdigest(),
    }


def _key_id(label):
    return "key-" + hashlib.sha256(_key(label)).hexdigest()[:32]


def _context_digest(context):
    wrapped = {
        "domain": "ai-governance-control:approval-context-preview",
        "version": "offline-approval-context/1",
        "context": context,
    }
    return hashlib.sha256(_json(wrapped)).hexdigest()


def _approval_tag(payload, label="reviewer"):
    _, payload["approval"] = _seal(
        "fixture-review-approval/1", payload["approval"]["body"], label
    )


def _bundle(reviewer="reviewer"):
    context = {
        "version": "offline-approval-context/1",
        "action": "task_execution",
        "task_id": "FIXTURE-101",
        "repository_id": "agc-signed-review-fixture",
        "repository": "https://example.invalid/agc/fixture",
        "base_sha": "a" * 40,
        "candidate_sha": "b" * 40,
        "candidate_seal_digest": "c" * 64,
        "assessment_digest": "d" * 64,
        "policy_hash": "e" * 64,
        "plan_hash": "f" * 64,
        "approved_suite_digest": "1" * 64,
        "runner_profile_digest": "2" * 64,
        "manifest_digest": "3" * 64,
        "target_ref": "refs/heads/task/fixture-example",
        "runtime": {
            "profile": "offline-linux-v1",
            "image": "sha256:" + "4" * 64,
            "runtime_root": "/fixture/runtime",
            "worktree_reference": "/fixture/candidate",
            "command_id": "check-docs",
            "argv": ["/fixture/bin/check-docs", "unreflected-inert-test-marker"],
            "timeout_sec": 3,
            "network": "NONE",
            "inputs": {"fixture": "5" * 64},
        },
    }
    roster = {
        "version": "agc-fixture-reviewer-registry/1",
        "reviewers": {
            f"fixture:principal:{label}": {
                "enabled": enabled,
                "role": role,
                "epoch": f"fixture:activation:{label}-1",
                "key_id": _key_id(label),
            }
            for label, enabled, role in (
                ("reviewer", True, "reviewer"),
                ("disabled", False, "reviewer"),
                ("actor", True, "actor"),
                ("requester", True, "reviewer"),
            )
        },
    }
    review_text = "Fixture: 審査\nExact review bytes.\n"
    roster_digest, registry = _seal("fixture-reviewer-registry/1", roster, "registry-authority")
    payload = {
        "context": context,
        "review_text": review_text,
        "registry": registry,
        "approval": {
            "body": {
                "version": "agc-fixture-review-approval/1",
                "token_id": "fixture:approval:example",
                "reviewer_id": f"fixture:principal:{reviewer}",
                "reviewer_epoch": f"fixture:activation:{reviewer}-1",
                "key_id": _key_id(reviewer),
                "requester_id": "fixture:principal:requester",
                "registry_digest": roster_digest,
                "context_digest": _context_digest(context),
                "review_digest": hashlib.sha256(review_text.encode()).hexdigest(),
                "issued_at": 1_799_999_990,
                "expires_at": 1_800_000_010,
            },
        },
    }
    _approval_tag(payload, reviewer)
    return payload


def _assert_both(raw, reason, match=False):
    expected = {
        "reason": reason,
        "mode": "MANUAL_ONLY",
        "approval_verified": False,
        "execution_authorized": False,
        "token_consumed": False,
    }
    assert preview_signed_review(raw).summary() == expected
    cli = subprocess.run(
        [sys.executable, "-m", "orchestrator.signed_review_preview"],
        input=raw,
        capture_output=True,
        check=False,
        timeout=10,
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert cli.returncode == (0 if match else 2)
    assert cli.stderr == b""
    assert json.loads(cli.stdout) == expected


def test_matching_fixture_is_never_approval():
    _assert_both(_json(_bundle()), "FIXTURE_SIGNED_REVIEW_MATCH", match=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("base_sha", "7" * 40),
        ("candidate_sha", "8" * 40),
        ("candidate_seal_digest", "9" * 64),
        ("assessment_digest", "0" * 64),
        ("target_ref", "refs/heads/task/fixture-different"),
    ],
)
def test_changed_context_refused_even_if_token_is_unchanged(field, value):
    payload = _bundle()
    payload["context"][field] = value
    _assert_both(_json(payload), "APPROVAL_CONTEXT_MISMATCH")
    # Changing the digest alongside the candidate cannot repair the old tag.
    payload["approval"]["body"]["context_digest"] = _context_digest(payload["context"])
    _assert_both(_json(payload), "APPROVAL_TAG_MISMATCH")


def test_editing_review_bytes_or_digest_cannot_repin_approval():
    payload = _bundle()
    payload["review_text"] = payload["review_text"].replace("\n", "\r\n")
    _assert_both(_json(payload), "APPROVAL_REVIEW_MISMATCH")
    payload["approval"]["body"]["review_digest"] = hashlib.sha256(
        payload["review_text"].encode()
    ).hexdigest()
    _assert_both(_json(payload), "APPROVAL_TAG_MISMATCH")


@pytest.mark.parametrize(
    "reviewer,reason",
    [
        ("absent", "UNKNOWN_REVIEWER"),
        ("disabled", "DISABLED_REVIEWER"),
        ("actor", "REVIEWER_NOT_ELIGIBLE"),
        ("requester", "REVIEWER_NOT_ELIGIBLE"),
    ],
)
def test_a_valid_tag_does_not_make_unqualified_reviewer_eligible(reviewer, reason):
    _assert_both(_json(_bundle(reviewer)), reason)


def test_registry_cannot_be_changed_or_replaced_and_resigned():
    payload = _bundle("disabled")
    registry = payload["registry"]["body"]
    registry["reviewers"]["fixture:principal:disabled"]["enabled"] = True
    _assert_both(_json(payload), "REGISTRY_TAG_MISMATCH")
    digest, payload["registry"] = _seal("fixture-reviewer-registry/1", registry, "registry-authority")
    payload["approval"]["body"]["registry_digest"] = digest
    _approval_tag(payload, "disabled")
    _assert_both(_json(payload), "REGISTRY_SNAPSHOT_MISMATCH")


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("registry_digest", "0" * 64, "APPROVAL_REGISTRY_MISMATCH"),
        ("key_id", _key_id("actor"), "REVIEWER_KEY_OR_EPOCH_MISMATCH"),
        (
            "reviewer_epoch",
            "fixture:activation:reviewer-0",
            "REVIEWER_KEY_OR_EPOCH_MISMATCH",
        ),
        ("requester_id", "fixture:principal:other", "REQUESTER_MISMATCH"),
        ("expires_at", 1_800_000_000, "APPROVAL_OUTSIDE_FIXTURE_WINDOW"),
    ],
)
def test_signed_but_stale_or_unbound_approval_denied(field, value, reason):
    payload = _bundle()
    payload["approval"]["body"][field] = value
    _approval_tag(payload)
    _assert_both(_json(payload), reason)


def test_wrong_reviewer_key_cannot_use_registered_identity():
    payload = _bundle()
    _approval_tag(payload, "actor")
    _assert_both(_json(payload), "APPROVAL_TAG_MISMATCH")


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b"\xff",
        b" " * (MAX_BUNDLE_BYTES + 1),
        b'{"registry":{"tag":"a","tag":"b"}}',
        b'{"approval":{"body":{"expires_at":NaN}}}',
    ],
    ids=["empty", "truncated", "utf8", "oversize", "duplicate", "nonfinite"],
)
def test_invalid_input_is_bounded_and_not_echoed(raw):
    _assert_both(raw, "INVALID_FIXTURE_PAYLOAD")


def test_regular_context_cannot_enter_the_fixture_gate():
    payload = _bundle()
    payload["context"]["repository"] = "https://example.com/live"
    payload["approval"]["body"]["context_digest"] = _context_digest(payload["context"])
    _approval_tag(payload)
    _assert_both(_json(payload), "INVALID_FIXTURE_PAYLOAD")


def test_duplicate_nested_key_in_otherwise_matching_bundle_is_refused():
    raw = _json(_bundle())
    member = b'"key_id":"' + _key_id("reviewer").encode() + b'"'
    assert member in raw
    # The replacement preserves the parsed meaning under last-key-wins parsing.
    raw = raw.replace(member, member + b"," + member, 1)
    _assert_both(raw, "INVALID_FIXTURE_PAYLOAD")


def test_review_is_capped_by_utf8_bytes_not_characters():
    payload = _bundle()
    payload["review_text"] = "審" * 6000
    payload["approval"]["body"]["review_digest"] = hashlib.sha256(
        payload["review_text"].encode("utf-8")
    ).hexdigest()
    _approval_tag(payload)
    _assert_both(_json(payload), "INVALID_FIXTURE_PAYLOAD")


def test_caller_cannot_supply_authority_flags():
    payload = _bundle()
    payload["approval"]["execution_authorized"] = True
    _assert_both(_json(payload), "INVALID_FIXTURE_PAYLOAD")

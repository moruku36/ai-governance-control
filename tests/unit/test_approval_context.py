"""Shared API/real CLI canonicalization; no token issuance or command execution."""

import copy
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from orchestrator.core.approval_context import (
    DOMAIN,
    MAX_CONTEXT_BYTES,
    STATUS,
    VERSION,
    ApprovalContextError,
    build_approval_context,
    parse_approval_context,
)


@pytest.fixture
def payload():
    return {
        "version": VERSION, "action": "task_execution", "task_id": "TEST-001",
        "repository_id": "synthetic", "repository": "https://example.invalid/public-repo",
        "base_sha": "1" * 40, "candidate_sha": "2" * 40,
        "candidate_seal_digest": "3" * 64, "assessment_digest": "4" * 64,
        "policy_hash": "5" * 64, "plan_hash": "6" * 64,
        "approved_suite_digest": "7" * 64, "runner_profile_digest": "8" * 64,
        "manifest_digest": "9" * 64, "target_ref": "refs/heads/task/synthetic",
        "runtime": {"profile": "offline-linux-v1", "image": "sha256:" + "a" * 64,
                    "runtime_root": "/synthetic/runtime", "worktree_reference": "/synthetic/tree",
                    "command_id": "pytest", "argv": ["/usr/bin/python", "-m", "pytest", "tests"],
                    "timeout_sec": 30, "network": "NONE", "inputs": {"request.txt": "b" * 64}},
    }


def cli(raw, tmp_path, *args):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]),
               PYTHONDONTWRITEBYTECODE="1", AI_FACTORY_APPROVAL_SECRET="SYNTHETIC_DO_NOT_ECHO")
    return subprocess.run([sys.executable, "-m", "orchestrator.approval_context", *args],
                          input=raw, capture_output=True, cwd=tmp_path, env=env, timeout=5, check=False)


def test_api_cli_share_exact_digest_and_do_not_write(payload, tmp_path):
    before = list(tmp_path.iterdir())
    api = build_approval_context(payload)
    result = cli(json.dumps(payload).encode(), tmp_path)
    assert result.returncode == 0 and result.stderr == b""
    assert json.loads(result.stdout) == api.summary()
    assert api.status == STATUS
    assert list(tmp_path.iterdir()) == before
    assert b"SYNTHETIC_DO_NOT_ECHO" not in result.stdout
    assert b"request.txt" not in result.stdout and b"argv" not in result.stdout
    assert api.digest != __import__("hashlib").sha256(api.canonical_json.encode()).hexdigest()
    assert DOMAIN


def test_payload_detached_order_independent_and_immutable(payload):
    record = build_approval_context(payload)
    reversed_keys = dict(reversed(list(payload.items())))
    assert build_approval_context(reversed_keys) == record
    assert parse_approval_context(json.dumps(payload, indent=4).encode()) == record
    payload["runtime"]["argv"].append("mutated")
    assert "mutated" not in record.canonical_json
    assert build_approval_context(payload).digest != record.digest
    with pytest.raises(FrozenInstanceError):
        record.digest = "f" * 64


CHANGES = {
    "task_id": "TEST-002", "repository_id": "other", "repository": "https://example.invalid/other",
    "base_sha": "f" * 40, "candidate_sha": "e" * 40,
    "candidate_seal_digest": "f" * 64, "assessment_digest": "f" * 64,
    "policy_hash": "f" * 64, "plan_hash": "f" * 64,
    "approved_suite_digest": "f" * 64, "runner_profile_digest": "f" * 64,
    "manifest_digest": "f" * 64, "target_ref": "refs/heads/task/other",
    "runtime.image": "sha256:" + "f" * 64, "runtime.runtime_root": "/other/runtime",
    "runtime.worktree_reference": "/other/tree", "runtime.command_id": "ruff",
    "runtime.argv": ["/usr/bin/python", "-m", "pytest", "different tests"],
    "runtime.timeout_sec": 31, "runtime.inputs": {"different.txt": "b" * 64},
}


def set_field(payload, path, value):
    parent = payload
    keys = path.split(".")
    for key in keys[:-1]:
        parent = parent[key]
    parent[keys[-1]] = value


@pytest.mark.parametrize("path,value", list(CHANGES.items()))
def test_every_mutable_binding_changes_shared_digest(payload, tmp_path, path, value):
    original = build_approval_context(payload).digest
    set_field(payload, path, value)
    api = build_approval_context(payload)
    assert api.digest != original
    result = cli(json.dumps(payload).encode(), tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout)["digest"] == api.digest


def test_input_content_digest_and_argv_boundaries_are_bound(payload):
    original = build_approval_context(payload).digest
    payload["runtime"]["inputs"]["request.txt"] = "c" * 64
    assert build_approval_context(payload).digest != original
    payload["runtime"]["argv"] = ["/usr/bin/python", "one two"]
    single = build_approval_context(payload).digest
    payload["runtime"]["argv"] = ["/usr/bin/python", "one", "two"]
    assert build_approval_context(payload).digest != single


INVALID = [
    ("version", "other"), ("action", "merge"), ("task_id", "arbitrary"),
    ("repository_id", "bad/id"), ("repository", ""), ("target_ref", "bad\nref"),
    ("base_sha", "unknown"), ("candidate_sha", "HEAD"),
    ("candidate_seal_digest", "bad"), ("assessment_digest", "A" * 64),
    ("policy_hash", None), ("plan_hash", "g" * 64), ("approved_suite_digest", 1),
    ("runner_profile_digest", True), ("manifest_digest", ""),
    ("runtime.profile", "live"), ("runtime.network", "PUBLIC"),
    ("runtime.image", "python:latest"), ("runtime.runtime_root", "relative"),
    ("runtime.worktree_reference", "/a/../b"), ("runtime.command_id", "pytest tests"),
    ("runtime.argv", "python -m pytest"), ("runtime.argv", []),
    ("runtime.argv", ["", "arg"]), ("runtime.argv", ["/usr/bin/python", None]),
    ("runtime.argv", ["/usr/bin/python", "nul\0arg"]), ("runtime.timeout_sec", True),
    ("runtime.timeout_sec", 0), ("runtime.inputs", {"../escape": "b" * 64}),
    ("runtime.inputs", {"valid": "bad"}), ("runtime.inputs", []), ("runtime", None),
]


@pytest.mark.parametrize("path,value", INVALID)
def test_invalid_fields_fail_closed_without_echo(payload, tmp_path, path, value):
    set_field(payload, path, value)
    with pytest.raises(ApprovalContextError, match="^Invalid approval context$"):
        build_approval_context(payload)
    result = cli(json.dumps(payload).encode(), tmp_path)
    assert result.returncode == 2 and result.stdout == b""
    assert result.stderr == ("Invalid approval context" + os.linesep).encode("ascii")


@pytest.mark.parametrize("location", ["top", "runtime"])
def test_unknown_and_missing_fields_rejected(payload, location):
    for mutation in ("unknown", "missing"):
        data = copy.deepcopy(payload)
        node = data if location == "top" else data["runtime"]
        if mutation == "unknown":
            node["SECRET_MARKER"] = "SYNTHETIC_SECRET"
        else:
            del node[next(iter(node))]
        with pytest.raises(ApprovalContextError):
            build_approval_context(data)


@pytest.mark.parametrize("raw", [b"", b"{}", b"[]", b"null", b"\xff", b"{", b"{}{}",
                                 b'{"key":1,"key":2}', b'{"x":NaN}', b'{"x":Infinity}',
                                 b"[" * 2000 + b"]" * 2000, b" " * (MAX_CONTEXT_BYTES + 1)],
                         ids=["empty", "object", "array", "null", "invalid-utf8", "incomplete",
                              "trailing-object", "duplicate-key", "nan", "infinity",
                              "excessive-nesting", "oversized"])
def test_bounded_parser_and_cli_reject_malformed(raw, tmp_path):
    with pytest.raises(ApprovalContextError):
        parse_approval_context(raw)
    result = cli(raw, tmp_path)
    assert result.returncode == 2 and result.stdout == b""
    assert result.stderr == ("Invalid approval context" + os.linesep).encode("ascii")


def test_nested_duplicate_key_rejected(payload, tmp_path):
    raw = json.dumps(payload).replace('"timeout_sec": 30', '"timeout_sec":30,"timeout_sec":31').encode()
    with pytest.raises(ApprovalContextError):
        parse_approval_context(raw)
    assert cli(raw, tmp_path).returncode == 2


def test_literal_argv_is_not_executed_or_echoed(payload, tmp_path):
    sentinel = "SYNTHETIC_SECRET; touch never-created\necho ignored"
    payload["runtime"]["argv"] = ["/nonexistent-executable", "-c", sentinel]
    result = cli(json.dumps(payload).encode(), tmp_path)
    assert result.returncode == 0
    assert sentinel.encode() not in result.stdout and result.stderr == b""
    assert list(tmp_path.iterdir()) == []
    result = cli(b"", tmp_path, sentinel)
    assert result.returncode == 2 and sentinel.encode() not in result.stderr


def test_oversized_api_payload_rejected(payload):
    payload["runtime"]["argv"] = ["/usr/bin/python"] + ["x" * 4096] * 32
    with pytest.raises(ApprovalContextError):
        build_approval_context(payload)


def test_preview_does_not_project_or_change_legacy_context(payload):
    from types import SimpleNamespace

    from orchestrator.adapters.container import ApprovedContainerAdapter

    plan = {"repository": payload["repository"], "head_sha": payload["base_sha"],
            "target_ref": payload["target_ref"], "policy_hash": payload["policy_hash"],
            "plan_hash": payload["plan_hash"], "command_id": "pytest",
            "inputs": {"request.txt": b"synthetic"}}
    manifest = {"id": payload["task_id"]}
    runner = SimpleNamespace(commands={"pytest": SimpleNamespace(
        argv=payload["runtime"]["argv"], timeout_sec=30)}, image_id=payload["runtime"]["image"],
        root=Path("/synthetic/runtime"))
    before = ApprovedContainerAdapter._context(manifest, "/synthetic/tree", plan, runner)
    preview = build_approval_context(payload)
    after = ApprovedContainerAdapter._context(manifest, "/synthetic/tree", plan, runner)
    assert before == after
    assert set(after) == {"repository", "head_sha", "target_ref", "policy_hash", "plan_hash",
                          "action", "task_id", "argv_digest"}
    assert after["plan_hash"] == payload["plan_hash"]
    assert after["head_sha"] == payload["base_sha"] != payload["candidate_sha"]
    assert preview.digest != after["argv_digest"]


def test_flat_input_count_matches_runner_limit(payload):
    payload["runtime"]["inputs"] = {f"input-{i}": "b" * 64 for i in range(100)}
    build_approval_context(payload)
    payload["runtime"]["inputs"]["input-100"] = "b" * 64
    with pytest.raises(ApprovalContextError):
        build_approval_context(payload)


def test_preview_command_is_representable_by_current_container_command(payload):
    from orchestrator.core.container import ContainerCommand

    build_approval_context(payload)
    runtime = payload["runtime"]
    command = ContainerCommand(tuple(runtime["argv"]), runtime["timeout_sec"])
    assert command.argv == tuple(runtime["argv"])
    for timeout in (1, 300):
        runtime["timeout_sec"] = timeout
        build_approval_context(payload)
        ContainerCommand(tuple(runtime["argv"]), timeout)


@pytest.mark.parametrize("path,value", [
    ("runtime.argv", ["python", "relative-executable"]),
    ("runtime.argv", ["/usr/bin/python", ""]),
    ("runtime.timeout_sec", 301),
    ("runtime.inputs", {"nested/file": "b" * 64}),
    ("runtime.inputs", {"a" * 101: "b" * 64}),
    ("runtime.inputs", {".leading": "b" * 64}),
    ("runtime.runtime_root", "/unsupported,mount"),
    ("runtime.worktree_reference", "/unsupported,mount"),
])
def test_unsupported_offline_profile_values_rejected(payload, tmp_path, path, value):
    set_field(payload, path, value)
    with pytest.raises(ApprovalContextError):
        build_approval_context(payload)
    result = cli(json.dumps(payload).encode(), tmp_path)
    assert result.returncode == 2 and result.stdout == b""
    assert result.stderr == ("Invalid approval context" + os.linesep).encode("ascii")

"""Shared, non-authorizing offline approval-context preview contract.

No token, ledger, credential, process-execution or network operations are imported.
"""

import hashlib
import json
import re
from dataclasses import dataclass

VERSION = "offline-approval-context/1"
DOMAIN = "ai-governance-control:approval-context-preview"
STATUS = "PREVIEW_NOT_AUTHORIZATION"
MAX_CONTEXT_BYTES = 64 * 1024
_TOP = {"version", "action", "task_id", "repository_id", "repository", "base_sha",
        "candidate_sha", "candidate_seal_digest", "assessment_digest", "policy_hash",
        "plan_hash", "approved_suite_digest", "runner_profile_digest", "manifest_digest",
        "target_ref", "runtime"}
_RUNTIME = {"profile", "image", "runtime_root", "worktree_reference", "command_id",
            "argv", "timeout_sec", "network", "inputs"}


class ApprovalContextError(ValueError):
    """Invalid preview input; messages never contain submitted field values."""


def _require(condition):
    if not condition:
        raise ApprovalContextError("Invalid approval context")


def _text(value, maximum=1024):
    return (type(value) is str and 0 < len(value) <= maximum
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def _matches(pattern, value):
    return type(value) is str and re.fullmatch(pattern, value) is not None


def _validate(data):
    _require(type(data) is dict and set(data) == _TOP)
    _require(data["version"] == VERSION and data["action"] == "task_execution")
    _require(_matches(r"[A-Z][A-Z0-9]{1,7}-[0-9]{3,6}", data["task_id"]))
    _require(_matches(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", data["repository_id"]))
    for key in ("repository", "target_ref"):
        _require(_text(data[key]))
    for key in ("base_sha", "candidate_sha"):
        _require(_matches(r"[0-9a-f]{40}", data[key]))
    for key in ("candidate_seal_digest", "assessment_digest", "policy_hash", "plan_hash",
                "approved_suite_digest", "runner_profile_digest", "manifest_digest"):
        _require(_matches(r"[0-9a-f]{64}", data[key]))
    runtime = data["runtime"]
    _require(type(runtime) is dict and set(runtime) == _RUNTIME)
    _require(runtime["profile"] == "offline-linux-v1" and runtime["network"] == "NONE")
    _require(_matches(r"sha256:[0-9a-f]{64}", runtime["image"]))
    for key in ("runtime_root", "worktree_reference"):
        _require(_text(runtime[key]) and runtime[key].startswith("/")
                 and "\\" not in runtime[key] and "," not in runtime[key]
                 and all(part not in {".", "..", ""} for part in runtime[key].split("/")[1:]))
    _require(_matches(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", runtime["command_id"]))
    argv = runtime["argv"]
    _require(type(argv) is list and 0 < len(argv) <= 256)
    # argv is literal data, not a raw command line; match ContainerCommand shape.
    _require(all(type(arg) is str and 0 < len(arg) <= 4096 and "\0" not in arg for arg in argv))
    _require(argv[0].startswith("/"))
    _require(type(runtime["timeout_sec"]) is int and 1 <= runtime["timeout_sec"] <= 300)
    inputs = runtime["inputs"]
    _require(type(inputs) is dict and len(inputs) <= 100)
    for name, digest in inputs.items():
        _require(_matches(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", name))
        _require(_matches(r"[0-9a-f]{64}", digest))


@dataclass(frozen=True)
class ApprovalContextPreview:
    digest: str
    canonical_json: str
    version: str = VERSION
    status: str = STATUS

    def summary(self):
        """Safe CLI summary: no command, path, repository or input data is echoed."""
        return {"status": self.status, "version": self.version, "digest": self.digest}


def build_approval_context(data: dict) -> ApprovalContextPreview:
    """Validate and detach caller data into a domain/version-bound immutable preview.

    Input hashes/references are assertions here, not independently measured facts.
    This does not authorize an action or populate any existing approval token field.
    """
    try:
        _validate(data)
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False)
        _require(len(canonical.encode("ascii")) <= MAX_CONTEXT_BYTES)
        detached = json.loads(canonical)
        _validate(detached)
        bound = json.dumps({"domain": DOMAIN, "version": VERSION, "context": detached},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return ApprovalContextPreview(hashlib.sha256(bound.encode("ascii")).hexdigest(), canonical)
    except (ValueError, TypeError, RecursionError, KeyError, OverflowError):
        raise ApprovalContextError("Invalid approval context") from None


def parse_approval_context(raw: bytes) -> ApprovalContextPreview:
    """Bounded UTF-8 JSON parsing with duplicate-key and nonfinite-number refusal."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result)
            result[key] = value
        return result

    def invalid_constant(_value):
        raise ApprovalContextError("Invalid approval context")

    try:
        _require(type(raw) is bytes and 0 < len(raw) <= MAX_CONTEXT_BYTES)
        data = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                          parse_constant=invalid_constant)
        return build_approval_context(data)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ApprovalContextError("Invalid approval context") from None

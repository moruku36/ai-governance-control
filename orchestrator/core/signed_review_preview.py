"""Ambiguity-refusing comparison of signed, disconnected G2 fixtures.

The fixed fixture trust anchors are public and must never be used for live approvals.
"""
import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from orchestrator.core.approval_context import ApprovalContextError, build_approval_context
from orchestrator.core.auth import derive_key_fingerprint

MAX_BUNDLE_BYTES = 128 * 1024
_MAX_REVIEW_BYTES = 16 * 1024
_FIXTURE_REPO = "https://example.invalid/agc/fixture"
_REQUESTER = "fixture:principal:requester"
_CHECKED_AT = 1_800_000_000
_ROSTER_VERSION = "agc-fixture-reviewer-registry/1"
_APPROVAL_VERSION = "agc-fixture-review-approval/1"
_ROSTER_DOMAIN = b"ai-governance-control:fixture-reviewer-registry/1\0"
_APPROVAL_DOMAIN = b"ai-governance-control:fixture-review-approval/1\0"
_HEX256 = re.compile(r"[0-9a-f]{64}")
_PRINCIPAL = re.compile(r"fixture:principal:[a-z0-9][a-z0-9-]{0,63}")
_TOKEN = re.compile(r"fixture:approval:[a-z0-9][a-z0-9-]{0,63}")
_TASK = re.compile(r"FIXTURE-[0-9]{3,6}")
_DESTINATION = re.compile(r"refs/heads/task/fixture-[a-z0-9][a-z0-9-]{0,63}")
_EPOCH = re.compile(r"fixture:activation:[a-z0-9][a-z0-9-]{0,63}")
_KEY_ID = re.compile(r"key-[0-9a-f]{32}")
_APPROVAL_FIELDS = {
    "version", "token_id", "reviewer_id", "reviewer_epoch", "key_id", "requester_id",
    "registry_digest", "context_digest", "review_digest", "issued_at", "expires_at",
}


@dataclass(frozen=True, slots=True)
class SignedReviewPreview:
    reason: str
    mode: Literal["MANUAL_ONLY"] = field(init=False, default="MANUAL_ONLY")
    approval_verified: Literal[False] = field(init=False, default=False)
    execution_authorized: Literal[False] = field(init=False, default=False)
    token_consumed: Literal[False] = field(init=False, default=False)

    def summary(self) -> dict:
        return asdict(self)


class _InvalidFixture(ValueError):
    pass


def _require(condition: bool) -> None:
    if not condition:
        raise _InvalidFixture


def _unique(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    raise _InvalidFixture


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _fixture_key(label: str) -> bytes:
    # Deliberately public, deterministic test vectors, not operational credentials.
    return hashlib.sha256(f"agc:public-signed-review-fixture:{label}".encode("ascii")).digest()


def _registry_pin() -> str:
    # Non-input trust anchor for the exact synthetic snapshot, not a writable registry.
    rows = {}
    for label, enabled, role in (
        ("reviewer", True, "reviewer"),
        ("disabled", False, "reviewer"),
        ("actor", True, "actor"),
        ("requester", True, "reviewer"),
    ):
        rows[f"fixture:principal:{label}"] = {
            "enabled": enabled,
            "role": role,
            "epoch": f"fixture:activation:{label}-1",
            "key_id": derive_key_fingerprint(_fixture_key(label)),
        }
    return hashlib.sha256(
        _ROSTER_DOMAIN + _canonical({"version": _ROSTER_VERSION, "reviewers": rows})
    ).hexdigest()


def _matches(pattern: re.Pattern, value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _signed_parts(value: object) -> tuple[dict, str]:
    _require(type(value) is dict and value.keys() == {"body", "tag"})
    body, tag = value["body"], value["tag"]
    _require(type(body) is dict and _matches(_HEX256, tag))
    return body, tag


def _valid_approval(body: dict) -> bool:
    return (
        body.keys() == _APPROVAL_FIELDS
        and body["version"] == _APPROVAL_VERSION
        and _matches(_TOKEN, body["token_id"])
        and _matches(_PRINCIPAL, body["reviewer_id"])
        and _matches(_EPOCH, body["reviewer_epoch"])
        and _matches(_KEY_ID, body["key_id"])
        and _matches(_PRINCIPAL, body["requester_id"])
        and all(
            _matches(_HEX256, body[name])
            for name in ("registry_digest", "context_digest", "review_digest")
        )
        and type(body["issued_at"]) is int
        and type(body["expires_at"]) is int
        and 0 <= body["issued_at"] < body["expires_at"] < 2**63
    )


def _evaluate(payload: dict) -> SignedReviewPreview:
    _require(type(payload) is dict and payload.keys() == {
        "context", "review_text", "registry", "approval",
    })
    context = payload["context"]
    context_digest = build_approval_context(context).digest
    _require(
        context["repository"] == _FIXTURE_REPO
        and context["repository_id"] == "agc-signed-review-fixture"
        and _matches(_TASK, context["task_id"])
        and _matches(_DESTINATION, context["target_ref"])
    )
    review_text = payload["review_text"]
    _require(type(review_text) is str and 0 < len(review_text) <= _MAX_REVIEW_BYTES)
    review_bytes = review_text.encode("utf-8", "strict")
    _require(len(review_bytes) <= _MAX_REVIEW_BYTES)
    review_digest = hashlib.sha256(review_bytes).hexdigest()

    registry, registry_tag = _signed_parts(payload["registry"])
    approval, approval_tag = _signed_parts(payload["approval"])
    _require(_valid_approval(approval))

    registry_frame = _ROSTER_DOMAIN + _canonical(registry)
    if not hmac.compare_digest(
        registry_tag, hmac.digest(_fixture_key("registry-authority"), registry_frame, "sha256").hex()
    ):
        return SignedReviewPreview("REGISTRY_TAG_MISMATCH")
    registry_digest = hashlib.sha256(registry_frame).hexdigest()
    if not hmac.compare_digest(registry_digest, _registry_pin()):
        return SignedReviewPreview("REGISTRY_SNAPSHOT_MISMATCH")
    if not hmac.compare_digest(approval["registry_digest"], registry_digest):
        return SignedReviewPreview("APPROVAL_REGISTRY_MISMATCH")
    if approval["requester_id"] != _REQUESTER:
        return SignedReviewPreview("REQUESTER_MISMATCH")

    reviewer = approval["reviewer_id"]
    row = registry["reviewers"].get(reviewer)
    if row is None:
        return SignedReviewPreview("UNKNOWN_REVIEWER")
    if not row["enabled"]:
        return SignedReviewPreview("DISABLED_REVIEWER")
    if reviewer == _REQUESTER or row["role"] != "reviewer":
        return SignedReviewPreview("REVIEWER_NOT_ELIGIBLE")
    if row["epoch"] != approval["reviewer_epoch"] or not hmac.compare_digest(
        row["key_id"], approval["key_id"]
    ):
        return SignedReviewPreview("REVIEWER_KEY_OR_EPOCH_MISMATCH")

    reviewer_key = _fixture_key(reviewer.removeprefix("fixture:principal:"))
    if not hmac.compare_digest(derive_key_fingerprint(reviewer_key), row["key_id"]):
        return SignedReviewPreview("REVIEWER_KEY_OR_EPOCH_MISMATCH")
    signed_frame = _APPROVAL_DOMAIN + _canonical(approval)
    if not hmac.compare_digest(approval_tag, hmac.digest(reviewer_key, signed_frame, "sha256").hex()):
        return SignedReviewPreview("APPROVAL_TAG_MISMATCH")
    if not approval["issued_at"] <= _CHECKED_AT < approval["expires_at"]:
        return SignedReviewPreview("APPROVAL_OUTSIDE_FIXTURE_WINDOW")
    if not hmac.compare_digest(approval["context_digest"], context_digest):
        return SignedReviewPreview("APPROVAL_CONTEXT_MISMATCH")
    if not hmac.compare_digest(approval["review_digest"], review_digest):
        return SignedReviewPreview("APPROVAL_REVIEW_MISMATCH")
    return SignedReviewPreview("FIXTURE_SIGNED_REVIEW_MATCH")


def preview_signed_review(raw: bytes) -> SignedReviewPreview:
    """Compare one bounded JSON bundle without producing any form of authority.

    Python and the CLI use this same entry point. No caller field chooses the
    trust anchor or clock. Input evidence is parsed into one detached snapshot;
    a match is not evidence of a live review, repository, or execution state.
    """
    try:
        _require(type(raw) is bytes and 0 < len(raw) <= MAX_BUNDLE_BYTES)
        payload = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_unique,
            parse_constant=_invalid_constant,
        )
        return _evaluate(payload)
    except (ApprovalContextError, ValueError, RecursionError):
        return SignedReviewPreview("INVALID_FIXTURE_PAYLOAD")

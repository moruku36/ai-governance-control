"""Non-authorizing R7 status-only notification contract (content only).

This module builds and validates the *content* of a notification. It never sends
anything, never receives a destination, endpoint, URL or credential, and has no
free-form field: there is no place to put review text, hook output, error text,
paths, commands or digests, so there is nothing to redact. Redaction is not the
control here; the absence of the field is.

A returned notification states that an event happened. It does not approve,
verify, complete, merge or authorize anything, and it changes no task state.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import jsonschema

from orchestrator.core.schema import validate_against_schema

CONTRACT_VERSION = "status-notification/1"
ALLOWED_FIELDS = frozenset(
    {"contract_version", "task_id", "repository_id", "event", "occurred_at"}
)
EVENTS = frozenset({
    "task_collected", "task_failed", "task_stopped",
    "approval_needed", "review_needed", "guard_denied",
})
MAX_TEXT_LENGTH = 200
_TASK_ID = re.compile(r"[A-Z][A-Z0-9]{1,7}-[0-9]{3,6}")
_REPOSITORY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
# A long unbroken alphanumeric run looks like a token or digest, not an identifier.
_TOKEN_LIKE_RUN = re.compile(r"[A-Za-z0-9]{32,}")


class StatusNotificationError(ValueError):
    """Invalid notification content. Messages never echo submitted values."""


@dataclass(frozen=True)
class StatusNotification:
    """Immutable, integrity-neutral content. Not an approval or a delivery."""

    payload_json: str
    text: str


def _fail() -> StatusNotificationError:
    return StatusNotificationError("Invalid status notification")


def _is_valid(record: Any) -> bool:
    if type(record) is not dict or set(record) != ALLOWED_FIELDS:
        return False
    for key in ("contract_version", "task_id", "repository_id", "occurred_at", "event"):
        if type(record[key]) is not str:
            return False
    if record["contract_version"] != CONTRACT_VERSION or record["event"] not in EVENTS:
        return False
    if _TASK_ID.fullmatch(record["task_id"]) is None:
        return False
    repository = record["repository_id"]
    if (_REPOSITORY_ID.fullmatch(repository) is None
            or _TOKEN_LIKE_RUN.search(repository) is not None):
        return False
    stamp = record["occurred_at"]
    if _TIMESTAMP.fullmatch(stamp) is None:
        return False
    try:
        datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return False
    return True


def _finish(record: dict[str, Any]) -> StatusNotification:
    if not _is_valid(record):
        raise _fail()
    try:
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False)
        # Defense in depth: the published schema must agree with the code checks.
        validate_against_schema(json.loads(canonical), "status-notification.schema.json")
    except (TypeError, ValueError, RecursionError, jsonschema.ValidationError):
        raise _fail() from None
    text = (f"[ai-governance-control] STATUS-ONLY {record['task_id']} {record['event']} "
            f"repo={record['repository_id']} at {record['occurred_at']}")
    if len(text) > MAX_TEXT_LENGTH or not text.isascii() or "\n" in text or "\r" in text:
        raise _fail()
    return StatusNotification(payload_json=canonical, text=text)


def build_status_notification(
    *, task_id: str, repository_id: str, event: str, occurred_at: str,
) -> StatusNotification:
    """Build a notification from the only fields the contract allows.

    Keyword-only on purpose: any extra argument (message, url, endpoint, output)
    is a TypeError, so free-form content cannot be added by accident.
    """
    return _finish({
        "contract_version": CONTRACT_VERSION, "task_id": task_id,
        "repository_id": repository_id, "event": event, "occurred_at": occurred_at,
    })


def validate_status_notification(payload: dict[str, Any]) -> StatusNotification:
    """Validate a detached payload, e.g. one produced by a hook, field for field.

    Unknown keys are refused rather than dropped, so a payload that tried to carry
    extra content is visible as a failure instead of being silently trimmed.
    """
    if type(payload) is not dict:
        raise _fail()
    return _finish(dict(payload))

# R7 status-only notification contract

Local implementation of **notification content only**. It is not a notifier, not
completed G4, not a report and not an authorization signal. Experimental /
MANUAL_ONLY and complete-diff receipt refusal remain unchanged.

## What it does

[`status_notification.py`](../../orchestrator/core/status_notification.py) builds
and validates a fixed-field notice described by
[`status-notification.schema.json`](../../schemas/status-notification.schema.json)
(contract version `status-notification/1`):

| Field | Constraint |
|-------|------------|
| `contract_version` | constant `status-notification/1` |
| `task_id` | existing task ID shape, e.g. `SMP-001` |
| `repository_id` | operator-assigned, `[A-Za-z0-9_-]`, at most 48 characters, no run of 32 or more alphanumerics |
| `event` | one of `task_collected`, `task_failed`, `task_stopped`, `approval_needed`, `review_needed`, `guard_denied` |
| `occurred_at` | strict UTC `YYYY-MM-DDTHH:MM:SSZ`, a real calendar time, supplied by the trusted caller |

The schema's calendar-time check uses `format: date-time` with the project's
format checker. Consumers using the schema directly must enable a compatible
format checker; JSON Schema otherwise treats `format` as an annotation. The
builder also checks calendar validity independently.

Unknown keys are refused, not trimmed, so a payload that tried to carry extra
content shows up as a failure. The builder is keyword-only: an extra argument such
as `message` or `url` is a `TypeError`. Output is an immutable pair of canonical
JSON and one ASCII status line (`[ai-governance-control] STATUS-ONLY <task> <event>
repo=<id> at <time>`), at most 200 characters.

## Why there is no redaction

The R7 proposal says filtering is weaker than not including the data. This
contract follows that: there is no field for review text, hook output, error text,
paths, commands, digests, URLs, endpoints or credentials, so nothing is redacted.
Dots, slashes, colons and at-signs are refused in `repository_id` so a hostname,
URL or webhook path cannot be carried there. No event name claims verified,
complete, approved or merged; `task_collected` mirrors the existing COLLECTED-only
receipt and does not promote it.

## Boundaries and limits

- The module imports no network, process, environment or storage library. A test
  checks this by parsing the module's imports. It never reads a clock and accepts
  no destination, so **notification endpoints are out of scope**; treat an
  endpoint name as a secret in whatever future sender is built, as the R7 note says.
- `task_id` and `repository_id` are checked for **shape, not provenance**. A short
  identifier-shaped string is accepted, and a test pins that. They must come from
  the operator's own registry, never from PR text, hook output or model output.
  The 32-character run rule is a heuristic, not a secret detector.
- A valid notification grants no permission, consumes no token, changes no task
  state and is not evidence that anything was verified. Reaching an event such as
  `approval_needed` does not approve anything.
- Not done here: a sender, a destination allowlist, rate limiting, delivery
  reconciliation, wiring into hooks, the CLI or the adapters, and the G4 pilot's
  measurement of what notifications carried. Roadmap order places G4 after G1/G2,
  so this is a standalone part awaiting those gates.

## Synthetic acceptance coverage

`tests/unit/test_status_notification.py` checks the exact field set against the
schema, the exact status line, immutability, round trip and key-order
independence, 13 extra-field names, keyword-only construction, missing fields, a
paired accept/refuse table (hostnames, URLs, paths, userinfo, ports, token-like
runs, whitespace, newline and forged-line injection, look-alike Unicode, malformed
and impossible timestamps, claim-like events), non-string and `str`-subclass
values, wrong versions, no echo of submitted values in errors, a free-text marker
accepted by no field, schema/code agreement, and the import restriction. These are
local content checks, not a live notifier, channel or injection test.

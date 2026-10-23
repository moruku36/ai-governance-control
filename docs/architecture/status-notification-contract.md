# R7 status-only notification contract

The core module implements **notification content only**. A separate optional
delivery adapter now prepares an HTTPS request, but has no CLI, hook or runtime
wiring. Neither module completes G4, produces a report, or grants authority.
Experimental / MANUAL_ONLY and complete-diff receipt refusal remain unchanged.

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

- The content module imports no network, process, environment or storage library.
  A test checks this by parsing the module's imports. It never reads a clock and
  accepts no destination. The separate delivery adapter treats its destination
  as sensitive in-memory operator configuration.
- `task_id` and `repository_id` are checked for **shape, not provenance**. A short
  identifier-shaped string is accepted, and a test pins that. They must come from
  the operator's own registry, never from PR text, hook output or model output.
  The 32-character run rule is a heuristic, not a secret detector.
- A valid notification grants no permission, consumes no token, changes no task
  state and is not evidence that anything was verified. Reaching an event such as
  `approval_needed` does not approve anything.
- Not done here: wiring into hooks or the CLI, rate limiting, durable delivery
  reconciliation, and the G4 pilot's measurement of what notifications carried.
  Roadmap order places G4 after G1/G2, so this remains standalone.

## Optional delivery adapter (local implementation only)

[`adapters/status_notification.py`](../../orchestrator/adapters/status_notification.py)
accepts only a canonical `StatusNotification`. It revalidates both JSON and text
before any transport call, so a forged dataclass cannot add content. Its
in-memory configuration requires an exact, lowercase hostname allowlist, a
canonical public IP pin, and a bounded HTTPS URL without userinfo, port, query
or fragment. Endpoint values and the IP pin are excluded from configuration
representations, results and error messages.
The allowlist must come from an operator-owned source; URL shape cannot prove
that provenance. No endpoint, credential or configuration file is committed.

Delivery is disabled and dry-run by default. Dry-run validates content and
configuration without DNS lookup or network activity. A caller must explicitly
set `enabled=True` and `dry_run=False` to attempt one POST. The built-in
transport connects directly to the configured public IP without DNS, verifies
the allowlisted hostname with TLS, ignores proxies, does not follow redirects,
reads no response body and does not retry. Only HTTP 2xx yields
`HTTP_ACCEPTED`; that means an HTTP endpoint accepted a request, **not** that
any human received a notification. Socket operations have a 1–10 second idle
timeout; this is **not an end-to-end wall-clock deadline**. Runtime integration
must provide a separate deadline and reconciliation. Transport exceptions have
an unconfirmed outcome, so callers must not assume a retry is safe. No live
transport has been run.

The adapter is not wired into a task, hook, approval path or CLI. Its opt-in
switch is not an authorization token. Rate limiting, recipient ownership,
delivery reconciliation and a controlled G4 pilot still require a separate
integration decision.

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
`tests/unit/test_status_notification_delivery.py` adds synthetic paired
configuration and transport checks; it never opens a network connection.

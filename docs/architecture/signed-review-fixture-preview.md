# Signed G2 review comparison: offline fixtures only

Status: **MANUAL_ONLY**, including when the fixture matches. This diagnostic does
not verify a live approval, grant authority, issue or consume a token, read an
operational registry or clock, change state, or run anything from a submission.

## Shared, bounded comparison

The Python entry point is
[preview_signed_review(raw_bytes)](../../orchestrator/core/signed_review_preview.py).
Run the [identical check through the CLI](../../orchestrator/signed_review_preview.py)
with python -m orchestrator.signed_review_preview and pipe in the fixture JSON.
No command-line or environment override can select a fixture trust root. See the
[synthetic fixtures](../../tests/test_signed_review_preview.py) for complete examples.
The CLI returns 0 for a match and 2 for a refusal; it reports only a fixed reason,
MANUAL_ONLY, and false values for approval, execution and consumption.

Inputs are a bounded UTF-8 JSON bundle with four fields: context, review_text,
registry and approval. Two independent HMAC domains separate the registry
authority from the reviewer and the two formats from legacy tokens. The verifier:

1. Builds the existing [canonical approval context](approval-context-preview.md)
   without changing its meaning or projecting it onto legacy token fields.
2. Checks the registry tag and the exact synthetic registry pin retained outside
   the bundle. The approval's signed registry digest, reviewer identity,
   activation epoch and key fingerprint must match an active reviewer row.
   An unknown or disabled reviewer, the requester, and an actor are refused.
3. Checks the reviewer tag over the complete approval body, including the requester,
   roster digest, validity interval, approval reference and context/review digests.
4. Compares the signed context digest to the supplied candidate snapshot fields,
   including base commit, candidate commit, full seal and assessment digests, and
   independently hashes the supplied review text's exact UTF-8 bytes. A different
   line ending changes the review digest.

## Trust and compatibility limits

Keys, pin and time are deterministic, public fixture values. This comparison proves
format and binding behavior only, not an authenticated human or a current registry.
It compares context/seal/assessment assertions rather than measuring actual artifacts.
It neither interprets the review text as a verdict nor asserts anything about the
existing policy engine. A signed token reference is not a ledger or replay defense.
Repeating a matching preview is still just a comparison, not another authorization.

The legacy manager, approve CLI, adapter, merge policy and execution paths are all
unchanged. For operational G2, choose a protected registry, clock and evidence
source, independently measure artifacts, retain and atomically check the token
binding and lifecycle, enforce hard denies, and verify the same use-time guard in
the real CLI and Python dispatch paths. Do not use the fixture keys or protocol as
an operational trust or signing format.

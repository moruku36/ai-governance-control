# Shared CLI/API approval-context preview

Status: additive **PREVIEW_NOT_AUTHORIZATION** contract. This module does not issue,
verify or consume an approval; read credentials; update a database or task state;
execute argv; contact a service; change the existing CLI or adapter; or relax any
receipt refusal. It is a preparation primitive, not complete G2.

## One bounded contract, two entry points

Python: `orchestrator.core.approval_context.build_approval_context(mapping)` or
`parse_approval_context(utf8_bytes)` returns an immutable canonical JSON record and
digest. CLI: `python -m orchestrator.approval_context < context.json` calls that same
parser/builder. No command-line values are accepted. CLI success outputs only
`status`, `version`, and `digest`; it does not echo repository names, paths, argv or
input names. Invalid input returns code 2 and a generic error without submitted
values. Success code 0 means only that preview preparation succeeded.

The version is `offline-approval-context/1`, domain-separated with
`ai-governance-control:approval-context-preview`. Only the exact documented keys
are accepted. Parsing refuses duplicate keys at any level, unknown/missing fields,
invalid types, malformed UTF-8, nonfinite numbers, and input beyond 64 KiB. API
canonical output is also capped at 64 KiB. Unicode is JSON-escaped deterministically;
key ordering/whitespace do not change the digest. Array order and argv boundaries do.

The top-level keys are:

- `version`, fixed `action: task_execution`, existing-schema `task_id`;
- `repository_id` (opaque controller ID), `repository` (existing repository reference);
- `base_sha`, `candidate_sha` (separate full lowercase SHA-1 commits);
- `candidate_seal_digest`, `assessment_digest`, `policy_hash`;
- `plan_hash`, retaining the **existing approved specification digest meaning**;
- `approved_suite_digest`, `runner_profile_digest`, `manifest_digest`;
- `target_ref` and the `runtime` object.

The runtime keys are `profile` (only `offline-linux-v1`), immutable `image`
(`sha256:` plus full digest), canonical absolute Linux `runtime_root` and
`worktree_reference`, `command_id`, **typed list** `argv` (absolute executable, every argument nonempty), integer `timeout_sec` (1–300),
`network` (only `NONE`), and `inputs` (at most 100 flat names matching `[A-Za-z0-9][A-Za-z0-9_.-]{0,99}` to content SHA-256 mapping).
No shell splitting is performed. Literal shell-looking strings remain data. Empty arguments are refused to match the existing `ContainerCommand` contract. An empty input mapping explicitly means no
input files; a missing mapping is rejected. These validations do not certify the
existence, ownership, approval or safety of any referenced path or executable.
Comma-containing runtime/worktree paths are refused to match mount-syntax limits.
Input hashes alone cannot prove the runner’s 1 MiB aggregate content bound; actual
bytes must still be independently checked by the runner.

The suite/profile/manifest fields are digest assertions, not supplied raw data.
`candidate_seal_digest` means the complete `CandidateSeal.digest`, not a bare tree
snapshot. `assessment_digest` means the retained full assessment record digest.
The preview cannot establish those relationships by itself because it does not
receive or independently measure the referenced records.

## Compatibility: no automatic projection

The existing `ApprovedContainerAdapter._context` binds action/task/repository,
`head_sha`, destination, policy and plan, then hashes offline profile/image/runtime
root, command ID/argv/timeout/network, full manifest, worktree reference and input
hashes into its legacy `argv_digest`. Its existing `head_sha` is checked against
the ledger's **base SHA**; it must not silently become the candidate SHA.

This preview names base and candidate separately and uses its own digest/domain.
It neither overwrites nor aliases the legacy `argv_digest`. `plan_hash` remains the
existing specification hash, not this new context digest. The legacy CLI's raw
command-splitting behavior is not changed by this additive module; calling the new
preview does not mean legacy CLI/API authorization has been unified. Existing
signed token fields and token verification/consumption remain untouched.

## Owner and execution decisions still required

Before any authorizing integration, an owner must choose and review:

1. The protected source of task/spec/policy/manifest, complete candidate seal,
   approved assessment and test suite, and how all those records are independently
   compared to this payload. Worker-submitted matching hashes are not authority.
2. The identity and review/qualification policy for the human issuer, plus protected
   storage, expiry/revocation checks and single-use consumption. No new credential
   or identity mechanism is supplied here.
3. A trusted runtime inspector and independent executor that measure actual image,
   command registry entry, argv, mounts/paths, network, inputs and runner profile.
   A structurally valid JSON assertion is not proof of those observations.
4. A reviewed versioned mapping/migration into existing approval and adapter gates,
   preserving base-versus-candidate semantics and the current plan/spec invariant.
   This preview is deliberately not a replacement token context.
5. Controller serialization/CAS, stale-context rejection, evidence provenance and
   restart/uncertain-outcome handling before any state transition or side effect.

Do not put secrets in argv, repository URLs or paths. The digest-only CLI output
minimizes accidental disclosure but cannot detect every secret in submitted data;
the API canonical record intentionally retains the caller's supplied context.

## Verification

Synthetic tests compare actual subprocess CLI and Python API digests, vary every
mutable binding, reject fixed-mode changes and malformed/duplicate/oversized input,
preserve typed argv boundaries, verify immutable detachment and generic errors,
and show literal argv is neither executed nor echoed. A compatibility test calls
the existing offline adapter's context builder before/after preview generation and
checks that legacy field set, base head, plan hash and argv digest remain unchanged.
No tokens, live providers or operational credentials are used.

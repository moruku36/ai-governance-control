# Committed-candidate binding (local offline G1/F1 groundwork)

Status: standalone controller-side primitive, **not runtime integration or complete
G1/G2**. Nothing here changes approval tokens, state transitions, handoff acceptance,
container mounting, credentials, settings, or live adapters. The existing
complete-diff receipt refusal remains in place.

## Why a separate committed-only boundary

The current `snapshot_worktree` copies tracked working-tree bytes; it does not
preserve a complete commit's modes/deletions. `ArtifactCollector` and
`IndependentVerifier.compute_diff` likewise have explicitly narrower contracts.
This tranche does not silently reinterpret those outputs as full candidates.

`candidate_binding.seal_committed_candidate` instead uses the existing
[`full-candidate/1` measurement](complete-candidate-contract.md) to seal an
**already committed** candidate from a trusted object store. It does not create a
commit, import an arbitrary worker worktree, modify refs, or certify dirty/untracked
files. A later controller integration must establish that the intended candidate is
exactly this commit before dispatching an independent tester.

## Seal and scope

An immutable `CandidateSeal` contains actual base, candidate, and approved-suite
`TreeSnapshot` entries, complete diff digest, literal allowed/prohibited path
prefixes, version, and a `BindingContext` binding:

- task ID;
- approved specification digest;
- effective policy digest;
- previously approved independent test-suite snapshot digest;
- runner/configuration/dependency profile digest.

The independent suite is represented by a separate commit in the same trusted
repository object store. Its measured digest must match the previously approved
context. No candidate-provided `approved` flag or newly calculated suite hash
substitutes for that prior approval. The runner profile digest must cover all
relevant execution settings under a future reviewed profile contract; this module
does not inspect a runner or invent that contract.

The allowed-prefix list must be nonempty. Only literal canonical path prefixes are
supported; no wildcard or empty-list-means-allow-all behavior is inherited. Every
changed path, including deletion and mode-only changes, is checked. Prohibited
prefixes are case-insensitive and take precedence. Existing collector protected
control-path semantics are conservatively retained, including `.git*` components;
this does not create a way to authorize protected control changes. Unchanged
tracked configuration is inventory data, not executable instructions.

## Current candidate and evidence

The trusted controller supplies a resolver for its current candidate SHA. The
resolver is called before and after sealing. For `bind_test_evidence`, the
controller also supplies its independently retained seal digest, current binding
context, and a trusted independent executor's `TestObservation`.

Acceptance checks:

1. Seal, task/specification/policy/suite/runner context, and all observation bindings
   match exactly.
2. The controller's current full candidate SHA still matches the seal; the commit
   is remeasured and its entire inventory compared.
3. The measured process exit is zero and structured JUnit passes the existing
   strict parser. Missing, malformed, failing, empty and all-skipped reports do not
   pass. No free-form success-log heuristic is used.
4. The current candidate resolver is checked again immediately before returning.

The result is an immutable `BOUND_TEST_EVIDENCE` record, **not** VERIFIED,
READY_FOR_MERGE, completed, approved, or an authentic receipt. It retains the seal,
execution and executor references, report digest, and measured test counts.

## Trust and residual gaps

This is not an untrusted worker API. A Python caller can construct dataclasses or
forge observations. Hashes bind content, not origin. The controller must protect
its object store, context, expected digest, resolver and executor observations;
opaque executor IDs do not prove independent identity. JUnit syntax validation is
not producer authentication or proof that the suite was actually run. The execution
adapter must independently establish the candidate/suite/runner digests it reports.
The existing approval manager remains unchanged and supplies no implicit approval
for this contract.

The resolver must read trusted controller state, not return a worker assertion or
a cached SHA merely to satisfy the comparison. There is no atomic lock spanning an
external state update: after return, a later candidate change is still possible.
An integrating controller must serialize or CAS the final state update against the
same seal and context; this module performs no state update and claims no durable
anti-replay ledger.

Each snapshot measurement inherits file-count, per-file/aggregate-byte, stdout and
cumulative-time bounds. Sealing performs **three** bounded measurements and test
binding performs one; this is not one shared task budget, provider-cost budget or
cumulative retry ledger. No real container isolation or external cleanup is proven.

## Tests and next gate

Synthetic local Git fixtures cover a passing bound receipt, context/observation
changes, tampered seals, invalid/failing/empty/all-skipped reports, process failure,
head movement before/during sealing and acceptance, unresolved resolver, missing or
ambiguous path scope, deny precedence, deletion/mode scope enforcement, protected
control changes, wrong approved suite, and failed remeasurement.

Next integration requires controller-owned candidate freezing, protected storage
and CAS, an authenticated independent execution path, reviewed runner provenance,
and approval/state wiring with new integration tests. The primitive alone must not
remove handoff refusal or enable any live execution path.

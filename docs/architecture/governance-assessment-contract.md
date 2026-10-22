# G1 non-authorizing assessment contract

Local implementation of a bounded **evidence record**, not completed G1/G2,
execution admission, authenticated human review or a production security claim.
Experimental / MANUAL_ONLY and complete-diff receipt refusal remain unchanged.

## Format and binding

[`governance-assessment.schema.json`](../../schemas/governance-assessment.schema.json)
uses JSON Schema draft 2020-12. Its separate product contract version is
`governance-assessment/1`; the draft is not a product version. Unknown fields are
rejected, including worker-authored `approved` or `permission_granted` flags.

The record binds task ID, operator-assigned repository ID, existing task spec
digest, candidate seal digest and policy digest. `candidate_digest` specifically
means **`CandidateSeal.digest` from `committed-candidate-binding/1`**, selected and
retained by the trusted controller. It is not `TreeSnapshot.digest`, a worker's
claim or the legacy partial collected-file digest. `runtime.snapshot_digest`
is the distinct declared mounted-snapshot reference. This module does not measure
a Git tree, resolve a seal or verify runtime configuration itself; the trusted
caller must derive the expected fields from the same verified seal context.

Assessment dimensions are:

- Existing `low/medium/high/critical` risk enum, action ID, data classification,
  external impact, reversibility, reasons, explicit unknowns and assessor reference.
- Allowed operation IDs and runtime principal/profile references, runtime
  configuration digest, snapshot digest, mount references and network/egress scope.
- Credential delivery mode and retrieval-authority reference, never a credential
  value or capability handle. `none` requires a null authority. Other modes need
  a reference; `unknown` also needs an explanation in `unknowns`.

Data classifications follow the roadmap's `public/internal/confidential/unknown`;
there is **no automatic mapping** from task output classification `restricted`.
`unknown` classification, impact, reversibility, network scope or delivery mode
requires at least one recorded unknown. An integrity-valid unknown remains
unknown; this module makes no live-eligibility decision. `none` network scope
forbids egress references; `allowlisted` requires at least one.

References are bounded opaque identifiers, not names, emails, keys, endpoints or
filesystem paths. Reasons/unknowns are bounded text intended for public or
synthetic explanations. Syntax restrictions are not a secret detector: the
trusted author remains responsible for excluding private information. Assessor
references are declarations, not authenticated identities or competence claims.

## Pure validator and trust precondition

[`assessment.py`](../../orchestrator/core/assessment.py) validates a detached JSON
representation, limits it to 64 KiB and hashes canonical sorted-key JSON. All
assessment fields participate in the digest. It returns an immutable digest plus
canonical JSON string, so later mutations to the input cannot alter the record.

`assessment_digest` supports trusted preparation only. `validate_assessment`
requires separately held expected task/repository/spec/candidate/policy bindings
**and the whole assessment digest**, reviewed and retained by the trusted
controller. Supplying expected values from the same untrusted submission proves
nothing. A hash detects differences against that independent reference; it is
not a signature, authenticated human review or proof of actual runtime settings.

There is no token issuance/consumption, credential lookup, network operation,
subprocess execution, task-state promotion or runtime policy change. A returned
record may be stored or reviewed. It cannot authorize an action, satisfy a
qualification gate, or turn COLLECTED into VERIFIED/COMPLETE. Diagnostic messages
do not echo invalid input payloads.

## Integration decision: runtime wiring deferred

The existing container adapter builds approval context from manifest, runner,
command, input hashes and worktree reference. Its independently created snapshot
is not presently part of that pre-execution context. CLI `approve` hashes a split
command string rather than the container's structured context, and `plan_hash`
is already tied to the ledger's `spec_digest`. Repurposing that field for this
assessment would break the current contract.

Before wiring admission, introduce a shared, versioned CLI/API context builder;
distinguish pre-execution assessment from post-execution candidate review; bind
actual measured snapshot/runtime configuration and assessment/review to the
existing approval mechanism; and recheck these bindings immediately before use.
Real risk-based Actor/Reviewer/Owner assignment and separation rules require an
explicit owner policy. Qualification remains separate G3 work. Do not weaken the
current receipt refusal or enable a live adapter to accommodate this record.

## Synthetic acceptance coverage

`tests/unit/test_assessment.py` covers every required dimension, stale task/spec/
candidate/policy/repository, mutation of each assessment dimension, untrusted
self-rehashing of changed context, absent/stale digest, wrong contract version,
extra authority fields, contradictory network/credential fields, explicit
unknowns, payload limits, canonical ordering and immutable outputs. These are
local contract checks, not live boundary, identity or model-injection testing.

A shared non-authorizing [CLI/API preview builder](approval-context-preview.md) is
now available as preparation groundwork. It does not unify the existing authorizing
entry points or satisfy the runtime integration conditions above.

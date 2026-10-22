# Local remediation inventory — 2026-10-22

Baseline: `4e9a8dc0a48ef35cbd84d69ca5a5dce17217ad0c` (main, PR #47).
This records local changes, not a merged release or independent approval.
Experimental / MANUAL_ONLY and complete-diff receipt refusal remain in force.

## Reconciliation and order

Read AGENTS, CONTRIBUTING, README, project state, G1–G5 roadmap, bounded-factory
F1–F5 plan, R1–R8 proposals, rules/skill YAML, CI, relevant implementations and
tests. No standalone TODO file exists in the tracked tree. GitHub REST returned
47 closed, merged PRs, no standalone Issues and no open PRs at inspection time.
Closed PRs are history, not evidence that every proposal is implemented.

| Priority / dependency | Work | Existing overlap / local status |
|---|---|---|
| First: regression foundation | R2 limits; R4 paired controls; R3 exact IDs and R5 explicit context | R2 coverage matrix added to threat model and linked from project state. Paired synthetic regressions enter existing full-suite CI. R3/R5 are partial: exact IDs, explicit branch/type checks, protected full refs and absolute hook cwd; no shell parser or universal enforcement claim. |
| Next: G1 / F1 | Complete diff: deletion, mode, rename and unknown base | #22 added collected-file comparison; #30 documented deletion limits; #29/#43 receipts deliberately reject complete-diff tasks. A standalone full committed-tree contract and negatives are now implemented locally; see [contract and trust limits](../architecture/complete-candidate-contract.md). Receipt integration, freezing and authenticity remain incomplete. |
| After full candidate: G1 / F1 | Assessment, approved requirement/oracle provenance, trusted-base instructions, TDD evidence/checkpoints | Task/risk schemas, digests and JUnit are reusable. No unified assessment or RED/GREEN provenance contract. Share one complete-diff foundation rather than duplicate engines. |
| After contract: G2 / F2 | Accountable review, common CLI/API gates, broader approval binding, criterion ownership | HMAC/registry/single-use/hard denies already implemented (#13/#14/#25); not qualification or complete duty separation. No deployed auth/permission change in this batch. |
| Within G2: R1, remaining R3/R5 | Resource deny, actual executed-input mapping, all mandatory gates and durable denial audit | Collector/path checks and container mounts overlap but do not prevent arbitrary host interpreter reads. Nested execution parsing, caller-to-command mapping and universal guard coverage remain open. Do not weaken the existing argv filter based on the narrower hook literal-data test. |
| G2 then G5: R6 | Candidate-as-data reviewer, base-owned criteria, final-head recheck | AGENTS roles/digests are reusable, not a reviewer sandbox. Native Codex/Claude adapters remain absent. Needs runtime design and later authorized integration. |
| After G2: G3 | Qualification references | No qualification admission contract. Keep separate from test quality and credentials. |
| After G1/G2: G4 / F3 | Joined reports, R7 status-only notifications, R8 red-team checklist/pilot | Journals/receipts/JUnit are foundations (#27/#30/#43). Paired regressions are a start, not a full pilot or end-to-end report. No external notification or scheduled job created. |
| After preceding gates: G4 / F4, G5 | Controlled pilot and one live adapter; optional HW/SW profile | Offline Linux adapter exists (#12/#13); no live model adapter enabled. Windows/RunPod (#31–#35) stay dormant. Real credentials, resources, cost and cleanup need a separate authorized plan. |
| Separate decision: F5 | Cloudflare / personal-agent boundary | Research only (#45). No company connectivity, OAuth setup, purchase, production deployment or DB update. |

#37 completed G0; #38/#39/#40/#42/#45/#47 added proposals; #46 reorganized docs.
Do not repeat naming, broker mocks, receipt coordinator or JUnit work as new
features. Historical “not implemented” text describes its original change; this
inventory gives the narrower local status.

## Compatibility and review scope

`evaluate_command_id` accepts exact registry keys only; pass arguments separately
in typed argv. `evaluate_git_operation` accepts `push` or `direct_commit`, explicit
short branches or `refs/heads/...`, and actual boolean force flags. Missing or
unsupported context raises `BranchProtectionError`; protected branches still
raise `HardDenyViolationError`. This does not establish remote ref existence or
normalize arbitrary Git refspec syntax.

`run_command_hook` requires a nonempty list of string argv and an existing
absolute directory string. Missing, relative, unresolved or file-valued cwd gives
ERROR with a DENIED reason before launch; HookEngine propagates denial. The
caller still owns intended repository, trusted executable and output handling.
Literal shell text passed to a trusted command remains data with `shell=False`.

No runtime ledger, policy settings, credentials, network settings, workflows or
public identifiers changed. No public push, PR, merge or deployment occurred.

## Validation

See the delivered local validation log for exact commands/outcomes. Installation
into `.venv` failed acquiring a setuptools build dependency with a TLS handshake
failure at `files.pythonhosted.org`; TLS/DNS settings were not weakened.
Unavailable checks are not passes. Linux Docker and live providers are outside
this Windows synthetic run.

Local results:

- Existing Windows pytest 9.1.1: `tests/negative/test_guardrail_pairs.py -k 'hook or tables'`
  passed **18 tests**, with **17 policy cases deselected**. Real synthetic child
  processes exercised absolute cwd and literal argv; denied contexts never launched.
- The complementary 17 policy cases were attempted and **all failed at import**
  because `jsonschema` is missing (PyYAML is also missing). They did not execute
  policy assertions. Policy runtime behavior and the full suite remain unverified;
  this batch is not ready for merge until the dependency-complete tests pass.
- Ruff 0.16.7 checked `orchestrator tests scripts`: passed. Python compileall and
  `git diff --check`: passed.
- The first hook attempt had a missing parent for the chosen pytest basetemp;
  after creating that local parent, the above 18 tests passed.
- WSL inventory returned `Wsl/E_ACCESSDENIED`; no Linux run or retry was made.

Re-run the full table, existing policy/hooks tests and the full suite in an
environment with the repository's pinned dependencies before accepting the code.

### Isolated cloud verification (same baseline, 2026-10-22)

The Windows patch was transferred without modification (26,690 bytes;
SHA-256 `aadd125ab66ebcf1ea08ed69e756b99ac85a0393cfece083281244de197f1021`)
and applied to a fresh public clone. An isolated Python 3.12 virtual environment
installed all four pinned requirements without weakening TLS or changing network
settings. This is additional Linux/Python 3.12 evidence, not a Windows or the
CI matrix's Python 3.11 run.

- Baseline: **386 passed, 10 skipped, 51 subtests passed**.
- The transferred patch: **420 passed, 1 failed, 10 skipped, 51 subtests passed**.
  The failure exposed an adapter exception-contract regression: the policy's new
  full-ref denial preceded the publisher's existing short-branch input rejection.
  No command was executed and both paths denied the protected branch.
- Repair: validate publisher branch syntax before the policy call and reject
  non-string branch input explicitly. Existing protected-branch policy denial is
  unchanged. Added three malformed-input cases, retaining the existing assertion
  that no subprocess starts.
- Repaired guardrail batch: **424 passed, 10 skipped, 51 subtests passed**;
  Ruff, secret scan, dependency audit (four pinned packages; no unmitigated CVEs
  reported by OSV at execution), and the 12 launcher mock tests passed. The
  launcher's default invocation remained disabled.

The skips are real-container acceptance (no configured immutable test image)
and platform-specific Windows checks. No Docker daemon, container image, live
provider, Windows isolation, or real credential boundary was provisioned or
claimed verified. A vulnerability scan is time-specific, not a security guarantee.

### G1 foundation and review corrections

Added the standalone `full-candidate/1` committed-tree primitive, not an admission
upgrade. It measures every regular blob from explicit trusted commits and binds
path, executable mode and content; deletions and rename-as-delete/add are included.
Unknown/noncommit bases, unsupported entries, noncanonical/colliding paths,
tampered inventories and count/byte/cumulative-time limits fail closed. The
[contract document](../architecture/complete-candidate-contract.md) states the
trusted object-store preconditions and remaining integration gates. Dirty and
untracked worktrees are deliberately not described as complete candidates.

Independent guardrail review additionally found asymmetric configured protected
branch forms. Both configured and requested short/full branch forms now normalize
consistently, with four paired regression combinations. This fixes a pre-existing
custom-policy gap without changing stored policy data or its digest. The reviewer
found no remaining blocker in the scoped hooks/policy/publisher changes and reran
77 focused tests; this is code-review evidence, not human merge authorization.

Final combined local result: **476 passed, 10 skipped, 51 subtests passed**;
48 tests cover the new G1 foundation. Ruff and `git diff --cached --check` passed.
The full explicit 14-file candidate was staged locally before the final secret
scan, so that scan included new and modified content, not only baseline HEAD.
No commit or remote write was made. The eight container tests and two Windows
junction tests remain skipped, not passed. This is not completion of G1–G5.

## Second local checkpoint: committed binding and assessment

The first verified patch remains preserved unchanged: 60,932 bytes, SHA-256
`50f1acdb02d7559dadaa9750e22261eb0cd5f815ba45c9fdf45267d194c2f49f`,
based on `4e9a8dc0a48ef35cbd84d69ca5a5dce17217ad0c`.

Added [committed-candidate binding](../architecture/candidate-binding.md): immutable
base/candidate/approved-suite inventories, task/spec/policy/runner binding, deny-first
changed-path scope checks (including deletion and mode changes), remeasurement and
current-candidate checks around structured test evidence. It seals an already
committed candidate; it does not freeze arbitrary dirty worker trees. A trusted
controller, independently observed execution and final controller CAS are still
required. No token, state or receipt behavior changes.

Added the [non-authorizing governance assessment](../architecture/governance-assessment-contract.md):
a separately versioned strict schema, canonical immutable record and comparison
against independently retained task/repository/spec/candidate-seal/policy and whole
assessment digests. Explicit unknowns remain unknown; assessor references are not
authentication or qualifications. Records carry no permissions.

Runtime wiring remains deliberately deferred: CLI and container approval contexts
currently differ, the working-tree snapshot is not part of pre-execution approval,
and `plan_hash` already means the ledger spec digest. A shared versioned context
builder, actual snapshot/runtime binding, independent executor provenance and
atomic stale-context checks need separate integration tests before changing
authorization. Real Actor/Reviewer/Owner assignment and risk-separation policy need
an explicit owner policy. No complete-diff refusal was removed.

Second-checkpoint validation: **615 passed, 10 skipped, 51 subtests passed**,
including 71 committed-binding and 68 assessment tests. Ruff and compileall
passed. Final staged secret scan includes all candidate files. The same eight
Docker and two Windows junction checks remain skipped; no live boundary was run.

## Third local checkpoint: shared CLI/API context preview

Checkpoint 2 remains preserved unchanged: 117,899 bytes, SHA-256
`2c1ae9b58fda14adb612e35781e6512675f432b7cdf3390dd82defa2babe4e2c`.

Added [one versioned approval-context preview builder](../architecture/approval-context-preview.md)
shared by a Python API and a separate `python -m orchestrator.approval_context`
stdin CLI. It binds typed argv and explicit candidate, assessment, task, policy,
specification and offline runtime references. CLI output is digest-only with
`PREVIEW_NOT_AUTHORIZATION`; it never issues or consumes tokens. Existing CLI,
approval signatures/schema/DB, adapter context and plan_hash semantics are unchanged.

Independent review found and repaired a representability mismatch before acceptance:
the offline profile now mirrors the existing runner's absolute executable, nonempty
arguments, 1–300 second timeout, flat input names/count and mount-syntax constraints.
The real input-byte budget cannot be measured from hashes and remains an executor
responsibility. Actual referenced records/runtime are not authenticated by preview
JSON. No implicit legacy-token projection exists.

Before authorizing integration, choose whether the first gate is execution preflight
or post-candidate review; designate protected issuer/executor records and risk-based
Actor/Reviewer/Owner separation. Then implement a reviewed versioned token/context
migration with no legacy downgrade, measured runtime/snapshot provenance and atomic
stale-context checks. These are not decisions a preview may infer or grant itself.

Third-checkpoint validation: **698 passed, 10 skipped, 51 subtests passed**,
including 83 preview tests. Independent read-only review approved the scoped
non-authorizing design after the compatibility repair and reran all 83 tests.
Ruff and compileall passed; final staged secret scan and diff checks passed.
Docker/Windows omissions remain unchanged; review is not human merge approval.

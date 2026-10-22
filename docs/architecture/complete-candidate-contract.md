# Full-candidate inventory foundation (local G1 tranche)

Status: implemented as a standalone, offline contract primitive. **Not complete G1,
not an approval, not an independent test verdict, and not handoff admission.**
`complete_diff_required` receipts continue to fail closed. Experimental /
MANUAL_ONLY is unchanged. No adapter, credential, workflow or policy is enabled.

## What the primitive measures

`orchestrator.core.candidate.measure_git_commit` reads an **explicit, full lowercase
SHA-1 commit** from an **operator-controlled Git object store**. The operator supplies
an opaque repository ID and an absolute Git directory; the caller's cwd, HEAD,
working tree and index are not discovery inputs. Missing commits and tree/tag/blob
IDs are rejected. SHA-256 Git object-format repositories are not supported in v1.

Each `full-candidate/1` snapshot binds:

- repository ID and full commit SHA;
- every tracked regular blob path, executable/non-executable Git mode, and measured
  SHA-256 of its raw content;
- the contract version and canonical sorted inventory, via canonical JSON SHA-256.

There is no path filtering. An unsupported entry rejects the entire snapshot,
rather than silently omitting it. Empty commit trees are valid complete inventories.
Symlinks, submodules, non-UTF-8 names, control-character/traversal paths, `.git`
components, duplicate/case-colliding names, file/directory collisions and
noncanonical path spelling are refused. This is deliberately narrower than every
path Git can store and is not a guarantee of portability to every filesystem.
Tracked instructions/configuration are measured as data, never loaded as agent
instructions. This measurement API is not an artifact extraction API and does not
permit writing those paths.

`compare_snapshots` requires separately held expected digests for both snapshots
and matching repository IDs. It binds both full snapshots and all before/after
entries in its own digest. Thus deletions, additions, content edits and executable
mode changes cannot vanish from the comparison. Renames are deterministic
**delete + add**, not heuristic similarity matches. Mode and content changes on
the same path remain one changed path containing both states.

## Trust and limits

- The Git executable, object store, local Git configuration and repository-ID
  assignment must be controlled by the trusted controller, not by a worker. This
  module does **not** sandbox an arbitrary candidate repository, authenticate a
  caller or prove who supplied a commit. Git runs only fixed read-object commands
  with `shell=False`; inherited `GIT_*` settings, global/system configuration,
  replacement objects, lazy fetching and terminal prompts are disabled. Trusted
  local configuration and object-store integrity remain preconditions.
- A Python caller can construct `TreeSnapshot` directly. Validation and expected
  hashes cannot prove that such a caller included every file. **Only an independently
  measured full commit inventory in a trusted control path establishes the intended
  completeness here.** A worker-provided matching digest is not evidence of trust.
- A commit snapshot excludes dirty and untracked worktree files by definition. A
  later integration must freeze the actual candidate into a controller-verified
  commit and check it is exactly the candidate independently tested/reviewed. Do not
  use this API to describe a dirty worktree as completely verified.
- File count, per-blob bytes, aggregate blob bytes, bounded Git stdout and a shared
  cumulative deadline fail closed. Git errors and stderr are reduced to generic
  diagnostics, not forwarded untrusted output. These are process/output limits,
  not an OS sandbox, a global task budget or a provider-cost ledger. The deadline
  is shared across subprocesses, not reset for each blob.
- Git SHA-1 IDs locate objects; the measured content and contract use SHA-256.
  A hash is not authenticity. There is no signature, human review, approved-policy
  binding, TDD chronology, assessor identity or qualification admission in this
  primitive.

## Verification and next integration gate

Synthetic tests construct local Git objects without commit hooks or live services.
They cover full additions/deletions/modifications/mode changes, rename-as-delete/add,
empty trees, unknown/missing/noncommit bases, unsupported entries, path/case/prefix
collisions, tampering, wrong repository/version, immutable inventories, byte/count
limits, cumulative timeout, bounded output, process timeout, inherited Git-setting
isolation, dirty worktree exclusion, and unchanged handoff refusal.

Before removing the existing complete-diff refusal, add and independently review a
controller-owned candidate-freezing workflow, trusted provenance/storage, task and
policy binding, allowed-path checks over **all** changed paths (including deletes),
protected control-path enforcement, independent execution-to-candidate binding and
stale-head rejection. The assessment, broader approval and qualification contracts,
reports/pilot and live adapter stages remain separate work.

The next local evidence-only pieces are now implemented separately:
[committed-candidate binding](candidate-binding.md) and
[governance assessment](governance-assessment-contract.md). They do not satisfy
the runtime integration gates above or authorize receipt upgrades.

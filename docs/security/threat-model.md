# Threat Model & Security Boundaries

## 1. Threat Vectors
1. **Malicious or Hallucinated Task Manifests**: Manifests attempting path traversal (`../`, absolute paths, symlink attacks) or command injection via shell metacharacters.
2. **Untrusted Agent Output**: Workers attempting to overwrite system files, exfiltrate environment secrets, or tamper with Git metadata (`.git`).
3. **Approval Forgery**: Counterfeit approval tokens or tokens reused across tasks or expired tokens.
4. **Race Conditions / Concurrent Writers**: Simultaneous writes causing split-brain state or corrupted ledgers.

## 2. Mitigation Strategy
- **Strict Parsing**: Safe YAML parsing only, JSON Schema 2020-12 validation, size limit 1 MiB, max recursion depth 20.
- **Typed Command Execution**: Disallow `shell=True`. Commands mapped to explicit, pre-approved command registries.
- **Single Writer Pattern**: Lock acquisition and revision verification prior to any state update.
- **Token Binding**: Approval tokens cryptographically bound to SHA of task spec, policy, target ref, and argv.

## 3. Control coverage and residual gaps (R2)

Checked against main `4e9a8dc0a48ef35cbd84d69ca5a5dce17217ad0c` and the local
R3/R4/R5 remediation. Keep each guard's limit alongside its backing control when
adding or reviewing a guard. Do not place high-value secrets in worker inputs;
synthetic markers are sufficient for regression tests.

| Guard / implementation | What it checks | Blind spot / actual backing boundary |
|---|---|---|
| Parsing (`schema.py`) | Schema, duplicate keys, size and depth | Valid data is not authorization or safe program behavior. Admission and runtime isolation enforce scope. |
| Command IDs (`policy.py`) | Exact registered IDs; missing IDs and raw command lines refused | An interpreter can read every visible file. IDs do not bind executable bytes or argv. ManualAdapter is trusted host execution; the offline runner uses exact trusted argv inside a container. |
| Git operations (`policy.py`) | Explicit branch, supported operation and boolean force; protected short/full branch refs denied | Does not resolve remote destinations/refspecs or intercept arbitrary Git processes. Callers supply the real operation; server-side protection is separate. |
| Paths/collection (`worktree.py`, `artifacts.py`) | Selected paths, containment and collection restrictions | Does not stop earlier reads by an interpreter, on-disk script or host process. Exclude credential files from snapshots and isolate mounts. |
| Environment (`sandbox.py`) | Allowlisted names and credential-like names | Does not inspect files or every allowed value. This is not a secret-file deny layer; the snapshot must already be sanitized. |
| Offline runner (`container.py`) | Immutable Linux image, exact commands, no network, non-root/read-only mounts and cleanup reconciliation | Linux-only, not a general escape proof or scanner of all snapshot bytes. Manual/same-user host execution is outside the boundary. Missing Docker never authorizes fallback. |
| Hooks (`hooks.py`) | Required handler, PASS result, exceptions, elapsed-time rejection; command hooks require typed argv and existing absolute cwd | Directory existence does not identify the intended repository. Trusted callers must supply it and register mandatory hooks at every entry point. Elapsed-time checks do not preempt stuck in-process handlers. Raw hook output is trusted-channel data, not notification text. |
| Approval (`approval.py`, `auth.py`) | Bound single-use HMAC approval and registered operator/action permission | Not qualification or automatic separation of duties. Protected key/registry provisioning and G1/G2 assessment/review bindings remain prerequisites. |
| State/leases (`state.py`, `lease.py`) | CAS transitions, journal and execution ownership | Not protection from direct access to the trusted controller/storage. Private runtime storage and process identity remain deployment prerequisites. |
| Evidence (`verifier.py`, `junit.py`, `handoff.py`) | Collected bytes, bounded consistent JUnit and receipts | Collected files do not bind deletions/modes/renames; unknown base and fabricated logs are not complete-diff/provenance evidence. Handoff still refuses require_complete_diff; COLLECTED is not VERIFIED/COMPLETE. |
| Full committed-tree foundation (`candidate.py`) | Versioned path/mode/content inventory measured from explicit commits, integrity binding and bounded comparison | Trusted immutable Git store and trusted expected digests are prerequisites, not authenticated here. Dirty/untracked worktrees are excluded; no approval, qualification or receipt upgrade. |
| Publication (`adapters/github.py`) | Repository/head/PR checks, reconciliation and human merge boundary | Does not establish reviewer isolation from candidate configuration. R6 and base-owned review criteria remain future work. Local passes do not authorize public writes. |
| Secret scan (`scripts/secret_scan.py`) | Known patterns in tracked content and commit/staged diffs | Not every encoding, endpoint name or private datum. Minimize output and prevent secret placement; redaction is a last net. R7 content contract is implemented as a non-sending library ([status notification contract](../architecture/status-notification-contract.md)); no sender, destination or wiring exists. |

The paired [regression table](../../tests/negative/test_guardrail_pairs.py) covers
structured policy and trusted command hooks. It does not parse nested shell
languages or demonstrate reviewer isolation. The [local inventory](../operations/remediation-status-2026-10-22.md)
retains unfinished [R1–R8 proposals](../research/ai-dev-harness-guard-bypass-2610.md).

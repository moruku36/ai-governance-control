# Self-built agent guards that were bypassed: lessons and remediation proposals

[English](ai-dev-harness-guard-bypass-2610.md) | [日本語](ai-dev-harness-guard-bypass-2610.ja.md) · [README](../../README.md) · [Governance roadmap](../architecture/governance-roadmap.md)

*Practitioner-report note. The items below are our own proposals for future remediation. They are **not implemented**, carry no dates, and are not product claims. No experiment or code run was performed on the article's code or on this project; the "existing overlap" statements come from reading this repository's source only.*

## Source and status

**Article:** 「AIに開発を任せたら、自作のセキュリティガードが素通りしていた」 (roughly: "I handed development to AI, and my home-made security guards were bypassed"), nekoai_lab, Zenn, published 2026-10-18 (JST). <https://zenn.dev/nekoai_lab/articles/013b347bc56ebb>. Read in full on 2026-10-21.

It is a single author's first-person report about a personal setup (several coding agents, ~10 repositories, a shared hook repository). It is not a benchmark, a peer-reviewed study or a certification. Its figures (for example "40/40 tests pass") are self-reported and unverified here. We summarize in our own words and do not copy its code. The adaptation to this project is ours and is not the author's recommendation.

## What the article reports (author's claims)

1. **Secret-read guard bypassed by another tool.** A hook that blocked `cat`/`grep`/`sed`-style reads of `.env` files was bypassed by a one-line interpreter call; a `permissions.deny` read rule also does not cover programs that a shell command launches. The fix was to block by the *target file name appearing anywhere in the command*, not by tool name, and to document the remaining gap: a script already on disk that opens the file never shows the file name in the command string. The author's stated conclusion is that truly sensitive values should not be on the development machine at all; the hook is only an outer net.
2. **Protected-branch guard bypassed by a newline.** A hook that tokenised commands blocked a force push on one line but not when the same command followed another command on a new line, because the tokenizer treated newline as whitespace rather than a command separator. Agents often chain commands with newlines. It was found only when a test table was written.
3. **The fix then over-blocked.** Once nested execution (`bash -c`, `eval`, remote shell, here-doc fed to a shell) was inspected, text that is merely *mentioned* (commit messages, `echo` arguments, here-doc bodies written to a file) triggered false positives. The remedy was to inspect only strings that will actually be executed, and to keep "must block" and "must pass" cases in one test table run in CI.
4. **Hooks fail silently open.** A branch-name check depended on the caller's working directory; outside the repository the name was empty and the check was skipped without any error.
5. **The reviewer agent could be steered by the PR it reviews.** An AI reviewer started inside a checkout of the PR head reads that checkout's agent configuration (hook settings, tool-server definitions, rules). A PR author can therefore add configuration that runs when the reviewer starts. The author maps this to OWASP CICD-SEC-4 (Poisoned Pipeline Execution) and LLM01 (Prompt Injection). The six layered measures: check out outside any trusted directory; delete agent-config files from the copy before launch; start the reviewer with project settings and tool servers disabled and read-only permissions; read review rules from the *base* revision; redact secret-like strings before posting results; and compare the PR head revision immediately before applying a pass label. Notifications were reduced to a one-line status because filtering is weaker than not including the data.
6. **A checklist** of self-tests (secret reads, dangerous commands, AI review), including treating a notification endpoint name as a secret.

## Existing overlap in this repository

Read against main `f1d3216` (source only):

| Article theme | Existing overlap | Gap / limit (to verify, not asserted as a vulnerability) |
|---|---|---|
| Protected-branch guard | `PolicyEngine.evaluate_git_operation` and the hard-deny set take structured arguments (target branch, operation, force flag), not a raw shell string ([policy.py](../../orchestrator/core/policy.py)). | Structured input avoids newline/nesting parsing bugs only if every caller builds those arguments from the real command; the mapping from an executed command to these arguments is not shown to be complete. |
| Command allowlist | `evaluate_command_id` allows by the first token against `DEFAULT_ALLOWED_COMMANDS`, which includes general interpreters (`python3`, `node`) and `git`. | A first-token allowlist is name-based. Interpreters can open any file visible to them, so protection then rests on the container/worktree boundary ([runtime-isolation](../operations/runtime-isolation.md)), not on this check. |
| Secrets reaching workers | `sanitize_worker_environment` strips credential-like environment variables and uses an allowlist ([sandbox.py](../../orchestrator/core/sandbox.py)). | Environment scrubbing does not cover credential *files* inside a mounted workspace. |
| Independent verification / review | Builder, Tester and Reviewer are separated in [AGENTS](../../AGENTS.md); `IndependentVerifier` collects results. | The roles are declarations plus phases; whether a reviewer process loads configuration from the candidate being reviewed is not covered by the documents we read. |
| Hooks | `HookEngine` and `run_command_hook` take an explicit `cwd` ([hooks.py](../../orchestrator/core/hooks.py)). | Fail-open versus fail-closed behaviour on missing context is not specified in the documents we read. |
| Negative tests | [test_guardrail_negatives.py](../../tests/negative/test_guardrail_negatives.py) exists. | Not shown to pair every "must block" case with a "must pass" case. |

## Remediation proposals (not implemented)

Each item names the roadmap stage it extends ([governance roadmap](../architecture/governance-roadmap.md)) and a done-when condition. All keep existing security boundaries unchanged and add to, rather than replace, current work.

| ID | Proposal | Stage | Done when |
|---|---|---|---|
| R1 | **Deny by target resource, not by tool name.** Add a path/resource deny layer (secret-bearing files and directories) evaluated independently of which executable is invoked, alongside the command allowlist. | G2 | Tests show that interpreter one-liners, copy, encoding and redirection of a protected path are rejected on the same rule that rejects the obvious reader. |
| R2 | **Write down residual gaps next to each control.** For every guard record what it cannot see (for example a pre-existing on-disk script opening a file) and what actually backs it (container boundary, not mounting the secret). Prefer not placing high-value secrets in the workspace. | G1 | Threat model and PROJECT_STATE list each guard with its known blind spots; a guard without a recorded limit fails documentation review. |
| R3 | **Prefer structured argv over raw command strings; where a string must be parsed, treat newline as a separator and inspect only strings that are actually executed.** Cover chained commands, `bash -c`, `eval`, remote shell and here-doc-to-shell; exclude commit messages, echoed text and here-docs written to files. | G2 | A fixed test table of chained, nested and merely-mentioned forms passes in both directions. |
| R4 | **Pair "must block" and "must pass" cases in one CI table** so a fix cannot trade a hole for a false positive unnoticed. | G1 / G4 | Adding a block rule without a matching pass case, or the reverse, fails CI. |
| R5 | **Fail closed on missing context.** Guards must not depend on the caller's working directory or an inferred branch name; an empty or unresolved value must deny (or require approval), never pass silently. Emit an auditable record when a guard cannot decide. | G2 | Tests invoke each guard from outside the repository and with unresolved inputs and observe a denial plus a recorded reason. |
| R6 | **Treat the candidate as data, not configuration, for the reviewer.** Review a copy located outside trusted directories; remove agent configuration (hooks, tool-server definitions, rules, instruction files) from it before launch; start the reviewer with project-level settings and tool servers disabled and read-only permissions; read review criteria from the base revision; re-compare the candidate head revision immediately before recording a pass; redact secret-like strings from review output. Extends the digest-binding idea in G2 and the [GitInject survey](gitinject-2606.09935.md). | G2 / G5 | A candidate that adds reviewer-config files or edits its own review criteria has no effect on the review; a head revision change between review and pass blocks the pass. |
| R7 | **Minimise what notifications and review comments carry, and treat notification endpoints as secrets.** Status-only messages; no free-form review text outside the trusted channel. Redaction is a last net, not the primary control. | G4 | A test confirms notifications contain only the allowed fields. |
| R8 | **Periodically attack our own guards.** Keep a red-team checklist (secret reads via alternative tools, chained and nested commands, wrong-directory invocation, poisoned review input) and run it in the G4 pilot; optionally add a read-only source audit. | G4 | The checklist is run, results (including misses) are recorded, and each miss becomes a R3/R4-style regression case. |

## Limits of this note

One article, one author, self-reported results; we reproduced nothing. The "existing overlap" column reflects source reading only and flags places to verify rather than confirmed weaknesses. Hook and tool names in the article are specific to that author's setup and do not transfer one-to-one. Legal, compliance and certification claims are out of scope.

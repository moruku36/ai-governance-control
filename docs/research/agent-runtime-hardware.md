# Agent runtime and HW/SW verification

2026-10-13 · Research proposal · [English](agent-runtime-hardware.md) / [日本語](agent-runtime-hardware.ja.md)

This supplements the [G1–G5 governance roadmap](../architecture/governance-roadmap.md); it does not enable autonomous coding, merging or deployment.

### Research inputs

- [OpenClaw and Ollama in Agentic AI: Toward Fully Autonomous and Scalable AI Agent Systems](https://arxiv.org/abs/2607.28629v1) (Roumeliotis / Sapkota): layered agent architecture is relevant to the boundary between worker inference and this project's control plane. [Accessible manuscript](https://www.researchgate.net/publication/411138539_OpenClaw_and_Ollama_in_Agentic_AI_Toward_Fully_Autonomous_and_Scalable_AI_Agent_Systems) and [current author code](https://github.com/Applied-AI-Research-Lab/OpenClaw-and-Ollama-in-Agentic-AI) are different evaluation snapshots; do not combine their reported results.
- [Accelerating Post-Quantum Cryptography via LLM-Driven Hardware-Software Co-Design](https://arxiv.org/html/2602.09410v1) (Liao / Adegbija / Lysecky), Sections III–IV: profiling and generated Verilog provide a candidate domain for external-tool verification. Constant-time and side-channel properties were not formally established.

These are **project proposals**, not features demonstrated in this repository. A JSON checkpoint is our adaptation, not a confirmed named Memory Anchor technique from the OpenClaw manuscript.

| Existing stage | Proposed extension | Acceptance criterion |
|---|---|---|
| G1 — contracts | Define worker proposal, trusted task checkpoint and evidence as separate versioned artifacts. Bind each to task, approved requirement, full candidate, runtime/tool profile and budgets. Reuse the complete-diff foundation. | Wrong task, stale candidate, altered policy, corrupt state or missing provenance blocks admission. A checkpoint never grants permissions or promotes COLLECTED to VERIFIED. |
| G2 — approval | Keep action authorization and acceptance-oracle ownership outside the generating model; bind proposed memory/checkpoint changes to the existing review and approval contract. | Injected notes or tool output cannot expand scope, overwrite accepted tests or approve a candidate. Any changed approved criterion invalidates affected evidence and approvals. |
| G4 — pilot | Compare a bounded local worker with and without persistence under the same model, input, tools and independent oracle. Include restart, stale-state, scope-violation and poisoned-memory scenarios. | Record all trials, independently checked effects, failures, cost, latency and restoration. A favorable prototype score does not imply production reliability or general injection resistance. |
| G4 — optional HW/SW exercise | Add a separately scoped HDL verification profile for one small public arithmetic kernel. Compare generated Verilog, reference C and an explicitly configured HLS baseline. | Trusted reference vectors and corner cases are independently supplied; syntax/lint, simulation, reference equivalence and synthesis/timing evidence remain separate. Generator-authored tests are supplemental, not the sole oracle. |
| G4 — security evidence | Track functional correctness, timing closure, constant-time analysis and side-channel evaluation as distinct claims. Preserve unsupported checks as unknown. | Simulation or fixed pipeline latency cannot satisfy an unperformed cryptographic security check. Reports state tool versions, target, constraints and limitations. |
| G5 — adapter | Consider one allowlisted profiler/simulator/synthesis adapter only after preceding gates. Include image/license availability, runtime limits, output bounds, fixed argv and cleanup. | Missing tools or licenses block required evidence; retries preserve cumulative budgets. No arbitrary shell, cloud provisioning, credential exposure or automatic production accelerator deployment. |

**First milestone:** a manual offline reference-versus-candidate exercise with independent expected results and recorded failure cases. FPGA acquisition, live integration and production cryptographic use require separate plans. Native Sidekick/OpenClaw adapters remain unimplemented.

# ドキュメント索引 / Documentation index

[日本語 README](../README.ja.md) · [English README](../README.md)

**Experimental / MANUAL_ONLY。** 初めての利用は「はじめに」、利用可否は「現在の状態」、設計判断は「設計」から確認してください。計画・研究は実装済み機能を意味しません。

Start with **Getting started**, check **Current state** for capability limits, and use **Design** for architecture and decisions. Plans and research do not enable features. Nothing in this organization change alters execution, approval, CI, or merge policy.

## はじめに / Start here

| 目的 / Purpose | 文書 / Documents |
|---|---|
| 導入・最初のタスク / Setup and first task | [Getting started](getting-started.md) |
| 現在の機能・未実装・制約 / Capabilities and limits | [Current project state](operations/PROJECT_STATE.md) |
| 用語 / Terminology | [Glossary](glossary.md) |
| 対応環境 / Supported environments | [Compatibility matrix](compatibility/matrix.md) |
| 貢献・セキュリティ方針 / Contributing and security | [Contributing](../CONTRIBUTING.md) · [Security policy](../SECURITY.md) · [Agent roles](../AGENTS.md) |

## 設計と判断 / Design and decisions

| 内容 / Topic | 文書 / Documents |
|---|---|
| 正本の仕様と概要 / Specification and overview | [Architecture specification](architecture/ARCHITECTURE.md) · [Overview](architecture/overview.md) |
| 設計の出典 / Design influences | [Design influences](architecture/design-influences.md) |
| ADR / Architecture decisions | [Core stack and isolation](adr/0001-core-tech-stack-and-isolation.md) · [Worker boundary](adr/0002-worker-execution-boundary.md) · [Control plane and approval](adr/0003-control-plane-trust-and-approval.md) · [Name and governance roadmap](adr/0004-product-name-and-governance-roadmap.md) |
| 構成図 / Diagrams and sources | [English SVG](diagrams/architecture.en.svg) / [Mermaid](diagrams/architecture.en.mmd) · [日本語 SVG](diagrams/architecture.ja.svg) / [Mermaid](diagrams/architecture.ja.mmd) |

仕様の図は将来像を含みます。現在の状態と文書の優先順位は [PROJECT_STATE](operations/PROJECT_STATE.md) を参照してください。The architecture diagrams include planned components; use the current-state document for status and precedence.

## 運用と adapter / Operations and adapters

| 内容 / Topic | 文書 / Documents |
|---|---|
| 運用・復旧・CLI / Operations, recovery, and CLI | [Operations guide](operations/OPERATIONS.md) · [Runtime isolation](operations/runtime-isolation.md) |
| コンテナ境界と承認 / Container boundary and approval | [Offline container boundary](operations/OFFLINE_CONTAINER_BOUNDARY.md) · [Approved container loop](operations/APPROVED_CONTAINER_LOOP.md) |
| 成果物の引渡し / Artifact handoff | [日本語](operations/HANDOFF_V01.ja.md) · [English](operations/HANDOFF_V01.md) |
| Repository URL の移行 / Repository URL migration | [Migration plan](operations/repository-url-migration.md) |
| Adapter の入口 / Adapter entry point | [Adapter index](adapters/README.md) |
| Agent 別の利用手順 / Agent workflows | [Codex](adapters/codex.md) · [Claude Code](adapters/claude-code.md) · [Manual](adapters/manual.md) · [Custom adapter](adapters/custom-adapter.md) · [Antigravity limitations](adapters/antigravity.md) |

## セキュリティと検証記録 / Security and validation records

| 内容 / Topic | 文書 / Documents |
|---|---|
| 方針と脅威モデル / Policy and threat model | [Security policy](../SECURITY.md) · [Threat model](security/threat-model.md) |
| Credential broker 設計 / Broker design | [Local credential broker](security/local-credential-broker.md) · [Owner handoff / 日本語](security/local-credential-owner-handoff.ja.md) |
| 起動・登録段階の設計 / Startup and enrollment design | [Startup credential / 日本語](security/runpod-startup-credential.ja.md) · [Local enrollment stage / 日本語](security/runpod-local-enrollment-stage.ja.md) · [Launcher mapping draft / 日本語](security/launcher-broker-mapping-draft.ja.md) |
| 防御検証の過去記録 / Historical defensive validation | [日本語](security/defensive-evidence.ja.md) · [English](security/defensive-evidence.md) · [Recorded verification](security/evidence/defensive-local-verification.json) · [JUnit baseline](security/evidence/junit-baseline.json) |

検証記録は記録時点の合成・ローカル検証であり、今回の整理のテスト結果や実サービスの保証ではありません。These are historical synthetic/local records, not fresh test results or live-service guarantees.

## 改修計画と研究 / Plans and research

| 内容 / Topic | 文書 / Documents |
|---|---|
| G1–G5 ガバナンス計画 / Governance roadmap | [日本語](architecture/governance-roadmap.ja.md) · [English](architecture/governance-roadmap.md) |
| 要件から merge 判断資料まで / Bounded factory plan | [計画 / 日本語](architecture/bounded-factory-plan.ja.md) |
| Cloudflare と個人 agent の境界 / Cloudflare and personal agents | [研究メモ / 日本語](research/cloudflare-personal-agent-boundaries.ja.md) |
| TDD の研究 / TDD survey | [日本語](research/tdd-governance-2604.26615.ja.md) · [English](research/tdd-governance-2604.26615.md) |
| AI CI/CD の prompt injection / GitInject survey | [日本語](research/gitinject-2606.09935.ja.md) · [English](research/gitinject-2606.09935.md) |
| 自作ガード突破の教訓 / Guard-bypass lessons (practitioner report) | [日本語](research/ai-dev-harness-guard-bypass-2610.ja.md) · [English](research/ai-dev-harness-guard-bypass-2610.md) |

## 事例と例 / Case study and examples

- [Web security control lab](case-studies/web-security-control-lab.md)
- [Handoff v0.1 example packet](examples/handoff-v01/manifest.json) · [Example trust record](examples/handoff-v01/trusted.example.json)
- [Local broker examples](examples/local-credential-broker/) · [Task templates](../tasks/templates/)

## 文書の配置 / Document layout

ルートには README 日英、LICENSE、AGENTS、CONTRIBUTING、SECURITY、package 設定などの入口・標準ファイルを残します。`.agents/`、`.claude/`、`.github/` と実行・設定・テスト・状態のフォルダは、自動参照や既存の実行構造を保つため移しません。`getting-started.md` は CLI の案内先なので現位置を維持します。

Root entry points and standard files stay in place. Agent/GitHub metadata and runtime, configuration, test, and state directories retain their paths. The CLI still points to `docs/getting-started.md`. The specification and overview remain separate documents with distinct roles.

### 移動一覧 / Moved files

| 以前の場所 / Previous path | 現在の場所 / Current path |
|---|---|
| `ARCHITECTURE.md` | [docs/architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) |
| `OPERATIONS.md` | [docs/operations/OPERATIONS.md](operations/OPERATIONS.md) |
| `PROJECT_STATE.md` | [docs/operations/PROJECT_STATE.md](operations/PROJECT_STATE.md) |
| `docs/defensive-evidence.md` | [docs/security/defensive-evidence.md](security/defensive-evidence.md) |
| `docs/defensive-evidence.ja.md` | [docs/security/defensive-evidence.ja.md](security/defensive-evidence.ja.md) |
| `evidence/defensive-local-verification.json` | [docs/security/evidence/defensive-local-verification.json](security/evidence/defensive-local-verification.json) |
| `evidence/junit-baseline.json` | [docs/security/evidence/junit-baseline.json](security/evidence/junit-baseline.json) |

以前のパスを使う外部リンクは更新が必要です。過去 commit を固定した参照は履歴として維持します。旧名の stub はルートに追加せず、この一覧を移動先の案内に使います。External links using old paths need updating; commit-pinned historical references remain unchanged.

Local implementation follow-up (not merged): [2026-10-22 remediation inventory](operations/remediation-status-2026-10-22.md).

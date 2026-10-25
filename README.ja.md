# AI Governance Control

[English](README.md) | [日本語](README.ja.md)

**Experimental / MANUAL_ONLY** ・ Python 3.11 以上

[ドキュメント索引 / Documentation index](docs/README.md) ・ [はじめに](docs/getting-started.md) ・ [現在の状態](docs/operations/PROJECT_STATE.md)

> **一文で言うと：** AIコーディングエージェント（または人間）にコードを編集させるための管理基盤です。検証されていない変更が、人間の承認なしに main へ入ることはありません。

## どのようなプロジェクトか

AIエージェントにコードを書かせるとき、速さは問題になりません。問題は「その変更を信用できるか」です。できあがったように見える変更でも、内容が間違っていたり、頼んだ範囲を超えていたり、後から追跡できなかったりします。

このプロジェクトは、エージェントとリポジトリの間に入る関門です。すべての変更はまずタスクとして登録され、独立した検証器にチェックされ、証拠と一緒にプルリクエストになります。人間がその証拠を見て承認し、マージできるのは人間だけです。

このプロジェクト自体はコードを書きません。自動マージも自動デプロイもしません。作業をする側ではなく、作業を管理する側です。

## なぜ必要なのか

- エージェントは、人間がレビューできる速度を超えて変更を作ります
- 「できたように見える」ことと「検証された」ことは別です
- すべてを自動化すると、悪い変更を本流に入る前に止める場所がなくなります

このプロジェクトは、その「止める場所」を残し、厳格にします。影響の大きい変更には単回使用の署名付き承認を必須とし、必要な検査や制御が使えない場合は、弱い方式に黙って切り替えずに停止します（フェイルクローズ）。

## どのように動くか

1. **タスクを登録する** — 何を変えてよいか、どのポリシーに従うかを決める
2. **編集する** — 人間または外部エージェントが、手作業で、または通信を遮断したLinuxコンテナの中で編集する
3. **回収して検証する** — 成果物を回収し、独立した検証器がチェックする
4. **証拠つきでPRにする** — 変更内容と検証結果をレビューに出す
5. **人間が承認する** — 人間が確認し、単回使用の署名で承認する。main へマージできるのは人間だけ

![構成図：人間または外部エージェントがCLIからタスクを投入し、制御プレーン（ポリシー、スケジューラ、SQLite台帳、署名付き承認）が手動またはオフラインコンテナのadapterを実行。成果物は回収・独立検証され、証拠つきPRが人間のレビューを経て、人間だけが main にマージする](docs/diagrams/architecture.ja.svg)

<sub>[Pele](https://pele.run/) で [Mermaidソース](docs/diagrams/architecture.ja.mmd) から描画。正本の仕様は [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) です。</sub>

## やらないこと

- コードを自律的に書くこと
- 自動マージ・自動デプロイ
- Claude Code / Codex のネイティブadapterの提供（現在の製品では Antigravity はブロックされています）

## 構造

- `orchestrator/`: 状態、ポリシー、実行、承認、GitHub確認
- `schemas/`, `tasks/`, `config/`, `tests/`, `scripts/`, `.github/`: 契約、テンプレート、CI
- `docs/`: 詳細。DB・ログ・認証情報はリポジトリの外に置きます

## 現在の状態

**実装済み**

- タスクのスキーマとスケジューリング
- 通信を遮断したLinuxコンテナでの実行、成果物の回収、独立した検証器
- 単回使用の署名付き人間承認と、その記録（ジャーナル）
- ブランチとPRのAPI
- なお、記録されるのは `COLLECTED`（回収済み）までで、`VERIFIED`（検証済み）や `COMPLETE`（完了）とは記録しません
- Windows資格情報とRunPod起動のコードはありますが、初期状態では無効で、使うには別途、人間の承認が必要です

**未提供**

- 自動マージ・自動デプロイ
- Claude Code / Codex のネイティブadapter（現在の製品では Antigravity はブロックされています）

**制限・未検証**

- 完全な差分（complete-diff）の扱いには制限があり、引き渡しの対象としては受け付けません
- 隔離の仕組みはLinuxのみです
- CIの対象は通常のUbuntuとWindowsで、macOSとWSL2は未検証です
- 模擬テストは、実キー、GPU、Windows Hello、Mattermost が動くことの証明にはなりません
- プロセスを止めただけでは、Podの削除や課金の停止までは確認できません

### 安全の考え方

影響の大きい変更には人間の承認が必要です。必要な検査や制御が使えない場合は、黙って弱い方式に切り替えず、停止します（フェイルクローズ）。秘密情報はチャットやログに出しません。

### プロジェクトの経緯

表示名を変更しました（旧称 AI Engineering Factory）。リポジトリ名は `moruku36/ai-governance-control` に移行しました。パッケージとCLIは変更ありません。[URL移行計画](docs/operations/repository-url-migration.md)を参照してください。

## 最短の開始手順

Python 3.11 以上の仮想環境を用意し、クイックスタートに従って有効化してください。

```bash
git clone https://github.com/moruku36/ai-governance-control.git
cd ai-governance-control
pip install -e ".[dev]"
python -m orchestrator.cli doctor
python -m orchestrator.cli demo --task-file tasks/templates/basic-task.yaml --worktree .
```

検査が通れば、doctorの終了コード2は想定どおりです（MANUAL_ONLY）。demoは信頼できる既存の編集を確認するだけで、AI起動、隔離、パス制限の強制、独立した証拠はありません。

## ドキュメント

[プロジェクト状態](docs/operations/PROJECT_STATE.md) ・ [アーキテクチャ](docs/architecture/ARCHITECTURE.md) ・ [運用](docs/operations/OPERATIONS.md) ・ [セキュリティ](SECURITY.md) ・ [クイックスタート](docs/getting-started.md) ・ [Adapter](docs/adapters/README.md) ・ [互換性](docs/compatibility/matrix.md) ・ [引き渡し](docs/operations/HANDOFF_V01.ja.md) ・ [起動時の認証情報](docs/security/runpod-startup-credential.ja.md)

今後の計画（未実装）: [ガバナンス・ロードマップ](docs/architecture/governance-roadmap.ja.md) ・ [TDD研究サーベイ](docs/research/tdd-governance-2604.26615.ja.md) ・ [AI CI/CDプロンプトインジェクション調査](docs/research/gitinject-2606.09935.ja.md)

追加の計画・研究（未実装）: [要件から merge 判断資料までの自動化計画](docs/architecture/bounded-factory-plan.ja.md) ・ [Cloudflare と個人 coding agent の情報境界](docs/research/cloudflare-personal-agent-boundaries.ja.md)。既存 G1–G5 を具体化し、例外承認・hard deny を維持します。会社接続や配備は行いません。

[MIT License](LICENSE)

---

<details>
<summary><strong>Future Research — エージェント実行層とHW/SW独立検証（2026-10-13）</strong> — 改善提案。未実装・未再現です</summary>

[既存のG1〜G5ロードマップ](docs/architecture/governance-roadmap.ja.md)に追加する調査候補で、自律実装・自動マージ・自動デプロイを有効化するものではありません。

### 参照研究

- [OpenClaw and Ollama in Agentic AI: Toward Fully Autonomous and Scalable AI Agent Systems](https://arxiv.org/abs/2607.28629v1)（Roumeliotis / Sapkota）：Workerの推論と制御基盤の責任分離に活用。[取得できた本文](https://www.researchgate.net/publication/411138539_OpenClaw_and_Ollama_in_Agentic_AI_Toward_Fully_Autonomous_and_Scalable_AI_Agent_Systems)と[現在の著者コード](https://github.com/Applied-AI-Research-Lab/OpenClaw-and-Ollama-in-Agentic-AI)は評価時点が異なるため、結果を混ぜません。
- [Accelerating Post-Quantum Cryptography via LLM-Driven Hardware-Software Co-Design](https://arxiv.org/html/2602.09410v1)（Liao / Adegbija / Lysecky）、III〜IV節：プロファイル解析とVerilog生成を、外部ツールによる検証の応用先として参照。定時間性・サイドチャネル耐性は形式的に検証されていません。

以下は**本プロジェクト独自の計画案**です。JSONチェックポイントは応用案で、OpenClaw論文の確認済み「Memory Anchor」手法ではありません。

| 既存段階 | 改善候補 | 完了条件 |
|---|---|---|
| G1：契約 | Workerの提案、信頼されたチェックポイント、検証証拠を別の版付き成果物にする。タスク・承認済み要件・完全候補・実行/ツール設定・予算に結びつける | 別タスク、古い候補、変更されたポリシー、破損状態、出典欠落を拒否。チェックポイントは権限を付与せず、COLLECTEDをVERIFIEDに昇格させない。既存の完全差分基盤を再利用する |
| G2：承認 | 操作認可と受け入れ判定の管理を生成モデルの外に置く。メモリ/状態の変更を既存レビュー・承認契約に組み込む | 注入されたメモやツール結果から範囲拡大・受け入れテスト改変・自己承認ができない。承認済み基準の変更で関連証拠・承認が失効する |
| G4：小規模検証 | モデル・入力・ツール・独立判定を揃えて、永続化あり/なしを比較。再起動、古い状態、範囲逸脱、メモリ汚染を含める | 全試行・実際の効果・失敗・コスト・遅延・復旧を記録。試作の成功を本番の信頼性や一般的な注入耐性の証明にしない |
| G4：任意のHW/SW演習 | 小さな公開算術カーネル1件に限定したHDL検証プロファイル。生成Verilog、参照C、設定を明示したHLS基準を比較する | 独立に用意した信頼できる正解ベクトル・境界条件を使い、構文/lint、シミュレーション、参照一致、合成/タイミングを別々に記録。生成者のテストだけでは合格にしない |
| G4：安全性の証拠 | 機能一致、タイミング収束、定時間性解析、サイドチャネル評価を別の主張として管理する | シミュレーション成功や固定パイプライン遅延で、未実施の暗号安全性検査を合格にしない。ツール版・対象・制約・限界を記録する |
| G5：adapter | 前段の条件を満たした後、profiler/simulator/synthesisの登録済み操作1件を検討。イメージ・ライセンス・時間・出力量・固定argv・後処理を制限する | 必要なツール/ライセンス欠落時は証拠取得を停止。再試行で累積予算を維持し、任意shell・クラウド作成・秘密情報露出・本番アクセラレータ自動配置を許さない |

**最初の調査目標：** オフラインで参照実装と候補を手動比較し、独立した期待値と失敗ケースを記録します。FPGA購入、実環境接続、本番暗号への採用は別途検討。Sidekick/OpenClawのネイティブadapterは未実装のままです。

</details>

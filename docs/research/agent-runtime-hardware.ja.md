# エージェント実行層とHW/SW独立検証

2026-10-13 · 研究提案 · [English](agent-runtime-hardware.md) / [日本語](agent-runtime-hardware.ja.md)

[既存のG1〜G5ロードマップ](../architecture/governance-roadmap.ja.md)に追加する調査候補で、自律実装・自動マージ・自動デプロイを有効化するものではありません。

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

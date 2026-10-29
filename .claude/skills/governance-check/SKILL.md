---
name: governance-check
description: タスクの成果物がガバナンス規則(許可範囲・承認・証拠)を満たすかを読み取り専用で点検する。
when_to_use: TRIGGER when: 「ガバナンス確認」「承認前の点検」「allowed_paths を確認」など、成果物や PR の統制状況を確認したいとき。 SKIP: 承認の記録、コマンド実行、ファイル変更が必要なとき。
allowed-tools: Read, Grep, Glob, AskUserQuestion
---

# governance-check

読み取り専用の点検手順。ファイルは変更しない。

1. 対象の task / PR を確認する(`tasks/`、`docs/operations/PROJECT_STATE.md`)。
2. `references/checklist.md` の項目を順に確認する。
3. 各所見に `ファイルパス:行番号` の根拠を付け、PASS / FAIL / 判断不能(UNEXECUTED を含む)で報告する。
4. 承認の記録や merge は行わない。必要なら人に案内する(`approval-signoff` は人専用)。

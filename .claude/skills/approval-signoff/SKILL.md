---
name: approval-signoff
description: 人間が最終承認(Sign-off)を記録するための手順を案内する。人専用で、AI は自動実行しない。
when_to_use: TRIGGER when: ユーザーが明示的に /approval-signoff を実行したとき。 SKIP: AI の判断での呼び出し全般。承認の代行、承認トークンの自動発行、merge。
disable-model-invocation: true
---

# approval-signoff (MANUAL_ONLY)

この Skill は手順の案内だけを行う。承認トークンの発行・merge は人が自分で実行する。

1. 承認対象の task と、点検結果(`governance-check`)を人に提示する。
2. 人が内容を確認したことを、人自身の入力で確認する(AskUserQuestion を使わず、ここでは進めない)。
3. 承認コマンドの使い方は `python -m orchestrator.cli approve --help` で人に確認させる。AI はコマンドを実行しない。
4. merge は人が行う。AI は merge も承認もしない。

---
name: project-conventions
description: このリポジトリの用語と役割(Builder / Tester / Reviewer)の背景知識。ユーザーが直接呼ぶ必要はない。
when_to_use: TRIGGER when: Builder / Tester / Reviewer の権限境界や task profile の扱いを確認するとき。 SKIP: 実装・承認・実行の手順そのもの。
user-invocable: false
---

# project-conventions

役割と制約の正本は `AGENTS.md`。ここには要点を複製しない。

- Builder / Tester / Reviewer の権限は署名つき task profile で決まる。
- Agent は task の状態や権限を直接変えない。状態更新は Control Plane が仲介する。
- 詳細は `AGENTS.md` と `docs/architecture/ARCHITECTURE.md` を読む。

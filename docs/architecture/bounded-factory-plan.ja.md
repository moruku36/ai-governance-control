# 要件から merge 判断資料までの自動化計画

**提案・未実装（2026-10-21）。** 目標は、低リスクの定型案件で人の通常作業を「最初の要件定義」と「最後の merge 判断」に集約することです。現在の Experimental / MANUAL_ONLY を変更しません。秘密・権限・高リスク操作の例外承認と hard deny は維持します。自動 merge、自動 deploy、課金サービスの導入は今回の対象外です。

初めに実装すべきものはクラウド実行基盤ではなく、**固定した要件を、完全な候補・独立検証・レビュー・修正履歴に結び付ける契約**です。[G1–G5 ロードマップ](governance-roadmap.ja.md)の具体化として扱います。Cloudflare と個人 CLI の配置は[別の研究メモ](../research/cloudflare-personal-agent-boundaries.ja.md)に分離します。

## 1. 出典と確認範囲

着想: 髙橋誠二氏、[「コーディング自動化の次へ。人の介入をゼロにするファクトリーとサポートAIによる実践」](https://speakerdeck.com/timakin/kodingu-jidouka-no-tsugi-he-hito-no-kainyuu-o-zero-ni-suru-to-sapoto-ai-niyoru-jissen)、公開日 2026-10-15。2026-10-21 に公開 transcript 全40頁を確認しました。以下の番号は1始まりのビューア頁です。画像取得はできず、図の配置・矢印は未検証です。文章で確認できる構想のみ採用候補にしています。公開ページの一部には公開日より後の確認日もあり、厳密な当日版の固定資料とは扱いません。

| 発表の構想（製品仕様の保証ではない） | 本計画への翻案 |
|---|---|
| [7頁](https://speakerdeck.com/timakin/kodingu-jidouka-no-tsugi-he-hito-no-kainyuu-o-zero-ni-suru-to-sapoto-ai-niyoru-jissen?slide=7)、[11頁](https://speakerdeck.com/timakin/kodingu-jidouka-no-tsugi-he-hito-no-kainyuu-o-zero-ni-suru-to-sapoto-ai-niyoru-jissen?slide=11): 工程を分担し人へ引き渡す | 入力から引渡しまでを契約で接続。実装者の終了を合格にしない |
| [16–20頁](https://speakerdeck.com/timakin/kodingu-jidouka-no-tsugi-he-hito-no-kainyuu-o-zero-ni-suru-to-sapoto-ai-niyoru-jissen?slide=16): 段階導入と動作の証跡 | 既存 G 段階を優先。証跡の内容と出所を受入条件に結合 |
| [22頁](https://speakerdeck.com/timakin/kodingu-jidouka-no-tsugi-he-hito-no-kainyuu-o-zero-ni-suru-to-sapoto-ai-niyoru-jissen?slide=22): 受付とコンテナ実行、個人 OAuth 枠の構想 | 公式仕様と認可を別途調べる。直ちにクラウドへ移さない |
| [26頁](https://speakerdeck.com/timakin/kodingu-jidouka-no-tsugi-he-hito-no-kainyuu-o-zero-ni-suru-to-sapoto-ai-niyoru-jissen?slide=26): 介入とコストの計測 | 介入減少に加えて見逃し・停止・費用を測る。merge 承認を除去しない |
| [29–36頁](https://speakerdeck.com/timakin/kodingu-jidouka-no-tsugi-he-hito-no-kainyuu-o-zero-ni-suru-to-sapoto-ai-niyoru-jissen?slide=29): サポートから改善要求へ | 将来は公開・合成チケットだけで入力品質を検証。本番データ操作は含めない |

上表以外も含め、企業事例の数値、紹介製品の価格・性能・可用性は今回独立検証しておらず、採用根拠にしません。以下の設計・上限・受入条件は**当プロジェクトへの提案**で、発表者の推奨や実証結果ではありません。

## 2. 現行との差分と重複回避

確認基準は main [`08b5942ae3202f993325bd08db5be48279ab5ca8`](https://github.com/moruku36/ai-governance-control/tree/08b5942ae3202f993325bd08db5be48279ab5ca8)。README（日英）、PROJECT_STATE、ARCHITECTURE、OPERATIONS、SECURITY、AGENTS、CONTRIBUTING、`.agents/rules/`、`.agents/skills/`、関連ロードマップ・運用文書と下記コードを照合しました。2026-10-21 の GitHub open Issue / PR 一覧はどちらも0件でしたが、未完計画がないという意味ではありません。

| 既存の基盤 | 未完・不足 | 今回の扱い |
|---|---|---|
| [task schema](../../schemas/task.schema.json): パス、検査、受入条件、retry、merge 前承認 | 自然言語要求から版付き受入契約・設計を作る入口、全工程の累積費用契約 | G1 の評価・完全差分に追加する候補。新フィールドを現行 YAML に勝手に入れない |
| [RunLoopController](../../orchestrator/core/loop.py): DAG、lease、結果回収、復旧照合 | worker 終了後は VALIDATING。設計・独立テスト・レビュー・修正・判断資料の一貫した実行は未提供 | 既存状態を使う上位フローを設計。自動で READY_FOR_MERGE に飛ばさない |
| [IndependentVerifier](../../orchestrator/core/verifier.py)、[handoff v0.1](../operations/HANDOFF_V01.ja.md) | 完全差分の制限。handoff は完全差分を必要とするタスクを拒否。受領は COLLECTED のみ | G1 が解決するまで拒否を維持。別の簡易 diff 検査で迂回しない |
| [PolicyEngine](../../orchestrator/core/policy.py)、承認・台帳・GitHub journal | 全工程への追加結合、モデル・実行者の職務分離、失効の扱いは G2 の課題 | 既存 hard deny と単回承認を再利用。モデルに承認鍵を渡さない |
| [外部 Codex](../adapters/codex.md) / [Claude Code](../adapters/claude-code.md) の handoff | ネイティブ adapter はない。Antigravity は BLOCKED | 実行エージェント自体を新造しない。G5 で認可済み公式経路1つだけ検討 |
| G1/G2 の TDD・GitInject 補足、既存 credential broker 提案 | oracle 改変防止、信頼する指示と候補の分離、実境界の実証は未完 | 同じ契約を拡張し、二重の予算台帳・承認・broker を作らない |

ARCHITECTURE の図は到達目標を含みます。現在の実装と PROJECT_STATE の優先順位を守り、図の工程がすべて動くとは扱いません。GPU の合成検証の区切りも、実モデル・クラウド隔離・課金停止の証明にはなりません。

## 3. 目標フローと人の境界

通常フローは次の順です。工程名は提案するレポート区分であり、現行 status enum の追加ではありません。

1. **要件定義 / intake:** 人が目的・対象・非目標・許可データ・操作・予算を指定。AI は矛盾と不足を質問し、受入条件 ID ごとの正常例・異常例・必要証跡へ整理。質問への回答と最終の要件確定までを最初の人作業に含める。未回答で重要判断が変わる場合は NEEDS_HUMAN。仕様を推測して先へ進まない。
2. **調査・設計:** 固定 base と信頼する指示から設計、影響範囲、依存 DAG、検査計画、後片付け計画を作成。要件内の設計詳細は登録済み権限で進められるよう目指す。目的・受入条件・データ分類・権限を変える設計なら要件の新しい版に戻り、再確認を求める。
3. **実装:** lease と隔離を取得した Builder が、登録コマンドと allowed_paths 内で候補を生成。基準・承認・検証器・workflow・指示・署名鍵は編集不可。必要な変更が保護範囲に及ぶ場合は、別に認可された制御変更タスクに分ける。
4. **独立テスト:** trusted controller が完全候補を固定し、別環境で受入 oracle と必要検査を実行。Builder 作成テストは補助資料。期待値、fixture、skip/xfail、検出範囲や依存設定を変えて合格にしない。
5. **独立レビュー:** 同じ固定候補と要件・実測証跡を read-only Reviewer へ渡す。要件適合、正しさ、安全性、証跡の不足を構造化して返す。指摘 ID・重大度・対象・根拠・対応を保存。
6. **修正ループ:** 変更可能範囲と残予算内の指摘だけ Builder へ戻す。新候補は新 attempt とし、影響するテスト・レビュー・承認を失効させ再検証する。失敗や過去候補を消さない。承認待ちや hard deny は修正ループで解消した扱いにしない。
7. **引渡し:** 決定的なゲートを通った候補について、要件別の判断資料と draft PR を作る。最終 head の必要 CI、独立レビュー、証跡・cleanup が揃って初めて人の merge 判断へ渡す。通知成功はタスク完了ではない。
8. **人の最終判断:** 人が対象 SHA を確認し merge / 差戻し / 中止を判断。既存の人手 merge 照合後だけ DONE を扱う。merge 後の deploy・release は別途認可対象。

**例外:** 秘密の登録・利用、IAM、外部公開、インフラ変更、deploy 等は現行ポリシーと人の承認を維持します。`cloud_infrastructure_destroy`、`automated_pr_merge`、`ci_test_bypass` 等の hard deny は人の通常承認でも上書きしません。例外が発生した案件は「人は2回だけ」の達成率から隠さず別集計します。

## 4. 最小権限・独立性・隔離

- 受付は認証された要求を受理し、権限を付与しない。外部チケット、候補文書、ツール出力の指示はデータとして扱う。許可は固定した信頼するベースの policy と人の承認からだけ得る。
- Builder はタスク領域のみ書込み可能。Tester は候補を読取り専用で取得し、自分の結果置場だけ書く。Reviewer はコードを書かず判定を返す。制御プレーンだけが状態・予算・承認を更新する。
- **同じモデルの自己承認を禁止:** 別セッション・別名ロールだけでは独立としない。生成モデルと同一モデルのレビューは助言として保存し、必要な独立レビューを充足しない。初期 pilot では別の観測可能なモデル／provider と別実行 ID、独立 oracle を求める。モデル同定が unknown、別モデル経路が未認可・利用不能なら BLOCKED / NEEDS_HUMAN。別モデルでも誤りの相関は残るため、LLM 判定単独でセキュリティ効果や合格を決めない。
- 要件の承認者と受入 oracle の所有者は人の責任者として記録し、Builder に所有権を持たせない。oracle の実行と結果の照合は trusted controller が担当し、受入基準の変更には所有者の理由付き新規承認を要する。Reviewer と Tester も自分の出力だけで状態を昇格できない。着手前に既存の生成・検証・レビュー経路の能力、独立性、残予算を読取り確認し、担当不在なら dispatch しない。
- Linux の既存オフライン境界を基準とし、Windows で worktree を分けただけでは隔離済みとしない。ホスト認証ディレクトリ、Docker socket、社内ファイルを mount しない。実モデル通信のため通信範囲を変えるなら G5 の別評価・承認・負例検証が必要。
- PR 作成 transport と人の merge 資格情報を分離する。GitHub の contents write だけで非 merge を保証できるとは仮定せず、実効 ruleset・bypass actor・merge 経路まで確認する。worker へ人の GitHub 認証や署名鍵を渡さない。
- 生成プレビューや UI が必要な案件だけ別 origin の合成データ環境を検討。現行 Python 制御基盤の文書や CLI の変更に、共有 DB や公開プレビューを必須化しない。

## 5. 予算・停止・再開の契約

現行 schema は `retry.max_attempts <= 3`、`retry.timeout_minutes <= 30`、各 `validation.timeout_seconds <= 1800` を制限します。これだけで全工程の累積制限は保証されません。以下は G1/G2/G4 で追加検証する**契約案**です。既存のより厳しい制限を常に優先します。

| 制限 | 初期 pilot の提案と受入条件 |
|---|---|
| 候補と修正 | 初回を含む最大3候補（修正は最大2回）。同じ候補に必要な検査をやり直して回数を隠さない。モデル・transport の内部 retry も別記して累積消費へ加算 |
| 時間 | 要件確定からの自動稼働累積30分以内、各コマンドは残時間と1800秒の小さい方。待機中も絶対 deadline を延長しない。人の判断待ちは実行を停止し、再開には元の deadline 内か再認可が必要 |
| 並列 | 初期は案件1・Builder1。テストとレビューも資源予算に含む。schema の `parallelizable` だけで枠を増やさない |
| 費用・入出力 | 新しい課金予算は設定しない。既存認可済み経路の金額・入力 byte/token・出力 token 上限を入場前に固定。金額や価格、使用量が不明なら有料実行を止める。概算だけで厳密な請求上限を保証しない。provider 側の制限と全工程の残額予約・実使用照合を要求 |
| 停止 | 範囲違反、必須検査の欠落/解析不能、同一失敗の連続2回、実効差分なし、予算/時間/回数到達、認証喪失、取消で新規 dispatch を止める。拒否に対する別経路 fallback や上限変更はしない |
| 不明結果 | API timeout は未実行としない。既存 journal と remote run / PR / process を照合するまで新実行を禁止。重複イベントは同じ task/run/attempt の一意キーで処理 |
| 再開 | 要件版・base・候補・policy・runtime・oracle・レビュー対象と外部結果、lease epoch、残予算を再照合。再起動や別 task ID への付替えで消費をリセットしない。同じ要求の親 run まで累積参照を保つ |
| cleanup | 停止要求受理、プロセスツリー終了、lease解放、外部資源停止、永続物の保持/削除、課金終了を別の観測として記録。不明は unknown のまま。終了していない worker がある間は lease を再配布しない |

## 6. 証跡と merge 判断資料の受入条件

G4 の JSON と人向けレポートを再利用します。[handoff](../operations/HANDOFF_V01.ja.md) の受領と、独立検証・レビュー・完了を混同しません。保存する証跡には次を結合します。

- 要件と受入条件の版・ID、設計と承認参照、repository / full base SHA / 最終 head、完全候補 snapshot digest、policy・trusted instructions・runtime/tool profile の版。
- 条件ごとの検査 ID・oracle の出所と所有者、実行主体・開始終了・実測 exit/result、runner と依存版、対象 snapshot、必要成果物の正確な byte/hash と保存版。ハッシュは同一性を検査する手段であり出所の認証ではない。
- テストの未検出、0件、全 skip、失敗、timeout、runner error は成功にしない。非適用は理由と事前に認可された条件を明示。文章や見た目が要件なら、hash と JUnit だけで満たしたとしない。
- 独立レビューの対象候補、観測できたモデル/provider・実行 ID、指摘と修正履歴、未解決事項。生成モデルの「問題なし」を承認記録へ昇格させない。
- 全 attempt の費用・時間・retry、拒否・取消・不明結果、実 cleanup、既知の限界。公開版には匿名の技術証跡のみを残し、生ログ・秘密・個人情報・社内情報は載せない。秘匿で必須根拠を失う場合は、許可された非公開の検証経路を別途用意するまで停止。

**merge 判断へ渡せる条件:** 全受入 ID に根拠があり、最終候補とテスト/レビュー/必要 CI が一致し、hard deny・必要承認・未解決の重大指摘・必須証跡欠落がなく、実行と cleanup の結果が照合されていること。満たさない候補は不足理由を付けた draft としてのみ提示し、READY_FOR_MERGE を宣言しません。head・base・基準変更時には影響する根拠を再取得します。

### 判定主体と最低限の検証表（提案）

判定は trusted controller の決定的な検査と人の oracle 所有者が認めた基準で行います。LLM に基準の充足や予算の解除を決めさせません。F3 の各負例は全件拒否、正常対照は全件受入を必要とし、1件でも逆ならその gate を不合格とします。

| 検証 ID | 入力・故障 | 必要な観測結果 |
|---|---|---|
| AC-01 | 古い候補、削除/mode/rename、unknown base | 完全候補の再構成不能や digest 不一致を拒否。部分 diff で代用しない |
| AC-02 | oracle・fixture・skip・選択範囲の改変、全skip、検査欠落 | 合格への昇格なし。必要基準の変更なら新しい承認と再検証 |
| AC-03 | 同一モデルのみのレビュー、モデル/実行 ID 不明 | 独立レビュー未充足。人の判断または認可済み別経路の確認まで停止 |
| AC-04 | 3候補到達、30分到達、費用/入出力の上限到達 | 次の呼出なし。台帳の消費と停止理由を再起動後も維持 |
| AC-05 | 同じ失敗2回、変更なし、範囲違反 | 修正ループを停止し、失敗 fingerprint と候補を残す |
| AC-06 | 取消、worker 生存、外部結果不明 | 新規 dispatch なし。process と外部結果を照合するまで lease 再配布なし |
| AC-07 | 二重配信、応答喪失後の再開 | 同じ task/run/attempt の予約・journal を照合し、副作用を重複実行しない |
| AC-08 | 正常な固定要件・候補・独立根拠・cleanup | 判断資料だけから試行を再構成可能。必要 CI と人の merge 判断を待つ |

提案する状態対応は、未確定要件→PROPOSED/NEEDS_HUMAN、認可・preflight 済→READY、Builder実行→RUNNING、独立検査→VALIDATING、独立レビュー→REVIEW、全根拠確定→READY_FOR_MERGE、人の merge を実測照合→DONE です。失敗→FAILED、未確認境界→BLOCKED、停止確認後→CANCELLED を使い、遷移は既存 StateLedger の許可・CAS に従います。修正時に既存状態から RUNNING へ直接戻せるとは仮定せず、合法な再試行遷移と新 attempt を F2 で設計・検証します。

安全性の採用閾値は、必要検査の見逃し、承認逸脱、未照合の外部副作用、必須証跡欠落、予算超過の継続呼出がすべて0件です。時間短縮や介入率の数値目標は baseline 測定後、pilot 前に人が固定します。未定義の性能指標を達成済みとしたり、自動的な本番採用の条件にしたりしません。

## 7. 段階と採用判断

| 順序 / 対応 G | 次に作るもの | 進めるための受入条件 |
|---|---|---|
| F1 / G1 | 完全差分の負例と版付き要件・設計・証跡契約 | 削除・mode・rename・unknown base、古い候補、改変基準を拒否。現行の完全差分拒否を外すのは修復後の検証付き別 PR だけ |
| F2 / G2 | CLI/API 共通の承認・モデル分離・累積予算ゲート設計 | 偽の承認、同じモデルだけの自己合格、基準書換え、失効、予算リセット、未認可 fallback を両入口で拒否 |
| F3 / G4 | 公開・合成案件によるオフライン全工程 harness と判断資料 | 正常系1件と、検査欠落・全skip・改ざん・上限・取消・再起動・二重配信・結果不明の各負例を再構成可能。模擬値は実モデルの品質・隔離証明としない |
| F4 / G4→G5 | 既存認可済み公式 worker 経路1つの限定 pilot | 前段成功、実行能力/上限/独立 reviewer/cleanup が確認できた時だけ着手。3件の同程度の実案件で全試行と分母を保存。承認逸脱・必須根拠欠落・未照合副作用が1件でもあれば拡大停止 |
| F5 / G5 の配置研究 | Cloudflare 等への配置可否 ADR | 別研究メモの未確認点と費用・契約・情報管理が解決するまで配置しない。既存オフライン adapter の安全性を継承したとは主張しない |

G3 の人の資格参照は既存計画のままです。F 段階は実装順の候補で、現行 task schema の phase 1–4 とは異なります。

測定はタスク種別・難度・モデル・入力・oracle を揃え、既存手動 handoff と比較します。要件確定後の追加人介入件数、merge 判断時間、受入条件の見逃し、失敗/中断/再試行率、全候補あたり費用、最終受理案件あたり費用、復旧時間を報告します。中止案件も分母に含めます。3件の成功は一般信頼性の証明にはせず、短期的な使い勝手と境界の採否判断に限ります。

## 8. ダッシュボード担当へ渡すタスク候補

以下は既存受信口へ渡すための候補です。台帳の直接編集、タスク投入、自動着手はこの文書では行いません。ID は担当側で既存ルールに従って発行してください。

| 候補キー / 種別 | 内容と依存 | 受入条件 |
|---|---|---|
| FACTORY-CONTRACT / 改修計画 | F1→F2、既存 G1/G2 に紐付け | 固定要件・完全候補・oracle・承認・累積上限の契約と負例一覧がレビュー可能。既存拒否を維持 |
| FACTORY-EVIDENCE / 改修計画 | F3、上記契約後 | 正常/異常系、独立レビュー不足、再開/取消を含む判断資料を1件再構成できる。COLLECTED を合格としない |
| FACTORY-PILOT / 条件付き候補 | F4、F1–F3通過後 | 既存認可済み1経路・3案件・全試行記録。追加購入せず、実 cleanup と分母付き測定を確認 |
| CLOUD-BOUNDARY / 研究 | F5、改修と独立 | Worker/Containers/Sandbox、個人 OAuth と API 課金、会社の入力/認証/デバイス境界を出典付きで区別。未承認の接続・認証・配備をしない |

最初の具体的な開発候補は FACTORY-CONTRACT です。今回の成果は計画と研究の記録であり、実装完了や pilot 着手を示しません。

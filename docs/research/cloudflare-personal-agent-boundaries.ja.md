# Cloudflare と個人 coding agent の配置・情報境界の研究メモ

**調査のみ / 未実装（2026-10-21）。** Cloudflare を入口に個人 Codex / Claude Code を動かす構成は技術的な候補ですが、会社環境からの利用可否は未確定です。会社情報を個人アカウントへ持ち出さないことを前提に、公開または明示的に外部送信を許可された入力だけを扱います。接続できることと、情報管理上許可されることは別です。

今回、実装・deploy・トンネル・会社への接続・新規認証・資格情報の移動・サービス契約や購入は行いません。特定の会社、端末、アカウント、社内規則に関する事実は収集・公開していません。現行 Experimental / MANUAL_ONLY と[改修計画](../architecture/bounded-factory-plan.ja.md)のゲートを維持します。

## 1. 発表の構想と公式仕様を分ける

発表の出典・確認方法は[計画の出典欄](../architecture/bounded-factory-plan.ja.md#1-出典と確認範囲)を参照してください。[22頁](https://speakerdeck.com/timakin/kodingu-jidouka-no-tsugi-he-hito-no-kainyuu-o-zero-ni-suru-to-sapoto-ai-niyoru-jissen?slide=22)の transcript は、Worker 受付、Sandbox、個人 OAuth / サブスクリプション、ブラウザ検証、Vault を組み合わせる構想です。図の画像は未確認で、実装コードや運用保証が添付された検証結果としては扱いません。

以下は **2026-10-21 に本文を確認した公式仕様**です。将来の検討時には対象バージョンと提供状態を再確認してください。

| 対象と一次資料 | 確認できた事実 | ここからは保証されないこと |
|---|---|---|
| [Workers limits](https://developers.cloudflare.com/workers/platform/limits/) | Worker は isolate の CPU・メモリ等に制限がある。CPU時間とネットワーク待機を含む wall time は別 | 通常の Worker 内で Linux CLI や長時間の開発工程すべてを動かせること |
| [Containers](https://developers.cloudflare.com/containers/) | Worker が制御するコンテナで、Linux 環境等を要するコードを実行できる。Workers Paid plan の機能 | 既存プランで利用可能・追加費用ゼロであること。本 repo のオフライン境界との同等性 |
| [Sandboxes overview](https://developers.cloudflare.com/sandbox/) | Worker から利用する Container と Dynamic Worker の選択肢。Container は full Linux の microVM。SDK 0.x と現行版の移行説明が分かれている | SDK サンプルを旧版へそのまま移植できること。Dynamic Worker で既存 Linux CLI が動くこと |
| [Sandbox security](https://developers.cloudflare.com/sandbox/concepts/security/) | caller を Worker で認証し、identity から sandbox 名を導く必要がある。Container のネットワーク、出力、preview の origin には個別統制が必要 | sandbox 名が認可になること、隔離だけで漏洩や越権を防ぐこと |
| [Sandbox lifetime](https://developers.cloudflare.com/sandbox/concepts/lifetime/) | instance と Durable Object の寿命は別。snapshot は filesystem を保存するがメモリやプロセスを継続しない。instance 終了で mounted bucket の保存物は消えない | 停止要求だけで成果物・認証情報・課金がすべて消えること。snapshot で実行がそのまま再開すること |
| [Queues delivery](https://developers.cloudflare.com/queues/reference/delivery-guarantees/) | 既定は at-least-once で重複配信があり得る | exactly-once の job 起動。受理しただけで副作用の重複がないこと |
| [Cloudflare Codex runner](https://developers.cloudflare.com/sandbox/coding-agents/codex/) / [Claude Code runner](https://developers.cloudflare.com/sandbox/coding-agents/claude-code/) | 現行の公式例は AI Gateway 経由で provider API を利用し、provider key または Unified Billing の経路を前提にする | 発表22頁の個人 OAuth 枠でそのまま動くこと。個人サブスクリプションと API 利用料が共通であること |
| [OpenAI authentication](https://learn.chatgpt.com/docs/auth) | ChatGPT サインインは subscription、API key は usage-based access。headless の device code 認証は beta で設定/権限の前提がある | この Cloudflare 構成や対象アカウントで認証・更新・必要モデルが使えること |
| [OpenAI CI/CD account auth](https://learn.chatgpt.com/docs/auth/ci-cd-auth) | 通常の自動化には API key を推奨。account auth を維持する方法は trusted private automation 向けの高度な手順 | 個人 OAuth を共有サービスへ再配布する認可、会社データを個人枠へ送る許可 |
| [Claude Code authentication](https://code.claude.com/docs/en/authentication) | 個人 subscription、組織アカウント、Console 等で認証経路が異なり、組織による login 制限がある | 個人のログインを組織用統制の代替にできること |
| [Claude Code Remote Control](https://code.claude.com/docs/en/remote-control) | ローカル session を別デバイスから操作する。実行はローカルに残り、outbound HTTPS で接続する | Cloudflare の実行環境への移行、会社端末の利用許可、会話データがローカルだけに留まること |

**採用しないサンプル設定:** Cloudflare の現行 Codex / Claude Code runner 例には、agent 内蔵の承認・sandbox を無効にして外側の container に境界を任せる設定が含まれます。本依頼は検査・拒否を緩めないため、設定を転記・実行しません。外部境界があるという説明だけで内蔵統制の除去を正当化せず、同等以上の強制と実証がない方式は本プロジェクトへの採用対象から外します。

## 2. 構成候補と実現性（当方の提案）

### A. Worker を受付、既存の個人実行環境を worker にする

流れの候補: 認証済み要求 → 受付のデータ分類・権限検査 → 既存 transport → 個人の隔離実行領域 → 既存 handoff → 独立検証 → 人の merge 判断。

Cloudflare 上へ個人 CLI のログインを移す必要はありません。一方、個人端末への配送・応答・停止・状態照合を担う既存の認可済み経路が必要です。Worker は任意の個人 PC 上の CLI を直接起動する製品ではありません。Cloudflare Tunnel や新規常駐 agent の導入を暗黙に加えません。Claude Remote Control は独立した公式の候補として比較できますが、独自 Worker の job transport と互換とは扱いません。会社環境から個人端末を操作できるかは認可未確認です。

**判定:** 公開・合成入力の配置案として設計可能。既存配送経路・停止照合・端末の認可が確認できるまでは研究段階。

### B. Worker を受付、Cloudflare の Linux Sandbox で CLI を実行

流れの候補: caller 認証 → 受付と一意な job 登録 → durable controller → タスク別 Linux instance → 制限した provider 通信 → 候補回収 → 別の trusted verifier / Reviewer → PR 判断資料。

Linux CLI を実行する役割は Containers/Sandbox、HTTP 受付・認可・状態連携は Worker とし、重複配信対策を制御プレーンで行います。instance のディスクを永続台帳にしません。現行の公式例は API 経路なので、個人 OAuth 版は別の認証・契約・可用性検証が必要です。subscription 枠の % を token や金額へ換算して予算としません。

**判定:** 公式の実行部品は存在するものの、個人枠・費用・情報管理・既存拒否の維持を含む構成全体は未検証。新規有料機能が必要なら今回の禁止条件により着手不可。API 課金へ無断で切り替えません。

### C. 会社用途は会社が認可・管理する実行環境とアカウントに分ける

会社情報を要する依頼は、会社が認めたアカウント・保存先・実行環境で扱う別案にします。個人サービスへ会社コード、ログ、チケット本文、画面、顧客情報、識別子を送らないことが前提です。匿名化したつもり、公開リンクに置いた、本人の会社端末で閲覧できる、という理由だけでは送信許可にしません。

**判定:** 会社の情報管理・法務/契約・端末/ネットワーク担当による確認が必要。特定組織の許可を取得したとは記録しません。公開・合成課題の設計研究だけは会社接続と独立に進められます。

## 3. 認証・端末・データの境界

次の境界は別々に確認します。認証の成立は下流の操作・データ送信の認可を意味しません。

| 境界 | 設計で求める条件 | 確認すべき負例 |
|---|---|---|
| 依頼者 → 受付 | caller、対象アプリ、操作、task scope を照合。[Cloudflare Access JWT](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/) は署名・issuer・audience を検証する公式方法があるが、導入は未決定 | 認証なし・別 audience・期限切れ・別利用者の run 参照を拒否 |
| 会社端末 → 個人サービス | 会社が許可した端末・接続先・入力分類だけ。端末 posture / IdP / browser 管理要件は組織依存で未確認 | ログインできても禁止データを送らない。SSO 有効だけで端末準拠済みとしない |
| 受付 → job / runtime | caller 由来の tenant と task をサーバ側で結合。一意キーと lease、期限、予算を既存制御へ結合 | 利用者提供の sandbox 名、重複要求、snapshot の共有で他人の内容へ到達しない |
| CLI → model provider | 本人/組織の正当な認証、許可されたモデル・データ・endpoint。個人 OAuth と API key を別の費用/管理境界として扱う | login 失効・モデル不明・料金不明で停止。API key へ fallback しない |
| runtime → GitHub / evidence | branch/PR のみを認可した transport と独立 verifier。必要証跡を安全に回収し、公開前の分類と確認 | 人の merge 資格情報の共用、社内 log の貼付、COLLECTED の成功昇格を拒否 |

Vault や secret store から環境変数へ注入すると、そのプロセスが値を読める可能性が残ります。[既存 broker 計画](../security/local-credential-broker.md)と G2/G5 の分離を再利用し、値をモデルに渡さない操作代理を優先候補にします。ただしモデル通信の OAuth が代理方式で成立するかは provider ごとに未確認で、API key 用の注入例を OAuth 更新へ一般化しません。

## 4. 後続研究で閉じる問いと採用条件

| 未確認点 | 次に必要な証拠 / 採用を止める条件 |
|---|---|
| 個人 OAuth の自動実行と更新 | 対象 CLI 版・provider 公式仕様・契約上の許容範囲、利用者単位の保存/失効/更新方式。未確認なら OAuth runtime を作らない |
| 既存契約と追加費用 | 既存 plan の利用権・予算・残枠と compute/storage/egress/model の別見積。新規課金・購入が必要なら停止。今回の研究で利用資格を調べるためのログインはしない |
| 情報管理・保持・学習 | 各 provider / gateway / log / snapshot / artifact の処理者、保持・学習設定、保存地域、削除・監査条件。組織管理者が認めるまでは会社情報を送らない |
| 会社端末・ネットワーク | 会社が認める認証方式、端末準拠、外部送信・遠隔操作・個人環境利用の可否。未許可の Tunnel / VPN / proxy / agent を置かない |
| 隔離と最小権限 | internet/egress、mount、identity、credential、preview origin、出力回収を固定し、合成マーカーの漏洩・越権・cross-user の負例を検証。内蔵統制の除去を前提にしない |
| 停止・再開・費用 | controller 再起動、重複配信、instance 強制終了、snapshot 復元で cumulative budget と結果照合が維持される証跡。process 終了と課金/保存物終了を区別 |
| 本 repo との接続 | G1 の完全差分、G2 の承認と予算、G4 の受入証跡が通ること。外部 agent の成功だけでは採用しない |

最初の研究用ケースは、社内由来でない公開の小さなリポジトリか合成チケットとし、入力・出力・preview・ログも合成データだけに固定します。会社接続を伴う実証とは別に扱います。会社の承認文書や内部データをこの公開リポジトリへ保存する必要はありません。

**現在の判断:** Worker と Linux 実行環境の役割分担には一次資料上の裏付けがあります。個人 subscription を使う構成の運用成立、会社からの利用可否、費用・保持・認証更新・停止照合は未確認です。したがって設計候補の記録までに留め、実装・認証・配備へは進みません。

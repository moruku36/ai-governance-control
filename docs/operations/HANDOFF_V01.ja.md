# ローカル成果物受渡し v0.1

承認済み個人AIチーム計画の最初の小さな実装として、manifestと受け手側のbytes照合を追加した。
AI Governance ControlはExperimental / MANUAL_ONLYのまま。外部agent、クラウド実行、model切替や常駐の保存サービスは追加しない（基本の受信器はステートレスのままであり、任意のcoordinatorも呼出元が明示指定したローカルSQLiteファイルのみを使用する）。

## 手順

1. 開始時に必須一覧、依頼・入力のhash、受入条件、対象snapshot、許可範囲と上限を固定する。
   成果物を作った後、正確なサイズ・SHA-256・既存private保存先のID/versionを記録する。
   変更や再試行には新attemptを付け、旧記録を残す。
2. `manifest.json`と許可した出力だけを既存の承認済みprivate保存先に置く。
   manifestの期待SHA-256、run/attempt ID、各versionはDottie等の**別の信頼した実行記録**に固定する。
   packetの自己申告hashだけでpacket全体の差替えを検出することはできない。
3. 受け手の別環境へ実際のbytesを既存ツールで取得する。元環境のpathやURLだけでは取得済みにしない。
4. 変更のない受け手側directoryに対し次を実行する。trusted recordは別の信頼した経路で受け取る。

   ```powershell
   python -m orchestrator.handoff --packet C:\private\receiver\packet `
     --trust C:\private\coordinator\trusted.json `
     --receipt C:\private\receiver\receipt-attempt-1.json
   ```

   exit 0は**COLLECTEDのみ**。exit 2は受領検証のBLOCKEDで、成功receiptは作られない。
   JSONをUTF-8へ完全にencodeしてから同じdirectoryの一時ファイルへ書き、flush後にhard linkで原子的に公開する。
   同時作成を含め同名receiptの上書きを拒否する。hard link非対応のfilesystemはBLOCKEDとする。
   強制終了で一時ファイルが残る場合はあるが、書込み途中の最終receiptは公開しない。
   一時ファイルの後始末はbest effortで、失敗しても公開済みreceiptの成功や元の公開エラーを変更しない。
   trustとreceiptはpacketの外に置く。
   trusted recordの認証は既存の配送経路の責任であり、このローカルツールは認証しない。

   **受信器の境界と再試行手順**:
   - 受信器は完全に**ステートレス**であり、原子的なhard linkによる同一パスの排他作成（上書き拒否）のみを保証する。別パスでの重複排除や実行再送制御は上位coordinator（Control Plane/Dottie）の責務であり、受信器に新たな永続サービスや汎用dedupeは追加しない。
   - 下記の任意のローカルcoordinatorは`(run_id, attempt_id)`と受領先パスの固定を実装する。上の単独受信器コマンドにはこのガードがないため、直接利用する呼出し元は一意なパスを管理する。
   - exit 2（BLOCKED）はhashや検証の失敗だけでなく、既存受領先との衝突（二重作成拒絶）や公開失敗も表す。そのため終了コード単体で再試行可否を判断してはならず、エラー原因と固定受領先パスの状態を確認しなければならない。公開前に検証が失敗した場合は成功receiptは作成されない。coordinatorは以下の手順でのみ安全に再試行できる:
     1. 具体的なエラー原因を確認し、指定受領先パスに成功receiptが存在しないことを確認する。
     2. packet転送の補正や不足証拠の補充を行う。
     3. 同じ固定受領先パスに対して再度照合を実行する。
     既に成功receiptが存在する場合、coordinatorは同一パスに対して絶対に再試行してはならない（MUST NOT）。変更や後続実行には新しい正規の`attempt_id`と別受領先パスを割り当てなければならない。
5. 固定candidateへの受入試験と必要な独立レビューを別に行う。実際の実行・取消・停止・引継ぎも別に照合する。
   本ツールはVERIFIED/COMPLETEへ進めない。送信側の`declared_status`を主張として残し、
   verificationはunknownとし、`next_step`を受領記録に残す。再送や二重起動は行わない。

## 任意のローカルcoordinator（実験段階）

`python -m orchestrator.coordinate_handoff --packet PACKET --trust TRUST_JSON --db PRIVATE_LEDGER_SQLITE --receipt-dir PRIVATE_RECEIPTS`で、明示指定したSQLite DBを使う。DBの親ディレクトリとprivate受領ディレクトリは事前に作る。運用台帳への統合には所有者の承認が必要。信頼記録は既存の認証済み経路から受け取り、packetの外に置く。このコマンド自体は配送元を認証せず、常駐サービス、遠隔agent、タスク状態更新も行わない。

coordinatorは`handoff_receipt_reservations`テーブルのみを追加する。SQLiteの即時トランザクションでrun/attemptの組に対する受領先をSHA-256由来のファイル名に固定し、信頼記録全体のhashを保存する。同じattemptで信頼記録や受領ディレクトリが変われば拒否する。異なるattemptは別パスとなり、IDは生のパス部品にしない。既存の`task_states`は変更しない。このガードの対象は同じDBを共有する呼出し元のみ。

受信器の従来のbytes検証と上書きしない公開を再利用する。検証失敗や予約後の中断なら同じ記録とパスで再試行できる。公開後、DB更新前に中断した場合は、DB内のランダムな予約鍵を用いて受領ファイル全体のMACを検証し、`COLLECTED`に戻す。異なるMACやpins、`COLLECTED`後の受領ファイル欠落は手動照合まで拒否し、上書きしない。hard linkが拒否されても予約は残り、成功受領にはしない。このMACはローカルDBとの整合性確認であり、送信元認証ではない。復旧試験はプロセス中断（クラッシュやkill）を対象としたものであり、停電時のディレクトリ永続化（ディレクトリfsync等）は未検証かつ保証外である。

**Done条件**: `COLLECTED`は固定されたbytesを受領したことのみ示す。完了には認証済み配送、実ソースの来歴、独立した受入テストとレビュー、実行・取消状態の照合、本番統合の承認が別途必要。合成データによるオフライン試験と模擬公開はこれらを満たさない。

## 最小記録

- 識別: `schema_version=0.1`、run/attempt/親run、目的、producer、依頼hash、受入条件、状態主張、次の1手。
- 入力・コード: 入力ID/サイズ/hash、repo、完全な40桁Git SHAまたはunknown、固定snapshot SHA-256、dirty、base、完全差分必須フラグ。
  入力の記録はprovenanceであり、本出力検証で入力bytesを再取得した保証ではない。
- 環境: 種別・OS・ツール版、要求model/effortと観測したmodel/effortを別欄にする。未観測はunknown。
- 実行: 受付・開始・終了・exit code。未観測はnull。本ツールは呼出者の記録を認証・実行しない。
- 出力: 相対path、用途、必須/任意、byte数、SHA-256、producer、取得時刻、永続保存先IDと文字列version。
- 試験: 必須フラグ。JUnit必須なら一覧内の必須report、command、tool版、snapshot hashを指定する。
  欠落・切詰め・0 testcase・全skip・failure/error・件数矛盾・DTD/entityを拒否する。
  JUnitはUTF-8のみ（UTF-8 BOM可）。NUL・他encoding宣言・DTD/entityをXML解析前に拒否する。
  hash一致やreport構文だけでは、実際の試験実行を証明しない。
- レビュー: reviewer、対象snapshot hash、判定・指摘。未実施なら空配列。主張だけで承認済みにしない。
- `limits_and_authority`: 許可操作・期限・費用/試行上限。秘密値を書かない。本ツールによる権限追加はない。

別trusted JSONは`manifest_sha256`、`run_id`、`attempt_id`、全出力の`output_versions`を持つ。
manifestのbytes（文字コード・改行含む）を固定してhashを取る。必須を減らす変更も期待hashと合意の更新が必要。
任意の欠落をreceiptに列挙し、一覧外ファイルは読み出し・コピー・受領件数に含めない。

上限: manifest/trust 1 MiB、100出力、1ファイル10 MiB、総宣言50 MiB。
path traversal、Windows drive/ADS/予約名、秘密/制御path、大小文字違いの重複、競合path、symlink/Windows reparse pointを拒否する。
WindowsではPython 3.11にもあるlstatのst_file_attributesを使い、3.12専用のPath.is_junctionに依存しない。
実測はWindows Python 3.12で行い、実junctionと旧pathlibを模した負例を含む。3.11実環境は未実測。
本処理は受け手が管理する静止directoryで行う。攻撃者による同時書換えへのsandboxではなく、secret scan保証でもない。

## 試験と残る範囲

Python >=3.11、追加依存なしのCPU試験:

```powershell
python -m unittest discover -s tests/unit -p test_handoff.py -v
```

同じ試験は通常のpytestにも参加する。匿名例は
[`../examples/handoff-v01`](../examples/handoff-v01/manifest.json)にある。
JUnitも合成fixtureであり、実メール処理・RunPod実行の証拠ではない。
`trusted.example.json`は実受信packetの外に置く。教材のhashは認証された信頼記録ではない。

既存adapterのartifact抽出既定、削除/mode差分欠落、unknown baseのbest-effort経路は今回修正していない。
この最小受領ツールは完全差分が必須ならbase既知でもBLOCKEDとする。完全差分の修正・負例再現は別の段階が必要。
取消/クラッシュは既存controllerの実測照合が必要で、packetの状態主張を停止確認に読み替えない。

業務試行は合成メールだけで、未回答・矛盾・約束の勝手な追加を本人が受入確認する。hashだけでは対話品質を保証しない。
RunPodは既存の許可済み固定selftestと実際の終了証跡が必要。本ツールはその実行機能を提供しない。
同種実仕事3件の再取得と負担時間測定はまだ未実施であり、採用効果を主張しない。

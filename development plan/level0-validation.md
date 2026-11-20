# レベル0の実装と確認（2026-11-18）

## 実装した範囲

- Gmailの検索・本文取得・送信はすべてバックエンドで保留し、ブラウザの許可/拒否を待つ。LLMの引数や音声での「はい」は承認にしない。
- 実行ID、固定された引数、有効期限（120秒）、状態をセッションごとのメモリで保持。LiveKitが認証したRPC呼び出し元を使用し、最初のブラウザに承認権限を固定する。
- 拒否・期限切れ・切断・セッション終了では未実行の操作を実行しない。重複決定を再実行しない。同じセッション内の同一内容の依頼は、終端状態も含めて再実行しない。
- 実行を開始したAPI呼び出しは取り消せない。実行中の切断や送信エラーは結果不明として扱い、自動再送しない。結果不明時は送信済みを人が確認する。
- プロセス再起動をまたぐ承認の保存・再開はしない。新セッションには引き継がず、結果不明の操作を再作成しないよう人が確認する。
- RPCのペイロード上限に収めるため、承認内容はUTF-8で9,000バイトまで、1セッション100操作まで。同時承認待ちは1件ずつ表示する。
- consoleモードは承認UIがないので、外部ツールを実行できない。通常の会話は利用可能。
- `prompts/system-v1.md`を既定にし、版番号とSHA-256をトレースへ付与。比較用に以前の指示を`system-v0.md`へ保存。
- LiveKitの既存`llm_request`をLangfuse generationとして扱い、モデル・プロバイダー・トークン数・TTFTを対応付ける。generationを追加生成して費用を二重計上しない。
- SDKの会話ターンID、メッセージID、割り込み、遅延、ツール実行ID、状態イベント、セッション終了時のモデル別使用量を記録する。累積使用量は加算せず最新値に置換する。
- セッションを閉じてSDKのルートspanが終了した後にflushし、exporterをshutdownする。起動エラー・通常終了・途中終了を同じ経路で処理する。

## トレース内容と費用の方針

Langfuse向けには会話・メール本文・ツール引数を送らず、`allow_pii=False`を固定する。プロンプト本文も送らず版とハッシュのみ記録する。ローカル評価結果にも実メールや秘密情報を記載しない。LiveKit Cloud自身の収集・保存設定は別途LiveKitプロジェクトで管理する。

`LOCAL_USER_ID`は匿名のローカル識別子を指定する（メールアドレスを使わない）。`LANGFUSE_RELEASE`には比較するGitコミットなどを指定できる。

LLM費用は次のいずれかとして扱う。

- Langfuseでモデル名が価格定義に一致する場合：Langfuse側の価格推計。
- `OBSERVABILITY_PRICES_FILE`を設定する場合：アプリで使用量×設定単価をUSD推計し、`configured_rate_estimate_usd`と明示。
- 価格が不明な場合：未取得。0ドルという意味ではない。

単価ファイルはモデル名をキーにしたJSONで、`input_per_million`、`output_per_million`を指定する。キャッシュが発生するモデルには`cached_input_per_million`、`cache_creation_input_per_million`も必要。現在の契約・プロバイダー単価を人が確認して設定する。キャッシュ分は通常入力から差し引き、二重計上しない。

STT/TTSはモデル別の音声時間・文字数・トークン数をSDKが提供する範囲で記録し、費用は現段階では`unavailable`。それ以外のサービス費用は`not_instrumented`。Langfuse合計は請求額ではない。

## ローカル自動検証

```sh
cd Test-LiveKit
uv run --locked pytest -q
```

```sh
cd fronted-test
npm ci
npm run build
```

承認の状態遷移、引数の固定、他セッション・他参加者の拒否、二重実行防止、結果不明時の再試行禁止を実メールなしで検証する。実SDKのOTel spanをメモリ内exporterへ送り、親子関係・セッション属性・本文除外・generation・使用量・推計費用を検証する。

## あなた側で行う作業

1. GitHub ActionsとCloudflareの停止は前回案内した管理画面で実施する。このレベル0の変更は未デプロイで、CI/CD停止をリモートへ反映しない。
2. `Test-LiveKit/.env`へLiveKit/OpenRouter、必要なSTT/TTS、LangfuseのプロジェクトキーとリージョンURLを設定する。既存ファイルを上書きせず不足項目だけ補う。
3. 合成トレースを送る。

   ```sh
   cd Test-LiveKit
   uv run --locked python trace_smoke.py --export
   ```

   会話・Gmailを使わず3つの合成spanを送る。`accepted_spans`と`failed_spans`を確認する。`queue_drained=True`だけで受理成功と判断しない。
4. Langfuseで出力された`session_id`/`trace_id`を検索する。プロジェクト、日付、environmentのフィルターを確認し、ルート・generation・synthetic_toolの親子関係を確認する。合成のトークン数は請求実績ではない。
5. READMEの3ターミナルでAgent・token server・UIを起動し、`http://localhost:5173`を開く。クラウドAgentが同じLiveKitプロジェクトで動いていないことを確認する。
6. `Test-LiveKit/evaluations/level0-cases.json`の同じ会話を`SYSTEM_PROMPT_VERSION=v0`と`v1`で評価する。版を変えるたびにAgentを再起動する。実メール送信は不要。許可する検索・読み取りはテスト用アカウントで行う。
7. 各版の結果を`results-template.csv`のコピーへ記録し、最大3文・不足情報の確認・不明時の回答・自然さ・承認挙動を比較する。トレースからTTFT/応答遅延、LLM使用量・費用と推計根拠も記録する。環境とモデルを揃えて比較する。
8. 実会話のトレースとコスト表示を別々に確認する。Langfuse価格が未対応なら価格定義か単価ファイルを設定し、サービス側の実績と照合する。

## 現在の確認状況

フロントエンドの型チェック・本番ビルドは成功。ローカル自動テストは94件すべて成功（既存テストを含む）。実ブラウザでのLiveKit接続・音声・承認UIの一連の操作は、認証情報を設定した環境での確認が残る。

ローカル環境の解決済みSDKはLiveKit Agents/OpenAI plugin 1.8.12、OpenTelemetry 1.45.2。コードと公式仕様を照合した。

実接続診断は実行したが、このローカル環境ではLangfuseの必要設定が揃わず、送信前に終了した。既報の「セッションは見えるがtraceが見えない」問題の原因をこれだけで断定しない。実サーバー受理・画面表示・実会話・価格の一致は未確認で、上の手順で最終確認する。SIGKILLや電源断時のflushは保証しない。

## 参照

- https://langfuse.com/integrations/frameworks/livekit
- https://langfuse.com/integrations/native/opentelemetry
- https://langfuse.com/docs/observability/features/token-and-cost-tracking
- https://docs.livekit.io/transport/data/rpc/

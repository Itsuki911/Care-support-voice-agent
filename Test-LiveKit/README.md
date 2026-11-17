# Test-LiveKit

ブラウザから音声会話を試す場合は、[fronted-test の手順](../fronted-test/README.md)を参照してください。

LiveKit Agents をターミナルから試す最小の Python 例です。コードは現行の LiveKit Agents API (`AgentServer`, `AgentSession`, `cli.run_app`) を使用します。LLM は OpenRouter 経由、音声認識・音声合成（STT/TTS）は LiveKit Inference 経由です。

## 1. 依存関係を準備する

PowerShell でこのフォルダを開き、次を実行します。

```powershell
uv sync
```

`uv` がない場合は、先に [uv の公式インストール手順](https://docs.astral.sh/uv/getting-started/installation/) に従って導入してください。

## 2. 設定を作る

```powershell
Copy-Item .env.example .env
```

`.env` を編集し、OpenRouter の `OPENROUTER_API_KEY` と `OPENROUTER_MODEL` を設定してください。LLM の `OPENROUTER_MODEL` は OpenRouter のモデル ID（例: `anthropic/claude-haiku-5.5`）です。テキスト専用コンソールでは、この 2 つだけで起動できます。

音声モードには、LiveKit Cloud プロジェクトの `LIVEKIT_URL`、`LIVEKIT_API_KEY`、`LIVEKIT_API_SECRET` と、LiveKit Inference の `STT_MODEL`、`TTS_MODEL`、`TTS_VOICE` が必要です。`STT_MODEL` と `TTS_MODEL` は `provider/model` 形式、`TTS_VOICE` は選択した TTS プロバイダーの音声 ID です。

`OPENROUTER_API_KEY` は必ずローカルの `.env` にのみ置いてください。すでに `.env.example` にキーを貼り付けた場合は、上記のコピー後に `.env.example` 側の値を空に戻してください。キーが共有済み・履歴に残った可能性がある場合は、OpenRouter 側でローテーションしてください。

OpenRouter 接続には LiveKit の OpenAI プラグインを使用します。API キーを Git に追加しないでください（`.env` は除外済みです）。OpenRouter のモデル一覧は [OpenRouter Models](https://openrouter.ai/models)、LiveKit の連携仕様は [OpenRouter LLM plugin guide](https://docs.livekit.io/agents/models/llm/openrouter/) を参照してください。

## 3. ターミナルで試す

テキストだけで対話する場合:

```powershell
lk agent console --text
```

マイクとスピーカーを使う場合:

```powershell
lk agent console
```

オーディオ機器を確認する場合:

```powershell
lk agent console --list-devices
```

コンソール実行はローカルで 1 セッションを試す用途です。LiveKit のルームで待ち受ける開発モードは、設定後に以下で起動できます。

```powershell
lk agent dev
```

## 公式資料

- [Voice AI quickstart](https://docs.livekit.io/agents/start/voice-ai/)
- [Agent server startup modes / Console mode](https://docs.livekit.io/agents/server/startup-modes/)
- [LiveKit Inference](https://docs.livekit.io/agents/models/inference/)
- [OpenRouter LLM plugin guide](https://docs.livekit.io/agents/models/llm/openrouter/)
- [LiveKit CLI](https://docs.livekit.io/intro/basics/cli/)

LiveKit CLI が未導入の場合は、公式の Windows 手順で導入してください。

```powershell
winget install LiveKit.LiveKitCLI
```

導入後は PowerShell を開き直し、`lk --version` で確認できます。Cloud プロジェクトへサインインする場合は `lk cloud auth` を使います。CLI があれば、Cloud の資格情報を `.env.local` に書き出す `lk app env -w` も利用できます。なお、このサンプルは Python の `python-dotenv` が読む `.env` を採用しています。

`lk` を使わず Python から直接起動することもできます。

```powershell
uv run agent.py console --text
```

## Gmail送受信ツール

agentに次のツールを登録しています。Gmail未設定でもagentは生成でき、Gmailツール呼び出し時に設定不足を案内します。

- `search_emails(query="in:inbox", max_results=5, page_token="")`: 受信メールを検索。`is:unread`、`from:...`などGmail検索式を使えます。1〜20件ずつIDを返し、`next_page_token`で続きを取得します。
- `read_email(message_id)`: 検索結果のIDで件名・差出人・本文を取得。既読には変更しません。本文は最大20,000文字で、省略時は`truncated=true`です。
- `send_email(recipient, subject, body)`: 宛先1件にプレーンテキストメールを送信。日本語の件名・本文に対応します。送信者はOAuth認証したGmailアカウントです。

受信はユーザーの依頼時に取得する方式です。常時受信通知、添付ファイルの取得・送信、CC/BCC、返信スレッド指定には対応していません。HTMLのみのメールはタグを除いたテキストに変換します。

### 後から認証情報を設定する（自分のPC）

Gmailは通常のAPIキーではなくOAuth 2.0が必要です。

1. Google CloudでGmail APIを有効化し、OAuth同意画面を設定します。テスト状態では使うGoogleアカウントをテストユーザーに追加します。
2. OAuthクライアントIDを「デスクトップアプリ」で作成し、ダウンロードしたJSONを `Test-LiveKit/.secrets/gmail-client.json` に保存します。
3. `Test-LiveKit`で以下を実行します。ブラウザとPythonを同じPCで動かしてください（スマホのlocalhostや、このCloud環境での認証にはそのまま使えません）。

```sh
uv sync
uv run gmail_auth.py
```

4. ブラウザで許可すると `.secrets/gmail-token.json` にトークンが保存されます。その後、通常どおり `uv run agent.py dev` または `uv run agent.py console` を実行します。

権限は `gmail.readonly` と `gmail.send` です。権限を変更した場合は再認証してください。テスト状態のOAuthアプリはGoogleのポリシーにより再認証が必要になることがあります。
設定ファイルの場所は `.env` の `GMAIL_CLIENT_SECRET_FILE` / `GMAIL_TOKEN_FILE` で変更できます。相対パスの基準は `Test-LiveKit` です。
`.secrets/` はGit除外済みです。JSONやトークンをチャットやリポジトリに貼らないでください。

例: 「未読メールを3件探して」「このメールの本文を読んで」「example@example.com に、件名を○○、本文を○○として送って」。送信はユーザーの明示的な依頼に限るようagentへ指示しています。
通信失敗で送信結果が不明な場合は、送信済みフォルダを確認してから再操作してください。SDKのAPIエラー再試行は0回に設定し、自動再送を行いません。実行中の送信は会話を停止しても取り消せない場合があります。

### API接続なしのテスト

```sh
uv run --locked pytest -q
```

Google SDKの呼び出し先をモックして、日本語MIME、検索・ページング、本文・HTML・添付の扱い、不正入力、未設定・権限不足・認証更新失敗、HTTPエラー、タイムアウト、非同期ツール登録、認証ファイル保存を検証します。実アカウントへの送信は行いません。
実際のGoogle認証・配送・LLMによるツール選択は認証情報の設定後に確認が必要です。

参照した公式資料:

- [Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
- [Gmail送信（MIME/base64url）](https://developers.google.com/workspace/gmail/api/guides/sending)
- [messages.list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list) / [messages.get](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get)
- [Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)
- [LiveKit Function tools](https://docs.livekit.io/agents/logic/tools/definition/)

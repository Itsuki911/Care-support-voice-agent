# Care Support Voice Agent

介護支援を想定した音声エージェントの機能検証プロジェクトです。LiveKit をリアルタイム会話基盤に、OpenRouter を LLM 接続に使用し、必要に応じて Gmail の検索・読み取り・送信をツールとして利用できます。

## 開発方針：ローカル作業（2026-11-18）

Cloudflareへの自動デプロイを一時停止する設定に変更しました。GitHub Actionsは手動実行の検証のみとし、デプロイジョブは無効化しています。この変更はGitHubへ反映して初めてリモート側に適用されます。

ブラウザUI・トークンサーバー・Agentは手元のPCで起動します。LiveKit Cloud、OpenRouter、STT/TTSなどの外部APIは引き続き使用するため、オフライン動作ではありません。

（参考）Cloudflare Workers 上の検証用 URL:
https://care-support-voice-agent.neymar020510.workers.dev/

### macOS / Linuxでの起動

リポジトリ直下から、別々のターミナルで実行します。初回は `Test-LiveKit/.env.example` を `.env` にコピーして認証情報を設定してください（既存の `.env` は上書きしません）。

```sh
# ターミナル1：Agent
cd Test-LiveKit
uv sync --locked
uv run agent.py dev
```

```sh
# ターミナル2：ローカルトークンサーバー
cd Test-LiveKit
uv run uvicorn token_server:app --host 127.0.0.1 --port 8000
```

```sh
# ターミナル3：ブラウザUI
cd fronted-test
npm ci
npm run dev
```

`http://localhost:5173` を開きます。UIの `/api` は標準で `http://127.0.0.1:8000` に転送されます。`fronted-test/.env.local` などに `TOKEN_SERVER_URL` を設定している場合もローカルURLを使用してください。

### リモート環境の停止確認

ローカルファイルの変更だけでは、既存の公開環境や実行中のジョブは停止しません。

- GitHub Actionsで `CI and Cloudflare deployment` を無効化し、実行中・待機中のrunがあればキャンセルします。
- Cloudflare側のCron Trigger、公開ルート、稼働中のContainerを確認して停止します。CI/CDの停止だけでは5分ごとのウォームアップは止まりません。
- 同じLiveKitプロジェクトに接続するクラウド側Agentが残っていないことを確認してからローカルAgentを使用します。

Cloudflareの設定ファイルは将来の再開用に保持します。以下のデプロイ手順は再開時の参考情報です。

## 現在の構成

```text
ブラウザ UI（fronted-test）
        │
        ├─ LiveKit Cloud ── LiveKit Agent（Test-LiveKit）
        │                         ├─ OpenRouter（LLM）
        │                         ├─ LiveKit Inference（STT / TTS、音声モード時）
        │                         └─ Gmail API（OAuth 設定時のみ）
        │
        └─ Token server（Test-LiveKit/token_server.py）
```

## 現在検証できる機能

- OpenRouter 経由の日本語テキスト会話
- LiveKit を使ったブラウザ音声会話
- 音声認識（STT）、音声合成（TTS）、発話区間検出（VAD）を含む音声モード
- Gmail の検索、本文の読み取り、明示的な依頼に基づくメール送信
- LiveKit Agent のローカル console モード

Gmail 機能には Google OAuth 2.0 の追加設定が必要です。添付ファイル、CC/BCC、スレッド返信、常時受信通知は現在の検証対象外です。

## ディレクトリ構成

| パス | 内容 |
| --- | --- |
| [`Test-LiveKit/`](./Test-LiveKit/) | Python 製 LiveKit Agent、Gmail ツール、トークンサーバー、テスト |
| [`fronted-test/`](./fronted-test/) | Vite + TypeScript + LiveKit Client SDK の検証用ブラウザ UI |

## ローカル起動

### 前提条件

- Python 3.10 以上と [uv](https://docs.astral.sh/uv/getting-started/installation/)
- OpenRouter の API キー
- 音声モードを使う場合: LiveKit Cloud の URL・API キー・API シークレット
- ブラウザ UI を使う場合: Node.js（LTS 推奨）

初回のみ、検証用の設定ファイルを作成します。

```powershell
cd "C:\Users\ITSUKI\voice agent\Test-LiveKit"
Copy-Item .env.example .env
```

`.env` に API キーとモデル名を設定してください。`.env`、OAuth JSON、トークンは Git にコミットしません。

### テキスト対話のみ

`.env` に少なくとも次を設定します。

```env
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=anthropic/claude-haiku-5.5
```

次に実行します。

```powershell
cd "C:\Users\ITSUKI\voice agent\Test-LiveKit"
uv sync
uv run agent.py console --text
```

LiveKit CLI が利用可能な場合は、次でも実行できます。

```powershell
lk agent console --text
```

### ブラウザ音声対話（ローカル）

音声モードでは、`Test-LiveKit/.env` に `LIVEKIT_URL`、`LIVEKIT_API_KEY`、`LIVEKIT_API_SECRET`、`STT_MODEL`、`TTS_MODEL`、`TTS_VOICE` も設定します。そのうえで、リポジトリ直下から 3 つのターミナルを開きます。

PowerShell 1（LiveKit Agent）:

```powershell
cd "C:\Users\ITSUKI\voice agent\Test-LiveKit"
uv sync
uv run agent.py dev
```

PowerShell 2（ブラウザ参加者用トークンを発行するローカル API）:

```powershell
cd "C:\Users\ITSUKI\voice agent\Test-LiveKit"
uv run uvicorn token_server:app --host 127.0.0.1 --port 8000
```

PowerShell 3（ブラウザ UI）:

```powershell
cd "C:\Users\ITSUKI\voice agent\fronted-test"
npm ci
npm run dev
```

表示された `http://localhost:5173` を開き、マイクの使用を許可して接続を試します。ハウリング防止のため、イヤホンの利用を推奨します。

## Cloudflareへのデプロイ（Workers + Containers）

ブラウザ UI とトークン発行は Cloudflare Workers で、常駐する Python 製 LiveKit Agent は Cloudflare Containers で動作します。`/api/token` は Worker 内でのみ実行され、LiveKit API secret や OpenRouter API key はブラウザへ送信しません。5分ごとの内部ヘルスチェックでコンテナをウォームアップし、初回の会話接続でも Agent を利用可能な状態に保ちます。

> これらのファイルをデプロイするまで、現在の公開 URL は静的フロントエンドのみです。`POST /api/token` が 404 の間はスマートフォンから会話を起動できません。

### GitHub Secrets（CI/CDのデプロイ認証用）

GitHub リポジトリの **Settings → Secrets and variables → Actions** に次の2つを登録します。

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

現在はpush・pull requestによる自動実行を停止しています。手動実行では検証のみ行い、Cloudflareにはデプロイしません。再開時はワークフローのイベントとデプロイ条件を明示的に復元してください。

### Cloudflareのruntime secrets（Agentとトークン発行用）

最初のデプロイ後、Cloudflare Dashboard の **Workers & Pages → care-support-voice-agent → Settings → Variables and Secrets** で、以下を **Secret** として登録します。または `cloudflare/` から `npx wrangler secret put 変数名 --config ../wrangler.jsonc` で登録できます。

```text
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
OPENROUTER_API_KEY
OPENROUTER_MODEL
```

音声会話を使う場合は、これら3つも同時に設定します。

```text
STT_MODEL
TTS_MODEL
TTS_VOICE
```

Langfuse を使う場合は `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_BASE_URL`、`LANGFUSE_TRACING_ENABLED`、`LANGFUSE_TRACING_ENVIRONMENT`、`LANGFUSE_RELEASE` を追加します。Gmailをコンテナで有効にする場合は、OAuth client JSON と token JSON をBase64化して、`GMAIL_CLIENT_SECRET_JSON_B64` と `GMAIL_TOKEN_JSON_B64` に設定します。JSONファイルはGitへコミットしません。

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes(".secrets\gmail-client.json"))
[Convert]::ToBase64String([IO.File]::ReadAllBytes(".secrets\gmail-token.json"))
```

Cloudflare向けの実行用設定例は [`cloudflare/.dev.vars.example`](./cloudflare/.dev.vars.example)、Worker/コンテナ設定は [`wrangler.jsonc`](./wrangler.jsonc) にあります。

## テスト

```powershell
cd Test-LiveKit
uv run --locked pytest -q
```

```powershell
cd fronted-test
npm run build
```

テストでは外部 API、実際の Gmail アカウント、マイクは使用しません。実環境での音声会話・Gmail 操作には、各サービスの有効な認証情報が必要です。

## 詳細ドキュメント

- [レベル0：承認UI・監視の確認と残作業](./development%20plan/level0-validation.md)

- [LiveKit Agent / Gmail ツールの設定](./Test-LiveKit/README.md)
- [ブラウザ音声会話 UI の設定](./fronted-test/README.md)

## 主な技術

- Python / LiveKit Agents
- OpenRouter
- LiveKit Cloud / LiveKit Inference
- FastAPI / Uvicorn
- Gmail API / Google OAuth 2.0
- TypeScript / Vite / LiveKit Client SDK
- Cloudflare Workers（機能検証用 URL）

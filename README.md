# Care Support Voice Agent

介護支援を想定した音声エージェントの機能検証プロジェクトです。LiveKit をリアルタイム会話基盤に、OpenRouter を LLM 接続に使用し、必要に応じて Gmail の検索・読み取り・送信をツールとして利用できます。

## 機能検証用 URL

現在、ブラウザ側の機能検証には Cloudflare を使用しています。検証用 URL は次のとおりです。

- [https://care-support-voice-agent.neymar020510.workers.dev/](https://care-support-voice-agent.neymar020510.workers.dev/)

この URL は機能検証段階の環境です。恒久的な本番 URL・可用性・データ保存方針を保証するものではありません。Cloudflare へのデプロイ設定やシークレットは、このリポジトリには含めません。

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

`main` への push で、Pythonテスト・フロントエンドビルド・Worker型検査が成功した場合のみ、Cloudflareへデプロイされます。

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

```powershell
cd cloudflare
npm ci
npm run check
```

テストでは外部 API、実際の Gmail アカウント、マイクは使用しません。実環境での音声会話・Gmail 操作には、各サービスの有効な認証情報が必要です。

## 詳細ドキュメント

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

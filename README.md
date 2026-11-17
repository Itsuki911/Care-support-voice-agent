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

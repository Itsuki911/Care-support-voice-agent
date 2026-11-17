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

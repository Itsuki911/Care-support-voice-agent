# ブラウザ音声会話テスト

TypeScript + Vite + LiveKit Client SDK の最小画面です。操作は「起動」「停止」のみです。
起動するとマイク音声を送信してAIの音声を再生し、停止すると切断してマイクを解放します。
ブラウザのボタンは会話への接続・切断用です。Pythonプロセスは別途起動します。

## 設定

`Test-LiveKit/.env.example` を同フォルダの `.env` にコピーし、既存のLiveKit・OpenRouter・STT/TTSの値を設定してください。
LiveKit Cloudを利用し、agentとトークンサーバーで同じプロジェクトの設定を使います。
フロントエンドでは、このフォルダの `.env.example` を `.env.local` にコピーします。
APIキーやシークレットをフロントエンドの環境変数に追加しないでください。

## 起動（3つのターミナル）

リポジトリのルートから、それぞれ実行します。

```sh
cd Test-LiveKit
uv sync
uv run agent.py dev
```

```sh
cd Test-LiveKit
uv run uvicorn token_server:app --host 127.0.0.1 --port 8000
```

```sh
cd fronted-test
npm ci
npm run dev
```

同じPCの `http://localhost:5173` を開いて「起動」を押し、マイク利用を許可して話しかけます。
AIの挨拶・応答を確認したら「停止」を押します。再度「起動」すると新しい会話になります。
ハウリングを避けるためイヤホンを推奨します。各プロセスの終了はターミナルで Ctrl+C です。
コンソールモードの `agent.py console` はブラウザ接続用ではありません。
既存agentは名前未指定のため、新規ルームへ自動dispatchされます。同一プロジェクトで動かすこのサンプルのagentは1つにしてください。

この設定はlocalhostでの開発確認専用です。`npm run build` は型チェック・ビルド検証用です。
`vite preview` や静的配信には開発用 `/api` プロキシがないため、上記の `npm run dev` を使ってください。

## 検証

```sh
cd Test-LiveKit
uv run pytest -q
```

```sh
cd fronted-test
npm run build
```

Pythonテストは実際のLiveKit SDKで署名したJWTを検証します。外部APIやマイクは使用しません。
実際の音声対話の確認には、有効なLiveKit/OpenRouter設定とブラウザのマイクが必要です。

## 参照した公式仕様

- [JavaScript SDK（Room・音声トラック）](https://docs.livekit.io/reference/client-sdk-js/)
- [Custom token generation](https://docs.livekit.io/frontends/build/authentication/custom/)
- [Agent dispatch（名前未指定時の自動割り当て）](https://docs.livekit.io/agents/server/agent-dispatch/)

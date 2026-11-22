# 音声エージェント評価基盤

`evaluations/evaluate_voice_agent.py` は、STT → LLM → TTS、Speech-to-Speech、RAG、ツール利用のいずれにも使える、プロバイダー非依存の評価ランナーです。結果は JSON と Markdown の両方で出力します。計測されていない値は **0 点ではなく `N/A`** と理由を記録します。

## 実行

```powershell
cd Test-LiveKit
uv run python evaluations/evaluate_voice_agent.py --input evaluations/voice_agent_cases.json --output-dir ../export/evaluation_reports/example
```

上記はネットワーク・API キー不要です。DeepEval の LLM-as-a-Judge 指標（回答関連性、タスク完了、RAG Faithfulness / Contextual Relevancy）も実行する場合は、評価用に独立したモデルを `.env` の `EVAL_JUDGE_MODEL` と `OPENROUTER_API_KEY` または `OPENAI_API_KEY` に設定し、次を使います。

```powershell
uv run python evaluations/evaluate_voice_agent.py --input evaluations/voice_agent_cases.json --deepeval-judge
```

通常実行でも DeepEval 4.3.4 の `ToolPermissionMetric` を実行します。これは LLM を呼ばない決定論的な権限境界チェックです。既存の秘書モードは、`evaluations/evaluate_secretary.py` の `GEval` / `ConversationalGEval` による会話評価を継続して使います。

## データ形式

入力は `voice-agent-evaluation-v1` JSON です。最小例は `evaluations/voice_agent_cases.json` にあります。`scenario_id` と `scenarios` は必須です。次のフィールドは任意で、存在するものだけを評価します。

| フィールド | 用途 |
| --- | --- |
| `stt_samples` | `reference_transcript` と `recognized_transcript`。WER は `reference_tokens` / `recognized_tokens` も必須。 |
| `tts_samples` | 生成音声を独立 STT で再認識した同形式のデータ。音声の明瞭性を CER/WER で評価。 |
| `latencies_ms` | `end_to_end`, `stt`, `end_of_utterance`, `llm_ttft`, `tts_ttfa`, `tts_ttfb`, `tool`, `network` の数値または数値配列。すべて単調時計で測る。 |
| `turn_samples` | 発話終了・初回音声・割り込み検出・停止の各 ms 時刻と、明示的なアノテーション。 |
| `task` | `eligible` と `completed`。最終 DB 状態等で確定した値を入れる。 |
| `tools` | `expected` / `actual`、各呼び出しの `name` / `arguments` / `status`、必要なら allow/deny list と承認情報。 |
| `conversation` | Judge 実行時の `input`, `actual_output`, 任意の `expected_output`, `expected_outcome`, `retrieval_context`。 |
| `reliability`, `usage` | 成功・エラー・タイムアウト・リカバリ、および実測 `cost_usd`。 |

## 指標と判定方法

| 分類 | 指標 | 計算・データ要件 |
| --- | --- | --- |
| STT | CER micro/macro、WER micro/macro | NFKC + 空白削除のみの保守的正規化。CER は文字編集距離。WER はデータセットで固定済みのトークン配列がある時だけ計算。 |
| 重要情報 | Entity precision / recall / F1 / critical entity error | 型と値の完全一致。`critical: true` の未認識を重大エラーとして独立表示。 |
| 遅延 | mean / P50 / P95 / P99 / max | E2E と各コンポーネントを混同せず ms の原値を出力。パーセンタイルは線形補間。 |
| ターン制御 | early response、false EOT/interruption、overlap、barge-in、silence | タイムスタンプと明示アノテーションがある場合のみ。推測しない。 |
| タスク・ツール | task completion、tool selection F1、argument accuracy、execution success、不要呼出 | 期待呼出、実行ログ、最終状態の構造化比較。 |
| 安全 | approval violation、false success claim、ToolPermissionMetric | 未承認の外部操作と、失敗を成功と伝えたケースは 0 が必須閾値の重大ゲート。 |
| TTS | independent-STT CER/WER | 出力音声を**独立した STT**で再認識した結果を `tts_samples` に入れる。波形がないログだけで音声品質を採点しない。 |
| 品質/RAG | AnswerRelevancy、TaskCompletion、Faithfulness、ContextualRelevancy | `--deepeval-judge` 時の DeepEval 標準 Metric。判定モデル、プロンプト、データセット版を結果と実行記録に残して比較する。 |

`VoiceNaturalnessMetric`、`SpeechIntelligibilityMetric`、`VoiceConsistencyMetric`、`AudioIntegrityMetric`、`AudioGlitchMetric`、`TurnTakingNaturalnessMetric`、`AgentResponsivenessMetric` は DeepEval 4.3.4 の標準 Metric として実装済みです。実行するには、各シナリオの `voice_turns` に `role`、`content`、`audio_path`、必要に応じて `start_time_seconds` / `duration_seconds` を入れます。波形・音声 URL がない現行トレースでは、これらは `N/A` となります。音声ログだけからスコアを捏造することはありません。`AudioGlitchMetric` は Judge モデルも必要です。

## テストの分離

```powershell
uv run pytest tests/test_voice_agent_evaluation.py -q
```

これは固定イベントを用いたオフライン決定論的テストです。実音声ストリーム、外部 STT/TTS、LiveKit 接続、Judge API を使うケースは CI の通常テストと分離し、実行回数・音声条件・モデル版を固定してください。

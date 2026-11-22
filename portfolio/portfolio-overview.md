# Care Support Voice Agent — ポートフォリオ技術解説・開発履歴

> **対象範囲**: 本ドキュメントは `development plan/roadmap.md` および Git コミット履歴・各種設計資料に基づき、現時点で実装・検証済みの **Level 0 〜 Level 4** および **TEST-秘書モード（ローカル評価検証用）** の範囲をまとめています（未着手の **Level 3B の GCP 移行** は今後の展望としています）。  
> **最終更新日**: 2026-11-22（TEST-秘書モード + DeepEval/Langfuse 手動評価基盤追加）

---

## 1. プロジェクト概要

**Care Support Voice Agent** は、介護支援などの対話業務を想定した **リアルタイム音声・テキスト対応 AI エージェント** の機能検証プロジェクトです。

単なる「LLM と会話できるチャットボット」にとどまらず、実運用で必須となる以下の4つの柱をローカル環境から段階的に設計・実装・計測しています。

1. **安全制御（Human-in-the-Loop）**: Gmail などの外部操作は AI の判断だけで実行せず、必ずブラウザ UI 上で人間の明示的な承認を経てから実行する。
2. **オブザーバビリティ（監視と改善サイクル）**: OpenTelemetry + Langfuse で全会話・ツール実行・メモリ・RAG のレイテンシやコストを可視化し、実データに基づいて継続的に改善する。
3. **長期記憶（Agent Memory）**: セッションをまたいでユーザーの好み・習慣・基本情報を PostgreSQL + pgvector に記憶・統合し、次回以降の会話に自然に活かす。
4. **ローカル文書検索（RAG）**: PDF / TXT / Markdown の業務文書をベクトル検索し、根拠に基づいた回答を行う。

---

## 2. システムアーキテクチャと技術スタック

### 全体構成図

```text
ブラウザ UI (fronted-test: React + TypeScript + Vite + assistant-ui + Vercel AI SDK)
   │
   ├─ POST /api/token ──► Token Server (FastAPI / Uvicorn)
   │
   └─ WebRTC / DataChannel / RPC ──► LiveKit Cloud
                                          │
                                          ▼
                             LiveKit Agent (Test-LiveKit: Python 3.11 / asyncio)
                              ├─ LLM ──────────► OpenRouter (openai/gpt-6-luna)
                              ├─ STT/TTS/VAD ──► LiveKit Inference (音声モード時)
                              ├─ 外部ツール ───► Gmail API (OAuth 2.0 + 承認フロー必須)
                              ├─ 長期記憶 ─────► PostgreSQL + pgvector + Ollama (Level 2)
                              ├─ 文書検索(RAG) ► PostgreSQL + pgvector + Ollama (Level 3A)
                              └─ 監視・計測 ───► OpenTelemetry ──► Langfuse v4 (OTLP)
```

### 採用技術一覧

| レイヤー | 採用技術 | 役割・選定理由 |
| --- | --- | --- |
| **フロントエンド** | React 19, TypeScript, Vite, `livekit-client`, `@assistant-ui/react`, `@ai-sdk/react`, AI Elements (`ChainOfThought` / `@radix-ui/react-collapsible`) | リアルタイム文字起こし、承認 UI、および開閉可能な処理進捗表示を構築。音声処理は LiveKit 側に任せ、UI は表示と承認操作に専念 |
| **リアルタイム基盤** | LiveKit Cloud, LiveKit Agents (Python), LiveKit Inference | 低遅延な WebRTC 音声通信、STT/TTS/VAD、およびエージェントのターン制御 |
| **トークン発行 API** | FastAPI, Uvicorn | ブラウザ参加者用の短命 LiveKit トークンを発行（秘密鍵をブラウザに渡さない設計） |
| **LLM** | OpenRouter (`openai/gpt-6-luna`) | モデル差し替えの容易さと、`livekit-plugins-openai` の自動 Prompt Caching 対応 |
| **外部ツール連携** | Gmail API (Google OAuth 2.0), Tavily Search API | メール操作および Web 検索（いずれも `ApprovalManager` の承認ゲート経由） |
| **データベース / 検索** | PostgreSQL, `pgvector` (HNSW), SQLAlchemy 2.x (async), `psycopg` 3, Alembic | 会話履歴・長期記憶・RAG チャンクを単一 DB で管理し、スキーマをマイグレーションで版管理 |
| **埋め込みモデル** | Ollama (`embeddinggemma-2:270m`, 768次元) | ローカル環境で完結する高速・低コストな日本語ベクトル生成 |
| **監視・評価** | OpenTelemetry, Langfuse v4, `pytest`, `vitest` | レイテンシ・トークン・コスト・エラーの定量観測と、自動テストによる回帰防止 |
| **デプロイ構成（検証用）** | Cloudflare Workers + Containers, GitHub Actions | クラウド公開用パイプラインを構築済み（現在はローカル検証優先のため自動デプロイを停止し構成を保持） |

---

## 3. 段階別ロードマップと実装内容（Level 0 〜 Level 3A）

`development plan/roadmap.md` に基づき、機能追加と検証を段階的に進めています。

### Level 0: ツール制御・システムプロンプト・監視
- **Human-in-the-Loop 承認フロー（`approvals.py` / `fronted-test/src/approvals.ts`）**:
  - Gmail の検索・読み取り・送信はすべて承認対象。
  - バックエンド側で「実行ID・引数・有効期限（TTL 120秒）・フィンガープリント（SHA-256）・状態」を管理し、認証済み LiveKit RPC 経由でのみ許可／拒否を受理する。
  - 引数改ざんの無効化、拒否・期限切れ・切断時の未実行保証、重複リクエストによる二重送信防止を実装。
- **システムプロンプトの版管理（`prompt_config.py` / `prompts/`）**:
  - プロンプトをコードから分離して Git で版管理し、バージョン番号と SHA-256 ハッシュを Langfuse トレースへ自動紐付け。
  - 会話方針として「最大3文」「不足情報の最初の確認」「不明時は推測せず伝える」を定義。
- **Langfuse オブザーバビリティ（`observability.py` / `trace_export.py` / `session_monitor.py`）**:
  - OpenTelemetry OTLP 経由で Langfuse v4 へ送信。
  - デフォルトで PII（会話本文・メール本文）を外部送信しない `content_policy: redacted` を採用。
  - Langfuse v4 Observations API v2 を使ってセッション単位のトレースをローカル JSON に出力する `export_langfuse_session.py` を整備。

### Level 1: チャット形式の文字起こし UI
- `fronted-test` を Vite + React + TypeScript 構成へ拡張し、`assistant-ui` と Vercel AI SDK UI を導入。
- テキスト専用セッション（`frontend-test-text-*`）と音声専用セッションを明確に分離し、テキスト検証時に不要な STT/TTS が動かない構成を実現。
- 途中認識の逐次更新、確定発言の履歴化、割り込み（interrupted）状態の区別に対応。

### Level 2: PostgreSQL による Agent Memory（長期記憶）
- **フレームワーク非依存・クラウド移行対応の抽象設計**:
  - `BaseMemoryService` / `BaseEmbeddingProvider` / `BaseMemoryRepository` を定義し、将来の GCP Memory Bank / Cloud SQL 移行時に差し替え可能な構造を採用。
- **記憶のライフサイクル**:
  - **セッション開始時**: 直近の記憶（最大5件）をシステムプロンプトへ自動注入。
  - **会話中**: ユーザーの明示的な依頼時のみ `search_memories`（ベクトル検索）、`list_recent_memories`（一覧）、`save_memory`（即時保存）を呼び出し。
  - **セッション終了時**: バックグラウンドワーカー（`workers/memory_worker.py`）が会話から LLM Structured Output + Pydantic 検証で記憶候補を抽出し、既存記憶と比較して `ADD` / `UPDATE` / `DELETE` / `NOOP` を自動統合。
- **耐障害性**: DB 接続障害時にもフォールバック応答を返し、基本会話を止めない設計。

### Level 3A: ローカル RAG 基盤（文書検索）
- **取り込みパイプライン（`rag/`）**:
  - `.pdf`（`pypdf`）、`.txt` / `.md` / `.markdown` をパースし、日本語区切り文字対応の `RecursiveCharacterTextSplitter` でチャンク分割。
  - `OllamaEmbeddingProvider`（`embeddinggemma-2:270m`, 768次元）でベクトル化し、単一トランザクションで `rag_documents` + `rag_chunks`（HNSW コサインインデックス）に原子的に保存。
  - `(corpus_id, file_hash)` による重複取り込み防止と、文書更新・削除（`ON DELETE CASCADE`）に対応。
- **検索と評価**:
  - LiveKit ツール `search_documents` としてエージェントへ統合。
  - `scripts/evaluate_rag.py` およびテスト用日本語 PDF フィクスチャにより、検索精度・レイテンシ（埋め込み時間 / DB 検索時間）を定量評価可能にした。

### Level 3B: Web 検索（Tavily）
- **採用理由**: OpenAI Responses API のサーバーサイド `WebSearch` は自動実行されるため承認フローを挟めない一方、**Tavily** は業界で幅広く利用されており検索品質が高く、REST API 経由で `ApprovalManager`（Human-in-the-Loop）と組み合わせられるため採用。
- **実装内容（`web_search_tools.py` / `fronted-test/src/approvals.ts`）**:
  - `TAVILY_API_KEY` 設定時に `search_web` ツールを有効化し、実行前に必ずブラウザ承認 UI で許可を取得。
  - ローカル文書検索（`search_documents`）と使い分け、1セッションあたりの検索回数上限（既定5回）・タイムアウト（10秒）・結果件数上限（5件）を制御。
  - 検索結果（`url`, `fetched_at`）および失敗時の `error_type` を OpenTelemetry スパン（`web_search.tavily`）へ記録（API キーや本文 PII は非露出）。

### Level 4: ストリーミング進捗表示（Vercel AI SDK + AI Elements）
- **バックエンド進捗イベント配信（`agent.py` / `transcript_events.py` / `memory_tools.py` / `rag/livekit_adapter.py`）**:
  - LiveKit の `agent_state_changed`（`thinking` → 「文章を考え中…」、`speaking` → 「回答中…」）および各ツール（`web_search`: 「Web を検索中…」、`rag`: 「ローカル文書を検索中…」、`memory`: 「記憶を検索／確認／保存中…」、Gmail: 承認待ち〜実行中〜完了）の状態遷移を `agent_status_event` としてリアルタイム配信。
- **AI Elements による開閉可能な進捗パネル（`fronted-test/src/components/ai-elements/chain-of-thought.tsx` / `App.tsx` / `protocol.ts`）**:
  - Vercel AI Elements の `ChainOfThought` パターン（`@radix-ui/react-collapsible` + `lucide-react`）を導入し、処理ステップの一覧をワンクリックで開閉可能に実装。
  - 各ステップの種別アイコン、独自進捗ステータスバッジ（`実行中` / `承認待ち` / `完了` / `失敗` / `拒否` / `キャンセル`）、取得件数などの詳細を表示。
  - セッション終了・切断時には `finalizeActiveStatusEvents()` により未完了の進行中ステータスを自動で `cancelled` へ収束させ、「実行中」のまま残る問題を防止。

### TEST-秘書モード（ローカル評価検証用仮用途）
- **社員照合とセッション紐付け（`token_server.py` / `fronted-test/src/App.tsx`）**:
  - フロントエンドのセッション種別から `TEST-秘書モード（音声・社員照合）`（または `VITE_DEFAULT_SESSION_MODE=secretary`）を選択すると、氏名・社員ID入力画面を表示。
  - FastAPI の `POST /api/secretary/verify` で PostgreSQL の `secretary_employees` と照合し、一致時のみ `POST /api/token`（`mode="secretary"`）で `frontend-test-secretary-*` ルーム用の LiveKit トークンを発行。
  - 確定した `employee_id` はサーバー署名付き JWT の `metadata` に埋め込み、エージェント側（`agent.py`）はブラウザ指定の `user_id` ではなく JWT `metadata` の社員のみを参照。
- **PostgreSQL テーブルと読み取り専用秘書ツール（`database/models.py` / `migrations/versions/0003_secretary_schema.py` / `secretary/`）**:
  - `secretary_employees`、`secretary_events`（会議・作業予定）、`secretary_tasks`（期限付きタスク）を Alembic で管理。
  - `secretary/seed.py` により架空社員2名（`EMP-1001` 佐藤 花子 / `EMP-1002` 鈴木 太郎）を冪等に投入可能（同日同時刻の別予定・片方のみの当日締切タスク・0件の日を含む）。
  - ツールは `get_schedule` / `get_tasks`（JST基準・本人限定・0件とDBエラーを区別）に限定し、専用プロンプト（`prompts/secretary_v1.txt`）で動作。
- **DeepEval + Langfuse 手動評価 CLI（`evaluations/evaluate_secretary.py` / `evaluations/secretary_cases.json`）**:
  - 通話の確定発話をローカル（`evaluations/transcripts/`、Git 除外）へ順序保持で保存し、`LANGFUSE_ALLOW_PII=false` を維持。
  - **固定ケース評価（`--mode case`）**: 2指標（`GEval` 最終回答正確性、`ConversationalGEval` 途中訂正追従※訂正なしケースは対象外）で採点。
  - **会話全体評価（`--mode conversation`）**: 質問を固定せず複数ターンの自由な会話全体を `ConversationalGEval` の6指標（`TaskCompletion` / `ContextRetention` / `VoiceUX` / `SafetyBoundary` / `TurnTakingAndFillers`＝つなぎ言葉・途中区切り割り込み検証 / `LanguageAdaptation`＝ユーザー言語に合わせた言語切り替え検証）で採点（`--employee-id` 指定時はシードの予定・タスクを事実照合用 `context` として自動付与）。
  - Langfuse 対象トレースへ PII を含まない判定スコアとメタデータ（`case_id`, `eval_config_version`, `judge_model_id`）を登録。

#### TEST-秘書モード 再現コマンド
```powershell
# 1. DB マイグレーション & 冪等シード投入
uv --directory Test-LiveKit run alembic upgrade head
uv --directory Test-LiveKit run python -m secretary.seed

# 2. 起動（3ターミナル）
uv --directory Test-LiveKit run agent.py dev
uv --directory Test-LiveKit run uvicorn token_server:app --host 127.0.0.1 --port 8000
npm --prefix fronted-test run dev

# 3. DeepEval 手動採点（固定ケース / 会話全体） & Langfuse スコア登録
uv --directory Test-LiveKit run python -m evaluations.evaluate_secretary --case-id SEC-03 --session-id <SESSION_ID>
uv --directory Test-LiveKit run python -m evaluations.evaluate_secretary --mode conversation --employee-id EMP-1001 --session-id <SESSION_ID>
```

---

## 4. 開発履歴（Git コミット履歴ベース）

| 日付 | 主なコミット | 開発マイルストーン |
| --- | --- | --- |
| **2026-11-16** | `2af9421`, `c0fb22f` | LiveKit + OpenRouter の最小コンソールサンプル構築、テキスト専用モード追加 |
| **2026-11-17** | `a6b123d`, `c472557`, `a98d15a`, `d5df061`, `1f7e22a` | ブラウザ音声 UI＆Token Server 追加、Gmail OAuth ツール実装、Langfuse トレーシング導入、Cloudflare Containers パイプライン構築、開発ロードマップ初版策定 |
| **2026-11-18** | `8af6ba3`, `2e0d306` | `assistant-ui` + Vercel AI SDK 採用方針の確定、ローカル開発優先への方針整理 |
| **2026-11-19〜20** | `88b5db1`, `8189726`, `2ea3b53` | Level 0（承認 UI・プロンプト版管理・監視）と Level 1（チャット UI）実装、テキスト/音声セッションモード分離 |
| **2026-11-20** | `00deaca`, `4e5472b`, `e88555b` | Level 2 Agent Memory 基盤実装＆トレーシング統合、Level 3A ローカル RAG 基盤実装 |
| **2026-11-21** | `32d1828` | RAG 評価手法・評価スクリプト整備 |
| **2026-11-21** | `442c921`, `3c4ff07`, `d7f8293` | 実会話の Langfuse JSON 解析に基づく障害修正・機能強化・モデル最適化（詳細は次章） |

---

## 5. 実運用トレースに基づく問題発見と修正の実行記録

本プロジェクトでは、**「動かして終わり」にせず、Langfuse からエクスポートした実会話 JSON を解析して問題を発見→修正→再計測で効果を確認する** サイクルを回しました。

### サイクル 1: 重大エラー・コスト未計測・承認詰まりの解消（コミット `442c921`）

| 発見した問題（Langfuse JSON 解析結果） | 原因 | 実施した修正 | 検証結果（再計測） |
| --- | --- | --- | --- |
| **PostgreSQL 関連処理が全セッションで `ERROR`**（`memory.*`, `rag.*` がすべて失敗） | Windows 環境の既定 `ProactorEventLoop` が `psycopg` 3 非同期モードと非互換 | `agent.py` 読み込み時に `WindowsSelectorEventLoopPolicy()` を適用 | `ERROR` 件数 **6件 → 0件**。メモリ抽出・RAG 検索が正常動作 |
| **全セッションで `total_cost: 0.0`** | `OBSERVABILITY_PRICES_FILE` 未設定により価格表が空 | `prices.json` を整備し `.env` で指定、`observability.py` の単価表も更新 | セッション単価（例: `0.0387 USD`）が自動算出されるように改善 |
| **`read_email` 並列実行時に 4件が約 111秒待機後に失敗** | 承認 UI が 1件ずつしか表示せず、残りの待機件数がユーザーに見えなかった | `approvals.py` の `snapshot()` に `pending_count` を追加し、UI 側で残り件数を明示 | 複数件の承認待ちをユーザーが把握可能に |
| **サービス名不整合とツール失敗の不可視** | `TracerProvider()` の `Resource` 未指定、`lk.function_tool.is_error` が `DEFAULT` レベル扱い | `Resource({"service.name": "care-support-voice-agent"})` 設定、`is_error`/`expired`/`cancelled` を `ERROR` レベル化 | `resourceAttributes.service.name` 統一、ツール失敗が Langfuse 上で即判別可能に |

### サイクル 2: 会話中の「記憶保存機能がない」誤回答の解消（コミット `3c4ff07`）

- **発見した問題**: DB への自動抽出・保存（終了時）は正常に動いていたにもかかわらず、ユーザーが会話中に「覚えておいて」と頼むとエージェントが「保存機能がない」と回答。
- **原因**: `MemoryTools` が読み取り専用ツール（`search_memories` / `list_recent_memories`）のみで、プロンプトにも自動保存の説明がなかったため。
- **実施した修正**:
  1. `MemoryTools` に即時保存ツール `save_memory`（`BaseMemoryService.add_memory()` 呼び出し）を追加。
  2. システムプロンプトに「終了時の自動抽出・保存」と「明示的依頼時の `save_memory` 利用ルール」を明記。

### サイクル 3: レイテンシ・コスト・トレース品質のさらなる最適化（コミット `d7f8293`）

| 発見した小さな問題（直近5セッション解析） | 実施した修正 |
| --- | --- |
| 初回接続時に `psycopg.types.net` の遅延インポートで **イベントループが 120ms ブロック**（`event_loop_blocked`） | `agent.py` モジュール読み込み時に `psycopg.types.net` を事前インポート |
| 承認キュー待機中に後ろの操作の **TTL（120秒）が同時消費されて期限切れ** | 先頭操作の `decide()` 完了時に次キューの `deadline` / `expires_at` をリフレッシュ |
| `memory.prompt_injection` 等が `agent_session` より先に送信され **親スパンがリンク切れ** | `setup_langfuse()` 時点の未エクスポート親 ID を検知し、`ReportingExporter` で孤立親を補正 |
| `memory.llm.extraction` / `consolidation` の **LLM コストが `total_cost` に未計上** | `trace_export.py` の対象を `llm_request` 限定から全 `generation` スパンへ拡張 |
| 全セッションで **Prompt Caching が `cached=0`**（`livekit-plugins-openai` の自動キャッシュが OpenAI `gpt-5.6+` 系のみ対象） | `OPENROUTER_MODEL` を `anthropic/claude-haiku-5.5` から `openai/gpt-6-luna` へ変更し、`agent.py` に `prompt_cache_key` を設定（README にも理由を明記） |

---

## 6. 今後の展望（次フェーズ）

- **Level 3B（残り）**: 将来の GCP 移行設計（Cloud SQL / Memory Bank / Vertex AI RAG 等）。

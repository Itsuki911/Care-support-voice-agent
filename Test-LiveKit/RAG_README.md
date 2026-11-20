# Level 3: ローカル RAG 基盤（PostgreSQL + pgvector + Ollama）

ローカル PostgreSQL + pgvector + Ollama（`embeddinggemma-2:270m`）上で動作する、フレームワーク非依存・GCP Vertex AI RAG Engine 移行対応の独自 RAG 基盤です。Docker / Docker Compose は使用せず、macOS・Windows 共通の Python コードで動作します。

---

## 1. RAG アーキテクチャとコンポーネント責務

```text
[取り込み時 (Ingestion)]
  Document (PDF / TXT / Markdown)
        │
        ▼
  LocalDocumentParser (pypdf / Python stdlib UTF-8)
        │  テキスト抽出・PDFページ番号取得・SHA-256ハッシュ・空/破損検出
        ▼
  RecursiveTextChunker (langchain-text-splitters)
        │  日本語対応区切り文字で分割・chunk_index/page_number/metadata保持
        ▼
  OllamaEmbeddingProvider (Level 2 再利用 / embeddinggemma-2:270m, 768次元)
        │  バッチ非同期ベクトル化（DB書込前に全件生成して不完全データを防止）
        ▼
  PostgresRAGRepository (SQLAlchemy 2.x async + psycopg 3 + pgvector)
        │  単一トランザクションで rag_documents + rag_chunks を原子的に保存

[検索時 (Retrieval)]
  User Query
        │
        ▼
  OllamaEmbeddingProvider.embed()
        │
        ▼
  RAGRetrieverService -> PostgresRAGRepository.search_similar()
        │  pgvector コサイン類似度 (HNSW) + corpus_id 分離 + 将来メタデータフィルタ
        ▼
  SearchResponse (RetrievalResult[] + embedding_ms / db_search_ms / total_ms)
        │
        ▼
  PostgresRAGService (BaseRAGService) -> Agent / LiveKit RAGTools
```

### Level 2（Agent Memory）との関係
- **再利用コンポーネント**: PostgreSQL、pgvector、SQLAlchemy 2.x、psycopg 3、Alembic、`DatabaseManager`（`database/connection.py`）、`BaseEmbeddingProvider` / `OllamaEmbeddingProvider`（`memory/providers/ollama_embedding.py`）。
- **責務とテーブルの分離**:
  - Level 2（`memory/`）: ユーザー単位の会話履歴・長期記憶（`users`, `conversations`, `memories`, `memory_history`）
  - Level 3（`rag/`）: 外部文書・知識ベース（`rag_corpora`, `rag_documents`, `rag_chunks`）
  - 同一 PostgreSQL インスタンスを共有しますが、サービス・リポジトリ・テーブルは完全に分離されており、Level 2 の既存機能に影響を与えません。

---

## 2. 使用ライブラリ

| ライブラリ | 用途 |
|---|---|
| `pypdf` | PDF からのテキストおよびページ番号抽出 |
| `langchain-text-splitters` | `RecursiveCharacterTextSplitter` によるチャンク分割（LangChain 全体には非依存） |
| `reportlab`（dev） | 日本語テスト用 PDF（`UnicodeCIDFont("HeiseiKakuGo-W5")`）の生成 |
| `psycopg[binary]`, `sqlalchemy[asyncio]`, `alembic`, `pgvector`, `httpx`, `pydantic`, `pytest` | Level 2 からそのまま再利用 |

---

## 3. DB スキーマ（Alembic Migration `0002_rag_schema`）

| テーブル | 役割 | 主なカラム・制約・インデックス |
|---|---|---|
| `rag_corpora` | 文書集合（Corpus）管理 | `id` (PK), `name`, `description`, `metadata` (JSONB), `created_at`, `updated_at` |
| `rag_documents` | 元文書メタデータ・重複防止 | `id` (UUID PK), `corpus_id` (FK CASCADE), `filename`, `file_type`, `file_hash` (SHA-256), `metadata`, `UNIQUE (corpus_id, file_hash)` |
| `rag_chunks` | 分割テキスト・ベクトル格納 | `id` (UUID PK), `document_id` (FK CASCADE), `content`, `chunk_index`, `page_number`, `embedding` (`vector(768)`), `embedding_model`, `embedding_dimension`, `metadata`, `UNIQUE (document_id, chunk_index)`, **HNSW コサインインデックス** (`ix_rag_chunks_embedding_hnsw`) |

マイグレーション適用:
```bash
cd Test-LiveKit
uv run alembic upgrade head
```

---

## 4. Parser / Chunking / Retriever 仕様

- **対応ファイル形式**: `.pdf`（`pypdf`）、`.txt` / `.md` / `.markdown`（Python 標準ライブラリ `UTF-8`）。空文書・0バイト・破損 PDF・非対応拡張子は `DocumentParseError` を送出。
- **Chunking**: `RecursiveCharacterTextSplitter`（デフォルト `RAG_CHUNK_SIZE=450`, `RAG_CHUNK_OVERLAP=80`, 区切り文字 `["\n\n", "\n", "。", "、", " ", ""]`）。環境変数またはコンストラクタ引数で変更可能。
- **重複防止・更新・削除**:
  - `ingest_document()`: `(corpus_id, file_hash)` の一致で重複登録を防止（`status="duplicate"` を返却）。
  - `update_document()`: 同一ファイル名または指定 `document_id` のチャンクを単一トランザクションで原子的に差し替え。
  - `delete_document()`: `ON DELETE CASCADE` で文書と全チャンクを一括削除。
- **Retriever**: コサイン類似度検索（`1 - cosine_distance`）、`top_k`（デフォルト 5 件）、`corpus_id` フィルタ、`embedding_model` 一致保証、将来の `metadata_filter`（JSONB `@>`）拡張フック付き。検索結果には `document_id`, `chunk_id`, `corpus_id`, `content`, `similarity_score`, `filename`, `page_number`, `metadata` および `embedding_ms` / `db_search_ms` / `total_ms` を返却。

---

## 5. RAG Service の使用方法と LiveKit 連携

### Python からの基本利用
```python
from rag.factory import create_rag_runtime

runtime = create_rag_runtime()
try:
    ingested = await runtime.service.ingest_document(
        "tests/fixtures/rag_documents/company_rules.pdf",
        corpus_id="attendance_kb",
    )
    resp = await runtime.service.search(
        "勤務開始時刻は何時ですか？",
        corpus_id="attendance_kb",
        top_k=5,
    )
    for hit in resp.results:
        print(hit.filename, hit.page_number, hit.similarity_score, hit.content[:60])
finally:
    await runtime.close()
```

### LiveKit Agents 連携（`rag/livekit_adapter.py`）
- `RAGTools(rag_service, corpus_id="attendance_kb").search_documents` を LiveKit Agent のツールとして登録可能です。
- `PostgresRAGService.format_results_for_agent()` は取得チャンクを `<retrieved_documents>` で囲み、**外部文書内の命令文をシステム指示として実行しない**プロンプトインジェクション対策フレーミングを付与します。

---

## 6. テスト用ドキュメントと評価データセット

架空の企業「株式会社あおばソリューションズ」の勤怠管理システム「AobaTime」をテーマに、以下の検証データを生成・配置しています。

- **テスト文書**（`tests/fixtures/rag_documents/`）:
  1. `company_rules.pdf`（2 ページ）— 就業時刻・フレックス・休憩・遅刻早退・有給・残業上限
  2. `employee_manual.pdf`（2 ページ）— 出勤/退勤打刻・中抜け休憩・打刻忘れ修正・月次履歴確認
  3. `faq.md` — パスワード再設定・打刻トラブル・承認済みデータ訂正・スマホ二段階認証
  4. `system_guide.txt` — ログイン・画面構成・CSV 出力・エラーコード（`E-101`, `E-204`, `E-310`, `E-503`）
  5. `business_procedures.pdf`（2 ページ）— 管理者日次確認・一次/二次承認フロー・月末締め・ロック解除
- **評価データセット**（`tests/fixtures/rag_evaluation/evaluation_dataset.json`）:
  - 全 **28 クエリ**（正解あり 26 件：完全一致・言い換え・複数文書横断・自然な日本語質問 / 正解なし 2 件：根拠不足検出用）

---

## 7. テスト・評価の実行方法（macOS / Windows 共通）

前提セットアップ（PostgreSQL + pgvector + Ollama `embeddinggemma-2:270m` + `.env`）は [MEMORY_README.md](./MEMORY_README.md) と共通です。

```bash
cd Test-LiveKit

# 1. 依存関係同期 & マイグレーション適用
uv sync
uv run alembic upgrade head

# 2. （再生成したい場合）テスト文書・評価データセットの生成
uv run python scripts/generate_rag_fixtures.py

# 3. 全テスト実行（Level 0〜3 すべて / オフライン時は実 DB 結合テストを自動スキップ）
uv run pytest -q

# 4. テスト文書取り込み + Recall@5 / Latency / 出典整合性 評価の実行
uv run python scripts/evaluate_rag.py --reset
```

評価結果は以下に自動出力されます:
- `tests/fixtures/rag_evaluation/evaluation_report.json`
- `tests/fixtures/rag_evaluation/evaluation_report.md`

---

## 8. Vertex AI RAG Engine への移行方針

- **インターフェース抽象化**: `BaseRAGService`（`rag/interfaces/rag_service.py`）に対して現在は `PostgresRAGService` を実装しています。将来は `VertexRAGEngineService` を新規追加し、`rag/factory.py` で切り替える構成とします。
- **コンポーネント交換性**: `BaseDocumentParser`（Document AI Layout Parser 等）、`BaseTextChunker`（Semantic Chunking 等）、`BaseEmbeddingProvider`（Vertex AI Embeddings 等）、`BaseRAGRepository` はすべて抽象化済みです。
- **移行時の注意点**:
  - Cloud SQL for PostgreSQL と Vertex AI RAG Engine（マネージド Vector DB / Corpus）は別サービスのため、Vertex AI RAG Engine へ完全移行する際は GCS への元文書配置と再取り込み（再インデキシング）が必要です。
  - Vertex AI RAG Engine のレスポンス形式（`RagContexts` 等）は Adapter 層で共通の `SearchResponse` / `RetrievalResult` へ変換し、呼び出し元の Agent コードを変更しない設計とします。

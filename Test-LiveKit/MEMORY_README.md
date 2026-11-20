# Level 2: Agent Memory システム（PostgreSQL + pgvector + Ollama）

LiveKit Agents や特定のクラウドサービスに依存しない、ローカル PostgreSQL + pgvector + Ollama（`embeddinggemma-2:270m`）ベースの Agent Memory システムです。将来の GCP Cloud SQL for PostgreSQL および GCP Agent Platform Memory Bank への移行を見据えた抽象インターフェース設計を採用しています。

> Docker / Docker Compose は使用せず、OS に直接インストールした PostgreSQL と Ollama で動作します。Python コードは macOS / Windows 共通です。

---

## 1. システムアーキテクチャ

```text
LiveKit Agent / 任意クライアント
        │
        ▼
  MemoryManager  (memory/services/memory_manager.py)
        │  ※ BaseMemoryService インターフェース経由
        ▼
  PostgresMemoryService  (将来は GCPMemoryBankService に差し替え可能)
   ├─ MemoryRetrievalService      (memory/services/retrieval.py)
   ├─ MemoryExtractionService     (memory/services/extraction.py)
   ├─ MemoryConsolidationService  (memory/services/consolidation.py)
   ├─ BaseEmbeddingProvider       ──► OllamaEmbeddingProvider (embeddinggemma-2:270m, 768次元)
   └─ BaseMemoryRepository        ──► PostgresMemoryRepository (SQLAlchemy 2.x + psycopg 3 + pgvector)
                                         └─ PostgreSQL (users / conversations / memories / memory_history)

  MemoryBackgroundWorker (workers/memory_worker.py)
   └─ 音声応答をブロックしない非同期キューで process_conversation() を実行
```

### コンポーネントの責務
| コンポーネント | ファイル | 責務 |
| --- | --- | --- |
| **抽象インターフェース** | `memory/interfaces/` | `BaseMemoryService`・`BaseEmbeddingProvider`・`BaseMemoryRepository` |
| **Memory Manager** | `memory/services/memory_manager.py` | 外部エージェントからの統一エントリーポイント。DB/Embedding 実装を持たず各サービスへ委譲 |
| **Memory Retrieval** | `memory/services/retrieval.py` | クエリの Embedding 生成、user_id と embedding_model 一致による類似検索、Agent 向け整形 |
| **Memory Extraction** | `memory/services/extraction.py`, `memory/providers/llm_extractor.py` | LLM の Structured Output（JSON）＋ Pydantic 検証による長期記憶候補の抽出 |
| **Memory Consolidation** | `memory/services/consolidation.py` | 既存記憶との比較による `ADD` / `UPDATE` / `DELETE` / `NOOP` 判断、重複抑止、ユーザー単位ロック |
| **Memory Repository** | `memory/repositories/postgres_repository.py` | SQLAlchemy 2.x + psycopg 3 による非同期 CRUD・pgvector 類似検索・更新履歴監査 |
| **Background Worker** | `workers/memory_worker.py` | 音声応答パスから切り離した非同期バッチ処理キュー |

---

## 2. Memory の種類と役割

`MemoryType`（`memory/models/memory.py`）で以下を区別します。

- `preference`: ユーザーの好み・要望（例：温かい緑茶が好き、ゆっくり話してほしい）
- `habit`: 習慣・日課（例：毎朝6時に起床して散歩する）
- `profile`: 本人の基本情報
- `interest`: 継続的な関心・趣味
- `event`: 重要な出来事・定期予定
- `topic`: 継続中の話題・関心事
- `fact`: その他の事実情報

> 挨拶・一回限りの依頼・仮定の話・他人の情報・推測に基づく情報は長期記憶として保存しない設計としています。

---

## 3. 使用ライブラリと採用理由

| ライブラリ | 用途・採用理由 |
| --- | --- |
| `psycopg[binary]` (psycopg 3) | 非同期・同期両対応の最新 PostgreSQL ドライバ（macOS / Windows 共通バイナリ配布） |
| `sqlalchemy[asyncio]` (2.x) | 型安全な ORM・非同期セッション管理・トランザクション制御 |
| `alembic` | スキーマ変更と pgvector 拡張・インデックスの版管理 |
| `pgvector` | PostgreSQL の `vector(768)` 型およびコサイン距離演算子（`<=>`）の SQLAlchemy 連携 |
| `pydantic` (v2) | ドメインモデルおよび LLM Structured Output の厳密なバリデーション |
| `httpx` | Ollama `/api/embed` および OpenRouter Chat Completions API への非同期 HTTP 呼び出し |
| `pytest` | 単体テスト（DB/Ollama 不要）およびローカル結合テストの実行 |

---

## 4. DB スキーマ（Alembic 管理）

マイグレーション: `Test-LiveKit/migrations/versions/0001_initial_memory_schema.py`

- **`users`**: `id` (PK), `display_name`, `metadata` (JSONB), `created_at`, `updated_at`
- **`conversations`**: `id` (UUID PK), `user_id` (FK → `users.id`), `session_id`, `role` (`user|assistant|system`), `content`, `created_at`
  - Index: `(user_id, session_id, created_at)`
- **`memories`**: `id` (UUID PK), `user_id` (FK → `users.id`), `content`, `memory_type`, `embedding` (`vector(768)`), `embedding_model`, `embedding_dimension`, `importance` (0.0–1.0), `confidence` (0.0–1.0), `source_session_id`, `version`, `created_at`, `updated_at`, `expires_at`
  - Indexes: HNSW cosine index (`ix_memories_embedding_hnsw`), `(user_id, updated_at)`, `(user_id, embedding_model)`, `(user_id, memory_type)`
- **`memory_history`**: `id` (UUID PK), `memory_id` (FK → `memories.id` `ON DELETE SET NULL`), `user_id` (FK → `users.id`), `action` (`ADD|UPDATE|DELETE`), `previous_content`, `new_content`, `reason`, `source_session_id`, `created_at`

---

## 5. セットアップ手順

### 5.1 macOS（Homebrew）

> 既存の PostgreSQL がポート `5432` で稼働している場合は、既存 DB を停止・破壊せず、別ポート（例: `5433`）を使用してください。

1. **PostgreSQL と pgvector のインストール**
   Homebrew の現行 `pgvector` ボトルは `postgresql@18` / `postgresql@19` を同梱しています（PostgreSQL 17 を使う場合は互換ビルドを用意してください）。
   ```zsh
   brew install postgresql@18 pgvector
   brew services start postgresql@18
   ```
   ※ ポート `5432` が既存 PostgreSQL で使用中の場合は、`/opt/homebrew/var/postgresql@18/postgresql.conf` に `port = 5433` を追記して `brew services restart postgresql@18` を実行します。

2. **データベース作成と pgvector 有効化**
   ```zsh
   /opt/homebrew/opt/postgresql@18/bin/createdb -h 127.0.0.1 -p 5432 care_support
   /opt/homebrew/opt/postgresql@18/bin/createdb -h 127.0.0.1 -p 5432 care_support_test
   /opt/homebrew/opt/postgresql@18/bin/psql -h 127.0.0.1 -p 5432 -d care_support -c "CREATE EXTENSION IF NOT EXISTS vector;"
   /opt/homebrew/opt/postgresql@18/bin/psql -h 127.0.0.1 -p 5432 -d care_support_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
   ```
   （別ポート `5433` の場合は `-p 5433` に読み替えてください。）

3. **Ollama と EmbeddingGemma 2 のセットアップ**
   ```zsh
   ollama pull embeddinggemma-2:270m
   ollama list
   ```

4. **Python 依存関係と Alembic マイグレーション**
   ```zsh
   cd Test-LiveKit
   cp -n .env.example .env
   # .env に DATABASE_URL / TEST_DATABASE_URL / OLLAMA_BASE_URL / EMBEDDING_MODEL 等を設定
   uv sync
   uv run alembic upgrade head
   ```

### 5.2 Windows（PostgreSQL 17 公式インストーラー）

> ※ Windows 環境での実機検証は未実施です。公式配布物に基づく再現手順として記載しています。

1. **PostgreSQL 17 のインストール**
   - [PostgreSQL 公式 Windows インストーラー（EDB）](https://www.postgresql.org/download/windows/) から PostgreSQL 17 をインストールします。
   - インストール時に設定した `postgres` パスワードとポート番号（既定: `5432`）を控えます。
   - `C:\Program Files\PostgreSQL\17\bin` を環境変数 `Path` に追加します。

2. **pgvector のインストール（PostgreSQL 17 向け）**
   - 公式手順（[pgvector GitHub - Windows](https://github.com/pgvector/pgvector#windows)）に従い、Visual Studio C++ Build Tools（x64 Native Tools Command Prompt）でビルド・配置します：
     ```cmd
     set "PGROOT=C:\Program Files\PostgreSQL\17"
     git clone --branch v0.8.7 https://github.com/pgvector/pgvector.git
     cd pgvector
     nmake /F Makefile.win
     nmake /F Makefile.win install
     ```
   - ビルド後、PowerShell から DB 作成と拡張有効化を行います：
     ```powershell
     createdb -U postgres -h 127.0.0.1 -p 5432 care_support
     createdb -U postgres -h 127.0.0.1 -p 5432 care_support_test
     psql -U postgres -h 127.0.0.1 -p 5432 -d care_support -c "CREATE EXTENSION IF NOT EXISTS vector;"
     psql -U postgres -h 127.0.0.1 -p 5432 -d care_support_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
     ```

3. **Windows 版 Ollama と EmbeddingGemma 2**
   - [Ollama 公式 Windows インストーラー](https://ollama.com/download/windows) をインストールし、起動後に以下を実行します：
     ```powershell
     ollama pull embeddinggemma-2:270m
     ```

4. **Python 環境とマイグレーション（macOS と共通）**
   ```powershell
   cd Test-LiveKit
   Copy-Item .env.example .env
   # .env に DATABASE_URL=postgresql+psycopg://postgres:<PASSWORD>@127.0.0.1:5432/care_support 等を設定
   uv sync
   uv run alembic upgrade head
   ```

---

## 6. Memory Manager の利用方法（LiveKit Agents 連携例）

```python
from memory.factory import create_memory_runtime
from memory.models.memory import ConversationMessage
from memory.services.retrieval import MemoryRetrievalService

runtime = create_memory_runtime()
runtime.worker.start()

# 1. 発話応答前に関連記憶を取得（DB停止時でも search_memory_safe は空リストで継続）
memories = await runtime.service.search_memory_safe(user_id="local-user", query="朝の習慣について")
context_block = MemoryRetrievalService.format_for_agent(memories)

# 2. 会話ターン完了後、音声応答をブロックせず非同期キューへ投入
runtime.worker.enqueue_conversation(
    user_id="local-user",
    session_id="session-123",
    messages=[
        ConversationMessage(user_id="local-user", session_id="session-123", role="user", content="毎朝6時に散歩しています"),
        ConversationMessage(user_id="local-user", session_id="session-123", role="assistant", content="毎朝6時の散歩、健康的ですね。"),
    ],
)

# 3. セッション終了時にキューをドレインしてクローズ
await runtime.close()
```

---

## 7. テストと性能測定

### 単体テスト（DB / Ollama / 外部 API 不要、macOS・Windows 共通）
```zsh
cd Test-LiveKit
uv run --locked pytest -q tests/test_retrieval.py tests/test_extraction.py tests/test_consolidation.py tests/test_memory_manager.py
```

### ローカル結合テスト（テスト専用 DB `TEST_DATABASE_URL` + ローカル Ollama 使用）
```zsh
cd Test-LiveKit
uv run --locked pytest -v tests/test_postgres_integration.py
```

### 性能測定（平均・p50・p95）
```zsh
cd Test-LiveKit
# Embedding + PostgreSQL検索 + Retrieval全体のみ
uv run python scripts/benchmark_memory.py --iterations 15

# LLMによる Extraction / Consolidation も含めて計測
uv run python scripts/benchmark_memory.py --iterations 15 --with-llm
```

---

## 8. GCP 移行時の変更箇所

| レイヤー | 現在（Level 2 ローカル） | 将来（GCP 移行後） | 変更範囲 |
| --- | --- | --- | --- |
| **会話履歴・業務データ** | ローカル PostgreSQL | **Cloud SQL for PostgreSQL** | `DATABASE_URL` の差し替えのみ（SQLAlchemy + psycopg 3 + Alembic はそのまま利用可能） |
| **長期記憶サービス** | `PostgresMemoryService` | **`GCPMemoryBankService`** | `BaseMemoryService`（`memory/interfaces/memory_service.py`）の新規実装クラスを追加し、`memory/factory.py` で切り替え |
| **Memory Manager / Agent 側** | `MemoryManager(BaseMemoryService)` | 変更不要 | `MemoryManager` および LiveKit Agent 側の呼び出しコードはインターフェース依存のため無修正 |
| **Embedding モデル変更時** | `embeddinggemma-2:270m` (768次元) | 任意モデル | `memories.embedding_model` と `embedding_dimension` を保持しているため、モデル変更時は既存レコードの再 Embedding バッチを実行 |

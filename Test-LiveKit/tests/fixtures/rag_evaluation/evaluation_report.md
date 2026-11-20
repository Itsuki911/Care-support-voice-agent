# Level 3 RAG 検索評価レポート

- 実行日時 (UTC): `2026-11-20T13:51:05.250026+00:00`
- Corpus: `rag_eval_attendance`
- Embedding Model: `embeddinggemma-2:270m` (768 次元)
- Chunking: `chunk_size=450`, `chunk_overlap=80`
- Top-K: `5`

## 1. 取り込み文書一覧

| ファイル名 | 形式 | Chunk数 | ステータス |
|---|---|---:|---|
| `business_procedures.pdf` | `pdf` | 4 | `duplicate` |
| `company_rules.pdf` | `pdf` | 4 | `duplicate` |
| `employee_manual.pdf` | `pdf` | 4 | `duplicate` |
| `faq.md` | `markdown` | 4 | `duplicate` |
| `system_guide.txt` | `txt` | 5 | `duplicate` |

## 2. 検索精度・出典・遅延（実測値）

- **Document Recall@5**: `96.2%` (25/26)
- **Chunk Recall@5** (キーワード根拠一致): `96.2%` (25/26)
- **PDF ページ番号一致率@5**: `100.0%` (16/16)
- **出典情報整合率** (`document_id`, `chunk_id`, `filename`, PDF `page_number`): `100.0%` (140/140)
- **正解あり質問の Top-1 類似度平均**: `0.8179`
- **正解なし質問の Top-1 類似度平均**: `0.6929`（閾値 `0.72` 未満で根拠不足検出: 2/2）

### Retrieval Latency (ms)

| 計測項目 | 平均 (mean) | p50 | p95 | 最小 / 最大 |
|---|---:|---:|---:|---:|
| Embedding 生成 | `43.318 ms` | `42.59 ms` | `52.084 ms` | `35.034` / `54.337 ms` |
| PostgreSQL Vector Search | `4.83 ms` | `4.42 ms` | `7.004 ms` | `3.413` / `10.423 ms` |
| **Retrieval 合計** | **`48.148 ms`** | **`47.942 ms`** | **`56.306 ms`** | `39.439` / `58.316 ms` |

## 3. クエリ別結果

| ID | カテゴリ | 正解文書 | Doc@5 | Chunk@5 | Top-1 Score | 合計(ms) |
|---|---|---|---:|---:|---:|---:|
| `q01` | `exact_match` | `company_rules.pdf` | OK | OK | `0.8014` | `50.533` |
| `q02` | `exact_match` | `company_rules.pdf` | OK | OK | `0.7985` | `56.306` |
| `q03` | `paraphrase` | `company_rules.pdf` | OK | OK | `0.7857` | `52.791` |
| `q04` | `natural_japanese` | `company_rules.pdf` | OK | OK | `0.8207` | `52.672` |
| `q05` | `exact_match` | `company_rules.pdf` | OK | OK | `0.8465` | `44.565` |
| `q06` | `paraphrase` | `company_rules.pdf` | OK | OK | `0.8148` | `49.025` |
| `q07` | `natural_japanese` | `company_rules.pdf` | OK | OK | `0.8581` | `51.684` |
| `q08` | `natural_japanese` | `employee_manual.pdf` | OK | OK | `0.8044` | `43.982` |
| `q09` | `paraphrase` | `employee_manual.pdf` | OK | OK | `0.8519` | `46.518` |
| `q10` | `exact_match` | `employee_manual.pdf` | OK | OK | `0.8011` | `48.61` |
| `q11` | `paraphrase` | `employee_manual.pdf` | OK | OK | `0.7766` | `52.065` |
| `q12` | `exact_match` | `employee_manual.pdf` | OK | OK | `0.8641` | `46.745` |
| `q13` | `exact_match` | `faq.md` | OK | OK | `0.8287` | `48.124` |
| `q14` | `natural_japanese` | `faq.md` | OK | OK | `0.7823` | `43.215` |
| `q15` | `exact_match` | `faq.md` | OK | OK | `0.8313` | `47.253` |
| `q16` | `cross_document` | `faq.md` | OK | OK | `0.8664` | `52.837` |
| `q17` | `natural_japanese` | `faq.md` | OK | OK | `0.8189` | `58.316` |
| `q18` | `natural_japanese` | `system_guide.txt` | OK | OK | `0.8342` | `46.381` |
| `q19` | `paraphrase` | `system_guide.txt` | MISS | MISS | `0.7735` | `47.76` |
| `q20` | `natural_japanese` | `system_guide.txt` | OK | OK | `0.8504` | `50.448` |
| `q21` | `exact_match` | `system_guide.txt` | OK | OK | `0.8050` | `49.222` |
| `q22` | `exact_match` | `system_guide.txt` | OK | OK | `0.8017` | `55.074` |
| `q23` | `cross_document` | `business_procedures.pdf` | OK | OK | `0.7543` | `46.344` |
| `q24` | `natural_japanese` | `business_procedures.pdf` | OK | OK | `0.8346` | `40.471` |
| `q25` | `exact_match` | `business_procedures.pdf` | OK | OK | `0.8300` | `45.94` |
| `q26` | `cross_document` | `business_procedures.pdf` | OK | OK | `0.8315` | `39.52` |
| `q27` | `unanswerable` | `(なし)` | — | 根拠不足検出 | `0.6866` | `42.291` |
| `q28` | `unanswerable` | `(なし)` | — | 根拠不足検出 | `0.6992` | `39.439` |

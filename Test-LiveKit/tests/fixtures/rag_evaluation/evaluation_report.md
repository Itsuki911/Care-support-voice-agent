# Level 3 RAG 検索評価レポート

- 実行日時 (UTC): `2026-11-21T07:33:35.943181+00:00`
- Corpus: `local_test_docs`
- Embedding Model: `embeddinggemma-2:270m` (768 次元)
- Chunking: `chunk_size=450`, `chunk_overlap=80`
- Top-K: `5`

## 1. 取り込み文書一覧

| ファイル名 | 形式 | Chunk数 | ステータス |
|---|---|---:|---|
| `business_procedures.pdf` | `pdf` | 4 | `ingested` |
| `company_rules.pdf` | `pdf` | 4 | `ingested` |
| `employee_manual.pdf` | `pdf` | 4 | `ingested` |
| `faq.md` | `markdown` | 4 | `ingested` |
| `system_guide.txt` | `txt` | 4 | `ingested` |

## 2. 検索精度・出典・遅延（実測値）

- **Document Recall@5**: `100.0%` (26/26)
- **Chunk Recall@5** (キーワード根拠一致): `96.2%` (25/26)
- **PDF ページ番号一致率@5**: `100.0%` (16/16)
- **出典情報整合率** (`document_id`, `chunk_id`, `filename`, PDF `page_number`): `100.0%` (140/140)
- **正解あり質問の Top-1 類似度平均**: `0.8110`
- **正解なし質問の Top-1 類似度平均**: `0.6913`（閾値 `0.72` 未満で根拠不足検出: 2/2）

### Retrieval Latency (ms)

| 計測項目 | 平均 (mean) | p50 | p95 | 最小 / 最大 |
|---|---:|---:|---:|---:|
| Embedding 生成 | `36.76 ms` | `36.712 ms` | `39.492 ms` | `33.919` / `39.822 ms` |
| PostgreSQL Vector Search | `5.953 ms` | `4.792 ms` | `10.451 ms` | `4.12` / `12.553 ms` |
| **Retrieval 合計** | **`42.713 ms`** | **`42.255 ms`** | **`48.373 ms`** | `38.372` / `51.713 ms` |

## 3. クエリ別結果

| ID | カテゴリ | 正解文書 | Doc@5 | Chunk@5 | Top-1 Score | 合計(ms) |
|---|---|---|---:|---:|---:|---:|
| `q01` | `exact_match` | `company_rules.pdf` | OK | OK | `0.8052` | `40.752` |
| `q02` | `exact_match` | `company_rules.pdf` | OK | OK | `0.8062` | `42.98` |
| `q03` | `paraphrase` | `company_rules.pdf` | OK | OK | `0.7783` | `46.664` |
| `q04` | `natural_japanese` | `company_rules.pdf` | OK | OK | `0.8185` | `44.025` |
| `q05` | `exact_match` | `company_rules.pdf` | OK | OK | `0.8409` | `38.906` |
| `q06` | `paraphrase` | `company_rules.pdf` | OK | OK | `0.8157` | `41.992` |
| `q07` | `natural_japanese` | `company_rules.pdf` | OK | OK | `0.8529` | `39.916` |
| `q08` | `natural_japanese` | `employee_manual.pdf` | OK | OK | `0.8127` | `51.713` |
| `q09` | `paraphrase` | `employee_manual.pdf` | OK | OK | `0.8487` | `42.617` |
| `q10` | `exact_match` | `employee_manual.pdf` | OK | OK | `0.7914` | `40.587` |
| `q11` | `paraphrase` | `employee_manual.pdf` | OK | OK | `0.7531` | `44.734` |
| `q12` | `exact_match` | `employee_manual.pdf` | OK | OK | `0.8694` | `43.214` |
| `q13` | `exact_match` | `faq.md` | OK | OK | `0.7820` | `48.373` |
| `q14` | `natural_japanese` | `faq.md` | OK | OK | `0.7480` | `38.372` |
| `q15` | `exact_match` | `faq.md` | OK | OK | `0.8314` | `41.064` |
| `q16` | `cross_document` | `faq.md` | OK | OK | `0.8265` | `42.518` |
| `q17` | `natural_japanese` | `faq.md` | OK | OK | `0.8132` | `41.047` |
| `q18` | `natural_japanese` | `system_guide.txt` | OK | OK | `0.8358` | `46.407` |
| `q19` | `paraphrase` | `system_guide.txt` | OK | MISS | `0.7600` | `39.23` |
| `q20` | `natural_japanese` | `system_guide.txt` | OK | OK | `0.8207` | `40.947` |
| `q21` | `exact_match` | `system_guide.txt` | OK | OK | `0.7931` | `40.463` |
| `q22` | `exact_match` | `system_guide.txt` | OK | OK | `0.8116` | `42.535` |
| `q23` | `cross_document` | `business_procedures.pdf` | OK | OK | `0.7638` | `45.412` |
| `q24` | `natural_japanese` | `business_procedures.pdf` | OK | OK | `0.8320` | `38.432` |
| `q25` | `exact_match` | `business_procedures.pdf` | OK | OK | `0.8322` | `41.705` |
| `q26` | `cross_document` | `business_procedures.pdf` | OK | OK | `0.8425` | `44.246` |
| `q27` | `unanswerable` | `(なし)` | — | 根拠不足検出 | `0.6902` | `40.659` |
| `q28` | `unanswerable` | `(なし)` | — | 根拠不足検出 | `0.6923` | `46.459` |

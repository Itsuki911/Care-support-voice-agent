"""Reproducible Level 3 RAG ingestion & retrieval evaluation script.

Workflow:
1. Ensure test fixtures exist (tests/fixtures/rag_documents/ & rag_evaluation/).
2. Ingest all 5 test documents into a dedicated test corpus (`rag_eval_attendance`).
   - Re-runs are idempotent (duplicate file hash detection; optional `--reset` rebuilds corpus).
3. Run all evaluation queries against PostgreSQL + pgvector + Ollama.
4. Measure:
   - Document-level Recall@5 (separate from Chunk-level Recall@5)
   - Chunk-level Recall@5 (keyword evidence match within top-5 chunks of expected doc)
   - Retrieval Latency (mean / p50 / p95 for total, embedding, and DB vector search)
   - Citation integrity (filename, document_id, chunk_id, page_number for PDFs)
   - Unanswerable query score analysis (insufficient-evidence detection threshold)
5. Save JSON and Markdown reports to tests/fixtures/rag_evaluation/.

Usage:
    cd Test-LiveKit
    uv run python scripts/evaluate_rag.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from rag.factory import RAGSettings, create_rag_runtime

DOCS_DIR = BASE_DIR / "tests" / "fixtures" / "rag_documents"
EVAL_DIR = BASE_DIR / "tests" / "fixtures" / "rag_evaluation"
DATASET_PATH = EVAL_DIR / "evaluation_dataset.json"
REPORT_JSON_PATH = EVAL_DIR / "evaluation_report.json"
REPORT_MD_PATH = EVAL_DIR / "evaluation_report.md"
DEFAULT_EVAL_CORPUS = "rag_eval_attendance"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return round(ordered[idx], 3)


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": round(statistics.mean(values), 3),
        "p50": round(statistics.median(values), 3),
        "p95": _percentile(values, 95),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def _chunk_matches_keywords(content: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    return any(kw in content for kw in keywords)


async def run_evaluation(
    *,
    corpus_id: str = DEFAULT_EVAL_CORPUS,
    top_k: int = 5,
    reset_corpus: bool = False,
    insufficient_threshold: float = 0.72,
) -> dict[str, Any]:
    if not DOCS_DIR.exists() or not DATASET_PATH.exists():
        raise FileNotFoundError(
            "Test fixtures missing. Run `uv run python scripts/generate_rag_fixtures.py` first."
        )

    settings = RAGSettings.from_env()
    runtime = create_rag_runtime(settings)
    try:
        if reset_corpus:
            await runtime.service.delete_corpus(corpus_id)

        ingestion_summary: list[dict[str, Any]] = []
        for path in sorted(DOCS_DIR.iterdir()):
            if not path.is_file() or not runtime.parser.supports(path):
                continue
            res = await runtime.service.ingest_document(path, corpus_id=corpus_id)
            ingestion_summary.append(
                {
                    "filename": res.document.filename,
                    "file_type": res.document.file_type,
                    "document_id": str(res.document.id),
                    "chunk_count": res.chunk_count,
                    "status": res.status,
                }
            )

        dataset: list[dict[str, Any]] = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

        # Warm up Ollama model once so latency stats reflect steady-state retrieval
        await runtime.service.search("勤怠", corpus_id=corpus_id, top_k=1)

        embed_latencies: list[float] = []
        db_latencies: list[float] = []
        total_latencies: list[float] = []

        answerable_total = 0
        doc_hits = 0
        chunk_hits = 0
        page_checked = 0
        page_hits = 0

        unanswerable_total = 0
        unanswerable_top_scores: list[float] = []
        answerable_top_scores: list[float] = []
        unanswerable_flagged = 0

        citation_checks = 0
        citation_valid = 0

        query_details: list[dict[str, Any]] = []

        for item in dataset:
            resp = await runtime.service.search(
                item["query"], corpus_id=corpus_id, top_k=top_k
            )
            embed_latencies.append(resp.embedding_ms)
            db_latencies.append(resp.db_search_ms)
            total_latencies.append(resp.total_ms)

            for r in resp.results:
                citation_checks += 1
                pdf_page_ok = (r.file_type != "pdf") or (
                    r.page_number is not None and r.page_number >= 1
                )
                if r.document_id and r.chunk_id and r.filename and pdf_page_ok:
                    citation_valid += 1

            top_score = round(resp.results[0].similarity_score, 4) if resp.results else 0.0
            returned_docs = [r.filename for r in resp.results]

            if item["answerable"]:
                answerable_total += 1
                answerable_top_scores.append(top_score)
                expected_doc = item["expected_document"]
                expected_page = item.get("expected_page")
                expected_keywords = item.get("expected_keywords", [])

                doc_hit = expected_doc in returned_docs
                if doc_hit:
                    doc_hits += 1

                matching_doc_results = [r for r in resp.results if r.filename == expected_doc]
                chunk_hit = any(
                    _chunk_matches_keywords(r.content, expected_keywords)
                    for r in matching_doc_results
                )
                if chunk_hit:
                    chunk_hits += 1

                page_hit: bool | None = None
                if expected_page is not None:
                    page_checked += 1
                    page_hit = any(r.page_number == expected_page for r in matching_doc_results)
                    if page_hit:
                        page_hits += 1

                query_details.append(
                    {
                        "id": item["id"],
                        "category": item["category"],
                        "query": item["query"],
                        "answerable": True,
                        "expected_document": expected_doc,
                        "expected_page": expected_page,
                        "doc_hit_at_5": doc_hit,
                        "chunk_hit_at_5": chunk_hit,
                        "page_hit_at_5": page_hit,
                        "top_score": top_score,
                        "top_results": [
                            {
                                "filename": r.filename,
                                "page_number": r.page_number,
                                "score": round(r.similarity_score, 4),
                            }
                            for r in resp.results
                        ],
                        "latency_ms": {
                            "embedding": resp.embedding_ms,
                            "db_search": resp.db_search_ms,
                            "total": resp.total_ms,
                        },
                    }
                )
            else:
                unanswerable_total += 1
                unanswerable_top_scores.append(top_score)
                insufficient = top_score < insufficient_threshold
                if insufficient:
                    unanswerable_flagged += 1
                query_details.append(
                    {
                        "id": item["id"],
                        "category": item["category"],
                        "query": item["query"],
                        "answerable": False,
                        "top_score": top_score,
                        "flagged_insufficient_evidence": insufficient,
                        "top_results": [
                            {
                                "filename": r.filename,
                                "page_number": r.page_number,
                                "score": round(r.similarity_score, 4),
                            }
                            for r in resp.results[:3]
                        ],
                        "latency_ms": {
                            "embedding": resp.embedding_ms,
                            "db_search": resp.db_search_ms,
                            "total": resp.total_ms,
                        },
                    }
                )

        report: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "corpus_id": corpus_id,
            "embedding_model": settings.embedding_model,
            "embedding_dimension": settings.embedding_dimension,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "top_k": top_k,
            "ingested_documents": ingestion_summary,
            "metrics": {
                "total_queries": len(dataset),
                "answerable_queries": answerable_total,
                "unanswerable_queries": unanswerable_total,
                "document_recall_at_5": round(doc_hits / answerable_total, 4)
                if answerable_total
                else 0.0,
                "document_hits": doc_hits,
                "chunk_recall_at_5": round(chunk_hits / answerable_total, 4)
                if answerable_total
                else 0.0,
                "chunk_hits": chunk_hits,
                "pdf_page_recall_at_5": round(page_hits / page_checked, 4)
                if page_checked
                else 0.0,
                "pdf_page_hits": page_hits,
                "pdf_page_checked": page_checked,
                "citation_integrity_rate": round(citation_valid / citation_checks, 4)
                if citation_checks
                else 1.0,
                "citation_valid": citation_valid,
                "citation_checked": citation_checks,
                "answerable_top1_score_mean": round(statistics.mean(answerable_top_scores), 4)
                if answerable_top_scores
                else 0.0,
                "unanswerable_top1_score_mean": round(statistics.mean(unanswerable_top_scores), 4)
                if unanswerable_top_scores
                else 0.0,
                "insufficient_evidence_threshold": insufficient_threshold,
                "unanswerable_flagged_count": unanswerable_flagged,
                "latency_ms": {
                    "embedding": _stats(embed_latencies),
                    "db_search": _stats(db_latencies),
                    "total": _stats(total_latencies),
                },
            },
            "details": query_details,
        }
        return report
    finally:
        await runtime.close()


def _render_markdown(report: dict[str, Any]) -> str:
    m = report["metrics"]
    lat = m["latency_ms"]
    lines = [
        "# Level 3 RAG 検索評価レポート",
        "",
        f"- 実行日時 (UTC): `{report['generated_at']}`",
        f"- Corpus: `{report['corpus_id']}`",
        f"- Embedding Model: `{report['embedding_model']}` ({report['embedding_dimension']} 次元)",
        f"- Chunking: `chunk_size={report['chunk_size']}`, `chunk_overlap={report['chunk_overlap']}`",
        f"- Top-K: `{report['top_k']}`",
        "",
        "## 1. 取り込み文書一覧",
        "",
        "| ファイル名 | 形式 | Chunk数 | ステータス |",
        "|---|---|---:|---|",
    ]
    for d in report["ingested_documents"]:
        lines.append(
            f"| `{d['filename']}` | `{d['file_type']}` | {d['chunk_count']} | `{d['status']}` |"
        )

    lines.extend(
        [
            "",
            "## 2. 検索精度・出典・遅延（実測値）",
            "",
            f"- **Document Recall@5**: `{m['document_recall_at_5'] * 100:.1f}%` ({m['document_hits']}/{m['answerable_queries']})",
            f"- **Chunk Recall@5** (キーワード根拠一致): `{m['chunk_recall_at_5'] * 100:.1f}%` ({m['chunk_hits']}/{m['answerable_queries']})",
            f"- **PDF ページ番号一致率@5**: `{m['pdf_page_recall_at_5'] * 100:.1f}%` ({m['pdf_page_hits']}/{m['pdf_page_checked']})",
            f"- **出典情報整合率** (`document_id`, `chunk_id`, `filename`, PDF `page_number`): `{m['citation_integrity_rate'] * 100:.1f}%` ({m['citation_valid']}/{m['citation_checked']})",
            f"- **正解あり質問の Top-1 類似度平均**: `{m['answerable_top1_score_mean']:.4f}`",
            f"- **正解なし質問の Top-1 類似度平均**: `{m['unanswerable_top1_score_mean']:.4f}`（閾値 `{m['insufficient_evidence_threshold']}` 未満で根拠不足検出: {m['unanswerable_flagged_count']}/{m['unanswerable_queries']}）",
            "",
            "### Retrieval Latency (ms)",
            "",
            "| 計測項目 | 平均 (mean) | p50 | p95 | 最小 / 最大 |",
            "|---|---:|---:|---:|---:|",
            f"| Embedding 生成 | `{lat['embedding']['mean']} ms` | `{lat['embedding']['p50']} ms` | `{lat['embedding']['p95']} ms` | `{lat['embedding']['min']}` / `{lat['embedding']['max']} ms` |",
            f"| PostgreSQL Vector Search | `{lat['db_search']['mean']} ms` | `{lat['db_search']['p50']} ms` | `{lat['db_search']['p95']} ms` | `{lat['db_search']['min']}` / `{lat['db_search']['max']} ms` |",
            f"| **Retrieval 合計** | **`{lat['total']['mean']} ms`** | **`{lat['total']['p50']} ms`** | **`{lat['total']['p95']} ms`** | `{lat['total']['min']}` / `{lat['total']['max']} ms` |",
            "",
            "## 3. クエリ別結果",
            "",
            "| ID | カテゴリ | 正解文書 | Doc@5 | Chunk@5 | Top-1 Score | 合計(ms) |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in report["details"]:
        if row["answerable"]:
            lines.append(
                f"| `{row['id']}` | `{row['category']}` | `{row['expected_document']}` | "
                f"{'OK' if row['doc_hit_at_5'] else 'MISS'} | "
                f"{'OK' if row['chunk_hit_at_5'] else 'MISS'} | "
                f"`{row['top_score']:.4f}` | `{row['latency_ms']['total']}` |"
            )
        else:
            lines.append(
                f"| `{row['id']}` | `{row['category']}` | `(なし)` | "
                f"— | {'根拠不足検出' if row['flagged_insufficient_evidence'] else '閾値超過'} | "
                f"`{row['top_score']:.4f}` | `{row['latency_ms']['total']}` |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Level 3 RAG ingestion and evaluation.")
    parser.add_argument("--corpus", default=DEFAULT_EVAL_CORPUS)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--reset", action="store_true", help="Delete and re-ingest test corpus")
    parser.add_argument("--threshold", type=float, default=0.72)
    args = parser.parse_args()

    report = asyncio.run(
        run_evaluation(
            corpus_id=args.corpus,
            top_k=args.top_k,
            reset_corpus=args.reset,
            insufficient_threshold=args.threshold,
        )
    )
    REPORT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    REPORT_MD_PATH.write_text(_render_markdown(report), encoding="utf-8")

    m = report["metrics"]
    print(f"Document Recall@5 : {m['document_recall_at_5'] * 100:.1f}% ({m['document_hits']}/{m['answerable_queries']})")
    print(f"Chunk Recall@5    : {m['chunk_recall_at_5'] * 100:.1f}% ({m['chunk_hits']}/{m['answerable_queries']})")
    print(f"Citation Integrity: {m['citation_integrity_rate'] * 100:.1f}% ({m['citation_valid']}/{m['citation_checked']})")
    print(f"Latency Total     : mean={m['latency_ms']['total']['mean']}ms p50={m['latency_ms']['total']['p50']}ms p95={m['latency_ms']['total']['p95']}ms")
    print(f"Reports saved to  : {REPORT_JSON_PATH} and {REPORT_MD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Unit tests for Level 3 Document Parser and Recursive Text Chunker."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from rag.chunkers.recursive_chunker import RecursiveTextChunker
from rag.interfaces.parser import DocumentParseError
from rag.parsers.document_parser import LocalDocumentParser

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "rag_documents"


def test_parse_all_five_rag_fixture_documents():
    parser = LocalDocumentParser()
    expected_files = {
        "company_rules.pdf": ("pdf", 2, "午前9時00分"),
        "employee_manual.pdf": ("pdf", 2, "出勤打刻"),
        "faq.md": ("markdown", 1, "パスワード"),
        "system_guide.txt": ("txt", 1, "E-204"),
        "business_procedures.pdf": ("pdf", 2, "月末締め"),
    }
    for filename, (file_type, min_pages, expected_snippet) in expected_files.items():
        path = FIXTURES_DIR / filename
        assert path.exists(), f"Missing fixture: {path}"
        assert parser.supports(path) is True
        doc = parser.parse(path)
        assert doc.filename == filename
        assert doc.file_type == file_type
        assert len(doc.file_hash) == 64
        assert len(doc.pages) >= min_pages
        assert expected_snippet in doc.full_text
        if file_type == "pdf":
            assert [p.page_number for p in doc.pages] == list(range(1, len(doc.pages) + 1))


def test_parser_rejects_missing_empty_corrupt_and_unsupported_files(tmp_path: Path):
    parser = LocalDocumentParser()

    with pytest.raises(DocumentParseError):
        parser.parse(tmp_path / "does_not_exist.txt")

    empty_txt = tmp_path / "empty.txt"
    empty_txt.write_text("", encoding="utf-8")
    with pytest.raises(DocumentParseError):
        parser.parse(empty_txt)

    whitespace_md = tmp_path / "blank.md"
    whitespace_md.write_text("   \n\n  ", encoding="utf-8")
    with pytest.raises(DocumentParseError):
        parser.parse(whitespace_md)

    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"%PDF-1.4\nnot-a-valid-pdf-stream")
    with pytest.raises(DocumentParseError):
        parser.parse(corrupt_pdf)

    unsupported = tmp_path / "notes.docx"
    unsupported.write_text("hello", encoding="utf-8")
    assert parser.supports(unsupported) is False
    with pytest.raises(DocumentParseError):
        parser.parse(unsupported)


def test_recursive_chunker_preserves_page_numbers_and_metadata():
    parser = LocalDocumentParser()
    doc = parser.parse(FIXTURES_DIR / "company_rules.pdf")

    doc_id = uuid.uuid4()
    chunker = RecursiveTextChunker(chunk_size=220, chunk_overlap=40)
    chunks = chunker.chunk(doc, document_id=doc_id)

    assert len(chunks) >= 4
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.document_id == doc_id for c in chunks)
    assert all(c.content.strip() for c in chunks)
    assert {c.page_number for c in chunks} == {1, 2}
    assert all(c.metadata["filename"] == "company_rules.pdf" for c in chunks)
    assert all(c.metadata["file_type"] == "pdf" for c in chunks)

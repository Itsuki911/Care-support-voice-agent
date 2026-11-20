"""Document parser supporting PDF (pypdf), TXT, and Markdown (Python stdlib)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from rag.interfaces.parser import BaseDocumentParser, DocumentParseError
from rag.models.rag import ParsedDocument, ParsedPage

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
}


class LocalDocumentParser(BaseDocumentParser):
    """Parses local PDF, TXT, and Markdown files into a normalized ParsedDocument."""

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in SUPPORTED_EXTENSIONS

    def parse(self, path: Path) -> ParsedDocument:
        file_path = Path(path)
        if not file_path.exists():
            raise DocumentParseError(f"Document file not found: {file_path}")
        if not file_path.is_file():
            raise DocumentParseError(f"Path is not a file: {file_path}")

        ext = file_path.suffix.lower()
        file_type = SUPPORTED_EXTENSIONS.get(ext)
        if file_type is None:
            raise DocumentParseError(
                f"Unsupported file extension '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        raw_bytes = file_path.read_bytes()
        if not raw_bytes:
            raise DocumentParseError(f"Document is empty (0 bytes): {file_path.name}")

        file_hash = hashlib.sha256(raw_bytes).hexdigest()

        if file_type == "pdf":
            pages = self._parse_pdf(file_path)
        else:
            pages = self._parse_text(file_path, raw_bytes, file_type=file_type)

        if not pages or not any(p.text.strip() for p in pages):
            raise DocumentParseError(f"No extractable text found in document: {file_path.name}")

        return ParsedDocument(
            filename=file_path.name,
            file_type=file_type,
            file_hash=file_hash,
            pages=pages,
            metadata={
                "source_path": str(file_path.name),
                "page_count": len(pages),
                "byte_size": len(raw_bytes),
            },
        )

    def _parse_pdf(self, file_path: Path) -> list[ParsedPage]:
        try:
            reader = PdfReader(str(file_path))
        except (PdfReadError, OSError, ValueError) as exc:
            raise DocumentParseError(f"Failed to read PDF '{file_path.name}': {exc}") from None

        if len(reader.pages) == 0:
            raise DocumentParseError(f"PDF has 0 pages: {file_path.name}")

        pages: list[ParsedPage] = []
        for idx, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception as exc:
                raise DocumentParseError(
                    f"Failed to extract text from '{file_path.name}' page {idx}: {exc}"
                ) from None
            if text:
                pages.append(ParsedPage(text=text, page_number=idx))
        return pages

    def _parse_text(
        self, file_path: Path, raw_bytes: bytes, *, file_type: str
    ) -> list[ParsedPage]:
        try:
            text = raw_bytes.decode("utf-8-sig").strip()
        except UnicodeDecodeError as exc:
            raise DocumentParseError(
                f"Failed to decode {file_type} file '{file_path.name}' as UTF-8: {exc}"
            ) from None
        if not text:
            return []
        return [ParsedPage(text=text, page_number=None)]

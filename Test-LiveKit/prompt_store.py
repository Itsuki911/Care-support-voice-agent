"""Versioned system prompt loader for Git-tracked prompt management."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class PromptSpec:
    """Loaded system prompt with version identifier and content digest."""

    version: str
    text: str
    sha256: str


def load_system_prompt(version: str | None = None, *, prompts_dir: Path | None = None) -> PromptSpec:
    """Load a versioned system prompt from disk and compute its SHA-256 digest."""
    resolved_version = (version or os.getenv("PROMPT_VERSION") or "v1").strip()
    if not _VERSION_PATTERN.fullmatch(resolved_version):
        raise ValueError(f"Invalid prompt version identifier: {resolved_version!r}")

    base_dir = prompts_dir or PROMPTS_DIR
    path = base_dir / f"system_{resolved_version}.md"
    if not path.is_file():
        raise FileNotFoundError(f"System prompt file not found: {path}")

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"System prompt file is empty: {path}")

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return PromptSpec(version=resolved_version, text=text, sha256=digest)

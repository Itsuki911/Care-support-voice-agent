"""Git-versioned prompts; content hash distinguishes edits to the same version."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import re


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str
    digest: str


def load_prompt() -> Prompt:
    version = os.getenv('SYSTEM_PROMPT_VERSION', 'v2')
    if not re.fullmatch(r'v[0-9]+', version):
        raise ValueError('SYSTEM_PROMPT_VERSION must be v followed by digits')
    text = (Path(__file__).parent / 'prompts' / f'system-{version}.md').read_text(encoding='utf-8').strip()
    return Prompt(version, text, sha256(text.encode()).hexdigest())

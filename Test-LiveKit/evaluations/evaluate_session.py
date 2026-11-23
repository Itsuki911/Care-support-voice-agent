"""Manual CLI evaluation for voice, text, and TEST-Secretary sessions using DeepEval."""

from __future__ import annotations

import sys

from evaluations.evaluate_secretary import run_cli


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if "--mode" not in raw:
        raw = ["--mode", "conversation", *raw]
    return run_cli(raw)


if __name__ == "__main__":
    raise SystemExit(main())

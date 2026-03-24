from __future__ import annotations

from pathlib import Path


def load_text_file(path: str | Path) -> tuple[str, str]:
    target = Path(path)
    return target.name, target.read_text(encoding="utf-8")


def normalize_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())

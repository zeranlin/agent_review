from __future__ import annotations

from pathlib import Path

from ..models import ParseResult, ParsedPage


def parse_text(path: str | Path) -> ParseResult:
    target = Path(path).expanduser().resolve()
    text = target.read_text(encoding="utf-8")
    return ParseResult(
        parser_name="text",
        source_path=str(target),
        source_format=target.suffix.lower().lstrip(".") or "txt",
        page_count=1,
        text=text,
        pages=[ParsedPage(page_index=1, text=text, source="text")],
        tables=[],
        warnings=[],
    )

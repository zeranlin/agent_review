from __future__ import annotations

from pathlib import Path

from ...models import ParseResult, ParsedPage
from .structure_helpers import extract_text_structure_artifacts


def parse_text(path: str | Path) -> ParseResult:
    target = Path(path).expanduser().resolve()
    text = target.read_text(encoding="utf-8")
    raw_blocks, raw_tables, parsed_tables, _, _ = extract_text_structure_artifacts(
        text,
        source_path=str(target),
        source_label="text",
    )
    return ParseResult(
        parser_name="text",
        source_path=str(target),
        source_format=target.suffix.lower().lstrip(".") or "txt",
        page_count=1,
        text=text,
        pages=[ParsedPage(page_index=1, text=text, source="text")],
        tables=parsed_tables,
        raw_blocks=raw_blocks,
        raw_tables=raw_tables,
        warnings=[],
    )

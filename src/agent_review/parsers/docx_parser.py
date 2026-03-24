from __future__ import annotations

from pathlib import Path

from docx import Document

from ..models import ParseResult, ParsedPage, ParsedTable


def parse_docx(path: str | Path) -> ParseResult:
    target = Path(path).expanduser().resolve()
    document = Document(str(target))

    paragraphs = [item.text.strip() for item in document.paragraphs if item.text.strip()]
    table_records: list[ParsedTable] = []
    table_text_blocks: list[str] = []
    for table_index, table in enumerate(document.tables, start=1):
        rows: list[list[str]] = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                rows.append(cells)
        if not rows:
            continue
        table_records.append(
            ParsedTable(
                table_index=table_index,
                row_count=len(rows),
                rows=rows,
                source="docx_table",
            )
        )
        table_text_blocks.append("\n".join(" | ".join(cell for cell in row) for row in rows))

    text_parts = paragraphs + table_text_blocks
    text = "\n".join(part for part in text_parts if part)
    return ParseResult(
        parser_name="docx",
        source_path=str(target),
        source_format="docx",
        page_count=None,
        text=text,
        pages=[ParsedPage(page_index=1, text=text, source="docx")],
        tables=table_records,
        warnings=[],
    )

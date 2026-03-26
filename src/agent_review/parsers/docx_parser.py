from __future__ import annotations

from pathlib import Path
import re

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from ..models import ParseResult, ParsedPage, ParsedTable, RawBlock, RawCell, RawTable, SourceAnchor
from .structure_helpers import guess_catalog_candidate, guess_heading_candidate, guess_numbering_level, infer_table_title


def parse_docx(path: str | Path) -> ParseResult:
    target = Path(path).expanduser().resolve()
    document = Document(str(target))

    raw_blocks, raw_tables, table_records, text_parts = _parse_docx_structure(document, target)
    text = "\n".join(part for part in text_parts if part)
    return ParseResult(
        parser_name="docx",
        source_path=str(target),
        source_format="docx",
        page_count=None,
        text=text,
        pages=[ParsedPage(page_index=1, text=text, source="docx")],
        tables=table_records,
        raw_blocks=raw_blocks,
        raw_tables=raw_tables,
        warnings=[],
    )


def _parse_docx_structure(
    document: Document,
    target: Path,
) -> tuple[list[RawBlock], list[RawTable], list[ParsedTable], list[str]]:
    blocks: list[RawBlock] = []
    raw_tables: list[RawTable] = []
    parsed_tables: list[ParsedTable] = []
    text_parts: list[str] = []
    last_heading = ""
    document_order = 0
    table_index = 0
    for item in _iter_docx_block_items(document):
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if not text:
                continue
            style_name = _paragraph_style_name(item)
            numbering = _extract_numbering_text(text)
            heading_candidate = guess_heading_candidate(text, style_name)
            metadata = {
                "heading_candidate": heading_candidate,
                "catalog_candidate": guess_catalog_candidate(text),
                "style_name": style_name,
                "numbering_level_guess": guess_numbering_level(text, style_name),
                "document_order": document_order,
                "source_label": "docx",
            }
            blocks.append(
                RawBlock(
                    block_id=f"p-{document_order + 1}",
                    block_type="paragraph",
                    text=text,
                    style_name=style_name,
                    numbering=numbering,
                    anchor=SourceAnchor(
                        source_path=str(target),
                        block_no=document_order + 1,
                        paragraph_no=document_order + 1,
                        line_hint=f"line:{document_order + 1}",
                    ),
                    metadata=metadata,
                )
            )
            text_parts.append(text)
            document_order += 1
            if heading_candidate:
                last_heading = text
            continue

        if isinstance(item, Table):
            raw_rows: list[list[RawCell]] = []
            parsed_rows: list[list[str]] = []
            for row_index, row in enumerate(item.rows, start=1):
                raw_row: list[RawCell] = []
                parsed_row: list[str] = []
                for col_index, cell in enumerate(row.cells, start=1):
                    cell_text = cell.text.strip()
                    raw_row.append(
                        RawCell(
                            row_index=row_index,
                            col_index=col_index,
                            text=cell_text,
                            is_header=row_index == 1,
                            anchor=SourceAnchor(
                                source_path=str(target),
                                table_no=table_index + 1,
                                row_no=row_index,
                                cell_no=col_index,
                                line_hint=f"line:{document_order + row_index}",
                            ),
                        )
                    )
                    parsed_row.append(cell_text)
                if any(item for item in parsed_row):
                    raw_rows.append(raw_row)
                    parsed_rows.append(parsed_row)
            if not parsed_rows:
                continue
            table_index += 1
            title_hint = infer_table_title(parsed_rows)
            raw_tables.append(
                RawTable(
                    table_id=f"t-{table_index}",
                    rows=raw_rows,
                    anchor=SourceAnchor(
                        source_path=str(target),
                        table_no=table_index,
                        line_hint=f"line:{document_order + 1}",
                    ),
                    title_hint=title_hint,
                    metadata={
                        "header_row_count": 1,
                        "column_count": max((len(row) for row in parsed_rows), default=0),
                        "document_order": document_order,
                        "preceding_heading": last_heading,
                        "table_kind": _infer_table_kind(parsed_rows, last_heading, title_hint),
                    },
                )
            )
            parsed_tables.append(
                ParsedTable(
                    table_index=table_index,
                    row_count=len(parsed_rows),
                    rows=parsed_rows,
                    source="docx_table",
                )
            )
            text_parts.append("\n".join(" | ".join(cell for cell in row) for row in parsed_rows))
            document_order += 1
    return blocks, raw_tables, parsed_tables, text_parts


def _iter_docx_block_items(document: Document):
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def _paragraph_style_name(paragraph) -> str:
    style = getattr(paragraph, "style", None)
    return getattr(style, "name", "") or ""


def _extract_numbering_text(text: str) -> str:
    match = re.match(r"^\s*((?:第[一二三四五六七八九十百千0-9]+[章节册部分篇])|(?:[一二三四五六七八九十]+、)|(?:（[一二三四五六七八九十0-9]+）)|(?:\d+[\.、]))", text)
    return match.group(1) if match else ""


def _infer_table_kind(rows: list[list[str]], preceding_heading: str, title_hint: str) -> str:
    haystack = f"{preceding_heading} {title_hint} " + " ".join(" ".join(row) for row in rows)
    if any(token in haystack for token in ["评分项", "分值", "评分标准", "得分", "评标", "综合评分"]):
        return "scoring"
    if any(token in haystack for token in ["中小企业声明函", "投标文件格式", "声明函", "承诺函", "附件", "附表", "格式"]):
        return "template"
    if any(token in haystack for token in ["付款", "验收", "违约", "解除合同", "质保", "保修"]):
        return "contract"
    if any(token in haystack for token in ["详见附件", "另册提供"]):
        return "appendix_reference"
    return "general"

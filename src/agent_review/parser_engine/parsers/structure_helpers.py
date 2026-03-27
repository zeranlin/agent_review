from __future__ import annotations

import re

from ...models import ParsedTable, RawBlock, RawCell, RawTable, SourceAnchor


TABLE_HINT_TOKENS = [
    "评分项",
    "分值",
    "评分标准",
    "序号",
    "内容",
    "说明",
    "备注",
    "项目",
    "标准",
    "要求",
    "报价",
    "金额",
    "名称",
    "参数",
    "评标",
    "得分",
]


def guess_heading_candidate(text: str, style_name: str = "") -> bool:
    if style_name and "heading" in style_name.lower():
        return True
    normalized = text.strip()
    if not normalized:
        return False
    if normalized == "目录":
        return True
    if normalized.startswith(("附件", "附表", "声明函", "承诺函", "投标文件格式")):
        return True
    return bool(_extract_numbering_text(normalized)) or bool(
        re.match(r"^(项目概况|投标人资格要求|评分标准|综合评分法评标信息|评标信息|合同条款|技术要求|商务要求|采购需求|投标文件格式|投标文件格式、附件)", normalized)
    )


def guess_catalog_candidate(text: str) -> bool:
    normalized = text.strip()
    if normalized == "目录":
        return True
    return bool(
        re.match(
            r"^(第[一二三四五六七八九十百千0-9]+[章节册部分篇]|[一二三四五六七八九十]+、|（[一二三四五六七八九十0-9]+）)",
            normalized,
        )
        and len(normalized) <= 40
    )


def guess_numbering_level(text: str, style_name: str = "") -> int:
    normalized = text.strip()
    if style_name and "heading 1" in style_name.lower():
        return 1
    if style_name and "heading 2" in style_name.lower():
        return 2
    if re.match(r"^第[一二三四五六七八九十百千0-9]+[章节册部分篇]", normalized):
        return 1
    if re.match(r"^[一二三四五六七八九十]+、", normalized):
        return 2
    if re.match(r"^（[一二三四五六七八九十0-9]+）", normalized):
        return 3
    if re.match(r"^\d+[\.、]", normalized):
        return 4
    return 0


def infer_table_title(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    first_row = " ".join(cell for cell in rows[0] if cell).strip()
    return first_row[:80]


def extract_text_structure_artifacts(
    text: str,
    *,
    source_path: str = "",
    source_label: str = "text",
    page_no: int | None = None,
    line_offset: int = 0,
    table_index_offset: int = 0,
) -> tuple[list[RawBlock], list[RawTable], list[ParsedTable], int, int]:
    lines = text.splitlines()
    raw_blocks: list[RawBlock] = []
    raw_tables: list[RawTable] = []
    parsed_tables: list[ParsedTable] = []

    table_index = table_index_offset
    document_order = 0
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        line_no = line_offset + idx + 1
        if not line:
            idx += 1
            continue

        table_rows, consumed = _collect_table_rows(lines, idx)
        if len(table_rows) >= 2:
            table_index += 1
            raw_table = _build_raw_table(
                table_rows,
                table_index=table_index,
                source_path=source_path,
                source_label=source_label,
                page_no=page_no,
                start_line_no=line_no,
                line_offset=line_offset,
                document_order=document_order,
            )
            raw_tables.append(raw_table)
            parsed_tables.append(
                ParsedTable(
                    table_index=table_index,
                    row_count=len(table_rows),
                    rows=table_rows,
                    source=source_label,
                )
            )
            idx += consumed
            document_order += 1
            continue

        raw_blocks.append(
            RawBlock(
                block_id=f"b-{line_offset + idx + 1}",
                block_type="paragraph",
                text=line,
                style_name="",
                numbering=_extract_numbering_text(line),
                anchor=SourceAnchor(
                    source_path=source_path,
                    page_no=page_no,
                    block_no=document_order + 1,
                    line_hint=f"line:{line_no}",
                ),
                metadata={
                    "heading_candidate": guess_heading_candidate(line),
                    "catalog_candidate": guess_catalog_candidate(line),
                    "style_name": "",
                    "numbering_level_guess": guess_numbering_level(line),
                    "document_order": document_order,
                    "line_no": line_no,
                    "source_label": source_label,
                },
            )
        )
        document_order += 1
        idx += 1

    return raw_blocks, raw_tables, parsed_tables, len(lines), table_index - table_index_offset


def _collect_table_rows(lines: list[str], start_index: int) -> tuple[list[list[str]], int]:
    rows: list[list[str]] = []
    idx = start_index
    while idx < len(lines):
        candidate = lines[idx].strip()
        if not candidate:
            break
        columns = _split_table_row(candidate)
        if columns is None:
            break
        rows.append(columns)
        idx += 1
    return rows, idx - start_index


def _split_table_row(line: str) -> list[str] | None:
    if "|" in line:
        columns = [part.strip() for part in line.split("|") if part.strip()]
        if len(columns) >= 2:
            return columns
    if "\t" in line:
        columns = [part.strip() for part in line.split("\t") if part.strip()]
        if len(columns) >= 2:
            return columns

    columns = [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]
    if len(columns) >= 3 and _looks_like_table_columns(columns, line):
        return columns
    return None


def _looks_like_table_columns(columns: list[str], line: str) -> bool:
    if any(token in line for token in TABLE_HINT_TOKENS):
        return True
    if len(columns) >= 4:
        return True
    if any(any(char.isdigit() for char in column) for column in columns):
        return True
    return max((len(column) for column in columns), default=0) <= 20


def _build_raw_table(
    rows: list[list[str]],
    *,
    table_index: int,
    source_path: str,
    source_label: str,
    page_no: int | None,
    start_line_no: int,
    line_offset: int,
    document_order: int,
) -> RawTable:
    title_hint = infer_table_title(rows)
    table_kind = _infer_table_kind(rows, title_hint)
    raw_rows: list[list[RawCell]] = []
    for row_index, row in enumerate(rows, start=1):
        raw_row: list[RawCell] = []
        row_line_no = start_line_no + row_index - 1
        for col_index, cell_text in enumerate(row, start=1):
            raw_row.append(
                RawCell(
                    row_index=row_index,
                    col_index=col_index,
                    text=cell_text,
                    is_header=row_index == 1,
                    anchor=SourceAnchor(
                        source_path=source_path,
                        page_no=page_no,
                        table_no=table_index,
                        row_no=row_index,
                        cell_no=col_index,
                        line_hint=f"line:{row_line_no}",
                    ),
                )
            )
        raw_rows.append(raw_row)

    return RawTable(
        table_id=f"t-{table_index}",
        rows=raw_rows,
        anchor=SourceAnchor(
            source_path=source_path,
            page_no=page_no,
            table_no=table_index,
            row_no=1,
            line_hint=f"line:{start_line_no}",
        ),
        title_hint=title_hint,
        metadata={
            "document_order": document_order,
            "line_start": start_line_no,
            "line_end": start_line_no + len(rows) - 1,
            "source_label": source_label,
            "table_kind": table_kind,
        },
    )


def _infer_table_kind(rows: list[list[str]], title_hint: str) -> str:
    haystack = " ".join(" ".join(row) for row in rows)
    text = f"{title_hint} {haystack}"
    if any(token in text for token in ["评分项", "分值", "评分标准", "得分", "评标", "综合评分"]):
        return "scoring"
    if any(token in text for token in ["中小企业声明函", "投标文件格式", "声明函", "承诺函", "附件", "附表", "格式"]):
        return "template"
    if any(token in text for token in ["付款", "验收", "违约", "解除合同", "质保", "保修"]):
        return "contract"
    if any(token in text for token in ["详见附件", "另册提供"]):
        return "appendix_reference"
    return "general"


def _extract_numbering_text(text: str) -> str:
    match = re.match(r"^\s*((?:第[一二三四五六七八九十百千0-9]+[章节册部分篇])|(?:[一二三四五六七八九十]+、)|(?:（[一二三四五六七八九十0-9]+）)|(?:\d+[\.、]))", text)
    return match.group(1) if match else ""

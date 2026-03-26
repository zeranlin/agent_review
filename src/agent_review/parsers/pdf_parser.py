from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from .ocr import extract_pdf_images, ocr_image_records
from .structure_helpers import extract_text_structure_artifacts
from ..models import ParseResult, ParsedPage, ParsedTable


def parse_pdf(path: str | Path) -> ParseResult:
    target = Path(path).expanduser().resolve()
    reader = PdfReader(str(target))

    pages: list[ParsedPage] = []
    tables: list[ParsedTable] = []
    warnings: list[str] = []
    text_blocks: list[str] = []
    raw_blocks: list = []
    raw_tables: list = []
    text_table_count = 0
    line_offset = 0
    text_page_count = 0
    for page_index, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if page_text:
            text_page_count += 1
            page_blocks, page_raw_tables, page_parsed_tables, line_count, table_count = extract_text_structure_artifacts(
                page_text,
                source_path=str(target),
                source_label="pdf_text",
                page_no=page_index,
                line_offset=line_offset,
                table_index_offset=text_table_count,
            )
            raw_blocks.extend(page_blocks)
            raw_tables.extend(page_raw_tables)
            tables.extend(page_parsed_tables)
            text_table_count += table_count
            line_offset += line_count
        pages.append(
            ParsedPage(
                page_index=page_index,
                text=page_text,
                source="pdf_text",
            )
        )
        if page_text:
            text_blocks.append(page_text)

    image_records = extract_pdf_images(target)
    if image_records:
        ocr_results, ocr_tables, ocr_warnings = ocr_image_records(image_records)
        warnings.extend(ocr_warnings)
        ocr_text = "\n".join(item for item in ocr_results if item.strip())
        if ocr_text:
            text_blocks.append(ocr_text)
            ocr_blocks, ocr_raw_tables, ocr_parsed_tables, line_count, table_count = extract_text_structure_artifacts(
                ocr_text,
                source_path=str(target),
                source_label="pdf_ocr_text",
                page_no=len(pages) + 1,
                line_offset=line_offset,
                table_index_offset=text_table_count,
            )
            raw_blocks.extend(ocr_blocks)
            if not ocr_tables:
                raw_tables.extend(ocr_raw_tables)
                tables.extend(ocr_parsed_tables)
                text_table_count += table_count
            line_offset += line_count
            pages.append(
                ParsedPage(
                    page_index=len(pages) + 1,
                    text=ocr_text,
                    source="pdf_image_ocr",
                )
            )
        else:
            warnings.append("PDF 中提取了图片，但 OCR 未识别出可用文本。")
        tables.extend(ocr_tables)
    elif text_page_count == 0:
        warnings.append("PDF 未提取到文本，且未发现可 OCR 的嵌入图片；当前环境缺少整页渲染 OCR 通道。")

    text = "\n".join(block for block in text_blocks if block)
    if text_page_count == 0 and text:
        warnings.append("PDF 正文文本较少，已尝试通过图片 OCR 补充。")

    return ParseResult(
        parser_name="pdf",
        source_path=str(target),
        source_format="pdf",
        page_count=len(reader.pages),
        text=text,
        pages=pages,
        tables=tables,
        raw_blocks=raw_blocks,
        raw_tables=raw_tables,
        warnings=list(dict.fromkeys(warnings)),
    )

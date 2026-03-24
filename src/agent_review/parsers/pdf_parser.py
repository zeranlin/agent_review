from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from .ocr import extract_pdf_images, ocr_image_records
from ..models import ParseResult, ParsedPage, ParsedTable


def parse_pdf(path: str | Path) -> ParseResult:
    target = Path(path).expanduser().resolve()
    reader = PdfReader(str(target))

    pages: list[ParsedPage] = []
    tables: list[ParsedTable] = []
    warnings: list[str] = []
    text_blocks: list[str] = []
    text_page_count = 0
    for page_index, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if page_text:
            text_page_count += 1
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
        warnings=list(dict.fromkeys(warnings)),
    )

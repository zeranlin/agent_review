from __future__ import annotations

from pathlib import Path

from .docx_parser import parse_docx
from .ocr import is_image_file, parse_image_with_ocr
from .pdf_parser import parse_pdf
from .text_parser import parse_text
from ..models import ParseResult, ParsedPage, SourceDocument
from ..structure import enrich_parse_result_structure


def load_document(path: str | Path) -> tuple[str, ParseResult]:
    target = Path(path).expanduser().resolve()
    suffix = target.suffix.lower()

    if suffix in {".txt", ".md"}:
        result = parse_text(target)
    elif suffix == ".pdf":
        result = parse_pdf(target)
    elif suffix == ".docx":
        result = parse_docx(target)
    elif suffix == ".doc":
        raise ValueError("暂不直接支持 .doc，请先转换为 .docx 或 PDF。")
    elif is_image_file(target):
        result = parse_image_with_ocr(target)
    else:
        raise ValueError(f"暂不支持的文件类型: {suffix}")

    return target.name, enrich_parse_result_structure(result)


def normalize_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def load_documents(paths: list[str | Path]) -> tuple[str, ParseResult, list[SourceDocument]]:
    if not paths:
        raise ValueError("至少需要提供一个待审查文件。")

    parse_results: list[tuple[str, ParseResult]] = [load_document(path) for path in paths]
    source_documents = [
        SourceDocument(
            document_name=document_name,
            source_path=parse_result.source_path,
            source_format=parse_result.source_format,
            parser_name=parse_result.parser_name,
            page_count=parse_result.page_count,
        )
        for document_name, parse_result in parse_results
    ]
    merged_text_parts: list[str] = []
    warnings: list[str] = []
    pages: list[ParsedPage] = []
    total_page_count = 0
    page_cursor = 1
    for document_name, parse_result in parse_results:
        merged_text_parts.append(f"## 文档：{document_name}")
        merged_text_parts.append(parse_result.text)
        warnings.extend(parse_result.warnings)
        if parse_result.page_count is not None:
            total_page_count += parse_result.page_count
        for page in parse_result.pages:
            pages.append(
                ParsedPage(
                    page_index=page_cursor,
                    text=page.text,
                    source=document_name,
                )
            )
            page_cursor += 1

    primary_name = source_documents[0].document_name
    merged_name = (
        primary_name
        if len(source_documents) == 1
        else f"{primary_name} 等{len(source_documents)}个文件"
    )
    merged_result = ParseResult(
        parser_name="multi_loader" if len(source_documents) > 1 else parse_results[0][1].parser_name,
        source_path=";".join(item.source_path for item in source_documents),
        source_format="multi" if len(source_documents) > 1 else parse_results[0][1].source_format,
        page_count=total_page_count if total_page_count else None,
        text="\n\n".join(part for part in merged_text_parts if part.strip()),
        pages=pages,
        tables=[],
        warnings=list(dict.fromkeys(warnings)),
    )
    return merged_name, enrich_parse_result_structure(merged_result), source_documents

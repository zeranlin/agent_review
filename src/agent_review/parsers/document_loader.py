from __future__ import annotations

from pathlib import Path

from .docx_parser import parse_docx
from .ocr import is_image_file, parse_image_with_ocr
from .pdf_parser import parse_pdf
from .text_parser import parse_text
from ..models import ParseResult


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

    return target.name, result


def normalize_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())

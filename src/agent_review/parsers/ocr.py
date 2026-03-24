from __future__ import annotations

import mimetypes
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytesseract
from PIL import Image
from pypdf import PdfReader


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(slots=True)
class OcrImageRecord:
    source_path: str
    page_index: int | None
    image_index: int
    image_name: str
    stored_path: str
    media_type: str


def is_image_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def parse_image_with_ocr(path: str | Path):
    from ..models import ParseResult, ParsedPage

    target = Path(path).expanduser().resolve()
    text, warnings = _ocr_image(target)
    return ParseResult(
        parser_name="ocr_image",
        source_path=str(target),
        source_format=target.suffix.lower().lstrip("."),
        page_count=1,
        text=text,
        pages=[ParsedPage(page_index=1, text=text, source="ocr_image")],
        tables=[],
        warnings=warnings,
    )


def extract_pdf_images(pdf_path: str | Path) -> list[OcrImageRecord]:
    source = Path(pdf_path).expanduser().resolve()
    reader = PdfReader(str(source))
    target_dir = Path(tempfile.mkdtemp(prefix="agent_review_pdf_images_"))

    records: list[OcrImageRecord] = []
    image_counter = 0
    for page_index, page in enumerate(reader.pages, start=1):
        for local_index, image in enumerate(page.images, start=1):
            image_counter += 1
            image_name = image.name or f"page_{page_index}_image_{local_index}.bin"
            suffix = Path(image_name).suffix or ".bin"
            stored_name = f"page_{page_index:03d}_img_{local_index:02d}{suffix}"
            stored_path = target_dir / stored_name
            stored_path.write_bytes(image.data)
            media_type, _ = mimetypes.guess_type(stored_name)
            records.append(
                OcrImageRecord(
                    source_path=str(source),
                    page_index=page_index,
                    image_index=image_counter,
                    image_name=image_name,
                    stored_path=str(stored_path),
                    media_type=media_type or "application/octet-stream",
                )
            )
    return records


def ocr_image_records(image_records: list[OcrImageRecord]) -> list[str]:
    results: list[str] = []
    for record in image_records:
        text, _ = _ocr_image(record.stored_path)
        if text.strip():
            prefix = f"[OCR page {record.page_index}]"
            results.append(f"{prefix}\n{text}")
    return results


def _ocr_image(path: str | Path) -> tuple[str, list[str]]:
    target = Path(path).expanduser().resolve()
    warnings: list[str] = []
    try:
        image = Image.open(target)
    except Exception as exc:  # pragma: no cover - defensive
        return "", [f"OCR 无法打开图片: {exc}"]

    try:
        text = pytesseract.image_to_string(image, lang="chi_sim+eng")
    except pytesseract.TesseractNotFoundError:
        text = ""
        warnings.append("未检测到 tesseract 可执行程序，OCR 未运行。")
    except Exception as exc:  # pragma: no cover - defensive
        text = ""
        warnings.append(f"OCR 执行失败: {exc}")
    return text.strip(), warnings

from __future__ import annotations

import mimetypes
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytesseract
from PIL import Image, ImageFilter, ImageOps
from pypdf import PdfReader

from ..models import ParseResult, ParsedPage, ParsedTable


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(slots=True)
class OcrImageRecord:
    source_path: str
    page_index: int | None
    image_index: int
    image_name: str
    stored_path: str
    media_type: str


@dataclass(slots=True)
class OcrResult:
    text: str
    tables: list[ParsedTable]
    warnings: list[str]


def is_image_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def parse_image_with_ocr(path: str | Path) -> ParseResult:
    target = Path(path).expanduser().resolve()
    ocr_result = run_ocr(target)
    return ParseResult(
        parser_name="ocr_image",
        source_path=str(target),
        source_format=target.suffix.lower().lstrip("."),
        page_count=1,
        text=ocr_result.text,
        pages=[ParsedPage(page_index=1, text=ocr_result.text, source="ocr_image")],
        tables=ocr_result.tables,
        warnings=ocr_result.warnings,
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


def ocr_image_records(image_records: list[OcrImageRecord]) -> tuple[list[str], list[ParsedTable], list[str]]:
    results: list[str] = []
    tables: list[ParsedTable] = []
    warnings: list[str] = []
    table_index = 1
    for record in image_records:
        ocr_result = run_ocr(record.stored_path, table_index_offset=table_index - 1)
        warnings.extend(ocr_result.warnings)
        if ocr_result.text.strip():
            prefix = f"[OCR page {record.page_index}]"
            results.append(f"{prefix}\n{ocr_result.text}")
        if ocr_result.tables:
            tables.extend(ocr_result.tables)
            table_index += len(ocr_result.tables)
    return results, tables, list(dict.fromkeys(warnings))


def run_ocr(path: str | Path, table_index_offset: int = 0) -> OcrResult:
    target = Path(path).expanduser().resolve()
    warnings: list[str] = []
    try:
        image = Image.open(target)
    except Exception as exc:  # pragma: no cover - defensive
        return OcrResult(text="", tables=[], warnings=[f"OCR 无法打开图片: {exc}"])

    images = _preprocess_variants(image)
    best_text = ""
    best_length = -1
    tesseract_available = True
    for candidate in images:
        try:
            text = pytesseract.image_to_string(candidate, lang="chi_sim+eng")
        except pytesseract.TesseractNotFoundError:
            tesseract_available = False
            text = ""
            warnings.append("未检测到 tesseract 可执行程序，OCR 未运行。")
            break
        except Exception as exc:  # pragma: no cover - defensive
            text = ""
            warnings.append(f"OCR 执行失败: {exc}")
        normalized = text.strip()
        if len(normalized) > best_length:
            best_text = normalized
            best_length = len(normalized)

    if not tesseract_available:
        return OcrResult(text="", tables=[], warnings=list(dict.fromkeys(warnings)))

    tables = _extract_tables_from_image(
        images[0],
        table_index_offset=table_index_offset,
        warnings=warnings,
    )
    if not best_text and tables:
        row_text = [" | ".join(cell for cell in row) for table in tables for row in table.rows]
        best_text = "\n".join(row_text).strip()
    return OcrResult(
        text=best_text,
        tables=tables,
        warnings=list(dict.fromkeys(warnings)),
    )


def _preprocess_variants(image: Image.Image) -> list[Image.Image]:
    base = image.convert("L")
    enlarged = base.resize((max(base.width * 2, 1), max(base.height * 2, 1)))
    sharpened = enlarged.filter(ImageFilter.SHARPEN)
    autocontrast = ImageOps.autocontrast(sharpened)
    binary = autocontrast.point(lambda pixel: 255 if pixel > 180 else 0)
    inverted = ImageOps.invert(binary)
    return [autocontrast, binary, inverted]


def _extract_tables_from_image(
    image: Image.Image,
    table_index_offset: int,
    warnings: list[str],
) -> list[ParsedTable]:
    try:
        data = pytesseract.image_to_data(
            image,
            lang="chi_sim+eng",
            output_type=pytesseract.Output.DICT,
        )
    except pytesseract.TesseractNotFoundError:
        return []
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"OCR 表格识别失败: {exc}")
        return []

    rows_by_line: dict[tuple[int, int, int], list[tuple[int, str]]] = {}
    total = len(data.get("text", []))
    for index in range(total):
        text = str(data["text"][index]).strip()
        conf = str(data.get("conf", [""] * total)[index]).strip()
        if not text or conf in {"-1", ""}:
            continue
        block = int(data["block_num"][index])
        paragraph = int(data["par_num"][index])
        line = int(data["line_num"][index])
        left = int(data["left"][index])
        rows_by_line.setdefault((block, paragraph, line), []).append((left, text))

    candidate_rows: list[list[str]] = []
    for _, items in sorted(rows_by_line.items()):
        ordered = [text for _, text in sorted(items, key=lambda item: item[0])]
        if len(ordered) >= 2:
            candidate_rows.append(ordered)

    if len(candidate_rows) < 2:
        return []

    return [
        ParsedTable(
            table_index=table_index_offset + 1,
            row_count=len(candidate_rows),
            rows=candidate_rows,
            source="ocr_table",
        )
    ]

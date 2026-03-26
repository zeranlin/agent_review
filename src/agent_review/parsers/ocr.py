from __future__ import annotations

import mimetypes
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytesseract
from PIL import Image, ImageFilter, ImageOps
from pypdf import PdfReader

from ..models import ParseResult, ParsedPage, ParsedTable
from .structure_helpers import extract_text_structure_artifacts
from .vision_ocr import run_vision_ocr


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
    raw_blocks, raw_tables, parsed_tables, _, _ = extract_text_structure_artifacts(
        ocr_result.text,
        source_path=str(target),
        source_label="ocr_image",
        page_no=1,
    )
    if ocr_result.tables:
        raw_tables = []
        parsed_tables = []
    return ParseResult(
        parser_name="ocr_image",
        source_path=str(target),
        source_format=target.suffix.lower().lstrip("."),
        page_count=1,
        text=ocr_result.text,
        pages=[ParsedPage(page_index=1, text=ocr_result.text, source="ocr_image")],
        tables=ocr_result.tables + parsed_tables,
        raw_blocks=raw_blocks,
        raw_tables=raw_tables,
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
        ocr_result = run_ocr(
            record.stored_path,
            table_index_offset=table_index - 1,
            source_label=record.source_path,
            page_index=record.page_index,
            image_index=record.image_index,
        )
        warnings.extend(ocr_result.warnings)
        if ocr_result.text.strip():
            prefix = f"[OCR page {record.page_index}]"
            results.append(f"{prefix}\n{ocr_result.text}")
        if ocr_result.tables:
            tables.extend(ocr_result.tables)
            table_index += len(ocr_result.tables)
    return results, tables, list(dict.fromkeys(warnings))


def run_ocr(
    path: str | Path,
    table_index_offset: int = 0,
    source_label: str | None = None,
    page_index: int | None = None,
    image_index: int = 1,
) -> OcrResult:
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
    vision_result = run_vision_ocr(
        image_path=target,
        source_label=source_label or str(target),
        page_index=page_index,
        image_index=image_index,
    )
    warnings.extend(vision_result.warnings)
    merged_text = _merge_ocr_text(best_text, vision_result)
    tables = _merge_ocr_tables(tables, vision_result, table_index_offset)
    return OcrResult(
        text=merged_text,
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


def _merge_ocr_text(local_text: str, vision_result) -> str:
    parts = [part.strip() for part in [local_text, vision_result.extracted_text] if part and part.strip()]
    if vision_result.summary:
        parts.append(f"[视觉OCR摘要] {vision_result.summary}")
    if vision_result.doc_type:
        parts.append(f"[视觉OCR类型] {vision_result.doc_type}")
    return "\n".join(dict.fromkeys(parts))


def _merge_ocr_tables(
    local_tables: list[ParsedTable],
    vision_result,
    table_index_offset: int,
) -> list[ParsedTable]:
    if local_tables:
        return local_tables
    headers = vision_result.fields.get("table_headers") if isinstance(vision_result.fields, dict) else None
    if isinstance(headers, list) and len(headers) >= 2:
        return [
            ParsedTable(
                table_index=table_index_offset + 1,
                row_count=1,
                rows=[[str(item).strip() for item in headers if str(item).strip()]],
                source="vision_ocr_table",
            )
        ]
    return local_tables

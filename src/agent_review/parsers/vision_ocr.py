from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..llm.client import OpenAICompatibleClient, QwenLocalConfig


OCR_VISION_SYSTEM_PROMPT = """你是政府采购审查场景下的 OCR 与图片信息抽取助手。

你的任务不是判断是否合规，而是忠实描述图片内容，并提取对后续审查有用的结构化信息。

要求：
1. 只根据图片内容回答，不要臆测看不清的内容。
2. 优先识别图片类型，例如：报价表、评分表、签章页、盖章页、授权书、营业执照、合同页、声明函页、其他。
3. 输出必须是 JSON 对象，不要使用 Markdown 代码块。
4. 如果某项识别不出来，使用空字符串、空对象或 null。
5. extracted_text 尽量保留图片中的原文关键信息。
6. fields 里优先保留对招标审查有价值的字段，例如 company_name、amount、brand、model、manufacturer、signature_present、seal_present、table_headers。
"""


@dataclass(slots=True)
class VisionOcrResult:
    doc_type: str
    summary: str
    extracted_text: str
    fields: dict[str, object] = field(default_factory=dict)
    confidence: float | None = None
    warnings: list[str] = field(default_factory=list)


def run_vision_ocr(
    image_path: str | Path,
    source_label: str,
    page_index: int | None = None,
    image_index: int = 1,
    client: OpenAICompatibleClient | None = None,
) -> VisionOcrResult:
    ocr_client = client or OpenAICompatibleClient(QwenLocalConfig.from_env_or_default())
    prompt = build_ocr_user_prompt(
        source_label=source_label,
        page_index=page_index,
        image_index=image_index,
    )
    try:
        raw = ocr_client.generate_vision_text(
            system_prompt=OCR_VISION_SYSTEM_PROMPT,
            user_prompt=prompt,
            image_path=image_path,
        )
        payload = _parse_json_response(raw)
        return VisionOcrResult(
            doc_type=str(payload.get("doc_type", "")).strip(),
            summary=str(payload.get("summary", "")).strip(),
            extracted_text=str(payload.get("extracted_text", "")).strip(),
            fields=dict(payload.get("fields") or {}),
            confidence=_coerce_confidence(payload.get("confidence")),
            warnings=[],
        )
    except Exception as exc:
        return VisionOcrResult(
            doc_type="",
            summary="",
            extracted_text="",
            fields={},
            confidence=None,
            warnings=[f"视觉 OCR 未生效: {exc}"],
        )


def build_ocr_user_prompt(
    source_label: str,
    page_index: int | None,
    image_index: int,
) -> str:
    page_text = f"第 {page_index} 页" if page_index is not None else "无页码信息"
    return f"""请识别这张图片中的信息。

来源文件：{source_label}
页码：{page_text}
图片序号：{image_index}

请严格输出如下 JSON 结构：
{{
  "doc_type": "图片类型",
  "summary": "对图片主要内容的简短描述",
  "extracted_text": "尽量忠实提取的关键信息原文",
  "fields": {{
    "company_name": "",
    "amount": "",
    "manufacturer": "",
    "brand": "",
    "model": "",
    "table_headers": [],
    "signature_present": null,
    "seal_present": null
  }},
  "confidence": 0.0
}}
"""


def _parse_json_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            return json.loads(match.group(0))
        return {
            "doc_type": "unknown",
            "summary": text[:120],
            "extracted_text": text,
            "fields": {},
            "confidence": None,
        }


def _coerce_confidence(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

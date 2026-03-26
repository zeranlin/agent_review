from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import EffectTag, ReviewReport
from .ontology import SemanticZoneType


@dataclass(slots=True)
class HeaderInfo:
    project_name: str
    project_code: str
    purchaser_name: str


def resolve_header_info(report: ReviewReport) -> HeaderInfo:
    return HeaderInfo(
        project_name=_resolve_project_name(report),
        project_code=_resolve_project_code(report),
        purchaser_name=_resolve_purchaser_name(report),
    )


def _resolve_project_name(report: ReviewReport) -> str:
    candidates = []
    for clause in report.extracted_clauses:
        if clause.field_name != "项目名称":
            continue
        value = _extract_project_name_value(clause.content)
        if not value:
            continue
        candidates.append((value, _score_project_name_candidate(clause.content, clause.source_anchor, clause)))
    text_value = _search_text_value(
        report.parse_result.text or "",
        [
            r"项目名称[:：]\s*([^\n]+)",
            r"项目名称\s*\|\s*([^\|\n]+)",
        ],
    )
    if text_value:
        candidates.append((text_value, 120))
    if not candidates:
        return Path(report.file_info.document_name).stem
    candidates.sort(key=lambda item: (-item[1], len(item[0])))
    return candidates[0][0]


def _resolve_purchaser_name(report: ReviewReport) -> str:
    candidates = []
    for clause in report.extracted_clauses:
        value = _extract_purchaser_value(clause.content)
        if not value:
            continue
        candidates.append((value, _score_purchaser_candidate(clause.content, clause.source_anchor, clause)))
    text_value = _search_text_value(
        report.parse_result.text or "",
        [
            r"采购人(?:名称)?[:：]\s*([^\n]+)",
            r"采购单位[:：]\s*([^\n]+)",
            r"(?:^|\n)\s*\d+(?:\.\d+)?\s*\|\s*采购人\s*\|\s*([^\|\n]+)",
            r"(?:^|\n)\s*\d+(?:\.\d+)?\s*\|\s*采购单位\s*\|\s*([^\|\n]+)",
        ],
    )
    if text_value:
        candidates.append((text_value, 120))
    if not candidates:
        return "未自动识别"
    candidates.sort(key=lambda item: (-item[1], len(item[0])))
    return candidates[0][0]


def _resolve_project_code(report: ReviewReport) -> str:
    candidates = []
    for clause in report.extracted_clauses:
        if clause.field_name != "项目编号":
            continue
        value = _extract_project_code_value(clause.content)
        if not value:
            continue
        candidates.append((value, _score_project_code_candidate(clause.content, clause.source_anchor)))
    text_value = _search_text_value(
        report.parse_result.text or "",
        [
            r"项目编号[:：]\s*([^\n]+)",
            r"项目编号\s*\|\s*([^\|\n]+)",
        ],
    )
    if text_value:
        candidates.append((text_value, 120))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[1], len(item[0])))
    return candidates[0][0]


def _extract_project_name_value(text: str) -> str:
    cleaned = _strip_field_prefix(text, "项目名称")
    cleaned = _clean_header_value(cleaned)
    if not cleaned:
        return ""
    if any(token in cleaned for token in _PROJECT_NAME_REJECT_TOKENS):
        return ""
    return cleaned


def _extract_purchaser_value(text: str) -> str:
    patterns = [
        r"(?:^|\|)\s*采购人(?:名称)?\s*(?:[:：]|\|)\s*([^\|\n]+)",
        r"(?:^|\|)\s*采购单位\s*(?:[:：]|\|)\s*([^\|\n]+)",
        r"采购人(?:名称)?[:：]\s*([^\n]+)",
        r"采购单位[:：]\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        cleaned = _clean_header_value(match.group(1))
        if not cleaned:
            continue
        if any(token in cleaned for token in _PURCHASER_REJECT_TOKENS):
            continue
        return cleaned
    return ""


def _extract_project_code_value(text: str) -> str:
    cleaned = _strip_field_prefix(text, "项目编号")
    cleaned = _clean_header_value(cleaned)
    if not cleaned:
        return ""
    if any(token in cleaned for token in _PROJECT_CODE_REJECT_TOKENS):
        return ""
    return cleaned


def _score_project_name_candidate(text: str, anchor: str, clause) -> int:
    score = 0
    value = _extract_project_name_value(text)
    if not value:
        return -999
    if clause.semantic_zone == SemanticZoneType.administrative_info:
        score += 160
    if clause.semantic_zone == SemanticZoneType.template:
        score -= 120
    if EffectTag.template in clause.effect_tags:
        score -= 120
    if any(token in text for token in _PROJECT_NAME_REJECT_TOKENS):
        score -= 300
    if re.match(r"^\s*项目名称[:：]", text):
        score += 140
    if " | " in text and "项目名称" in text:
        score += 60
    score += _score_anchor(anchor)
    if len(value) > 60:
        score -= 80
    return score


def _score_purchaser_candidate(text: str, anchor: str, clause) -> int:
    score = 0
    value = _extract_purchaser_value(text)
    if not value:
        return -999
    if clause.semantic_zone in {SemanticZoneType.administrative_info, SemanticZoneType.contract}:
        score += 100
    if clause.semantic_zone == SemanticZoneType.template:
        score -= 160
    if EffectTag.template in clause.effect_tags:
        score -= 160
    if any(token in text for token in _PURCHASER_REJECT_CONTEXT_TOKENS):
        score -= 260
    if " | 采购人 | " in text or " | 采购单位 | " in text:
        score += 180
    if re.search(r"采购人(?:名称)?[:：]", text) or re.search(r"采购单位[:：]", text):
        score += 100
    score += _score_anchor(anchor)
    if len(value) > 40:
        score -= 40
    return score


def _score_project_code_candidate(text: str, anchor: str) -> int:
    score = 0
    value = _extract_project_code_value(text)
    if not value:
        return -999
    if re.match(r"^\s*项目编号[:：]", text):
        score += 140
    if " | " in text and "项目编号" in text:
        score += 60
    if any(token in text for token in _PROJECT_CODE_REJECT_TOKENS):
        score -= 300
    score += _score_anchor(anchor)
    if len(value) > 80:
        score -= 40
    return score


def _score_anchor(anchor: str) -> int:
    match = re.search(r"line:(\d+)", anchor or "")
    if not match:
        return 0
    line_no = int(match.group(1))
    if line_no <= 10:
        return 120
    if line_no <= 30:
        return 80
    if line_no <= 80:
        return 30
    return max(0, 20 - min(line_no, 200) // 20)


def _search_text_value(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        cleaned = _clean_header_value(match.group(1))
        if cleaned:
            return cleaned
    return ""


def _strip_field_prefix(text: str, field_name: str) -> str:
    cleaned = re.sub(rf"^\s*{re.escape(field_name)}\s*[:：]?\s*", "", text).strip()
    if " | " in cleaned:
        parts = [item.strip(" ：:|") for item in cleaned.split("|") if item.strip(" ：:|")]
        if parts:
            return parts[-1]
    return cleaned.strip(" ：:|")


def _clean_header_value(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip(" ：:;；,，。|")
    text = re.sub(r"^[（(][^)）]{0,20}[)）]\s*", "", text)
    return text.strip()


_PROJECT_NAME_REJECT_TOKENS = {
    "投标样品",
    "样品名称",
    "项目名称及项目编号",
    "下划线处如实填写",
    "采购活动",
}

_PROJECT_CODE_REJECT_TOKENS = {
    "项目名称及项目编号",
    "导入《投标文件制作软件》",
    "包号一致",
}

_PURCHASER_REJECT_TOKENS = {
    "采购人名称",
    "深圳公共资源交易中心不是本项目的采购人",
    "国家机关、事业单位、团体组织",
    "指利用财政性资金依法进行政府采购",
}

_PURCHASER_REJECT_CONTEXT_TOKENS = {
    "不是本项目的采购人",
    "“采购人”：指",
    "本投标人参加（采购人名称）",
}

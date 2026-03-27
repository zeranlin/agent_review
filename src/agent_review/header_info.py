from __future__ import annotations

from pathlib import Path
import re

from .models import EffectTag, HeaderInfo, ParseResult, ReviewReport
from .ontology import SemanticZoneType


class _ClauseLike:
    def __init__(self, path: str, effect_tags) -> None:
        self.path = path
        self.effect_tags = effect_tags
        self.semantic_zone = SemanticZoneType.administrative_info if "招标公告" in path or "项目概况" in path else SemanticZoneType.mixed_or_uncertain


def resolve_header_info(report: ReviewReport) -> HeaderInfo:
    project_name = _resolve_project_name(report)
    project_code = _resolve_project_code(report)
    purchaser_name = _resolve_purchaser_name(report)
    agency_name = _resolve_agency_name(report)
    budget_amount = _resolve_amount_field(report, "预算金额")
    max_price = _resolve_amount_field(report, "最高限价")
    return HeaderInfo(
        project_name=project_name,
        project_code=project_code,
        purchaser_name=purchaser_name,
        agency_name=agency_name,
        budget_amount=budget_amount,
        max_price=max_price,
        source_evidence={
            "project_name": "resolver",
            "project_code": "resolver",
            "purchaser_name": "resolver",
            "agency_name": "resolver",
            "budget_amount": "resolver",
            "max_price": "resolver",
        },
        confidence={
            "project_name": 1.0 if project_name else 0.0,
            "project_code": 1.0 if project_code else 0.0,
            "purchaser_name": 1.0 if purchaser_name and purchaser_name != "未自动识别" else 0.0,
            "agency_name": 1.0 if agency_name else 0.0,
            "budget_amount": 1.0 if budget_amount else 0.0,
            "max_price": 1.0 if max_price else 0.0,
        },
    )


def resolve_header_info_from_parse_result(parse_result: ParseResult, *, document_name: str = "") -> HeaderInfo:
    project_name = _resolve_project_name_from_parse_result(parse_result, document_name=document_name)
    project_code = _search_header_text_value(
        parse_result,
        [
            r"项目编号[:：]\s*([^\n]+)",
            r"项目编号\s*\|\s*([^\|\n]+)",
        ],
        extractor=_extract_project_code_value,
    )
    purchaser_name = _search_header_text_value(
        parse_result,
        [
            r"采购人(?:名称)?[:：]\s*([^\n]+)",
            r"采购单位[:：]\s*([^\n]+)",
            r"(?:^|\n)\s*\d+(?:\.\d+)?\s*\|\s*采购人\s*\|\s*([^\|\n]+)",
            r"(?:^|\n)\s*\d+(?:\.\d+)?\s*\|\s*采购单位\s*\|\s*([^\|\n]+)",
        ],
        extractor=_extract_purchaser_value_fragment,
    )
    agency_name = _search_header_text_value(
        parse_result,
        [
            r"采购代理机构(?:名称)?[:：]\s*([^\n]+)",
            r"(?:^|\n)\s*\d+(?:\.\d+)?\s*\|\s*采购代理机构\s*\|\s*([^\|\n]+)",
        ],
        extractor=_extract_agency_value_fragment,
    )
    budget_amount = _search_header_text_value(
        parse_result,
        [
            r"预算金额(?:（元）)?[:：]\s*([^\n]+)",
            r"预算金额\s*\|\s*([^\|\n]+)",
        ],
        extractor=_extract_amount_value,
    )
    max_price = _search_header_text_value(
        parse_result,
        [
            r"最高限价(?:（元）)?[:：]\s*([^\n]+)",
            r"最高限价\s*\|\s*([^\|\n]+)",
        ],
        extractor=_extract_amount_value,
    )
    return HeaderInfo(
        project_name=project_name,
        project_code=project_code,
        purchaser_name=purchaser_name,
        agency_name=agency_name,
        budget_amount=budget_amount,
        max_price=max_price,
        source_evidence={
            "project_name": "parse_result_resolver",
            "project_code": "parse_result_resolver",
            "purchaser_name": "parse_result_resolver",
            "agency_name": "parse_result_resolver",
            "budget_amount": "parse_result_resolver",
            "max_price": "parse_result_resolver",
        },
        confidence={
            "project_name": 1.0 if project_name else 0.0,
            "project_code": 1.0 if project_code else 0.0,
            "purchaser_name": 1.0 if purchaser_name else 0.0,
            "agency_name": 1.0 if agency_name else 0.0,
            "budget_amount": 1.0 if budget_amount else 0.0,
            "max_price": 1.0 if max_price else 0.0,
        },
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


def _resolve_project_name_from_parse_result(parse_result: ParseResult, *, document_name: str = "") -> str:
    candidates: list[tuple[str, int]] = []
    for unit in parse_result.clause_units[:80]:
        if not re.search(r"项目名称[:：]|\|\s*项目名称\s*\|", unit.text):
            continue
        value = _extract_project_name_value(unit.text)
        if not value:
            continue
        anchor = unit.anchor.line_hint or ""
        score = _score_project_name_candidate(unit.text, anchor, _ClauseLike(unit.path, unit.effect_tags))
        candidates.append((value, score))
    text_value = _search_text_value(
        parse_result.text or "",
        [
            r"项目名称[:：]\s*([^\n]+)",
            r"项目名称\s*\|\s*([^\|\n]+)",
        ],
    )
    if text_value:
        candidates.append((text_value, 120))
    if not candidates:
        return Path(document_name or parse_result.source_path).stem
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


def _resolve_agency_name(report: ReviewReport) -> str:
    candidates = []
    for clause in report.extracted_clauses:
        value = _extract_agency_value(clause.content)
        if not value:
            continue
        candidates.append((value, _score_agency_candidate(clause.content, clause.source_anchor, clause)))
    text_value = _search_text_value(
        report.parse_result.text or "",
        [
            r"采购代理机构(?:名称)?[:：]\s*([^\n]+)",
            r"(?:^|\n)\s*\d+(?:\.\d+)?\s*\|\s*采购代理机构\s*\|\s*([^\|\n]+)",
        ],
    )
    if text_value:
        candidates.append((text_value, 120))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[1], len(item[0])))
    return candidates[0][0]


def _resolve_amount_field(report: ReviewReport, field_name: str) -> str:
    candidates = []
    for clause in report.extracted_clauses:
        if clause.field_name != field_name:
            continue
        value = _extract_amount_value(clause.content)
        if not value:
            continue
        candidates.append((value, _score_amount_candidate(clause.content, clause.source_anchor)))
    text_value = _search_text_value(
        report.parse_result.text or "",
        [
            rf"{field_name}(?:（元）)?[:：]\s*([^\n]+)",
            rf"{field_name}\s*\|\s*([^\|\n]+)",
        ],
    )
    normalized = _extract_amount_value(text_value) if text_value else ""
    if normalized:
        candidates.append((normalized, 120))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[1], len(item[0])))
    return candidates[0][0]


def _search_header_text_value(
    parse_result: ParseResult,
    patterns: list[str],
    *,
    extractor,
) -> str:
    candidates: list[str] = []
    for unit in parse_result.clause_units[:120]:
        for pattern in patterns:
            match = re.search(pattern, unit.text)
            if not match:
                continue
            value = extractor(match.group(1))
            if value:
                candidates.append(value)
    text_value = _search_text_value(parse_result.text or "", patterns)
    if text_value:
        normalized = extractor(text_value)
        if normalized:
            candidates.append(normalized)
    if not candidates:
        return ""
    candidates.sort(key=len)
    return candidates[0]


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


def _extract_purchaser_value_fragment(text: str) -> str:
    cleaned = _clean_header_value(text)
    if not cleaned:
        return ""
    if any(token in cleaned for token in _PURCHASER_REJECT_TOKENS):
        return ""
    return cleaned


def _extract_project_code_value(text: str) -> str:
    cleaned = _strip_field_prefix(text, "项目编号")
    cleaned = _clean_header_value(cleaned)
    if not cleaned:
        return ""
    if any(token in cleaned for token in _PROJECT_CODE_REJECT_TOKENS):
        return ""
    return cleaned


def _extract_agency_value(text: str) -> str:
    patterns = [
        r"(?:^|\|)\s*采购代理机构(?:名称)?\s*(?:[:：]|\|)\s*([^\|\n]+)",
        r"采购代理机构(?:名称)?[:：]\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        cleaned = _clean_header_value(match.group(1))
        if not cleaned:
            continue
        if any(token in cleaned for token in _AGENCY_REJECT_TOKENS):
            continue
        return cleaned
    return ""


def _extract_agency_value_fragment(text: str) -> str:
    cleaned = _clean_header_value(text)
    if not cleaned:
        return ""
    if any(token in cleaned for token in _AGENCY_REJECT_TOKENS):
        return ""
    return cleaned


def _extract_amount_value(text: str) -> str:
    if not text:
        return ""
    matches = re.findall(r"\d[\d,]*(?:\.\d+)?", text)
    if not matches:
        return ""
    value = max(matches, key=lambda token: (len(token.replace(",", "")), "." in token)).replace(",", "")
    return value


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


def _score_agency_candidate(text: str, anchor: str, clause) -> int:
    score = 0
    value = _extract_agency_value(text)
    if not value:
        return -999
    if clause.semantic_zone == SemanticZoneType.administrative_info:
        score += 140
    if clause.semantic_zone == SemanticZoneType.template:
        score -= 180
    if EffectTag.template in clause.effect_tags:
        score -= 180
    if re.search(r"采购代理机构(?:名称)?[:：]", text) or " | 采购代理机构 | " in text:
        score += 120
    if any(token in text for token in _AGENCY_REJECT_CONTEXT_TOKENS):
        score -= 260
    score += _score_anchor(anchor)
    return score


def _score_amount_candidate(text: str, anchor: str) -> int:
    score = 0
    value = _extract_amount_value(text)
    if not value:
        return -999
    if any(token in text for token in ["预算金额", "最高限价"]):
        score += 100
    if any(token in text for token in ["（元）", "元"]):
        score += 30
    score += _score_anchor(anchor)
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

_AGENCY_REJECT_TOKENS = {
    "采购代理机构",
}

_AGENCY_REJECT_CONTEXT_TOKENS = {
    "对招标文件拥有最终的解释权",
    "政府集中采购机构",
    "名词解释",
}

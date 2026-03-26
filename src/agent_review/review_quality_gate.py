from __future__ import annotations

import re

from .models import ClauseRole, ExtractedClause, QualityGateStatus, ReviewPoint, ReviewQualityGate
from .ontology import EffectTag, SemanticZoneType


WEAK_EFFECT_TAGS = {
    EffectTag.template,
    EffectTag.example,
    EffectTag.reference_only,
    EffectTag.catalog,
    EffectTag.public_copy_noise,
}

WEAK_ZONE_TYPES = {
    SemanticZoneType.template,
    SemanticZoneType.appendix_reference,
    SemanticZoneType.catalog_or_navigation,
    SemanticZoneType.public_copy_or_noise,
}

PROCUREMENT_SIGNAL_MARKERS = {
    "资格",
    "评分",
    "技术",
    "商务",
    "合同",
    "履约",
    "项目经理",
    "检测报告",
    "证书",
    "售后",
    "驻场",
    "验收",
    "工期",
    "交货",
    "维保",
    "培训",
    "响应",
    "承诺",
    "资质",
    "要求",
    "条件",
    "提供",
    "具备",
    "具有",
    "须",
    "应",
    "必须",
    "不少于",
    "至少",
    "达到",
    "分值",
    "得分",
}

REFERENCE_ONLY_MARKERS = {
    "详见附件",
    "见附件",
    "附件一",
    "附件二",
    "附件三",
    "详见附表",
    "见附表",
    "附表",
    "附录",
    "附件：",
}


def build_review_quality_gates(
    review_points: list[ReviewPoint],
    extracted_clauses: list[ExtractedClause],
) -> list[ReviewQualityGate]:
    results: list[ReviewQualityGate] = []
    seen_by_key: dict[str, str] = {}
    for point in review_points:
        reasons: list[str] = []
        status = QualityGateStatus.passed
        duplicate_of = ""

        if point.evidence_bundle.evidence_level.value == "missing":
            status = QualityGateStatus.manual_confirmation
            reasons.append("当前审查点缺少直接证据。")

        if _point_evidence_is_noise_only(point, extracted_clauses):
            status = QualityGateStatus.filtered
            reasons.append("当前审查点主证据更像法规引用、表格残片或清单串接，暂不进入正式意见。")

        weak_roles = point.evidence_bundle.clause_roles and all(
            role in {
                ClauseRole.form_template,
                ClauseRole.document_definition,
                ClauseRole.appendix_reference,
                ClauseRole.unknown,
            }
            for role in point.evidence_bundle.clause_roles
        )
        if weak_roles and not _point_has_substantive_procurement_signal(point, extracted_clauses):
            status = QualityGateStatus.filtered
            reasons.append(_describe_weak_roles(point.evidence_bundle.clause_roles))

        weak_effect_only = _point_effects_are_weak_only(point, extracted_clauses)
        if weak_effect_only:
            status = QualityGateStatus.filtered
            reasons.append("当前审查点证据主要来自模板、示例或引用性条款，暂不进入正式意见。")

        policy_background_only = _point_policy_background_is_noise_only(point, extracted_clauses)
        if policy_background_only:
            status = QualityGateStatus.filtered
            reasons.append("当前审查点主证据更像政策引用或背景说明，暂不进入正式意见。")

        weak_zone_only = _point_zones_are_weak_only(point, extracted_clauses)
        if weak_zone_only:
            status = QualityGateStatus.filtered
            reasons.append("当前审查点证据主要位于模板、附件或目录噪声区域，暂不进入正式意见。")

        dedupe_key = f"{point.catalog_id}|{_primary_quote(point)}"
        if dedupe_key in seen_by_key:
            status = QualityGateStatus.filtered
            duplicate_of = seen_by_key[dedupe_key]
            reasons.append(f"当前审查点与 {duplicate_of} 证据链重复，已做归并过滤。")
        else:
            seen_by_key[dedupe_key] = point.point_id

        if not reasons:
            reasons.append("当前审查点通过质量关卡。")

        results.append(
            ReviewQualityGate(
                point_id=point.point_id,
                status=status,
                reasons=reasons,
                duplicate_of=duplicate_of,
            )
        )
    return results


def _primary_quote(point: ReviewPoint) -> str:
    evidence = point.evidence_bundle.direct_evidence or point.evidence_bundle.supporting_evidence
    if not evidence:
        return point.title
    return evidence[0].quote


def _point_effects_are_weak_only(
    point: ReviewPoint,
    extracted_clauses: list[ExtractedClause],
) -> bool:
    matched = _matched_clauses(point, extracted_clauses)
    if not matched:
        return False
    all_tags = {tag for clause in matched for tag in clause.effect_tags}
    if not all_tags:
        return False
    return (
        all(tag in WEAK_EFFECT_TAGS for tag in all_tags)
        and EffectTag.binding not in all_tags
        and not _point_has_substantive_procurement_signal(point, extracted_clauses)
    )


def _matched_clauses(point: ReviewPoint, extracted_clauses: list[ExtractedClause]) -> list[ExtractedClause]:
    evidence = point.evidence_bundle.direct_evidence or point.evidence_bundle.supporting_evidence
    quotes = {item.quote for item in evidence if item.quote}
    anchors = {item.section_hint for item in evidence if item.section_hint}
    return [
        clause
        for clause in extracted_clauses
        if clause.source_anchor in anchors
        or clause.content in quotes
        or any(quote and quote[:40] in clause.content for quote in quotes)
    ]


def _point_zones_are_weak_only(
    point: ReviewPoint,
    extracted_clauses: list[ExtractedClause],
) -> bool:
    matched = _matched_clauses(point, extracted_clauses)
    if not matched:
        return False
    return all(clause.semantic_zone in WEAK_ZONE_TYPES for clause in matched) and not _point_has_substantive_procurement_signal(
        point,
        extracted_clauses,
    )


def _point_evidence_is_noise_only(
    point: ReviewPoint,
    extracted_clauses: list[ExtractedClause],
) -> bool:
    family_key = _formal_family_key(point.title)
    evidence = point.evidence_bundle.direct_evidence or point.evidence_bundle.supporting_evidence
    if evidence and all(_quote_looks_like_noise(item.quote, family_key) for item in evidence if item.quote):
        if _point_has_substantive_procurement_signal(point, extracted_clauses):
            return False
        return True
    matched = _matched_clauses(point, extracted_clauses)
    if matched and all(_clause_looks_like_noise(clause, family_key) for clause in matched):
        if _point_has_substantive_procurement_signal(point, extracted_clauses):
            return False
        return True
    return False


def _point_policy_background_is_noise_only(
    point: ReviewPoint,
    extracted_clauses: list[ExtractedClause],
) -> bool:
    evidence = point.evidence_bundle.direct_evidence or point.evidence_bundle.supporting_evidence
    if evidence and all(_quote_looks_like_policy_background(item.quote) for item in evidence if item.quote):
        if _point_has_substantive_procurement_signal(point, extracted_clauses):
            return False
        return True
    matched = _matched_clauses(point, extracted_clauses)
    if matched and all(_clause_looks_like_policy_background(clause) for clause in matched):
        if _point_has_substantive_procurement_signal(point, extracted_clauses):
            return False
        return True
    return False


def _clause_looks_like_noise(clause: ExtractedClause, family_key: str) -> bool:
    text = (clause.content or clause.normalized_value or "").strip()
    if not text:
        return True
    normalized = re.sub(r"\s+", " ", text)
    if _quote_looks_like_legal_citation(normalized):
        return True
    if _quote_looks_like_table_splice(normalized) and family_key not in {"scoring", "score_weight"}:
        return True
    if _quote_looks_like_list_splice(normalized) and family_key not in {"scoring", "score_weight"}:
        return True
    if _quote_looks_like_catalog_navigation(normalized):
        return True
    if _quote_looks_like_policy_background(normalized):
        return True
    if _quote_looks_like_template_noise(normalized):
        return True
    return False


def _quote_looks_like_noise(quote: str, family_key: str) -> bool:
    normalized = re.sub(r"\s+", " ", quote).strip()
    if not normalized:
        return True
    if normalized == "当前自动抽取未定位到可直接引用的原文。":
        return True
    if _quote_looks_like_legal_citation(normalized):
        return True
    if _quote_looks_like_table_splice(normalized) and family_key not in {"scoring", "score_weight"}:
        return True
    if _quote_looks_like_list_splice(normalized) and family_key not in {"scoring", "score_weight"}:
        return True
    if _quote_looks_like_catalog_navigation(normalized):
        return True
    if _quote_looks_like_policy_background(normalized):
        return True
    if _quote_looks_like_template_noise(normalized):
        return True
    return False


def _quote_looks_like_legal_citation(text: str) -> bool:
    return bool(
        ("《" in text and "》" in text and "第" in text and "条" in text)
        or re.search(r"^\s*[一二三四五六七八九十0-9]+、《", text)
        or ("依据" in text and "第" in text and "条" in text)
    )


def _quote_looks_like_table_splice(text: str) -> bool:
    if text.count("|") >= 2 or text.count(" | ") >= 2:
        return True
    numeric_tokens = re.findall(r"\d+", text)
    return len(text) >= 80 and len(numeric_tokens) >= 4 and any(
        token in text for token in ["项目名称", "品目", "规格", "数量", "单价", "分值", "教工宿舍", "拒绝进口"]
    )


def _quote_looks_like_list_splice(text: str) -> bool:
    separator_count = text.count("；") + text.count(";")
    return len(text) >= 100 and separator_count >= 3


def _quote_looks_like_catalog_navigation(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return False
    compact = re.sub(r"\s+", "", normalized)
    if "目录" in normalized and any(token in normalized for token in ["第一章", "第二章", "第三章", "第四章"]):
        return len(compact) < 180
    chapter_hits = sum(1 for token in ["第一章", "第二章", "第三章", "第四章", "第五章", "第六章"] if token in normalized)
    if chapter_hits >= 2 and len(compact) < 180:
        return True
    return bool(
        re.search(r"第[一二三四五六七八九十0-9]+章", normalized)
        and any(token in normalized for token in ["招标公告", "采购需求", "投标文件格式", "合同条款", "评分办法"])
        and len(compact) < 140
    )


def _quote_looks_like_policy_background(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return False
    if _quote_looks_like_legal_citation(normalized):
        return True
    policy_markers = ["根据", "依据", "按照", "参照", "执行", "适用", "规定", "办法", "通知", "财政部", "管理办法"]
    if not any(token in normalized for token in policy_markers):
        return False
    if any(token in normalized for token in ["本项目", "采购标的", "项目属性", "价格扣除", "专门面向中小企业采购", "招标文件", "采购需求"]):
        return False
    return len(normalized) < 180


def _quote_looks_like_reference_only(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return False
    if any(marker in normalized for marker in REFERENCE_ONLY_MARKERS):
        return True
    return bool(re.search(r"附件[一二三四五六七八九十0-9]+", normalized))


def _quote_looks_like_template_noise(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return False
    if _quote_looks_like_catalog_navigation(normalized) or _quote_looks_like_policy_background(normalized):
        return True
    template_markers = [
        "格式",
        "示例",
        "填写",
        "填报",
        "盖章",
        "签字",
        "模板",
        "范本",
        "样例",
        "空白",
        "此处",
        "打印",
        "占位",
        "演示",
    ]
    if not any(marker in normalized for marker in template_markers):
        return False
    if any(marker in normalized for marker in ["示例", "模板", "范本", "样例", "空白", "此处", "打印", "占位", "演示"]):
        return True
    if any(marker in normalized for marker in ["格式", "填写", "填报"]) and any(
        marker in normalized for marker in PROCUREMENT_SIGNAL_MARKERS
    ):
        return True
    if any(marker in normalized for marker in ["资格", "评分", "技术", "商务", "合同", "履约", "项目经理", "检测报告", "证书"]):
        return False
    return True


def _clause_looks_like_policy_background(clause: ExtractedClause) -> bool:
    text = (clause.content or clause.normalized_value or "").strip()
    if not text:
        return True
    normalized = re.sub(r"\s+", " ", text)
    if _quote_looks_like_policy_background(normalized):
        return True
    if clause.semantic_zone == SemanticZoneType.policy_explanation:
        policy_markers = ["根据", "依据", "按照", "参照", "执行", "适用", "规定", "办法", "通知", "财政部", "管理办法"]
        if any(token in normalized for token in policy_markers) and not any(
            token in normalized for token in ["本项目", "采购标的", "项目属性", "价格扣除", "专门面向中小企业采购", "招标文件", "采购需求"]
        ):
            return len(normalized) < 180
    return False


def _point_has_substantive_procurement_signal(
    point: ReviewPoint,
    extracted_clauses: list[ExtractedClause],
) -> bool:
    evidence = point.evidence_bundle.direct_evidence or point.evidence_bundle.supporting_evidence
    texts = [item.quote for item in evidence if item.quote]
    matched = _matched_clauses(point, extracted_clauses)
    texts.extend(
        clause.content or clause.normalized_value or ""
        for clause in matched
        if (clause.content or clause.normalized_value)
    )
    return any(_quote_has_substantive_procurement_signal(text) for text in texts)


def _quote_has_substantive_procurement_signal(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return False
    if _quote_looks_like_template_noise(normalized):
        return False
    if _quote_looks_like_catalog_navigation(normalized) or _quote_looks_like_policy_background(normalized):
        return False
    if _quote_looks_like_reference_only(normalized):
        return False
    if not any(marker in normalized for marker in PROCUREMENT_SIGNAL_MARKERS):
        return False
    if any(marker in normalized for marker in ["目录", "附件", "附表", "附录", "格式", "示例", "填写"]):
        return False
    return True


def _formal_family_key(title: str) -> str:
    if any(token in title for token in ["方案评分", "评分分档", "评分量化"]):
        return "scoring"
    if any(token in title for token in ["证书", "检测报告", "财务指标"]):
        return "score_weight"
    return "generic"


def _describe_weak_roles(clause_roles: list[ClauseRole]) -> str:
    role_set = set(clause_roles)
    if role_set <= {ClauseRole.document_definition, ClauseRole.unknown}:
        return "当前审查点证据主要来自目录或定义说明等弱来源。"
    if role_set <= {ClauseRole.policy_explanation, ClauseRole.unknown}:
        return "当前审查点证据主要来自政策背景或法规说明等弱来源。"
    if role_set <= {ClauseRole.appendix_reference, ClauseRole.unknown}:
        return "当前审查点证据主要来自附件引用等弱来源。"
    return "当前审查点证据主要来自模板、定义或附件引用等弱来源。"

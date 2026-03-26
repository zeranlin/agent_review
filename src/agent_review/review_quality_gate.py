from __future__ import annotations

import re

from .models import ClauseRole, ExtractedClause, QualityGateStatus, ReviewPoint, ReviewQualityGate
from .ontology import EffectTag, SemanticZoneType


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
                ClauseRole.policy_explanation,
                ClauseRole.document_definition,
                ClauseRole.appendix_reference,
                ClauseRole.unknown,
            }
            for role in point.evidence_bundle.clause_roles
        )
        if weak_roles:
            status = QualityGateStatus.filtered
            reasons.append("当前审查点证据主要来自模板、定义或附件引用等弱来源。")

        weak_effect_only = _point_effects_are_weak_only(point, extracted_clauses)
        if weak_effect_only:
            status = QualityGateStatus.filtered
            reasons.append("当前审查点证据主要来自模板、示例或引用性条款，暂不进入正式意见。")

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
    weak_tags = {
        EffectTag.template,
        EffectTag.example,
        EffectTag.reference_only,
    }
    return all(tag in weak_tags for tag in all_tags) and EffectTag.binding not in all_tags


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
    weak_zones = {
        SemanticZoneType.template,
        SemanticZoneType.appendix_reference,
        SemanticZoneType.catalog_or_navigation,
        SemanticZoneType.public_copy_or_noise,
    }
    return all(clause.semantic_zone in weak_zones for clause in matched)


def _point_evidence_is_noise_only(
    point: ReviewPoint,
    extracted_clauses: list[ExtractedClause],
) -> bool:
    family_key = _formal_family_key(point.title)
    evidence = point.evidence_bundle.direct_evidence or point.evidence_bundle.supporting_evidence
    if evidence and all(_quote_looks_like_noise(item.quote, family_key) for item in evidence if item.quote):
        return True
    matched = _matched_clauses(point, extracted_clauses)
    if matched and all(_clause_looks_like_noise(clause, family_key) for clause in matched):
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


def _formal_family_key(title: str) -> str:
    if any(token in title for token in ["方案评分", "评分分档", "评分量化"]):
        return "scoring"
    if any(token in title for token in ["证书", "检测报告", "财务指标"]):
        return "score_weight"
    return "generic"

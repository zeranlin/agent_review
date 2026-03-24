from __future__ import annotations

from .models import (
    ApplicabilityCheck,
    ApplicabilityItem,
    ApplicabilityStatus,
    ExtractedClause,
    ReviewPoint,
)
from .review_point_catalog import resolve_review_point_definition


def build_applicability_checks(
    review_points: list[ReviewPoint],
    extracted_clauses: list[ExtractedClause],
) -> list[ApplicabilityCheck]:
    results: list[ApplicabilityCheck] = []
    clause_mapping = _clause_map(extracted_clauses)
    for point in review_points:
        definition = resolve_review_point_definition(point.title, point.dimension, point.severity)
        haystack = _build_haystack(point, clause_mapping)
        requirement_results: list[ApplicabilityItem] = []
        exclusion_results: list[ApplicabilityItem] = []

        for condition in definition.required_conditions:
            matched, matched_by_fields, matched_fields = _matches_condition(
                haystack, clause_mapping, condition.clause_fields, condition.signal_groups
            )
            status = ApplicabilityStatus.satisfied if matched else ApplicabilityStatus.insufficient
            detail = (
                _matched_detail("要件", matched_by_fields, matched_fields)
                if matched
                else _unmatched_detail("要件", condition.clause_fields)
            )
            requirement_results.append(
                ApplicabilityItem(name=condition.name, status=status, detail=detail)
            )

        for condition in definition.exclusion_conditions:
            matched, matched_by_fields, matched_fields = _matches_condition(
                haystack, clause_mapping, condition.clause_fields, condition.signal_groups
            )
            status = ApplicabilityStatus.excluded if matched else ApplicabilityStatus.not_applicable
            detail = (
                _matched_detail("排除条件", matched_by_fields, matched_fields)
                if matched
                else _unmatched_detail("排除条件", condition.clause_fields)
            )
            exclusion_results.append(
                ApplicabilityItem(name=condition.name, status=status, detail=detail)
            )

        applicable = bool(
            (not requirement_results or all(item.status == ApplicabilityStatus.satisfied for item in requirement_results))
            and not any(item.status == ApplicabilityStatus.excluded for item in exclusion_results)
        )
        summary = _build_summary(requirement_results, exclusion_results, applicable)
        results.append(
            ApplicabilityCheck(
                point_id=point.point_id,
                catalog_id=definition.catalog_id,
                applicable=applicable,
                requirement_results=requirement_results,
                exclusion_results=exclusion_results,
                summary=summary,
            )
        )
    return results


def _build_haystack(point: ReviewPoint, clause_mapping: dict[str, list[ExtractedClause]]) -> str:
    texts = [point.title, point.rationale]
    texts.extend(item.quote for item in point.evidence_bundle.direct_evidence)
    texts.extend(item.quote for item in point.evidence_bundle.supporting_evidence)
    texts.extend(item.quote for item in point.evidence_bundle.conflicting_evidence)
    texts.extend(item.quote for item in point.evidence_bundle.rebuttal_evidence)
    for sources in point.source_findings:
        if sources.startswith("risk_hit:"):
            texts.append(sources.replace("risk_hit:", "", 1))
    texts.extend(
        clause.content
        for clauses in clause_mapping.values()
        for clause in clauses
        if clause.source_anchor in {
            evidence.section_hint
            for evidence in (
                point.evidence_bundle.direct_evidence
                + point.evidence_bundle.supporting_evidence
                + point.evidence_bundle.conflicting_evidence
                + point.evidence_bundle.rebuttal_evidence
            )
        }
    )
    return " ".join(texts)


def _matches_condition(
    haystack: str,
    clause_mapping: dict[str, list[ExtractedClause]],
    clause_fields: list[str],
    signal_groups: list[list[str]],
) -> tuple[bool, bool, list[str]]:
    matched_fields = [field for field in clause_fields if clause_mapping.get(field)]
    fields_ok = not clause_fields or len(matched_fields) == len(clause_fields)
    signals_ok = not signal_groups or all(any(token and token in haystack for token in group) for group in signal_groups)
    return fields_ok and signals_ok, bool(matched_fields), matched_fields


def _build_summary(
    requirement_results: list[ApplicabilityItem],
    exclusion_results: list[ApplicabilityItem],
    applicable: bool,
) -> str:
    satisfied = sum(1 for item in requirement_results if item.status == ApplicabilityStatus.satisfied)
    excluded = any(item.status == ApplicabilityStatus.excluded for item in exclusion_results)
    if applicable:
        return f"要件满足 {satisfied} 项，未命中排除条件，可进入 formal 适法性判断。"
    if excluded:
        return "已命中排除条件，当前审查点不宜直接 formal 定性。"
    if requirement_results:
        return f"当前仅满足 {satisfied}/{len(requirement_results)} 项要件，需补充证据或人工确认。"
    return "当前目录项尚未配置细化要件，暂按通用审查点处理。"


def _clause_map(clauses: list[ExtractedClause]) -> dict[str, list[ExtractedClause]]:
    mapping: dict[str, list[ExtractedClause]] = {}
    for clause in clauses:
        mapping.setdefault(clause.field_name, []).append(clause)
    return mapping


def _matched_detail(prefix: str, matched_by_fields: bool, matched_fields: list[str]) -> str:
    if matched_by_fields and matched_fields:
        return f"已通过结构化字段命中该{prefix}：{', '.join(matched_fields)}。"
    return f"已在当前审查点证据或理由中定位到该{prefix}信号。"


def _unmatched_detail(prefix: str, clause_fields: list[str]) -> str:
    if clause_fields:
        return f"当前结构化条款中尚未完整满足该{prefix}字段要求：{', '.join(clause_fields)}。"
    return f"当前审查点证据中尚未完整定位到该{prefix}信号。"

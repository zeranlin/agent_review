from __future__ import annotations

from .models import (
    ApplicabilityCheck,
    ApplicabilityItem,
    ApplicabilityStatus,
    ReviewPoint,
)
from .review_point_catalog import resolve_review_point_definition


def build_applicability_checks(review_points: list[ReviewPoint]) -> list[ApplicabilityCheck]:
    results: list[ApplicabilityCheck] = []
    for point in review_points:
        definition = resolve_review_point_definition(point.title, point.dimension, point.severity)
        haystack = _build_haystack(point)
        requirement_results: list[ApplicabilityItem] = []
        exclusion_results: list[ApplicabilityItem] = []

        for condition in definition.required_conditions:
            matched = _matches_condition(haystack, condition.signal_groups)
            status = ApplicabilityStatus.satisfied if matched else ApplicabilityStatus.insufficient
            detail = (
                "已在当前审查点证据或理由中定位到该要件信号。"
                if matched
                else "当前审查点证据中尚未完整定位到该要件信号。"
            )
            requirement_results.append(
                ApplicabilityItem(name=condition.name, status=status, detail=detail)
            )

        for condition in definition.exclusion_conditions:
            matched = _matches_condition(haystack, condition.signal_groups)
            status = ApplicabilityStatus.excluded if matched else ApplicabilityStatus.not_applicable
            detail = (
                "已命中排除条件，需谨慎避免直接 formal 定性。"
                if matched
                else "未命中该排除条件。"
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


def _build_haystack(point: ReviewPoint) -> str:
    texts = [point.title, point.rationale]
    texts.extend(item.quote for item in point.evidence_bundle.direct_evidence)
    texts.extend(item.quote for item in point.evidence_bundle.supporting_evidence)
    texts.extend(item.quote for item in point.evidence_bundle.conflicting_evidence)
    texts.extend(item.quote for item in point.evidence_bundle.rebuttal_evidence)
    return " ".join(texts)


def _matches_condition(haystack: str, signal_groups: list[list[str]]) -> bool:
    if not signal_groups:
        return True
    return all(any(token and token in haystack for token in group) for group in signal_groups)


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

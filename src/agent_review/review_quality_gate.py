from __future__ import annotations

from .models import ClauseRole, QualityGateStatus, ReviewPoint, ReviewQualityGate


def build_review_quality_gates(review_points: list[ReviewPoint]) -> list[ReviewQualityGate]:
    results: list[ReviewQualityGate] = []
    seen_by_key: dict[str, str] = {}
    for point in review_points:
        reasons: list[str] = []
        status = QualityGateStatus.passed
        duplicate_of = ""

        if point.evidence_bundle.evidence_level.value == "missing":
            status = QualityGateStatus.manual_confirmation
            reasons.append("当前审查点缺少直接证据。")

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

from __future__ import annotations

from collections.abc import Iterable

from .models import (
    ClauseRole,
    ConsistencyCheck,
    Evidence,
    EvidenceBundle,
    ExtractedClause,
    Finding,
    FindingType,
    FormalAdjudication,
    FormalDisposition,
    LegalBasis,
    RiskHit,
    ReviewPoint,
    ReviewPointStatus,
    Severity,
)
from .quality import infer_evidence_roles, is_formal_eligible


def build_review_points(
    findings: list[Finding],
    report_text: str,
    extracted_clauses: list[ExtractedClause],
) -> list[ReviewPoint]:
    return build_review_points_from_findings(findings, report_text, extracted_clauses)


def build_review_points_from_findings(
    findings: list[Finding],
    report_text: str,
    extracted_clauses: list[ExtractedClause],
) -> list[ReviewPoint]:
    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        if finding.title.strip():
            key = f"{finding.dimension}|{finding.title}"
            grouped.setdefault(key, []).append(finding)

    review_points: list[ReviewPoint] = []
    for index, (_, group) in enumerate(grouped.items(), start=1):
        primary = sorted(
            group,
            key=lambda item: (
                {"critical": 0, "high": 1, "medium": 2, "low": 3}[item.severity.value],
                0 if item.finding_type.value == "confirmed_issue" else 1,
            ),
        )[0]
        bundle = build_evidence_bundle(group, report_text, extracted_clauses)
        review_points.append(
            ReviewPoint(
                point_id=f"RP-{index:03d}",
                title=primary.title,
                dimension=primary.dimension,
                severity=primary.severity,
                status=_derive_review_point_status(primary, bundle),
                rationale=primary.rationale,
                evidence_bundle=bundle,
                legal_basis=primary.legal_basis,
                source_findings=[
                    f"finding:{item.finding_type.value}:{item.title}" for item in group
                ],
            )
        )
    return review_points


def build_review_points_from_risk_hits(
    risk_hits: Iterable[RiskHit],
) -> list[ReviewPoint]:
    review_points: list[ReviewPoint] = []
    for index, hit in enumerate(risk_hits, start=1):
        direct = []
        if hit.matched_text:
            direct.append(Evidence(quote=hit.matched_text, section_hint=hit.source_anchor))
        bundle = EvidenceBundle(
            direct_evidence=direct,
            supporting_evidence=[],
            conflicting_evidence=[],
            missing_evidence_notes=[] if direct else [f"{hit.rule_name} 当前未抽到直接证据。"],
            clause_roles=[],
            sufficiency_summary=(
                "规则命中已提供直接证据，可进入后续裁决。"
                if direct
                else "规则命中尚缺直接证据，需补充原文定位。"
            ),
        )
        review_points.append(
            ReviewPoint(
                point_id=f"RULE-{index:03d}",
                title=hit.rule_name,
                dimension=hit.risk_group,
                severity=hit.severity,
                status=(
                    ReviewPointStatus.confirmed
                    if hit.severity in {Severity.high, Severity.critical}
                    else ReviewPointStatus.suspected
                ),
                rationale=hit.rationale,
                evidence_bundle=bundle,
                legal_basis=hit.legal_basis,
                source_findings=[f"risk_hit:{hit.rule_name}"],
            )
        )
    return review_points


def build_review_points_from_consistency_checks(
    checks: Iterable[ConsistencyCheck],
) -> list[ReviewPoint]:
    review_points: list[ReviewPoint] = []
    for index, check in enumerate(checks, start=1):
        if check.status != "issue":
            continue
        review_points.append(
            ReviewPoint(
                point_id=f"CONS-{index:03d}",
                title=check.topic,
                dimension="跨条款一致性检查",
                severity=Severity.high,
                status=ReviewPointStatus.suspected,
                rationale=check.detail,
                evidence_bundle=EvidenceBundle(
                    direct_evidence=[],
                    supporting_evidence=[],
                    conflicting_evidence=[],
                    missing_evidence_notes=[f"{check.topic} 当前未形成可直接引用的冲突条款。"],
                    clause_roles=[],
                    sufficiency_summary="当前为一致性疑点，需结合原文或附件补充直接证据。",
                ),
                legal_basis=check.legal_basis,
                source_findings=[f"consistency_check:{check.topic}"],
            )
        )
    return review_points


def merge_review_points(review_points: Iterable[ReviewPoint]) -> list[ReviewPoint]:
    grouped: dict[str, list[ReviewPoint]] = {}
    for point in review_points:
        key = f"{point.dimension}|{point.title}"
        grouped.setdefault(key, []).append(point)

    merged: list[ReviewPoint] = []
    for index, (_, group) in enumerate(grouped.items(), start=1):
        primary = sorted(
            group,
            key=lambda item: (
                _severity_rank(item.severity),
                _status_rank(item.status),
            ),
        )[0]
        merged.append(
            ReviewPoint(
                point_id=f"RP-{index:03d}",
                title=primary.title,
                dimension=primary.dimension,
                severity=primary.severity,
                status=primary.status,
                rationale=_pick_rationale(group),
                evidence_bundle=_merge_evidence_bundles([item.evidence_bundle for item in group]),
                legal_basis=_merge_legal_basis(group),
                source_findings=_dedupe_strings(
                    source
                    for item in group
                    for source in item.source_findings
                ),
            )
        )
    return merged


def convert_review_points_to_findings(
    review_points: Iterable[ReviewPoint],
) -> list[Finding]:
    findings: list[Finding] = []
    for point in review_points:
        evidence = point.evidence_bundle.direct_evidence or point.evidence_bundle.supporting_evidence[:2]
        finding_type = _finding_type_from_review_point(point)
        next_action = (
            "结合直接证据与关联条款做最终裁决。"
            if point.status == ReviewPointStatus.confirmed
            else "补充原文、附件或跨章节证据后再决定是否正式定性。"
        )
        findings.append(
            Finding(
                dimension=point.dimension,
                finding_type=finding_type,
                severity=point.severity,
                title=point.title,
                rationale=point.rationale,
                evidence=evidence,
                legal_basis=point.legal_basis,
                confidence=_confidence_from_review_point(point),
                next_action=next_action,
            )
        )
    return findings


def build_formal_adjudication(
    review_points: list[ReviewPoint],
    findings: list[Finding],
    report_text: str,
    extracted_clauses: list[ExtractedClause],
) -> list[FormalAdjudication]:
    finding_index = {(item.dimension, item.title): item for item in findings}
    results: list[FormalAdjudication] = []
    for point in review_points:
        finding = finding_index.get((point.dimension, point.title))
        if finding is None:
            results.append(
                FormalAdjudication(
                    point_id=point.point_id,
                    title=point.title,
                    disposition=FormalDisposition.filtered_out,
                    rationale="当前审查点尚未绑定原始 finding，暂不进入正式输出。",
                    included_in_formal=False,
                )
            )
            continue

        eligible = is_formal_eligible(finding, report_text, extracted_clauses)
        if eligible:
            disposition = FormalDisposition.include
            rationale = "证据锚点、条款角色和问题标题已通过正式输出过滤，可进入正式意见。"
        elif point.status == ReviewPointStatus.manual_confirmation:
            disposition = FormalDisposition.manual_confirmation
            rationale = "当前审查点证据尚不充分或存在弱证据来源，应进入人工确认而非正式定性。"
        else:
            disposition = FormalDisposition.filtered_out
            rationale = "当前审查点未通过正式输出过滤，暂不进入正式意见。"
        results.append(
            FormalAdjudication(
                point_id=point.point_id,
                title=point.title,
                disposition=disposition,
                rationale=rationale,
                included_in_formal=eligible,
            )
        )
    return results


def build_evidence_bundle(
    findings: list[Finding],
    report_text: str,
    extracted_clauses: list[ExtractedClause],
) -> EvidenceBundle:
    direct_evidence: list[Evidence] = []
    supporting_evidence: list[Evidence] = []
    clause_roles: list[ClauseRole] = []
    missing_notes: list[str] = []

    for finding in findings:
        if finding.evidence:
            if not direct_evidence:
                direct_evidence.extend(finding.evidence[:1])
            else:
                supporting_evidence.extend(finding.evidence[:2])
            clause_roles.extend(infer_evidence_roles(report_text, extracted_clauses, finding))
        else:
            missing_notes.append(f"{finding.title} 当前未抽到直接证据。")

    if direct_evidence:
        sufficiency_summary = "已汇集直接证据，可作为后续裁决基础。"
    elif supporting_evidence:
        sufficiency_summary = "仅有弱证据或辅助证据，需补充直接条款。"
    else:
        sufficiency_summary = "当前缺少可直接引用的证据，需人工补证。"

    dedup_roles: list[ClauseRole] = []
    seen = set()
    for role in clause_roles:
        if role not in seen:
            dedup_roles.append(role)
            seen.add(role)

    return EvidenceBundle(
        direct_evidence=direct_evidence,
        supporting_evidence=supporting_evidence,
        conflicting_evidence=[],
        missing_evidence_notes=missing_notes,
        clause_roles=dedup_roles,
        sufficiency_summary=sufficiency_summary,
    )


def _derive_review_point_status(
    finding: Finding,
    bundle: EvidenceBundle,
) -> ReviewPointStatus:
    if finding.finding_type.value == "confirmed_issue" and bundle.direct_evidence:
        return ReviewPointStatus.confirmed
    if finding.finding_type.value == "manual_review_required" or not bundle.direct_evidence:
        return ReviewPointStatus.manual_confirmation
    if finding.finding_type.value == "warning":
        return ReviewPointStatus.suspected
    return ReviewPointStatus.identified


def _merge_evidence_bundles(bundles: Iterable[EvidenceBundle]) -> EvidenceBundle:
    direct = _dedupe_evidence(
        evidence
        for bundle in bundles
        for evidence in bundle.direct_evidence
    )
    supporting = _dedupe_evidence(
        evidence
        for bundle in bundles
        for evidence in bundle.supporting_evidence
    )
    conflicting = _dedupe_evidence(
        evidence
        for bundle in bundles
        for evidence in bundle.conflicting_evidence
    )
    clause_roles = _dedupe_clause_roles(
        role
        for bundle in bundles
        for role in bundle.clause_roles
    )
    missing_notes = _dedupe_strings(
        note
        for bundle in bundles
        for note in bundle.missing_evidence_notes
        if note
    )
    if direct:
        summary = "已汇集直接证据，可作为正式裁决基础。"
    elif supporting:
        summary = "目前以辅助证据为主，需进一步补强直接条款。"
    else:
        summary = "当前缺少可直接引用的证据，需补证或人工确认。"
    return EvidenceBundle(
        direct_evidence=direct,
        supporting_evidence=supporting,
        conflicting_evidence=conflicting,
        missing_evidence_notes=missing_notes,
        clause_roles=clause_roles,
        sufficiency_summary=summary,
    )


def _merge_legal_basis(review_points: Iterable[ReviewPoint]) -> list[LegalBasis]:
    seen: set[tuple[str, str, str, str]] = set()
    merged: list[LegalBasis] = []
    for point in review_points:
        for basis in point.legal_basis:
            key = (
                basis.source_name,
                basis.article_hint,
                basis.summary,
                basis.basis_type,
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(basis)
    return merged


def _dedupe_evidence(evidence_iter: Iterable[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, str]] = set()
    result: list[Evidence] = []
    for item in evidence_iter:
        key = (item.quote, item.section_hint)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dedupe_clause_roles(role_iter: Iterable[ClauseRole]) -> list[ClauseRole]:
    seen: set[ClauseRole] = set()
    result: list[ClauseRole] = []
    for role in role_iter:
        if role in seen:
            continue
        seen.add(role)
        result.append(role)
    return result


def _dedupe_strings(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _severity_rank(severity: Severity) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}[severity.value]


def _status_rank(status: ReviewPointStatus) -> int:
    return {
        ReviewPointStatus.confirmed: 0,
        ReviewPointStatus.manual_confirmation: 1,
        ReviewPointStatus.suspected: 2,
        ReviewPointStatus.identified: 3,
    }[status]


def _pick_rationale(points: Iterable[ReviewPoint]) -> str:
    candidates = [item.rationale.strip() for item in points if item.rationale.strip()]
    if not candidates:
        return ""
    return sorted(candidates, key=len, reverse=True)[0]


def _finding_type_from_review_point(point: ReviewPoint) -> FindingType:
    source_types = {
        item.split(":", 2)[1]
        for item in point.source_findings
        if item.startswith("finding:") and item.count(":") >= 2
    }
    if FindingType.missing_evidence.value in source_types:
        return FindingType.missing_evidence
    if FindingType.manual_review_required.value in source_types:
        return FindingType.manual_review_required
    if FindingType.confirmed_issue.value in source_types:
        return FindingType.confirmed_issue
    if FindingType.pass_.value in source_types:
        return FindingType.pass_

    status = point.status
    if status == ReviewPointStatus.confirmed:
        return FindingType.confirmed_issue
    if status == ReviewPointStatus.manual_confirmation:
        return FindingType.manual_review_required
    if status == ReviewPointStatus.identified:
        return FindingType.pass_
    return FindingType.warning


def _confidence_from_review_point(point: ReviewPoint) -> float:
    base = {
        ReviewPointStatus.confirmed: 0.82,
        ReviewPointStatus.suspected: 0.70,
        ReviewPointStatus.manual_confirmation: 0.58,
        ReviewPointStatus.identified: 0.55,
    }[point.status]
    if point.evidence_bundle.direct_evidence:
        return min(0.92, base + 0.06)
    if point.evidence_bundle.supporting_evidence:
        return min(0.88, base + 0.03)
    return base

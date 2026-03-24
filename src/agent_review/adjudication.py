from __future__ import annotations

from .models import (
    ClauseRole,
    Evidence,
    EvidenceBundle,
    ExtractedClause,
    Finding,
    FormalAdjudication,
    FormalDisposition,
    ReviewPoint,
    ReviewPointStatus,
)
from .quality import infer_evidence_roles, is_formal_eligible


def build_review_points(
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
    for index, (key, group) in enumerate(grouped.items(), start=1):
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
                source_findings=[item.title for item in group],
            )
        )
    return review_points


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

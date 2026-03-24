from __future__ import annotations

from collections.abc import Iterable

from .applicability import build_applicability_checks
from .fact_collectors import collect_task_facts
from .models import (
    ApplicabilityCheck,
    ClauseRole,
    ConsistencyCheck,
    Evidence,
    EvidenceLevel,
    EvidenceBundle,
    ExtractedClause,
    Finding,
    FindingType,
    FormalAdjudication,
    FormalDisposition,
    LegalBasis,
    QualityGateStatus,
    RiskHit,
    ReviewPoint,
    ReviewPointStatus,
    ReviewQualityGate,
    Severity,
)
from .quality import evidence_supports_title, infer_evidence_roles, infer_role_from_text, line_text_from_anchor, search_line_by_keyword
from .review_point_catalog import resolve_review_point_definition, select_standard_review_tasks, snapshot_catalog_for_points
from .review_quality_gate import build_review_quality_gates


def build_review_points(
    findings: list[Finding],
    report_text: str,
    extracted_clauses: list[ExtractedClause],
) -> list[ReviewPoint]:
    return build_review_points_from_findings(findings, report_text, extracted_clauses)


def build_review_points_from_task_library(
    report_text: str,
    extracted_clauses: list[ExtractedClause],
) -> list[ReviewPoint]:
    task_definitions = select_standard_review_tasks(report_text, extracted_clauses)
    review_points: list[ReviewPoint] = []
    for index, definition in enumerate(task_definitions, start=1):
        evidence_bundle, status, rationale = collect_task_facts(definition, extracted_clauses)
        review_points.append(
            ReviewPoint(
                point_id=f"TASK-{index:03d}",
                catalog_id=definition.catalog_id,
                title=definition.title,
                dimension=definition.dimension,
                severity=definition.default_severity,
                status=status,
                rationale=rationale,
                evidence_bundle=evidence_bundle,
                legal_basis=[],
                source_findings=[f"task_library:{definition.catalog_id}"],
            )
        )
    return review_points


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
                catalog_id=resolve_review_point_definition(
                    primary.title,
                    primary.dimension,
                    primary.severity,
                ).catalog_id,
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
            rebuttal_evidence=[],
            missing_evidence_notes=[] if direct else [f"{hit.rule_name} 当前未抽到直接证据。"],
            clause_roles=[],
            sufficiency_summary=(
                "规则命中已提供直接证据，可进入后续裁决。"
                if direct
                else "规则命中尚缺直接证据，需补充原文定位。"
            ),
            evidence_level=_derive_evidence_level(direct, []),
            evidence_score=_derive_evidence_score(direct, []),
        )
        review_points.append(
            ReviewPoint(
                point_id=f"RULE-{index:03d}",
                catalog_id=resolve_review_point_definition(
                    hit.rule_name,
                    hit.risk_group,
                    hit.severity,
                ).catalog_id,
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
                catalog_id=resolve_review_point_definition(
                    check.topic,
                    "跨条款一致性检查",
                    Severity.high,
                ).catalog_id,
                title=check.topic,
                dimension="跨条款一致性检查",
                severity=Severity.high,
                status=ReviewPointStatus.suspected,
                rationale=check.detail,
                evidence_bundle=EvidenceBundle(
                    direct_evidence=[],
                    supporting_evidence=[],
                    conflicting_evidence=[],
                    rebuttal_evidence=[],
                    missing_evidence_notes=[f"{check.topic} 当前未形成可直接引用的冲突条款。"],
                    clause_roles=[],
                    sufficiency_summary="当前为一致性疑点，需结合原文或附件补充直接证据。",
                    evidence_level=EvidenceLevel.missing,
                    evidence_score=0.0,
                ),
                legal_basis=check.legal_basis,
                source_findings=[f"consistency_check:{check.topic}"],
            )
        )
    return review_points


def merge_review_points(review_points: Iterable[ReviewPoint]) -> list[ReviewPoint]:
    grouped: dict[str, list[ReviewPoint]] = {}
    for point in review_points:
        key = point.catalog_id or f"{point.dimension}|{point.title}"
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
                catalog_id=resolve_review_point_definition(
                    primary.title,
                    primary.dimension,
                    primary.severity,
                ).catalog_id,
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
        if _is_task_library_placeholder(point):
            continue
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
    applicability_checks: list[ApplicabilityCheck],
    quality_gates: list[ReviewQualityGate],
    report_text: str,
    extracted_clauses: list[ExtractedClause],
) -> list[FormalAdjudication]:
    applicability_index = {item.point_id: item for item in applicability_checks}
    quality_gate_index = {item.point_id: item for item in quality_gates}
    results: list[FormalAdjudication] = []
    for point in review_points:
        applicability = applicability_index.get(point.point_id)
        quality_gate = quality_gate_index.get(point.point_id)
        section_hint, quote = _resolve_review_point_evidence(point, report_text)
        roles = _resolve_review_point_roles(point, extracted_clauses, quote)
        has_direct = bool(point.evidence_bundle.direct_evidence)
        strong_anchor = bool(section_hint) and section_hint not in {
            "未明确定位",
            "keyword_match",
            "restrictive_term",
            "missing_marker",
        }
        weak_role_only = bool(roles) and all(
            role
            in {
                ClauseRole.form_template,
                ClauseRole.policy_explanation,
                ClauseRole.document_definition,
                ClauseRole.appendix_reference,
                ClauseRole.unknown,
            }
            for role in roles
        )
        legal_basis_applicable = bool(point.legal_basis) and (
            applicability.applicable if applicability is not None else True
        )
        evidence_sufficient = bool(
            has_direct
            and strong_anchor
            and quote
            and quote != "当前自动抽取未定位到可直接引用的原文。"
            and evidence_supports_title(point.title, quote)
            and not weak_role_only
        )

        applicability_summary = applicability.summary if applicability else "未进行适法性检查。"
        quality_status = quality_gate.status if quality_gate else QualityGateStatus.passed
        if quality_status == QualityGateStatus.filtered:
            disposition = FormalDisposition.filtered_out
            rationale = "当前审查点未通过 review_quality_gate，暂不进入正式意见。"
        elif point.status == ReviewPointStatus.identified or point.severity not in {Severity.high, Severity.critical}:
            disposition = FormalDisposition.filtered_out
            rationale = "当前审查点不属于正式意见输出范围，暂不进入高风险正式裁决。"
        elif evidence_sufficient and legal_basis_applicable:
            disposition = FormalDisposition.include
            rationale = "审查点已具备直接证据、有效条款角色和可适用法规依据，可进入正式意见。"
        elif point.status == ReviewPointStatus.manual_confirmation:
            disposition = FormalDisposition.manual_confirmation
            rationale = "当前审查点已识别到问题方向，但证据或适法性尚不足，应进入人工确认。"
        elif not evidence_sufficient:
            disposition = FormalDisposition.manual_confirmation
            rationale = "当前审查点缺少足够强的直接证据、有效锚点或实质性条款角色，不宜直接定性。"
        elif not legal_basis_applicable:
            disposition = FormalDisposition.manual_confirmation
            rationale = "当前审查点虽有证据，但尚未完成法规适用挂接，应先补充适法性判断。"
        else:
            disposition = FormalDisposition.filtered_out
            rationale = "当前审查点未通过正式裁决过滤，暂不进入正式意见。"
        results.append(
            FormalAdjudication(
                point_id=point.point_id,
                catalog_id=point.catalog_id,
                title=point.title,
                disposition=disposition,
                rationale=rationale,
                included_in_formal=disposition == FormalDisposition.include,
                section_hint=section_hint,
                primary_quote=quote,
                evidence_sufficient=evidence_sufficient,
                legal_basis_applicable=legal_basis_applicable,
                applicability_summary=applicability_summary,
                quality_gate_status=quality_status,
            )
        )
    return results


def build_review_point_catalog_snapshot(review_points: list[ReviewPoint]):
    return snapshot_catalog_for_points(review_points)


def build_point_applicability_checks(
    review_points: list[ReviewPoint],
    extracted_clauses: list[ExtractedClause],
) -> list[ApplicabilityCheck]:
    return build_applicability_checks(review_points, extracted_clauses)


def build_point_quality_gates(review_points: list[ReviewPoint]) -> list[ReviewQualityGate]:
    return build_review_quality_gates(review_points)


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
        rebuttal_evidence=[],
        missing_evidence_notes=missing_notes,
        clause_roles=dedup_roles,
        sufficiency_summary=sufficiency_summary,
        evidence_level=_derive_evidence_level(direct_evidence, supporting_evidence),
        evidence_score=_derive_evidence_score(direct_evidence, supporting_evidence),
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
    rebuttal = _dedupe_evidence(
        evidence
        for bundle in bundles
        for evidence in bundle.rebuttal_evidence
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
    if direct and (conflicting or rebuttal):
        summary = "已汇集直接证据，但同时存在冲突证据或反证，需谨慎裁决。"
    elif direct:
        summary = "已汇集直接证据，可作为正式裁决基础。"
    elif supporting:
        summary = "目前以辅助证据为主，需进一步补强直接条款。"
    else:
        summary = "当前缺少可直接引用的证据，需补证或人工确认。"
    return EvidenceBundle(
        direct_evidence=direct,
        supporting_evidence=supporting,
        conflicting_evidence=conflicting,
        rebuttal_evidence=rebuttal,
        missing_evidence_notes=missing_notes,
        clause_roles=clause_roles,
        sufficiency_summary=summary,
        evidence_level=_derive_evidence_level(direct, supporting),
        evidence_score=_derive_evidence_score(direct, supporting),
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


def _is_task_library_placeholder(point: ReviewPoint) -> bool:
    return (
        bool(point.source_findings)
        and point.source_findings
        and all(source.startswith("task_library:") for source in point.source_findings)
    )


def _derive_evidence_level(
    direct_evidence: list[Evidence],
    supporting_evidence: list[Evidence],
) -> EvidenceLevel:
    if direct_evidence:
        return EvidenceLevel.strong
    if len(supporting_evidence) >= 2:
        return EvidenceLevel.moderate
    if supporting_evidence:
        return EvidenceLevel.weak
    return EvidenceLevel.missing


def _derive_evidence_score(
    direct_evidence: list[Evidence],
    supporting_evidence: list[Evidence],
) -> float:
    if direct_evidence:
        return min(1.0, 0.75 + 0.08 * len(direct_evidence))
    if supporting_evidence:
        return min(0.7, 0.35 + 0.1 * len(supporting_evidence))
    return 0.0


def _resolve_review_point_evidence(point: ReviewPoint, report_text: str) -> tuple[str, str]:
    evidence = point.evidence_bundle.direct_evidence or point.evidence_bundle.supporting_evidence
    if not evidence:
        return "未明确定位", "当前自动抽取未定位到可直接引用的原文。"

    primary = evidence[0]
    section_hint = primary.section_hint or "未明确定位"
    raw_quote = primary.quote.strip()
    supplemental: list[str] = []
    for item in evidence[:3]:
        line_quote = line_text_from_anchor(report_text, item.section_hint)
        if line_quote:
            supplemental.append(line_quote)
        elif item.quote.strip():
            supplemental.append(item.quote.strip())

    quote = "；".join(dict.fromkeys([item for item in supplemental if item]))

    if raw_quote and " / " in raw_quote:
        parts = [part.strip() for part in raw_quote.split("/") if part.strip()]
        for part in parts:
            matched = search_line_by_keyword(report_text, part)
            if matched:
                supplemental.append(matched)
        if supplemental:
            return section_hint, "；".join(dict.fromkeys(supplemental))

    if quote:
        return section_hint, quote

    if raw_quote and " / " in raw_quote:
        parts = [part.strip() for part in raw_quote.split("/") if part.strip()]
        supplemental = [matched for part in parts if (matched := search_line_by_keyword(report_text, part))]
        if supplemental:
            return section_hint, "；".join(dict.fromkeys(supplemental))
    if raw_quote:
        return section_hint, raw_quote
    return section_hint, "当前自动抽取未定位到可直接引用的原文。"


def _resolve_review_point_roles(
    point: ReviewPoint,
    extracted_clauses: list[ExtractedClause],
    quote: str,
) -> list[ClauseRole]:
    roles = [role for role in point.evidence_bundle.clause_roles if role != ClauseRole.unknown]
    if roles:
        return roles

    clause_roles = [
        clause.clause_role
        for clause in extracted_clauses
        if quote and clause.content == quote and clause.clause_role != ClauseRole.unknown
    ]
    if clause_roles:
        return _dedupe_clause_roles(clause_roles)

    inferred = infer_role_from_text(quote)
    if inferred != ClauseRole.unknown:
        return [inferred]
    return []

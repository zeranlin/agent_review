from __future__ import annotations

from collections.abc import Iterable
import re

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
    ParsedTable,
    QualityGateStatus,
    RiskHit,
    ReviewPoint,
    ReviewPointStatus,
    ReviewQualityGate,
    Severity,
)
from .quality import (
    clause_window_from_anchor,
    evidence_supports_title,
    infer_evidence_roles,
    infer_role_from_text,
    line_text_from_anchor,
    search_line_by_keyword,
)
from .review_point_catalog import resolve_review_point_definition, select_standard_review_tasks, snapshot_catalog_for_points
from .review_quality_gate import build_review_quality_gates
from .ontology import EffectTag


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
    extracted_clauses: list[ExtractedClause] | None = None,
) -> list[ReviewPoint]:
    review_points: list[ReviewPoint] = []
    extracted_clauses = extracted_clauses or []
    for index, hit in enumerate(risk_hits, start=1):
        direct = []
        if hit.matched_text:
            direct.append(Evidence(quote=hit.matched_text, section_hint=hit.source_anchor))
        clause_roles = _dedupe_clause_roles(
            clause.clause_role
            for clause in extracted_clauses
            if clause.source_anchor == hit.source_anchor or clause.content == hit.matched_text
        )
        bundle = EvidenceBundle(
            direct_evidence=direct,
            supporting_evidence=[],
            conflicting_evidence=[],
            rebuttal_evidence=[],
            missing_evidence_notes=[] if direct else [f"{hit.rule_name} 当前未抽到直接证据。"],
            clause_roles=clause_roles,
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
    parse_tables: list[ParsedTable] | None = None,
) -> list[FormalAdjudication]:
    applicability_index = {item.point_id: item for item in applicability_checks}
    quality_gate_index = {item.point_id: item for item in quality_gates}
    rigid_patent_present = any(
        point.catalog_id == "RP-REST-004"
        and (applicability_index.get(point.point_id).applicable if applicability_index.get(point.point_id) else False)
        for point in review_points
    )
    results: list[FormalAdjudication] = []
    for point in review_points:
        applicability = applicability_index.get(point.point_id)
        quality_gate = quality_gate_index.get(point.point_id)
        section_hint, quote = _resolve_review_point_evidence(
            point,
            report_text,
            parse_tables or [],
        )
        roles = _resolve_review_point_roles(point, extracted_clauses, quote)
        effect_tags = _resolve_review_point_effect_tags(point, extracted_clauses, quote)
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
        weak_effect_only = bool(effect_tags) and all(
            tag in {
                EffectTag.template,
                EffectTag.example,
                EffectTag.reference_only,
            }
            for tag in effect_tags
        ) and EffectTag.binding not in effect_tags
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
            and not weak_effect_only
        )

        applicability_summary = applicability.summary if applicability else "未进行适法性检查。"
        quality_status = quality_gate.status if quality_gate else QualityGateStatus.passed
        if point.catalog_id == "RP-REST-003" and rigid_patent_present:
            disposition = FormalDisposition.filtered_out
            rationale = "同一证据链已被“刚性门槛型专利要求”更精确覆盖，泛化专利要求不再单独进入正式意见。"
        elif quality_status == QualityGateStatus.filtered:
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
            rationale = "当前审查点缺少足够强的直接证据、有效锚点、实质性条款角色或正式效力，不宜直接定性。"
        elif not legal_basis_applicable:
            disposition = FormalDisposition.manual_confirmation
            rationale = "当前审查点虽有证据，但尚未完成法规适用挂接，应先补充适法性判断。"
        else:
            disposition = FormalDisposition.filtered_out
            rationale = "当前审查点未通过正式裁决过滤，暂不进入正式意见。"
        recommended_for_review = (
            disposition == FormalDisposition.manual_confirmation
            and point.severity in {Severity.high, Severity.critical}
        )
        review_reason = ""
        if recommended_for_review:
            if not evidence_sufficient:
                review_reason = "当前已识别高风险方向，但主证据、锚点或条款角色仍需进一步复核。"
            elif not legal_basis_applicable:
                review_reason = "当前已识别高风险方向，但法规适用链条尚未闭合，建议人工复核后决定是否进入正式高风险。"
            else:
                review_reason = "当前已识别高风险方向，但仍需人工确认后再正式定性。"
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
                recommended_for_review=recommended_for_review,
                review_reason=review_reason,
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


def build_point_quality_gates(
    review_points: list[ReviewPoint],
    extracted_clauses: list[ExtractedClause],
) -> list[ReviewQualityGate]:
    return build_review_quality_gates(review_points, extracted_clauses)


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


def _resolve_review_point_evidence(
    point: ReviewPoint,
    report_text: str,
    parse_tables: list[ParsedTable],
) -> tuple[str, str]:
    evidence = point.evidence_bundle.direct_evidence or point.evidence_bundle.supporting_evidence
    if not evidence:
        return "未明确定位", "当前自动抽取未定位到可直接引用的原文。"

    family_key = _formal_family_key(point.title)
    table_quote = ""
    if family_key in {"scoring", "score_weight"}:
        table_quote = _find_table_row_quote(point.title, evidence, parse_tables)

    ranked = _rank_evidence_for_formal(point.title, evidence, report_text)
    primary = ranked[0]
    section_hint = primary.section_hint or "未明确定位"
    quote_cluster = _build_formal_evidence_cluster(point.title, ranked, report_text, section_hint)
    raw_quote = primary.quote.strip()
    line_quote = clause_window_from_anchor(report_text, section_hint)

    if raw_quote and " / " in raw_quote:
        parts = [part.strip() for part in raw_quote.split("/") if part.strip()]
        supplemental: list[str] = []
        for part in parts:
            matched = search_line_by_keyword(report_text, part, prefer_window=True)
            if matched:
                supplemental.append(matched)
        if supplemental:
            return section_hint, "；".join(dict.fromkeys(supplemental))

    if table_quote and family_key in {"scoring", "score_weight"}:
        return section_hint, table_quote

    if family_key in {"scoring", "score_weight"}:
        scoring_row = _reconstruct_scoring_row_window(
            quote_cluster or line_quote or raw_quote,
            point.title,
        )
        if scoring_row and evidence_supports_title(point.title, scoring_row):
            return section_hint, scoring_row

    if family_key == "personnel":
        if quote_cluster and evidence_supports_title(point.title, quote_cluster):
            return section_hint, quote_cluster
        if line_quote and evidence_supports_title(point.title, line_quote):
            return section_hint, line_quote
        return section_hint, "当前自动抽取未定位到可直接引用的原文。"

    if quote_cluster:
        return section_hint, quote_cluster

    if raw_quote and " / " in raw_quote:
        parts = [part.strip() for part in raw_quote.split("/") if part.strip()]
        supplemental = [matched for part in parts if (matched := search_line_by_keyword(report_text, part, prefer_window=True))]
        if supplemental:
            return section_hint, "；".join(dict.fromkeys(supplemental))
    if raw_quote:
        return section_hint, raw_quote
    return section_hint, "当前自动抽取未定位到可直接引用的原文。"


def _find_table_row_quote(
    title: str,
    evidence: list[Evidence],
    parse_tables: list[ParsedTable],
) -> str:
    if not parse_tables:
        return ""

    best_row = ""
    best_score = 0
    title_tokens = _formal_title_tokens(title)
    family_tokens = _formal_family_tokens(title)

    for item in evidence[:5]:
        quote_tokens = _formal_quote_tokens(item.quote.strip())
        for table in parse_tables:
            for row in table.rows:
                row_text = " | ".join(cell.strip() for cell in row if cell and cell.strip())
                if not row_text:
                    continue
                score = 0
                if item.quote and item.quote.strip() and item.quote.strip() in row_text:
                    score += 6
                for token in title_tokens:
                    if token in row_text:
                        score += 2
                for token in quote_tokens:
                    if token in row_text:
                        score += 3 if len(token) >= 4 else 1
                for token in family_tokens:
                    if token in row_text:
                        score += 1
                if score > best_score and evidence_supports_title(title, row_text):
                    best_score = score
                    best_row = row_text

    if best_score < 3:
        return ""
    return best_row


def _rank_evidence_for_formal(title: str, evidence: list[Evidence], report_text: str) -> list[Evidence]:
    def score(item: Evidence) -> tuple[int, int, int]:
        quote = item.quote.strip()
        line_quote = clause_window_from_anchor(report_text, item.section_hint) or line_text_from_anchor(report_text, item.section_hint) or quote
        text = f"{quote} {line_quote}"
        raw_support = bool(quote) and evidence_supports_title(title, quote)
        line_support = bool(line_quote) and evidence_supports_title(title, line_quote)
        title_score = 0
        if raw_support:
            title_score += 8
        elif line_support:
            title_score += 3
        if title in {"方案评分量化不足", "评分分档主观性与量化充分性复核"}:
            if any(token in text for token in ["完全满足且优于", "完全满足项目要求", "不完全满足项目要求", "缺陷", "扣分"]):
                title_score += 3
            if "方案" in text:
                title_score += 2
        elif title in {"证书类评分分值偏高", "投标阶段证书或检测报告负担过重"}:
            if any(token in text for token in ["资质证书", "管理体系认证", "认证证书", "检测报告"]):
                title_score += 3
            if "分" in text or "评分总分=" in text:
                title_score += 2
        elif title in {"评分项与采购标的不相关", "行业无关证书或财务指标被纳入评分"}:
            if any(token in text for token in ["利润率", "软件企业认定证书", "ITSS", "财务报告", "信用评价"]):
                title_score += 4
            if any(token in text for token in ["评分", "详细评审", "履约能力", "分"]):
                title_score += 2
        elif title in {"专门面向中小企业却仍保留价格扣除", "专门面向中小企业却保留价格扣除模板"}:
            if "专门面向中小企业" in text:
                title_score += 3
            if "价格扣除" in text:
                title_score += 3
            if "中小企业声明函" in text:
                title_score += 1
        elif title == "中小企业采购金额口径不一致":
            if any(token in text for token in ["预算金额", "最高限价", "面向中小企业采购金额"]):
                title_score += 3
            if any(token in text for token in ["元", "金额"]):
                title_score += 1
        elif title in {"项目属性与采购内容、合同类型不一致", "项目属性与合同类型口径疑似不一致", "货物采购混入持续性作业服务"}:
            if any(token in text for token in ["项目所属分类", "项目属性", "货物", "服务"]):
                title_score += 2
            if any(token in text for token in ["人工管护", "清林整地", "抚育", "运水", "持续性作业"]):
                title_score += 3
            if any(token in text for token in ["合同类型", "承揽合同"]):
                title_score += 3
        elif title in {"合同条款出现非本行业成果模板表述", "合同文本存在明显模板残留", "验收标准存在优胜原则或单方弹性判断", "货物保修表述与项目实际履约内容不匹配"}:
            if any(token in text for token in ["项目成果", "移作他用", "泄露本项目成果", "研究成果", "技术文档"]):
                title_score += 4
            if any(token in text for token in ["比较优胜", "优胜的原则", "确定该项的约定标准", "验收"]):
                title_score += 3
            if any(token in text for token in ["货物质保期", "质量保修范围和保修期", "1095日", "人工管护"]):
                title_score += 3
        elif title == "团队稳定性要求过强":
            if any(token in text for token in ["团队稳定", "核心团队", "人员稳定", "团队成员"]):
                title_score += 3
            if any(token in text for token in ["保持稳定", "不得更换", "未经采购人同意", "服务期内"]):
                title_score += 3
        elif title == "人员更换限制较强":
            if any(token in text for token in ["人员更换", "更换", "替换", "变更", "调整"]):
                title_score += 3
            if any(token in text for token in ["采购人同意", "采购人批准", "须经", "不得更换", "未经采购人同意"]):
                title_score += 3
        elif title == "刚性门槛型专利要求":
            if any(token in text for token in ["必须具备", "须具备", "应具备", "刚性门槛"]):
                title_score += 3
            if "专利" in text:
                title_score += 2
        elif title == "合同文本存在明显模板残留":
            if any(token in text for token in ["设计、测试", "X年", "事件发生后", "免费质保服务"]):
                title_score += 3
        return (
            title_score,
            1 if raw_support else 0,
            1 if line_support else 0,
            1 if item.section_hint and item.section_hint.startswith("line:") else 0,
            len(quote),
        )

    return sorted(evidence, key=score, reverse=True)


def _build_formal_evidence_cluster(
    title: str,
    ranked: list[Evidence],
    report_text: str,
    primary_section_hint: str,
) -> str:
    cluster: list[str] = []
    family_key = _formal_family_key(title)
    for item in ranked[:5]:
        if item.section_hint and primary_section_hint and item.section_hint != primary_section_hint:
            if _formal_family_key(title) not in {"scoring", "policy", "structure", "contract", "score_weight"}:
                continue
        line_quote = clause_window_from_anchor(report_text, item.section_hint) or line_text_from_anchor(report_text, item.section_hint) or item.quote.strip()
        if not line_quote:
            continue
        if cluster and line_quote in cluster:
            continue
        if not evidence_supports_title(title, line_quote) and family_key == "scoring":
            continue
        candidate_cluster = "；".join(cluster + [line_quote])
        if family_key in {"contract", "structure", "policy", "score_weight"}:
            cluster.append(line_quote)
            if evidence_supports_title(title, candidate_cluster):
                break
            if len(cluster) >= 2:
                break
            continue
        if not evidence_supports_title(title, line_quote):
            continue
        cluster.append(line_quote)
        if len(cluster) >= 2:
            break
    cluster_text = "；".join(cluster)
    if cluster_text and evidence_supports_title(title, cluster_text):
        return cluster_text
    return ""


def _formal_family_key(title: str) -> str:
    if any(token in title for token in ["方案评分", "评分分档", "评分量化"]):
        return "scoring"
    if any(token in title for token in ["证书", "检测报告", "财务指标"]):
        return "score_weight"
    if any(token in title for token in ["中小企业", "价格扣除", "采购金额口径"]):
        return "policy"
    if any(token in title for token in ["项目属性", "合同类型", "持续性作业服务", "采购内容"]):
        return "structure"
    if any(token in title for token in ["模板", "成果", "验收标准", "质保", "保修"]):
        return "contract"
    if any(token in title for token in ["团队稳定", "人员更换", "采购人批准更换", "采购人审批录用", "容貌体形", "身高限制", "性别限制", "年龄限制"]):
        return "personnel"
    if any(token in title for token in ["专利"]):
        return "restrictive"
    if any(token in title for token in ["模板残留", "成果模板"]):
        return "template"
    return "generic"


def _formal_family_tokens(title: str) -> list[str]:
    family = _formal_family_key(title)
    if family == "scoring":
        return ["评分", "方案", "售后", "优于", "完全满足", "不完全满足", "扣分"]
    if family == "score_weight":
        return ["评分", "证书", "认证", "检测报告", "财务", "分值", "分"]
    if family == "policy":
        return ["中小企业", "价格扣除", "预算金额", "最高限价", "采购金额"]
    if family == "structure":
        return ["项目属性", "项目所属分类", "合同类型", "承揽合同", "人工管护", "货物", "服务"]
    if family == "contract":
        return ["项目成果", "研究成果", "技术文档", "优胜原则", "验收", "质保", "保修"]
    if family == "personnel":
        return ["团队稳定", "人员更换", "采购人同意", "采购人批准", "关键岗位", "团队成员"]
    return []


def _formal_title_tokens(title: str) -> list[str]:
    return [token for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", title) if len(token) >= 2]


def _formal_quote_tokens(quote: str) -> list[str]:
    return [token for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", quote) if len(token) >= 3]


def _reconstruct_scoring_row_window(text: str, title: str) -> str:
    if not text:
        return ""
    normalized = re.sub(r"\s+", " ", text).strip()
    if not any(token in normalized for token in ["评审", "评分", "分值", "详细评审"]):
        return ""

    row_pattern = re.compile(
        r"(\d+\s+详细评审\s+.*?)(?=(?:\d+\s+详细评审\s+)|$)"
    )
    matches = [item.strip() for item in row_pattern.findall(normalized) if item.strip()]
    if matches:
        scored = sorted(matches, key=lambda item: _score_scoring_row_candidate(item, title), reverse=True)
        if _score_scoring_row_candidate(scored[0], title) > 0:
            return scored[0]

    if "评审项编号" in normalized:
        marker = normalized.find("评审项编号")
        sliced = normalized[marker:]
        row_start = re.search(r"\d+\s+详细评审\s+", sliced)
        if row_start:
            candidate = sliced[row_start.start() :].strip()
            return candidate
    return ""


def _score_scoring_row_candidate(text: str, title: str) -> int:
    score = 0
    family = _formal_family_key(title)
    if family == "scoring":
        for token in ["实施方案", "售后服务", "完全满足", "优于", "不完全满足", "缺陷", "扣分"]:
            if token in text:
                score += 2
    if family == "score_weight":
        for token in ["资质证书", "管理体系认证", "认证证书", "检测报告", "软件企业认定证书", "ITSS", "利润率", "财务报告"]:
            if token in text:
                score += 2
    if "分" in text:
        score += 1
    return score


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
        if (
            quote
            and (clause.content == quote or quote in clause.content or clause.content in quote)
            and clause.clause_role != ClauseRole.unknown
        )
    ]
    if clause_roles:
        return _dedupe_clause_roles(clause_roles)

    inferred = infer_role_from_text(quote)
    if inferred != ClauseRole.unknown:
        return [inferred]
    return []


def _resolve_review_point_effect_tags(
    point: ReviewPoint,
    extracted_clauses: list[ExtractedClause],
    quote: str,
) -> list[EffectTag]:
    tags: list[EffectTag] = []
    anchors = {
        item.section_hint
        for item in (point.evidence_bundle.direct_evidence + point.evidence_bundle.supporting_evidence)
        if item.section_hint
    }
    for clause in extracted_clauses:
        if clause.source_anchor in anchors:
            tags.extend(clause.effect_tags)
            continue
        if quote and (clause.content == quote or quote in clause.content or clause.content in quote):
            tags.extend(clause.effect_tags)
    dedup: list[EffectTag] = []
    seen: set[EffectTag] = set()
    for tag in tags:
        if tag not in seen:
            dedup.append(tag)
            seen.add(tag)
    return dedup

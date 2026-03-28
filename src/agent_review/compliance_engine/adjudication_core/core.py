from __future__ import annotations

from collections.abc import Iterable
import re

from .applicability import build_applicability_checks
from ...fact_collectors import collect_task_facts
from .authority_bindings import list_bindings_for_point
from ..compliance.external_data import lookup_external_manual_review_boundary
from ...review_point_contract_registry import get_review_point_contract
from ...models import (
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
    DocumentProfile,
    ReviewPoint,
    ReviewPointDefinition,
    ReviewPointInstance,
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
from ...review_point_catalog import resolve_review_point_definition, select_standard_review_tasks, snapshot_catalog_for_points
from .review_quality_gate import build_review_quality_gates
from ...ontology import EffectTag
from ...ontology import SemanticZoneType


WARNING_BACKGROUND_TOKENS = (
    "警示条款",
    "特别警示条款",
    "供应商参与投标禁止情形",
    "违法行为风险知悉确认书",
    "风险知悉确认书",
    "不作为供应商资格性审查及符合性审查条件",
    "不作为资格性审查及符合性审查条件",
    "虚假的检验检测报告",
    "不得存在以下所列禁止情形",
    "处罚",
)


def build_review_points(
    findings: list[Finding],
    report_text: str,
    extracted_clauses: list[ExtractedClause],
) -> list[ReviewPoint]:
    return build_review_points_from_findings(findings, report_text, extracted_clauses)


def build_review_points_from_task_library(
    report_text: str,
    extracted_clauses: list[ExtractedClause],
    document_profile: DocumentProfile | None = None,
    review_point_instances: list[ReviewPointInstance] | None = None,
) -> list[ReviewPoint]:
    task_definitions = select_standard_review_tasks(
        report_text,
        extracted_clauses,
        document_profile=document_profile,
        review_point_instances=review_point_instances,
    )
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


def build_review_points_from_instances(
    review_point_instances: list[ReviewPointInstance],
    legal_fact_candidates: list,
) -> list[ReviewPoint]:
    fact_index = {item.fact_id: item for item in legal_fact_candidates}
    review_points: list[ReviewPoint] = []
    for index, instance in enumerate(review_point_instances, start=1):
        contract = get_review_point_contract(instance.point_id)
        if contract is None:
            continue
        evidence = []
        ranked_fact_ids = _rank_instance_fact_ids(instance, instance.supporting_fact_ids, fact_index)
        for fact_id in ranked_fact_ids[:3]:
            fact = fact_index.get(fact_id)
            if fact is None or not fact.object_text.strip():
                continue
            evidence.append(
                Evidence(
                    quote=fact.object_text,
                    section_hint=str(fact.anchor.get("line_hint") or fact.anchor.get("block_no") or fact.source_unit_id),
                )
            )
        if not evidence:
            continue
        bindings = list_bindings_for_point(instance.point_id)
        legal_basis = [
            LegalBasis(
                source_name=item.doc_title,
                article_hint=item.article_label,
                summary=item.legal_proposition or item.reasoning_template,
                basis_type=item.norm_level,
            )
            for item in bindings
            if item.doc_title.strip()
        ]
        severity = Severity.high if contract.severity_policy in {"high", "critical"} else Severity.medium
        rationale = contract.description or contract.legal_theme or instance.summary
        review_points.append(
            ReviewPoint(
                point_id=f"RPI-POINT-{index:03d}",
                catalog_id=instance.point_id,
                title=contract.title,
                dimension=contract.report_group or "法理审查实例",
                severity=severity,
                status=ReviewPointStatus.confirmed if instance.confidence >= 0.75 else ReviewPointStatus.suspected,
                rationale=rationale,
                evidence_bundle=EvidenceBundle(
                    direct_evidence=evidence[:1],
                    supporting_evidence=evidence[1:3],
                    conflicting_evidence=[],
                    rebuttal_evidence=[],
                    missing_evidence_notes=[],
                    sufficiency_summary=instance.summary or "由规则命中与法律事实支撑。",
                    clause_roles=[],
                    evidence_level=EvidenceLevel.strong if instance.confidence >= 0.8 else EvidenceLevel.moderate,
                    evidence_score=round(instance.confidence, 3),
                ),
                legal_basis=legal_basis,
                source_findings=[f"review_point_instance:{instance.point_id}", *(f"rule_hit:{item}" for item in instance.matched_rule_ids)],
            )
        )
    return review_points


def _rank_instance_fact_ids(
    instance: ReviewPointInstance,
    fact_ids: list[str],
    fact_index: dict[str, object],
) -> list[str]:
    def score(fact_id: str) -> tuple[int, int, int]:
        fact = fact_index.get(fact_id)
        if fact is None:
            return (-1, -1, -1)
        text = getattr(fact, "object_text", "")
        score_value = 0
        if instance.point_id == "RP-EVID-001":
            if any(token in text for token in ["检测中心", "税务部门", "研究院", "实验室"]):
                score_value += 8
            if "出具" in text:
                score_value += 4
            if "第三方检测机构" in text:
                score_value -= 3
        elif instance.point_id == "RP-QUAL-004":
            if getattr(fact, "zone_type", "") == "qualification":
                score_value += 5
            if any(token in text for token in ["同类项目业绩", "类似项目业绩"]):
                score_value += 6
            if any(token in text for token in ["深圳市", "广州市", "行业"]):
                score_value += 3
            if any(token in text for token in ["得分", "评分内容", "评分依据"]):
                score_value -= 1
        elif instance.point_id == "RP-QUAL-003":
            if any(token in text for token in ["高新技术企业", "纳税信用", "成立满", "科技型中小企业"]):
                score_value += 4
        elif instance.point_id == "RP-CONTRACT-012":
            if any(token in text for token in ["履约担保", "履约保证金", "质量保证金"]):
                score_value += 6
            if any(token in text for token in ["银行转账", "无息退还"]):
                score_value += 4
        elif instance.point_id == "RP-CONTRACT-013":
            if "第三方检测费用" in text:
                score_value += 6
            if any(token in text for token in ["中标人承担", "无论检测结果是否合格"]):
                score_value += 4
        elif instance.point_id == "RP-COMP-001":
            if any(token in text for token in ["预算金额", "不得低于", "无效投标"]):
                score_value += 6
            if "%" in text:
                score_value += 3
        line_hint = str(getattr(fact, "anchor", {}).get("line_hint", ""))
        return (
            score_value,
            1 if line_hint.startswith("line:") else 0,
            -len(text),
        )

    return sorted(fact_ids, key=score, reverse=True)


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
                catalog_id=primary.catalog_id or resolve_review_point_definition(
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
    review_point_instances: list[ReviewPointInstance] | None = None,
) -> list[FormalAdjudication]:
    applicability_index = {item.point_id: item for item in applicability_checks}
    quality_gate_index = {item.point_id: item for item in quality_gates}
    instance_index = {
        item.point_id: item
        for item in (review_point_instances or [])
        if item.point_id.strip()
    }
    rigid_patent_present = any(
        point.catalog_id == "RP-REST-004"
        and (applicability_index.get(point.point_id).applicable if applicability_index.get(point.point_id) else False)
        for point in review_points
    )
    results: list[FormalAdjudication] = []
    for point in review_points:
        applicability = applicability_index.get(point.point_id)
        quality_gate = quality_gate_index.get(point.point_id)
        instance = instance_index.get(point.catalog_id)
        section_hint, quote = _resolve_review_point_evidence(
            point,
            report_text,
            parse_tables or [],
            extracted_clauses,
        )
        family_key = _formal_family_key(point.title)
        noise_like_quote = _formal_quote_is_noise_like(quote, family_key)
        roles = _resolve_review_point_roles(point, extracted_clauses, quote)
        effect_tags = _resolve_review_point_effect_tags(point, extracted_clauses, quote)
        has_direct = bool(point.evidence_bundle.direct_evidence)
        risk_hit_direct = any(source.startswith("risk_hit:") for source in point.source_findings)
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
        weak_zone_only = _review_point_zones_are_weak_only(point, extracted_clauses, quote)
        authority_bindings = list_bindings_for_point(point.catalog_id)
        legal_basis_applicable = bool(point.legal_basis or authority_bindings) and (
            applicability.applicable if applicability is not None else True
        )
        if risk_hit_direct and point.legal_basis:
            legal_basis_applicable = True
        if risk_hit_direct and authority_bindings:
            legal_basis_applicable = True
        external_boundary = lookup_external_manual_review_boundary(
            catalog_id=point.catalog_id,
            title=point.title,
        )
        boundary_reasons = _ordered_unique(
            [
                *external_boundary.get("reasons", []),
                *(
                    reason
                    for binding in authority_bindings
                    for reason in binding.requires_human_review_when
                ),
            ]
        )
        authority_refs = _ordered_unique(
            [
                *external_boundary.get("authority_refs", []),
                *(
                    " ".join(part for part in [binding.doc_title, binding.article_label] if part)
                    for binding in authority_bindings
                ),
            ]
        )
        authority_propositions = _ordered_unique(
            binding.legal_proposition for binding in authority_bindings if binding.legal_proposition
        )
        if risk_hit_direct and has_direct and quote and quote != "当前自动抽取未定位到可直接引用的原文。":
            weak_role_only = False
            weak_effect_only = False
            weak_zone_only = False
        evidence_sufficient = bool(
            has_direct
            and strong_anchor
            and quote
            and quote != "当前自动抽取未定位到可直接引用的原文。"
            and evidence_supports_title(point.title, quote)
            and not noise_like_quote
            and not weak_role_only
            and not weak_effect_only
            and not weak_zone_only
        )
        if point.title in {
            "履约保证金转质量保证金或长期无息占压",
            "第三方检测费用无论结果均由中标人承担",
        } and has_direct and strong_anchor and quote and evidence_supports_title(point.title, quote):
            evidence_sufficient = True

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
        elif noise_like_quote:
            disposition = FormalDisposition.manual_confirmation
            rationale = "当前主证据更像法规引用、表格残片或清单串接，建议人工确认后再正式定性。"
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
        if disposition == FormalDisposition.manual_confirmation and boundary_reasons:
            boundary_summary = "；".join(boundary_reasons[:2])
            authority_summary = "、".join(authority_refs[:2])
            if authority_summary:
                rationale += f" 外部法理边界提示：依据 {authority_summary}，如存在“{boundary_summary}”情形，应保留人工复核。"
            else:
                rationale += f" 外部法理边界提示：如存在“{boundary_summary}”情形，应保留人工复核。"
            if review_reason:
                review_reason += f" 重点核查：{boundary_summary}。"
            else:
                review_reason = f"外部法理边界提示需复核：{boundary_summary}。"
        if authority_propositions and disposition in {
            FormalDisposition.include,
            FormalDisposition.manual_confirmation,
        }:
            rationale += f" 法理命题：{authority_propositions[0]}"
        instance_support_summary = instance.summary if instance is not None else ""
        instance_rule_ids = list(instance.matched_rule_ids) if instance is not None else []
        if instance_support_summary and disposition in {
            FormalDisposition.include,
            FormalDisposition.manual_confirmation,
        }:
            rationale += f" 新链实例支撑：{instance_support_summary}"
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
                instance_support_summary=instance_support_summary,
                instance_rule_ids=instance_rule_ids,
            )
        )
    return results


def _ordered_unique(items) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        current = str(item).strip()
        if not current or current in seen:
            continue
        seen.add(current)
        ordered.append(current)
    return ordered


def build_review_point_catalog_snapshot(
    review_points: list[ReviewPoint],
    review_point_instances: list[ReviewPointInstance] | None = None,
):
    snapshot = snapshot_catalog_for_points(review_points)
    seen = {item.catalog_id for item in snapshot}
    for instance in review_point_instances or []:
        if instance.point_id in seen:
            continue
        contract = get_review_point_contract(instance.point_id)
        if contract is None:
            continue
        snapshot.append(
            ReviewPointDefinition(
                catalog_id=contract.point_id,
                title=contract.title,
                dimension=contract.report_group or "法理审查实例",
                default_severity=Severity.high if contract.severity_policy in {"high", "critical"} else Severity.medium,
                risk_family=contract.risk_family,
                target_zones=list(contract.target_zone_types),
                required_fields=list(contract.required_fields),
                enhancement_fields=list(contract.enhancement_fields),
                basis_hint=contract.description or contract.legal_theme,
            )
        )
        seen.add(instance.point_id)
    return snapshot


def build_point_applicability_checks(
    review_points: list[ReviewPoint],
    extracted_clauses: list[ExtractedClause],
    review_point_instances: list[ReviewPointInstance] | None = None,
) -> list[ApplicabilityCheck]:
    return build_applicability_checks(review_points, extracted_clauses, review_point_instances)


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
    extracted_clauses: list[ExtractedClause],
) -> tuple[str, str]:
    evidence = point.evidence_bundle.direct_evidence or point.evidence_bundle.supporting_evidence
    if not evidence:
        return "未明确定位", "当前自动抽取未定位到可直接引用的原文。"

    if point.catalog_id == "RP-QUAL-004" and point.evidence_bundle.direct_evidence:
        primary_direct = point.evidence_bundle.direct_evidence[0]
        direct_quote = primary_direct.quote.strip()
        if direct_quote and evidence_supports_title(point.title, direct_quote):
            return primary_direct.section_hint or "未明确定位", _sanitize_formal_quote(point.title, direct_quote)

    if any(source.startswith("risk_hit:") for source in point.source_findings):
        ranked_direct = _rank_evidence_for_formal(point.title, list(evidence), report_text)
        if ranked_direct:
            primary_direct = ranked_direct[0]
            direct_section_hint = primary_direct.section_hint or "未明确定位"
            direct_line_quote = (
                clause_window_from_anchor(report_text, direct_section_hint)
                or line_text_from_anchor(report_text, direct_section_hint)
                or primary_direct.quote.strip()
            )
            direct_raw_quote = primary_direct.quote.strip()
            direct_quote = (
                direct_line_quote
                if direct_line_quote
                and evidence_supports_title(point.title, direct_line_quote)
                and not _formal_quote_is_noise_like(direct_line_quote, _formal_family_key(point.title))
                else direct_raw_quote
            )
            if direct_quote and evidence_supports_title(point.title, direct_quote):
                return direct_section_hint, _sanitize_formal_quote(point.title, direct_quote)

    family_key = _formal_family_key(point.title)
    matched_clauses = _resolve_point_matched_clauses(point, extracted_clauses, "")
    clause_candidate = _best_clause_quote_for_formal(point.title, matched_clauses, report_text)
    if clause_candidate is not None:
        section_hint = clause_candidate.source_anchor or "未明确定位"
        qualification_cluster = _build_qualification_gate_cluster(point.title, matched_clauses, report_text)
        if qualification_cluster and not _formal_quote_is_noise_like(qualification_cluster, family_key):
            return section_hint, _sanitize_formal_quote(point.title, qualification_cluster)
        line_quote = clause_window_from_anchor(report_text, section_hint)
        content_quote = clause_candidate.content or ""
        if content_quote and evidence_supports_title(point.title, content_quote) and (
            not line_quote
            or not evidence_supports_title(point.title, line_quote)
            or len(content_quote) <= len(line_quote)
            or _formal_quote_is_noise_like(line_quote, family_key)
        ):
            clause_quote = content_quote
        else:
            clause_quote = line_quote or content_quote
        if clause_quote and not _formal_quote_is_noise_like(clause_quote, family_key):
            return section_hint, _sanitize_formal_quote(point.title, clause_quote)

    table_quote = ""
    if family_key in {"scoring", "score_weight"}:
        table_quote = _find_table_row_quote(point.title, evidence, parse_tables)

    ranked = _rank_evidence_for_formal(point.title, evidence, report_text)
    primary = ranked[0]
    section_hint = primary.section_hint or "未明确定位"
    quote_cluster = _build_formal_evidence_cluster(point.title, ranked, report_text, section_hint)
    raw_quote = primary.quote.strip()
    line_quote = clause_window_from_anchor(report_text, section_hint)
    resolved_quote = ""

    if raw_quote and " / " in raw_quote:
        parts = [part.strip() for part in raw_quote.split("/") if part.strip()]
        supplemental: list[str] = []
        for part in parts:
            matched = search_line_by_keyword(report_text, part, prefer_window=True)
            if matched:
                supplemental.append(matched)
        if supplemental:
            resolved_quote = "；".join(dict.fromkeys(supplemental))

    if not resolved_quote and table_quote and family_key in {"scoring", "score_weight"}:
        resolved_quote = table_quote

    if not resolved_quote and family_key in {"scoring", "score_weight"}:
        scoring_row = _reconstruct_scoring_row_window(
            quote_cluster or line_quote or raw_quote,
            point.title,
        )
        if scoring_row and evidence_supports_title(point.title, scoring_row):
            resolved_quote = scoring_row

    if not resolved_quote and family_key == "personnel":
        if quote_cluster and evidence_supports_title(point.title, quote_cluster):
            resolved_quote = quote_cluster
        elif line_quote and evidence_supports_title(point.title, line_quote):
            resolved_quote = line_quote

    if not resolved_quote and quote_cluster:
        resolved_quote = quote_cluster

    if not resolved_quote and raw_quote:
        resolved_quote = raw_quote

    if not resolved_quote:
        resolved_quote = "当前自动抽取未定位到可直接引用的原文。"

    if family_key == "score_weight":
        resolved_quote = _augment_score_weight_quote_from_evidence(resolved_quote, raw_quote)

    return section_hint, _sanitize_formal_quote(point.title, resolved_quote)


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
    family_key = _formal_family_key(title)

    def score(item: Evidence) -> tuple[int, int, int, int, int]:
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
        title_score -= _formal_noise_penalty(text, family_key)
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
            -len(quote),
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
        if _formal_quote_is_noise_like(line_quote, family_key):
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


def _best_clause_quote_for_formal(
    title: str,
    clauses: list[ExtractedClause],
    report_text: str,
) -> ExtractedClause | None:
    if not clauses:
        return None
    family_key = _formal_family_key(title)
    candidates = []
    for clause in clauses:
        line_quote = clause_window_from_anchor(report_text, clause.source_anchor)
        quote = ""
        if line_quote and not _formal_quote_is_noise_like(line_quote, family_key) and evidence_supports_title(title, line_quote):
            quote = line_quote
        elif clause.content and not _formal_quote_is_noise_like(clause.content, family_key) and evidence_supports_title(title, clause.content):
            quote = clause.content
        if not quote:
            continue
        candidates.append(clause)
    if not candidates:
        return None
    if family_key == "qualification":
        candidates.sort(key=lambda clause: _qualification_clause_priority_for_formal(title, clause))
    else:
        candidates.sort(key=_matched_clause_priority)
    return candidates[0]


def _qualification_clause_priority_for_formal(
    title: str,
    clause: ExtractedClause,
) -> tuple[int, int, int, int, int, int, int]:
    constraint_values = {item.value for item in clause.clause_constraint.constraint_types}
    return (
        0
        if (
            "证明材料来源" in title
            and any(token in clause.content for token in ["检测中心", "税务部门", "研究院", "实验室"])
        )
        else 1,
        0 if clause.semantic_zone == SemanticZoneType.qualification else 1,
        0 if clause.field_name == "资格门槛明细" else 1,
        0
        if (
            "资格业绩要求" in title
            and "performance_experience" in constraint_values
            and "同类业绩" in clause.content
        )
        else 1,
        0
        if (
            "资格业绩要求" in title
            and (clause.clause_constraint.region_tokens or clause.clause_constraint.industry_tokens)
        )
        else 1,
        0
        if (
            "资格条件可能缺乏履约必要性或带有歧视性门槛" in title
            and constraint_values & {"certification", "credit_rating", "establishment_age"}
        )
        else 1,
        0 if clause.source_anchor.startswith("line:") else 1,
        len(clause.content),
    )


def _build_qualification_gate_cluster(
    title: str,
    clauses: list[ExtractedClause],
    report_text: str,
) -> str:
    if title not in {
        "资格条件可能缺乏履约必要性或带有歧视性门槛",
        "资格业绩要求可能存在地域限定、行业口径过窄或与评分重复",
    }:
        return ""
    ordered = sorted(clauses, key=lambda clause: _qualification_clause_priority_for_formal(title, clause))
    if title == "资格业绩要求可能存在地域限定、行业口径过窄或与评分重复":
        performance_clause = next(
            (
                clause
                for clause in ordered
                if ("同类业绩" in clause.content or "类似项目业绩" in clause.content)
                and clause.semantic_zone == SemanticZoneType.qualification
            ),
            None,
        )
        if performance_clause is None:
            performance_clause = next(
                (
                    clause
                    for clause in ordered
                    if "同类业绩" in clause.content or "类似项目业绩" in clause.content
                ),
                None,
            )
        scoring_clause = next(
            (
                clause
                for clause in ordered
                if any(token in clause.content for token in ["得分", "评分内容", "评分依据"])
                and clause.semantic_zone == SemanticZoneType.scoring
            ),
            None,
        )
        fragments: list[str] = []
        for clause in [performance_clause, scoring_clause]:
            if clause is None:
                continue
            quote = clause.content or clause_window_from_anchor(report_text, clause.source_anchor)
            if not quote or _formal_quote_is_noise_like(quote, "qualification"):
                continue
            if quote not in fragments:
                fragments.append(quote)
        candidate = "；".join(fragments)
        return candidate if candidate and evidence_supports_title(title, candidate) else candidate
    entity_clause = next(
        (
            clause
            for clause in ordered
            if any(item.value == "entity_identity" for item in clause.clause_constraint.constraint_types)
        ),
        None,
    )
    gate_clause = next(
        (
            clause
            for clause in ordered
            if any(
                item.value in {"certification", "credit_rating", "establishment_age"}
                for item in clause.clause_constraint.constraint_types
            )
        ),
        None,
    )
    preferred = [clause for clause in [entity_clause, gate_clause] if clause is not None]
    if preferred:
        ordered = [*preferred, *[clause for clause in ordered if clause not in preferred]]
    fragments: list[str] = []
    for clause in ordered[:4]:
        quote = clause.content or clause_window_from_anchor(report_text, clause.source_anchor)
        if not quote or _formal_quote_is_noise_like(quote, "qualification"):
            continue
        if quote in fragments:
            continue
        fragments.append(quote)
        candidate = "；".join(fragments)
        if len(fragments) >= 2 and evidence_supports_title(title, candidate):
            return candidate
    return ""


def _formal_family_key(title: str) -> str:
    if any(token in title for token in ["资格条件", "资格业绩", "证明材料来源", "政策适用口径"]):
        return "qualification"
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
    if any(token in title for token in ["扣款", "解约", "违约责任", "付款", "满意度", "考核"]):
        return "contract"
    if any(token in title for token in ["质量保证金", "履约保证金", "第三方检测费用"]):
        return "contract"
    if any(token in title for token in ["最低报价门槛", "预算金额比例"]):
        return "policy"
    if any(token in title for token in ["团队稳定", "人员更换", "采购人批准更换", "采购人审批录用", "容貌体形", "身高限制", "性别限制", "年龄限制"]):
        return "personnel"
    if any(token in title for token in ["专利"]):
        return "restrictive"
    if any(token in title for token in ["模板残留", "成果模板"]):
        return "template"
    return "generic"


def _formal_family_tokens(title: str) -> list[str]:
    family = _formal_family_key(title)
    if family == "qualification":
        return ["资格", "投标人", "科技型中小企业", "高新技术企业", "纳税信用", "成立满", "同类业绩", "检测中心", "检测报告"]
    if family == "scoring":
        return ["评分", "方案", "售后", "优于", "完全满足", "不完全满足", "扣分"]
    if family == "score_weight":
        return ["评分", "证书", "认证", "检测报告", "财务", "分值", "分"]
    if family == "policy":
        return ["中小企业", "价格扣除", "预算金额", "最高限价", "采购金额", "最低报价门槛", "无效投标"]
    if family == "structure":
        return ["项目属性", "项目所属分类", "合同类型", "承揽合同", "人工管护", "货物", "服务"]
    if family == "contract":
        return ["项目成果", "研究成果", "技术文档", "优胜原则", "验收", "质保", "保修", "付款", "尾款", "考核", "满意度", "扣款", "解约", "违约", "质量保证金", "履约保证金", "第三方检测费用"]
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


def _augment_score_weight_quote_from_evidence(resolved_quote: str, raw_quote: str) -> str:
    if not resolved_quote or not raw_quote or " / " not in raw_quote:
        return resolved_quote

    normalized_quote = re.sub(r"\s+", " ", resolved_quote).strip()
    additions: list[str] = []
    token_score_map = {
        "ITSS": "ITSS证书（2分）",
        "软件企业认定证书": "软件企业认定证书（5分）",
        "财务报告": "财务报告（2分）",
        "利润率": "利润率（10分）",
    }
    for part in [item.strip() for item in raw_quote.split("/") if item.strip()]:
        for token, snippet in token_score_map.items():
            if token not in part:
                continue
            if token in normalized_quote or snippet in normalized_quote:
                break
            additions.append(snippet)
            break

    if not additions:
        return resolved_quote
    return "；".join([normalized_quote, *dict.fromkeys(additions)])


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
        for clause in _resolve_point_matched_clauses(point, extracted_clauses, quote)
        if clause.clause_role != ClauseRole.unknown
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
    for clause in _resolve_point_matched_clauses(point, extracted_clauses, quote):
        tags.extend(clause.effect_tags)
    dedup: list[EffectTag] = []
    seen: set[EffectTag] = set()
    for tag in tags:
        if tag not in seen:
            dedup.append(tag)
            seen.add(tag)
    return dedup


def _resolve_point_matched_clauses(
    point: ReviewPoint,
    extracted_clauses: list[ExtractedClause],
    quote: str,
) -> list[ExtractedClause]:
    direct_evidence = list(point.evidence_bundle.direct_evidence)
    supporting_evidence = list(point.evidence_bundle.supporting_evidence)
    direct_anchors = {item.section_hint for item in direct_evidence if item.section_hint}
    direct_quotes = {item.quote for item in direct_evidence if item.quote}
    anchors = {
        item.section_hint
        for item in (direct_evidence + supporting_evidence)
        if item.section_hint
    }
    matched = [
        clause
        for clause in extracted_clauses
        if clause.source_anchor in anchors
        or (
            quote
            and (clause.content == quote or quote in clause.content or clause.content in quote)
        )
    ]
    matched.sort(
        key=lambda clause: (
            0 if clause.source_anchor in direct_anchors else 1,
            0
            if any(
                direct_quote == clause.content
                or direct_quote in clause.content
                or clause.content in direct_quote
                for direct_quote in direct_quotes
            )
            else 1,
            *_matched_clause_priority(clause),
        )
    )
    return matched


def _matched_clause_priority(clause: ExtractedClause) -> tuple[int, int, int]:
    weak_zones = {
        SemanticZoneType.template,
        SemanticZoneType.appendix_reference,
        SemanticZoneType.catalog_or_navigation,
        SemanticZoneType.public_copy_or_noise,
    }
    weak_tags = {
        EffectTag.template,
        EffectTag.example,
        EffectTag.reference_only,
        EffectTag.catalog,
        EffectTag.public_copy_noise,
    }
    return (
        1 if clause.semantic_zone in weak_zones else 0,
        1 if clause.effect_tags and all(tag in weak_tags for tag in clause.effect_tags) else 0,
        -len(clause.content),
    )


def _review_point_zones_are_weak_only(
    point: ReviewPoint,
    extracted_clauses: list[ExtractedClause],
    quote: str,
) -> bool:
    matched = _resolve_point_matched_clauses(point, extracted_clauses, quote)
    if not matched:
        return _formal_quote_is_noise_like(quote, _formal_family_key(point.title))
    weak_zones = {
        SemanticZoneType.template,
        SemanticZoneType.appendix_reference,
        SemanticZoneType.catalog_or_navigation,
        SemanticZoneType.public_copy_or_noise,
    }
    return all(clause.semantic_zone in weak_zones for clause in matched) or _formal_quote_is_noise_like(
        quote,
        _formal_family_key(point.title),
    )


def _sanitize_formal_quote(title: str, quote: str) -> str:
    family_key = _formal_family_key(title)
    if title in {
        "履约保证金转质量保证金或长期无息占压",
        "第三方检测费用无论结果均由中标人承担",
    } and quote and evidence_supports_title(title, quote):
        return quote
    if quote and not _formal_quote_is_noise_like(quote, family_key):
        return quote
    return "当前自动抽取未定位到可直接引用的原文。"


def _formal_quote_is_noise_like(quote: str, family_key: str) -> bool:
    normalized = re.sub(r"\s+", " ", quote).strip()
    if not normalized:
        return True
    if normalized == "当前自动抽取未定位到可直接引用的原文。":
        return True
    if _formal_quote_is_legal_citation(normalized):
        return True
    if _formal_quote_is_template_noise(normalized):
        return True
    if any(token in normalized for token in WARNING_BACKGROUND_TOKENS):
        if family_key in {"scoring", "score_weight", "qualification", "generic", "policy"}:
            return True
    if _formal_quote_is_table_splice(normalized) and family_key not in {"scoring", "score_weight", "qualification", "contract", "policy"}:
        return True
    if _formal_quote_is_list_splice(normalized) and family_key not in {"scoring", "score_weight", "qualification", "contract", "policy"}:
        return True
    if family_key == "contract" and not any(
        token in normalized for token in ["付款", "支付", "尾款", "验收", "考核", "满意度", "扣款", "违约", "解约", "解除合同", "质保", "保修"]
    ):
        return True
    if family_key == "qualification" and not any(
        token in normalized
        for token in ["投标人", "资格", "科技型中小企业", "高新技术企业", "纳税信用", "成立满", "同类业绩", "检测中心", "检测报告"]
    ):
        return True
    return False


def _formal_quote_is_template_noise(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return True
    compact = re.sub(r"\s+", "", normalized)
    if "目录" in normalized and any(token in normalized for token in ["第一章", "第二章", "第三章", "第四章"]):
        return True
    chapter_hits = sum(1 for token in ["第一章", "第二章", "第三章", "第四章", "第五章", "第六章"] if token in normalized)
    if chapter_hits >= 2 and len(compact) < 180:
        return True
    if (
        re.search(r"第[一二三四五六七八九十0-9]+章", normalized)
        and any(token in normalized for token in ["招标公告", "采购需求", "投标文件格式", "合同条款", "评分办法"])
        and len(compact) < 140
    ):
        return True
    policy_markers = ["根据", "依据", "按照", "参照", "执行", "适用", "规定", "办法", "通知", "财政部", "管理办法"]
    if any(token in normalized for token in policy_markers):
        if not any(token in normalized for token in ["本项目", "采购标的", "项目属性", "价格扣除", "专门面向中小企业采购", "招标文件", "采购需求"]):
            return len(normalized) < 180
    if _formal_quote_is_legal_citation(normalized):
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
        marker in normalized for marker in ["资格", "评分", "技术", "商务", "合同", "履约", "项目经理", "检测报告", "证书", "中小企业", "价格扣除"]
    ):
        return True
    return False


def _formal_noise_penalty(text: str, family_key: str) -> int:
    penalty = 0
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return 8
    if _formal_quote_is_legal_citation(normalized):
        penalty += 8
    if any(token in normalized for token in WARNING_BACKGROUND_TOKENS):
        penalty += 8 if family_key in {"scoring", "score_weight", "qualification", "generic", "policy"} else 4
    if _formal_quote_is_table_splice(normalized) and family_key not in {"scoring", "score_weight"}:
        penalty += 6
    if _formal_quote_is_list_splice(normalized) and family_key not in {"scoring", "score_weight"}:
        penalty += 4
    if family_key not in {"scoring", "score_weight"} and len(normalized) > 140:
        penalty += 2
    return penalty


def _formal_quote_is_legal_citation(text: str) -> bool:
    return bool(
        ("《" in text and "》" in text and "第" in text and "条" in text)
        or re.search(r"^\s*[一二三四五六七八九十0-9]+、《", text)
        or ("依据" in text and "第" in text and "条" in text)
    )


def _formal_quote_is_table_splice(text: str) -> bool:
    if text.count("|") >= 2 or text.count(" | ") >= 2:
        return True
    numeric_tokens = re.findall(r"\d+", text)
    return len(text) >= 80 and len(numeric_tokens) >= 4 and any(
        token in text for token in ["项目名称", "品目", "规格", "数量", "单价", "分值", "教工宿舍", "拒绝进口"]
    )


def _formal_quote_is_list_splice(text: str) -> bool:
    separator_count = text.count("；") + text.count(";")
    return len(text) >= 100 and separator_count >= 3


def _formal_family_key(title: str) -> str:
    if any(token in title for token in ["资格条件", "资格业绩", "证明材料来源", "政策适用口径"]):
        return "qualification"
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

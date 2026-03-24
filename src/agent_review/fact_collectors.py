from __future__ import annotations

from collections.abc import Callable

from .models import Evidence, EvidenceBundle, EvidenceLevel, ExtractedClause, ReviewPointDefinition, ReviewPointStatus


FactCollector = Callable[[ReviewPointDefinition, list[ExtractedClause]], tuple[EvidenceBundle, ReviewPointStatus, str]]


def collect_task_facts(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    collector = TASK_FACT_COLLECTORS.get(definition.catalog_id, _collect_generic_task_facts)
    return collector(definition, extracted_clauses)


def _collect_generic_task_facts(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_clauses_for_definition(definition, extracted_clauses)
    return _bundle_from_relevant_clauses(definition, relevant)


def _collect_policy_conflict_facts(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(
        extracted_clauses,
        ["是否专门面向中小企业", "是否仍保留价格扣除条款", "中小企业声明函类型"],
    )
    return _bundle_from_relevant_clauses(definition, relevant)


def _collect_service_template_facts(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(extracted_clauses, ["项目属性", "中小企业声明函类型"])
    return _bundle_from_relevant_clauses(definition, relevant)


def _collect_contract_linkage_facts(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(extracted_clauses, ["付款节点", "考核条款", "验收标准", "扣款条款"])
    return _bundle_from_relevant_clauses(definition, relevant)


def _collect_personnel_boundary_facts(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_clauses_for_definition(definition, extracted_clauses)
    relevant.extend(_collect_by_fields(extracted_clauses, ["项目属性", "采购标的"]))
    return _bundle_from_relevant_clauses(definition, _dedupe_clauses(relevant))


def _collect_structure_conflict_facts(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(
        extracted_clauses,
        ["项目属性", "采购标的", "品目名称", "所属行业划分", "中小企业声明函类型", "质保期"],
    )
    return _bundle_from_relevant_clauses(definition, relevant)


def _collect_by_fields(
    extracted_clauses: list[ExtractedClause],
    field_names: list[str],
) -> list[ExtractedClause]:
    return [clause for clause in extracted_clauses if clause.field_name in field_names]


def _collect_clauses_for_definition(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> list[ExtractedClause]:
    field_names = {
        field_name
        for condition in [*definition.required_conditions, *definition.exclusion_conditions]
        for field_name in condition.clause_fields
    }
    relevant = [clause for clause in extracted_clauses if clause.field_name in field_names]
    if relevant:
        return _dedupe_clauses(relevant)

    signal_tokens = {
        token
        for condition in [*definition.required_conditions, *definition.exclusion_conditions]
        for group in condition.signal_groups
        for token in group
    }
    return _dedupe_clauses(
        [
            clause
            for clause in extracted_clauses
            if any(token and token in clause.content for token in signal_tokens)
        ]
    )


def _bundle_from_relevant_clauses(
    definition: ReviewPointDefinition,
    relevant: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    direct = [
        Evidence(quote=_render_clause_quote(clause), section_hint=clause.source_anchor)
        for clause in relevant[:2]
    ]
    supporting = [
        Evidence(quote=_render_clause_quote(clause), section_hint=clause.source_anchor)
        for clause in relevant[2:6]
    ]
    missing_fields = [
        field_name
        for condition in definition.required_conditions
        for field_name in condition.clause_fields
        if not any(clause.field_name == field_name for clause in relevant)
    ]
    if direct:
        status = ReviewPointStatus.suspected
        summary = f"标准任务已采集到 {len(direct) + len(supporting)} 条候选事实，可进入后续适法性判断。"
        rationale = f"标准审查任务已围绕 {definition.title} 主动采集候选事实。"
        evidence_level = EvidenceLevel.strong if direct else EvidenceLevel.missing
        evidence_score = min(0.8, 0.45 + 0.08 * len(direct) + 0.04 * len(supporting))
    elif supporting:
        status = ReviewPointStatus.identified
        summary = f"标准任务仅采集到辅助事实 {len(supporting)} 条，仍需补强直接条款。"
        rationale = f"标准审查任务已采集到部分事实，但尚不足以支持 {definition.title} 的直接判断。"
        evidence_level = EvidenceLevel.weak
        evidence_score = min(0.55, 0.25 + 0.05 * len(supporting))
    else:
        status = ReviewPointStatus.identified
        summary = "当前仅完成标准审查任务建模，尚未采集到候选事实。"
        rationale = f"标准审查任务已建立，但尚未找到支撑 {definition.title} 的结构化事实。"
        evidence_level = EvidenceLevel.missing
        evidence_score = 0.0

    missing_notes = []
    if missing_fields:
        missing_notes.append(f"当前任务尚未采集到关键字段：{', '.join(sorted(set(missing_fields)))}。")
    if not relevant:
        missing_notes.append("当前任务尚未采集到候选事实，需依赖后续规则、一致性或人工补证。")

    bundle = EvidenceBundle(
        direct_evidence=direct,
        supporting_evidence=supporting,
        conflicting_evidence=[],
        rebuttal_evidence=[],
        missing_evidence_notes=missing_notes,
        clause_roles=[clause.clause_role for clause in relevant if clause.clause_role.value != "未识别"],
        sufficiency_summary=summary,
        evidence_level=evidence_level,
        evidence_score=evidence_score,
    )
    return bundle, status, rationale


def _render_clause_quote(clause: ExtractedClause) -> str:
    if clause.normalized_value:
        return f"{clause.field_name}={clause.normalized_value}"
    return clause.content


def _dedupe_clauses(clauses: list[ExtractedClause]) -> list[ExtractedClause]:
    seen: set[tuple[str, str]] = set()
    result: list[ExtractedClause] = []
    for clause in clauses:
        key = (clause.field_name, clause.source_anchor)
        if key in seen:
            continue
        seen.add(key)
        result.append(clause)
    return result


TASK_FACT_COLLECTORS: dict[str, FactCollector] = {
    "RP-SME-001": _collect_policy_conflict_facts,
    "RP-SME-002": _collect_service_template_facts,
    "RP-SME-003": _collect_service_template_facts,
    "RP-SME-004": _collect_policy_conflict_facts,
    "RP-CONTRACT-002": _collect_contract_linkage_facts,
    "RP-CONTRACT-003": _collect_contract_linkage_facts,
    "RP-CONTRACT-005": _collect_contract_linkage_facts,
    "RP-PER-001": _collect_personnel_boundary_facts,
    "RP-PER-002": _collect_personnel_boundary_facts,
    "RP-PER-003": _collect_personnel_boundary_facts,
    "RP-PER-004": _collect_personnel_boundary_facts,
    "RP-PER-005": _collect_personnel_boundary_facts,
    "RP-PER-006": _collect_personnel_boundary_facts,
    "RP-PER-007": _collect_personnel_boundary_facts,
    "RP-STRUCT-003": _collect_structure_conflict_facts,
    "RP-STRUCT-005": _collect_structure_conflict_facts,
    "RP-CONS-003": _collect_policy_conflict_facts,
    "RP-CONS-004": _collect_contract_linkage_facts,
}

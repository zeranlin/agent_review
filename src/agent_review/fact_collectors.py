from __future__ import annotations

from collections.abc import Callable

from .models import (
    ClauseRole,
    Evidence,
    EvidenceBundle,
    EvidenceLevel,
    ExtractedClause,
    ReviewPointCondition,
    ReviewPointDefinition,
    ReviewPointStatus,
)


TaskEvidenceAssembler = Callable[[ReviewPointDefinition, list[ExtractedClause]], tuple[EvidenceBundle, ReviewPointStatus, str]]


def collect_task_facts(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    assembler = TASK_EVIDENCE_ASSEMBLERS.get(definition.catalog_id, _assemble_generic_task_evidence)
    return assembler(definition, extracted_clauses)


def _assemble_generic_task_evidence(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_relevant_clauses(definition, extracted_clauses)
    return _assemble_bundle_for_definition(definition, relevant)


def _assemble_policy_conflict_evidence(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(
        extracted_clauses,
        ["是否专门面向中小企业", "是否仍保留价格扣除条款", "中小企业声明函类型"],
    )
    return _assemble_bundle_for_definition(definition, relevant)


def _assemble_service_template_evidence(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(extracted_clauses, ["项目属性", "中小企业声明函类型"])
    return _assemble_bundle_for_definition(definition, relevant)


def _assemble_contract_linkage_evidence(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(
        extracted_clauses,
        ["付款节点", "考核条款", "验收标准", "扣款条款", "解约条款"],
    )
    return _assemble_bundle_for_definition(definition, relevant)


def _assemble_personnel_boundary_evidence(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_relevant_clauses(definition, extracted_clauses)
    relevant.extend(_collect_by_fields(extracted_clauses, ["项目属性", "采购标的"]))
    return _assemble_bundle_for_definition(definition, _dedupe_clauses(relevant))


def _assemble_structure_conflict_evidence(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(
        extracted_clauses,
        ["项目属性", "采购标的", "品目名称", "所属行业划分", "中小企业声明函类型", "质保期"],
    )
    return _assemble_bundle_for_definition(definition, relevant)


def _assemble_scoring_evidence(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(
        extracted_clauses,
        [
            "评分方法",
            "价格分",
            "技术分",
            "商务分",
            "样品要求",
            "现场演示要求",
            "样品分",
            "财务指标加分",
            "人员评分要求",
        ],
    )
    return _assemble_bundle_for_definition(definition, relevant)


def _assemble_restrictive_competition_evidence(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(
        extracted_clauses,
        [
            "是否指定品牌",
            "是否有限制产地厂家商标",
            "是否要求专利",
            "采购标的",
            "品目名称",
        ],
    )
    return _assemble_bundle_for_definition(definition, relevant)


def _assemble_template_conflict_evidence(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(
        extracted_clauses,
        [
            "项目属性",
            "采购标的",
            "中小企业声明函类型",
            "是否仍保留价格扣除条款",
            "是否允许联合体",
            "是否允许分包",
        ],
    )
    return _assemble_bundle_for_definition(definition, relevant)


def _assemble_consistency_policy_evidence(
    definition: ReviewPointDefinition,
    extracted_clauses: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    relevant = _collect_by_fields(
        extracted_clauses,
        [
            "是否专门面向中小企业",
            "是否仍保留价格扣除条款",
            "是否允许联合体",
            "是否允许分包",
            "分包比例",
            "是否为预留份额采购",
        ],
    )
    return _assemble_bundle_for_definition(definition, relevant)


def _assemble_bundle_for_definition(
    definition: ReviewPointDefinition,
    relevant: list[ExtractedClause],
) -> tuple[EvidenceBundle, ReviewPointStatus, str]:
    required_clauses = _dedupe_clauses(
        clause
        for condition in definition.required_conditions
        for clause in _match_condition_clauses(condition, relevant)
    )
    exclusion_clauses = _dedupe_clauses(
        clause
        for condition in definition.exclusion_conditions
        for clause in _match_condition_clauses(condition, relevant)
    )
    weak_role_clauses = [
        clause
        for clause in relevant
        if clause.clause_role
        in {
            ClauseRole.form_template,
            ClauseRole.policy_explanation,
            ClauseRole.document_definition,
            ClauseRole.appendix_reference,
        }
    ]
    rebuttal_clauses = [
        clause
        for clause in relevant
        if clause not in exclusion_clauses and _is_rebuttal_clause(clause)
    ]

    direct_clauses = [
        clause
        for clause in required_clauses
        if clause not in exclusion_clauses and clause not in weak_role_clauses and clause not in rebuttal_clauses
    ]
    supporting_clauses = [
        clause
        for clause in relevant
        if clause not in direct_clauses and clause not in exclusion_clauses and clause not in rebuttal_clauses
    ]
    conflicting_clauses = _dedupe_clauses([*exclusion_clauses, *weak_role_clauses])

    direct = [_to_evidence(clause) for clause in direct_clauses[:3]]
    supporting = [_to_evidence(clause) for clause in supporting_clauses[:4]]
    conflicting = [_to_evidence(clause) for clause in conflicting_clauses[:3]]
    rebuttal = [_to_evidence(clause) for clause in rebuttal_clauses[:3]]

    missing_fields = sorted(
        {
            field_name
            for condition in definition.required_conditions
            for field_name in condition.clause_fields
            if not any(clause.field_name == field_name for clause in direct_clauses + supporting_clauses)
        }
    )

    missing_notes: list[str] = []
    if missing_fields:
        missing_notes.append(f"当前任务尚未采集到关键字段：{', '.join(missing_fields)}。")
    if not direct and not supporting:
        missing_notes.append("当前任务尚未采集到有效候选事实，需依赖后续规则、一致性或人工补证。")
    if conflicting:
        missing_notes.append("当前任务存在冲突或弱来源证据，formal 前需结合适法性与质量关卡复核。")
    if rebuttal:
        missing_notes.append("当前任务已识别到反证或否定性事实，需防止过度定性。")

    evidence_level, evidence_score = _derive_bundle_strength(direct, supporting, conflicting, rebuttal)
    status = _derive_task_status(direct, supporting, conflicting, rebuttal)
    summary = _build_bundle_summary(direct, supporting, conflicting, rebuttal, missing_fields)
    rationale = _build_task_rationale(definition, direct, supporting, conflicting, rebuttal)

    bundle = EvidenceBundle(
        direct_evidence=direct,
        supporting_evidence=supporting,
        conflicting_evidence=conflicting,
        rebuttal_evidence=rebuttal,
        missing_evidence_notes=missing_notes,
        clause_roles=_dedupe_roles(relevant),
        sufficiency_summary=summary,
        evidence_level=evidence_level,
        evidence_score=evidence_score,
    )
    return bundle, status, rationale


def _collect_relevant_clauses(
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
        clause
        for clause in extracted_clauses
        if any(token and token in clause.content for token in signal_tokens)
    )


def _collect_by_fields(
    extracted_clauses: list[ExtractedClause],
    field_names: list[str],
) -> list[ExtractedClause]:
    return [clause for clause in extracted_clauses if clause.field_name in field_names]


def _match_condition_clauses(
    condition: ReviewPointCondition,
    clauses: list[ExtractedClause],
) -> list[ExtractedClause]:
    matched: list[ExtractedClause] = []
    field_names = set(condition.clause_fields)
    signal_tokens = {
        token
        for group in condition.signal_groups
        for token in group
        if token
    }
    for clause in clauses:
        if field_names and clause.field_name in field_names:
            matched.append(clause)
            continue
        if signal_tokens and any(
            token in clause.content or token in clause.normalized_value or token in " ".join(clause.relation_tags)
            for token in signal_tokens
        ):
            matched.append(clause)
    return _dedupe_clauses(matched)


def _is_rebuttal_clause(clause: ExtractedClause) -> bool:
    normalized = clause.normalized_value
    if normalized in {"否", "不允许"}:
        return True
    return any(tag in {"价格扣除不适用", "禁止"} for tag in clause.relation_tags)


def _to_evidence(clause: ExtractedClause) -> Evidence:
    if clause.normalized_value:
        return Evidence(
            quote=f"{clause.field_name}={clause.normalized_value}",
            section_hint=clause.source_anchor,
        )
    return Evidence(quote=clause.content, section_hint=clause.source_anchor)


def _derive_bundle_strength(
    direct: list[Evidence],
    supporting: list[Evidence],
    conflicting: list[Evidence],
    rebuttal: list[Evidence],
) -> tuple[EvidenceLevel, float]:
    if direct and not conflicting and not rebuttal:
        return EvidenceLevel.strong, min(0.9, 0.52 + 0.1 * len(direct) + 0.03 * len(supporting))
    if direct:
        return EvidenceLevel.moderate, min(0.78, 0.44 + 0.08 * len(direct) + 0.02 * len(supporting))
    if supporting:
        return EvidenceLevel.weak, min(0.58, 0.24 + 0.06 * len(supporting))
    return EvidenceLevel.missing, 0.0


def _derive_task_status(
    direct: list[Evidence],
    supporting: list[Evidence],
    conflicting: list[Evidence],
    rebuttal: list[Evidence],
) -> ReviewPointStatus:
    if direct and not conflicting and not rebuttal:
        return ReviewPointStatus.suspected
    if direct or supporting:
        return ReviewPointStatus.manual_confirmation
    return ReviewPointStatus.identified


def _build_bundle_summary(
    direct: list[Evidence],
    supporting: list[Evidence],
    conflicting: list[Evidence],
    rebuttal: list[Evidence],
    missing_fields: list[str],
) -> str:
    parts = [f"直接证据 {len(direct)} 条", f"辅助证据 {len(supporting)} 条"]
    if conflicting:
        parts.append(f"冲突证据 {len(conflicting)} 条")
    if rebuttal:
        parts.append(f"反证 {len(rebuttal)} 条")
    if missing_fields:
        parts.append(f"缺失字段 {len(missing_fields)} 项")
    return "；".join(parts) + "。"


def _build_task_rationale(
    definition: ReviewPointDefinition,
    direct: list[Evidence],
    supporting: list[Evidence],
    conflicting: list[Evidence],
    rebuttal: list[Evidence],
) -> str:
    if direct and not conflicting and not rebuttal:
        return f"标准审查任务已围绕 {definition.title} 采集到直接证据，可进入后续适法性判断。"
    if direct and (conflicting or rebuttal):
        return f"标准审查任务已围绕 {definition.title} 采集到支持证据，但同时存在冲突或反证，需谨慎裁决。"
    if supporting:
        return f"标准审查任务已围绕 {definition.title} 采集到辅助证据，但尚不足以直接定性。"
    return f"标准审查任务已建立，但尚未找到支撑 {definition.title} 的有效事实。"


def _dedupe_clauses(clauses: list[ExtractedClause] | tuple[ExtractedClause, ...] | object) -> list[ExtractedClause]:
    seen: set[tuple[str, str, str]] = set()
    result: list[ExtractedClause] = []
    for clause in clauses:
        key = (clause.field_name, clause.source_anchor, clause.normalized_value or clause.content)
        if key in seen:
            continue
        seen.add(key)
        result.append(clause)
    return result


def _dedupe_roles(clauses: list[ExtractedClause]) -> list[ClauseRole]:
    seen: set[ClauseRole] = set()
    result: list[ClauseRole] = []
    for clause in clauses:
        role = clause.clause_role
        if role == ClauseRole.unknown or role in seen:
            continue
        seen.add(role)
        result.append(role)
    return result


TASK_EVIDENCE_ASSEMBLERS: dict[str, TaskEvidenceAssembler] = {
    "RP-SME-001": _assemble_policy_conflict_evidence,
    "RP-SME-002": _assemble_service_template_evidence,
    "RP-SME-003": _assemble_service_template_evidence,
    "RP-SME-004": _assemble_policy_conflict_evidence,
    "RP-REST-001": _assemble_restrictive_competition_evidence,
    "RP-REST-002": _assemble_restrictive_competition_evidence,
    "RP-REST-003": _assemble_restrictive_competition_evidence,
    "RP-SCORE-001": _assemble_scoring_evidence,
    "RP-SCORE-002": _assemble_scoring_evidence,
    "RP-SCORE-003": _assemble_scoring_evidence,
    "RP-SCORE-004": _assemble_scoring_evidence,
    "RP-CONTRACT-002": _assemble_contract_linkage_evidence,
    "RP-CONTRACT-003": _assemble_contract_linkage_evidence,
    "RP-CONTRACT-005": _assemble_contract_linkage_evidence,
    "RP-CONTRACT-006": _assemble_contract_linkage_evidence,
    "RP-CONTRACT-007": _assemble_contract_linkage_evidence,
    "RP-PER-001": _assemble_personnel_boundary_evidence,
    "RP-PER-002": _assemble_personnel_boundary_evidence,
    "RP-PER-003": _assemble_personnel_boundary_evidence,
    "RP-PER-004": _assemble_personnel_boundary_evidence,
    "RP-PER-005": _assemble_personnel_boundary_evidence,
    "RP-PER-006": _assemble_personnel_boundary_evidence,
    "RP-PER-007": _assemble_personnel_boundary_evidence,
    "RP-PER-008": _assemble_personnel_boundary_evidence,
    "RP-STRUCT-001": _assemble_structure_conflict_evidence,
    "RP-STRUCT-002": _assemble_structure_conflict_evidence,
    "RP-STRUCT-003": _assemble_structure_conflict_evidence,
    "RP-STRUCT-004": _assemble_structure_conflict_evidence,
    "RP-STRUCT-005": _assemble_structure_conflict_evidence,
    "RP-STRUCT-006": _assemble_structure_conflict_evidence,
    "RP-TPL-002": _assemble_template_conflict_evidence,
    "RP-TPL-003": _assemble_template_conflict_evidence,
    "RP-TPL-004": _assemble_template_conflict_evidence,
    "RP-TPL-005": _assemble_template_conflict_evidence,
    "RP-TPL-006": _assemble_template_conflict_evidence,
    "RP-CONS-003": _assemble_policy_conflict_evidence,
    "RP-CONS-004": _assemble_contract_linkage_evidence,
    "RP-CONS-005": _assemble_consistency_policy_evidence,
    "RP-CONS-007": _assemble_consistency_policy_evidence,
    "RP-CONS-008": _assemble_consistency_policy_evidence,
}

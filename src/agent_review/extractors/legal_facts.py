from __future__ import annotations

import re

from ..legal_semantics import infer_clause_constraint, infer_legal_effect
from ..models import ClauseUnit, LegalFactCandidate
from ..ontology import ClauseSemanticType, EffectTag, LegalEffectType, RestrictionAxis, SemanticZoneType


def extract_legal_facts_from_units(
    clause_units: list[ClauseUnit],
    *,
    document_id: str,
    raw_text: str = "",
) -> list[LegalFactCandidate]:
    facts: list[LegalFactCandidate] = []
    for unit in clause_units:
        if not unit.text.strip():
            continue
        if EffectTag.catalog in unit.effect_tags or EffectTag.public_copy_noise in unit.effect_tags:
            continue
        fact_type = _infer_fact_type(unit)
        if not fact_type:
            continue
        fact_zone_type = _infer_fact_zone_type(unit, fact_type)
        facts.append(
            LegalFactCandidate(
                fact_id=f"LF-{len(facts) + 1:04d}",
                document_id=document_id,
                source_unit_id=unit.unit_id,
                fact_type=fact_type,
                zone_type=fact_zone_type.value,
                clause_semantic_type=unit.clause_semantic_type.value,
                effect_tags=[item.value for item in unit.effect_tags],
                subject=unit.clause_constraint.subject,
                predicate=_infer_predicate(unit.text),
                object_text=unit.text.strip(),
                normalized_terms=_normalized_terms(unit),
                constraint_type=_infer_constraint_type(unit),
                constraint_value=_infer_constraint_value(unit),
                legal_effect_type=unit.legal_effect_type.value,
                source_role=_infer_source_role(unit),
                project_binding=_infer_project_binding(unit),
                binding_strength=_infer_binding_strength(unit),
                rebuttal_strength=_infer_rebuttal_strength(unit),
                condition_scope=_infer_condition_scope(unit),
                policy_branch=_infer_policy_branch(unit),
                evidence_stage=_infer_evidence_stage(unit),
                counterparty=_infer_counterparty(unit),
                anchor=unit.anchor.to_dict(),
                table_context=dict(unit.table_context),
                supporting_context=_supporting_context(unit),
                confidence=round(unit.confidence, 3),
                needs_llm_disambiguation=_needs_llm_disambiguation(unit),
            )
        )
    facts.extend(
        _extract_fallback_facts_from_text(
            raw_text,
            document_id=document_id,
            existing_texts={re.sub(r"\s+", "", item.object_text) for item in facts if item.object_text.strip()},
            start_index=len(facts) + 1,
        )
    )
    return facts


def _extract_fallback_facts_from_text(
    raw_text: str,
    *,
    document_id: str,
    existing_texts: set[str],
    start_index: int,
) -> list[LegalFactCandidate]:
    if not raw_text.strip():
        return []

    facts: list[LegalFactCandidate] = []
    current_zone = SemanticZoneType.mixed_or_uncertain
    current_semantic = ClauseSemanticType.unknown_clause
    for line_no, line in enumerate(raw_text.splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        compact = re.sub(r"\s+", "", text)
        if compact in existing_texts:
            continue

        heading_zone, heading_semantic = _fallback_heading_context(text)
        if heading_zone is not None:
            current_zone = heading_zone
            current_semantic = heading_semantic
            continue

        candidate = _fallback_fact_candidate(text, current_zone, current_semantic)
        if candidate is None:
            continue
        zone_type, clause_semantic_type, fact_type = candidate
        legal_effect = infer_legal_effect(
            text=text,
            zone_type=zone_type,
            clause_semantic_type=clause_semantic_type,
        )
        constraint = infer_clause_constraint(text, legal_effect)
        facts.append(
            LegalFactCandidate(
                fact_id=f"LF-{start_index + len(facts):04d}",
                document_id=document_id,
                source_unit_id=f"fallback-line:{line_no}",
                fact_type=fact_type,
                zone_type=zone_type.value,
                clause_semantic_type=clause_semantic_type.value,
                effect_tags=[],
                subject=constraint.subject,
                predicate=_infer_predicate(text),
                object_text=text,
                normalized_terms=_dedupe_strings(
                    [
                        *constraint.qualifier_tokens,
                        *constraint.region_tokens,
                        *constraint.industry_tokens,
                        constraint.evidence_source,
                        *_policy_terms_from_text(text),
                    ]
                ),
                constraint_type=_infer_constraint_type_from_constraint(zone_type, clause_semantic_type, constraint),
                constraint_value=_infer_constraint_value_from_constraint(text, zone_type, constraint),
                legal_effect_type=legal_effect.value,
                source_role=_infer_source_role_from_fallback(zone_type, clause_semantic_type, text),
                project_binding=_infer_project_binding_from_text(text),
                binding_strength=_infer_fallback_binding_strength(text, zone_type, clause_semantic_type),
                rebuttal_strength=_infer_rebuttal_strength_from_text(text),
                condition_scope=_infer_condition_scope_from_text(text),
                policy_branch=_infer_policy_branch_from_text(text),
                evidence_stage=_infer_fallback_evidence_stage(zone_type, clause_semantic_type),
                counterparty=_infer_counterparty_from_text(text),
                anchor={"line_hint": f"line:{line_no}", "block_no": line_no, "paragraph_no": line_no},
                table_context={},
                supporting_context=[],
                confidence=0.76 if zone_type == SemanticZoneType.qualification else 0.72,
                needs_llm_disambiguation=zone_type == SemanticZoneType.mixed_or_uncertain,
            )
        )
        existing_texts.add(compact)
    return facts


def _fallback_heading_context(text: str) -> tuple[SemanticZoneType | None, ClauseSemanticType]:
    compact = re.sub(r"\s+", "", text)
    if any(token in compact for token in ["资格要求", "申请人的资格要求", "投标人资格要求", "特定资格要求", "一般资格要求"]):
        return SemanticZoneType.qualification, ClauseSemanticType.qualification_condition
    if any(token in compact for token in ["评分标准", "评标信息", "评审要求", "评分项"]):
        return SemanticZoneType.scoring, ClauseSemanticType.scoring_rule
    if any(token in compact for token in ["合同条款", "履约担保", "付款方式", "验收", "违约责任"]):
        return SemanticZoneType.contract, ClauseSemanticType.acceptance_term
    if any(token in compact for token in ["技术要求", "技术参数", "用户需求书"]):
        return SemanticZoneType.technical, ClauseSemanticType.technical_requirement
    return None, ClauseSemanticType.unknown_clause


def _fallback_fact_candidate(
    text: str,
    current_zone: SemanticZoneType,
    current_semantic: ClauseSemanticType,
) -> tuple[SemanticZoneType, ClauseSemanticType, str] | None:
    compact = re.sub(r"\s+", "", text)
    if "投标人" in text and any(
        token in compact
        for token in ["科技型中小企业", "高新技术企业", "纳税信用", "成立满", "同类项目业绩", "类似项目业绩"]
    ):
        zone_type = SemanticZoneType.qualification if current_zone != SemanticZoneType.scoring else current_zone
        clause_semantic_type = ClauseSemanticType.qualification_condition
        fact_type = "performance_requirement" if any(token in compact for token in ["同类项目业绩", "类似项目业绩"]) else "qualification_requirement"
        return zone_type, clause_semantic_type, fact_type
    if any(token in compact for token in ["检测中心", "检测机构", "实验室", "税务部门"]) and any(
        token in compact for token in ["出具", "提供", "检测报告", "证明"]
    ):
        zone_type = current_zone if current_zone in {SemanticZoneType.qualification, SemanticZoneType.technical} else SemanticZoneType.technical
        clause_semantic_type = (
            ClauseSemanticType.qualification_material_requirement
            if zone_type == SemanticZoneType.qualification
            else ClauseSemanticType.technical_requirement
        )
        return zone_type, clause_semantic_type, "evidence_source_requirement"
    if current_zone == SemanticZoneType.scoring and any(token in compact for token in ["得分", "评分", "最高得", "加分", "扣分"]):
        if any(token in compact for token in ["证书", "认证", "检测报告", "ITSS", "营业收入", "利润率", "资产规模", "信用评价", "业绩", "方案"]):
            return SemanticZoneType.scoring, ClauseSemanticType.scoring_factor, "scoring_factor"
    if "履约担保" in compact or "质量保证金" in compact or "履约保证金" in compact:
        return SemanticZoneType.contract, ClauseSemanticType.acceptance_term, "acceptance_term"
    if "第三方检测费用" in compact and "中标人承担" in compact:
        return SemanticZoneType.contract, ClauseSemanticType.acceptance_term, "acceptance_term"
    if "投标报价不得低于预算金额" in compact or ("预算金额" in compact and "无效投标" in compact):
        return SemanticZoneType.business, ClauseSemanticType.business_requirement, "delivery_requirement"
    if "专门面向中小企业采购的项目" in compact or "非专门面向中小企业采购的项目" in compact:
        return SemanticZoneType.policy_explanation, ClauseSemanticType.conditional_policy, "policy_matrix_statement"
    if any(token in compact for token in ["本项目专门面向中小企业采购", "本项目为非专门面向中小企业采购项目", "价格扣除不适用本项目", "本项目仍适用价格扣除"]):
        return SemanticZoneType.policy_explanation, ClauseSemanticType.policy_clause, "policy_statement"
    return None


def _infer_constraint_type_from_constraint(
    zone_type: SemanticZoneType,
    clause_semantic_type: ClauseSemanticType,
    constraint,
) -> str:
    if zone_type == SemanticZoneType.scoring:
        return "scoring_bonus"
    if clause_semantic_type in {ClauseSemanticType.payment_term, ClauseSemanticType.acceptance_term}:
        return "mandatory"
    if constraint.evidence_source:
        return "source_designation"
    if constraint.region_tokens:
        return "regional_limit"
    if any(axis == RestrictionAxis.establishment_years for axis in constraint.restriction_axes):
        return "time_limit"
    if any(axis == RestrictionAxis.performance_count for axis in constraint.restriction_axes):
        return "range_limit"
    return "mandatory"


def _infer_constraint_value_from_constraint(
    text: str,
    zone_type: SemanticZoneType,
    constraint,
) -> dict[str, object]:
    value: dict[str, object] = {}
    if constraint.region_tokens:
        value["region"] = _normalize_extracted_scope(constraint.region_tokens[0])
    if constraint.industry_tokens:
        value["industry_scope"] = _normalize_extracted_scope(constraint.industry_tokens[0])
    if constraint.evidence_source:
        value["evidence_source"] = _normalize_extracted_scope(constraint.evidence_source)
    min_years = _extract_first_int(text, r"成立满(\d+)年")
    if min_years is not None:
        value["min_years"] = min_years
    min_count = _extract_first_int(text, r"(?:不少于|至少|满)(\d+)(?:个|项|份)")
    if min_count is not None:
        value["min_count"] = min_count
    score = _extract_first_int(text, r"(\d+)\s*分")
    if score is not None and (zone_type == SemanticZoneType.scoring or _looks_like_scoring_factor(text)):
        value["score"] = score
    clause_type = (
        ClauseSemanticType.qualification_material_requirement
        if zone_type == SemanticZoneType.qualification and constraint.evidence_source
        else ClauseSemanticType.acceptance_term
        if zone_type == SemanticZoneType.contract and "验收" in text
        else ClauseSemanticType.payment_term
        if zone_type == SemanticZoneType.contract and any(token in text for token in ["付款", "支付", "尾款"])
        else ClauseSemanticType.scoring_factor
        if zone_type == SemanticZoneType.scoring
        else ClauseSemanticType.technical_requirement
        if zone_type == SemanticZoneType.technical
        else ClauseSemanticType.unknown_clause
    )
    return _augment_constraint_value_from_text(text, zone_type, clause_type, value)


def _infer_fallback_evidence_stage(zone_type: SemanticZoneType, clause_semantic_type: ClauseSemanticType) -> str:
    if zone_type == SemanticZoneType.qualification:
        return "qualification"
    if zone_type == SemanticZoneType.scoring:
        return "evaluation"
    if zone_type == SemanticZoneType.contract:
        if clause_semantic_type == ClauseSemanticType.acceptance_term:
            return "acceptance"
        return "contract_performance"
    if zone_type == SemanticZoneType.technical:
        return "technical_response"
    return "unknown"


def _infer_counterparty_from_text(text: str) -> str:
    if "采购人" in text:
        return "采购人"
    if "中标人" in text:
        return "中标人"
    if "供应商" in text:
        return "供应商"
    if "投标人" in text:
        return "投标人"
    return ""


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        current = str(item).strip()
        if not current or current in seen:
            continue
        seen.add(current)
        ordered.append(current)
    return ordered


def _infer_fact_type(unit: ClauseUnit) -> str:
    clause_type = unit.clause_semantic_type
    if unit.legal_effect_type == LegalEffectType.evidence_source_requirement:
        return "evidence_source_requirement"
    if unit.clause_constraint.evidence_source:
        return "evidence_source_requirement"
    if _looks_like_scoring_factor(unit.text):
        return "scoring_factor"
    if _looks_like_policy_statement(unit.text):
        return "policy_statement" if _infer_project_binding(unit) else "policy_reference"
    if clause_type == ClauseSemanticType.conditional_policy:
        return "policy_matrix_statement"
    if clause_type == ClauseSemanticType.policy_clause:
        if _infer_project_binding(unit):
            return "policy_statement"
        return "policy_reference"
    if clause_type == ClauseSemanticType.qualification_condition:
        if any(axis == RestrictionAxis.performance_count for axis in unit.clause_constraint.restriction_axes):
            return "performance_requirement"
        return "qualification_requirement"
    if clause_type == ClauseSemanticType.qualification_material_requirement:
        if unit.clause_constraint.evidence_source:
            return "evidence_source_requirement"
        return "qualification_material_requirement"
    if clause_type in {ClauseSemanticType.scoring_rule, ClauseSemanticType.scoring_factor}:
        if any(token in unit.text for token in ["得", "分值", "扣分", "分"]) or unit.zone_type == SemanticZoneType.scoring:
            return "scoring_factor"
        return "scoring_scale"
    if clause_type == ClauseSemanticType.technical_requirement:
        return "technical_parameter"
    if clause_type == ClauseSemanticType.sample_or_demo_requirement:
        return "technical_parameter"
    if clause_type == ClauseSemanticType.business_requirement:
        return "delivery_requirement"
    if clause_type == ClauseSemanticType.payment_term:
        return "payment_term"
    if clause_type == ClauseSemanticType.acceptance_term:
        return "acceptance_term"
    if clause_type == ClauseSemanticType.breach_term:
        return "breach_term"
    if clause_type == ClauseSemanticType.termination_term:
        return "termination_term"
    if clause_type in {ClauseSemanticType.template_instruction, ClauseSemanticType.declaration_template, ClauseSemanticType.example_clause}:
        return "template_reference"
    if clause_type == ClauseSemanticType.reference_clause:
        return "template_reference"
    if unit.legal_effect_type == LegalEffectType.contract_obligation:
        if "履约担保" in unit.text or "履约保证金" in unit.text or "质量保证金" in unit.text:
            return "acceptance_term"
        if "付款" in unit.text or "支付" in unit.text or "尾款" in unit.text:
            return "payment_term"
        if "验收" in unit.text:
            return "acceptance_term"
    return ""


def _infer_fact_zone_type(unit: ClauseUnit, fact_type: str) -> SemanticZoneType:
    if fact_type == "scoring_factor" or _looks_like_scoring_factor(unit.text):
        return SemanticZoneType.scoring
    if fact_type in {"payment_term", "acceptance_term", "breach_term", "termination_term"}:
        return SemanticZoneType.contract
    if fact_type == "delivery_requirement" and _looks_like_price_floor_clause(unit.text):
        return SemanticZoneType.business
    if fact_type == "evidence_source_requirement" and unit.zone_type == SemanticZoneType.mixed_or_uncertain:
        return SemanticZoneType.technical
    return unit.zone_type


def _infer_predicate(text: str) -> str:
    for token in ["须具备", "应具备", "须提供", "应提供", "得分", "扣分", "支付", "验收", "解除", "不适用", "执行价格扣除", "专门面向中小企业", "非专门面向中小企业"]:
        if token in text:
            return token
    return ""


def _normalized_terms(unit: ClauseUnit) -> list[str]:
    tokens = [
        *unit.clause_constraint.qualifier_tokens,
        *unit.clause_constraint.region_tokens,
        *unit.clause_constraint.industry_tokens,
    ]
    conditional_context = unit.conditional_context or {}
    if conditional_context.get("policy_branch") == "set_aside":
        tokens.append("专门面向中小企业路径")
    if conditional_context.get("policy_branch") == "non_set_aside":
        tokens.append("非专门面向中小企业路径")
    if conditional_context.get("price_deduction_rule") == "allowed":
        tokens.append("价格扣除保留")
    if conditional_context.get("price_deduction_rule") == "forbidden":
        tokens.append("价格扣除不适用")
    if conditional_context.get("project_binding") == "true":
        tokens.append("项目事实绑定")
    if unit.clause_constraint.evidence_source:
        tokens.append(unit.clause_constraint.evidence_source)
    tokens.extend(_policy_terms_from_text(unit.text))
    tokens.extend(_semantic_terms_from_text(unit.text, unit.zone_type, unit.clause_semantic_type))
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        current = token.strip()
        if current and current not in seen:
            seen.add(current)
            ordered.append(current)
    return ordered


def _infer_constraint_type(unit: ClauseUnit) -> str:
    if unit.zone_type == SemanticZoneType.scoring:
        return "scoring_bonus"
    if unit.clause_semantic_type in {ClauseSemanticType.payment_term, ClauseSemanticType.acceptance_term}:
        return "mandatory"
    if unit.clause_constraint.evidence_source:
        return "source_designation"
    if unit.clause_constraint.region_tokens:
        return "regional_limit"
    if any(axis == RestrictionAxis.establishment_years for axis in unit.clause_constraint.restriction_axes):
        return "time_limit"
    if any(axis == RestrictionAxis.performance_count for axis in unit.clause_constraint.restriction_axes):
        return "range_limit"
    return "mandatory"


def _infer_constraint_value(unit: ClauseUnit) -> dict[str, object]:
    value: dict[str, object] = {}
    if unit.clause_constraint.region_tokens:
        value["region"] = _normalize_extracted_scope(unit.clause_constraint.region_tokens[0])
    if unit.clause_constraint.industry_tokens:
        value["industry_scope"] = _normalize_extracted_scope(unit.clause_constraint.industry_tokens[0])
    if unit.clause_constraint.evidence_source:
        value["evidence_source"] = _normalize_extracted_scope(unit.clause_constraint.evidence_source)
    min_years = _extract_first_int(unit.text, r"成立满(\d+)年")
    if min_years is not None:
        value["min_years"] = min_years
    min_count = _extract_first_int(unit.text, r"(?:不少于|至少|满)(\d+)(?:个|项|份)")
    if min_count is not None:
        value["min_count"] = min_count
    score = _extract_first_int(unit.text, r"(\d+)\s*分")
    if score is not None and (unit.zone_type == SemanticZoneType.scoring or _looks_like_scoring_factor(unit.text)):
        value["score"] = score
    return _augment_constraint_value_from_text(unit.text, unit.zone_type, unit.clause_semantic_type, value)


def _extract_first_int(text: str, pattern: str) -> int | None:
    match = re.search(pattern, re.sub(r"\s+", "", text))
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _infer_evidence_stage(unit: ClauseUnit) -> str:
    if unit.zone_type == SemanticZoneType.qualification:
        return "qualification"
    if unit.zone_type == SemanticZoneType.scoring:
        return "evaluation"
    if unit.zone_type == SemanticZoneType.contract:
        if unit.clause_semantic_type == ClauseSemanticType.acceptance_term:
            return "acceptance"
        return "contract_performance"
    if any(token in unit.text for token in ["投标时", "投标文件中"]):
        return "bidding"
    return "unknown"


def _infer_counterparty(unit: ClauseUnit) -> str:
    text = unit.text
    if "采购人" in text:
        return "采购人"
    if any(token in text for token in ["中标人", "供应商", "投标人"]):
        return "中标人" if "中标人" in text else "供应商" if "供应商" in text else "投标人"
    return ""


def _supporting_context(unit: ClauseUnit) -> list[str]:
    context: list[str] = []
    heading = str(unit.table_context.get("heading_context", "")).strip()
    if heading:
        context.append(heading)
    title = str(unit.table_context.get("title", "")).strip()
    if title and title not in context:
        context.append(title)
    row_label = str(unit.table_context.get("row_label", "")).strip()
    if row_label and row_label not in context:
        context.append(row_label)
    return context[:3]


def _needs_llm_disambiguation(unit: ClauseUnit) -> bool:
    if unit.confidence < 0.65:
        return True
    if unit.zone_type == SemanticZoneType.mixed_or_uncertain:
        return True
    if unit.effect_tags and all(tag in {EffectTag.template, EffectTag.example, EffectTag.reference_only} for tag in unit.effect_tags):
        return False
    return unit.zone_type in {SemanticZoneType.qualification, SemanticZoneType.scoring} and (
        "检测报告" in unit.text or "证书" in unit.text or "业绩" in unit.text
    )


def _infer_source_role(unit: ClauseUnit) -> str:
    if EffectTag.template in unit.effect_tags:
        return "template"
    if EffectTag.reference_only in unit.effect_tags:
        return "reference"
    if unit.zone_type == SemanticZoneType.policy_explanation:
        return "policy"
    if unit.zone_type == SemanticZoneType.contract:
        return "contract"
    if unit.zone_type == SemanticZoneType.scoring:
        return "scoring"
    if unit.zone_type == SemanticZoneType.qualification:
        return "qualification"
    return "unknown"


def _infer_project_binding(unit: ClauseUnit) -> bool:
    conditional_context = unit.conditional_context or {}
    if conditional_context.get("project_binding") == "true":
        return True
    return _infer_project_binding_from_text(unit.text)


def _infer_binding_strength(unit: ClauseUnit) -> str:
    if EffectTag.template in unit.effect_tags or EffectTag.reference_only in unit.effect_tags:
        return "weak"
    if _infer_project_binding(unit):
        return "strong"
    if unit.clause_semantic_type == ClauseSemanticType.conditional_policy:
        return "conditional"
    if unit.zone_type in {
        SemanticZoneType.qualification,
        SemanticZoneType.scoring,
        SemanticZoneType.technical,
        SemanticZoneType.business,
        SemanticZoneType.contract,
    }:
        return "strong"
    return "contextual"


def _infer_rebuttal_strength(unit: ClauseUnit) -> str:
    compact = re.sub(r"\s+", "", unit.text)
    if any(token in compact for token in ["不适用", "不再执行", "不执行", "非专门面向中小企业"]):
        return "strong"
    if any(token in compact for token in ["仅供参考", "示例", "格式"]):
        return "weak"
    return "none"


def _infer_condition_scope(unit: ClauseUnit) -> str:
    conditional_context = unit.conditional_context or {}
    if conditional_context.get("conditional_policy") == "true":
        return "project_bound" if conditional_context.get("project_binding") == "true" else "conditional_only"
    return "project_bound" if _infer_project_binding(unit) else "standalone"


def _infer_policy_branch(unit: ClauseUnit) -> str:
    conditional_context = unit.conditional_context or {}
    if conditional_context.get("policy_branch"):
        return conditional_context["policy_branch"]
    return _infer_policy_branch_from_text(unit.text)


def _infer_source_role_from_fallback(
    zone_type: SemanticZoneType,
    clause_semantic_type: ClauseSemanticType,
    text: str,
) -> str:
    if clause_semantic_type == ClauseSemanticType.conditional_policy:
        return "policy"
    if zone_type == SemanticZoneType.policy_explanation:
        return "policy"
    if any(token in text for token in ["示例", "格式", "模板"]):
        return "template"
    return zone_type.value


def _infer_project_binding_from_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return any(token in compact for token in ["本项目", "本包", "本采购包", "本次采购"])


def _infer_fallback_binding_strength(
    text: str,
    zone_type: SemanticZoneType,
    clause_semantic_type: ClauseSemanticType,
) -> str:
    if _infer_project_binding_from_text(text):
        return "strong"
    if clause_semantic_type == ClauseSemanticType.conditional_policy:
        return "conditional"
    if zone_type in {
        SemanticZoneType.qualification,
        SemanticZoneType.scoring,
        SemanticZoneType.technical,
        SemanticZoneType.business,
        SemanticZoneType.contract,
    }:
        return "strong"
    return "contextual"


def _infer_rebuttal_strength_from_text(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    if any(token in compact for token in ["不适用", "不再执行", "不执行", "非专门面向中小企业"]):
        return "strong"
    if any(token in compact for token in ["示例", "格式", "模板"]):
        return "weak"
    return "none"


def _infer_condition_scope_from_text(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    if "专门面向中小企业采购的项目" in compact or "非专门面向中小企业采购的项目" in compact:
        return "conditional_only"
    if _infer_project_binding_from_text(text):
        return "project_bound"
    return "standalone"


def _infer_policy_branch_from_text(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    if "非专门面向中小企业" in compact:
        return "non_set_aside"
    if "专门面向中小企业" in compact:
        return "set_aside"
    return ""


def _looks_like_policy_statement(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if "中小企业" not in compact and "价格扣除" not in compact:
        return False
    return any(
        token in compact
        for token in [
            "本项目专门面向中小企业采购",
            "本项目为非专门面向中小企业采购项目",
            "本项目非专门面向中小企业采购",
            "价格扣除不适用本项目",
            "本项目仍适用价格扣除",
            "本项目执行价格扣除",
        ]
    )


def _looks_like_scoring_factor(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not any(token in compact for token in ["得分", "评分", "最高得", "加分", "扣分", "分值"]) and not re.search(r"得\d+(?:\.\d+)?分", compact):
        return False
    return any(
        token in compact
        for token in ["证书", "认证", "检测报告", "ITSS", "营业收入", "利润率", "资产规模", "信用评价", "业绩", "方案"]
    )


def _policy_terms_from_text(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    tokens: list[str] = []
    if any(token in compact for token in ["本项目", "本包", "本采购包", "本次采购"]):
        tokens.append("项目事实绑定")
    if "非专门面向中小企业" in compact:
        tokens.append("非专门面向中小企业路径")
    elif "专门面向中小企业" in compact:
        tokens.append("专门面向中小企业路径")
    if "价格扣除" in compact:
        if any(token in compact for token in ["不适用", "不再执行", "不执行"]):
            tokens.append("价格扣除不适用")
        elif any(token in compact for token in ["仍适用", "继续适用", "执行", "给予", "参与评审"]):
            tokens.append("价格扣除保留")
    return tokens


def _semantic_terms_from_text(
    text: str,
    zone_type: SemanticZoneType,
    clause_semantic_type: ClauseSemanticType,
) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    tokens: list[str] = []
    if any(token in compact for token in ["检测中心", "检测机构", "实验室", "税务部门", "研究院"]):
        tokens.append("指定机构来源")
    if "检测报告" in compact:
        tokens.append("检测报告")
    if "证明" in compact:
        tokens.append("证明材料")
    if any(token in compact for token in ["证书", "认证"]) and zone_type == SemanticZoneType.scoring:
        tokens.append("证书评分项")
    if any(token in compact for token in ["财务", "营业收入", "利润率", "资产规模"]) and zone_type == SemanticZoneType.scoring:
        tokens.append("财务指标评分项")
    if any(token in compact for token in ["尾款", "验收合格后支付", "验收后支付"]):
        tokens.append("验收付款联动")
    if any(token in compact for token in ["考核", "满意度"]) and any(token in compact for token in ["付款", "支付", "尾款"]):
        tokens.append("考核付款联动")
    if any(token in compact for token in ["采购人确认", "采购人认为", "最终解释", "单方判断", "确定验收标准"]):
        tokens.append("单方弹性判断")
    if clause_semantic_type == ClauseSemanticType.acceptance_term and "第三方检测费用" in compact:
        tokens.append("第三方检测费用")
    if any(token in compact for token in ["履约担保", "履约保证金"]) and "质量保证金" in compact:
        tokens.append("履约转质保")
    if "银行转账" in compact:
        tokens.append("银行转账")
    if "无息退还" in compact:
        tokens.append("无息退还")
    if "第三方检测费用" in compact and "中标人承担" in compact:
        tokens.append("检测费用转嫁")
    if "无论检测结果是否合格" in compact:
        tokens.append("结果无关承担")
    if _looks_like_price_floor_clause(text):
        tokens.append("预算比例最低价")
    return tokens


def _augment_constraint_value_from_text(
    text: str,
    zone_type: SemanticZoneType,
    clause_semantic_type: ClauseSemanticType,
    base: dict[str, object],
) -> dict[str, object]:
    value = dict(base)
    compact = re.sub(r"\s+", "", text)

    evidence_source = _infer_designated_source_category(compact)
    if evidence_source and "source_category" not in value:
        value["source_category"] = evidence_source
    evidence_kind = _infer_evidence_kind(compact)
    if evidence_kind and "evidence_kind" not in value:
        value["evidence_kind"] = evidence_kind

    if (
        zone_type == SemanticZoneType.scoring
        or clause_semantic_type in {ClauseSemanticType.scoring_rule, ClauseSemanticType.scoring_factor}
        or _looks_like_scoring_factor(text)
    ):
        scoring_item_type = _infer_scoring_item_type(compact)
        if scoring_item_type:
            value.setdefault("scoring_item_type", scoring_item_type)
        scoring_mode = _infer_scoring_mode(compact)
        if scoring_mode:
            value.setdefault("scoring_mode", scoring_mode)

    if zone_type == SemanticZoneType.contract or clause_semantic_type in {
        ClauseSemanticType.payment_term,
        ClauseSemanticType.acceptance_term,
        ClauseSemanticType.breach_term,
        ClauseSemanticType.termination_term,
    }:
        decision_mode = _infer_contract_decision_mode(compact)
        if decision_mode:
            value.setdefault("decision_mode", decision_mode)
        payment_linkage = _infer_payment_linkage(compact)
        if payment_linkage:
            value.setdefault("payment_linkage", payment_linkage)
        payment_phase = _infer_payment_phase(compact)
        if payment_phase:
            value.setdefault("payment_phase", payment_phase)
        contract_control = _infer_contract_control(compact)
        if contract_control:
            value.setdefault("contract_control", contract_control)
        guarantee_transform = _infer_guarantee_transform(compact)
        if guarantee_transform:
            value.setdefault("guarantee_transform", guarantee_transform)
        guarantee_ratio = _infer_guarantee_ratio(compact)
        if guarantee_ratio is not None:
            value.setdefault("guarantee_ratio", guarantee_ratio)
        payment_method = _infer_payment_method(compact)
        if payment_method:
            value.setdefault("payment_method", payment_method)
        refund_policy = _infer_refund_policy(compact)
        if refund_policy:
            value.setdefault("refund_policy", refund_policy)
        cost_bearer = _infer_cost_bearer(compact)
        if cost_bearer:
            value.setdefault("cost_bearer", cost_bearer)
        result_condition = _infer_result_condition(compact)
        if result_condition:
            value.setdefault("result_condition", result_condition)

    if zone_type == SemanticZoneType.business or clause_semantic_type == ClauseSemanticType.business_requirement or _looks_like_price_floor_clause(text):
        price_floor_ratio = _infer_price_floor_ratio(compact)
        if price_floor_ratio is not None:
            value.setdefault("price_floor_ratio", price_floor_ratio)
        price_floor_base = _infer_price_floor_base(compact)
        if price_floor_base:
            value.setdefault("price_floor_base", price_floor_base)
        rejection_trigger = _infer_rejection_trigger(compact)
        if rejection_trigger:
            value.setdefault("rejection_trigger", rejection_trigger)
        pricing_control = _infer_pricing_control(compact)
        if pricing_control:
            value.setdefault("pricing_control", pricing_control)
    return value


def _infer_designated_source_category(compact: str) -> str:
    for token in ["检测中心", "检测机构", "实验室", "税务部门", "研究院"]:
        if token in compact:
            return token
    return ""


def _infer_evidence_kind(compact: str) -> str:
    for token in ["检测报告", "证明", "证书", "合同扫描件", "营业执照复印件"]:
        if token in compact:
            return token
    return ""


def _infer_scoring_item_type(compact: str) -> str:
    if any(token in compact for token in ["证书", "认证证书", "管理体系认证", "ITSS"]):
        return "certificate"
    if "检测报告" in compact:
        return "report"
    if any(token in compact for token in ["财务", "营业收入", "利润率", "资产规模"]):
        return "financial"
    if any(token in compact for token in ["项目负责人", "人员配置", "学历", "职称", "社保"]):
        return "personnel"
    if any(token in compact for token in ["业绩", "同类项目"]):
        return "performance"
    if any(token in compact for token in ["方案", "实施方案", "售后服务方案"]):
        return "plan"
    if any(token in compact for token in ["信用评价", "信用分", "信用等级"]):
        return "credit"
    return ""


def _infer_scoring_mode(compact: str) -> str:
    if any(token in compact for token in ["扣分", "每缺项扣", "每处缺陷扣"]):
        return "deduction"
    if any(token in compact for token in ["得分", "得", "最高得", "加分"]):
        return "additive"
    return ""


def _infer_contract_decision_mode(compact: str) -> str:
    if any(token in compact for token in ["采购人确认", "采购人认为", "最终解释", "单方判断", "优胜的原则", "确定验收标准"]):
        return "unilateral_discretion"
    return ""


def _infer_payment_linkage(compact: str) -> str:
    if any(token in compact for token in ["考核", "满意度"]) and any(token in compact for token in ["付款", "支付", "尾款"]):
        return "assessment_or_satisfaction"
    if "验收" in compact and any(token in compact for token in ["付款", "支付", "尾款"]):
        return "acceptance"
    return ""


def _infer_payment_phase(compact: str) -> str:
    if "尾款" in compact:
        return "final_payment"
    if any(token in compact for token in ["预付款", "预付"]):
        return "advance_payment"
    return ""


def _infer_contract_control(compact: str) -> str:
    if "第三方检测费用" in compact and "承担" in compact:
        return "test_cost_allocation"
    if any(token in compact for token in ["履约担保", "履约保证金"]) and "质量保证金" in compact:
        return "guarantee_fund_occupation"
    if any(token in compact for token in ["付款", "支付", "尾款"]) and any(token in compact for token in ["考核", "满意度", "验收"]):
        return "payment_control"
    if "验收" in compact and any(token in compact for token in ["采购人确认", "最终解释", "优胜的原则", "确定验收标准"]):
        return "acceptance_control"
    return ""


def _infer_guarantee_transform(compact: str) -> str:
    if any(token in compact for token in ["履约担保", "履约保证金"]) and "质量保证金" in compact:
        return "performance_to_quality"
    return ""


def _infer_guarantee_ratio(compact: str) -> float | None:
    match = re.search(r"合同总价的(\d+(?:\.\d+)?)%", compact)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _infer_payment_method(compact: str) -> str:
    if "银行转账" in compact:
        return "bank_transfer"
    return ""


def _infer_refund_policy(compact: str) -> str:
    if "无息退还" in compact:
        return "no_interest_return"
    return ""


def _infer_cost_bearer(compact: str) -> str:
    if "中标人承担" in compact:
        return "awardee"
    if "供应商承担" in compact:
        return "supplier"
    return ""


def _infer_result_condition(compact: str) -> str:
    if "无论检测结果是否合格" in compact or "无论结果是否合格" in compact:
        return "regardless_of_result"
    return ""


def _infer_price_floor_ratio(compact: str) -> float | None:
    match = re.search(r"预算金额的(\d+(?:\.\d+)?)%", compact)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _infer_price_floor_base(compact: str) -> str:
    if "预算金额" in compact:
        return "budget_amount"
    if "最高限价" in compact:
        return "ceiling_price"
    return ""


def _infer_rejection_trigger(compact: str) -> str:
    if "无效投标" in compact:
        return "invalid_bid"
    return ""


def _infer_pricing_control(compact: str) -> str:
    if _looks_like_price_floor_clause(compact):
        return "hard_price_floor"
    return ""


def _looks_like_price_floor_clause(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return "不得低于预算金额的" in compact and "无效投标" in compact


def _normalize_extracted_scope(text: str) -> str:
    compact = text.strip()
    for prefix in ["投标人须具备", "投标人须提供", "投标人应具备", "投标人应提供", "供应商须具备", "供应商应具备"]:
        if compact.startswith(prefix):
            compact = compact[len(prefix):]
            break
    return compact.strip("：:，,。.;； ")

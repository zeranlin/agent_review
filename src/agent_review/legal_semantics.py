from __future__ import annotations

import re

from .models import ClauseConstraint
from .ontology import (
    ClauseSemanticType,
    ConstraintType,
    LegalEffectType,
    LegalPrincipleTag,
    RestrictionAxis,
    SemanticZoneType,
)


REGION_SUFFIXES = ("省", "市", "区", "县", "自治区", "特别行政区")


def infer_legal_effect(
    *,
    text: str,
    zone_type: SemanticZoneType,
    clause_semantic_type: ClauseSemanticType,
    field_name: str = "",
) -> LegalEffectType:
    if field_name in {"附件引用"}:
        return LegalEffectType.reference_notice
    if field_name in {"投标文件格式", "中小企业声明函类型"}:
        return LegalEffectType.template_instruction
    if field_name in {"一般资格要求", "特定资格要求", "资格条件明细", "资格门槛明细"}:
        return LegalEffectType.qualification_gate
    if field_name in {"评分方法", "评分项明细", "信用评价要求", "行业相关性存疑评分项", "财务指标加分", "人员评分要求"}:
        return LegalEffectType.scoring_factor
    if field_name in {"付款节点", "验收标准", "违约责任", "履约保证金", "质保期", "考核条款", "满意度条款", "扣款条款", "解约条款"}:
        return LegalEffectType.contract_obligation
    if field_name in {"是否要求检测报告", "是否要求认证证书", "证书检测报告负担特征", "检测报告适用阶段", "证书材料适用阶段", "证明来源要求"}:
        return LegalEffectType.evidence_source_requirement
    if field_name in {"是否专门面向中小企业", "是否仍保留价格扣除条款", "是否为预留份额采购"}:
        return LegalEffectType.policy_statement

    if clause_semantic_type == ClauseSemanticType.administrative_clause:
        return LegalEffectType.unknown
    if clause_semantic_type in {
        ClauseSemanticType.qualification_review_clause,
        ClauseSemanticType.conformity_review_clause,
        ClauseSemanticType.preliminary_review_clause,
        ClauseSemanticType.invalid_bid_clause,
    }:
        return LegalEffectType.review_procedure
    if clause_semantic_type in {
        ClauseSemanticType.qualification_condition,
        ClauseSemanticType.qualification_material_requirement,
    }:
        return LegalEffectType.qualification_gate
    if clause_semantic_type in {ClauseSemanticType.scoring_rule, ClauseSemanticType.scoring_factor}:
        return LegalEffectType.scoring_factor
    if clause_semantic_type in {ClauseSemanticType.technical_requirement, ClauseSemanticType.sample_or_demo_requirement}:
        return LegalEffectType.technical_requirement
    if clause_semantic_type == ClauseSemanticType.business_requirement:
        return LegalEffectType.business_requirement
    if clause_semantic_type in {
        ClauseSemanticType.contract_obligation,
        ClauseSemanticType.payment_term,
        ClauseSemanticType.acceptance_term,
        ClauseSemanticType.breach_term,
        ClauseSemanticType.termination_term,
    }:
        return LegalEffectType.contract_obligation
    if clause_semantic_type in {ClauseSemanticType.policy_clause, ClauseSemanticType.conditional_policy}:
        return LegalEffectType.policy_statement
    if clause_semantic_type in {ClauseSemanticType.template_instruction, ClauseSemanticType.declaration_template}:
        return LegalEffectType.template_instruction
    if clause_semantic_type in {ClauseSemanticType.reference_clause, ClauseSemanticType.catalog_clause}:
        return LegalEffectType.reference_notice

    if zone_type == SemanticZoneType.qualification:
        return LegalEffectType.qualification_gate
    if zone_type == SemanticZoneType.scoring:
        return LegalEffectType.scoring_factor
    if zone_type == SemanticZoneType.technical:
        return LegalEffectType.technical_requirement
    if zone_type == SemanticZoneType.business:
        return LegalEffectType.business_requirement
    if zone_type == SemanticZoneType.contract:
        return LegalEffectType.contract_obligation
    if zone_type == SemanticZoneType.policy_explanation:
        return LegalEffectType.policy_statement
    return LegalEffectType.unknown


def infer_clause_constraint(text: str, legal_effect: LegalEffectType) -> ClauseConstraint:
    compact = re.sub(r"\s+", "", text)
    constraint_types: list[ConstraintType] = []
    restriction_axes: list[RestrictionAxis] = []
    qualifier_tokens: list[str] = []
    region_tokens = _extract_region_tokens(compact)
    industry_tokens = _extract_industry_tokens(compact)
    evidence_source = ""

    token_map: list[tuple[list[str], ConstraintType, RestrictionAxis | None]] = [
        (["科技型中小企业"], ConstraintType.entity_identity, RestrictionAxis.enterprise_size),
        (["高新技术企业", "高新企业"], ConstraintType.certification, RestrictionAxis.qualification_level),
        (["纳税信用", "信用A级", "信用AA"], ConstraintType.credit_rating, RestrictionAxis.credit_grade),
        (["成立满", "成立5年", "成立三年", "注册时间"], ConstraintType.establishment_age, RestrictionAxis.establishment_years),
        (["同类项目业绩", "业绩不少于", "类似项目业绩"], ConstraintType.performance_experience, RestrictionAxis.performance_count),
        (["检测报告", "检验报告", "认证证书", "资质证书", "证明扫描件", "合同扫描件"], ConstraintType.evidence_document, RestrictionAxis.stage_burden),
        (["检测中心", "检测机构", "实验室", "税务部门", "协会", "研究院"], ConstraintType.institution_source, RestrictionAxis.designated_institution),
        (["营业收入", "注册资本", "资产总额", "纳税额", "从业人员"], ConstraintType.enterprise_scale, RestrictionAxis.enterprise_size),
    ]
    for tokens, constraint_type, axis in token_map:
        if any(token in compact for token in tokens):
            constraint_types.append(constraint_type)
            if axis is not None:
                restriction_axes.append(axis)
            qualifier_tokens.extend([token for token in tokens if token in compact])

    if region_tokens:
        constraint_types.append(ConstraintType.geographic_scope)
        restriction_axes.append(RestrictionAxis.geographic_region)
    if industry_tokens:
        constraint_types.append(ConstraintType.industry_scope)
        restriction_axes.append(RestrictionAxis.industry_segment)

    if any(token in compact for token in ["出具", "提供", "提交"]) and any(
        token in compact for token in ["检测中心", "检测机构", "税务部门", "协会", "研究院", "实验室"]
    ):
        evidence_source = _extract_evidence_source(compact)

    return ClauseConstraint(
        subject="投标人" if any(token in compact for token in ["投标人", "供应商"]) else "",
        role="准入条件" if legal_effect == LegalEffectType.qualification_gate else (
            "评分因素" if legal_effect == LegalEffectType.scoring_factor else ""
        ),
        legal_effect=legal_effect,
        constraint_types=_dedupe_enum(constraint_types),
        restriction_axes=_dedupe_enum(restriction_axes),
        evidence_source=evidence_source,
        region_tokens=region_tokens,
        industry_tokens=industry_tokens,
        qualifier_tokens=_dedupe_strs(qualifier_tokens),
        exclusion_effect="排除/无效投标" if any(token in compact for token in ["无效投标", "不予通过", "资格审查不合格"]) else "",
    )


def infer_legal_principle_tags(
    text: str,
    legal_effect: LegalEffectType,
    constraint: ClauseConstraint,
) -> list[LegalPrincipleTag]:
    compact = re.sub(r"\s+", "", text)
    principles: list[LegalPrincipleTag] = []

    if legal_effect == LegalEffectType.qualification_gate:
        if constraint.constraint_types:
            principles.append(LegalPrincipleTag.qualification_necessity)
        if any(
            item in constraint.constraint_types
            for item in [
                ConstraintType.entity_identity,
                ConstraintType.credit_rating,
                ConstraintType.establishment_age,
                ConstraintType.geographic_scope,
                ConstraintType.industry_scope,
                ConstraintType.enterprise_scale,
            ]
        ):
            principles.append(LegalPrincipleTag.qualification_nondiscrimination)
        if ConstraintType.performance_experience in constraint.constraint_types and (
            constraint.region_tokens or constraint.industry_tokens
        ):
            principles.append(LegalPrincipleTag.qualification_nondiscrimination)

    if legal_effect == LegalEffectType.scoring_factor:
        principles.append(LegalPrincipleTag.scoring_relevance)
        if any(token in compact for token in ["业绩", "资质", "证书", "信用", "财务指标"]):
            principles.append(LegalPrincipleTag.qualification_scoring_boundary)

    if legal_effect == LegalEffectType.evidence_source_requirement or (
        ConstraintType.institution_source in constraint.constraint_types and any(token in compact for token in ["出具", "提供"])
    ):
        principles.append(LegalPrincipleTag.evidence_source_restriction)

    if any(token in compact for token in ["专门面向中小企业", "非专门面向中小企业", "科技型中小企业"]):
        principles.append(LegalPrincipleTag.internal_consistency)

    return _dedupe_enum(principles)


def _extract_region_tokens(text: str) -> list[str]:
    matches = re.findall(r"([\u4e00-\u9fa5]{2,12}(?:省|市|区|县|自治区|特别行政区))", text)
    return _dedupe_strs(
        token for token in matches
        if any(token.endswith(suffix) for suffix in REGION_SUFFIXES)
    )


def _extract_industry_tokens(text: str) -> list[str]:
    matches = re.findall(r"([\u4e00-\u9fa5A-Za-z]{2,20}行业)", text)
    return _dedupe_strs(matches)


def _extract_evidence_source(text: str) -> str:
    match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9（）()]{2,40}(?:检测中心|检测机构|实验室|税务部门|协会|研究院))", text)
    return match.group(1) if match else ""


def _dedupe_enum(items):
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _dedupe_strs(items) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result

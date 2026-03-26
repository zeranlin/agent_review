from __future__ import annotations

import re

from ..models import ClauseUnit, LegalFactCandidate
from ..ontology import ClauseSemanticType, EffectTag, LegalEffectType, RestrictionAxis, SemanticZoneType


def extract_legal_facts_from_units(clause_units: list[ClauseUnit], *, document_id: str) -> list[LegalFactCandidate]:
    facts: list[LegalFactCandidate] = []
    for unit in clause_units:
        if not unit.text.strip():
            continue
        if EffectTag.catalog in unit.effect_tags or EffectTag.public_copy_noise in unit.effect_tags:
            continue
        fact_type = _infer_fact_type(unit)
        if not fact_type:
            continue
        facts.append(
            LegalFactCandidate(
                fact_id=f"LF-{len(facts) + 1:04d}",
                document_id=document_id,
                source_unit_id=unit.unit_id,
                fact_type=fact_type,
                zone_type=unit.zone_type.value,
                clause_semantic_type=unit.clause_semantic_type.value,
                effect_tags=[item.value for item in unit.effect_tags],
                subject=unit.clause_constraint.subject,
                predicate=_infer_predicate(unit.text),
                object_text=unit.text.strip(),
                normalized_terms=_normalized_terms(unit),
                constraint_type=_infer_constraint_type(unit),
                constraint_value=_infer_constraint_value(unit),
                evidence_stage=_infer_evidence_stage(unit),
                counterparty=_infer_counterparty(unit),
                anchor=unit.anchor.to_dict(),
                table_context=dict(unit.table_context),
                supporting_context=_supporting_context(unit),
                confidence=round(unit.confidence, 3),
                needs_llm_disambiguation=_needs_llm_disambiguation(unit),
            )
        )
    return facts


def _infer_fact_type(unit: ClauseUnit) -> str:
    clause_type = unit.clause_semantic_type
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
    if unit.legal_effect_type == LegalEffectType.evidence_source_requirement:
        return "evidence_source_requirement"
    return ""


def _infer_predicate(text: str) -> str:
    for token in ["须具备", "应具备", "须提供", "应提供", "得分", "扣分", "支付", "验收", "解除"]:
        if token in text:
            return token
    return ""


def _normalized_terms(unit: ClauseUnit) -> list[str]:
    tokens = [
        *unit.clause_constraint.qualifier_tokens,
        *unit.clause_constraint.region_tokens,
        *unit.clause_constraint.industry_tokens,
    ]
    if unit.clause_constraint.evidence_source:
        tokens.append(unit.clause_constraint.evidence_source)
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
        value["evidence_source"] = unit.clause_constraint.evidence_source
    min_years = _extract_first_int(unit.text, r"成立满(\d+)年")
    if min_years is not None:
        value["min_years"] = min_years
    min_count = _extract_first_int(unit.text, r"(?:不少于|至少|满)(\d+)(?:个|项|份)")
    if min_count is not None:
        value["min_count"] = min_count
    score = _extract_first_int(unit.text, r"(\d+)\s*分")
    if score is not None and unit.zone_type == SemanticZoneType.scoring:
        value["score"] = score
    return value


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


def _normalize_extracted_scope(text: str) -> str:
    compact = text.strip()
    for prefix in ["投标人须具备", "投标人须提供", "投标人应具备", "投标人应提供", "供应商须具备", "供应商应具备"]:
        if compact.startswith(prefix):
            compact = compact[len(prefix):]
            break
    return compact.strip("：:，,。.;； ")

from __future__ import annotations

from ..models import ClauseUnit, DocumentNode, EffectTagResult, SemanticZone
from ..ontology import ClauseSemanticType, EffectTag, NodeType, SemanticZoneType


def build_clause_units(
    nodes: list[DocumentNode],
    semantic_zones: list[SemanticZone],
    effect_tag_results: list[EffectTagResult],
) -> list[ClauseUnit]:
    zone_index = {item.node_id: item for item in semantic_zones}
    effect_index = {item.node_id: item for item in effect_tag_results}
    units: list[ClauseUnit] = []

    for node in nodes:
        if node.node_id == "root":
            continue
        if node.node_type in {NodeType.catalog_entry, NodeType.table, NodeType.volume}:
            continue
        if not node.text.strip():
            continue

        zone = zone_index.get(node.node_id)
        effect = effect_index.get(node.node_id)
        zone_type = zone.zone_type if zone is not None else SemanticZoneType.mixed_or_uncertain
        effect_tags = effect.effect_tags if effect is not None else []
        clause_type = _infer_clause_semantic_type(node, zone_type, effect_tags)

        unit_text = node.text.strip()
        if node.node_type == NodeType.table_row and " | " in unit_text:
            title = unit_text.split(" | ", 1)[0].strip()
        else:
            title = node.title.strip() or unit_text[:60]

        units.append(
            ClauseUnit(
                unit_id=f"cu-{len(units) + 1:04d}",
                source_node_id=node.node_id,
                text=unit_text,
                path=node.path,
                anchor=node.anchor,
                zone_type=zone_type,
                clause_semantic_type=clause_type,
                effect_tags=effect_tags,
                table_context={
                    "node_type": node.node_type.value,
                    "title": title,
                    "metadata": node.metadata,
                },
                confidence=_unit_confidence(zone, effect),
            )
        )

    return units


def _infer_clause_semantic_type(
    node: DocumentNode,
    zone_type: SemanticZoneType,
    effect_tags: list[EffectTag],
) -> ClauseSemanticType:
    text = " ".join(part for part in [node.title, node.text, node.path] if part)
    if EffectTag.template in effect_tags:
        if "声明函" in text:
            return ClauseSemanticType.declaration_template
        return ClauseSemanticType.template_instruction
    if EffectTag.example in effect_tags:
        return ClauseSemanticType.example_clause
    if EffectTag.reference_only in effect_tags:
        return ClauseSemanticType.reference_clause
    if EffectTag.catalog in effect_tags:
        return ClauseSemanticType.catalog_clause

    if zone_type == SemanticZoneType.qualification:
        if any(token in text for token in ["证明", "资质证明", "原件备查", "材料", "证书"]):
            return ClauseSemanticType.qualification_material_requirement
        return ClauseSemanticType.qualification_condition

    if zone_type == SemanticZoneType.technical:
        if any(token in text for token in ["样品", "演示"]):
            return ClauseSemanticType.sample_or_demo_requirement
        return ClauseSemanticType.technical_requirement

    if zone_type == SemanticZoneType.business:
        return ClauseSemanticType.business_requirement

    if zone_type == SemanticZoneType.scoring:
        if any(token in text for token in ["得分", "扣分", "分值", "评分标准"]):
            return ClauseSemanticType.scoring_rule
        return ClauseSemanticType.scoring_factor

    if zone_type == SemanticZoneType.contract:
        if any(token in text for token in ["付款", "支付", "尾款"]):
            return ClauseSemanticType.payment_term
        if any(token in text for token in ["验收"]):
            return ClauseSemanticType.acceptance_term
        if any(token in text for token in ["违约", "违约金", "滞纳金"]):
            return ClauseSemanticType.breach_term
        if any(token in text for token in ["解除", "解约"]):
            return ClauseSemanticType.termination_term
        return ClauseSemanticType.contract_obligation

    if zone_type == SemanticZoneType.policy_explanation:
        return ClauseSemanticType.policy_clause

    return ClauseSemanticType.unknown_clause


def _unit_confidence(zone: SemanticZone | None, effect: EffectTagResult | None) -> float:
    zone_score = zone.confidence if zone is not None else 0.2
    effect_score = effect.confidence if effect is not None else 0.2
    return round((zone_score + effect_score) / 2, 4)

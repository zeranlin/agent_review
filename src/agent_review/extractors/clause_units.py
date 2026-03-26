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
        effect_tags = list(effect.effect_tags) if effect is not None else []
        unit_text = node.text.strip()

        if node.node_type == NodeType.table_row:
            zone_type, clause_type, effect_tags, confidence = _build_table_row_profile(
                node=node,
                zone_type=zone_type,
                effect_tags=effect_tags,
                zone=zone,
                effect=effect,
            )
            title = _row_label(unit_text) or node.title.strip() or unit_text[:60]
        else:
            clause_type = _infer_clause_semantic_type(node, zone_type, effect_tags)
            confidence = _unit_confidence(zone, effect, clause_type, effect_tags, node)
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
                    **_build_table_context(node, unit_text),
                },
                confidence=confidence,
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

    if zone_type == SemanticZoneType.catalog_or_navigation:
        return ClauseSemanticType.catalog_clause

    if zone_type == SemanticZoneType.public_copy_or_noise:
        return ClauseSemanticType.noise_clause

    return ClauseSemanticType.unknown_clause


def _build_table_row_profile(
    *,
    node: DocumentNode,
    zone_type: SemanticZoneType,
    effect_tags: list[EffectTag],
    zone: SemanticZone | None,
    effect: EffectTagResult | None,
) -> tuple[SemanticZoneType, ClauseSemanticType, list[EffectTag], float]:
    row_text = node.text.strip()
    row_cells = _split_table_row_text(row_text)
    is_header = bool(node.metadata.get("is_header")) or _looks_like_table_header(row_cells)

    if is_header:
        effective_effect_tags = [EffectTag.catalog]
        return (
            SemanticZoneType.catalog_or_navigation,
            ClauseSemanticType.catalog_clause,
            effective_effect_tags,
            _unit_confidence(
                zone,
                effect,
                ClauseSemanticType.catalog_clause,
                effective_effect_tags,
                node,
                override_cap=0.38,
            ),
        )

    clause_type = _infer_clause_semantic_type(node, zone_type, effect_tags)
    confidence = _unit_confidence(zone, effect, clause_type, effect_tags, node)
    return zone_type, clause_type, effect_tags, confidence


def _build_table_context(node: DocumentNode, unit_text: str) -> dict[str, object]:
    context: dict[str, object] = {
        "path": node.path,
        "heading_context": _heading_context_from_path(node.path),
        "metadata": node.metadata,
    }
    if node.node_type == NodeType.table_row:
        row_cells = _split_table_row_text(unit_text)
        context.update(
            {
                "row_role": "header" if bool(node.metadata.get("is_header")) or _looks_like_table_header(row_cells) else "data",
                "row_index": node.metadata.get("row_index"),
                "is_header": bool(node.metadata.get("is_header")),
                "table_kind": node.metadata.get("table_kind", ""),
                "row_label": _row_label(unit_text),
                "cells": row_cells,
                "cell_count": len(row_cells),
            }
        )
    elif node.node_type in {
        NodeType.chapter,
        NodeType.section,
        NodeType.subsection,
        NodeType.paragraph,
        NodeType.list_item,
        NodeType.appendix,
        NodeType.note,
    }:
        context["node_role"] = "heading" if node.node_type in {NodeType.chapter, NodeType.section, NodeType.subsection, NodeType.appendix} else "paragraph"
    return context


def _heading_context_from_path(path: str) -> str:
    if not path:
        return ""
    parts = [part.strip() for part in path.split(">") if part.strip()]
    if len(parts) <= 1:
        return path.strip()
    return " > ".join(parts[:-1])


def _split_table_row_text(text: str) -> list[str]:
    if "|" in text:
        return [part.strip() for part in text.split("|") if part.strip()]
    if "\t" in text:
        return [part.strip() for part in text.split("\t") if part.strip()]
    if "  " in text:
        return [part.strip() for part in text.split("  ") if part.strip()]
    return [text.strip()] if text.strip() else []


def _row_label(text: str) -> str:
    cells = _split_table_row_text(text)
    if not cells:
        return ""
    return cells[0]


def _looks_like_table_header(cells: list[str]) -> bool:
    if len(cells) < 2:
        return False
    header_keywords = {
        "评分项",
        "分值",
        "评分标准",
        "序号",
        "内容",
        "说明",
        "备注",
        "项目",
        "标准",
        "要求",
        "报价",
        "金额",
        "名称",
        "参数",
    }
    if any(cell in header_keywords for cell in cells):
        return True
    if len(cells) <= 4 and all(len(cell) <= 16 for cell in cells):
        label_like = sum(1 for cell in cells if _is_label_like(cell))
        return label_like >= 2 and not any(any(ch.isdigit() for ch in cell) for cell in cells)
    return False


def _is_label_like(text: str) -> bool:
    if not text:
        return False
    if any(token in text for token in ["评分", "项目", "内容", "标准", "要求", "说明", "备注", "名称", "序号", "分值"]):
        return True
    return len(text) <= 8


def _unit_confidence(
    zone: SemanticZone | None,
    effect: EffectTagResult | None,
    clause_type: ClauseSemanticType,
    effect_tags: list[EffectTag],
    node: DocumentNode,
    *,
    override_cap: float | None = None,
) -> float:
    zone_score = zone.confidence if zone is not None else 0.2
    effect_score = effect.confidence if effect is not None else 0.2
    raw_score = round((zone_score + effect_score) / 2, 4)
    cap = override_cap if override_cap is not None else _confidence_cap(clause_type, effect_tags, node)
    return round(min(raw_score, cap), 4)


def _confidence_cap(
    clause_type: ClauseSemanticType,
    effect_tags: list[EffectTag],
    node: DocumentNode,
) -> float:
    if clause_type in {ClauseSemanticType.catalog_clause, ClauseSemanticType.noise_clause}:
        return 0.38
    if clause_type in {ClauseSemanticType.reference_clause, ClauseSemanticType.example_clause}:
        return 0.5
    if clause_type in {ClauseSemanticType.template_instruction, ClauseSemanticType.declaration_template}:
        return 0.62
    if EffectTag.optional in effect_tags or EffectTag.reference_only in effect_tags:
        return 0.58
    if clause_type == ClauseSemanticType.unknown_clause:
        return 0.45
    if node.node_type == NodeType.table_row:
        return 0.86
    if clause_type in {
        ClauseSemanticType.scoring_rule,
        ClauseSemanticType.qualification_material_requirement,
        ClauseSemanticType.qualification_condition,
        ClauseSemanticType.technical_requirement,
        ClauseSemanticType.business_requirement,
        ClauseSemanticType.contract_obligation,
        ClauseSemanticType.payment_term,
        ClauseSemanticType.acceptance_term,
        ClauseSemanticType.breach_term,
        ClauseSemanticType.termination_term,
        ClauseSemanticType.policy_clause,
        ClauseSemanticType.sample_or_demo_requirement,
    }:
        return 0.92
    return 0.75

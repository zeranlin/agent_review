from __future__ import annotations

from ..models import DocumentNode, EffectTagResult, SemanticZone
from ..ontology import EffectTag, NodeType, SemanticZoneType


def tag_effects(
    nodes: list[DocumentNode],
    semantic_zones: list[SemanticZone],
) -> list[EffectTagResult]:
    zone_index = {item.node_id: item for item in semantic_zones}
    results: list[EffectTagResult] = []
    for node in nodes:
        zone = zone_index.get(node.node_id)
        tags, confidence, evidence = _classify_effect(node, zone)
        results.append(
            EffectTagResult(
                node_id=node.node_id,
                effect_tags=tags,
                confidence=confidence,
                evidence=evidence,
            )
        )
    return results


def _classify_effect(
    node: DocumentNode,
    zone: SemanticZone | None,
) -> tuple[list[EffectTag], float, list[str]]:
    haystack = " ".join(part for part in [node.title, node.text, node.path] if part)
    evidence: list[str] = []

    if node.node_id == "root":
        return [EffectTag.catalog], 1.0, ["synthetic_root"]
    if node.node_type == NodeType.catalog_entry:
        return [EffectTag.catalog], 1.0, ["node_type:catalog_entry"]
    if zone and zone.zone_type == SemanticZoneType.catalog_or_navigation:
        return [EffectTag.catalog], 0.98, ["zone:catalog_or_navigation"]
    if zone and zone.zone_type == SemanticZoneType.public_copy_or_noise:
        return [EffectTag.public_copy_noise], 0.95, ["zone:public_copy_or_noise"]

    tags: list[EffectTag] = []

    if any(token in haystack for token in ["格式", "声明函", "投标函", "法定代表人", "盖章", "签字", "附件："]):
        tags.append(EffectTag.template)
        evidence.append("template_keyword")

    if any(token in haystack for token in ["示例", "例如", "样例"]):
        tags.append(EffectTag.example)
        evidence.append("example_keyword")

    if any(token in haystack for token in ["可选", "选填", "按需提供"]):
        tags.append(EffectTag.optional)
        evidence.append("optional_keyword")

    if any(token in haystack for token in ["详见附件", "附表", "附件", "另册提供"]):
        tags.append(EffectTag.reference_only)
        evidence.append("reference_keyword")

    if zone and zone.zone_type == SemanticZoneType.template:
        if EffectTag.template not in tags:
            tags.append(EffectTag.template)
        evidence.append("zone:template")

    if zone and zone.zone_type == SemanticZoneType.appendix_reference:
        if EffectTag.reference_only not in tags:
            tags.append(EffectTag.reference_only)
        evidence.append("zone:appendix_reference")

    if zone and zone.zone_type == SemanticZoneType.policy_explanation:
        tags.append(EffectTag.policy_background)
        evidence.append("zone:policy_explanation")

    if not tags:
        tags.append(EffectTag.binding)
        evidence.append("default_binding")

    if EffectTag.template in tags and EffectTag.binding in tags:
        tags.remove(EffectTag.binding)

    if EffectTag.example in tags and EffectTag.binding in tags:
        tags.remove(EffectTag.binding)

    if EffectTag.reference_only in tags and EffectTag.binding in tags:
        tags.remove(EffectTag.binding)

    confidence = 0.92 if tags != [EffectTag.binding] else 0.75
    if len(tags) > 1:
        confidence = 0.85

    return list(dict.fromkeys(tags)), confidence, list(dict.fromkeys(evidence))

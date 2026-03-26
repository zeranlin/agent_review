from __future__ import annotations

from ..models import DocumentNode, EffectTagResult, SemanticZone
from ..ontology import EffectTag, NodeType, SemanticZoneType


PUBLIC_NOISE_MARKERS = ["页眉", "页脚", "深圳政府采购网", "信息公开", "下载地址", "复制文本"]
TEMPLATE_MARKERS = ["格式", "模板", "表样", "样表", "投标函", "声明函", "承诺函", "法定代表人"]
EXAMPLE_MARKERS = ["示例", "样例", "例如", "仅供参考"]
OPTIONAL_MARKERS = ["可选", "选填", "按需提供", "如有"]
REFERENCE_MARKERS = ["详见附件", "见附件", "附表", "另册提供", "附件1", "附件2", "附件一", "附件二", "见附表"]
POLICY_MARKERS = ["政策", "管理办法", "促进", "财政部", "中小企业", "节能产品", "环境标志", "采购政策"]
BINDING_MARKERS = [
    "应",
    "须",
    "必须",
    "不得",
    "投标人",
    "供应商",
    "资格",
    "资质",
    "评分",
    "得分",
    "扣分",
    "验收",
    "付款",
    "违约",
    "解除",
    "交货",
    "售后",
    "技术参数",
    "性能",
    "服务",
]
SUBSTANTIVE_ZONES = {
    SemanticZoneType.qualification,
    SemanticZoneType.technical,
    SemanticZoneType.business,
    SemanticZoneType.scoring,
    SemanticZoneType.contract,
}
WEAK_ZONES = {
    SemanticZoneType.template,
    SemanticZoneType.appendix_reference,
}


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
    zone_type = zone.zone_type if zone is not None else SemanticZoneType.mixed_or_uncertain
    evidence: list[str] = []

    if node.node_id == "root":
        return [EffectTag.catalog], 1.0, ["synthetic_root"]
    if node.node_type == NodeType.catalog_entry:
        return [EffectTag.catalog], 1.0, ["node_type:catalog_entry"]
    if zone_type == SemanticZoneType.catalog_or_navigation:
        return [EffectTag.catalog], 0.98, ["zone:catalog_or_navigation"]
    if _is_public_copy_noise(node, zone_type, haystack):
        return [EffectTag.public_copy_noise], 0.95, ["zone:public_copy_or_noise"]
    weak_tags, weak_evidence = _collect_weak_effects(node, zone_type, haystack)
    if weak_tags and (zone_type in WEAK_ZONES or node.node_type == NodeType.appendix):
        return _finalize_effect(weak_tags, 0.94 if zone_type in WEAK_ZONES else 0.92, weak_evidence)

    if zone_type == SemanticZoneType.policy_explanation or _contains_any(haystack, POLICY_MARKERS):
        tags = [EffectTag.policy_background]
        evidence.append("zone:policy_explanation" if zone_type == SemanticZoneType.policy_explanation else "policy_keyword")
        if not _has_binding_signals(node, zone_type, haystack) and _contains_any(haystack, REFERENCE_MARKERS):
            tags.append(EffectTag.reference_only)
            evidence.append("policy_reference_keyword")
        return _finalize_effect(tags, 0.88, evidence)

    if _has_binding_signals(node, zone_type, haystack):
        tags = [EffectTag.binding]
        if node.node_type == NodeType.table:
            evidence.append("table_binding_signal")
        elif node.node_type == NodeType.table_row:
            evidence.append("table_row_binding_signal")
        elif zone_type in SUBSTANTIVE_ZONES:
            evidence.append(f"zone:{zone_type.value}")
        else:
            evidence.append("binding_keyword")
        return _finalize_effect(tags, 0.93 if zone_type in SUBSTANTIVE_ZONES or node.node_type in {NodeType.table, NodeType.table_row} else 0.8, evidence)

    if weak_tags:
        return _finalize_effect(weak_tags, 0.88, weak_evidence)

    return [EffectTag.binding], 0.75, ["default_binding"]


def _collect_weak_effects(
    node: DocumentNode,
    zone_type: SemanticZoneType,
    haystack: str,
) -> tuple[list[EffectTag], list[str]]:
    tags: list[EffectTag] = []
    evidence: list[str] = []

    template_hit = _contains_any(haystack, TEMPLATE_MARKERS) or zone_type == SemanticZoneType.template
    example_hit = _contains_any(haystack, EXAMPLE_MARKERS)
    optional_hit = _contains_any(haystack, OPTIONAL_MARKERS)
    reference_hit = _contains_any(haystack, REFERENCE_MARKERS) or zone_type == SemanticZoneType.appendix_reference

    if node.node_type == NodeType.appendix:
        evidence.append("node_type:appendix")
        if template_hit:
            tags.append(EffectTag.template)
            evidence.append("appendix_template_keyword")
        if reference_hit:
            tags.append(EffectTag.reference_only)
            evidence.append("appendix_reference_keyword")
        if example_hit:
            tags.append(EffectTag.example)
            evidence.append("appendix_example_keyword")
        if optional_hit:
            tags.append(EffectTag.optional)
            evidence.append("appendix_optional_keyword")
        return list(dict.fromkeys(tags)), list(dict.fromkeys(evidence))

    if template_hit:
        tags.append(EffectTag.template)
        evidence.append("template_keyword")
    if example_hit:
        tags.append(EffectTag.example)
        evidence.append("example_keyword")
    if optional_hit:
        tags.append(EffectTag.optional)
        evidence.append("optional_keyword")
    if reference_hit:
        tags.append(EffectTag.reference_only)
        evidence.append("reference_keyword")

    if zone_type == SemanticZoneType.template:
        if EffectTag.template not in tags:
            tags.append(EffectTag.template)
        evidence.append("zone:template")
    if zone_type == SemanticZoneType.appendix_reference:
        if EffectTag.reference_only not in tags:
            tags.append(EffectTag.reference_only)
        evidence.append("zone:appendix_reference")

    return list(dict.fromkeys(tags)), list(dict.fromkeys(evidence))


def _has_binding_signals(node: DocumentNode, zone_type: SemanticZoneType, haystack: str) -> bool:
    if node.node_type == NodeType.table_row and _contains_any(haystack, ["评分项", "分值", "评分标准", "得分", "扣分"]):
        return True
    if node.node_type == NodeType.table and _contains_any(haystack, ["评分项", "分值", "评分标准", "得分", "检测报告", "资质", "资格"]):
        return True
    if zone_type in SUBSTANTIVE_ZONES and _contains_any(haystack, BINDING_MARKERS):
        return True
    if zone_type == SemanticZoneType.qualification and _contains_any(haystack, ["资格要求", "投标人", "供应商", "资质", "证书", "证明"]):
        return True
    if zone_type == SemanticZoneType.scoring and _contains_any(haystack, ["评分", "分值", "得分", "扣分", "评分项"]):
        return True
    if zone_type == SemanticZoneType.contract and _contains_any(haystack, ["付款", "验收", "违约", "解除", "解约", "责任"]):
        return True
    if zone_type == SemanticZoneType.business and _contains_any(haystack, ["交货", "售后", "服务", "实施", "培训"]):
        return True
    if zone_type == SemanticZoneType.technical and _contains_any(haystack, ["技术", "参数", "性能", "样品", "检测"]):
        return True
    return False


def _is_public_copy_noise(node: DocumentNode, zone_type: SemanticZoneType, haystack: str) -> bool:
    if zone_type == SemanticZoneType.public_copy_or_noise:
        return True
    if _contains_any(haystack, PUBLIC_NOISE_MARKERS):
        return True
    if node.node_type == NodeType.note and _contains_any(haystack, ["转载", "复制", "下载", "公开"]):
        return True
    return False


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _finalize_effect(tags: list[EffectTag], confidence: float, evidence: list[str]) -> tuple[list[EffectTag], float, list[str]]:
    deduped_tags = list(dict.fromkeys(tags))
    deduped_evidence = list(dict.fromkeys(evidence))
    if len(deduped_tags) > 1:
        confidence = max(confidence, 0.86)
    return deduped_tags, confidence, deduped_evidence

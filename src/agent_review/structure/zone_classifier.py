from __future__ import annotations

from ..models import DocumentNode, SemanticZone
from ..ontology import NodeType, SemanticZoneType


ZONE_RULES: dict[SemanticZoneType, list[str]] = {
    SemanticZoneType.qualification: ["资格要求", "资格证明", "资质要求", "业绩要求", "投标人资格"],
    SemanticZoneType.technical: ["技术要求", "技术参数", "货物清单", "样品要求", "检测报告", "参数"],
    SemanticZoneType.business: ["商务要求", "交货", "售后", "服务要求", "实施方案", "培训"],
    SemanticZoneType.scoring: ["评分标准", "评标信息", "综合评分", "评分项", "分值", "得分"],
    SemanticZoneType.contract: ["合同条款", "付款方式", "验收", "违约责任", "解除合同", "争议解决"],
    SemanticZoneType.template: ["投标文件格式", "附件", "声明函", "报价表", "承诺函", "法定代表人"],
    SemanticZoneType.policy_explanation: ["中小企业", "节能产品", "环境标志", "政策", "管理办法"],
    SemanticZoneType.appendix_reference: ["详见附件", "附表", "附件", "另册提供"],
}


def classify_semantic_zones(nodes: list[DocumentNode]) -> list[SemanticZone]:
    results: list[SemanticZone] = []
    for node in nodes:
        zone_type, confidence, basis = _classify_node(node)
        results.append(
            SemanticZone(
                node_id=node.node_id,
                zone_type=zone_type,
                confidence=confidence,
                classification_basis=basis,
            )
        )
    return results


def _classify_node(node: DocumentNode) -> tuple[SemanticZoneType, float, list[str]]:
    if node.node_id == "root":
        return SemanticZoneType.catalog_or_navigation, 1.0, ["synthetic_root"]
    if node.node_type == NodeType.catalog_entry:
        return SemanticZoneType.catalog_or_navigation, 1.0, ["node_type:catalog_entry"]

    haystack = " ".join(
        part for part in [node.title, node.text, node.path] if part
    )
    scores: dict[SemanticZoneType, float] = {
        zone: 0.0 for zone in SemanticZoneType if zone != SemanticZoneType.mixed_or_uncertain
    }
    basis: list[str] = []

    if any(token in haystack for token in ["页眉", "页脚", "深圳政府采购网", "信息公开"]):
        return SemanticZoneType.public_copy_or_noise, 0.95, ["noise_keyword"]

    if any(token in haystack for token in ["目录"]) and node.node_type == NodeType.catalog_entry:
        return SemanticZoneType.catalog_or_navigation, 1.0, ["catalog_keyword"]

    for zone, keywords in ZONE_RULES.items():
        for keyword in keywords:
            if keyword in node.title:
                scores[zone] += 0.65
            if keyword in node.path:
                scores[zone] += 0.55
            elif keyword in node.text:
                scores[zone] += 0.25

    if node.node_type == NodeType.table_row and any(token in node.text for token in ["评分项", "分值", "得分", "评分标准"]):
        scores[SemanticZoneType.scoring] += 0.8
        basis.append("table_row_scoring_header")

    if any(token in node.path for token in ["投标文件格式", "附件"]):
        scores[SemanticZoneType.template] += 0.8
        basis.append("path_template")

    if any(token in node.path for token in ["合同", "通用条款", "专用条款"]) and any(
        token in haystack for token in ["付款", "验收", "违约", "解除"]
    ):
        scores[SemanticZoneType.contract] += 0.75
        basis.append("path_contract")

    if any(token in haystack for token in ["详见附件", "附表", "附件"]) and len(haystack) < 80:
        scores[SemanticZoneType.appendix_reference] += 0.8
        basis.append("appendix_reference")

    best_zone, best_score = max(scores.items(), key=lambda item: item[1], default=(SemanticZoneType.mixed_or_uncertain, 0.0))
    runner_up = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0.0
    if best_score <= 0.0:
        return SemanticZoneType.mixed_or_uncertain, 0.2, ["no_rule_match"]
    if best_score - runner_up < 0.2:
        return SemanticZoneType.mixed_or_uncertain, min(0.55, best_score), ["rule_conflict"]

    basis.extend(_matched_basis(best_zone, node))
    return best_zone, min(0.99, 0.35 + best_score / 2), list(dict.fromkeys(basis))


def _matched_basis(zone: SemanticZoneType, node: DocumentNode) -> list[str]:
    matched: list[str] = []
    for keyword in ZONE_RULES.get(zone, []):
        if keyword in node.title:
            matched.append(f"title:{keyword}")
        elif keyword in node.path:
            matched.append(f"path:{keyword}")
        elif keyword in node.text:
            matched.append(f"text:{keyword}")
    return matched

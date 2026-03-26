from __future__ import annotations

import re

from ..models import DocumentNode, SemanticZone
from ..ontology import NodeType, SemanticZoneType


ZONE_RULES: dict[SemanticZoneType, list[str]] = {
    SemanticZoneType.administrative_info: ["关键信息", "项目属性", "项目编号", "项目名称", "预算金额", "最高限价"],
    SemanticZoneType.qualification: ["资格要求", "资格审查", "资格条件", "资格证明", "资质要求", "业绩要求", "投标人资格", "特定资格", "一般资格", "准入条件"],
    SemanticZoneType.technical: ["技术要求", "技术规范", "技术参数", "技术指标", "货物清单", "样品要求", "检测报告", "参数", "性能指标"],
    SemanticZoneType.business: ["商务要求", "商务部分", "交货", "交付", "售后", "服务要求", "实施方案", "培训", "响应", "供货"],
    SemanticZoneType.scoring: ["评分标准", "评标信息", "综合评分", "评分办法", "评标办法", "评分项", "分值", "得分", "评审因素", "评分规则", "量化"],
    SemanticZoneType.contract: ["合同条款", "合同专用条款", "合同通用条款", "专用条款", "通用条款", "付款方式", "付款", "验收", "违约责任", "解除合同", "争议解决", "质保", "保修"],
    SemanticZoneType.template: ["投标文件格式", "（格式）", "声明函", "报价表", "承诺函", "法定代表人", "模板", "范本", "盖章", "签字"],
    SemanticZoneType.policy_explanation: ["政府采购", "节能产品", "环境标志", "政策", "管理办法", "扶持", "采购促进"],
    SemanticZoneType.appendix_reference: ["详见附件", "见附件", "另册提供", "附表", "另附", "参见附件", "附件1", "附件一", "附件二"],
}

LOCATION_WEIGHTS = {
    "title": 0.95,
    "path": 0.75,
    "text": 0.35,
}

SHORT_REFERENCE_TOKENS = ["详见附件", "见附件", "参见附件", "另册提供", "另附"]
POLICY_CONTEXT_TOKENS = ["依据", "根据", "按照", "参照", "执行", "适用", "通知", "规定", "办法", "管理办法"]
TEMPLATE_STRONG_TOKENS = ["投标文件格式", "（格式）", "声明函", "报价表", "承诺函", "法定代表人", "模板", "范本", "盖章", "签字"]
APPENDIX_STRONG_TOKENS = ["详见附件", "见附件", "参见附件", "另册提供", "另附", "附表", "附件1", "附件一", "附件二"]
SCORING_STRONG_TOKENS = ["评分项", "分值", "评分标准", "评分办法", "评标办法", "得分", "评分规则", "评审因素", "量化"]
CONTRACT_STRONG_TOKENS = ["付款", "验收", "违约", "解除", "争议", "质保", "保修", "专用条款", "通用条款"]
QUALIFICATION_STRONG_TOKENS = ["资格", "资质", "准入", "资格条件", "资格要求", "资格证明"]
TECHNICAL_STRONG_TOKENS = ["技术", "参数", "指标", "规范", "样品", "检测报告"]
BUSINESS_STRONG_TOKENS = ["商务", "交货", "交付", "售后", "服务", "培训", "实施"]


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
    compact_text = re.sub(r"\s+", "", haystack)
    scores: dict[SemanticZoneType, float] = {
        zone: 0.0 for zone in SemanticZoneType if zone != SemanticZoneType.mixed_or_uncertain
    }
    basis: list[str] = []

    if any(token in haystack for token in ["页眉", "页脚", "深圳政府采购网", "信息公开"]):
        return SemanticZoneType.public_copy_or_noise, 0.95, ["noise_keyword"]

    if any(token in haystack for token in ["目录"]) and node.node_type == NodeType.catalog_entry:
        return SemanticZoneType.catalog_or_navigation, 1.0, ["catalog_keyword"]

    _score_keyword_family(scores, basis, node, SemanticZoneType.administrative_info, ZONE_RULES[SemanticZoneType.administrative_info])
    _score_keyword_family(scores, basis, node, SemanticZoneType.qualification, ZONE_RULES[SemanticZoneType.qualification])
    _score_keyword_family(scores, basis, node, SemanticZoneType.technical, ZONE_RULES[SemanticZoneType.technical])
    _score_keyword_family(scores, basis, node, SemanticZoneType.business, ZONE_RULES[SemanticZoneType.business])
    _score_keyword_family(scores, basis, node, SemanticZoneType.scoring, ZONE_RULES[SemanticZoneType.scoring])
    _score_keyword_family(scores, basis, node, SemanticZoneType.contract, ZONE_RULES[SemanticZoneType.contract])
    _score_keyword_family(scores, basis, node, SemanticZoneType.template, ZONE_RULES[SemanticZoneType.template])
    _score_keyword_family(scores, basis, node, SemanticZoneType.appendix_reference, ZONE_RULES[SemanticZoneType.appendix_reference])

    if node.node_type == NodeType.appendix:
        scores[SemanticZoneType.appendix_reference] += 0.35
        basis.append("node_type:appendix")

    if node.node_type == NodeType.table_row and any(token in haystack for token in SCORING_STRONG_TOKENS):
        scores[SemanticZoneType.scoring] += 0.8
        basis.append("table_row_scoring_header")
    if node.node_type == NodeType.table_row and any(token in haystack for token in QUALIFICATION_STRONG_TOKENS):
        scores[SemanticZoneType.qualification] += 0.35
        basis.append("table_row_qualification_header")
    if node.node_type == NodeType.table_row and any(token in haystack for token in TECHNICAL_STRONG_TOKENS):
        scores[SemanticZoneType.technical] += 0.3
        basis.append("table_row_technical_context")

    if node.node_type == NodeType.table_row and any(token in node.text for token in ["评分项", "分值", "得分", "评分标准"]):
        scores[SemanticZoneType.scoring] += 0.8
        basis.append("table_row_scoring_header")

    if node.node_type == NodeType.table:
        table_kind = str(node.metadata.get("table_kind", "")).strip()
        if table_kind == "scoring":
            scores[SemanticZoneType.scoring] += 1.0
            basis.append("table_kind:scoring")
        elif table_kind == "template":
            scores[SemanticZoneType.template] += 0.9
            basis.append("table_kind:template")
        elif table_kind == "contract":
            scores[SemanticZoneType.contract] += 0.85
            basis.append("table_kind:contract")
        elif table_kind == "appendix_reference":
            scores[SemanticZoneType.appendix_reference] += 0.95
            basis.append("table_kind:appendix_reference")

        if any(token in haystack for token in SCORING_STRONG_TOKENS + ["综合评分"]):
            scores[SemanticZoneType.scoring] += 0.6
            basis.append("table_keyword_scoring")
        if any(token in haystack for token in TEMPLATE_STRONG_TOKENS):
            scores[SemanticZoneType.template] += 0.6
            basis.append("table_keyword_template")
        if any(token in haystack for token in APPENDIX_STRONG_TOKENS):
            scores[SemanticZoneType.appendix_reference] += 0.7
            basis.append("table_keyword_appendix")

    if any(token in node.path for token in ["投标文件格式", "格式", "模板", "范本"]):
        scores[SemanticZoneType.template] += 0.35
        basis.append("path_template")
    if any(token in node.path for token in ["附件", "附表", "另册"]):
        scores[SemanticZoneType.appendix_reference] += 0.25
        basis.append("path_appendix")

    if any(token in node.path for token in ["合同", "通用条款", "专用条款"]) and any(
        token in haystack for token in CONTRACT_STRONG_TOKENS
    ):
        scores[SemanticZoneType.contract] += 0.75
        basis.append("path_contract")

    if any(token in haystack for token in APPENDIX_STRONG_TOKENS) and len(compact_text) < 80:
        scores[SemanticZoneType.appendix_reference] += 0.9
        basis.append("short_appendix_reference")

    if any(token in haystack for token in POLICY_CONTEXT_TOKENS) and any(
        token in haystack for token in ["中小企业", "节能产品", "环境标志", "政府采购", "采购促进"]
    ):
        scores[SemanticZoneType.policy_explanation] += 0.95
        basis.append("policy_context")
    elif any(token in haystack for token in ["政府采购", "管理办法", "扶持", "政策", "节能产品", "环境标志"]):
        scores[SemanticZoneType.policy_explanation] += 0.5
        basis.append("policy_signal")

    if any(token in haystack for token in TEMPLATE_STRONG_TOKENS) and not any(
        token in haystack for token in APPENDIX_STRONG_TOKENS
    ):
        scores[SemanticZoneType.template] += 0.2
        basis.append("template_signal")

    best_zone, best_score = max(scores.items(), key=lambda item: item[1], default=(SemanticZoneType.mixed_or_uncertain, 0.0))
    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    runner_up_zone, runner_up_score = sorted_scores[1] if len(sorted_scores) > 1 else (SemanticZoneType.mixed_or_uncertain, 0.0)
    if best_score <= 0.0:
        return SemanticZoneType.mixed_or_uncertain, 0.2, ["no_rule_match"]
    if _is_ambiguous_zone(node, haystack, best_zone, best_score, runner_up_zone, runner_up_score):
        return SemanticZoneType.mixed_or_uncertain, min(0.55, best_score), ["rule_conflict"]

    basis.extend(_matched_basis(best_zone, node))
    return best_zone, min(0.99, 0.35 + best_score / 2), list(dict.fromkeys(basis))


def _score_keyword_family(
    scores: dict[SemanticZoneType, float],
    basis: list[str],
    node: DocumentNode,
    zone: SemanticZoneType,
    keywords: list[str],
) -> None:
    for keyword in keywords:
        if keyword in node.title:
            scores[zone] += LOCATION_WEIGHTS["title"]
            basis.append(f"title:{keyword}")
        if keyword in node.path:
            scores[zone] += LOCATION_WEIGHTS["path"]
            basis.append(f"path:{keyword}")
        elif keyword in node.text:
            scores[zone] += LOCATION_WEIGHTS["text"]
            basis.append(f"text:{keyword}")


def _is_ambiguous_zone(
    node: DocumentNode,
    haystack: str,
    best_zone: SemanticZoneType,
    best_score: float,
    runner_up_zone: SemanticZoneType,
    runner_up_score: float,
) -> bool:
    if best_score - runner_up_score < 0.18:
        return True
    if {best_zone, runner_up_zone} <= {SemanticZoneType.template, SemanticZoneType.appendix_reference}:
        if any(token in haystack for token in TEMPLATE_STRONG_TOKENS) and any(
            token in haystack for token in APPENDIX_STRONG_TOKENS
        ):
            return runner_up_score >= 0.8 and (node.node_type == NodeType.appendix or len(re.sub(r"\s+", "", haystack)) < 90)
    return False


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

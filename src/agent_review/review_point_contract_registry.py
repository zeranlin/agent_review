from __future__ import annotations

from .models import ReviewPointContract


REVIEW_POINT_CONTRACTS: list[ReviewPointContract] = [
    ReviewPointContract(
        point_id="RP-QUAL-003",
        title="资格条件可能缺乏履约必要性或带有歧视性门槛",
        description="审查与履约能力无直接关联、可能变相限制竞争的资格门槛。",
        risk_family="qualification",
        legal_theme="资格必要性与公平竞争",
        applicable_procurement_kinds=["goods", "service", "mixed", "unknown"],
        target_zone_types=["qualification", "scoring"],
        primary_review_types=["资格", "评分"],
        required_fact_types=["qualification_requirement", "certificate_requirement"],
        supporting_fact_types=["qualification_material_requirement", "cross_clause_conflict_signal"],
        activation_rule_ids=[
            "RULE-QUAL-CERT-001",
            "RULE-QUAL-TAX-001",
            "RULE-QUAL-AGE-001",
        ],
        required_fields=["特定资格要求", "资格条件明细", "资格门槛明细"],
        enhancement_fields=["证明来源要求", "证书材料适用阶段"],
        evidence_policy="single_direct_quote_sufficient",
        quality_gate_policy="template_or_reference_only_filtered",
        manual_boundary_policy="authority_driven",
        authority_binding_ids=["AUTH-RP-QUAL-003-001"],
        severity_policy="high",
        report_group="资格与公平竞争",
        report_priority=10,
    ),
    ReviewPointContract(
        point_id="RP-QUAL-004",
        title="资格业绩要求可能存在地域限定、行业口径过窄或与评分重复",
        description="审查资格业绩是否收窄地域、行业范围，或与评分项重复设门槛。",
        risk_family="qualification",
        legal_theme="资格业绩必要性与公平竞争",
        applicable_procurement_kinds=["goods", "service", "mixed", "unknown"],
        target_zone_types=["qualification", "scoring"],
        primary_review_types=["资格", "评分"],
        required_fact_types=["performance_requirement"],
        supporting_fact_types=["scoring_factor", "cross_clause_conflict_signal"],
        activation_rule_ids=[
            "RULE-QUAL-PERF-REGION-001",
            "RULE-QUAL-PERF-DUP-001",
        ],
        required_fields=["资格条件明细", "资格门槛明细", "评分项明细"],
        enhancement_fields=["采购包划分说明", "行业相关性存疑评分项"],
        evidence_policy="cross_clause_evidence_required",
        quality_gate_policy="weak_zone_only_manual",
        manual_boundary_policy="authority_driven",
        authority_binding_ids=["AUTH-RP-QUAL-004-001"],
        severity_policy="high",
        report_group="资格与公平竞争",
        report_priority=11,
    ),
    ReviewPointContract(
        point_id="RP-SCORE-005",
        title="行业无关证书或财务指标被纳入评分",
        description="审查评分项是否引入与采购需求和履约质量无直接关联的证书或财务指标。",
        risk_family="scoring",
        legal_theme="评分相关性",
        applicable_procurement_kinds=["goods", "service", "mixed", "unknown"],
        target_zone_types=["scoring", "qualification", "technical", "business"],
        primary_review_types=["评分"],
        required_fact_types=["scoring_factor"],
        supporting_fact_types=["certificate_requirement", "evidence_source_requirement"],
        activation_rule_ids=[
            "RULE-SCORE-CERT-001",
            "RULE-SCORE-FIN-001",
        ],
        required_fields=["评分方法", "评分项明细", "行业相关性存疑评分项"],
        enhancement_fields=["证书材料适用阶段", "检测报告适用阶段"],
        evidence_policy="table_and_text_alignment_required",
        quality_gate_policy="scoring_table_preferred",
        manual_boundary_policy="authority_driven",
        authority_binding_ids=["AUTH-RP-SCORE-005-001"],
        severity_policy="high",
        report_group="评分不规范风险",
        report_priority=20,
    ),
    ReviewPointContract(
        point_id="RP-EVID-001",
        title="证明材料来源可能被限定为特定机构或特定出具口径",
        description="审查检测报告、证明材料是否被限定为特定检测中心、机构或唯一出具来源。",
        risk_family="qualification",
        legal_theme="证明材料来源限制与公平竞争",
        applicable_procurement_kinds=["goods", "service", "mixed", "unknown"],
        target_zone_types=["qualification", "technical"],
        primary_review_types=["资格", "技术"],
        required_fact_types=["evidence_source_requirement"],
        supporting_fact_types=["qualification_material_requirement", "technical_parameter"],
        activation_rule_ids=["RULE-EVID-SOURCE-001"],
        required_fields=["证明来源要求", "资格条件明细"],
        enhancement_fields=["是否要求检测报告", "证书材料适用阶段"],
        evidence_policy="single_direct_quote_sufficient",
        quality_gate_policy="named_institution_quote_preferred",
        manual_boundary_policy="authority_driven",
        authority_binding_ids=["AUTH-RP-EVID-001-001"],
        severity_policy="high",
        report_group="证明材料与检测要求风险",
        report_priority=21,
    ),
    ReviewPointContract(
        point_id="RP-CONTRACT-009",
        title="验收标准存在优胜原则或单方弹性判断",
        description="审查验收标准是否依赖采购人单方解释、优胜原则或弹性判断。",
        risk_family="contract",
        legal_theme="合同公平性与验收明确性",
        applicable_procurement_kinds=["goods", "service", "mixed", "unknown"],
        target_zone_types=["contract"],
        primary_review_types=["合同"],
        required_fact_types=["acceptance_term"],
        supporting_fact_types=["payment_term", "breach_term"],
        activation_rule_ids=["RULE-CONTRACT-ACCEPT-001"],
        required_fields=["验收标准"],
        enhancement_fields=["付款节点", "违约责任"],
        evidence_policy="single_direct_quote_sufficient",
        quality_gate_policy="template_or_example_filtered",
        manual_boundary_policy="authority_driven",
        authority_binding_ids=["AUTH-RP-CONTRACT-009-001"],
        severity_policy="high",
        report_group="合同履约风险",
        report_priority=30,
    ),
]


CONTRACT_INDEX: dict[str, ReviewPointContract] = {
    item.point_id: item for item in REVIEW_POINT_CONTRACTS
}


def get_review_point_contract(point_id: str) -> ReviewPointContract | None:
    return CONTRACT_INDEX.get(point_id.strip())


def list_review_point_contracts() -> list[ReviewPointContract]:
    return list(REVIEW_POINT_CONTRACTS)

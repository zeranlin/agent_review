from __future__ import annotations

from enum import Enum


class SemanticZoneType(str, Enum):
    administrative_info = "administrative_info"
    qualification = "qualification"
    technical = "technical"
    business = "business"
    scoring = "scoring"
    contract = "contract"
    template = "template"
    policy_explanation = "policy_explanation"
    appendix_reference = "appendix_reference"
    catalog_or_navigation = "catalog_or_navigation"
    public_copy_or_noise = "public_copy_or_noise"
    mixed_or_uncertain = "mixed_or_uncertain"


class ClauseSemanticType(str, Enum):
    qualification_condition = "qualification_condition"
    qualification_material_requirement = "qualification_material_requirement"
    technical_requirement = "technical_requirement"
    business_requirement = "business_requirement"
    sample_or_demo_requirement = "sample_or_demo_requirement"
    scoring_rule = "scoring_rule"
    scoring_factor = "scoring_factor"
    contract_obligation = "contract_obligation"
    payment_term = "payment_term"
    acceptance_term = "acceptance_term"
    breach_term = "breach_term"
    termination_term = "termination_term"
    policy_clause = "policy_clause"
    template_instruction = "template_instruction"
    declaration_template = "declaration_template"
    example_clause = "example_clause"
    reference_clause = "reference_clause"
    catalog_clause = "catalog_clause"
    noise_clause = "noise_clause"
    unknown_clause = "unknown_clause"


class EffectTag(str, Enum):
    binding = "binding"
    template = "template"
    example = "example"
    optional = "optional"
    reference_only = "reference_only"
    policy_background = "policy_background"
    catalog = "catalog"
    public_copy_noise = "public_copy_noise"
    uncertain_effect = "uncertain_effect"


class EvidenceRole(str, Enum):
    direct_evidence = "direct_evidence"
    supporting_evidence = "supporting_evidence"
    conflicting_evidence = "conflicting_evidence"
    rebuttal_evidence = "rebuttal_evidence"
    missing_evidence_signal = "missing_evidence_signal"


class NodeType(str, Enum):
    volume = "volume"
    chapter = "chapter"
    section = "section"
    subsection = "subsection"
    paragraph = "paragraph"
    list_item = "list_item"
    table = "table"
    table_row = "table_row"
    table_cell = "table_cell"
    note = "note"
    appendix = "appendix"
    catalog_entry = "catalog_entry"


ONTOLOGY_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "semantic_zones": {
        SemanticZoneType.qualification.value: "投标人资格、资质、业绩及准入条件。",
        SemanticZoneType.technical.value: "技术参数、功能配置、样品和检测要求。",
        SemanticZoneType.business.value: "交付、实施、售后和服务响应要求。",
        SemanticZoneType.scoring.value: "评分项、分值、评分规则和量化标准。",
        SemanticZoneType.contract.value: "付款、验收、违约、解除和争议解决条款。",
        SemanticZoneType.template.value: "投标文件格式、声明函样式和模板化文本。",
    },
    "effect_tags": {
        EffectTag.binding.value: "正式约束性内容，可作为主证据候选。",
        EffectTag.template.value: "模板文本，不默认视为正式约束。",
        EffectTag.example.value: "示例文本，不默认视为正式约束。",
        EffectTag.optional.value: "可选项，需要结合上下文判断是否启用。",
        EffectTag.reference_only.value: "引用性文本，本身不构成完整约束。",
    },
}

from __future__ import annotations

from enum import Enum


class SemanticZoneType(str, Enum):
    administrative_info = "administrative_info"
    qualification = "qualification"
    conformity_review = "conformity_review"
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


ZONE_ONTOLOGY_VERSION = "v1"


ZONE_PRIMARY_REVIEW_TYPES: dict[SemanticZoneType, str] = {
    SemanticZoneType.administrative_info: "基础信息",
    SemanticZoneType.qualification: "资格",
    SemanticZoneType.conformity_review: "符合性审查",
    SemanticZoneType.technical: "技术",
    SemanticZoneType.business: "商务",
    SemanticZoneType.scoring: "评分",
    SemanticZoneType.contract: "合同",
    SemanticZoneType.template: "模板",
    SemanticZoneType.policy_explanation: "政策说明",
    SemanticZoneType.appendix_reference: "附件",
    SemanticZoneType.catalog_or_navigation: "导航",
    SemanticZoneType.public_copy_or_noise: "无关内容",
    SemanticZoneType.mixed_or_uncertain: "未确定",
}


ZONE_EVIDENCE_POLICY: dict[SemanticZoneType, str] = {
    SemanticZoneType.administrative_info: "可作为头信息与基础事实证据。",
    SemanticZoneType.qualification: "可作为资格审查直接证据。",
    SemanticZoneType.conformity_review: "可作为符合性审查、初审和无效投标程序条款证据。",
    SemanticZoneType.technical: "可作为技术要求直接证据。",
    SemanticZoneType.business: "可作为商务履约要求直接证据。",
    SemanticZoneType.scoring: "可作为评分规则直接证据。",
    SemanticZoneType.contract: "可作为履约及法律责任条款证据。",
    SemanticZoneType.template: "默认不作为正式约束证据，需结合效力标签二次判断。",
    SemanticZoneType.policy_explanation: "通常作为背景说明，不直接形成风险结论。",
    SemanticZoneType.appendix_reference: "仅提示证据位置，本身不构成完整约束。",
    SemanticZoneType.catalog_or_navigation: "不作为审查结论证据，只用于导航定位。",
    SemanticZoneType.public_copy_or_noise: "不作为证据。",
    SemanticZoneType.mixed_or_uncertain: "需进一步消解后再决定是否可用作证据。",
}


class ClauseSemanticType(str, Enum):
    administrative_clause = "administrative_clause"
    qualification_review_clause = "qualification_review_clause"
    conformity_review_clause = "conformity_review_clause"
    preliminary_review_clause = "preliminary_review_clause"
    invalid_bid_clause = "invalid_bid_clause"
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
    conditional_policy = "conditional_policy"
    template_instruction = "template_instruction"
    declaration_template = "declaration_template"
    example_clause = "example_clause"
    reference_clause = "reference_clause"
    catalog_clause = "catalog_clause"
    noise_clause = "noise_clause"
    unknown_clause = "unknown_clause"


class LegalEffectType(str, Enum):
    review_procedure = "review_procedure"
    qualification_gate = "qualification_gate"
    scoring_factor = "scoring_factor"
    technical_requirement = "technical_requirement"
    business_requirement = "business_requirement"
    contract_obligation = "contract_obligation"
    evidence_source_requirement = "evidence_source_requirement"
    policy_statement = "policy_statement"
    template_instruction = "template_instruction"
    reference_notice = "reference_notice"
    unknown = "unknown"


class LegalPrincipleTag(str, Enum):
    qualification_necessity = "qualification_necessity"
    qualification_nondiscrimination = "qualification_nondiscrimination"
    qualification_scoring_boundary = "qualification_scoring_boundary"
    scoring_relevance = "scoring_relevance"
    evidence_source_restriction = "evidence_source_restriction"
    internal_consistency = "internal_consistency"


class ConstraintType(str, Enum):
    entity_identity = "entity_identity"
    certification = "certification"
    credit_rating = "credit_rating"
    establishment_age = "establishment_age"
    performance_experience = "performance_experience"
    geographic_scope = "geographic_scope"
    industry_scope = "industry_scope"
    institution_source = "institution_source"
    evidence_document = "evidence_document"
    enterprise_scale = "enterprise_scale"
    policy_targeting = "policy_targeting"
    unknown = "unknown"


class RestrictionAxis(str, Enum):
    qualification_level = "qualification_level"
    credit_grade = "credit_grade"
    establishment_years = "establishment_years"
    geographic_region = "geographic_region"
    industry_segment = "industry_segment"
    performance_count = "performance_count"
    designated_institution = "designated_institution"
    enterprise_size = "enterprise_size"
    policy_scope = "policy_scope"
    stage_burden = "stage_burden"
    source_authority = "source_authority"


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
        SemanticZoneType.administrative_info.value: "项目名称、项目编号、预算金额、采购人、代理机构等基础信息。",
        SemanticZoneType.qualification.value: "投标人资格、资质、业绩及准入条件。",
        SemanticZoneType.conformity_review.value: "符合性审查、实质性响应、初审和投标无效判定程序。",
        SemanticZoneType.technical.value: "技术参数、功能配置、样品和检测要求。",
        SemanticZoneType.business.value: "交付、实施、售后和服务响应要求。",
        SemanticZoneType.scoring.value: "评分项、分值、评分规则和量化标准。",
        SemanticZoneType.contract.value: "付款、验收、违约、解除和争议解决条款。",
        SemanticZoneType.template.value: "投标文件格式、声明函样式和模板化文本。",
        SemanticZoneType.policy_explanation.value: "政府采购政策、扶持政策和合规背景说明。",
        SemanticZoneType.appendix_reference.value: "详见附件、附表、另册提供等引用性内容。",
        SemanticZoneType.catalog_or_navigation.value: "目录、章节导航和结构索引。",
        SemanticZoneType.public_copy_or_noise.value: "公开副本残片、页眉页脚和无关噪声。",
        SemanticZoneType.mixed_or_uncertain.value: "暂时无法稳定落入单一区域的混合内容。",
    },
    "effect_tags": {
        EffectTag.binding.value: "正式约束性内容，可作为主证据候选。",
        EffectTag.template.value: "模板文本，不默认视为正式约束。",
        EffectTag.example.value: "示例文本，不默认视为正式约束。",
        EffectTag.optional.value: "可选项，需要结合上下文判断是否启用。",
        EffectTag.reference_only.value: "引用性文本，本身不构成完整约束。",
    },
    "legal_effects": {
        LegalEffectType.qualification_gate.value: "投标准入门槛或资格审查条件。",
        LegalEffectType.review_procedure.value: "资格性审查、符合性审查、初审和无效投标判定等程序性要求。",
        LegalEffectType.scoring_factor.value: "进入评分表或量化打分的因素。",
        LegalEffectType.technical_requirement.value: "技术、参数、性能、检测等需求约束。",
        LegalEffectType.business_requirement.value: "交付、实施、售后等商务履约要求。",
        LegalEffectType.contract_obligation.value: "付款、验收、违约、保证金等合同义务。",
        LegalEffectType.evidence_source_requirement.value: "指定证明材料来源、机构或出具口径。",
        LegalEffectType.policy_statement.value: "政策适用口径或采购范围声明。",
        LegalEffectType.template_instruction.value: "格式、模板、示例性文本。",
        LegalEffectType.reference_notice.value: "附件、附表或引用提示。",
        LegalEffectType.unknown.value: "尚未判定法律作用。",
    },
    "legal_principles": {
        LegalPrincipleTag.qualification_necessity.value: "资格条件应与履约能力和项目需要直接相关。",
        LegalPrincipleTag.qualification_nondiscrimination.value: "资格条件不得形成不合理歧视或排斥。",
        LegalPrincipleTag.qualification_scoring_boundary.value: "资格门槛与评分因素应各司其职，不得双重抬门槛。",
        LegalPrincipleTag.scoring_relevance.value: "评分因素应与采购标的、履约质量直接相关。",
        LegalPrincipleTag.evidence_source_restriction.value: "证明材料来源不得无正当理由指定特定机构。",
        LegalPrincipleTag.internal_consistency.value: "采购文件内部政策、资格和评分口径应一致。",
    },
}


def build_zone_ontology_payload() -> dict[str, object]:
    return {
        "version": ZONE_ONTOLOGY_VERSION,
        "zones": [
            {
                "zone_type": zone.value,
                "primary_review_type": ZONE_PRIMARY_REVIEW_TYPES[zone],
                "description": ONTOLOGY_DESCRIPTIONS["semantic_zones"].get(zone.value, ""),
                "evidence_policy": ZONE_EVIDENCE_POLICY.get(zone, ""),
            }
            for zone in SemanticZoneType
        ],
        "legal_effects": [
            {
                "effect_type": effect.value,
                "description": ONTOLOGY_DESCRIPTIONS["legal_effects"].get(effect.value, ""),
            }
            for effect in LegalEffectType
        ],
        "legal_principles": [
            {
                "principle_tag": principle.value,
                "description": ONTOLOGY_DESCRIPTIONS["legal_principles"].get(principle.value, ""),
            }
            for principle in LegalPrincipleTag
        ],
    }

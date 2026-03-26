from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum

from .ontology import (
    ClauseSemanticType,
    ConstraintType,
    EffectTag,
    LegalEffectType,
    LegalPrincipleTag,
    NodeType,
    RestrictionAxis,
    SemanticZoneType,
    ZONE_ONTOLOGY_VERSION,
)


class FileType(str, Enum):
    complete_tender = "完整招标文件"
    procurement_requirement = "采购需求文件"
    scoring_detail = "评分细则文件"
    contract_draft = "合同草案"
    mixed_document = "混合型文件"
    unknown = "未知类型"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class FindingType(str, Enum):
    confirmed_issue = "confirmed_issue"
    warning = "warning"
    missing_evidence = "missing_evidence"
    manual_review_required = "manual_review_required"
    pass_ = "pass"


class ConclusionLevel(str, Enum):
    ready = "整体基本规范，可直接使用"
    optimize = "存在个别条款待完善，建议优化后发出"
    revise = "存在明显合规风险，建议修改后再发布"
    reject = "存在实质性不合规问题，不建议直接发布"


class ReviewMode(str, Enum):
    fast = "fast"
    enhanced = "enhanced"


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    timed_out = "timed_out"
    skipped = "skipped"


class AdoptionStatus(str, Enum):
    rule_based = "rule_based"
    direct = "可直接采用"
    manual = "需人工确认"


class ClauseRole(str, Enum):
    procurement_requirement = "采购约束条款"
    qualification_or_scoring = "资格或评分条款"
    contract_term = "合同履约条款"
    form_template = "投标文件模板"
    policy_explanation = "政策说明文本"
    document_definition = "定义或程序说明"
    appendix_reference = "附件引用"
    unknown = "未识别"


class ReviewPointStatus(str, Enum):
    identified = "identified"
    confirmed = "confirmed"
    suspected = "suspected"
    manual_confirmation = "manual_confirmation"


class FormalDisposition(str, Enum):
    include = "include"
    manual_confirmation = "manual_confirmation"
    filtered_out = "filtered_out"


class EvidenceLevel(str, Enum):
    strong = "strong"
    moderate = "moderate"
    weak = "weak"
    missing = "missing"


class ApplicabilityStatus(str, Enum):
    satisfied = "satisfied"
    unsatisfied = "unsatisfied"
    insufficient = "insufficient"
    excluded = "excluded"
    not_applicable = "not_applicable"


class QualityGateStatus(str, Enum):
    passed = "passed"
    manual_confirmation = "manual_confirmation"
    filtered = "filtered"


@dataclass(slots=True)
class Evidence:
    quote: str
    section_hint: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class LegalBasis:
    source_name: str
    article_hint: str
    summary: str
    basis_type: str = "规范性依据"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class ReviewPointCondition:
    name: str
    clause_fields: list[str] = field(default_factory=list)
    signal_groups: list[list[str]] = field(default_factory=list)
    legal_effects: list[str] = field(default_factory=list)
    principle_tags: list[str] = field(default_factory=list)
    constraint_types: list[str] = field(default_factory=list)
    restriction_axes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ClauseConstraint:
    subject: str = ""
    role: str = ""
    legal_effect: LegalEffectType = LegalEffectType.unknown
    constraint_types: list[ConstraintType] = field(default_factory=list)
    restriction_axes: list[RestrictionAxis] = field(default_factory=list)
    evidence_source: str = ""
    region_tokens: list[str] = field(default_factory=list)
    industry_tokens: list[str] = field(default_factory=list)
    qualifier_tokens: list[str] = field(default_factory=list)
    exclusion_effect: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "subject": self.subject,
            "role": self.role,
            "legal_effect": self.legal_effect.value,
            "constraint_types": [item.value for item in self.constraint_types],
            "restriction_axes": [item.value for item in self.restriction_axes],
            "evidence_source": self.evidence_source,
            "region_tokens": self.region_tokens,
            "industry_tokens": self.industry_tokens,
            "qualifier_tokens": self.qualifier_tokens,
            "exclusion_effect": self.exclusion_effect,
        }


@dataclass(slots=True)
class ReviewPointDefinition:
    catalog_id: str
    title: str
    dimension: str
    default_severity: Severity
    task_type: str = "generic"
    risk_family: str = ""
    target_zones: list[str] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    scenario_tags: list[str] = field(default_factory=list)
    required_conditions: list[ReviewPointCondition] = field(default_factory=list)
    exclusion_conditions: list[ReviewPointCondition] = field(default_factory=list)
    evidence_hints: list[str] = field(default_factory=list)
    rebuttal_templates: list[list[str]] = field(default_factory=list)
    enhancement_fields: list[str] = field(default_factory=list)
    basis_hint: str = ""
    legal_principle_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "catalog_id": self.catalog_id,
            "title": self.title,
            "dimension": self.dimension,
            "default_severity": self.default_severity.value,
            "task_type": self.task_type,
            "risk_family": self.risk_family,
            "target_zones": self.target_zones,
            "required_fields": self.required_fields,
            "scenario_tags": self.scenario_tags,
            "required_conditions": [item.to_dict() for item in self.required_conditions],
            "exclusion_conditions": [item.to_dict() for item in self.exclusion_conditions],
            "evidence_hints": self.evidence_hints,
            "rebuttal_templates": self.rebuttal_templates,
            "enhancement_fields": self.enhancement_fields,
            "basis_hint": self.basis_hint,
            "legal_principle_tags": self.legal_principle_tags,
        }


@dataclass(slots=True)
class LegalFactCandidate:
    fact_id: str
    document_id: str
    source_unit_id: str
    fact_type: str
    zone_type: str = ""
    clause_semantic_type: str = ""
    effect_tags: list[str] = field(default_factory=list)
    subject: str = ""
    predicate: str = ""
    object_text: str = ""
    normalized_terms: list[str] = field(default_factory=list)
    constraint_type: str = ""
    constraint_value: dict[str, object] = field(default_factory=dict)
    evidence_stage: str = "unknown"
    counterparty: str = ""
    anchor: dict[str, object] = field(default_factory=dict)
    table_context: dict[str, object] = field(default_factory=dict)
    supporting_context: list[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_llm_disambiguation: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RuleDefinition:
    rule_id: str
    version: str
    name: str
    point_id: str
    rule_type: str = "soft_rule"
    status: str = "active"
    risk_family: str = ""
    applicable_zone_types: list[str] = field(default_factory=list)
    applicable_fact_types: list[str] = field(default_factory=list)
    trigger_patterns: list[str] = field(default_factory=list)
    required_fact_slots: list[str] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    exception_patterns: list[str] = field(default_factory=list)
    severity_hint: str = Severity.medium.value
    default_disposition: str = FindingType.warning.value
    llm_assist_policy: str = "low_confidence_only"
    llm_questions: list[str] = field(default_factory=list)
    remedy_template_ids: list[str] = field(default_factory=list)
    authority_binding_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ReviewPointContract:
    point_id: str
    title: str
    description: str = ""
    risk_family: str = ""
    legal_theme: str = ""
    applicable_procurement_kinds: list[str] = field(default_factory=list)
    target_zone_types: list[str] = field(default_factory=list)
    primary_review_types: list[str] = field(default_factory=list)
    required_fact_types: list[str] = field(default_factory=list)
    supporting_fact_types: list[str] = field(default_factory=list)
    activation_rule_ids: list[str] = field(default_factory=list)
    suppression_rule_ids: list[str] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    enhancement_fields: list[str] = field(default_factory=list)
    evidence_policy: str = ""
    quality_gate_policy: str = ""
    manual_boundary_policy: str = ""
    authority_binding_ids: list[str] = field(default_factory=list)
    severity_policy: str = Severity.medium.value
    report_group: str = ""
    report_priority: int = 100

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class AuthorityBinding:
    binding_id: str
    authority_id: str
    clause_id: str
    doc_title: str
    article_label: str
    norm_level: str
    binding_scope: str = "point"
    point_id: str = ""
    rule_id: str = ""
    legal_proposition: str = ""
    applicability_conditions: list[str] = field(default_factory=list)
    exclusion_conditions: list[str] = field(default_factory=list)
    requires_human_review_when: list[str] = field(default_factory=list)
    evidence_expectations: list[str] = field(default_factory=list)
    reasoning_template: str = ""
    suggested_remedy_template: str = ""
    priority: str = "primary"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RuleHit:
    hit_id: str
    rule_id: str
    point_id: str
    fact_ids: list[str] = field(default_factory=list)
    trigger_reasons: list[str] = field(default_factory=list)
    matched_slots: list[str] = field(default_factory=list)
    confidence: float = 0.0
    severity_hint: str = Severity.medium.value
    default_disposition: str = FindingType.warning.value

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ReviewPointInstance:
    instance_id: str
    point_id: str
    title: str
    risk_family: str = ""
    matched_rule_ids: list[str] = field(default_factory=list)
    supporting_fact_ids: list[str] = field(default_factory=list)
    authority_binding_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ApplicabilityItem:
    name: str
    status: ApplicabilityStatus
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass(slots=True)
class ApplicabilityCheck:
    point_id: str
    catalog_id: str
    applicable: bool
    requirement_results: list[ApplicabilityItem] = field(default_factory=list)
    exclusion_results: list[ApplicabilityItem] = field(default_factory=list)
    satisfied_conditions: list[str] = field(default_factory=list)
    missing_conditions: list[str] = field(default_factory=list)
    blocking_conditions: list[str] = field(default_factory=list)
    requirement_chain_complete: bool = False
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "point_id": self.point_id,
            "catalog_id": self.catalog_id,
            "applicable": self.applicable,
            "requirement_results": [item.to_dict() for item in self.requirement_results],
            "exclusion_results": [item.to_dict() for item in self.exclusion_results],
            "satisfied_conditions": self.satisfied_conditions,
            "missing_conditions": self.missing_conditions,
            "blocking_conditions": self.blocking_conditions,
            "requirement_chain_complete": self.requirement_chain_complete,
            "summary": self.summary,
        }


@dataclass(slots=True)
class ReviewQualityGate:
    point_id: str
    status: QualityGateStatus
    reasons: list[str] = field(default_factory=list)
    duplicate_of: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "point_id": self.point_id,
            "status": self.status.value,
            "reasons": self.reasons,
            "duplicate_of": self.duplicate_of,
        }


@dataclass(slots=True)
class Finding:
    dimension: str
    finding_type: FindingType
    severity: Severity
    title: str
    rationale: str
    evidence: list[Evidence] = field(default_factory=list)
    legal_basis: list[LegalBasis] = field(default_factory=list)
    confidence: float = 0.0
    next_action: str = ""
    adoption_status: AdoptionStatus = AdoptionStatus.rule_based
    review_note: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["finding_type"] = self.finding_type.value
        payload["severity"] = self.severity.value
        payload["adoption_status"] = self.adoption_status.value
        payload["evidence"] = [item.to_dict() for item in self.evidence]
        payload["legal_basis"] = [item.to_dict() for item in self.legal_basis]
        return payload


@dataclass(slots=True)
class ReviewDimension:
    key: str
    display_name: str
    description: str
    triggers: list[str]
    missing_markers: list[str] = field(default_factory=list)
    risk_hint: str = ""


@dataclass(slots=True)
class ParsedPage:
    page_index: int
    text: str
    source: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ParsedTable:
    table_index: int
    row_count: int
    rows: list[list[str]]
    source: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class SourceAnchor:
    source_path: str = ""
    page_no: int | None = None
    block_no: int | None = None
    paragraph_no: int | None = None
    table_no: int | None = None
    row_no: int | None = None
    cell_no: int | None = None
    line_hint: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RawCell:
    row_index: int
    col_index: int
    text: str
    is_header: bool = False
    anchor: SourceAnchor = field(default_factory=SourceAnchor)

    def to_dict(self) -> dict[str, object]:
        return {
            "row_index": self.row_index,
            "col_index": self.col_index,
            "text": self.text,
            "is_header": self.is_header,
            "anchor": self.anchor.to_dict(),
        }


@dataclass(slots=True)
class RawTable:
    table_id: str
    rows: list[list[RawCell]] = field(default_factory=list)
    anchor: SourceAnchor = field(default_factory=SourceAnchor)
    title_hint: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "table_id": self.table_id,
            "rows": [[cell.to_dict() for cell in row] for row in self.rows],
            "anchor": self.anchor.to_dict(),
            "title_hint": self.title_hint,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class RawBlock:
    block_id: str
    block_type: str
    text: str
    style_name: str = ""
    numbering: str = ""
    anchor: SourceAnchor = field(default_factory=SourceAnchor)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "block_id": self.block_id,
            "block_type": self.block_type,
            "text": self.text,
            "style_name": self.style_name,
            "numbering": self.numbering,
            "anchor": self.anchor.to_dict(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class DocumentNode:
    node_id: str
    node_type: NodeType
    title: str
    text: str
    path: str = ""
    parent_id: str = ""
    children_ids: list[str] = field(default_factory=list)
    anchor: SourceAnchor = field(default_factory=SourceAnchor)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "title": self.title,
            "text": self.text,
            "path": self.path,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
            "anchor": self.anchor.to_dict(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class SemanticZone:
    node_id: str
    zone_type: SemanticZoneType
    confidence: float = 0.0
    classification_basis: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "zone_type": self.zone_type.value,
            "confidence": self.confidence,
            "classification_basis": self.classification_basis,
        }


@dataclass(slots=True)
class EffectTagResult:
    node_id: str
    effect_tags: list[EffectTag] = field(default_factory=list)
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "effect_tags": [item.value for item in self.effect_tags],
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass(slots=True)
class ClauseUnit:
    unit_id: str
    source_node_id: str
    text: str
    path: str = ""
    anchor: SourceAnchor = field(default_factory=SourceAnchor)
    zone_type: SemanticZoneType = SemanticZoneType.mixed_or_uncertain
    clause_semantic_type: ClauseSemanticType = ClauseSemanticType.unknown_clause
    effect_tags: list[EffectTag] = field(default_factory=list)
    table_context: dict[str, object] = field(default_factory=dict)
    confidence: float = 0.0
    ontology_version: str = ZONE_ONTOLOGY_VERSION
    primary_review_type: str = ""
    legal_effect_type: LegalEffectType = LegalEffectType.unknown
    legal_principle_tags: list[LegalPrincipleTag] = field(default_factory=list)
    clause_constraint: ClauseConstraint = field(default_factory=ClauseConstraint)

    def to_dict(self) -> dict[str, object]:
        return {
            "unit_id": self.unit_id,
            "source_node_id": self.source_node_id,
            "text": self.text,
            "path": self.path,
            "anchor": self.anchor.to_dict(),
            "zone_type": self.zone_type.value,
            "clause_semantic_type": self.clause_semantic_type.value,
            "effect_tags": [item.value for item in self.effect_tags],
            "table_context": self.table_context,
            "confidence": self.confidence,
            "ontology_version": self.ontology_version,
            "primary_review_type": self.primary_review_type,
            "legal_effect_type": self.legal_effect_type.value,
            "legal_principle_tags": [item.value for item in self.legal_principle_tags],
            "clause_constraint": self.clause_constraint.to_dict(),
        }


@dataclass(slots=True)
class DomainProfileCandidate:
    profile_id: str
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ZoneStat:
    zone_type: SemanticZoneType
    node_count: int = 0
    unit_count: int = 0
    ratio: float = 0.0

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["zone_type"] = self.zone_type.value
        return payload


@dataclass(slots=True)
class EffectStat:
    effect_tag: EffectTag
    unit_count: int = 0
    ratio: float = 0.0

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["effect_tag"] = self.effect_tag.value
        return payload


@dataclass(slots=True)
class ClauseSemanticStat:
    clause_semantic_type: ClauseSemanticType
    unit_count: int = 0
    ratio: float = 0.0

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["clause_semantic_type"] = self.clause_semantic_type.value
        return payload


@dataclass(slots=True)
class DomainProfile:
    profile_id: str
    display_name: str
    version: str = "v1"
    ontology_version: str = ZONE_ONTOLOGY_VERSION
    applies_to_procurement_kinds: list[str] = field(default_factory=list)
    supported_zone_types: list[str] = field(default_factory=list)
    primary_review_types: list[str] = field(default_factory=list)
    trigger_keywords: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=list)
    risk_lexicon_pack_id: str = ""
    evidence_pattern_pack_id: str = ""
    false_positive_pack_id: str = ""
    preferred_risk_families: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class DocumentProfile:
    document_id: str
    source_path: str
    ontology_version: str = ZONE_ONTOLOGY_VERSION
    procurement_kind: str = "unknown"
    procurement_kind_confidence: float = 0.0
    routing_mode: str = "standard"
    routing_reasons: list[str] = field(default_factory=list)
    domain_profile_candidates: list[DomainProfileCandidate] = field(default_factory=list)
    dominant_zones: list[ZoneStat] = field(default_factory=list)
    effect_distribution: list[EffectStat] = field(default_factory=list)
    clause_semantic_distribution: list[ClauseSemanticStat] = field(default_factory=list)
    structure_flags: list[str] = field(default_factory=list)
    risk_activation_hints: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    unknown_structure_flags: list[str] = field(default_factory=list)
    parser_semantic_assist_activated: bool = False
    parser_semantic_assist_reviewed_count: int = 0
    parser_semantic_assist_applied_count: int = 0
    zone_ontology_version: str = ZONE_ONTOLOGY_VERSION
    primary_review_types: list[str] = field(default_factory=list)
    representative_anchors: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "source_path": self.source_path,
            "ontology_version": self.ontology_version,
            "procurement_kind": self.procurement_kind,
            "procurement_kind_confidence": self.procurement_kind_confidence,
            "routing_mode": self.routing_mode,
            "routing_reasons": self.routing_reasons,
            "domain_profile_candidates": [item.to_dict() for item in self.domain_profile_candidates],
            "dominant_zones": [item.to_dict() for item in self.dominant_zones],
            "effect_distribution": [item.to_dict() for item in self.effect_distribution],
            "clause_semantic_distribution": [item.to_dict() for item in self.clause_semantic_distribution],
            "structure_flags": self.structure_flags,
            "risk_activation_hints": self.risk_activation_hints,
            "quality_flags": self.quality_flags,
            "unknown_structure_flags": self.unknown_structure_flags,
            "parser_semantic_assist_activated": self.parser_semantic_assist_activated,
            "parser_semantic_assist_reviewed_count": self.parser_semantic_assist_reviewed_count,
            "parser_semantic_assist_applied_count": self.parser_semantic_assist_applied_count,
            "zone_ontology_version": self.zone_ontology_version,
            "primary_review_types": self.primary_review_types,
            "representative_anchors": self.representative_anchors,
            "summary": self.summary,
        }


@dataclass(slots=True)
class ParserSemanticCandidate:
    node_id: str
    unit_id: str
    path: str
    text: str
    reasons: list[str] = field(default_factory=list)
    current_zone_type: SemanticZoneType = SemanticZoneType.mixed_or_uncertain
    current_clause_semantic_type: ClauseSemanticType = ClauseSemanticType.unknown_clause
    current_effect_tags: list[EffectTag] = field(default_factory=list)
    current_confidence: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "unit_id": self.unit_id,
            "path": self.path,
            "text": self.text,
            "reasons": self.reasons,
            "current_zone_type": self.current_zone_type.value,
            "current_clause_semantic_type": self.current_clause_semantic_type.value,
            "current_effect_tags": [item.value for item in self.current_effect_tags],
            "current_confidence": self.current_confidence,
        }


@dataclass(slots=True)
class ParserSemanticResolution:
    node_id: str
    proposed_zone_type: SemanticZoneType | None = None
    proposed_clause_semantic_type: ClauseSemanticType | None = None
    proposed_effect_tags: list[EffectTag] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    applied: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "proposed_zone_type": self.proposed_zone_type.value if self.proposed_zone_type else "",
            "proposed_clause_semantic_type": (
                self.proposed_clause_semantic_type.value if self.proposed_clause_semantic_type else ""
            ),
            "proposed_effect_tags": [item.value for item in self.proposed_effect_tags],
            "confidence": self.confidence,
            "reason": self.reason,
            "applied": self.applied,
        }


@dataclass(slots=True)
class ParserSemanticTrace:
    activated: bool = False
    strategy: str = "rule_primary_llm_disambiguation"
    activation_reasons: list[str] = field(default_factory=list)
    candidate_count: int = 0
    reviewed_count: int = 0
    applied_count: int = 0
    warnings: list[str] = field(default_factory=list)
    candidates: list[ParserSemanticCandidate] = field(default_factory=list)
    resolutions: list[ParserSemanticResolution] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "activated": self.activated,
            "strategy": self.strategy,
            "activation_reasons": self.activation_reasons,
            "candidate_count": self.candidate_count,
            "reviewed_count": self.reviewed_count,
            "applied_count": self.applied_count,
            "warnings": self.warnings,
            "candidates": [item.to_dict() for item in self.candidates],
            "resolutions": [item.to_dict() for item in self.resolutions],
        }


@dataclass(slots=True)
class ParseResult:
    parser_name: str
    source_path: str
    source_format: str
    page_count: int | None
    text: str
    pages: list[ParsedPage] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    raw_blocks: list[RawBlock] = field(default_factory=list)
    raw_tables: list[RawTable] = field(default_factory=list)
    document_nodes: list[DocumentNode] = field(default_factory=list)
    semantic_zones: list[SemanticZone] = field(default_factory=list)
    effect_tag_results: list[EffectTagResult] = field(default_factory=list)
    clause_units: list[ClauseUnit] = field(default_factory=list)
    legal_fact_candidates: list[LegalFactCandidate] = field(default_factory=list)
    rule_hits: list[RuleHit] = field(default_factory=list)
    review_point_instances: list[ReviewPointInstance] = field(default_factory=list)
    document_profile: DocumentProfile | None = None
    parser_semantic_trace: ParserSemanticTrace | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "parser_name": self.parser_name,
            "source_path": self.source_path,
            "source_format": self.source_format,
            "page_count": self.page_count,
            "text": self.text,
            "pages": [item.to_dict() for item in self.pages],
            "tables": [item.to_dict() for item in self.tables],
            "raw_blocks": [item.to_dict() for item in self.raw_blocks],
            "raw_tables": [item.to_dict() for item in self.raw_tables],
            "document_nodes": [item.to_dict() for item in self.document_nodes],
            "semantic_zones": [item.to_dict() for item in self.semantic_zones],
            "effect_tag_results": [item.to_dict() for item in self.effect_tag_results],
            "clause_units": [item.to_dict() for item in self.clause_units],
            "legal_fact_candidates": [item.to_dict() for item in self.legal_fact_candidates],
            "rule_hits": [item.to_dict() for item in self.rule_hits],
            "review_point_instances": [item.to_dict() for item in self.review_point_instances],
            "document_profile": self.document_profile.to_dict() if self.document_profile else None,
            "parser_semantic_trace": self.parser_semantic_trace.to_dict() if self.parser_semantic_trace else None,
            "warnings": self.warnings,
        }


@dataclass(slots=True)
class SourceDocument:
    document_name: str
    source_path: str
    source_format: str
    parser_name: str
    page_count: int | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class FileInfo:
    document_name: str
    format_hint: str
    text_length: int
    file_type: FileType
    review_scope: str
    review_boundary: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["file_type"] = self.file_type.value
        return payload


@dataclass(slots=True)
class SectionIndex:
    section_name: str
    located: bool
    anchor: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ExtractedClause:
    category: str
    field_name: str
    content: str
    source_anchor: str
    normalized_value: str = ""
    relation_tags: list[str] = field(default_factory=list)
    clause_role: ClauseRole = ClauseRole.unknown
    semantic_zone: SemanticZoneType = SemanticZoneType.mixed_or_uncertain
    effect_tags: list[EffectTag] = field(default_factory=list)
    adoption_status: AdoptionStatus = AdoptionStatus.rule_based
    review_note: str = ""
    legal_effect_type: LegalEffectType = LegalEffectType.unknown
    legal_principle_tags: list[LegalPrincipleTag] = field(default_factory=list)
    clause_constraint: ClauseConstraint = field(default_factory=ClauseConstraint)

    def to_dict(self) -> dict[str, str]:
        payload = asdict(self)
        payload["relation_tags"] = list(self.relation_tags)
        payload["clause_role"] = self.clause_role.value
        payload["semantic_zone"] = self.semantic_zone.value
        payload["effect_tags"] = [item.value for item in self.effect_tags]
        payload["adoption_status"] = self.adoption_status.value
        payload["legal_effect_type"] = self.legal_effect_type.value
        payload["legal_principle_tags"] = [item.value for item in self.legal_principle_tags]
        payload["clause_constraint"] = self.clause_constraint.to_dict()
        return payload


@dataclass(slots=True)
class RiskHit:
    risk_group: str
    rule_name: str
    severity: Severity
    matched_text: str
    rationale: str
    source_anchor: str
    legal_basis: list[LegalBasis] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["severity"] = self.severity.value
        payload["legal_basis"] = [item.to_dict() for item in self.legal_basis]
        return payload


@dataclass(slots=True)
class ConsistencyCheck:
    topic: str
    status: str
    detail: str
    legal_basis: list[LegalBasis] = field(default_factory=list)

    def to_dict(self) -> dict[str, str]:
        payload = asdict(self)
        payload["legal_basis"] = [item.to_dict() for item in self.legal_basis]
        return payload


@dataclass(slots=True)
class Recommendation:
    related_issue: str
    suggestion: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class SpecialistTableRow:
    item_name: str
    severity: Severity
    detail: str
    source_anchor: str

    def to_dict(self) -> dict[str, str]:
        payload = asdict(self)
        payload["severity"] = self.severity.value
        return payload


@dataclass(slots=True)
class SpecialistTables:
    project_structure: list[SpecialistTableRow] = field(default_factory=list)
    sme_policy: list[SpecialistTableRow] = field(default_factory=list)
    personnel_boundary: list[SpecialistTableRow] = field(default_factory=list)
    contract_performance: list[SpecialistTableRow] = field(default_factory=list)
    template_conflicts: list[SpecialistTableRow] = field(default_factory=list)
    summaries: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "project_structure": [item.to_dict() for item in self.project_structure],
            "sme_policy": [item.to_dict() for item in self.sme_policy],
            "personnel_boundary": [item.to_dict() for item in self.personnel_boundary],
            "contract_performance": [item.to_dict() for item in self.contract_performance],
            "template_conflicts": [item.to_dict() for item in self.template_conflicts],
            "summaries": self.summaries,
        }


@dataclass(slots=True)
class RunStageRecord:
    stage_name: str
    status: str
    item_count: int | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class TaskRecord:
    task_name: str
    status: TaskStatus
    detail: str = ""
    item_count: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "task_name": self.task_name,
            "status": self.status.value,
            "detail": self.detail,
            "item_count": self.item_count,
        }


@dataclass(slots=True)
class RuleSelection:
    core_modules: list[str] = field(default_factory=list)
    enhancement_modules: list[str] = field(default_factory=list)
    scenario_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ReviewPlanningContract:
    document_id: str
    procurement_kind: str
    ontology_version: str = ZONE_ONTOLOGY_VERSION
    routing_mode: str = "standard"
    route_tags: list[str] = field(default_factory=list)
    routing_flags: list[str] = field(default_factory=list)
    activation_reasons: list[str] = field(default_factory=list)
    activated_risk_families: list[str] = field(default_factory=list)
    suppressed_risk_families: list[str] = field(default_factory=list)
    target_zones: list[str] = field(default_factory=list)
    target_primary_review_types: list[str] = field(default_factory=list)
    planned_catalog_ids: list[str] = field(default_factory=list)
    priority_dimensions: list[str] = field(default_factory=list)
    base_extraction_demands: list[str] = field(default_factory=list)
    required_task_extraction_demands: list[str] = field(default_factory=list)
    optional_enhancement_extraction_demands: list[str] = field(default_factory=list)
    enhancement_extraction_demands: list[str] = field(default_factory=list)
    unknown_fallback_extraction_demands: list[str] = field(default_factory=list)
    extraction_demands: list[str] = field(default_factory=list)
    high_value_fields: list[str] = field(default_factory=list)
    matched_extraction_fields: list[str] = field(default_factory=list)
    base_hit_fields: list[str] = field(default_factory=list)
    required_hit_fields: list[str] = field(default_factory=list)
    optional_hit_fields: list[str] = field(default_factory=list)
    unknown_fallback_hit_fields: list[str] = field(default_factory=list)
    clause_unit_targeted_count: int = 0
    text_fallback_clause_count: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class HeaderInfo:
    ontology_version: str = ZONE_ONTOLOGY_VERSION
    project_name: str = ""
    project_code: str = ""
    purchaser_name: str = ""
    agency_name: str = ""
    budget_amount: str = ""
    max_price: str = ""
    source_evidence: dict[str, str] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class LLMSemanticReview:
    scenario_review_summary: str = ""
    scoring_review_summary: str = ""
    dynamic_review_tasks: list[ReviewPointDefinition] = field(default_factory=list)
    scoring_dynamic_review_tasks: list[ReviewPointDefinition] = field(default_factory=list)
    clause_supplements: list[ExtractedClause] = field(default_factory=list)
    specialist_findings: list[Finding] = field(default_factory=list)
    consistency_findings: list[Finding] = field(default_factory=list)
    verdict_review: str = ""
    role_review_notes: list[str] = field(default_factory=list)
    evidence_review_notes: list[str] = field(default_factory=list)
    applicability_review_notes: list[str] = field(default_factory=list)
    review_point_second_reviews: list["ReviewPointSecondReview"] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_review_summary": self.scenario_review_summary,
            "scoring_review_summary": self.scoring_review_summary,
            "dynamic_review_tasks": [item.to_dict() for item in self.dynamic_review_tasks],
            "scoring_dynamic_review_tasks": [item.to_dict() for item in self.scoring_dynamic_review_tasks],
            "clause_supplements": [item.to_dict() for item in self.clause_supplements],
            "specialist_findings": [item.to_dict() for item in self.specialist_findings],
            "consistency_findings": [item.to_dict() for item in self.consistency_findings],
            "verdict_review": self.verdict_review,
            "role_review_notes": self.role_review_notes,
            "evidence_review_notes": self.evidence_review_notes,
            "applicability_review_notes": self.applicability_review_notes,
            "review_point_second_reviews": [item.to_dict() for item in self.review_point_second_reviews],
        }


@dataclass(slots=True)
class ReviewWorkItem:
    item_type: str
    title: str
    severity: str
    source: str
    reason: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class EvidenceBundle:
    direct_evidence: list[Evidence] = field(default_factory=list)
    supporting_evidence: list[Evidence] = field(default_factory=list)
    conflicting_evidence: list[Evidence] = field(default_factory=list)
    rebuttal_evidence: list[Evidence] = field(default_factory=list)
    missing_evidence_notes: list[str] = field(default_factory=list)
    clause_roles: list[ClauseRole] = field(default_factory=list)
    sufficiency_summary: str = ""
    evidence_level: EvidenceLevel = EvidenceLevel.missing
    evidence_score: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "direct_evidence": [item.to_dict() for item in self.direct_evidence],
            "supporting_evidence": [item.to_dict() for item in self.supporting_evidence],
            "conflicting_evidence": [item.to_dict() for item in self.conflicting_evidence],
            "rebuttal_evidence": [item.to_dict() for item in self.rebuttal_evidence],
            "missing_evidence_notes": self.missing_evidence_notes,
            "clause_roles": [item.value for item in self.clause_roles],
            "sufficiency_summary": self.sufficiency_summary,
            "evidence_level": self.evidence_level.value,
            "evidence_score": self.evidence_score,
        }


@dataclass(slots=True)
class ReviewPoint:
    point_id: str
    catalog_id: str
    title: str
    dimension: str
    severity: Severity
    status: ReviewPointStatus
    rationale: str
    evidence_bundle: EvidenceBundle = field(default_factory=EvidenceBundle)
    legal_basis: list[LegalBasis] = field(default_factory=list)
    source_findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "point_id": self.point_id,
            "catalog_id": self.catalog_id,
            "title": self.title,
            "dimension": self.dimension,
            "severity": self.severity.value,
            "status": self.status.value,
            "rationale": self.rationale,
            "evidence_bundle": self.evidence_bundle.to_dict(),
            "legal_basis": [item.to_dict() for item in self.legal_basis],
            "source_findings": self.source_findings,
        }


@dataclass(slots=True)
class ReviewPointSecondReview:
    point_id: str
    title: str
    role_judgment: str = ""
    evidence_judgment: str = ""
    primary_evidence_judgment: str = ""
    supporting_evidence_judgment: str = ""
    applicability_judgment: str = ""
    intensity_judgment: str = ""
    suggested_disposition: str = ""
    rationale: str = ""
    adoption_status: AdoptionStatus = AdoptionStatus.manual

    def to_dict(self) -> dict[str, object]:
        return {
            "point_id": self.point_id,
            "title": self.title,
            "role_judgment": self.role_judgment,
            "evidence_judgment": self.evidence_judgment,
            "primary_evidence_judgment": self.primary_evidence_judgment,
            "supporting_evidence_judgment": self.supporting_evidence_judgment,
            "applicability_judgment": self.applicability_judgment,
            "intensity_judgment": self.intensity_judgment,
            "suggested_disposition": self.suggested_disposition,
            "rationale": self.rationale,
            "adoption_status": self.adoption_status.value,
        }


@dataclass(slots=True)
class FormalAdjudication:
    point_id: str
    catalog_id: str
    title: str
    disposition: FormalDisposition
    rationale: str
    included_in_formal: bool
    section_hint: str = ""
    primary_quote: str = ""
    evidence_sufficient: bool = False
    legal_basis_applicable: bool = False
    applicability_summary: str = ""
    quality_gate_status: QualityGateStatus = QualityGateStatus.passed
    recommended_for_review: bool = False
    review_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "point_id": self.point_id,
            "catalog_id": self.catalog_id,
            "title": self.title,
            "disposition": self.disposition.value,
            "rationale": self.rationale,
            "included_in_formal": self.included_in_formal,
            "section_hint": self.section_hint,
            "primary_quote": self.primary_quote,
            "evidence_sufficient": self.evidence_sufficient,
            "legal_basis_applicable": self.legal_basis_applicable,
            "applicability_summary": self.applicability_summary,
            "quality_gate_status": self.quality_gate_status.value,
            "recommended_for_review": self.recommended_for_review,
            "review_reason": self.review_reason,
        }


@dataclass(slots=True)
class ReviewReport:
    review_mode: ReviewMode
    parse_result: ParseResult
    file_info: FileInfo
    scope_statement: str
    overall_conclusion: ConclusionLevel
    summary: str
    llm_enhanced: bool
    llm_warnings: list[str]
    findings: list[Finding]
    relative_strengths: list[str]
    section_index: list[SectionIndex]
    extracted_clauses: list[ExtractedClause]
    risk_hits: list[RiskHit]
    specialist_tables: SpecialistTables
    consistency_checks: list[ConsistencyCheck]
    recommendations: list[Recommendation]
    manual_review_queue: list[str]
    reviewed_dimensions: list[str]
    source_documents: list[SourceDocument] = field(default_factory=list)
    review_points: list[ReviewPoint] = field(default_factory=list)
    review_point_catalog: list[ReviewPointDefinition] = field(default_factory=list)
    review_planning_contract: ReviewPlanningContract | None = None
    applicability_checks: list[ApplicabilityCheck] = field(default_factory=list)
    quality_gates: list[ReviewQualityGate] = field(default_factory=list)
    formal_adjudication: list[FormalAdjudication] = field(default_factory=list)
    high_risk_review_items: list[ReviewWorkItem] = field(default_factory=list)
    pending_confirmation_items: list[ReviewWorkItem] = field(default_factory=list)
    stage_records: list[RunStageRecord] = field(default_factory=list)
    task_records: list[TaskRecord] = field(default_factory=list)
    rule_selection: RuleSelection = field(default_factory=RuleSelection)
    llm_semantic_review: LLMSemanticReview = field(default_factory=LLMSemanticReview)

    def to_dict(self) -> dict[str, object]:
        return {
            "review_mode": self.review_mode.value,
            "parse_result": self.parse_result.to_dict(),
            "file_info": self.file_info.to_dict(),
            "scope_statement": self.scope_statement,
            "overall_conclusion": self.overall_conclusion.value,
            "summary": self.summary,
            "llm_enhanced": self.llm_enhanced,
            "llm_warnings": self.llm_warnings,
            "findings": [finding.to_dict() for finding in self.findings],
            "relative_strengths": self.relative_strengths,
            "section_index": [item.to_dict() for item in self.section_index],
            "extracted_clauses": [item.to_dict() for item in self.extracted_clauses],
            "risk_hits": [item.to_dict() for item in self.risk_hits],
            "specialist_tables": self.specialist_tables.to_dict(),
            "consistency_checks": [item.to_dict() for item in self.consistency_checks],
            "recommendations": [item.to_dict() for item in self.recommendations],
            "manual_review_queue": self.manual_review_queue,
            "reviewed_dimensions": self.reviewed_dimensions,
            "source_documents": [item.to_dict() for item in self.source_documents],
            "review_points": [item.to_dict() for item in self.review_points],
            "review_point_catalog": [item.to_dict() for item in self.review_point_catalog],
            "review_planning_contract": self.review_planning_contract.to_dict() if self.review_planning_contract else None,
            "applicability_checks": [item.to_dict() for item in self.applicability_checks],
            "quality_gates": [item.to_dict() for item in self.quality_gates],
            "formal_adjudication": [item.to_dict() for item in self.formal_adjudication],
            "high_risk_review_items": [item.to_dict() for item in self.high_risk_review_items],
            "pending_confirmation_items": [item.to_dict() for item in self.pending_confirmation_items],
            "stage_records": [item.to_dict() for item in self.stage_records],
            "task_records": [item.to_dict() for item in self.task_records],
            "rule_selection": self.rule_selection.to_dict(),
            "llm_semantic_review": self.llm_semantic_review.to_dict(),
        }

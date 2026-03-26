from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re

from ..models import ExtractedClause
from ..ontology import EffectTag, SemanticZoneType, ZONE_ONTOLOGY_VERSION, ZONE_PRIMARY_REVIEW_TYPES


@dataclass(slots=True)
class ZoneStat:
    zone_type: str
    node_count: int
    unit_count: int
    ratio: float

    def to_dict(self) -> dict[str, object]:
        return {
            "zone_type": self.zone_type,
            "node_count": self.node_count,
            "unit_count": self.unit_count,
            "ratio": self.ratio,
        }


@dataclass(slots=True)
class EffectStat:
    effect_tag: str
    unit_count: int
    ratio: float

    def to_dict(self) -> dict[str, object]:
        return {
            "effect_tag": self.effect_tag,
            "unit_count": self.unit_count,
            "ratio": self.ratio,
        }


@dataclass(slots=True)
class ClauseSemanticStat:
    clause_semantic_type: str
    unit_count: int
    ratio: float

    def to_dict(self) -> dict[str, object]:
        return {
            "clause_semantic_type": self.clause_semantic_type,
            "unit_count": self.unit_count,
            "ratio": self.ratio,
        }


@dataclass(slots=True)
class DomainProfileCandidate:
    profile_id: str
    confidence: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "confidence": self.confidence,
            "reasons": self.reasons,
        }


@dataclass(slots=True)
class DocumentProfile:
    document_id: str
    source_path: str
    procurement_kind: str
    procurement_kind_confidence: float
    ontology_version: str = ZONE_ONTOLOGY_VERSION
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
    primary_review_types: list[str] = field(default_factory=list)
    representative_anchors: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "source_path": self.source_path,
            "procurement_kind": self.procurement_kind,
            "procurement_kind_confidence": self.procurement_kind_confidence,
            "ontology_version": self.ontology_version,
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
            "primary_review_types": self.primary_review_types,
            "representative_anchors": self.representative_anchors,
            "summary": self.summary,
        }


@dataclass(slots=True)
class ZoneWeight:
    zone_type: str
    weight: float


@dataclass(slots=True)
class EffectWeight:
    effect_tag: str
    weight: float


@dataclass(slots=True)
class RiskLexiconPack:
    pack_id: str
    terms_by_family: dict[str, list[str]]
    anti_terms_by_family: dict[str, list[str]]


@dataclass(slots=True)
class EvidencePattern:
    pattern_id: str
    risk_family: str
    expected_zones: list[str]
    expected_effects: list[str]
    signal_groups: list[list[str]]
    anti_signal_groups: list[list[str]] = field(default_factory=list)


@dataclass(slots=True)
class EvidencePatternPack:
    pack_id: str
    primary_patterns: list[EvidencePattern] = field(default_factory=list)
    supporting_patterns: list[EvidencePattern] = field(default_factory=list)
    weak_patterns: list[EvidencePattern] = field(default_factory=list)


@dataclass(slots=True)
class FalsePositivePack:
    pack_id: str
    anti_terms_by_family: dict[str, list[str]]
    penalty: float = 0.12


@dataclass(slots=True)
class DomainProfile:
    profile_id: str
    display_name: str
    version: str
    applies_to_procurement_kinds: list[str]
    trigger_keywords: list[str]
    negative_keywords: list[str]
    risk_lexicon_pack_id: str
    evidence_pattern_pack_id: str
    false_positive_pack_id: str
    preferred_risk_families: list[str]
    preferred_zone_weights: list[ZoneWeight]
    preferred_effect_weights: list[EffectWeight]
    ontology_version: str = ZONE_ONTOLOGY_VERSION
    supported_zone_types: list[str] = field(default_factory=list)
    primary_review_types: list[str] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.supported_zone_types:
            self.supported_zone_types = [item.zone_type for item in self.preferred_zone_weights]
        if not self.primary_review_types:
            ordered: list[str] = []
            for zone_name in self.supported_zone_types:
                try:
                    zone_type = SemanticZoneType(zone_name)
                except ValueError:
                    continue
                review_type = ZONE_PRIMARY_REVIEW_TYPES.get(zone_type, "")
                if review_type and review_type not in ordered:
                    ordered.append(review_type)
            self.primary_review_types = ordered


RISK_FAMILY_TAG_MAP: dict[str, list[str]] = {
    "competition_restriction": ["goods", "structure"],
    "scoring_quantification": ["scoring"],
    "contract_performance": ["contract"],
    "template_conflict": ["template"],
    "procurement_structure": ["structure"],
    "personnel_boundary": ["personnel"],
    "sme_policy_consistency": ["policy"],
    "consistency": ["consistency"],
    "prudential": ["prudential"],
}

ACTIVATION_CONFIDENCE_THRESHOLDS: dict[str, float] = {
    "unknown": 0.58,
    "mixed": 0.44,
    "engineering": 0.4,
    "goods": 0.38,
    "service": 0.38,
}


RISK_LEXICON_PACKS: dict[str, RiskLexiconPack] = {
    "generic_goods_lexicon": RiskLexiconPack(
        pack_id="generic_goods_lexicon",
        terms_by_family={
            "competition_restriction": ["品牌", "原厂", "产地", "商标", "专利"],
            "scoring_quantification": ["评分", "得分", "样品", "检测报告"],
            "contract_performance": ["质保", "验收", "违约", "付款"],
            "template_conflict": ["声明函", "格式", "示例"],
        },
        anti_terms_by_family={
            "competition_restriction": ["服务", "运维", "驻场"],
        },
    ),
    "generic_service_lexicon": RiskLexiconPack(
        pack_id="generic_service_lexicon",
        terms_by_family={
            "personnel_boundary": ["团队", "人员", "驻场", "更换"],
            "contract_performance": ["验收", "付款", "解约", "违约"],
            "scoring_quantification": ["评分", "考核", "满意度"],
            "template_conflict": ["声明函", "格式", "示例"],
        },
        anti_terms_by_family={
            "personnel_boundary": ["家具", "货物"],
        },
    ),
    "mixed_procurement_lexicon": RiskLexiconPack(
        pack_id="mixed_procurement_lexicon",
        terms_by_family={
            "procurement_structure": ["货物", "服务", "采购包", "包件", "混合"],
            "consistency": ["一致", "不一致", "冲突", "混入"],
            "contract_performance": ["合同", "履约", "验收"],
        },
        anti_terms_by_family={
            "procurement_structure": ["单一", "纯货物", "纯服务"],
        },
    ),
    "furniture_lexicon": RiskLexiconPack(
        pack_id="furniture_lexicon",
        terms_by_family={
            "competition_restriction": ["家具", "课桌", "书桌", "档案柜", "会议桌", "茶几", "沙发", "床"],
            "scoring_quantification": ["样品", "检测报告", "环保", "封边条", "甲醛"],
            "contract_performance": ["安装", "验收", "质保", "售后"],
            "template_conflict": ["声明函", "格式", "示例"],
        },
        anti_terms_by_family={
            "competition_restriction": ["软件", "医疗", "系统", "平台", "接口", "数据库", "信息化", "摄像机", "网络", "服务器"],
        },
    ),
}


EVIDENCE_PATTERN_PACKS: dict[str, EvidencePatternPack] = {
    "generic_goods_patterns": EvidencePatternPack(
        pack_id="generic_goods_patterns",
        primary_patterns=[
            EvidencePattern(
                pattern_id="goods_brand_pattern",
                risk_family="competition_restriction",
                expected_zones=["technical", "business", "scoring"],
                expected_effects=["binding"],
                signal_groups=[["品牌", "原厂", "产地", "商标"]],
                anti_signal_groups=[["声明函", "格式", "示例"]],
            ),
            EvidencePattern(
                pattern_id="goods_score_pattern",
                risk_family="scoring_quantification",
                expected_zones=["scoring"],
                expected_effects=["binding"],
                signal_groups=[["评分", "得分", "样品", "检测报告"]],
            ),
        ],
    ),
    "generic_service_patterns": EvidencePatternPack(
        pack_id="generic_service_patterns",
        primary_patterns=[
            EvidencePattern(
                pattern_id="service_personnel_pattern",
                risk_family="personnel_boundary",
                expected_zones=["business", "contract", "scoring"],
                expected_effects=["binding"],
                signal_groups=[["团队", "人员", "驻场", "更换"]],
            ),
        ],
    ),
    "mixed_procurement_patterns": EvidencePatternPack(
        pack_id="mixed_procurement_patterns",
        primary_patterns=[
            EvidencePattern(
                pattern_id="mixed_structure_pattern",
                risk_family="procurement_structure",
                expected_zones=["administrative_info", "business", "contract", "mixed_or_uncertain"],
                expected_effects=["binding"],
                signal_groups=[["货物", "服务", "采购包", "包件"]],
            ),
        ],
    ),
    "furniture_patterns": EvidencePatternPack(
        pack_id="furniture_patterns",
        primary_patterns=[
            EvidencePattern(
                pattern_id="furniture_sample_pattern",
                risk_family="scoring_quantification",
                expected_zones=["scoring", "technical"],
                expected_effects=["binding"],
                signal_groups=[
                    ["家具", "课桌", "书桌", "档案柜", "会议桌", "茶几", "沙发", "床", "柜"],
                    ["样品", "检测报告", "环保", "封边条", "甲醛"],
                ],
            ),
            EvidencePattern(
                pattern_id="furniture_contract_pattern",
                risk_family="contract_performance",
                expected_zones=["contract", "business"],
                expected_effects=["binding"],
                signal_groups=[
                    ["家具", "课桌", "书桌", "档案柜", "会议桌", "茶几", "沙发", "床", "柜"],
                    ["安装", "验收", "质保", "售后"],
                ],
                anti_signal_groups=[["系统", "平台", "接口", "数据库", "信息化", "摄像机", "网络", "服务器", "运维"]],
            ),
        ],
    ),
}


FALSE_POSITIVE_PACKS: dict[str, FalsePositivePack] = {
    "generic_goods_fp": FalsePositivePack(
        pack_id="generic_goods_fp",
        anti_terms_by_family={
            "competition_restriction": ["服务", "运维", "驻场"],
        },
    ),
    "generic_service_fp": FalsePositivePack(
        pack_id="generic_service_fp",
        anti_terms_by_family={
            "personnel_boundary": ["家具", "货物"],
        },
    ),
    "mixed_procurement_fp": FalsePositivePack(
        pack_id="mixed_procurement_fp",
        anti_terms_by_family={
            "procurement_structure": ["单一", "纯货物", "纯服务"],
        },
    ),
    "furniture_fp": FalsePositivePack(
        pack_id="furniture_fp",
        anti_terms_by_family={
            "competition_restriction": [
                "软件",
                "系统",
                "平台",
                "接口",
                "数据库",
                "开发",
                "信息化",
                "数据迁移",
                "代码",
                "应用",
                "算法",
                "摄像机",
                "服务器",
                "网络",
                "运维",
            ],
        },
        penalty=0.22,
    ),
}


DOMAIN_PROFILES: dict[str, DomainProfile] = {
    "generic_goods": DomainProfile(
        profile_id="generic_goods",
        display_name="通用货物采购",
        version="v1",
        applies_to_procurement_kinds=["goods"],
        trigger_keywords=["货物", "设备", "原材料", "检测报告", "样品", "参数"],
        negative_keywords=["驻场", "运维", "服务"],
        risk_lexicon_pack_id="generic_goods_lexicon",
        evidence_pattern_pack_id="generic_goods_patterns",
        false_positive_pack_id="generic_goods_fp",
        preferred_risk_families=["competition_restriction", "scoring_quantification", "contract_performance", "template_conflict", "procurement_structure"],
        preferred_zone_weights=[
            ZoneWeight("technical", 0.9),
            ZoneWeight("scoring", 0.85),
            ZoneWeight("contract", 0.7),
            ZoneWeight("template", 0.45),
            ZoneWeight("business", 0.6),
        ],
        preferred_effect_weights=[
            EffectWeight("binding", 1.0),
            EffectWeight("policy_background", 0.5),
            EffectWeight("template", 0.2),
            EffectWeight("example", 0.2),
            EffectWeight("reference_only", 0.15),
        ],
        notes="面向通用货物采购场景的基础 profile。",
    ),
    "generic_service": DomainProfile(
        profile_id="generic_service",
        display_name="通用服务采购",
        version="v1",
        applies_to_procurement_kinds=["service"],
        trigger_keywords=["服务", "运维", "驻场", "实施", "售后", "人员"],
        negative_keywords=["货物", "家具"],
        risk_lexicon_pack_id="generic_service_lexicon",
        evidence_pattern_pack_id="generic_service_patterns",
        false_positive_pack_id="generic_service_fp",
        preferred_risk_families=["personnel_boundary", "contract_performance", "scoring_quantification", "template_conflict", "procurement_structure"],
        preferred_zone_weights=[
            ZoneWeight("business", 0.95),
            ZoneWeight("contract", 0.85),
            ZoneWeight("scoring", 0.55),
            ZoneWeight("template", 0.35),
        ],
        preferred_effect_weights=[
            EffectWeight("binding", 1.0),
            EffectWeight("policy_background", 0.45),
            EffectWeight("template", 0.2),
            EffectWeight("reference_only", 0.15),
        ],
        notes="面向通用服务采购场景的基础 profile。",
    ),
    "mixed_procurement": DomainProfile(
        profile_id="mixed_procurement",
        display_name="混合采购",
        version="v1",
        applies_to_procurement_kinds=["mixed"],
        trigger_keywords=["货物", "服务", "采购包", "包件", "混合"],
        negative_keywords=["纯货物", "纯服务"],
        risk_lexicon_pack_id="mixed_procurement_lexicon",
        evidence_pattern_pack_id="mixed_procurement_patterns",
        false_positive_pack_id="mixed_procurement_fp",
        preferred_risk_families=["procurement_structure", "consistency", "contract_performance", "scoring_quantification", "template_conflict"],
        preferred_zone_weights=[
            ZoneWeight("administrative_info", 0.7),
            ZoneWeight("business", 0.65),
            ZoneWeight("contract", 0.7),
            ZoneWeight("mixed_or_uncertain", 0.55),
        ],
        preferred_effect_weights=[
            EffectWeight("binding", 1.0),
            EffectWeight("template", 0.25),
            EffectWeight("reference_only", 0.15),
        ],
        notes="用于货物与服务并存或边界不清的混合采购场景。",
    ),
    "furniture": DomainProfile(
        profile_id="furniture",
        display_name="家具采购",
        version="v1",
        applies_to_procurement_kinds=["goods"],
        trigger_keywords=["家具", "课桌", "书桌", "档案柜", "会议桌", "茶几", "沙发", "床", "柜"],
        negative_keywords=["软件", "医疗", "驻场"],
        risk_lexicon_pack_id="furniture_lexicon",
        evidence_pattern_pack_id="furniture_patterns",
        false_positive_pack_id="furniture_fp",
        preferred_risk_families=["competition_restriction", "scoring_quantification", "contract_performance", "template_conflict", "procurement_structure"],
        preferred_zone_weights=[
            ZoneWeight("technical", 1.0),
            ZoneWeight("scoring", 0.9),
            ZoneWeight("contract", 0.8),
            ZoneWeight("template", 0.55),
            ZoneWeight("business", 0.7),
        ],
        preferred_effect_weights=[
            EffectWeight("binding", 1.0),
            EffectWeight("template", 0.25),
            EffectWeight("example", 0.2),
            EffectWeight("reference_only", 0.15),
        ],
        notes="家具类采购的高频样本 profile，重点覆盖样品、检测报告、尺寸参数和安装验收。",
    ),
}


def get_domain_profile(profile_id: str) -> DomainProfile | None:
    return DOMAIN_PROFILES.get(profile_id)


def build_document_profile(
    text: str,
    extracted_clauses: list[ExtractedClause],
    *,
    document_id: str = "",
    source_path: str = "",
) -> DocumentProfile:
    profile = DocumentProfile(
        document_id=document_id or source_path or "unknown-document",
        source_path=source_path,
        procurement_kind=_infer_procurement_kind(text, extracted_clauses),
        procurement_kind_confidence=0.0,
    )
    profile.dominant_zones = _build_zone_stats(extracted_clauses)
    profile.effect_distribution = _build_effect_stats(extracted_clauses)
    profile.clause_semantic_distribution = _build_clause_semantic_stats(extracted_clauses)
    profile.structure_flags = _build_structure_flags(text, extracted_clauses, profile.dominant_zones, profile.effect_distribution)
    profile.quality_flags = _build_quality_flags(profile)
    profile.unknown_structure_flags = _build_unknown_structure_flags(profile)
    profile.representative_anchors = _build_representative_anchors(extracted_clauses)

    profile.domain_profile_candidates = match_domain_profiles(profile, text=text, extracted_clauses=extracted_clauses)
    profile.procurement_kind_confidence = _procurement_kind_confidence(profile.procurement_kind, extracted_clauses, text)
    profile.routing_mode, profile.routing_reasons = _build_routing_policy(profile)
    profile.risk_activation_hints = _build_profile_activation_hints(profile)
    profile.summary = _build_profile_summary(profile)
    return profile


def match_domain_profiles(
    profile: DocumentProfile,
    *,
    text: str = "",
    extracted_clauses: list[ExtractedClause] | None = None,
    limit: int = 3,
) -> list[DomainProfileCandidate]:
    extracted_clauses = extracted_clauses or []
    candidates: list[DomainProfileCandidate] = []
    for domain_profile in DOMAIN_PROFILES.values():
        score, reasons = _score_domain_profile(domain_profile, profile, text, extracted_clauses)
        if score <= 0:
            continue
        candidates.append(
            DomainProfileCandidate(
                profile_id=domain_profile.profile_id,
                confidence=round(min(0.99, score), 3),
                reasons=reasons,
            )
        )
    if not candidates:
        candidates = _build_fallback_domain_candidates(profile, text, extracted_clauses)
    candidates.sort(key=lambda item: item.confidence, reverse=True)
    return candidates[:limit]


def profile_activation_tags(profile: DocumentProfile) -> set[str]:
    tags: set[str] = set()
    threshold = _activation_confidence_threshold(profile)
    for candidate in profile.domain_profile_candidates:
        if candidate.confidence < threshold:
            continue
        domain_profile = DOMAIN_PROFILES.get(candidate.profile_id)
        if not domain_profile:
            continue
        tags.update(_families_to_tags(domain_profile.preferred_risk_families))
        if domain_profile.profile_id == "furniture":
            tags.add("furniture")
        if domain_profile.profile_id == "generic_goods":
            tags.add("goods")
        if domain_profile.profile_id == "generic_service":
            tags.add("service")
        if domain_profile.profile_id == "mixed_procurement":
            tags.update({"structure", "consistency"})
    if profile.procurement_kind == "unknown":
        tags.difference_update({"goods", "service", "furniture", "structure"})
    if profile.procurement_kind == "goods":
        tags.add("goods")
    elif profile.procurement_kind == "service":
        tags.add("service")
    elif profile.procurement_kind == "mixed":
        tags.update({"structure", "consistency"})
    elif profile.procurement_kind == "unknown":
        tags.add("unknown")
    if "heavy_scoring_tables" in profile.structure_flags:
        tags.add("scoring")
    if "heavy_contract_terms" in profile.structure_flags:
        tags.add("contract")
    if "heavy_template_pollution" in profile.structure_flags:
        tags.add("template")
    if "heavy_appendix_reference" in profile.structure_flags:
        tags.add("template")
    if "mixed_structure_signals" in profile.structure_flags:
        tags.update({"structure", "consistency"})
    return tags


def _score_domain_profile(
    domain_profile: DomainProfile,
    profile: DocumentProfile,
    text: str,
    extracted_clauses: list[ExtractedClause],
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    haystack = " ".join([text, " ".join(clause.content for clause in extracted_clauses[:8])])
    if profile.procurement_kind in domain_profile.applies_to_procurement_kinds:
        score += 0.22
        reasons.append(f"procurement_kind={profile.procurement_kind}")
    if any(token in text for token in domain_profile.trigger_keywords):
        score += 0.18
        reasons.append("trigger_keyword_hit")
    if any(token in text for token in domain_profile.negative_keywords):
        score -= 0.08
        reasons.append("negative_keyword_hit")

    zone_index = {item.zone_type: item for item in profile.dominant_zones}
    for zone_weight in domain_profile.preferred_zone_weights:
        zone_stat = zone_index.get(zone_weight.zone_type)
        if zone_stat and zone_stat.ratio > 0:
            score += min(0.18, zone_stat.ratio * zone_weight.weight)
            reasons.append(f"zone:{zone_weight.zone_type}")

    effect_index = {item.effect_tag: item for item in profile.effect_distribution}
    for effect_weight in domain_profile.preferred_effect_weights:
        effect_stat = effect_index.get(effect_weight.effect_tag)
        if effect_stat and effect_stat.ratio > 0:
            score += min(0.08, effect_stat.ratio * effect_weight.weight * 0.2)
            reasons.append(f"effect:{effect_weight.effect_tag}")

    pattern_pack = EVIDENCE_PATTERN_PACKS.get(domain_profile.evidence_pattern_pack_id)
    if pattern_pack and domain_profile.profile_id != "furniture":
        if _matches_any_pattern(pattern_pack.primary_patterns, profile, text, extracted_clauses):
            score += 0.2
            reasons.append("primary_pattern_hit")
        if _matches_any_pattern(pattern_pack.supporting_patterns, profile, text, extracted_clauses):
            score += 0.08
            reasons.append("supporting_pattern_hit")
        if _matches_any_pattern(pattern_pack.weak_patterns, profile, text, extracted_clauses):
            score += 0.04
            reasons.append("weak_pattern_hit")

    lexicon_pack = RISK_LEXICON_PACKS.get(domain_profile.risk_lexicon_pack_id)
    if lexicon_pack:
        if _lexicon_hits_family(lexicon_pack, "competition_restriction", text, extracted_clauses):
            score += 0.1
            reasons.append("lexicon:competition_restriction")
        if _lexicon_hits_family(lexicon_pack, "personnel_boundary", text, extracted_clauses):
            score += 0.1
            reasons.append("lexicon:personnel_boundary")
        if _lexicon_hits_family(lexicon_pack, "template_conflict", text, extracted_clauses):
            score += 0.05
            reasons.append("lexicon:template_conflict")

    false_positive_pack = FALSE_POSITIVE_PACKS.get(domain_profile.false_positive_pack_id)
    if false_positive_pack:
        if any(
            token in haystack
            for family_terms in false_positive_pack.anti_terms_by_family.values()
            for token in family_terms
        ):
            score -= false_positive_pack.penalty
            reasons.append(f"false_positive:{false_positive_pack.pack_id}")

    if domain_profile.profile_id == "furniture":
        furniture_terms = ["家具", "课桌", "书桌", "档案柜", "会议桌", "茶几", "沙发", "床", "柜"]
        furniture_vocab_hit = sum(1 for token in furniture_terms if token in haystack) >= 1
        if furniture_vocab_hit and sum(1 for token in furniture_terms if token in text) >= 2:
            score += 0.12
            reasons.append("furniture_vocab_cluster")
        if profile.procurement_kind != "goods":
            score -= 0.12
            reasons.append("furniture_non_goods_penalty")
        if any(token in haystack for token in ["系统", "平台", "接口", "数据库", "信息化", "摄像机", "服务器", "网络", "运维"]):
            score -= 0.14
            reasons.append("furniture_it_anti_signal")
        if furniture_vocab_hit and _matches_any_pattern(
            EVIDENCE_PATTERN_PACKS[domain_profile.evidence_pattern_pack_id].primary_patterns,
            profile,
            text,
            extracted_clauses,
        ):
            score += 0.2
            reasons.append("primary_pattern_hit")
        if furniture_vocab_hit and "heavy_scoring_tables" in profile.structure_flags:
            score += 0.08
            reasons.append("furniture_scoring_tables")
        return score, reasons

    return score, reasons


def _matches_any_pattern(
    patterns: list[EvidencePattern],
    profile: DocumentProfile,
    text: str,
    extracted_clauses: list[ExtractedClause],
) -> bool:
    if not patterns:
        return False
    clauses_text = " ".join(
        filter(
            None,
            [
                text,
                " ".join(anchor for anchor in profile.representative_anchors if anchor),
                " ".join(clause.content for clause in extracted_clauses[:8]),
            ],
        )
    )
    for pattern in patterns:
        if pattern.expected_zones and not any(zone.zone_type in pattern.expected_zones for zone in profile.dominant_zones):
            continue
        if pattern.expected_effects and not any(effect.effect_tag in pattern.expected_effects for effect in profile.effect_distribution):
            continue
        if pattern.signal_groups and all(
            any(token in clauses_text for token in group)
            for group in pattern.signal_groups
        ):
            if pattern.anti_signal_groups and any(
                any(token in clauses_text for token in group)
                for group in pattern.anti_signal_groups
            ):
                continue
            return True
    return False


def _lexicon_hits_family(
    pack: RiskLexiconPack,
    family: str,
    text: str,
    extracted_clauses: list[ExtractedClause],
) -> bool:
    terms = pack.terms_by_family.get(family, [])
    anti_terms = pack.anti_terms_by_family.get(family, [])
    haystack = " ".join([text, " ".join(clause.content for clause in extracted_clauses[:8])])
    if anti_terms and any(token in haystack for token in anti_terms):
        return False
    return any(token in haystack for token in terms)


def _infer_procurement_kind(text: str, extracted_clauses: list[ExtractedClause]) -> str:
    haystack = " ".join([text, " ".join(clause.content for clause in extracted_clauses[:8])])
    goods_hits = sum(1 for token in ["货物", "家具", "设备", "课桌", "书桌", "档案柜", "会议桌", "茶几", "沙发", "床"] if token in haystack)
    service_hits = sum(1 for token in ["服务", "运维", "驻场", "实施", "售后", "人员"] if token in haystack)
    engineering_hits = sum(1 for token in ["工程", "施工", "建设"] if token in haystack)
    if goods_hits == 0 and service_hits == 0 and engineering_hits == 0:
        return "unknown"
    if goods_hits > service_hits and goods_hits >= engineering_hits:
        return "goods"
    if service_hits > goods_hits and service_hits >= engineering_hits:
        return "service"
    if engineering_hits > goods_hits and engineering_hits >= service_hits:
        return "engineering"
    return "mixed"


def _procurement_kind_confidence(procurement_kind: str, extracted_clauses: list[ExtractedClause], text: str) -> float:
    haystack = " ".join([text, " ".join(clause.content for clause in extracted_clauses[:8])])
    if procurement_kind == "goods":
        return min(0.95, 0.42 + 0.05 * sum(1 for token in ["货物", "家具", "设备", "课桌", "书桌", "档案柜"] if token in haystack))
    if procurement_kind == "service":
        return min(0.95, 0.42 + 0.05 * sum(1 for token in ["服务", "运维", "驻场", "实施", "售后"] if token in haystack))
    if procurement_kind == "engineering":
        return min(0.9, 0.4 + 0.08 * sum(1 for token in ["工程", "施工", "建设"] if token in haystack))
    if procurement_kind == "mixed":
        return 0.55
    return 0.25


def _build_zone_stats(extracted_clauses: list[ExtractedClause]) -> list[ZoneStat]:
    total = len(extracted_clauses) or 1
    counts = Counter(clause.semantic_zone.value for clause in extracted_clauses)
    return [
        ZoneStat(zone_type=zone, node_count=count, unit_count=count, ratio=round(count / total, 3))
        for zone, count in counts.most_common()
    ]


def _build_effect_stats(extracted_clauses: list[ExtractedClause]) -> list[EffectStat]:
    total = len(extracted_clauses) or 1
    counter: Counter[str] = Counter()
    for clause in extracted_clauses:
        if clause.effect_tags:
            for tag in clause.effect_tags:
                counter[tag.value] += 1
        else:
            counter["binding"] += 1
    return [
        EffectStat(effect_tag=tag, unit_count=count, ratio=round(count / total, 3))
        for tag, count in counter.most_common()
    ]


def _build_clause_semantic_stats(extracted_clauses: list[ExtractedClause]) -> list[ClauseSemanticStat]:
    total = len(extracted_clauses) or 1
    counts = Counter(_clause_semantic_label(clause) for clause in extracted_clauses)
    return [
        ClauseSemanticStat(clause_semantic_type=name, unit_count=count, ratio=round(count / total, 3))
        for name, count in counts.most_common()
    ]


def _clause_semantic_label(clause: ExtractedClause) -> str:
    clause_semantic_type = getattr(clause, "clause_semantic_type", None)
    if clause_semantic_type is not None:
        return getattr(clause_semantic_type, "value", str(clause_semantic_type))
    clause_role = getattr(clause, "clause_role", None)
    if clause_role is not None:
        return f"role:{getattr(clause_role, 'value', str(clause_role))}"
    return "unknown_clause"


def _build_structure_flags(
    text: str,
    extracted_clauses: list[ExtractedClause],
    dominant_zones: list[ZoneStat],
    effect_distribution: list[EffectStat],
) -> list[str]:
    flags: list[str] = []
    zone_ratio = {item.zone_type: item.ratio for item in dominant_zones}
    effect_ratio = {item.effect_tag: item.ratio for item in effect_distribution}
    if zone_ratio.get("scoring", 0.0) >= 0.12:
        flags.append("heavy_scoring_tables")
    if zone_ratio.get("template", 0.0) >= 0.12:
        flags.append("heavy_template_pollution")
    if zone_ratio.get("appendix_reference", 0.0) >= 0.08:
        flags.append("heavy_appendix_reference")
    if zone_ratio.get("contract", 0.0) >= 0.1:
        flags.append("heavy_contract_terms")
    if zone_ratio.get("mixed_or_uncertain", 0.0) >= 0.35:
        flags.append("mixed_structure_signals")
    if any("|" in clause.content for clause in extracted_clauses) or text.count("|") >= 8:
        flags.append("fragmented_table_text")
    if any(token in text for token in ["目录", "附表", "详见附件"]):
        flags.append("catalog_noise_present")
    if effect_ratio.get("template", 0.0) >= 0.1 or effect_ratio.get("reference_only", 0.0) >= 0.1:
        flags.append("template_ratio_high")
    return list(dict.fromkeys(flags))


def _build_quality_flags(profile: DocumentProfile) -> list[str]:
    flags: list[str] = []
    if "heavy_scoring_tables" in profile.structure_flags and "heavy_template_pollution" in profile.structure_flags:
        flags.append("table_anchor_unstable")
    if "fragmented_table_text" in profile.structure_flags:
        flags.append("long_flattened_rows")
    if profile.procurement_kind == "mixed":
        flags.append("cross_zone_clause_conflict")
    if not profile.domain_profile_candidates:
        flags.append("low_domain_match_confidence")
    return flags


def _build_unknown_structure_flags(profile: DocumentProfile) -> list[str]:
    flags: list[str] = []
    if profile.procurement_kind == "unknown":
        flags.append("unknown_procurement_kind")
    if not profile.domain_profile_candidates:
        flags.append("unknown_domain_lexicon_gap")
    if "heavy_template_pollution" in profile.structure_flags:
        flags.append("unknown_appendix_like_block")
    if "heavy_scoring_tables" in profile.structure_flags and "heavy_contract_terms" in profile.structure_flags:
        flags.append("mixed_scoring_contract_cluster")
    return list(dict.fromkeys(flags))


def _build_representative_anchors(extracted_clauses: list[ExtractedClause]) -> list[str]:
    anchors: list[str] = []
    for clause in extracted_clauses:
        if clause.source_anchor and clause.source_anchor not in anchors:
            anchors.append(clause.source_anchor)
        if len(anchors) >= 6:
            break
    return anchors


def _build_profile_activation_hints(profile: DocumentProfile) -> list[str]:
    hints: set[str] = set(profile_activation_tags(profile))
    if profile.procurement_kind == "unknown":
        hints.add("unknown_document")
    if profile.routing_mode == "unknown_conservative":
        hints.add("unknown_document_first")
    if profile.procurement_kind == "mixed":
        hints.update({"structure", "consistency"})
    if "heavy_template_pollution" in profile.structure_flags:
        hints.add("template")
    if profile.unknown_structure_flags:
        hints.update(profile.unknown_structure_flags)
    return sorted(hints)


def _build_routing_policy(profile: DocumentProfile) -> tuple[str, list[str]]:
    is_unknownish = profile.procurement_kind in {"unknown", "mixed"} or bool(profile.unknown_structure_flags)
    if not is_unknownish:
        return "standard", []
    reasons: list[str] = []
    if profile.procurement_kind == "unknown":
        reasons.append("unknown_procurement_kind")
    if profile.procurement_kind_confidence < 0.7:
        reasons.append("low_procurement_kind_confidence")
    reasons.extend(profile.unknown_structure_flags[:3])
    if "table_anchor_unstable" in profile.quality_flags:
        reasons.append("table_anchor_unstable")
    if not reasons:
        return "standard", []
    return "unknown_conservative", list(dict.fromkeys(reasons))


def _build_profile_summary(profile: DocumentProfile) -> str:
    candidates = ", ".join(
        f"{item.profile_id}:{item.confidence:.2f}" for item in profile.domain_profile_candidates[:3]
    ) or "none"
    return (
        f"procurement_kind={profile.procurement_kind}; "
        f"routing_mode={profile.routing_mode}; "
        f"candidates={candidates}; "
        f"flags={', '.join(profile.structure_flags) or 'none'}"
    )


def _families_to_tags(families: list[str]) -> set[str]:
    tags: set[str] = set()
    for family in families:
        tags.update(RISK_FAMILY_TAG_MAP.get(family, []))
    return tags


def _activation_confidence_threshold(profile: DocumentProfile) -> float:
    return ACTIVATION_CONFIDENCE_THRESHOLDS.get(profile.procurement_kind, 0.38)


def _build_fallback_domain_candidates(
    profile: DocumentProfile,
    text: str,
    extracted_clauses: list[ExtractedClause],
) -> list[DomainProfileCandidate]:
    candidates: list[DomainProfileCandidate] = []
    if profile.procurement_kind == "unknown":
        candidates.append(
            DomainProfileCandidate(
                profile_id="generic_goods",
                confidence=0.2,
                reasons=["unknown_procurement_kind", "保守回退到通用货物经验包"],
            )
        )
        candidates.append(
            DomainProfileCandidate(
                profile_id="generic_service",
                confidence=0.18,
                reasons=["unknown_procurement_kind", "保守回退到通用服务经验包"],
            )
        )
    if "mixed_structure_signals" in profile.structure_flags:
        candidates.append(
            DomainProfileCandidate(
                profile_id="mixed_procurement",
                confidence=0.22,
                reasons=["mixed_structure_signals", "保守回退到混合采购经验包"],
            )
        )
    if any(clause.semantic_zone == SemanticZoneType.scoring for clause in extracted_clauses):
        candidates.append(
            DomainProfileCandidate(
                profile_id="generic_goods",
                confidence=0.16,
                reasons=["评分区信号弱", "回退到通用货物经验包"],
            )
        )

    deduped: list[DomainProfileCandidate] = []
    seen: set[str] = set()
    for candidate in sorted(candidates, key=lambda item: item.confidence, reverse=True):
        if candidate.profile_id in seen:
            continue
        seen.add(candidate.profile_id)
        deduped.append(candidate)
    return deduped

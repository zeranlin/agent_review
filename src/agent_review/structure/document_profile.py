from __future__ import annotations

from collections import Counter

from ..external_data import match_external_domain_profile_candidates
from ..models import (
    ClauseSemanticStat,
    DocumentProfile,
    DomainProfileCandidate,
    EffectStat,
    NodeType,
    ParseResult,
    ZoneStat,
)
from ..ontology import ClauseSemanticType, EffectTag, SemanticZoneType, ZONE_PRIMARY_REVIEW_TYPES


_PROCUREMENT_KIND_TOKENS: dict[str, list[str]] = {
    "goods": ["货物", "家具", "设备", "器材", "课桌", "书桌", "桌椅", "柜", "床", "讲桌", "办公桌", "沙发"],
    "service": ["服务", "运维", "驻场", "保洁", "培训", "维护", "实施", "咨询", "巡检"],
    "engineering": ["工程", "施工", "改造", "装修", "装饰", "建设", "土建", "迁改"],
}

_ZONE_IMPORTANCE: dict[SemanticZoneType, int] = {
    SemanticZoneType.scoring: 100,
    SemanticZoneType.qualification: 95,
    SemanticZoneType.contract: 90,
    SemanticZoneType.template: 85,
    SemanticZoneType.appendix_reference: 80,
    SemanticZoneType.technical: 70,
    SemanticZoneType.business: 65,
    SemanticZoneType.policy_explanation: 35,
    SemanticZoneType.administrative_info: 30,
    SemanticZoneType.mixed_or_uncertain: 20,
    SemanticZoneType.catalog_or_navigation: 10,
    SemanticZoneType.public_copy_or_noise: 5,
}


def build_document_profile(
    parse_result: ParseResult,
    document_name: str,
) -> DocumentProfile:
    procurement_kind, procurement_confidence, kind_reasons = _infer_procurement_kind(parse_result)
    zone_stats = _build_zone_stats(parse_result)
    effect_stats = _build_effect_stats(parse_result)
    clause_stats = _build_clause_stats(parse_result)
    candidates = _build_domain_profile_candidates(
        procurement_kind,
        parse_result,
        kind_reasons,
        zone_stats,
        effect_stats,
        clause_stats,
    )
    quality_flags = _build_quality_flags(parse_result, zone_stats, effect_stats, clause_stats)
    structure_flags = _build_structure_flags(
        procurement_kind,
        parse_result,
        zone_stats,
        effect_stats,
        clause_stats,
        quality_flags,
    )
    risk_activation_hints = _build_risk_activation_hints(
        procurement_kind,
        structure_flags,
        quality_flags,
        zone_stats,
        effect_stats,
    )
    unknown_structure_flags = _build_unknown_structure_flags(procurement_kind, structure_flags, zone_stats, quality_flags)
    parser_semantic_trace = parse_result.parser_semantic_trace
    routing_mode, routing_reasons = _build_routing_policy(
        procurement_kind=procurement_kind,
        procurement_confidence=procurement_confidence,
        quality_flags=quality_flags,
        unknown_structure_flags=unknown_structure_flags,
        parser_semantic_trace=parse_result.parser_semantic_trace,
    )
    anchors = _build_representative_anchors(parse_result, zone_stats)
    summary = _build_summary(
        document_name=document_name,
        procurement_kind=procurement_kind,
        routing_mode=routing_mode,
        zone_stats=zone_stats,
        candidates=candidates,
        structure_flags=structure_flags,
        quality_flags=quality_flags,
        risk_activation_hints=risk_activation_hints,
    )
    return DocumentProfile(
        document_id=parse_result.source_path or document_name,
        source_path=parse_result.source_path or document_name,
        procurement_kind=procurement_kind,
        procurement_kind_confidence=procurement_confidence,
        routing_mode=routing_mode,
        routing_reasons=routing_reasons,
        domain_profile_candidates=candidates,
        dominant_zones=zone_stats,
        effect_distribution=effect_stats,
        clause_semantic_distribution=clause_stats,
        structure_flags=structure_flags,
        risk_activation_hints=risk_activation_hints,
        quality_flags=quality_flags,
        unknown_structure_flags=unknown_structure_flags,
        parser_semantic_assist_activated=bool(parser_semantic_trace and parser_semantic_trace.activated),
        parser_semantic_assist_reviewed_count=parser_semantic_trace.reviewed_count if parser_semantic_trace else 0,
        parser_semantic_assist_applied_count=parser_semantic_trace.applied_count if parser_semantic_trace else 0,
        primary_review_types=_build_primary_review_types(zone_stats),
        representative_anchors=anchors,
        summary=summary,
    )


def _infer_procurement_kind(parse_result: ParseResult) -> tuple[str, float, list[str]]:
    zone_by_node = {item.node_id: item.zone_type for item in parse_result.semantic_zones}
    scores: dict[str, float] = {kind: 0.0 for kind in _PROCUREMENT_KIND_TOKENS}
    reasons: dict[str, list[str]] = {kind: [] for kind in _PROCUREMENT_KIND_TOKENS}
    weak_only = True

    for node in parse_result.document_nodes:
        fragment = " ".join(part for part in [node.title, node.text] if part).strip()
        if not fragment:
            continue
        zone_type = zone_by_node.get(node.node_id, SemanticZoneType.mixed_or_uncertain)
        weight = _kind_signal_weight(zone_type, node.node_type)
        if weight >= 0.7:
            weak_only = False
        _accumulate_kind_scores(fragment, weight, scores, reasons, context=f"{zone_type.value}/{node.node_type.value}")

    for unit in parse_result.clause_units:
        if not unit.text:
            continue
        weight = _kind_signal_weight(unit.zone_type, None, unit.effect_tags)
        if weight >= 0.7:
            weak_only = False
        _accumulate_kind_scores(
            unit.text,
            weight,
            scores,
            reasons,
            context=f"{unit.zone_type.value}/{unit.clause_semantic_type.value}",
        )

    best_kind = max(scores, key=scores.get, default="unknown")
    best_score = scores.get(best_kind, 0.0)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    second_kind, second_score = ranked[1] if len(ranked) > 1 else ("unknown", 0.0)

    if best_score <= 0.0:
        return "unknown", 0.25, ["未识别到稳定采购类型信号"]
    if weak_only and best_score < 1.0:
        return "unknown", 0.31, [f"仅在弱结构区识别到 {best_kind} 相关信号"]
    if best_score < 1.2 and second_score > 0.8 and (best_score - second_score) < 0.35:
        mixed_kinds = [kind for kind, score in ranked[:2] if score > 0]
        return "mixed", min(0.78, 0.56 + 0.05 * len(mixed_kinds)), [f"同时识别到 {', '.join(mixed_kinds)} 信号"]

    best_reasons = reasons.get(best_kind, [])
    confidence = min(0.95, 0.48 + 0.10 * best_score)
    if second_score > 0.9 and (best_score - second_score) < 0.8:
        confidence = min(confidence, 0.76)
    if not best_reasons:
        best_reasons = [f"识别到 {best_kind} 相关信号"]
    return best_kind, confidence, best_reasons[:3]


def _build_zone_stats(parse_result: ParseResult) -> list[ZoneStat]:
    zone_by_node = {item.node_id: item.zone_type for item in parse_result.semantic_zones}
    node_counter: Counter[SemanticZoneType] = Counter()
    for node in parse_result.document_nodes:
        zone = zone_by_node.get(node.node_id)
        if zone is None:
            continue
        node_counter[zone] += 1

    unit_counter: Counter[SemanticZoneType] = Counter(unit.zone_type for unit in parse_result.clause_units)
    total_units = max(1, len(parse_result.clause_units))
    stats = []
    for zone in sorted(set(node_counter) | set(unit_counter), key=lambda item: (-unit_counter[item], item.value)):
        unit_count = unit_counter[zone]
        node_count = node_counter[zone]
        if unit_count == 0 and node_count == 0:
            continue
        stats.append(
            ZoneStat(
                zone_type=zone,
                node_count=node_count,
                unit_count=unit_count,
                ratio=round(unit_count / total_units, 4),
            )
        )
    return stats


def _build_effect_stats(parse_result: ParseResult) -> list[EffectStat]:
    effect_counter: Counter[EffectTag] = Counter()
    for unit in parse_result.clause_units:
        effect_counter.update(unit.effect_tags or [EffectTag.binding])
    total_units = max(1, len(parse_result.clause_units))
    stats = [
        EffectStat(effect_tag=tag, unit_count=count, ratio=round(count / total_units, 4))
        for tag, count in effect_counter.most_common()
    ]
    return stats


def _build_clause_stats(parse_result: ParseResult) -> list[ClauseSemanticStat]:
    clause_counter: Counter[ClauseSemanticType] = Counter(unit.clause_semantic_type for unit in parse_result.clause_units)
    total_units = max(1, len(parse_result.clause_units))
    return [
        ClauseSemanticStat(
            clause_semantic_type=clause_type,
            unit_count=count,
            ratio=round(count / total_units, 4),
        )
        for clause_type, count in clause_counter.most_common()
    ]


def _build_domain_profile_candidates(
    procurement_kind: str,
    parse_result: ParseResult,
    kind_reasons: list[str],
    zone_stats: list[ZoneStat],
    effect_stats: list[EffectStat],
    clause_stats: list[ClauseSemanticStat],
) -> list[DomainProfileCandidate]:
    text = " ".join(
        [parse_result.text] + [node.title for node in parse_result.document_nodes[:80]] + [node.text for node in parse_result.document_nodes[:80]]
    )
    candidates: list[DomainProfileCandidate] = []
    if procurement_kind == "mixed":
        candidates.append(DomainProfileCandidate("mixed_procurement", 0.86, kind_reasons + ["货物与服务信号并存"]))
    elif procurement_kind == "goods":
        candidates.append(DomainProfileCandidate("generic_goods", 0.84, kind_reasons))
    elif procurement_kind == "service":
        candidates.append(DomainProfileCandidate("generic_service", 0.84, kind_reasons))
    elif procurement_kind == "engineering":
        candidates.append(DomainProfileCandidate("generic_engineering", 0.82, kind_reasons))
    else:
        candidates.append(DomainProfileCandidate("generic_goods", 0.38, kind_reasons))
        candidates.append(DomainProfileCandidate("generic_service", 0.36, kind_reasons))

    furniture_candidate = _build_furniture_candidate(procurement_kind, text)
    if furniture_candidate is not None:
        candidates.append(furniture_candidate)

    if _zone_ratio(zone_stats, SemanticZoneType.scoring) > 0.15:
        candidates.append(DomainProfileCandidate("scoring_heavy", 0.71, ["评分区密度较高"]))
    if _zone_ratio(zone_stats, SemanticZoneType.template) > 0.15:
        candidates.append(DomainProfileCandidate("template_heavy", 0.69, ["模板区密度较高"]))
    if _effect_ratio(effect_stats, EffectTag.reference_only) > 0.1:
        candidates.append(DomainProfileCandidate("appendix_heavy", 0.68, ["引用性条款较多"]))
    if _clause_ratio(clause_stats, ClauseSemanticType.contract_obligation) > 0.1:
        candidates.append(DomainProfileCandidate("contract_heavy", 0.65, ["合同条款较多"]))
    candidates.extend(
        match_external_domain_profile_candidates(
            text=text,
            procurement_kind=procurement_kind,
            limit=3,
        )
    )

    deduped: list[DomainProfileCandidate] = []
    seen: set[str] = set()
    for item in sorted(candidates, key=lambda x: x.confidence, reverse=True):
        if item.profile_id in seen:
            continue
        seen.add(item.profile_id)
        deduped.append(item)
    return deduped[:4]


def _build_furniture_candidate(procurement_kind: str, text: str) -> DomainProfileCandidate | None:
    strong_terms = ["家具", "课桌", "课桌椅", "书桌", "会议桌", "讲桌", "书柜", "档案柜", "沙发", "茶几"]
    support_terms = ["桌椅", "桌", "椅", "柜", "床", "办公桌", "储物柜"]
    anti_terms = ["系统", "平台", "接口", "数据库", "信息化", "软件", "摄像机", "服务器", "交换机", "网络", "运维"]

    if procurement_kind not in {"goods", "mixed"}:
        return None

    strong_hits = [token for token in strong_terms if token in text]
    support_hits = [token for token in support_terms if token in text]
    anti_hits = [token for token in anti_terms if token in text]

    if anti_hits and len(strong_hits) < 2:
        return None

    if len(strong_hits) >= 2:
        confidence = 0.9 if procurement_kind == "goods" else 0.78
        reasons = ["命中家具强词簇", f"家具词汇：{', '.join(strong_hits[:3])}"]
        return DomainProfileCandidate("furniture", confidence, reasons)

    if procurement_kind == "goods" and strong_hits and support_hits and not anti_hits:
        reasons = ["货物属性下命中家具词汇组合", f"家具词汇：{', '.join((strong_hits + support_hits)[:3])}"]
        return DomainProfileCandidate("furniture", 0.82, reasons)

    return None


def _build_structure_flags(
    procurement_kind: str,
    parse_result: ParseResult,
    zone_stats: list[ZoneStat],
    effect_stats: list[EffectStat],
    clause_stats: list[ClauseSemanticStat],
    quality_flags: list[str],
) -> list[str]:
    flags: list[str] = []
    appendix_node_count = sum(1 for node in parse_result.document_nodes if node.node_type == NodeType.appendix)
    catalog_node_count = sum(1 for node in parse_result.document_nodes if node.node_type == NodeType.catalog_entry)
    scoring_ratio = _zone_ratio(zone_stats, SemanticZoneType.scoring)
    template_ratio = _zone_ratio(zone_stats, SemanticZoneType.template)
    appendix_ratio = _zone_ratio(zone_stats, SemanticZoneType.appendix_reference)
    catalog_ratio = _zone_ratio(zone_stats, SemanticZoneType.catalog_or_navigation)
    contract_ratio = _zone_ratio(zone_stats, SemanticZoneType.contract)
    uncertain_ratio = _zone_ratio(zone_stats, SemanticZoneType.mixed_or_uncertain)

    if procurement_kind == "unknown":
        flags.append("unknown_document_first")
    if catalog_ratio > 0.12 or catalog_node_count >= 2:
        flags.append("catalog_navigation_heavy")
        flags.append("directory_driven_structure")
    if scoring_ratio > 0.18:
        flags.append("heavy_scoring_tables")
        flags.append("scoring_dense_structure")
    if template_ratio > 0.18:
        flags.append("heavy_template_pollution")
        flags.append("template_pollution")
    if appendix_ratio > 0.12 or appendix_node_count >= 2:
        flags.append("heavy_appendix_reference")
        flags.append("attachment_driven_structure")
    if contract_ratio > 0.12:
        flags.append("heavy_contract_terms")
    catalog_noise = (
        _effect_ratio(effect_stats, EffectTag.catalog) > 0.08
        or _zone_ratio(zone_stats, SemanticZoneType.catalog_or_navigation) > 0.08
        or "catalog_noise_high" in quality_flags
        or "catalog_navigation_high" in quality_flags
        or "non_body_structure_dominant" in quality_flags
    )
    if catalog_noise:
        flags.append("catalog_noise_present")
        flags.append("catalog_navigation_heavy")
        flags.append("directory_driven_structure")
    if len([item for item in zone_stats if item.ratio >= 0.12]) >= 2 or (
        scoring_ratio > 0.08 and (template_ratio > 0.08 or appendix_ratio > 0.08)
    ):
        flags.append("mixed_structure_signals")
    if uncertain_ratio > 0.25 or (procurement_kind == "unknown" and (scoring_ratio + template_ratio + appendix_ratio) > 0.35):
        flags.append("mixed_structure_uncertain")
    if any(len(node.text) > 260 for node in parse_result.document_nodes if node.node_type.value == "table_row"):
        flags.append("fragmented_table_text")
    if _clause_ratio(clause_stats, ClauseSemanticType.unknown_clause) > 0.35:
        flags.append("unknown_clause_heavy")
    return list(dict.fromkeys(flags))


def _build_risk_activation_hints(
    procurement_kind: str,
    structure_flags: list[str],
    quality_flags: list[str],
    zone_stats: list[ZoneStat],
    effect_stats: list[EffectStat],
) -> list[str]:
    from ..domain_profiles.catalog import profile_activation_tags

    hints: set[str] = set(profile_activation_tags(_profile_like(procurement_kind, structure_flags, zone_stats)))
    if procurement_kind == "unknown":
        hints.update({"unknown_document", "unknown_document_first"})
    if any(flag in quality_flags for flag in ["template_ratio_high", "reference_ratio_high", "catalog_noise_high", "non_body_structure_dominant"]):
        hints.add("unknown_document_first")
    if procurement_kind in {"goods", "mixed"}:
        hints.add("competition_restriction")
    if procurement_kind in {"service", "mixed"}:
        hints.add("contract_performance")
    if any(flag in structure_flags for flag in ["catalog_navigation_heavy", "directory_driven_structure", "catalog_first_structure"]) or "catalog_navigation_high" in quality_flags:
        hints.update({"catalog_navigation", "directory_navigation"})
    if _zone_ratio(zone_stats, SemanticZoneType.qualification) > 0.08:
        hints.add("qualification_scoring_boundary")
    if _zone_ratio(zone_stats, SemanticZoneType.scoring) > 0.08:
        hints.update({"scoring_quantification", "scoring_dense_structure"})
    if _zone_ratio(zone_stats, SemanticZoneType.policy_explanation) > 0.04 or _effect_ratio(effect_stats, EffectTag.policy_background) > 0.04:
        hints.add("sme_policy_consistency")
    if any(flag in structure_flags for flag in ["heavy_template_pollution", "template_pollution"]):
        hints.update({"template_conflict", "template_pollution"})
    if any(flag in structure_flags for flag in ["heavy_appendix_reference", "attachment_driven_structure"]):
        hints.update({"attachment_driven_structure", "template_conflict"})
    if "catalog_noise_present" in structure_flags or "catalog_noise_high" in quality_flags:
        hints.add("catalog_noise_present")
    if any(flag in structure_flags for flag in ["mixed_structure_signals", "mixed_structure_uncertain"]):
        hints.update({"structure", "consistency", "mixed_structure_uncertain"})
    if "non_body_structure_dominant" in quality_flags:
        hints.update({"template_conflict", "attachment_driven_structure", "catalog_noise_present"})
    return sorted(hints)


def _build_quality_flags(
    parse_result: ParseResult,
    zone_stats: list[ZoneStat],
    effect_stats: list[EffectStat],
    clause_stats: list[ClauseSemanticStat],
) -> list[str]:
    flags: list[str] = []
    scoring_ratio = _zone_ratio(zone_stats, SemanticZoneType.scoring)
    qualification_ratio = _zone_ratio(zone_stats, SemanticZoneType.qualification)
    technical_ratio = _zone_ratio(zone_stats, SemanticZoneType.technical)
    business_ratio = _zone_ratio(zone_stats, SemanticZoneType.business)
    contract_ratio = _zone_ratio(zone_stats, SemanticZoneType.contract)
    template_ratio = _zone_ratio(zone_stats, SemanticZoneType.template)
    appendix_ratio = _zone_ratio(zone_stats, SemanticZoneType.appendix_reference)
    catalog_ratio = _zone_ratio(zone_stats, SemanticZoneType.catalog_or_navigation)
    uncertain_ratio = _zone_ratio(zone_stats, SemanticZoneType.mixed_or_uncertain)
    template_node_count = _zone_node_count(zone_stats, SemanticZoneType.template)
    appendix_node_count = _zone_node_count(zone_stats, SemanticZoneType.appendix_reference)
    catalog_node_count = _zone_node_count(zone_stats, SemanticZoneType.catalog_or_navigation)
    body_ratio = qualification_ratio + technical_ratio + business_ratio + contract_ratio + scoring_ratio

    if _effect_ratio(effect_stats, EffectTag.template) > 0.18 or template_ratio > 0.18:
        flags.append("template_ratio_high")
    if _effect_ratio(effect_stats, EffectTag.reference_only) > 0.12 or appendix_ratio > 0.12:
        flags.append("reference_ratio_high")
    if _effect_ratio(effect_stats, EffectTag.catalog) > 0.08 or catalog_ratio > 0.08 or catalog_node_count >= 2:
        flags.append("catalog_noise_high")
    if catalog_ratio >= 0.08 or catalog_node_count >= 1:
        flags.append("catalog_navigation_high")
    if uncertain_ratio > 0.25:
        flags.append("mixed_zone_ratio_high")
    if _clause_ratio(clause_stats, ClauseSemanticType.unknown_clause) > 0.3:
        flags.append("unknown_clause_ratio_high")
    if (
        template_ratio > 0.08
        or appendix_ratio > 0.08
        or catalog_ratio > 0.08
        or catalog_node_count >= 1
        or _effect_ratio(effect_stats, EffectTag.reference_only) > 0.12
        or _clause_ratio(clause_stats, ClauseSemanticType.unknown_clause) > 0.3
    ) and (
        not parse_result.clause_units
        or uncertain_ratio > 0.25
        or _effect_ratio(effect_stats, EffectTag.reference_only) > 0.12
        or _clause_ratio(clause_stats, ClauseSemanticType.unknown_clause) > 0.3
    ):
        flags.append("weak_source_support")
    if (template_ratio > 0.18 or template_node_count >= 2) and (appendix_ratio > 0.08 or appendix_node_count >= 1):
        flags.append("template_appendix_mix_high")
    if (template_ratio + appendix_ratio + catalog_ratio) > max(0.35, body_ratio) and (
        template_ratio > 0.12 or appendix_ratio > 0.12 or catalog_ratio > 0.08
    ):
        flags.append("non_body_structure_dominant")
    if not parse_result.clause_units:
        flags.append("no_clause_units")
    return list(dict.fromkeys(flags))


def _build_unknown_structure_flags(
    procurement_kind: str,
    structure_flags: list[str],
    zone_stats: list[ZoneStat],
    quality_flags: list[str],
) -> list[str]:
    flags: list[str] = []
    is_unknownish = procurement_kind in {"unknown", "mixed"}
    template_ratio = _zone_ratio(zone_stats, SemanticZoneType.template)
    appendix_ratio = _zone_ratio(zone_stats, SemanticZoneType.appendix_reference)
    catalog_ratio = _zone_ratio(zone_stats, SemanticZoneType.catalog_or_navigation)
    template_node_count = _zone_node_count(zone_stats, SemanticZoneType.template)
    appendix_node_count = _zone_node_count(zone_stats, SemanticZoneType.appendix_reference)
    catalog_node_count = _zone_node_count(zone_stats, SemanticZoneType.catalog_or_navigation)
    body_ratio = (
        _zone_ratio(zone_stats, SemanticZoneType.qualification)
        + _zone_ratio(zone_stats, SemanticZoneType.technical)
        + _zone_ratio(zone_stats, SemanticZoneType.business)
        + _zone_ratio(zone_stats, SemanticZoneType.contract)
        + _zone_ratio(zone_stats, SemanticZoneType.scoring)
    )

    if procurement_kind == "unknown":
        flags.append("unknown_procurement_kind")
    if is_unknownish and "unknown_document_first" in structure_flags:
        flags.append("unknown_document_first")
    if is_unknownish and ("catalog_navigation_heavy" in structure_flags or catalog_ratio > 0.12 or catalog_node_count >= 2):
        flags.append("unknown_catalog_navigation")
    if is_unknownish and "attachment_driven_structure" in structure_flags:
        flags.append("unknown_attachment_driven_structure")
    if is_unknownish and ("scoring_dense_structure" in structure_flags or "heavy_scoring_tables" in structure_flags):
        flags.append("unknown_scoring_dense_structure")
    if is_unknownish and ("template_pollution" in structure_flags or "heavy_template_pollution" in structure_flags):
        flags.append("unknown_template_pollution")
    if is_unknownish and "catalog_noise_present" in structure_flags:
        flags.append("unknown_catalog_noise")
    if is_unknownish and ("weak_source_support" in quality_flags or "no_clause_units" in quality_flags):
        flags.append("unknown_low_clause_support")
    if is_unknownish and ("mixed_structure_signals" in structure_flags or "mixed_structure_uncertain" in structure_flags):
        flags.append("mixed_structure_uncertain")
    if is_unknownish and (template_ratio > 0.12 or template_node_count >= 2) and template_ratio >= max(appendix_ratio, catalog_ratio, body_ratio):
        flags.append("template_first_structure")
    if is_unknownish and (appendix_ratio > 0.12 or appendix_node_count >= 1) and appendix_ratio >= max(template_ratio, catalog_ratio, body_ratio):
        flags.append("attachment_first_structure")
    if is_unknownish and (catalog_ratio > 0.08 or catalog_node_count >= 2) and catalog_ratio >= max(template_ratio, appendix_ratio, body_ratio):
        flags.append("catalog_first_structure")
    if is_unknownish and (template_ratio + appendix_ratio + catalog_ratio) > max(0.35, body_ratio):
        flags.append("non_body_structure_dominant")
    if is_unknownish and _zone_ratio(zone_stats, SemanticZoneType.mixed_or_uncertain) > 0.4:
        flags.append("majority_uncertain_zone")
    if procurement_kind == "unknown" and flags == ["unknown_procurement_kind"]:
        flags.append("unknown_domain_gap")
    return flags


def _build_routing_policy(
    *,
    procurement_kind: str,
    procurement_confidence: float,
    quality_flags: list[str],
    unknown_structure_flags: list[str],
    parser_semantic_trace,
) -> tuple[str, list[str]]:
    is_unknownish = procurement_kind in {"unknown", "mixed"} or bool(unknown_structure_flags)
    if not is_unknownish:
        return "standard", []
    reasons: list[str] = []
    if procurement_kind == "unknown":
        reasons.append("unknown_procurement_kind")
    if procurement_confidence < 0.7:
        reasons.append("low_procurement_kind_confidence")
    if unknown_structure_flags:
        reasons.extend(unknown_structure_flags[:3])
    if any(flag in quality_flags for flag in ["weak_source_support", "non_body_structure_dominant", "mixed_zone_ratio_high"]):
        reasons.extend(
            flag
            for flag in ["weak_source_support", "non_body_structure_dominant", "mixed_zone_ratio_high"]
            if flag in quality_flags
        )
    if parser_semantic_trace and parser_semantic_trace.activated:
        reasons.append("parser_semantic_assist_activated")
        if parser_semantic_trace.applied_count > 0:
            reasons.append("parser_semantic_assist_applied")
    if not reasons:
        return "standard", []
    return "unknown_conservative", list(dict.fromkeys(reasons))


def _build_primary_review_types(zone_stats: list[ZoneStat]) -> list[str]:
    ordered: list[str] = []
    for item in sorted(zone_stats, key=lambda stat: (-_ZONE_IMPORTANCE.get(stat.zone_type, 0), -stat.ratio, stat.zone_type.value)):
        review_type = ZONE_PRIMARY_REVIEW_TYPES.get(item.zone_type, "")
        if not review_type or review_type in ordered:
            continue
        ordered.append(review_type)
    return ordered


def _build_representative_anchors(parse_result: ParseResult, zone_stats: list[ZoneStat]) -> list[str]:
    zone_by_node = {item.node_id: item.zone_type for item in parse_result.semantic_zones}
    scored_anchors: list[tuple[int, int, str]] = []

    for index, unit in enumerate(parse_result.clause_units):
        if not unit.anchor.line_hint:
            continue
        priority = _anchor_priority(unit.zone_type, unit.clause_semantic_type, unit.effect_tags)
        scored_anchors.append((priority, index, unit.anchor.line_hint))

    for index, node in enumerate(parse_result.document_nodes):
        if not node.anchor.line_hint:
            continue
        zone_type = zone_by_node.get(node.node_id, SemanticZoneType.mixed_or_uncertain)
        priority = _anchor_priority(zone_type, None, [])
        if node.node_type == NodeType.appendix:
            priority += 8
        if node.node_type in {NodeType.table, NodeType.table_row} and zone_type in {
            SemanticZoneType.scoring,
            SemanticZoneType.qualification,
            SemanticZoneType.contract,
            SemanticZoneType.template,
        }:
            priority += 4
        scored_anchors.append((priority, len(parse_result.clause_units) + index, node.anchor.line_hint))

    anchors: list[str] = []
    for priority, index, anchor in sorted(scored_anchors, key=lambda item: (-item[0], item[1])):
        if anchor in anchors:
            continue
        anchors.append(anchor)
        if len(anchors) >= 6:
            break
    return anchors


def _build_summary(
    *,
    document_name: str,
    procurement_kind: str,
    routing_mode: str,
    zone_stats: list[ZoneStat],
    candidates: list[DomainProfileCandidate],
    structure_flags: list[str],
    quality_flags: list[str],
    risk_activation_hints: list[str],
) -> str:
    top_zones = ", ".join(f"{item.zone_type.value}:{item.ratio:.2f}" for item in zone_stats[:3]) or "无稳定区域"
    top_candidates = ", ".join(item.profile_id for item in candidates[:3]) or "无候选领域画像"
    top_flags = ", ".join(structure_flags[:3]) or "无明显结构风险"
    top_quality = ", ".join(quality_flags[:3]) or "无显著质量告警"
    top_hints = ", ".join(risk_activation_hints[:3]) or "无显著风险激活"
    return (
        f"文件《{document_name}》初步画像为 {procurement_kind}；"
        f"路由模式：{routing_mode}；"
        f"主要区域：{top_zones}；"
        f"候选领域：{top_candidates}；"
        f"结构标记：{top_flags}；"
        f"质量标记：{top_quality}；"
        f"风险提示：{top_hints}。"
    )


def _accumulate_kind_scores(
    fragment: str,
    weight: float,
    scores: dict[str, float],
    reasons: dict[str, list[str]],
    *,
    context: str,
) -> None:
    for kind, tokens in _PROCUREMENT_KIND_TOKENS.items():
        if not any(token in fragment for token in tokens):
            continue
        scores[kind] += weight
        if len(reasons[kind]) < 3:
            reasons[kind].append(f"{context} 命中 {kind} 信号")


def _kind_signal_weight(
    zone_type: SemanticZoneType,
    node_type: NodeType | None,
    effect_tags: list[EffectTag] | None = None,
) -> float:
    weight = {
        SemanticZoneType.qualification: 1.15,
        SemanticZoneType.technical: 1.1,
        SemanticZoneType.business: 1.05,
        SemanticZoneType.contract: 1.05,
        SemanticZoneType.scoring: 0.95,
        SemanticZoneType.template: 0.45,
        SemanticZoneType.appendix_reference: 0.45,
        SemanticZoneType.policy_explanation: 0.75,
        SemanticZoneType.administrative_info: 0.7,
        SemanticZoneType.mixed_or_uncertain: 0.55,
        SemanticZoneType.catalog_or_navigation: 0.35,
        SemanticZoneType.public_copy_or_noise: 0.2,
    }.get(zone_type, 0.5)
    if node_type == NodeType.appendix:
        weight *= 0.75
    if effect_tags and any(tag in {EffectTag.template, EffectTag.reference_only, EffectTag.public_copy_noise} for tag in effect_tags):
        weight *= 0.8
    return round(weight, 3)


def _anchor_priority(
    zone_type: SemanticZoneType,
    clause_semantic_type: ClauseSemanticType | None,
    effect_tags: list[EffectTag],
) -> int:
    priority = _ZONE_IMPORTANCE.get(zone_type, 0)
    if clause_semantic_type in {
        ClauseSemanticType.scoring_rule,
        ClauseSemanticType.scoring_factor,
    }:
        priority += 18
    elif clause_semantic_type in {
        ClauseSemanticType.qualification_condition,
        ClauseSemanticType.qualification_material_requirement,
    }:
        priority += 15
    elif clause_semantic_type in {
        ClauseSemanticType.contract_obligation,
        ClauseSemanticType.payment_term,
        ClauseSemanticType.acceptance_term,
        ClauseSemanticType.breach_term,
        ClauseSemanticType.termination_term,
    }:
        priority += 12
    elif clause_semantic_type in {
        ClauseSemanticType.template_instruction,
        ClauseSemanticType.declaration_template,
        ClauseSemanticType.example_clause,
    }:
        priority += 10
    elif clause_semantic_type in {
        ClauseSemanticType.reference_clause,
        ClauseSemanticType.catalog_clause,
    }:
        priority += 6
    if any(tag in {EffectTag.template, EffectTag.reference_only} for tag in effect_tags):
        priority += 4
    return priority


def _profile_like(
    procurement_kind: str,
    structure_flags: list[str],
    zone_stats: list[ZoneStat],
) -> DocumentProfile:
    return DocumentProfile(
        document_id="__profile_like__",
        source_path="__profile_like__",
        procurement_kind=procurement_kind,
        procurement_kind_confidence=0.0,
        structure_flags=structure_flags,
        dominant_zones=zone_stats,
    )


def _zone_node_count(zone_stats: list[ZoneStat], zone_type: SemanticZoneType) -> int:
    for item in zone_stats:
        if item.zone_type == zone_type:
            return item.node_count
    return 0


def _zone_ratio(zone_stats: list[ZoneStat], zone_type: SemanticZoneType) -> float:
    for item in zone_stats:
        if item.zone_type == zone_type:
            return item.ratio
    return 0.0


def _effect_ratio(effect_stats: list[EffectStat], effect_tag: EffectTag) -> float:
    for item in effect_stats:
        if item.effect_tag == effect_tag:
            return item.ratio
    return 0.0


def _clause_ratio(clause_stats: list[ClauseSemanticStat], clause_semantic_type: ClauseSemanticType) -> float:
    for item in clause_stats:
        if item.clause_semantic_type == clause_semantic_type:
            return item.ratio
    return 0.0

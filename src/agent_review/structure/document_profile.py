from __future__ import annotations

from collections import Counter

from ..models import (
    ClauseSemanticStat,
    DocumentProfile,
    DomainProfileCandidate,
    EffectStat,
    ParseResult,
    ZoneStat,
)
from ..ontology import ClauseSemanticType, EffectTag, SemanticZoneType


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
    structure_flags = _build_structure_flags(parse_result, zone_stats, effect_stats, clause_stats)
    risk_activation_hints = _build_risk_activation_hints(procurement_kind, structure_flags, zone_stats, effect_stats)
    quality_flags = _build_quality_flags(parse_result, zone_stats, effect_stats, clause_stats)
    unknown_structure_flags = _build_unknown_structure_flags(procurement_kind, structure_flags, zone_stats)
    anchors = _build_representative_anchors(parse_result, zone_stats)
    summary = _build_summary(
        document_name=document_name,
        procurement_kind=procurement_kind,
        zone_stats=zone_stats,
        candidates=candidates,
        structure_flags=structure_flags,
        quality_flags=quality_flags,
    )
    return DocumentProfile(
        document_id=parse_result.source_path or document_name,
        source_path=parse_result.source_path or document_name,
        procurement_kind=procurement_kind,
        procurement_kind_confidence=procurement_confidence,
        domain_profile_candidates=candidates,
        dominant_zones=zone_stats,
        effect_distribution=effect_stats,
        clause_semantic_distribution=clause_stats,
        structure_flags=structure_flags,
        risk_activation_hints=risk_activation_hints,
        quality_flags=quality_flags,
        unknown_structure_flags=unknown_structure_flags,
        representative_anchors=anchors,
        summary=summary,
    )


def _infer_procurement_kind(parse_result: ParseResult) -> tuple[str, float, list[str]]:
    text = " ".join(
        part
        for part in [
            parse_result.text,
            " ".join(node.title for node in parse_result.document_nodes[:120]),
            " ".join(node.text for node in parse_result.document_nodes[:120]),
        ]
        if part
    )
    scores = {
        "goods": _score_tokens(text, ["货物", "家具", "设备", "桌", "椅", "柜", "床", "柜体", "课桌", "讲桌"]),
        "service": _score_tokens(text, ["服务", "运维", "驻场", "保洁", "管护", "实施", "培训", "维护"]),
        "engineering": _score_tokens(text, ["工程", "施工", "改造", "装饰", "装修", "建设"]),
    }
    best_kind = max(scores, key=scores.get, default="unknown")
    best_score = scores.get(best_kind, 0)
    if best_score <= 0:
        return "unknown", 0.25, ["未识别到稳定采购类型信号"]

    kinds = [kind for kind, score in scores.items() if score > 0]
    if len(kinds) >= 2:
        return "mixed", min(0.78, 0.55 + 0.05 * len(kinds)), [f"同时识别到 {', '.join(kinds)} 信号"]
    return best_kind, min(0.95, 0.52 + 0.06 * best_score), [f"识别到 {best_kind} 相关信号"]


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

    if any(token in text for token in ["家具", "课桌", "书桌", "椅", "柜", "床", "讲桌"]):
        candidates.append(DomainProfileCandidate("furniture", 0.92, ["命中家具类词汇"]))

    if _zone_ratio(zone_stats, SemanticZoneType.scoring) > 0.15:
        candidates.append(DomainProfileCandidate("scoring_heavy", 0.71, ["评分区密度较高"]))
    if _zone_ratio(zone_stats, SemanticZoneType.template) > 0.15:
        candidates.append(DomainProfileCandidate("template_heavy", 0.69, ["模板区密度较高"]))
    if _effect_ratio(effect_stats, EffectTag.reference_only) > 0.1:
        candidates.append(DomainProfileCandidate("appendix_heavy", 0.68, ["引用性条款较多"]))
    if _clause_ratio(clause_stats, ClauseSemanticType.contract_obligation) > 0.1:
        candidates.append(DomainProfileCandidate("contract_heavy", 0.65, ["合同条款较多"]))

    deduped: list[DomainProfileCandidate] = []
    seen: set[str] = set()
    for item in sorted(candidates, key=lambda x: x.confidence, reverse=True):
        if item.profile_id in seen:
            continue
        seen.add(item.profile_id)
        deduped.append(item)
    return deduped[:4]


def _build_structure_flags(
    parse_result: ParseResult,
    zone_stats: list[ZoneStat],
    effect_stats: list[EffectStat],
    clause_stats: list[ClauseSemanticStat],
) -> list[str]:
    flags: list[str] = []
    if _zone_ratio(zone_stats, SemanticZoneType.scoring) > 0.2:
        flags.append("heavy_scoring_tables")
    if _zone_ratio(zone_stats, SemanticZoneType.template) > 0.2:
        flags.append("heavy_template_pollution")
    if _zone_ratio(zone_stats, SemanticZoneType.appendix_reference) > 0.12:
        flags.append("heavy_appendix_reference")
    if _zone_ratio(zone_stats, SemanticZoneType.contract) > 0.12:
        flags.append("heavy_contract_terms")
    if _effect_ratio(effect_stats, EffectTag.catalog) > 0.08:
        flags.append("catalog_noise_present")
    if len([item for item in zone_stats if item.ratio >= 0.12]) >= 2:
        flags.append("mixed_structure_signals")
    if any(len(node.text) > 260 for node in parse_result.document_nodes if node.node_type.value == "table_row"):
        flags.append("fragmented_table_text")
    if _clause_ratio(clause_stats, ClauseSemanticType.unknown_clause) > 0.35:
        flags.append("unknown_clause_heavy")
    return list(dict.fromkeys(flags))


def _build_risk_activation_hints(
    procurement_kind: str,
    structure_flags: list[str],
    zone_stats: list[ZoneStat],
    effect_stats: list[EffectStat],
) -> list[str]:
    hints: list[str] = []
    if procurement_kind in {"goods", "mixed"}:
        hints.append("competition_restriction")
    if procurement_kind in {"service", "mixed"}:
        hints.append("contract_performance")
    if _zone_ratio(zone_stats, SemanticZoneType.qualification) > 0.08:
        hints.append("qualification_scoring_boundary")
    if _zone_ratio(zone_stats, SemanticZoneType.scoring) > 0.08:
        hints.append("scoring_quantification")
    if _zone_ratio(zone_stats, SemanticZoneType.policy_explanation) > 0.04 or _effect_ratio(effect_stats, EffectTag.policy_background) > 0.04:
        hints.append("sme_policy_consistency")
    if any(flag in structure_flags for flag in ["heavy_template_pollution", "heavy_appendix_reference"]):
        hints.append("template_conflict")
    return list(dict.fromkeys(hints))


def _build_quality_flags(
    parse_result: ParseResult,
    zone_stats: list[ZoneStat],
    effect_stats: list[EffectStat],
    clause_stats: list[ClauseSemanticStat],
) -> list[str]:
    flags: list[str] = []
    if _effect_ratio(effect_stats, EffectTag.template) > 0.18:
        flags.append("template_ratio_high")
    if _effect_ratio(effect_stats, EffectTag.reference_only) > 0.12:
        flags.append("reference_ratio_high")
    if _zone_ratio(zone_stats, SemanticZoneType.mixed_or_uncertain) > 0.25:
        flags.append("mixed_zone_ratio_high")
    if _clause_ratio(clause_stats, ClauseSemanticType.unknown_clause) > 0.3:
        flags.append("unknown_clause_ratio_high")
    if not parse_result.clause_units:
        flags.append("no_clause_units")
    return list(dict.fromkeys(flags))


def _build_unknown_structure_flags(
    procurement_kind: str,
    structure_flags: list[str],
    zone_stats: list[ZoneStat],
) -> list[str]:
    flags: list[str] = []
    if procurement_kind == "unknown":
        flags.append("unknown_procurement_kind")
    if "mixed_structure_signals" in structure_flags:
        flags.append("mixed_structure_uncertain")
    if _zone_ratio(zone_stats, SemanticZoneType.mixed_or_uncertain) > 0.4:
        flags.append("majority_uncertain_zone")
    return flags


def _build_representative_anchors(parse_result: ParseResult, zone_stats: list[ZoneStat]) -> list[str]:
    dominant_zones = {item.zone_type for item in zone_stats[:3]}
    anchors: list[str] = []
    for unit in parse_result.clause_units:
        if unit.zone_type not in dominant_zones:
            continue
        if unit.anchor.line_hint and unit.anchor.line_hint not in anchors:
            anchors.append(unit.anchor.line_hint)
        if len(anchors) >= 5:
            break
    if not anchors:
        for node in parse_result.document_nodes[:5]:
            if node.anchor.line_hint and node.anchor.line_hint not in anchors:
                anchors.append(node.anchor.line_hint)
            if len(anchors) >= 5:
                break
    return anchors


def _build_summary(
    *,
    document_name: str,
    procurement_kind: str,
    zone_stats: list[ZoneStat],
    candidates: list[DomainProfileCandidate],
    structure_flags: list[str],
    quality_flags: list[str],
) -> str:
    top_zones = ", ".join(f"{item.zone_type.value}:{item.ratio:.2f}" for item in zone_stats[:3]) or "无稳定区域"
    top_candidates = ", ".join(item.profile_id for item in candidates[:3]) or "无候选领域画像"
    top_flags = ", ".join(structure_flags[:3]) or "无明显结构风险"
    top_quality = ", ".join(quality_flags[:3]) or "无显著质量告警"
    return (
        f"文件《{document_name}》初步画像为 {procurement_kind}；"
        f"主要区域：{top_zones}；"
        f"候选领域：{top_candidates}；"
        f"结构标记：{top_flags}；"
        f"质量标记：{top_quality}。"
    )


def _score_tokens(text: str, tokens: list[str]) -> int:
    return sum(1 for token in tokens if token in text)


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

from __future__ import annotations

import json
from dataclasses import replace

from ..llm.client import OpenAICompatibleClient, QwenLocalConfig
from ..models import (
    ClauseUnit,
    DocumentProfile,
    EffectTagResult,
    ParseResult,
    ParserSemanticCandidate,
    ParserSemanticResolution,
    ParserSemanticTrace,
    SemanticZone,
)
from ..ontology import ClauseSemanticType, EffectTag, SemanticZoneType


PARSER_SEMANTIC_ASSIST_SYSTEM_PROMPT = """
你是政府采购招标文件 parser 的“低置信度歧义消解器”。

任务边界：
1. 你不能重建整份文档，只能审查给出的少量候选条款。
2. 你不能直接输出合规结论，只能纠正 parser 的语义标签。
3. 你只能输出 JSON，不要输出解释性前后文。

输出 schema：
{
  "resolutions": [
    {
      "node_id": "n-1",
      "zone_type": "qualification",
      "clause_semantic_type": "qualification_condition",
      "effect_tags": ["binding"],
      "confidence": 0.91,
      "reason": "当前条款属于资格要求正文"
    }
  ]
}

约束：
1. zone_type 必须来自给定枚举。
2. clause_semantic_type 必须来自给定枚举。
3. effect_tags 必须来自给定枚举。
4. 如果没有把握，不要强改，保持与 current_* 一致即可。
5. 仅在明显优于当前标签时才调整。
""".strip()


class NullParserSemanticAssistant:
    def assist(
        self,
        parse_result: ParseResult,
        document_profile: DocumentProfile | None,
    ) -> tuple[ParseResult, ParserSemanticTrace]:
        return parse_result, ParserSemanticTrace(activated=False, activation_reasons=["disabled"])


class QwenParserSemanticAssistant:
    def __init__(
        self,
        client: OpenAICompatibleClient | None = None,
        timeout: float | None = None,
        max_candidates: int = 10,
        apply_threshold: float = 0.78,
    ) -> None:
        if client is not None:
            self.client = client
        else:
            config = QwenLocalConfig.from_env_or_default()
            if timeout is not None:
                config.timeout = timeout
            self.client = OpenAICompatibleClient(config)
        self.max_candidates = max_candidates
        self.apply_threshold = apply_threshold

    def assist(
        self,
        parse_result: ParseResult,
        document_profile: DocumentProfile | None,
    ) -> tuple[ParseResult, ParserSemanticTrace]:
        candidates = _collect_candidates(parse_result)
        activation_reasons = _build_activation_reasons(document_profile, candidates)
        if not activation_reasons or not candidates:
            return parse_result, ParserSemanticTrace(
                activated=False,
                activation_reasons=activation_reasons or ["no_low_confidence_candidates"],
                candidate_count=len(candidates),
            )

        reviewed_candidates = candidates[: self.max_candidates]
        trace = ParserSemanticTrace(
            activated=True,
            activation_reasons=activation_reasons,
            candidate_count=len(candidates),
            reviewed_count=len(reviewed_candidates),
            candidates=reviewed_candidates,
        )
        raw_response = self.client.generate_text(
            PARSER_SEMANTIC_ASSIST_SYSTEM_PROMPT,
            _build_user_prompt(document_profile, reviewed_candidates),
        )
        resolutions, warnings = _parse_resolutions(raw_response)
        trace.warnings.extend(warnings)
        trace.resolutions = resolutions
        trace.applied_count = _apply_resolutions(parse_result, resolutions, self.apply_threshold)
        return parse_result, trace


def _collect_candidates(parse_result: ParseResult) -> list[ParserSemanticCandidate]:
    zone_index = {item.node_id: item for item in parse_result.semantic_zones}
    effect_index = {item.node_id: item for item in parse_result.effect_tag_results}
    candidates: list[tuple[float, ParserSemanticCandidate]] = []
    for unit in parse_result.clause_units:
        zone = zone_index.get(unit.source_node_id)
        effect = effect_index.get(unit.source_node_id)
        reasons = _candidate_reasons(unit, zone, effect)
        if not reasons:
            continue
        score = _candidate_priority(unit, zone, effect)
        candidates.append(
            (
                score,
                ParserSemanticCandidate(
                    node_id=unit.source_node_id,
                    unit_id=unit.unit_id,
                    path=unit.path,
                    text=unit.text[:400],
                    reasons=reasons,
                    current_zone_type=unit.zone_type,
                    current_clause_semantic_type=unit.clause_semantic_type,
                    current_effect_tags=list(unit.effect_tags),
                    current_confidence=unit.confidence,
                ),
            )
        )
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in candidates]


def _candidate_reasons(
    unit: ClauseUnit,
    zone: SemanticZone | None,
    effect: EffectTagResult | None,
) -> list[str]:
    reasons: list[str] = []
    if unit.zone_type == SemanticZoneType.mixed_or_uncertain:
        reasons.append("mixed_zone")
    if unit.clause_semantic_type == ClauseSemanticType.unknown_clause:
        reasons.append("unknown_clause_type")
    if unit.confidence < 0.72:
        reasons.append("low_clause_confidence")
    if zone is not None and zone.confidence < 0.68:
        reasons.append("low_zone_confidence")
    if effect is not None and effect.confidence < 0.72:
        reasons.append("low_effect_confidence")
    if EffectTag.uncertain_effect in unit.effect_tags:
        reasons.append("uncertain_effect")
    return reasons


def _candidate_priority(
    unit: ClauseUnit,
    zone: SemanticZone | None,
    effect: EffectTagResult | None,
) -> float:
    score = 0.0
    if unit.zone_type == SemanticZoneType.mixed_or_uncertain:
        score += 1.4
    if unit.clause_semantic_type == ClauseSemanticType.unknown_clause:
        score += 1.2
    score += max(0.0, 0.8 - unit.confidence)
    if zone is not None:
        score += max(0.0, 0.75 - zone.confidence)
    if effect is not None:
        score += max(0.0, 0.75 - effect.confidence)
    return round(score, 4)


def _build_activation_reasons(
    document_profile: DocumentProfile | None,
    candidates: list[ParserSemanticCandidate],
) -> list[str]:
    reasons: list[str] = []
    if document_profile is None:
        return ["missing_document_profile"] if candidates else []
    if document_profile.procurement_kind == "unknown":
        reasons.append("unknown_procurement_kind")
    if document_profile.procurement_kind_confidence < 0.7:
        reasons.append("low_procurement_kind_confidence")
    if document_profile.unknown_structure_flags:
        reasons.extend(document_profile.unknown_structure_flags[:3])
    if len(candidates) >= 3:
        reasons.append("low_confidence_nodes_present")
    return list(dict.fromkeys(reasons))


def _build_user_prompt(
    document_profile: DocumentProfile | None,
    candidates: list[ParserSemanticCandidate],
) -> str:
    profile_summary = {
        "procurement_kind": document_profile.procurement_kind if document_profile else "unknown",
        "procurement_kind_confidence": document_profile.procurement_kind_confidence if document_profile else 0.0,
        "unknown_structure_flags": document_profile.unknown_structure_flags if document_profile else [],
        "top_domain_candidates": (
            [item.to_dict() for item in document_profile.domain_profile_candidates[:3]]
            if document_profile
            else []
        ),
    }
    payload = {
        "profile": profile_summary,
        "zone_type_enum": [item.value for item in SemanticZoneType],
        "clause_semantic_type_enum": [item.value for item in ClauseSemanticType],
        "effect_tag_enum": [item.value for item in EffectTag],
        "candidates": [item.to_dict() for item in candidates],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _parse_resolutions(raw_response: str) -> tuple[list[ParserSemanticResolution], list[str]]:
    warnings: list[str] = []
    if not raw_response.strip():
        return [], ["parser_semantic_assist_empty_response"]
    try:
        payload = json.loads(_extract_json_payload(raw_response))
    except json.JSONDecodeError:
        return [], ["parser_semantic_assist_invalid_json"]
    raw_items = payload.get("resolutions")
    if not isinstance(raw_items, list):
        return [], ["parser_semantic_assist_missing_resolutions"]
    resolutions: list[ParserSemanticResolution] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("node_id", "")).strip()
        if not node_id:
            continue
        zone_type = _parse_enum_value(item.get("zone_type"), SemanticZoneType)
        clause_type = _parse_enum_value(item.get("clause_semantic_type"), ClauseSemanticType)
        effect_tags = _parse_enum_list(item.get("effect_tags"), EffectTag)
        confidence = _safe_float(item.get("confidence"))
        reason = str(item.get("reason", "")).strip()
        resolutions.append(
            ParserSemanticResolution(
                node_id=node_id,
                proposed_zone_type=zone_type,
                proposed_clause_semantic_type=clause_type,
                proposed_effect_tags=effect_tags,
                confidence=confidence,
                reason=reason,
            )
        )
    if not resolutions:
        warnings.append("parser_semantic_assist_no_valid_resolution")
    return resolutions, warnings


def _extract_json_payload(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped


def _parse_enum_value(raw_value, enum_cls):
    if not raw_value:
        return None
    try:
        return enum_cls(str(raw_value).strip())
    except ValueError:
        return None


def _parse_enum_list(raw_value, enum_cls):
    if not isinstance(raw_value, list):
        return []
    parsed = []
    for item in raw_value:
        try:
            parsed.append(enum_cls(str(item).strip()))
        except ValueError:
            continue
    return list(dict.fromkeys(parsed))


def _safe_float(raw_value) -> float:
    try:
        return round(float(raw_value), 4)
    except (TypeError, ValueError):
        return 0.0


def _apply_resolutions(
    parse_result: ParseResult,
    resolutions: list[ParserSemanticResolution],
    apply_threshold: float,
) -> int:
    if not resolutions:
        return 0
    zone_index = {item.node_id: idx for idx, item in enumerate(parse_result.semantic_zones)}
    effect_index = {item.node_id: idx for idx, item in enumerate(parse_result.effect_tag_results)}
    unit_index: dict[str, list[int]] = {}
    for idx, unit in enumerate(parse_result.clause_units):
        unit_index.setdefault(unit.source_node_id, []).append(idx)

    applied_count = 0
    for resolution in resolutions:
        if resolution.confidence < apply_threshold:
            continue
        changed = False
        zone_pos = zone_index.get(resolution.node_id)
        if zone_pos is not None and resolution.proposed_zone_type is not None:
            current = parse_result.semantic_zones[zone_pos]
            if current.zone_type != resolution.proposed_zone_type:
                parse_result.semantic_zones[zone_pos] = replace(
                    current,
                    zone_type=resolution.proposed_zone_type,
                    confidence=max(current.confidence, resolution.confidence),
                    classification_basis=list(dict.fromkeys([*current.classification_basis, f"llm:{resolution.reason or 'disambiguated'}"])),
                )
                changed = True

        effect_pos = effect_index.get(resolution.node_id)
        if effect_pos is not None and resolution.proposed_effect_tags:
            current_effect = parse_result.effect_tag_results[effect_pos]
            if current_effect.effect_tags != resolution.proposed_effect_tags:
                parse_result.effect_tag_results[effect_pos] = replace(
                    current_effect,
                    effect_tags=resolution.proposed_effect_tags,
                    confidence=max(current_effect.confidence, resolution.confidence),
                    evidence=list(dict.fromkeys([*current_effect.evidence, f"llm:{resolution.reason or 'disambiguated'}"])),
                )
                changed = True

        for unit_pos in unit_index.get(resolution.node_id, []):
            current_unit = parse_result.clause_units[unit_pos]
            next_zone = resolution.proposed_zone_type or current_unit.zone_type
            next_clause_type = resolution.proposed_clause_semantic_type or current_unit.clause_semantic_type
            next_effect_tags = resolution.proposed_effect_tags or current_unit.effect_tags
            if (
                current_unit.zone_type != next_zone
                or current_unit.clause_semantic_type != next_clause_type
                or current_unit.effect_tags != next_effect_tags
            ):
                parse_result.clause_units[unit_pos] = replace(
                    current_unit,
                    zone_type=next_zone,
                    clause_semantic_type=next_clause_type,
                    effect_tags=list(next_effect_tags),
                    confidence=max(current_unit.confidence, resolution.confidence),
                )
                changed = True

        resolution.applied = changed
        if changed:
            applied_count += 1
    return applied_count

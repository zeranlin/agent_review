from __future__ import annotations

import json

from .authority_bindings import list_bindings_for_point
from .models import LegalFactCandidate, ReviewPointInstance, RuleHit
from .review_point_contract_registry import get_review_point_contract
from .rule_definitions import list_rule_definitions


def generate_rule_hits(legal_fact_candidates: list[LegalFactCandidate]) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for fact in legal_fact_candidates:
        haystack = " ".join(
            [
                fact.object_text,
                fact.subject,
                fact.predicate,
                " ".join(fact.normalized_terms),
                fact.zone_type,
                fact.fact_type,
                fact.legal_effect_type,
                fact.source_role,
                fact.binding_strength,
                fact.rebuttal_strength,
                fact.condition_scope,
                fact.policy_branch,
                "project_binding" if fact.project_binding else "",
                json.dumps(fact.constraint_value, ensure_ascii=False, sort_keys=True),
                " ".join(str(key) for key in fact.constraint_value.keys()),
                " ".join(str(value) for value in fact.constraint_value.values()),
            ]
        )
        for rule in list_rule_definitions():
            if fact.fact_type not in rule.applicable_fact_types:
                continue
            if rule.applicable_zone_types and fact.zone_type not in rule.applicable_zone_types:
                continue
            trigger_reasons = [pattern for pattern in rule.trigger_patterns if pattern and pattern in haystack]
            if not trigger_reasons:
                continue
            matched_slots = _matched_slots(fact, rule.required_fact_slots)
            if rule.required_fact_slots and len(matched_slots) < len(rule.required_fact_slots):
                continue
            hits.append(
                RuleHit(
                    hit_id=f"RH-{len(hits) + 1:04d}",
                    rule_id=rule.rule_id,
                    point_id=rule.point_id,
                    fact_ids=[fact.fact_id],
                    trigger_reasons=trigger_reasons[:4],
                    matched_slots=matched_slots,
                    confidence=round(min(0.99, fact.confidence + 0.08), 3),
                    severity_hint=rule.severity_hint,
                    default_disposition=rule.default_disposition,
                )
            )
    return hits


def build_review_point_instances(rule_hits: list[RuleHit]) -> list[ReviewPointInstance]:
    grouped: dict[str, list[RuleHit]] = {}
    for hit in rule_hits:
        grouped.setdefault(hit.point_id, []).append(hit)

    instances: list[ReviewPointInstance] = []
    for point_id, hits in grouped.items():
        contract = get_review_point_contract(point_id)
        authority_binding_ids = (
            list(contract.authority_binding_ids)
            if contract is not None
            else [item.binding_id for item in list_bindings_for_point(point_id)]
        )
        matched_rule_ids = _ordered_unique(hit.rule_id for hit in hits)
        fact_ids = _ordered_unique(fact_id for hit in hits for fact_id in hit.fact_ids)
        confidence = max((hit.confidence for hit in hits), default=0.0)
        title = contract.title if contract is not None else point_id
        risk_family = contract.risk_family if contract is not None else ""
        summary = f"由 {len(matched_rule_ids)} 条规则命中、{len(fact_ids)} 条法律事实支持。"
        instances.append(
            ReviewPointInstance(
                instance_id=f"RPI-{len(instances) + 1:04d}",
                point_id=point_id,
                title=title,
                risk_family=risk_family,
                matched_rule_ids=matched_rule_ids,
                supporting_fact_ids=fact_ids,
                authority_binding_ids=authority_binding_ids,
                confidence=round(confidence, 3),
                summary=summary,
            )
        )
    return instances


def _matched_slots(fact: LegalFactCandidate, required_slots: list[str]) -> list[str]:
    matched: list[str] = []
    normalized_value = fact.constraint_value or {}
    for slot in required_slots:
        current = slot.strip()
        if not current:
            continue
        if current == "object_text" and fact.object_text.strip():
            matched.append(current)
            continue
        if current == "constraint_value" and normalized_value:
            matched.append(current)
            continue
        if current == "project_binding" and fact.project_binding:
            matched.append(current)
            continue
        if current == "binding_strength" and fact.binding_strength:
            matched.append(current)
            continue
        if current == "rebuttal_strength" and fact.rebuttal_strength and fact.rebuttal_strength != "none":
            matched.append(current)
            continue
        if current == "condition_scope" and fact.condition_scope:
            matched.append(current)
            continue
        if current == "policy_branch" and fact.policy_branch:
            matched.append(current)
            continue
        if current == "legal_effect_type" and fact.legal_effect_type:
            matched.append(current)
            continue
        if current in normalized_value:
            matched.append(current)
    return matched


def _ordered_unique(items) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        current = str(item).strip()
        if not current or current in seen:
            continue
        seen.add(current)
        ordered.append(current)
    return ordered

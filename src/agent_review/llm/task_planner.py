from __future__ import annotations

from ..fact_collectors import collect_task_facts
from ..models import (
    ExtractedClause,
    ReviewPoint,
    ReviewPointCondition,
    ReviewPointDefinition,
    Severity,
)


def parse_dynamic_review_tasks(raw_items: object) -> list[ReviewPointDefinition]:
    if not isinstance(raw_items, list):
        return []
    results: list[ReviewPointDefinition] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        dimension = str(item.get("dimension", "")).strip()
        if not title or not dimension:
            continue
        catalog_id = str(item.get("catalog_id", "")).strip() or f"RP-DYN-{index:03d}"
        focus_fields = [
            str(value).strip()
            for value in item.get("focus_fields", [])
            if str(value).strip()
        ]
        signal_groups = []
        for group in item.get("signal_groups", []):
            if not isinstance(group, list):
                continue
            cleaned = [str(value).strip() for value in group if str(value).strip()]
            if cleaned:
                signal_groups.append(cleaned)

        required_conditions: list[ReviewPointCondition] = []
        if focus_fields:
            required_conditions.append(
                ReviewPointCondition(
                    name="存在关键结构化字段",
                    clause_fields=focus_fields,
                    signal_groups=[],
                )
            )
        for signal_index, group in enumerate(signal_groups, start=1):
            required_conditions.append(
                ReviewPointCondition(
                    name=f"命中场景信号{signal_index}",
                    clause_fields=[],
                    signal_groups=[group],
                )
            )
        if not required_conditions:
            continue

        results.append(
            ReviewPointDefinition(
                catalog_id=catalog_id,
                title=title,
                dimension=dimension,
                default_severity=_parse_severity(item.get("severity")),
                scenario_tags=[
                    str(value).strip()
                    for value in item.get("scenario_tags", [])
                    if str(value).strip()
                ],
                required_conditions=required_conditions,
                exclusion_conditions=[],
                basis_hint=str(item.get("basis_hint", "")).strip(),
            )
        )
    return results


def build_dynamic_review_points(
    definitions: list[ReviewPointDefinition],
    extracted_clauses: list[ExtractedClause],
) -> list[ReviewPoint]:
    review_points: list[ReviewPoint] = []
    for index, definition in enumerate(definitions, start=1):
        evidence_bundle, status, rationale = collect_task_facts(definition, extracted_clauses)
        review_points.append(
            ReviewPoint(
                point_id=f"DYN-{index:03d}",
                catalog_id=definition.catalog_id,
                title=definition.title,
                dimension=definition.dimension,
                severity=definition.default_severity,
                status=status,
                rationale=rationale or "LLM 场景识别建议新增该审查任务，待结合结构化事实进一步核定。",
                evidence_bundle=evidence_bundle,
                legal_basis=[],
                source_findings=[f"task_library:{definition.catalog_id}"],
            )
        )
    return review_points


def _parse_severity(raw_value: object) -> Severity:
    value = str(raw_value or "").strip().lower()
    if value == "critical":
        return Severity.critical
    if value == "high":
        return Severity.high
    if value == "low":
        return Severity.low
    return Severity.medium

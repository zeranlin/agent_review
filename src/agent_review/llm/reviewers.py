from __future__ import annotations

import json
import re
from dataclasses import replace

from ..merge import dedupe_extracted_clauses, dedupe_findings, dedupe_recommendations
from ..models import (
    Evidence,
    ExtractedClause,
    Finding,
    FindingType,
    LLMSemanticReview,
    Recommendation,
    ReviewReport,
    RunStageRecord,
    Severity,
    SpecialistTables,
)
from .client import OpenAICompatibleClient, QwenLocalConfig
from .prompts import REVIEW_ENHANCER_SYSTEM_PROMPT, build_review_enhancer_prompt


class NullReviewEnhancer:
    def enhance(self, report: ReviewReport) -> ReviewReport:
        return report


class QwenReviewEnhancer:
    def __init__(
        self,
        client: OpenAICompatibleClient | None = None,
        timeout: float | None = None,
    ) -> None:
        if client is not None:
            self.client = client
        else:
            config = QwenLocalConfig.from_env_or_default()
            if timeout is not None:
                config.timeout = timeout
            self.client = OpenAICompatibleClient(config)

    def enhance(self, report: ReviewReport) -> ReviewReport:
        try:
            raw = self.client.generate_text(
                system_prompt=REVIEW_ENHANCER_SYSTEM_PROMPT,
                user_prompt=build_review_enhancer_prompt(report),
            )
            parsed = _parse_json_response(raw)
            semantic_review = _parse_semantic_review(parsed.get("semantic_review"))
            summary = str(parsed.get("summary", "")).strip() or report.summary
            recommendations = _merge_recommendations(report, parsed.get("recommendations"))
            specialist_tables = _merge_specialist_summaries(
                report.specialist_tables, parsed.get("specialist_summaries")
            )
            merged_clauses = dedupe_extracted_clauses(
                report.extracted_clauses + semantic_review.clause_supplements
            )
            merged_findings = dedupe_findings(
                report.findings
                + semantic_review.specialist_findings
                + semantic_review.consistency_findings
            )
            stage_records = list(report.stage_records) + [
                RunStageRecord(
                    stage_name="llm_semantic_review",
                    status="completed",
                    item_count=(
                        len(semantic_review.clause_supplements)
                        + len(semantic_review.specialist_findings)
                        + len(semantic_review.consistency_findings)
                    ),
                    detail=(
                        "完成条款补全、专项语义复核、深层一致性分析与裁决复核。"
                    ),
                )
            ]
            return replace(
                report,
                summary=summary,
                recommendations=dedupe_recommendations(recommendations),
                specialist_tables=specialist_tables,
                extracted_clauses=merged_clauses,
                findings=merged_findings,
                llm_semantic_review=semantic_review,
                llm_enhanced=True,
                llm_warnings=[],
                stage_records=stage_records,
            )
        except Exception as exc:
            stage_records = list(report.stage_records) + [
                RunStageRecord(
                    stage_name="llm_semantic_review",
                    status="failed",
                    item_count=0,
                    detail=str(exc),
                )
            ]
            return replace(
                report,
                llm_enhanced=False,
                llm_warnings=[f"LLM 增强未生效：{exc}"],
                stage_records=stage_records,
            )


def _merge_recommendations(report: ReviewReport, raw_recommendations: object) -> list[Recommendation]:
    if not isinstance(raw_recommendations, list):
        return report.recommendations

    updated: list[Recommendation] = []
    seen: set[str] = set()
    for item in raw_recommendations:
        if not isinstance(item, dict):
            continue
        related_issue = str(item.get("related_issue", "")).strip()
        suggestion = str(item.get("suggestion", "")).strip()
        if not related_issue or not suggestion:
            continue
        updated.append(Recommendation(related_issue=related_issue, suggestion=suggestion))
        seen.add(related_issue)

    for item in report.recommendations:
        if item.related_issue not in seen:
            updated.append(item)
    return updated or report.recommendations


def _merge_specialist_summaries(
    specialist_tables: SpecialistTables,
    raw_summaries: object,
) -> SpecialistTables:
    if not isinstance(raw_summaries, dict):
        return specialist_tables

    merged = dict(specialist_tables.summaries)
    for key in [
        "project_structure",
        "sme_policy",
        "personnel_boundary",
        "contract_performance",
        "template_conflicts",
    ]:
        value = raw_summaries.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    specialist_tables.summaries = merged
    return specialist_tables


def _parse_semantic_review(raw_review: object) -> LLMSemanticReview:
    if not isinstance(raw_review, dict):
        return LLMSemanticReview()
    return LLMSemanticReview(
        clause_supplements=_parse_clause_supplements(raw_review.get("clause_supplements")),
        specialist_findings=_parse_findings(
            raw_review.get("specialist_findings"),
            default_dimension="专项语义复核",
        ),
        consistency_findings=_parse_findings(
            raw_review.get("consistency_findings"),
            default_dimension="深层一致性复核",
        ),
        verdict_review=str(raw_review.get("verdict_review", "")).strip(),
    )


def _parse_clause_supplements(raw_items: object) -> list[ExtractedClause]:
    if not isinstance(raw_items, list):
        return []
    results: list[ExtractedClause] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "")).strip()
        field_name = str(item.get("field_name", "")).strip()
        content = str(item.get("content", "")).strip()
        source_anchor = str(item.get("source_anchor", "")).strip() or "llm_semantic_review"
        if not category or not field_name or not content:
            continue
        results.append(
            ExtractedClause(
                category=category,
                field_name=field_name,
                content=content,
                source_anchor=source_anchor,
            )
        )
    return results


def _parse_findings(raw_items: object, default_dimension: str) -> list[Finding]:
    if not isinstance(raw_items, list):
        return []
    results: list[Finding] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        rationale = str(item.get("rationale", "")).strip()
        if not title or not rationale:
            continue
        severity = _parse_severity(item.get("severity"))
        source_anchor = str(item.get("source_anchor", "")).strip() or "llm_semantic_review"
        results.append(
            Finding(
                dimension=str(item.get("dimension", "")).strip() or default_dimension,
                finding_type=(
                    FindingType.confirmed_issue
                    if severity in {Severity.high, Severity.critical}
                    else FindingType.warning
                ),
                severity=severity,
                title=title,
                rationale=rationale,
                evidence=[Evidence(quote=title, section_hint=source_anchor)],
                confidence=0.62 if severity == Severity.medium else 0.70,
                next_action=str(item.get("next_action", "")).strip() or "结合原文条款进一步复核并修订。",
            )
        )
    return results


def _parse_severity(raw_value: object) -> Severity:
    value = str(raw_value or "").strip().lower()
    if value == "critical":
        return Severity.critical
    if value == "high":
        return Severity.high
    if value == "low":
        return Severity.low
    return Severity.medium


def _parse_json_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from dataclasses import replace

from ..adjudication import (
    build_formal_adjudication,
    build_point_applicability_checks,
    build_point_quality_gates,
    build_review_point_catalog_snapshot,
    merge_review_points,
)
from ..merge import dedupe_extracted_clauses, dedupe_findings, dedupe_recommendations
from ..models import (
    AdoptionStatus,
    ConclusionLevel,
    Evidence,
    ExtractedClause,
    Finding,
    FindingType,
    FormalAdjudication,
    FormalDisposition,
    LLMSemanticReview,
    Recommendation,
    ReviewReport,
    ReviewPointSecondReview,
    ReviewWorkItem,
    RunStageRecord,
    Severity,
    SpecialistTables,
    TaskRecord,
    TaskStatus,
)
from .client import OpenAICompatibleClient, QwenLocalConfig
from .prompts import (
    APPLICABILITY_REVIEW_SYSTEM_PROMPT,
    CLAUSE_SUPPLEMENT_SYSTEM_PROMPT,
    CONSISTENCY_REVIEW_SYSTEM_PROMPT,
    EVIDENCE_REVIEW_SYSTEM_PROMPT,
    SCORING_REVIEW_SYSTEM_PROMPT,
    SCENARIO_REVIEW_SYSTEM_PROMPT,
    REVIEW_POINT_SECOND_REVIEW_SYSTEM_PROMPT,
    ROLE_REVIEW_SYSTEM_PROMPT,
    SPECIALIST_REVIEW_SYSTEM_PROMPT,
    VERDICT_REVIEW_SYSTEM_PROMPT,
    build_applicability_review_prompt,
    build_clause_supplement_prompt,
    build_consistency_review_prompt,
        build_evidence_review_prompt,
        build_scoring_review_prompt,
        build_scenario_review_prompt,
        build_review_point_second_review_prompt,
        _select_second_review_points,
        build_role_review_prompt,
        build_specialist_review_prompt,
        build_verdict_review_prompt,
)
from .task_planner import build_dynamic_review_points, parse_dynamic_review_tasks


LLM_TASK_ORDER = [
    "llm_scenario_review",
    "llm_scoring_review",
    "llm_clause_supplement",
    "llm_role_review",
    "llm_evidence_review",
    "llm_applicability_review",
    "llm_review_point_second_review",
    "llm_specialist_review",
    "llm_consistency_review",
    "llm_verdict_review",
]

HIGH_VALUE_LLM_TASKS = {
    "llm_scenario_review",
    "llm_scoring_review",
    "llm_review_point_second_review",
}


class NullReviewEnhancer:
    def enhance(self, report: ReviewReport) -> ReviewReport:
        return report


class QwenReviewEnhancer:
    def __init__(
        self,
        client: OpenAICompatibleClient | None = None,
        timeout: float | None = None,
        task_mode: str = "precision",
    ) -> None:
        if client is not None:
            self.client = client
            self.timeout_seconds = float(
                timeout
                if timeout is not None
                else getattr(getattr(client, "config", None), "timeout", 1800.0)
            )
        else:
            config = QwenLocalConfig.from_env_or_default()
            if timeout is not None:
                config.timeout = timeout
            self.client = OpenAICompatibleClient(config)
            self.timeout_seconds = float(config.timeout)
        self.task_mode = task_mode

    def enhance(self, report: ReviewReport) -> ReviewReport:
        semantic_review = LLMSemanticReview()
        task_records = _seed_llm_task_records(report.task_records)
        specialist_tables = report.specialist_tables
        recommendations = report.recommendations
        summary = report.summary
        warnings: list[str] = []
        working_report = report

        scoring_payload, scoring_error = self._run_task(
            task_name="llm_scoring_review",
            task_records=task_records,
            system_prompt=SCORING_REVIEW_SYSTEM_PROMPT,
            user_prompt=build_scoring_review_prompt(report),
            skip_when=(not self._is_task_enabled("llm_scoring_review")) or (not _has_scoring_context(report)),
            skip_detail=self._skip_detail(
                "llm_scoring_review",
                "当前未识别到评分章节或评分相关条款，跳过评分语义分析。",
            ),
        )
        if scoring_payload:
            semantic_review.scoring_review_summary = str(
                scoring_payload.get("scoring_review_summary", "")
            ).strip()
            semantic_review.scoring_dynamic_review_tasks = parse_dynamic_review_tasks(
                scoring_payload.get("dynamic_review_tasks")
            )
            semantic_review.dynamic_review_tasks = _merge_dynamic_task_definitions(
                semantic_review.dynamic_review_tasks,
                semantic_review.scoring_dynamic_review_tasks,
            )
            if semantic_review.scoring_dynamic_review_tasks:
                working_report = _merge_dynamic_tasks_into_report(
                    report,
                    semantic_review.scoring_dynamic_review_tasks,
                )
        if scoring_error:
            warnings.append(scoring_error)

        scenario_payload, scenario_error = self._run_task(
            task_name="llm_scenario_review",
            task_records=task_records,
            system_prompt=SCENARIO_REVIEW_SYSTEM_PROMPT,
            user_prompt=build_scenario_review_prompt(working_report),
            skip_when=not self._is_task_enabled("llm_scenario_review"),
            skip_detail=self._skip_detail("llm_scenario_review", ""),
        )
        if scenario_payload:
            semantic_review.scenario_review_summary = str(
                scenario_payload.get("scenario_review_summary", "")
            ).strip()
            scenario_dynamic_tasks = parse_dynamic_review_tasks(
                scenario_payload.get("dynamic_review_tasks")
            )
            combined_dynamic_tasks = _merge_dynamic_task_definitions(
                semantic_review.scoring_dynamic_review_tasks,
                scenario_dynamic_tasks,
            )
            semantic_review.dynamic_review_tasks = combined_dynamic_tasks
            if scenario_dynamic_tasks:
                working_report = _merge_dynamic_tasks_into_report(
                    working_report,
                    scenario_dynamic_tasks,
                )
        if scenario_error:
            warnings.append(scenario_error)

        clause_payload, clause_error = self._run_task(
            task_name="llm_clause_supplement",
            task_records=task_records,
            system_prompt=CLAUSE_SUPPLEMENT_SYSTEM_PROMPT,
            user_prompt=build_clause_supplement_prompt(working_report),
            skip_when=not self._is_task_enabled("llm_clause_supplement"),
            skip_detail=self._skip_detail("llm_clause_supplement", ""),
        )
        if clause_payload:
            semantic_review.clause_supplements = _parse_clause_supplements(
                clause_payload.get("clause_supplements")
            )
        if clause_error:
            warnings.append(clause_error)

        role_payload, role_error = self._run_task(
            task_name="llm_role_review",
            task_records=task_records,
            system_prompt=ROLE_REVIEW_SYSTEM_PROMPT,
            user_prompt=build_role_review_prompt(working_report),
            skip_when=(not self._is_task_enabled("llm_role_review")) or (not working_report.review_points),
            skip_detail=self._skip_detail("llm_role_review", "当前无 ReviewPoint，跳过角色复核。"),
        )
        if role_payload:
            semantic_review.role_review_notes = _parse_notes(role_payload.get("role_review_notes"))
        if role_error:
            warnings.append(role_error)

        evidence_payload, evidence_error = self._run_task(
            task_name="llm_evidence_review",
            task_records=task_records,
            system_prompt=EVIDENCE_REVIEW_SYSTEM_PROMPT,
            user_prompt=build_evidence_review_prompt(working_report),
            skip_when=(not self._is_task_enabled("llm_evidence_review")) or (not working_report.review_points),
            skip_detail=self._skip_detail("llm_evidence_review", "当前无 ReviewPoint，跳过证据复核。"),
        )
        if evidence_payload:
            semantic_review.evidence_review_notes = _parse_notes(evidence_payload.get("evidence_review_notes"))
        if evidence_error:
            warnings.append(evidence_error)

        applicability_payload, applicability_error = self._run_task(
            task_name="llm_applicability_review",
            task_records=task_records,
            system_prompt=APPLICABILITY_REVIEW_SYSTEM_PROMPT,
            user_prompt=build_applicability_review_prompt(working_report),
            skip_when=(not self._is_task_enabled("llm_applicability_review")) or (not working_report.applicability_checks),
            skip_detail=self._skip_detail("llm_applicability_review", "当前无适法性检查结果，跳过适法性复核。"),
        )
        if applicability_payload:
            semantic_review.applicability_review_notes = _parse_notes(
                applicability_payload.get("applicability_review_notes")
            )
        if applicability_error:
            warnings.append(applicability_error)

        second_review_payload, second_review_error = self._run_second_review_batches(
            working_report,
            task_records,
        )
        if second_review_payload:
            semantic_review.review_point_second_reviews = second_review_payload
        if second_review_error:
            warnings.append(second_review_error)

        formal_adjudication = _apply_review_point_second_reviews(
            working_report.formal_adjudication,
            semantic_review.review_point_second_reviews,
        )
        overall_conclusion = _derive_conclusion_from_formal(
            working_report,
            formal_adjudication,
        )
        summary = _build_enhanced_summary(
            working_report,
            merged_findings=None,
            overall_conclusion=overall_conclusion,
            formal_adjudication=formal_adjudication,
        )

        specialist_skip = not any(
            getattr(report.specialist_tables, table_name)
            for table_name in [
                "project_structure",
                "sme_policy",
                "personnel_boundary",
                "contract_performance",
                "template_conflicts",
            ]
        )
        specialist_payload, specialist_error = self._run_task(
            task_name="llm_specialist_review",
            task_records=task_records,
            system_prompt=SPECIALIST_REVIEW_SYSTEM_PROMPT,
            user_prompt=build_specialist_review_prompt(working_report),
            skip_when=(not self._is_task_enabled("llm_specialist_review")) or specialist_skip,
            skip_detail=self._skip_detail("llm_specialist_review", "当前专项表为空，跳过专项语义复核。"),
        )
        if specialist_payload:
            semantic_review.specialist_findings = _parse_findings(
                specialist_payload.get("specialist_findings"),
                default_dimension="专项语义复核",
            )
            specialist_tables = _merge_specialist_summaries(
                specialist_tables,
                specialist_payload.get("specialist_summaries"),
            )
            recommendations = dedupe_recommendations(
                _merge_recommendations(working_report, specialist_payload.get("recommendations"))
            )
        if specialist_error:
            warnings.append(specialist_error)

        consistency_payload, consistency_error = self._run_task(
            task_name="llm_consistency_review",
            task_records=task_records,
            system_prompt=CONSISTENCY_REVIEW_SYSTEM_PROMPT,
            user_prompt=build_consistency_review_prompt(working_report),
            skip_when=(not self._is_task_enabled("llm_consistency_review")) or (not working_report.consistency_checks),
            skip_detail=self._skip_detail("llm_consistency_review", "当前一致性矩阵为空，跳过深层一致性复核。"),
        )
        if consistency_payload:
            semantic_review.consistency_findings = _parse_findings(
                consistency_payload.get("consistency_findings"),
                default_dimension="深层一致性复核",
            )
        if consistency_error:
            warnings.append(consistency_error)

        verdict_payload, verdict_error = self._run_task(
            task_name="llm_verdict_review",
            task_records=task_records,
            system_prompt=VERDICT_REVIEW_SYSTEM_PROMPT,
            user_prompt=build_verdict_review_prompt(working_report),
            skip_when=not self._is_task_enabled("llm_verdict_review"),
            skip_detail=self._skip_detail("llm_verdict_review", ""),
        )
        if verdict_payload:
            summary = str(verdict_payload.get("summary", "")).strip() or summary
            semantic_review.verdict_review = str(verdict_payload.get("verdict_review", "")).strip()
        if verdict_error:
            warnings.append(verdict_error)

        merged_clauses = dedupe_extracted_clauses(
            working_report.extracted_clauses + semantic_review.clause_supplements
        )
        merged_findings = dedupe_findings(
            working_report.findings
            + semantic_review.specialist_findings
            + semantic_review.consistency_findings
        )
        if not (verdict_payload and str(verdict_payload.get("summary", "")).strip()):
            summary = _build_enhanced_summary(
                working_report,
                merged_findings=merged_findings,
                overall_conclusion=overall_conclusion,
                formal_adjudication=formal_adjudication,
            )
        stage_records = list(working_report.stage_records) + [
            RunStageRecord(
                stage_name="llm_semantic_review",
                status="completed" if not warnings else "partial",
                item_count=(
                    len(semantic_review.dynamic_review_tasks)
                    + len(semantic_review.clause_supplements)
                    + len(semantic_review.role_review_notes)
                    + len(semantic_review.evidence_review_notes)
                    + len(semantic_review.applicability_review_notes)
                    + len(semantic_review.review_point_second_reviews)
                    + len(semantic_review.specialist_findings)
                    + len(semantic_review.consistency_findings)
                ),
                detail="已记录 LLM 角色、证据、适法性和专项语义复核子任务状态。",
            )
        ]
        llm_enhanced = any(item.status == TaskStatus.completed for item in task_records if item.task_name in LLM_TASK_ORDER)
        return replace(
            working_report,
            summary=summary,
            recommendations=recommendations,
            specialist_tables=specialist_tables,
            extracted_clauses=merged_clauses,
            findings=merged_findings,
            overall_conclusion=overall_conclusion,
            formal_adjudication=formal_adjudication,
            review_points=working_report.review_points,
            review_point_catalog=working_report.review_point_catalog,
            applicability_checks=working_report.applicability_checks,
            quality_gates=working_report.quality_gates,
            high_risk_review_items=_build_high_risk_review_items(merged_findings),
            pending_confirmation_items=_build_pending_confirmation_items(
                merged_findings,
                merged_clauses,
                working_report.manual_review_queue,
            ),
            llm_semantic_review=semantic_review,
            llm_enhanced=llm_enhanced,
            llm_warnings=warnings,
            stage_records=stage_records,
            task_records=task_records,
        )

    def _is_task_enabled(self, task_name: str) -> bool:
        if self.task_mode == "full":
            return True
        return task_name in HIGH_VALUE_LLM_TASKS

    def _skip_detail(self, task_name: str, fallback: str) -> str:
        if self._is_task_enabled(task_name):
            return fallback
        return "默认精准模式下跳过低价值 LLM 子任务。"

    def _run_task(
        self,
        task_name: str,
        task_records: list[TaskRecord],
        system_prompt: str,
        user_prompt: str,
        skip_when: bool,
        skip_detail: str,
    ) -> tuple[dict | None, str | None]:
        record = _find_task_record(task_records, task_name)
        started_at = datetime.now(timezone.utc)
        timing_context = _build_task_timing_context(started_at, self.timeout_seconds)
        if skip_when:
            record.status = TaskStatus.skipped
            record.detail = _format_task_detail(skip_detail or "任务已跳过。", timing_context)
            record.item_count = 0
            return None, None

        record.status = TaskStatus.running
        record.detail = _format_task_detail("任务执行中。", timing_context)
        try:
            raw = self.client.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            parsed = _parse_json_response(raw)
            record.status = TaskStatus.completed
            elapsed_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
            record.detail = _format_task_detail(
                "任务已完成。",
                timing_context,
                elapsed_seconds=elapsed_seconds,
            )
            record.item_count = _count_task_items(task_name, parsed)
            return parsed, None
        except Exception as exc:
            record.status = _infer_task_status(exc)
            record.detail = _format_task_detail(
                f"任务执行失败：{exc}",
                timing_context,
            )
            record.item_count = 0
            return None, f"{task_name} 未生效：{exc}"

    def _run_second_review_batches(
        self,
        report: ReviewReport,
        task_records: list[TaskRecord],
        batch_size: int = 1,
    ) -> tuple[list[ReviewPointSecondReview] | None, str | None]:
        task_name = "llm_review_point_second_review"
        record = _find_task_record(task_records, task_name)
        started_at = datetime.now(timezone.utc)
        timing_context = _build_task_timing_context(started_at, self.timeout_seconds)
        if (not self._is_task_enabled(task_name)) or (not report.review_points):
            record.status = TaskStatus.skipped
            record.detail = _format_task_detail(
                self._skip_detail(task_name, "当前无 ReviewPoint，跳过审查点二审。"),
                timing_context,
            )
            record.item_count = 0
            return None, None

        selected_points = _select_second_review_points(report)
        if not selected_points:
            record.status = TaskStatus.skipped
            record.detail = _format_task_detail("当前无可用于二审的 ReviewPoint。", timing_context)
            record.item_count = 0
            return None, None

        record.status = TaskStatus.running
        record.detail = _format_task_detail(
            f"按批次执行审查点二审，共 {len(selected_points)} 个审查点。",
            timing_context,
        )
        parsed_reviews: list[ReviewPointSecondReview] = []
        errors: list[str] = []

        for index in range(0, len(selected_points), batch_size):
            batch = selected_points[index : index + batch_size]
            try:
                raw = self.client.generate_text(
                    system_prompt=REVIEW_POINT_SECOND_REVIEW_SYSTEM_PROMPT,
                    user_prompt=build_review_point_second_review_prompt(report, batch),
                )
                parsed = _parse_json_response(raw)
                parsed_reviews.extend(
                    _parse_review_point_second_reviews(parsed.get("review_point_second_reviews"))
                )
            except Exception as exc:
                errors.append(str(exc))

        if parsed_reviews:
            record.status = TaskStatus.completed
            elapsed_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
            record.detail = (
                _format_task_detail(
                    f"分批二审完成，成功 {len(parsed_reviews)} 条。",
                    timing_context,
                    elapsed_seconds=elapsed_seconds,
                )
                + (f" 部分批次失败：{'; '.join(errors[:2])}" if errors else "")
            )
            record.item_count = len(parsed_reviews)
            return parsed_reviews, None if not errors else f"{task_name} 部分批次未生效：{'; '.join(errors[:2])}"

        record.status = _infer_task_status(Exception(errors[0] if errors else "no second review results"))
        record.detail = _format_task_detail(
            errors[0] if errors else "二审未返回结果。",
            timing_context,
        )
        record.item_count = 0
        return None, f"{task_name} 未生效：{record.detail}"


def _seed_llm_task_records(existing_records: list[TaskRecord]) -> list[TaskRecord]:
    results = list(existing_records)
    for task_name in LLM_TASK_ORDER:
        if not any(item.task_name == task_name for item in results):
            results.append(
                TaskRecord(
                    task_name=task_name,
                    status=TaskStatus.pending,
                    detail="等待执行。",
                    item_count=None,
                )
            )
    return results


def _find_task_record(task_records: list[TaskRecord], task_name: str) -> TaskRecord:
    for item in task_records:
        if item.task_name == task_name:
            return item
    task_record = TaskRecord(task_name=task_name, status=TaskStatus.pending, detail="等待执行。")
    task_records.append(task_record)
    return task_record


def _build_task_timing_context(started_at: datetime, timeout_seconds: float) -> str:
    deadline_at = started_at + timedelta(seconds=timeout_seconds)
    return f"预算 {timeout_seconds:.1f} 秒，截止 {deadline_at.isoformat(timespec='seconds')}"


def _format_task_detail(
    headline: str,
    timing_context: str,
    *,
    elapsed_seconds: float | None = None,
) -> str:
    parts = [headline.rstrip("。"), timing_context]
    if elapsed_seconds is not None:
        parts.append(f"耗时 {elapsed_seconds:.2f} 秒")
    return "。".join(parts) + "。"


def _count_task_items(task_name: str, parsed: dict) -> int:
    if task_name == "llm_scenario_review":
        return len(parsed.get("dynamic_review_tasks", []))
    if task_name == "llm_scoring_review":
        return len(parsed.get("dynamic_review_tasks", []))
    if task_name == "llm_clause_supplement":
        return len(parsed.get("clause_supplements", []))
    if task_name == "llm_specialist_review":
        return len(parsed.get("specialist_findings", []))
    if task_name == "llm_consistency_review":
        return len(parsed.get("consistency_findings", []))
    if task_name == "llm_role_review":
        return len(parsed.get("role_review_notes", []))
    if task_name == "llm_evidence_review":
        return len(parsed.get("evidence_review_notes", []))
    if task_name == "llm_applicability_review":
        return len(parsed.get("applicability_review_notes", []))
    if task_name == "llm_review_point_second_review":
        return len(parsed.get("review_point_second_reviews", []))
    if task_name == "llm_verdict_review":
        return 1 if parsed.get("verdict_review") or parsed.get("summary") else 0
    return 0


def _has_scoring_context(report: ReviewReport) -> bool:
    keywords = ("评分", "评审", "分值", "方案", "证书", "检测报告", "财务", "样品")
    return any(
        any(token in f"{item.category}{item.field_name}{item.content}" for token in keywords)
        for item in report.extracted_clauses
    )


def _merge_dynamic_task_definitions(
    existing: list,
    incoming: list,
) -> list:
    merged = list(existing)
    seen = {(item.catalog_id, item.title) for item in merged}
    for item in incoming:
        key = (item.catalog_id, item.title)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _merge_dynamic_tasks_into_report(
    report: ReviewReport,
    dynamic_tasks: list,
) -> ReviewReport:
    if not dynamic_tasks:
        return report
    dynamic_points = build_dynamic_review_points(
        dynamic_tasks,
        report.extracted_clauses,
    )
    merged_points = merge_review_points(report.review_points + dynamic_points)
    applicability_checks = build_point_applicability_checks(
        merged_points,
        report.extracted_clauses,
        report.parse_result.review_point_instances,
    )
    quality_gates = build_point_quality_gates(merged_points, report.extracted_clauses)
    return replace(
        report,
        review_points=merged_points,
        review_point_catalog=build_review_point_catalog_snapshot(merged_points),
        applicability_checks=applicability_checks,
        quality_gates=quality_gates,
        formal_adjudication=build_formal_adjudication(
            merged_points,
            applicability_checks,
            quality_gates,
            report.parse_result.text,
            report.extracted_clauses,
            report.parse_result.tables,
            report.parse_result.review_point_instances,
        ),
    )


def _infer_task_status(exc: Exception) -> TaskStatus:
    message = str(exc).lower()
    if "timed out" in message or "timeout" in message:
        return TaskStatus.timed_out
    return TaskStatus.failed


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
        source_anchor = str(item.get("source_anchor", "")).strip() or "llm_clause_supplement"
        adoption_status = _parse_adoption_status(item.get("adoption_status"))
        review_note = str(item.get("review_note", "")).strip()
        if not category or not field_name or not content:
            continue
        results.append(
            ExtractedClause(
                category=category,
                field_name=field_name,
                content=content,
                source_anchor=source_anchor,
                adoption_status=adoption_status,
                review_note=review_note,
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
        source_anchor = str(item.get("source_anchor", "")).strip() or default_dimension
        confidence = _parse_confidence(item.get("confidence"), severity)
        adoption_status = _parse_adoption_status(item.get("adoption_status"), confidence)
        review_note = str(item.get("review_note", "")).strip()
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
                confidence=confidence,
                next_action=str(item.get("next_action", "")).strip() or "结合原文条款进一步复核并修订。",
                adoption_status=adoption_status,
                review_note=review_note,
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


def _parse_confidence(raw_value: object, severity: Severity) -> float:
    try:
        if raw_value not in {None, ""}:
            return float(raw_value)
    except (TypeError, ValueError):
        pass
    return 0.62 if severity == Severity.medium else 0.70


def _parse_adoption_status(
    raw_value: object,
    confidence: float | None = None,
) -> AdoptionStatus:
    value = str(raw_value or "").strip()
    if value in {AdoptionStatus.direct.value, "direct"}:
        return AdoptionStatus.direct
    if value in {AdoptionStatus.manual.value, "manual"}:
        return AdoptionStatus.manual
    if confidence is not None and confidence < 0.75:
        return AdoptionStatus.manual
    return AdoptionStatus.direct


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


def _parse_notes(raw_items: object) -> list[str]:
    if not isinstance(raw_items, list):
        return []
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _apply_review_point_second_reviews(
    adjudications: list[FormalAdjudication],
    second_reviews: list[ReviewPointSecondReview],
) -> list[FormalAdjudication]:
    if not second_reviews:
        return adjudications
    review_index = {item.point_id: item for item in second_reviews}
    updated: list[FormalAdjudication] = []
    for adjudication in adjudications:
        review = review_index.get(adjudication.point_id)
        if review is None:
            updated.append(adjudication)
            continue
        suggested = _parse_formal_disposition(review.suggested_disposition)
        if suggested is None:
            updated.append(adjudication)
            continue
        if not _can_apply_second_review_override(adjudication.disposition, suggested, review.adoption_status):
            updated.append(adjudication)
            continue
        intensity_note = f"；强度判断：{review.intensity_judgment}" if review.intensity_judgment else ""
        primary_note = f"；主证据判断：{review.primary_evidence_judgment}" if review.primary_evidence_judgment else ""
        supporting_note = (
            f"；辅助证据判断：{review.supporting_evidence_judgment}"
            if review.supporting_evidence_judgment
            else ""
        )
        recommended_for_review = adjudication.recommended_for_review
        review_reason = adjudication.review_reason
        if suggested == FormalDisposition.manual_confirmation and review.intensity_judgment in {"证据不足", "一般要求"}:
            recommended_for_review = True
            review_reason = review_reason or "LLM二审认为当前更适合作为建议复核，不宜直接进入正式高风险。"
        if "应降为辅助证据" in review.primary_evidence_judgment or "需重新选择主证据" in review.primary_evidence_judgment:
            recommended_for_review = True
            review_reason = review_reason or "LLM二审认为当前主证据代表性不足，建议转入复核清单并重新核定主证据。"
        updated.append(
            FormalAdjudication(
                point_id=adjudication.point_id,
                catalog_id=adjudication.catalog_id,
                title=adjudication.title,
                disposition=suggested,
                rationale=f"{adjudication.rationale}；LLM二审：{review.rationale}{intensity_note}{primary_note}{supporting_note}",
                included_in_formal=suggested == FormalDisposition.include,
                section_hint=adjudication.section_hint,
                primary_quote=adjudication.primary_quote,
                evidence_sufficient=adjudication.evidence_sufficient,
                legal_basis_applicable=adjudication.legal_basis_applicable,
                applicability_summary=adjudication.applicability_summary,
                quality_gate_status=adjudication.quality_gate_status,
                recommended_for_review=recommended_for_review,
                review_reason=review_reason,
            )
        )
    return updated


def _parse_formal_disposition(raw_value: str) -> FormalDisposition | None:
    value = (raw_value or "").strip()
    for item in FormalDisposition:
        if item.value == value:
            return item
    return None


def _can_apply_second_review_override(
    current: FormalDisposition,
    suggested: FormalDisposition,
    adoption_status: AdoptionStatus,
) -> bool:
    if adoption_status == AdoptionStatus.direct:
        return True
    rank = {
        FormalDisposition.include: 2,
        FormalDisposition.manual_confirmation: 1,
        FormalDisposition.filtered_out: 0,
    }
    return rank[suggested] <= rank[current]


def _derive_conclusion_from_formal(
    report: ReviewReport,
    formal_adjudication: list[FormalAdjudication],
) -> ConclusionLevel:
    point_index = {item.point_id: item for item in report.review_points}
    included = [
        item for item in formal_adjudication if item.included_in_formal
    ]
    manual = [
        item for item in formal_adjudication if item.disposition == FormalDisposition.manual_confirmation
    ]
    if any(point_index.get(item.point_id) and point_index[item.point_id].severity == Severity.critical for item in included):
        return ConclusionLevel.reject
    if len(included) >= 2:
        return ConclusionLevel.reject
    if included:
        return ConclusionLevel.revise
    if manual:
        return ConclusionLevel.optimize
    return report.overall_conclusion


def _build_enhanced_summary(
    report: ReviewReport,
    merged_findings: list[Finding] | None,
    overall_conclusion: ConclusionLevel,
    formal_adjudication: list[FormalAdjudication],
) -> str:
    findings = merged_findings if merged_findings is not None else report.findings
    issue_count = sum(
        1
        for item in findings
        if item.finding_type
        in {
            FindingType.confirmed_issue,
            FindingType.warning,
            FindingType.manual_review_required,
            FindingType.missing_evidence,
        }
    )
    manual_count = sum(
        1 for item in formal_adjudication if item.disposition == FormalDisposition.manual_confirmation
    )
    if manual_count:
        return (
            f"审查结论为“{overall_conclusion.value}”。共生成 {len(findings)} 条审查结果，"
            f"其中 {issue_count} 条需要重点关注，{manual_count} 条建议进一步复核。"
        )
    return (
        f"审查结论为“{overall_conclusion.value}”。共生成 {len(findings)} 条审查结果，"
        f"其中 {issue_count} 条需要关注。"
    )


def _parse_review_point_second_reviews(raw_items: object) -> list[ReviewPointSecondReview]:
    if not isinstance(raw_items, list):
        return []
    results: list[ReviewPointSecondReview] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        point_id = str(item.get("point_id", "")).strip()
        title = str(item.get("title", "")).strip()
        rationale = str(item.get("rationale", "")).strip()
        if not point_id or not title or not rationale:
            continue
        results.append(
            ReviewPointSecondReview(
                point_id=point_id,
                title=title,
                role_judgment=str(item.get("role_judgment", "")).strip(),
                evidence_judgment=str(item.get("evidence_judgment", "")).strip(),
                primary_evidence_judgment=str(item.get("primary_evidence_judgment", "")).strip(),
                supporting_evidence_judgment=str(item.get("supporting_evidence_judgment", "")).strip(),
                applicability_judgment=str(item.get("applicability_judgment", "")).strip(),
                intensity_judgment=str(item.get("intensity_judgment", "")).strip(),
                suggested_disposition=str(item.get("suggested_disposition", "")).strip(),
                rationale=rationale,
                adoption_status=_parse_adoption_status(item.get("adoption_status")),
            )
        )
    return results


def _build_high_risk_review_items(findings: list[Finding]) -> list[ReviewWorkItem]:
    items: list[ReviewWorkItem] = []
    for finding in findings:
        if finding.severity not in {Severity.high, Severity.critical}:
            continue
        items.append(
            ReviewWorkItem(
                item_type="finding",
                title=finding.title,
                severity=finding.severity.value,
                source=finding.dimension,
                reason=finding.rationale,
                action=finding.next_action,
            )
        )
    return items


def _build_pending_confirmation_items(
    findings: list[Finding],
    clauses: list[ExtractedClause],
    manual_review_queue: list[str],
) -> list[ReviewWorkItem]:
    items: list[ReviewWorkItem] = []
    seen_titles: set[str] = set()

    for finding in findings:
        if finding.adoption_status != AdoptionStatus.manual:
            continue
        title = finding.title.strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        items.append(
            ReviewWorkItem(
                item_type="finding",
                title=title,
                severity=finding.severity.value,
                source=finding.dimension,
                reason=finding.review_note or finding.rationale,
                action=finding.next_action or "结合原文与上下文补充人工确认。",
            )
        )

    for clause in clauses:
        if clause.adoption_status != AdoptionStatus.manual:
            continue
        title = f"{clause.field_name}待确认"
        if title in seen_titles:
            continue
        seen_titles.add(title)
        items.append(
            ReviewWorkItem(
                item_type="clause",
                title=title,
                severity="medium",
                source=clause.category,
                reason=clause.review_note or clause.content,
                action="回到原文对应位置确认条款语义和适用范围。",
            )
        )

    for title in manual_review_queue:
        if title in seen_titles:
            continue
        seen_titles.add(title)
        items.append(
            ReviewWorkItem(
                item_type="queue",
                title=title,
                severity="medium",
                source="manual_review_queue",
                reason="基础筛查阶段已标记为需人工复核。",
                action="补充附件、上下文或外部材料后再定性。",
            )
        )

    return items

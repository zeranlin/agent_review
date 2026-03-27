from __future__ import annotations

import traceback

from ..engine import TenderReviewEngine
from ..header_info import resolve_header_info
from ..llm import QwenReviewEnhancer
from ..models import ReviewMode, ReviewReport, TaskStatus
from ..outputs import write_review_artifacts
from ..reporting import render_reviewer_report


REQUIRED_LLM_TASKS = (
    "llm_scenario_review",
    "llm_scoring_review",
    "llm_review_point_second_review",
)


def run_review_job(
    job,
    *,
    llm_timeout: float,
    engine_cls=TenderReviewEngine,
    enhancer_cls=QwenReviewEnhancer,
) -> None:
    enhancer = enhancer_cls(timeout=llm_timeout)
    base_engine = engine_cls(review_mode=ReviewMode.fast)
    enhanced_engine = engine_cls(review_enhancer=enhancer, review_mode=ReviewMode.enhanced)

    base_report = base_engine.review_file(job.upload_path)
    report = enhanced_engine.review_file(job.upload_path)
    ensure_complete_enhanced_run(report)
    bundle = write_review_artifacts(report=report, base_report=base_report)
    reviewer_markdown = render_reviewer_report(report)
    header_info = resolve_header_info(report).to_dict()
    document_profile = report.parse_result.document_profile.to_dict() if report.parse_result.document_profile else {}
    planning_summary = report.review_planning_contract.to_dict() if report.review_planning_contract else {}
    llm_tasks = [item.to_dict() for item in report.task_records if item.task_name.startswith("llm_")]
    artifact_paths = {
        "reviewer_report": bundle.reviewer_report_path,
        "evaluation_summary": bundle.evaluation_summary_path,
        "document_profile": bundle.document_profile_path,
        "domain_profile_match": bundle.domain_profile_match_path,
        "review_point_trace": bundle.review_point_trace_path,
        "llm_tasks": bundle.llm_tasks_path,
        "run_manifest": bundle.manifest_path,
        "high_risk_review": bundle.high_risk_review_path,
        "pending_confirmation": bundle.pending_confirmation_path,
        "enhancement_trace": bundle.enhancement_trace_path,
        "enhanced_report_json": bundle.final_json_path,
        "enhanced_report_md": bundle.final_markdown_path,
        "formal_review_opinion": bundle.formal_review_opinion_path,
        "opinion_letter": bundle.opinion_letter_path,
    }

    job.status = "completed"
    job.review_mode = report.review_mode.value
    job.overall_conclusion = report.overall_conclusion.value
    job.run_dir = bundle.run_dir
    job.reviewer_report_path = bundle.reviewer_report_path
    job.reviewer_report_markdown = reviewer_markdown
    job.header_info = header_info
    job.document_profile = document_profile
    job.planning_summary = planning_summary
    job.domain_profile_candidates = document_profile.get("domain_profile_candidates", [])
    job.high_risk_items = [item.to_dict() for item in report.high_risk_review_items]
    job.pending_confirmation_items = [item.to_dict() for item in report.pending_confirmation_items]
    job.llm_tasks = llm_tasks
    job.llm_status = {
        "enhanced": report.llm_enhanced,
        "warnings": report.llm_warnings,
        "task_count": len(llm_tasks),
    }
    job.artifact_paths = artifact_paths


def ensure_complete_enhanced_run(report: ReviewReport) -> None:
    task_map = {item.task_name: item for item in report.task_records}
    missing = [
        name
        for name in REQUIRED_LLM_TASKS
        if task_map.get(name) is None or task_map[name].status != TaskStatus.completed
    ]
    if missing:
        raise RuntimeError(f"增强审查未完整完成：{format_llm_task_state_summary(report)}")


def format_llm_task_state_summary(report: ReviewReport) -> str:
    task_map = {item.task_name: item for item in report.task_records}
    segments: list[str] = []
    for name in REQUIRED_LLM_TASKS:
        record = task_map.get(name)
        if record is None:
            segments.append(f"{name}=missing（未生成任务记录）")
            continue
        detail = record.detail.strip() or "无详情"
        segments.append(f"{name}={record.status.value}（{detail}）")
    return "; ".join(segments)


def format_job_exception(exc: Exception) -> str:
    return f"{exc}\n\n{traceback.format_exc()}"

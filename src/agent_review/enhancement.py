from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from queue import Empty, Queue
from threading import Thread
from time import monotonic

from .models import ReviewMode, ReviewReport, RunStageRecord


def run_review_enhancement_with_watchdog(
    base_report: ReviewReport,
    enhancer: object,
    timeout_seconds: float,
) -> tuple[ReviewReport, dict[str, object]]:
    enhancement_input = replace(deepcopy(base_report), review_mode=ReviewMode.enhanced)
    result_queue: Queue[tuple[str, object]] = Queue(maxsize=1)
    started_at = monotonic()
    started_clock = datetime.now(timezone.utc)
    deadline_at = started_clock + timedelta(seconds=timeout_seconds)

    def _worker() -> None:
        try:
            result_queue.put(("ok", enhancer.enhance(enhancement_input)))
        except Exception as exc:  # noqa: BLE001
            result_queue.put(("error", exc))

    Thread(target=_worker, daemon=True).start()

    try:
        kind, payload = result_queue.get(timeout=timeout_seconds)
    except Empty:
        elapsed_seconds = monotonic() - started_at
        warning = (
            f"LLM 增强在 {timeout_seconds:.1f} 秒预算内未完成，"
            f"截止 {deadline_at.isoformat(timespec='seconds')}，已回退到基础报告。"
        )
        fallback_report = build_fallback_enhanced_report(base_report, warning, status="timed_out")
        return fallback_report, build_enhancement_trace(
            base_report=base_report,
            report=fallback_report,
            outcome="timed_out",
            timeout_seconds=timeout_seconds,
            elapsed_seconds=elapsed_seconds,
            started_at=started_clock,
            warning=warning,
        )

    elapsed_seconds = monotonic() - started_at
    if kind == "error":
        error = payload if isinstance(payload, Exception) else Exception(str(payload))
        warning = (
            f"LLM 增强执行失败（预算 {timeout_seconds:.1f} 秒，"
            f"截止 {deadline_at.isoformat(timespec='seconds')}），已回退到基础报告：{error}"
        )
        fallback_report = build_fallback_enhanced_report(base_report, warning, status="failed")
        return fallback_report, build_enhancement_trace(
            base_report=base_report,
            report=fallback_report,
            outcome="failed",
            timeout_seconds=timeout_seconds,
            elapsed_seconds=elapsed_seconds,
            started_at=started_clock,
            warning=warning,
            error=error,
        )

    if not isinstance(payload, ReviewReport):
        warning = (
            f"LLM 增强返回了非预期结果（预算 {timeout_seconds:.1f} 秒，"
            f"截止 {deadline_at.isoformat(timespec='seconds')}），已回退到基础报告。"
        )
        fallback_report = build_fallback_enhanced_report(base_report, warning, status="failed")
        return fallback_report, build_enhancement_trace(
            base_report=base_report,
            report=fallback_report,
            outcome="failed",
            timeout_seconds=timeout_seconds,
            elapsed_seconds=elapsed_seconds,
            started_at=started_clock,
            warning=warning,
            error=TypeError("unexpected enhancer result"),
        )

    report = payload
    enhanced_report = attach_enhancement_stage(
        report,
        status="completed",
        detail=(
            f"LLM 增强在 {elapsed_seconds:.2f} 秒内完成，"
            f"预算 {timeout_seconds:.1f} 秒，截止 {deadline_at.isoformat(timespec='seconds')}。"
        ),
    )
    return enhanced_report, build_enhancement_trace(
        base_report=base_report,
        report=enhanced_report,
        outcome="completed",
        timeout_seconds=timeout_seconds,
        elapsed_seconds=elapsed_seconds,
        started_at=started_clock,
    )


def build_fallback_enhanced_report(
    base_report: ReviewReport,
    warning: str,
    *,
    status: str,
) -> ReviewReport:
    return attach_enhancement_stage(
        replace(
            base_report,
            review_mode=ReviewMode.enhanced,
            llm_warnings=[*base_report.llm_warnings, warning],
        ),
        status=status,
        detail=warning,
    )


def attach_enhancement_stage(
    report: ReviewReport,
    *,
    status: str,
    detail: str,
) -> ReviewReport:
    return replace(
        report,
        stage_records=[
            *report.stage_records,
            RunStageRecord(
                stage_name="llm_enhancement_watchdog",
                status=status,
                item_count=0,
                detail=detail,
            ),
        ],
    )


def build_enhancement_trace(
    *,
    base_report: ReviewReport,
    report: ReviewReport,
    outcome: str,
    timeout_seconds: float,
    elapsed_seconds: float,
    started_at: datetime,
    fallback_applied: bool | None = None,
    warning: str | None = None,
    error: Exception | None = None,
) -> dict[str, object]:
    deadline_at = started_at + timedelta(seconds=timeout_seconds)
    return {
        "document_name": report.file_info.document_name,
        "requested_mode": "enhanced",
        "base_mode": base_report.review_mode.value,
        "final_mode": report.review_mode.value,
        "outcome": outcome,
        "budget_seconds": timeout_seconds,
        "started_at": started_at.isoformat(timespec="seconds"),
        "deadline_at": deadline_at.isoformat(timespec="seconds"),
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "remaining_budget_seconds": round(max(0.0, timeout_seconds - elapsed_seconds), 3),
        "fallback_applied": (outcome != "completed") if fallback_applied is None else fallback_applied,
        "llm_enhanced": report.llm_enhanced,
        "llm_warnings": report.llm_warnings,
        "warning": warning or "",
        "error": str(error) if error else "",
        "task_records": [
            item.to_dict()
            for item in report.task_records
            if item.task_name.startswith("llm_")
        ],
        "stage_records": [
            item.to_dict()
            for item in report.stage_records
            if item.stage_name.startswith("llm_")
        ],
    }

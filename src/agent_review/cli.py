from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from queue import Empty, Queue
import sys
from threading import Thread
from time import monotonic

from .engine import TenderReviewEngine
from .llm import QwenReviewEnhancer
from .models import ReviewMode, ReviewReport, RunStageRecord
from .outputs import write_review_artifacts
from .reporting import (
    render_formal_review_opinion,
    render_json,
    render_markdown,
    render_opinion_letter,
    render_reviewer_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review a tender document for compliance risks.")
    parser.add_argument(
        "--input",
        required=True,
        action="append",
        help="待审查文件路径。可重复传入，用于多文件联合审查。",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json", "opinion", "formal", "reviewer"),
        default="markdown",
        help="终端输出格式。",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="启用本地 OpenAI 兼容 LLM，对总体结论和修改建议做增强。",
    )
    parser.add_argument(
        "--mode",
        choices=(ReviewMode.fast.value, ReviewMode.enhanced.value),
        default=ReviewMode.fast.value,
        help="运行模式：fast 只输出基础报告，enhanced 在基础报告上做 LLM 增强。",
    )
    parser.add_argument(
        "--artifacts-dir",
        help="审查产物输出目录。默认写入 runs/<文件名>/。",
    )
    parser.add_argument(
        "--llm-timeout",
        type=float,
        default=60.0,
        help="LLM 单次调用超时时间（秒）。",
    )
    return parser


def _run_enhancement_with_watchdog(base_report, enhancer, timeout_seconds: float):
    enhancement_input = replace(deepcopy(base_report), review_mode=ReviewMode.enhanced)
    result_queue: Queue[tuple[str, object]] = Queue(maxsize=1)
    started_at = monotonic()

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
        warning = f"LLM 增强在 {timeout_seconds:.1f} 秒内未完成，已回退到基础报告。"
        fallback_report = _build_fallback_enhanced_report(base_report, warning, status="timed_out")
        return fallback_report, _build_enhancement_trace(
            base_report=base_report,
            report=fallback_report,
            outcome="timed_out",
            timeout_seconds=timeout_seconds,
            elapsed_seconds=elapsed_seconds,
            warning=warning,
        )

    elapsed_seconds = monotonic() - started_at
    if kind == "error":
        error = payload if isinstance(payload, Exception) else Exception(str(payload))
        warning = f"LLM 增强执行失败，已回退到基础报告：{error}"
        fallback_report = _build_fallback_enhanced_report(base_report, warning, status="failed")
        return fallback_report, _build_enhancement_trace(
            base_report=base_report,
            report=fallback_report,
            outcome="failed",
            timeout_seconds=timeout_seconds,
            elapsed_seconds=elapsed_seconds,
            warning=warning,
            error=error,
        )

    if not isinstance(payload, ReviewReport):
        warning = "LLM 增强返回了非预期结果，已回退到基础报告。"
        fallback_report = _build_fallback_enhanced_report(base_report, warning, status="failed")
        return fallback_report, _build_enhancement_trace(
            base_report=base_report,
            report=fallback_report,
            outcome="failed",
            timeout_seconds=timeout_seconds,
            elapsed_seconds=elapsed_seconds,
            warning=warning,
            error=TypeError("unexpected enhancer result"),
        )

    report = payload
    enhanced_report = _attach_enhancement_stage(
        report,
        status="completed",
        detail=f"LLM 增强在 {elapsed_seconds:.2f} 秒内完成。",
    )
    return enhanced_report, _build_enhancement_trace(
        base_report=base_report,
        report=enhanced_report,
        outcome="completed",
        timeout_seconds=timeout_seconds,
        elapsed_seconds=elapsed_seconds,
    )


def _build_fallback_enhanced_report(base_report, warning: str, status: str):
    return _attach_enhancement_stage(
        replace(
            base_report,
            review_mode=ReviewMode.enhanced,
            llm_warnings=[*base_report.llm_warnings, warning],
        ),
        status=status,
        detail=warning,
    )


def _attach_enhancement_stage(report, *, status: str, detail: str):
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


def _build_enhancement_trace(
    *,
    base_report,
    report,
    outcome: str,
    timeout_seconds: float,
    elapsed_seconds: float,
    warning: str | None = None,
    error: Exception | None = None,
) -> dict[str, object]:
    return {
        "document_name": report.file_info.document_name,
        "requested_mode": "enhanced",
        "base_mode": base_report.review_mode.value,
        "final_mode": report.review_mode.value,
        "outcome": outcome,
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "fallback_applied": outcome != "completed",
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


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    review_mode = ReviewMode(args.mode)
    enhanced_enabled = args.use_llm or review_mode == ReviewMode.enhanced
    review_target = args.input if len(args.input) > 1 else args.input[0]

    base_engine = TenderReviewEngine(review_mode=ReviewMode.fast)
    if isinstance(review_target, list):
        base_report = base_engine.review_files(review_target)
    else:
        base_report = base_engine.review_file(review_target)

    enhancement_trace = None
    if enhanced_enabled:
        write_review_artifacts(
            report=base_report,
            base_report=base_report,
            output_dir=args.artifacts_dir,
            enhancement_trace={
                "document_name": base_report.file_info.document_name,
                "requested_mode": "enhanced",
                "base_mode": base_report.review_mode.value,
                "final_mode": base_report.review_mode.value,
                "outcome": "pending",
                "timeout_seconds": args.llm_timeout,
                "elapsed_seconds": 0.0,
                "fallback_applied": False,
                "llm_enhanced": base_report.llm_enhanced,
                "llm_warnings": base_report.llm_warnings,
                "warning": "",
                "error": "",
                "task_records": [],
                "stage_records": [],
            },
        )
    if enhanced_enabled:
        enhancer = QwenReviewEnhancer(timeout=args.llm_timeout)
        report, enhancement_trace = _run_enhancement_with_watchdog(
            base_report,
            enhancer,
            args.llm_timeout,
        )
    else:
        report = base_report

    write_review_artifacts(
        report=report,
        base_report=base_report,
        output_dir=args.artifacts_dir,
        enhancement_trace=enhancement_trace,
    )

    if args.format == "json":
        sys.stdout.write(render_json(report))
    elif args.format == "formal":
        sys.stdout.write(render_formal_review_opinion(report))
    elif args.format == "opinion":
        sys.stdout.write(render_opinion_letter(report))
    elif args.format == "reviewer":
        sys.stdout.write(render_reviewer_report(report))
    else:
        sys.stdout.write(render_markdown(report))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

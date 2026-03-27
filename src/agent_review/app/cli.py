from __future__ import annotations

import argparse
from datetime import datetime, timezone
import sys

from ..enhancement import build_enhancement_trace, run_review_enhancement_with_watchdog
from ..engine import TenderReviewEngine
from ..llm import QwenReviewEnhancer
from ..models import ReviewMode
from ..outputs import write_review_artifacts
from ..structure import QwenParserSemanticAssistant
from ..reporting import (
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
        default=ReviewMode.enhanced.value,
        help="运行模式：默认 enhanced，可显式切换为 fast 关闭增强链。",
    )
    parser.add_argument(
        "--artifacts-dir",
        help="审查产物输出目录。默认写入 runs/<文件名>/。",
    )
    parser.add_argument(
        "--llm-timeout",
        type=float,
        default=1800.0,
        help="LLM 单次调用超时时间（秒），默认 1800。",
    )
    parser.add_argument(
        "--parser-llm-assist",
        action="store_true",
        default=True,
        help="启用 parser 低置信度歧义消解。默认开启。",
    )
    parser.add_argument(
        "--disable-parser-llm-assist",
        dest="parser_llm_assist",
        action="store_false",
        help="显式关闭 parser 低置信度歧义消解。",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    review_mode = ReviewMode(args.mode)
    enhanced_enabled = args.use_llm or review_mode == ReviewMode.enhanced
    review_target = args.input if len(args.input) > 1 else args.input[0]

    parser_semantic_assistant = (
        QwenParserSemanticAssistant(timeout=args.llm_timeout) if args.parser_llm_assist else None
    )
    base_engine = TenderReviewEngine(
        review_mode=ReviewMode.fast,
        parser_semantic_assistant=parser_semantic_assistant,
    )
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
            enhancement_trace=build_enhancement_trace(
                base_report=base_report,
                report=base_report,
                outcome="pending",
                timeout_seconds=args.llm_timeout,
                elapsed_seconds=0.0,
                started_at=datetime.now(timezone.utc),
                fallback_applied=False,
            ),
        )
    if enhanced_enabled:
        enhancer = QwenReviewEnhancer(timeout=args.llm_timeout)
        report, enhancement_trace = run_review_enhancement_with_watchdog(
            base_report=base_report,
            enhancer=enhancer,
            timeout_seconds=args.llm_timeout,
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

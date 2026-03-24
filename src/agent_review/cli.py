from __future__ import annotations

import argparse
import sys

from .engine import TenderReviewEngine
from .llm import QwenReviewEnhancer
from .models import ReviewMode
from .outputs import write_review_artifacts
from .reporting import render_json, render_markdown, render_opinion_letter


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
        choices=("markdown", "json", "opinion"),
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

    if enhanced_enabled:
        enhancer = QwenReviewEnhancer(timeout=args.llm_timeout)
        engine = TenderReviewEngine(review_enhancer=enhancer, review_mode=ReviewMode.enhanced)
        if isinstance(review_target, list):
            report = engine.review_files(review_target)
        else:
            report = engine.review_file(review_target)
    else:
        report = base_report

    write_review_artifacts(report=report, base_report=base_report, output_dir=args.artifacts_dir)

    if args.format == "json":
        sys.stdout.write(render_json(report))
    elif args.format == "opinion":
        sys.stdout.write(render_opinion_letter(report))
    else:
        sys.stdout.write(render_markdown(report))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

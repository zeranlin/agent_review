from __future__ import annotations

import argparse
import sys

from .engine import TenderReviewEngine
from .llm import QwenReviewEnhancer
from .reporting import render_json, render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review a tender document for compliance risks.")
    parser.add_argument("--input", required=True, help="Path to a UTF-8 text file.")
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="启用本地 OpenAI 兼容 LLM，对总体结论和修改建议做增强。",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    enhancer = QwenReviewEnhancer() if args.use_llm else None
    engine = TenderReviewEngine(review_enhancer=enhancer)
    report = engine.review_file(args.input)

    if args.format == "json":
        sys.stdout.write(render_json(report))
    else:
        sys.stdout.write(render_markdown(report))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

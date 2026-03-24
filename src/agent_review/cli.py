from __future__ import annotations

import argparse
import sys

from .engine import TenderReviewEngine
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    engine = TenderReviewEngine()
    report = engine.review_file(args.input)

    if args.format == "json":
        sys.stdout.write(render_json(report))
    else:
        sys.stdout.write(render_markdown(report))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

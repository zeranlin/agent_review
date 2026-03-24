from __future__ import annotations

from pathlib import Path

from .checklist import DEFAULT_DIMENSIONS
from .llm import NullReviewEnhancer
from .models import ReviewDimension, ReviewMode, ReviewReport
from .parsers import load_document, load_documents, normalize_text
from .pipeline import ReviewPipeline, build_parse_result_for_text


class TenderReviewEngine:
    """招标文件合规审查编排器。"""

    def __init__(
        self,
        dimensions: list[ReviewDimension] | None = None,
        review_enhancer: object | None = None,
        review_mode: ReviewMode = ReviewMode.fast,
    ) -> None:
        self.dimensions = dimensions or DEFAULT_DIMENSIONS
        self.review_enhancer = review_enhancer or NullReviewEnhancer()
        self.review_mode = review_mode
        self.pipeline = ReviewPipeline(dimensions=self.dimensions)

    def review_text(self, text: str, document_name: str = "input.txt") -> ReviewReport:
        normalized_text = normalize_text(text)
        parse_result = build_parse_result_for_text(normalized_text, document_name)
        return self._run_pipeline(parse_result=parse_result, document_name=document_name)

    def review_file(self, path: str | Path) -> ReviewReport:
        document_name, parse_result = load_document(path)
        parse_result.text = normalize_text(parse_result.text)
        return self._run_pipeline(parse_result=parse_result, document_name=document_name)

    def review_files(self, paths: list[str | Path]) -> ReviewReport:
        document_name, parse_result, source_documents = load_documents(paths)
        parse_result.text = normalize_text(parse_result.text)
        return self._run_pipeline(
            parse_result=parse_result,
            document_name=document_name,
            source_documents=source_documents,
        )

    def _run_pipeline(self, parse_result, document_name: str, source_documents=None) -> ReviewReport:
        report = self.pipeline.run(
            parse_result=parse_result,
            document_name=document_name,
            review_mode=self.review_mode,
            source_documents=source_documents,
        )
        if self.review_mode == ReviewMode.enhanced:
            return self.review_enhancer.enhance(report)
        return report

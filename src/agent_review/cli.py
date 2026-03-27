from __future__ import annotations

from .app import cli as _impl

QwenReviewEnhancer = _impl.QwenReviewEnhancer
QwenParserSemanticAssistant = _impl.QwenParserSemanticAssistant
TenderReviewEngine = _impl.TenderReviewEngine
ReviewMode = _impl.ReviewMode


def _sync_impl_globals() -> None:
    _impl.QwenReviewEnhancer = QwenReviewEnhancer
    _impl.QwenParserSemanticAssistant = QwenParserSemanticAssistant
    _impl.TenderReviewEngine = TenderReviewEngine
    _impl.ReviewMode = ReviewMode


def build_parser():
    _sync_impl_globals()
    return _impl.build_parser()


def main() -> int:
    _sync_impl_globals()
    return _impl.main()


if __name__ == "__main__":
    raise SystemExit(main())

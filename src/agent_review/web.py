from __future__ import annotations

from .app import web as _impl

QwenReviewEnhancer = _impl.QwenReviewEnhancer
TenderReviewEngine = _impl.TenderReviewEngine
markdown_to_html = _impl.markdown_to_html
_parse_uploaded_file = _impl._parse_uploaded_file


def _sync_impl_globals() -> None:
    _impl.QwenReviewEnhancer = QwenReviewEnhancer
    _impl.TenderReviewEngine = TenderReviewEngine


ReviewJob = _impl.ReviewJob


class ReviewWebApp(_impl.ReviewWebApp):
    def __init__(self, llm_timeout: float = 1800.0) -> None:
        _sync_impl_globals()
        super().__init__(llm_timeout=llm_timeout)


def build_parser():
    _sync_impl_globals()
    return _impl.build_parser()


def main() -> int:
    _sync_impl_globals()
    return _impl.main()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
import threading
from wsgiref.simple_server import make_server

from ..engine import TenderReviewEngine
from ..llm import QwenReviewEnhancer
from .job_runner import ensure_complete_enhanced_run, format_job_exception, run_review_job
from .routes import WorkbenchRoutes
from .renderer import WorkbenchRenderer, markdown_to_html


@dataclass(slots=True)
class ReviewJob:
    job_id: str
    filename: str
    upload_path: str
    status: str = "running"
    review_mode: str = ""
    overall_conclusion: str = ""
    run_dir: str = ""
    reviewer_report_path: str = ""
    reviewer_report_markdown: str = ""
    header_info: dict[str, object] = None
    document_profile: dict[str, object] = None
    planning_summary: dict[str, object] = None
    domain_profile_candidates: list[dict[str, object]] = None
    high_risk_items: list[dict[str, object]] = None
    pending_confirmation_items: list[dict[str, object]] = None
    llm_tasks: list[dict[str, object]] = None
    llm_status: dict[str, object] = None
    artifact_paths: dict[str, str] = None
    error: str = ""
    llm_budget_seconds: float = 1800.0
    started_at: str = ""
    deadline_at: str = ""

    def __post_init__(self) -> None:
        self.header_info = self.header_info or {}
        self.document_profile = self.document_profile or {}
        self.planning_summary = self.planning_summary or {}
        self.domain_profile_candidates = self.domain_profile_candidates or []
        self.high_risk_items = self.high_risk_items or []
        self.pending_confirmation_items = self.pending_confirmation_items or []
        self.llm_tasks = self.llm_tasks or []
        self.llm_status = self.llm_status or {}
        self.artifact_paths = self.artifact_paths or {}


class ReviewWebApp:
    def __init__(self, llm_timeout: float = 1800.0) -> None:
        self.llm_timeout = llm_timeout
        self._jobs: dict[str, ReviewJob] = {}
        self._lock = threading.Lock()
        self._base_dir = (Path.cwd() / "runs" / "_web").resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._renderer = WorkbenchRenderer()
        self._routes = WorkbenchRoutes(
            jobs=self._jobs,
            lock=self._lock,
            base_dir=self._base_dir,
            llm_timeout=self.llm_timeout,
            renderer=self._renderer,
            parse_upload=_parse_uploaded_file,
            run_review_job=self._run_review_job,
            respond_html=self._respond_html,
        )

    def __call__(self, environ, start_response):
        return self._routes.dispatch(environ, start_response)

    def _handle_review_submit(self, environ, start_response):
        return self._routes.handle_review_submit(environ, start_response)

    def _handle_review_page(self, job_id: str, start_response):
        return self._routes.handle_review_page(job_id, start_response)

    def _handle_artifact_page(self, job_id: str, artifact_key: str, start_response):
        return self._routes.handle_artifact_page(job_id, artifact_key, start_response)

    def _render_home(self) -> str:
        return self._renderer.render_home()

    def _render_pending(self, job: ReviewJob) -> str:
        return self._renderer.render_pending(job)

    def _render_result(self, job: ReviewJob) -> str:
        return self._renderer.render_result(job)

    def _render_artifact(self, job: ReviewJob, artifact_key: str, target: Path) -> str:
        return self._renderer.render_artifact(job, artifact_key, target)

    def _render_error(self, message: str) -> str:
        return self._renderer.render_error(message)

    @staticmethod
    def _render_not_found() -> str:
        return WorkbenchRenderer.render_not_found()

    def _run_review_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]

        try:
            run_review_job(
                job,
                llm_timeout=self.llm_timeout,
                engine_cls=TenderReviewEngine,
                enhancer_cls=QwenReviewEnhancer,
            )
            with self._lock:
                self._jobs[job_id] = job
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                job.status = "failed"
                job.error = format_job_exception(exc)

    @staticmethod
    def _ensure_complete_enhanced_run(report) -> None:
        ensure_complete_enhanced_run(report)

    @staticmethod
    def _respond_html(start_response, body: str, status: str = "200 OK"):
        payload = body.encode("utf-8")
        start_response(
            status,
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(payload))),
            ],
        )
        return [payload]

def _parse_uploaded_file(environ) -> tuple[str, bytes] | None:
    content_type = environ.get("CONTENT_TYPE", "")
    if "multipart/form-data" not in content_type:
        return None
    try:
        content_length = int(environ.get("CONTENT_LENGTH", "0") or "0")
    except ValueError:
        return None
    if content_length <= 0:
        return None

    body = environ["wsgi.input"].read(content_length)
    header_blob = (
        f"Content-Type: {content_type}\r\n"
        "MIME-Version: 1.0\r\n\r\n"
    ).encode("utf-8")
    message = BytesParser(policy=default).parsebytes(header_blob + body)
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        if part.get_param("name", header="content-disposition") != "file":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        return filename, payload
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the minimal web demo for tender review.")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址。")
    parser.add_argument("--port", type=int, default=8765, help="监听端口。")
    parser.add_argument("--llm-timeout", type=float, default=1800.0, help="LLM 单次调用超时时间（秒），默认 1800。")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    app = ReviewWebApp(llm_timeout=args.llm_timeout)
    with make_server(args.host, args.port, app) as server:
        print(f"agent_review web demo running at http://{args.host}:{args.port}")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

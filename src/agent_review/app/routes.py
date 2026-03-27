from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
from urllib.parse import urlparse
from uuid import uuid4


class WorkbenchRoutes:
    def __init__(
        self,
        *,
        jobs: dict[str, object],
        lock: threading.Lock,
        base_dir: Path,
        llm_timeout: float,
        renderer,
        parse_upload,
        run_review_job,
        respond_html,
    ) -> None:
        self.jobs = jobs
        self.lock = lock
        self.base_dir = base_dir
        self.llm_timeout = llm_timeout
        self.renderer = renderer
        self.parse_upload = parse_upload
        self.run_review_job = run_review_job
        self.respond_html = respond_html

    def dispatch(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = urlparse(environ.get("PATH_INFO", "/")).path

        if method == "GET" and path == "/":
            return self.respond_html(start_response, self.renderer.render_home())
        if method == "POST" and path == "/review":
            return self.handle_review_submit(environ, start_response)
        if method == "GET" and path.startswith("/review/"):
            return self.handle_review_page(path.rsplit("/", 1)[-1], start_response)
        if method == "GET" and path.startswith("/artifact/"):
            parts = [item for item in path.split("/") if item]
            if len(parts) == 3:
                return self.handle_artifact_page(parts[1], parts[2], start_response)

        return self.respond_html(start_response, self.renderer.render_not_found(), status="404 Not Found")

    def handle_review_submit(self, environ, start_response):
        upload = self.parse_upload(environ)
        if upload is None:
            return self.respond_html(start_response, self.renderer.render_error("未选择文件。"), status="400 Bad Request")

        filename, payload = upload
        filename = Path(filename).name
        job_id = uuid4().hex
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        upload_path = job_dir / filename
        started_at = datetime.now(timezone.utc)
        deadline_at = started_at + timedelta(seconds=self.llm_timeout)

        with upload_path.open("wb") as output_file:
            output_file.write(payload)

        job = self._create_job(
            job_id=job_id,
            filename=filename,
            upload_path=str(upload_path),
            llm_budget_seconds=self.llm_timeout,
            started_at=started_at.isoformat(timespec="seconds"),
            deadline_at=deadline_at.isoformat(timespec="seconds"),
        )
        with self.lock:
            self.jobs[job_id] = job

        thread = threading.Thread(target=self.run_review_job, args=(job_id,), daemon=True)
        thread.start()
        start_response("303 See Other", [("Location", f"/review/{job_id}")])
        return [b""]

    def handle_review_page(self, job_id: str, start_response):
        with self.lock:
            job = self.jobs.get(job_id)

        if job is None:
            return self.respond_html(start_response, self.renderer.render_error("未找到对应审核任务。"), status="404 Not Found")
        if job.status == "running":
            return self.respond_html(start_response, self.renderer.render_pending(job))
        if job.status == "failed":
            return self.respond_html(start_response, self.renderer.render_error(job.error or "审核失败。"), status="500 Internal Server Error")
        return self.respond_html(start_response, self.renderer.render_result(job))

    def handle_artifact_page(self, job_id: str, artifact_key: str, start_response):
        with self.lock:
            job = self.jobs.get(job_id)

        if job is None:
            return self.respond_html(start_response, self.renderer.render_error("未找到对应审核任务。"), status="404 Not Found")
        artifact_path = job.artifact_paths.get(artifact_key, "")
        if not artifact_path:
            return self.respond_html(start_response, self.renderer.render_error("未找到对应产物。"), status="404 Not Found")
        target = Path(artifact_path)
        if not target.exists():
            return self.respond_html(start_response, self.renderer.render_error("产物文件不存在。"), status="404 Not Found")
        return self.respond_html(start_response, self.renderer.render_artifact(job, artifact_key, target))

    def _create_job(self, **kwargs):
        review_job_cls = self._review_job_cls()
        return review_job_cls(**kwargs)

    def _review_job_cls(self):
        from .workbench import ReviewJob

        return ReviewJob

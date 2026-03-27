from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from email.policy import default
from html import escape
from pathlib import Path
import re
import threading
import traceback
from typing import ClassVar
from urllib.parse import urlparse
from uuid import uuid4
from wsgiref.simple_server import make_server

from ..engine import TenderReviewEngine
from ..header_info import resolve_header_info
from ..llm import QwenReviewEnhancer
from ..models import ReviewMode, ReviewReport, TaskStatus
from ..outputs import write_review_artifacts
from ..reporting import render_reviewer_report


REQUIRED_LLM_TASKS = (
    "llm_scenario_review",
    "llm_scoring_review",
    "llm_review_point_second_review",
)


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

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = urlparse(environ.get("PATH_INFO", "/")).path

        if method == "GET" and path == "/":
            return self._respond_html(start_response, self._render_home())
        if method == "POST" and path == "/review":
            return self._handle_review_submit(environ, start_response)
        if method == "GET" and path.startswith("/review/"):
            job_id = path.rsplit("/", 1)[-1]
            return self._handle_review_page(job_id, start_response)
        if method == "GET" and path.startswith("/artifact/"):
            parts = [item for item in path.split("/") if item]
            if len(parts) == 3:
                return self._handle_artifact_page(parts[1], parts[2], start_response)

        return self._respond_html(start_response, self._render_not_found(), status="404 Not Found")

    def _handle_review_submit(self, environ, start_response):
        upload = _parse_uploaded_file(environ)
        if upload is None:
            return self._respond_html(start_response, self._render_error("未选择文件。"), status="400 Bad Request")

        filename, payload = upload
        filename = Path(filename).name
        job_id = uuid4().hex
        job_dir = self._base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        upload_path = job_dir / filename
        started_at = datetime.now(timezone.utc)
        deadline_at = started_at + timedelta(seconds=self.llm_timeout)

        with upload_path.open("wb") as output_file:
            output_file.write(payload)

        job = ReviewJob(
            job_id=job_id,
            filename=filename,
            upload_path=str(upload_path),
            llm_budget_seconds=self.llm_timeout,
            started_at=started_at.isoformat(timespec="seconds"),
            deadline_at=deadline_at.isoformat(timespec="seconds"),
        )
        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(target=self._run_review_job, args=(job_id,), daemon=True)
        thread.start()

        start_response("303 See Other", [("Location", f"/review/{job_id}")])
        return [b""]

    def _handle_review_page(self, job_id: str, start_response):
        with self._lock:
            job = self._jobs.get(job_id)

        if job is None:
            return self._respond_html(start_response, self._render_error("未找到对应审核任务。"), status="404 Not Found")
        if job.status == "running":
            return self._respond_html(start_response, self._render_pending(job))
        if job.status == "failed":
            return self._respond_html(start_response, self._render_error(job.error or "审核失败。"), status="500 Internal Server Error")
        return self._respond_html(start_response, self._render_result(job))

    def _handle_artifact_page(self, job_id: str, artifact_key: str, start_response):
        with self._lock:
            job = self._jobs.get(job_id)

        if job is None:
            return self._respond_html(start_response, self._render_error("未找到对应审核任务。"), status="404 Not Found")
        artifact_path = job.artifact_paths.get(artifact_key, "")
        if not artifact_path:
            return self._respond_html(start_response, self._render_error("未找到对应产物。"), status="404 Not Found")
        target = Path(artifact_path)
        if not target.exists():
            return self._respond_html(start_response, self._render_error("产物文件不存在。"), status="404 Not Found")
        return self._respond_html(start_response, self._render_artifact(job, artifact_key, target))

    def _run_review_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]

        try:
            enhancer = QwenReviewEnhancer(timeout=self.llm_timeout)
            base_engine = TenderReviewEngine(review_mode=ReviewMode.fast)
            enhanced_engine = TenderReviewEngine(review_enhancer=enhancer, review_mode=ReviewMode.enhanced)

            base_report = base_engine.review_file(job.upload_path)
            report = enhanced_engine.review_file(job.upload_path)
            self._ensure_complete_enhanced_run(report)
            bundle = write_review_artifacts(report=report, base_report=base_report)
            reviewer_markdown = render_reviewer_report(report)
            header_info = resolve_header_info(report).to_dict()
            document_profile = report.parse_result.document_profile.to_dict() if report.parse_result.document_profile else {}
            planning_summary = report.review_planning_contract.to_dict() if report.review_planning_contract else {}
            llm_tasks = [item.to_dict() for item in report.task_records if item.task_name.startswith("llm_")]
            artifact_paths = {
                "reviewer_report": bundle.reviewer_report_path,
                "evaluation_summary": bundle.evaluation_summary_path,
                "document_profile": bundle.document_profile_path,
                "domain_profile_match": bundle.domain_profile_match_path,
                "review_point_trace": bundle.review_point_trace_path,
                "llm_tasks": bundle.llm_tasks_path,
                "run_manifest": bundle.manifest_path,
                "high_risk_review": bundle.high_risk_review_path,
                "pending_confirmation": bundle.pending_confirmation_path,
                "enhancement_trace": bundle.enhancement_trace_path,
                "enhanced_report_json": bundle.final_json_path,
                "enhanced_report_md": bundle.final_markdown_path,
                "formal_review_opinion": bundle.formal_review_opinion_path,
                "opinion_letter": bundle.opinion_letter_path,
            }

            with self._lock:
                job.status = "completed"
                job.review_mode = report.review_mode.value
                job.overall_conclusion = report.overall_conclusion.value
                job.run_dir = bundle.run_dir
                job.reviewer_report_path = bundle.reviewer_report_path
                job.reviewer_report_markdown = reviewer_markdown
                job.header_info = header_info
                job.document_profile = document_profile
                job.planning_summary = planning_summary
                job.domain_profile_candidates = document_profile.get("domain_profile_candidates", [])
                job.high_risk_items = [item.to_dict() for item in report.high_risk_review_items]
                job.pending_confirmation_items = [item.to_dict() for item in report.pending_confirmation_items]
                job.llm_tasks = llm_tasks
                job.llm_status = {
                    "enhanced": report.llm_enhanced,
                    "warnings": report.llm_warnings,
                    "task_count": len(llm_tasks),
                }
                job.artifact_paths = artifact_paths
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                job.status = "failed"
                job.error = f"{exc}\n\n{traceback.format_exc()}"

    @staticmethod
    def _ensure_complete_enhanced_run(report: ReviewReport) -> None:
        task_map = {item.task_name: item for item in report.task_records}
        missing = [
            name
            for name in REQUIRED_LLM_TASKS
            if task_map.get(name) is None or task_map[name].status != TaskStatus.completed
        ]
        if missing:
            raise RuntimeError(f"增强审查未完整完成：{ReviewWebApp._format_llm_task_state_summary(report)}")

    @staticmethod
    def _format_llm_task_state_summary(report: ReviewReport) -> str:
        task_map = {item.task_name: item for item in report.task_records}
        segments: list[str] = []
        for name in REQUIRED_LLM_TASKS:
            record = task_map.get(name)
            if record is None:
                segments.append(f"{name}=missing（未生成任务记录）")
                continue
            detail = record.detail.strip() or "无详情"
            segments.append(f"{name}={record.status.value}（{detail}）")
        return "; ".join(segments)

    def _render_home(self) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>agent_review 演示</title>
  <style>{_base_css()}</style>
</head>
<body>
  <main class="shell">
    <section class="card">
      <h1>招标文件风险点审查</h1>
      <p class="muted">上传文件后，系统将直接使用 enhanced + LLM 模式完成审查。</p>
      <form method="post" action="/review" enctype="multipart/form-data" class="stack" id="review-form">
        <input type="file" name="file" id="review-file" required>
        <button type="submit" id="review-submit">开始审核</button>
        <p class="muted" id="submit-hint">选择文件后点击“开始审核”。</p>
      </form>
    </section>
  </main>
  <script>
    (function () {{
      const form = document.getElementById("review-form");
      const fileInput = document.getElementById("review-file");
      const submitButton = document.getElementById("review-submit");
      const submitHint = document.getElementById("submit-hint");
      if (!form || !fileInput || !submitButton || !submitHint) {{
        return;
      }}
      let submitting = false;
      form.addEventListener("submit", function (event) {{
        if (submitting) {{
          event.preventDefault();
          return;
        }}
        if (!fileInput.files || fileInput.files.length === 0) {{
          submitHint.textContent = "请先选择文件。";
          event.preventDefault();
          return;
        }}
        submitting = true;
        submitButton.disabled = true;
        submitButton.textContent = "正在提交...";
        submitHint.textContent = "文件已提交，正在进入审核队列。";
      }});
    }})();
  </script>
</body>
</html>"""

    def _render_pending(self, job: ReviewJob) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="2">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>审核中</title>
  <style>{_base_css()}</style>
</head>
<body>
  <main class="shell">
    <section class="card center">
      <h1>审核中...</h1>
      <p class="muted">{escape(job.filename)}</p>
      <p class="muted">开始于：{escape(job.started_at or '未知')}</p>
      <p class="muted">LLM 预算：{escape(f'{job.llm_budget_seconds:.0f}')} 秒，截止：{escape(job.deadline_at or '未知')}</p>
    </section>
  </main>
</body>
</html>"""

    def _render_result(self, job: ReviewJob) -> str:
        report_html = markdown_to_html(job.reviewer_report_markdown)
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>审核结果</title>
  <style>{_base_css()}</style>
</head>
<body>
  <main class="shell">
    <section class="card">
      <div class="topbar">
        <h1>审查工作台</h1>
        <a class="link-btn" href="/">继续上传</a>
      </div>
      {self._render_overview_panel(job)}
    </section>
    <section class="card">
      <h2>头部信息</h2>
      {self._render_key_value_grid([
        ("项目名称", job.header_info.get("project_name", "")),
        ("项目编号", job.header_info.get("project_code", "")),
        ("采购单位", job.header_info.get("purchaser_name", "")),
        ("采购代理机构", job.header_info.get("agency_name", "")),
        ("预算金额", job.header_info.get("budget_amount", "")),
        ("最高限价", job.header_info.get("max_price", "")),
      ])}
    </section>
    <section class="card">
      <h2>结构画像</h2>
      {self._render_profile_panel(job)}
    </section>
    <section class="card">
      <h2>审查规划</h2>
      {self._render_planning_panel(job)}
    </section>
    <section class="card">
      <h2>风险工作台</h2>
      {self._render_risk_panel(job)}
    </section>
    <section class="card">
      <h2>增强状态</h2>
      {self._render_llm_panel(job)}
    </section>
    <section class="card">
      <h2>运行产物</h2>
      {self._render_artifacts_panel(job)}
    </section>
    <section class="card report-card">
      <div class="topbar">
        <h2>审查意见书</h2>
        <a class="link-btn" href="/artifact/{escape(job.job_id)}/reviewer_report">查看原始产物</a>
      </div>
      <p class="muted">报告文件：{escape(job.reviewer_report_path)}</p>
      <p class="muted">开始于：{escape(job.started_at or '未知')}</p>
      <p class="muted">LLM 预算：{escape(f'{job.llm_budget_seconds:.0f}')} 秒，截止：{escape(job.deadline_at or '未知')}</p>
      <article class="report-content">{report_html}</article>
    </section>
  </main>
</body>
</html>"""

    def _render_overview_panel(self, job: ReviewJob) -> str:
        return self._render_key_value_grid(
            [
                ("文件名", job.filename),
                ("运行模式", job.review_mode or "unknown"),
                ("总体结论", job.overall_conclusion or "未知"),
                ("运行目录", job.run_dir or ""),
                ("高风险条目数", str(len(job.high_risk_items))),
                ("待人工确认数", str(len(job.pending_confirmation_items))),
                ("LLM 任务数", str(job.llm_status.get("task_count", 0))),
                ("增强状态", "已完成" if job.llm_status.get("enhanced") else "未增强/回退"),
            ]
        )

    def _render_profile_panel(self, job: ReviewJob) -> str:
        profile = job.document_profile
        candidate_items = "".join(
            f"<li>{escape(str(item.get('profile_id', '')))} / conf={escape(str(item.get('confidence', '')))} / reasons={escape(', '.join(item.get('reasons', [])))}</li>"
            for item in job.domain_profile_candidates[:5]
        ) or "<li>未生成领域候选</li>"
        zone_items = "".join(
            f"<li>{escape(str(item.get('zone_type', '')))} / ratio={escape(str(item.get('ratio', '')))} / units={escape(str(item.get('unit_count', '')))}</li>"
            for item in profile.get("dominant_zones", [])[:8]
        ) or "<li>未生成区域分布</li>"
        return (
            self._render_key_value_grid(
                [
                    ("采购类型", f"{profile.get('procurement_kind', 'unknown')} / conf={profile.get('procurement_kind_confidence', 0)}"),
                    ("路由模式", profile.get("routing_mode", "")),
                    ("主审查类型", ", ".join(profile.get("primary_review_types", [])) or "未识别"),
                    ("结构标记", ", ".join(profile.get("structure_flags", [])) or "无"),
                    ("质量标记", ", ".join(profile.get("quality_flags", [])) or "无"),
                    ("未知结构标记", ", ".join(profile.get("unknown_structure_flags", [])) or "无"),
                ]
            )
            + "<div class=\"split\"><div><h3>DomainProfile 候选</h3><ul>"
            + candidate_items
            + "</ul></div><div><h3>Dominant Zones</h3><ul>"
            + zone_items
            + "</ul></div></div>"
        )

    def _render_planning_panel(self, job: ReviewJob) -> str:
        planning = job.planning_summary
        if not planning:
            return "<p class=\"muted\">当前未生成 ReviewPlanningContract。</p>"
        return self._render_key_value_grid(
            [
                ("target_zones", ", ".join(planning.get("target_zones", [])) or "无"),
                ("target_primary_review_types", ", ".join(planning.get("target_primary_review_types", [])) or "无"),
                ("activated_risk_families", ", ".join(planning.get("activated_risk_families", [])) or "无"),
                ("suppressed_risk_families", ", ".join(planning.get("suppressed_risk_families", [])) or "无"),
                ("planned_catalog_ids", ", ".join(planning.get("planned_catalog_ids", [])[:8]) or "无"),
                ("high_value_fields", ", ".join(planning.get("high_value_fields", [])[:8]) or "无"),
                ("matched_extraction_fields", ", ".join(planning.get("matched_extraction_fields", [])[:8]) or "无"),
                ("summary", planning.get("summary", "")),
            ]
        )

    def _render_risk_panel(self, job: ReviewJob) -> str:
        return (
            "<div class=\"split\"><div><h3>高风险复核清单</h3>"
            + self._render_work_items(job.high_risk_items, empty_text="当前无高风险复核条目。")
            + "</div><div><h3>待人工确认</h3>"
            + self._render_work_items(job.pending_confirmation_items, empty_text="当前无待人工确认条目。")
            + "</div></div>"
        )

    def _render_llm_panel(self, job: ReviewJob) -> str:
        warnings = "".join(f"<li>{escape(str(item))}</li>" for item in job.llm_status.get("warnings", [])) or "<li>无</li>"
        task_rows = "".join(
            "<tr>"
            f"<td>{escape(str(item.get('task_name', '')))}</td>"
            f"<td>{escape(str(item.get('status', '')))}</td>"
            f"<td>{escape(str(item.get('item_count', '')))}</td>"
            f"<td>{escape(str(item.get('detail', '')))}</td>"
            "</tr>"
            for item in job.llm_tasks
        ) or "<tr><td colspan=\"4\">未记录 LLM 任务</td></tr>"
        return (
            self._render_key_value_grid(
                [
                    ("LLM enhanced", "true" if job.llm_status.get("enhanced") else "false"),
                    ("任务数量", str(job.llm_status.get("task_count", 0))),
                ]
            )
            + "<h3>LLM warnings</h3><ul>"
            + warnings
            + "</ul><h3>任务明细</h3><table><thead><tr><th>任务</th><th>状态</th><th>数量</th><th>详情</th></tr></thead><tbody>"
            + task_rows
            + "</tbody></table>"
        )

    def _render_artifacts_panel(self, job: ReviewJob) -> str:
        if not job.artifact_paths:
            return "<p class=\"muted\">当前未生成 artifacts。</p>"
        items = "".join(
            f"<li><a href=\"/artifact/{escape(job.job_id)}/{escape(key)}\">{escape(key)}</a><span class=\"path\">{escape(path)}</span></li>"
            for key, path in job.artifact_paths.items()
        )
        return "<ul class=\"artifact-list\">" + items + "</ul>"

    def _render_work_items(self, items: list[dict[str, object]], *, empty_text: str) -> str:
        if not items:
            return f"<p class=\"muted\">{escape(empty_text)}</p>"
        rendered = "".join(
            "<li>"
            f"<strong>{escape(str(item.get('title', '')))}</strong>"
            f"<div class=\"muted\">{escape(str(item.get('severity', '')))} / {escape(str(item.get('source', '')))}</div>"
            f"<div>{escape(str(item.get('reason', '')))}</div>"
            "</li>"
            for item in items[:8]
        )
        return "<ul>" + rendered + "</ul>"

    def _render_key_value_grid(self, items: list[tuple[str, str]]) -> str:
        rendered = "".join(
            "<div class=\"kv-item\">"
            f"<div class=\"kv-key\">{escape(str(key))}</div>"
            f"<div class=\"kv-value\">{escape(str(value or ''))}</div>"
            "</div>"
            for key, value in items
        )
        return "<div class=\"kv-grid\">" + rendered + "</div>"

    def _render_artifact(self, job: ReviewJob, artifact_key: str, target: Path) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Artifact</title>
  <style>{_base_css()}</style>
</head>
<body>
  <main class="shell">
    <section class="card">
      <div class="topbar">
        <h1>{escape(artifact_key)}</h1>
        <a class="link-btn" href="/review/{escape(job.job_id)}">返回工作台</a>
      </div>
      <p class="muted">{escape(str(target))}</p>
      <pre class="artifact-box">{escape(target.read_text(encoding="utf-8"))}</pre>
    </section>
  </main>
</body>
</html>"""

    def _render_error(self, message: str) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>审核失败</title>
  <style>{_base_css()}</style>
</head>
<body>
  <main class="shell">
    <section class="card">
      <h1>审核失败</h1>
      <pre class="error-box">{escape(message)}</pre>
      <p><a class="link-btn" href="/">返回上传页</a></p>
    </section>
  </main>
</body>
</html>"""

    @staticmethod
    def _render_not_found() -> str:
        return """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:40px;}</style></head>
<body><h1>404</h1><p>页面不存在。</p></body>
</html>"""

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


def markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    blocks: list[str] = []
    bullet_buffer: list[str] = []
    paragraph_buffer: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_buffer:
            return
        text = " ".join(part.strip() for part in paragraph_buffer if part.strip())
        if text:
            blocks.append(f"<p>{_render_inline(text)}</p>")
        paragraph_buffer.clear()

    def flush_bullets() -> None:
        if not bullet_buffer:
            return
        items = "".join(f"<li>{_render_inline(item)}</li>" for item in bullet_buffer)
        blocks.append(f"<ul>{items}</ul>")
        bullet_buffer.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_bullets()
            continue

        if line.startswith("- "):
            flush_paragraph()
            bullet_buffer.append(line[2:].strip())
            continue

        flush_bullets()
        if line.startswith("**") and line.endswith("**") and len(line) > 4:
            flush_paragraph()
            title = line[2:-2].strip()
            blocks.append(_render_heading(title))
            continue
        paragraph_buffer.append(line)

    flush_paragraph()
    flush_bullets()
    return "".join(blocks)


def _render_heading(text: str) -> str:
    if "意见书" in text:
        return f"<h1>{_render_inline(text)}</h1>"
    if re.match(r"^[一二三四五六七八九十]+、", text):
        return f"<h2>{_render_inline(text)}</h2>"
    if re.match(r"^\d+\.", text):
        return f"<h3>{_render_inline(text)}</h3>"
    return f"<h2>{_render_inline(text)}</h2>"


def _render_inline(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{escape(m.group(2), quote=True)}" target="_blank" rel="noreferrer">{escape(m.group(1))}</a>', escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", escaped)
    return escaped


def _base_css() -> str:
    return """
body {
  margin: 0;
  font-family: "PingFang SC", "Noto Sans SC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: linear-gradient(180deg, #f5f1e8 0%, #f9f7f2 100%);
  color: #2b241d;
}
.shell {
  max-width: 980px;
  margin: 0 auto;
  padding: 48px 20px 72px;
}
.card {
  background: rgba(255,255,255,0.9);
  border: 1px solid #e7dece;
  border-radius: 18px;
  box-shadow: 0 12px 40px rgba(77, 58, 31, 0.08);
  padding: 28px;
}
.center { text-align: center; padding: 72px 28px; }
.stack { display: grid; gap: 16px; margin-top: 20px; }
h1, h2, h3 { color: #1f1a15; line-height: 1.35; margin: 0 0 14px; }
h1 { font-size: 28px; }
h2 { font-size: 22px; margin-top: 28px; }
h3 { font-size: 18px; margin-top: 22px; }
p, li { font-size: 15px; line-height: 1.8; }
ul { padding-left: 22px; margin: 10px 0 16px; }
.muted { color: #6f6559; }
input[type="file"] {
  font: inherit;
  padding: 12px;
  background: #fff;
  border: 1px solid #d8ccb8;
  border-radius: 12px;
}
button, .link-btn {
  display: inline-block;
  text-decoration: none;
  font: inherit;
  background: #1d5b45;
  color: #fff;
  border: none;
  border-radius: 999px;
  padding: 12px 20px;
  cursor: pointer;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.report-card { padding: 32px; }
.report-content p { margin: 0 0 14px; }
.kv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.kv-item {
  background: #fcfaf6;
  border: 1px solid #eadfcf;
  border-radius: 12px;
  padding: 12px 14px;
}
.kv-key {
  font-size: 12px;
  color: #7e715f;
  margin-bottom: 6px;
}
.kv-value {
  font-size: 14px;
  line-height: 1.6;
  color: #251f19;
  word-break: break-word;
}
.split {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 18px;
  margin-top: 18px;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 12px;
  font-size: 14px;
}
th, td {
  border: 1px solid #eadfcf;
  padding: 10px;
  text-align: left;
  vertical-align: top;
}
th {
  background: #f7f1e8;
}
.artifact-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.artifact-list li {
  display: grid;
  gap: 4px;
  padding: 10px 0;
  border-bottom: 1px solid #eee4d5;
}
.artifact-list .path {
  color: #7e715f;
  font-size: 12px;
  word-break: break-all;
}
.artifact-box {
  white-space: pre-wrap;
  word-break: break-word;
  background: #f9f7f2;
  border: 1px solid #eadfcf;
  border-radius: 12px;
  padding: 16px;
  font-size: 13px;
  line-height: 1.7;
}
.error-box {
  white-space: pre-wrap;
  word-break: break-word;
  background: #fff8f8;
  border: 1px solid #f1c7c7;
  border-radius: 12px;
  padding: 16px;
  font-size: 13px;
  line-height: 1.6;
}
"""


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

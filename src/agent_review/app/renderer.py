from __future__ import annotations

from html import escape
from pathlib import Path
import re


class WorkbenchRenderer:
    def render_home(self) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>agent_review 演示</title>
  <style>{base_css()}</style>
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

    def render_pending(self, job) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="2">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>审核中</title>
  <style>{base_css()}</style>
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

    def render_result(self, job) -> str:
        report_html = markdown_to_html(job.reviewer_report_markdown)
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>审核结果</title>
  <style>{base_css()}</style>
</head>
<body>
  <main class="shell">
    <section class="card">
      <div class="topbar">
        <h1>审查工作台</h1>
        <a class="link-btn" href="/">继续上传</a>
      </div>
      {self.render_overview_panel(job)}
    </section>
    <section class="card">
      <h2>头部信息</h2>
      {self.render_key_value_grid([
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
      {self.render_profile_panel(job)}
    </section>
    <section class="card">
      <h2>审查规划</h2>
      {self.render_planning_panel(job)}
    </section>
    <section class="card">
      <h2>风险工作台</h2>
      {self.render_risk_panel(job)}
    </section>
    <section class="card">
      <h2>增强状态</h2>
      {self.render_llm_panel(job)}
    </section>
    <section class="card">
      <h2>运行产物</h2>
      {self.render_artifacts_panel(job)}
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

    def render_artifact(self, job, artifact_key: str, target: Path) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Artifact</title>
  <style>{base_css()}</style>
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

    def render_error(self, message: str) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>审核失败</title>
  <style>{base_css()}</style>
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
    def render_not_found() -> str:
        return """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:40px;}</style></head>
<body><h1>404</h1><p>页面不存在。</p></body>
</html>"""

    def render_overview_panel(self, job) -> str:
        return self.render_key_value_grid(
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

    def render_profile_panel(self, job) -> str:
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
            self.render_key_value_grid(
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

    def render_planning_panel(self, job) -> str:
        planning = job.planning_summary
        if not planning:
            return "<p class=\"muted\">当前未生成 ReviewPlanningContract。</p>"
        return self.render_key_value_grid(
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

    def render_risk_panel(self, job) -> str:
        return (
            "<div class=\"split\"><div><h3>高风险复核清单</h3>"
            + self.render_work_items(job.high_risk_items, empty_text="当前无高风险复核条目。")
            + "</div><div><h3>待人工确认</h3>"
            + self.render_work_items(job.pending_confirmation_items, empty_text="当前无待人工确认条目。")
            + "</div></div>"
        )

    def render_llm_panel(self, job) -> str:
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
            self.render_key_value_grid(
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

    def render_artifacts_panel(self, job) -> str:
        if not job.artifact_paths:
            return "<p class=\"muted\">当前未生成 artifacts。</p>"
        items = "".join(
            f"<li><a href=\"/artifact/{escape(job.job_id)}/{escape(key)}\">{escape(key)}</a><span class=\"path\">{escape(path)}</span></li>"
            for key, path in job.artifact_paths.items()
        )
        return "<ul class=\"artifact-list\">" + items + "</ul>"

    def render_work_items(self, items: list[dict[str, object]], *, empty_text: str) -> str:
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

    def render_key_value_grid(self, items: list[tuple[str, str]]) -> str:
        rendered = "".join(
            "<div class=\"kv-item\">"
            f"<div class=\"kv-key\">{escape(str(key))}</div>"
            f"<div class=\"kv-value\">{escape(str(value or ''))}</div>"
            "</div>"
            for key, value in items
        )
        return "<div class=\"kv-grid\">" + rendered + "</div>"


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


def base_css() -> str:
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

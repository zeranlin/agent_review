from __future__ import annotations

from dataclasses import replace
import json
import sys
import time
from pathlib import Path

from agent_review.cli import main


def test_cli_enhanced_mode_falls_back_on_timeout_and_records_trace(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "demo.txt"
    input_path.write_text("项目概况\n采购需求详见附件。", encoding="utf-8")

    class SlowEnhancer:
        def __init__(self, timeout: float | None = None) -> None:
            self.timeout = timeout

        def enhance(self, report):
            time.sleep(0.2)
            return replace(report, summary="不应被使用", llm_enhanced=True)

    artifacts_dir = tmp_path / "runs"
    monkeypatch.setattr("agent_review.cli.QwenReviewEnhancer", SlowEnhancer)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent_review",
            "--input",
            str(input_path),
            "--mode",
            "enhanced",
            "--llm-timeout",
            "0.01",
            "--artifacts-dir",
            str(artifacts_dir),
            "--format",
            "markdown",
        ],
    )

    assert main() == 0
    capsys.readouterr()

    enhanced_report_path = artifacts_dir / "enhanced_report.json"
    enhancement_trace_path = artifacts_dir / "enhancement_trace.json"
    enhanced_markdown_path = artifacts_dir / "enhanced_report.md"
    manifest_path = artifacts_dir / "run_manifest.json"
    base_report_path = artifacts_dir / "base_report.json"

    enhanced_report = json.loads(enhanced_report_path.read_text(encoding="utf-8"))
    enhancement_trace = json.loads(enhancement_trace_path.read_text(encoding="utf-8"))
    enhanced_markdown = enhanced_markdown_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base_report = json.loads(base_report_path.read_text(encoding="utf-8"))

    assert enhanced_report["review_mode"] == "enhanced"
    assert enhanced_report["llm_enhanced"] is False
    assert any("回退" in item for item in enhanced_report["llm_warnings"])
    assert base_report["review_mode"] == "fast"

    assert enhancement_trace["outcome"] == "timed_out"
    assert enhancement_trace["fallback_applied"] is True
    assert enhancement_trace["base_mode"] == "fast"
    assert enhancement_trace["final_mode"] == "enhanced"
    assert enhancement_trace["requested_mode"] == "enhanced"

    assert "增强链状态: 已回退到基础结果" in enhanced_markdown
    assert manifest["artifact_paths"]["enhancement_trace"] == str(enhancement_trace_path)

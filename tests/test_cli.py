from __future__ import annotations

from dataclasses import replace
import json
import sys
import time
from pathlib import Path

from agent_review.cli import main
from agent_review.models import ParserSemanticTrace


class _NoopParserAssistant:
    def __init__(self, timeout: float | None = None) -> None:
        self.timeout = timeout

    def assist(self, parse_result, document_profile):
        return parse_result, ParserSemanticTrace(activated=False, activation_reasons=["test_noop"])


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
    monkeypatch.setattr("agent_review.cli.QwenParserSemanticAssistant", _NoopParserAssistant)
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
    assert enhancement_trace["budget_seconds"] == 0.01
    assert enhancement_trace["deadline_at"]
    assert enhancement_trace["remaining_budget_seconds"] == 0.0

    assert "增强链状态: 已回退到基础结果" in enhanced_markdown
    assert manifest["artifact_paths"]["enhancement_trace"] == str(enhancement_trace_path)


def test_cli_enhanced_mode_uses_default_llm_timeout_budget(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "demo.txt"
    input_path.write_text("项目概况\n采购需求详见附件。", encoding="utf-8")

    recorded_timeouts: list[float | None] = []

    class RecordingEnhancer:
        def __init__(self, timeout: float | None = None) -> None:
            recorded_timeouts.append(timeout)

        def enhance(self, report):
            return replace(report, summary="增强完成", llm_enhanced=True)

    artifacts_dir = tmp_path / "runs"
    monkeypatch.setattr("agent_review.cli.QwenReviewEnhancer", RecordingEnhancer)
    monkeypatch.setattr("agent_review.cli.QwenParserSemanticAssistant", _NoopParserAssistant)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent_review",
            "--input",
            str(input_path),
            "--mode",
            "enhanced",
            "--artifacts-dir",
            str(artifacts_dir),
            "--format",
            "markdown",
        ],
    )

    assert main() == 0
    capsys.readouterr()

    enhancement_trace = json.loads((artifacts_dir / "enhancement_trace.json").read_text(encoding="utf-8"))
    assert recorded_timeouts == [1800.0]
    assert enhancement_trace["budget_seconds"] == 1800.0
    assert enhancement_trace["deadline_at"]
    assert enhancement_trace["remaining_budget_seconds"] >= 0


def test_cli_defaults_to_enhanced_mode_and_parser_llm_assist(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "demo.txt"
    input_path.write_text("项目概况\n采购需求详见附件。", encoding="utf-8")

    recorded_timeouts: list[float | None] = []
    parser_assist_calls: list[str] = []

    class RecordingEnhancer:
        def __init__(self, timeout: float | None = None) -> None:
            recorded_timeouts.append(timeout)

        def enhance(self, report):
            return replace(report, summary="增强完成", llm_enhanced=True)

    class RecordingParserAssistant:
        def __init__(self, timeout: float | None = None) -> None:
            parser_assist_calls.append(f"init:{timeout}")

        def assist(self, parse_result, document_profile):
            parser_assist_calls.append("assist")
            return parse_result, ParserSemanticTrace(activated=False, activation_reasons=["test_default"])

    artifacts_dir = tmp_path / "runs"
    monkeypatch.setattr("agent_review.cli.QwenReviewEnhancer", RecordingEnhancer)
    monkeypatch.setattr("agent_review.cli.QwenParserSemanticAssistant", RecordingParserAssistant)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent_review",
            "--input",
            str(input_path),
            "--artifacts-dir",
            str(artifacts_dir),
            "--format",
            "markdown",
        ],
    )

    assert main() == 0
    capsys.readouterr()

    enhanced_report = json.loads((artifacts_dir / "enhanced_report.json").read_text(encoding="utf-8"))
    assert enhanced_report["review_mode"] == "enhanced"
    assert recorded_timeouts == [1800.0]
    assert parser_assist_calls[0] == "init:1800.0"
    assert "assist" in parser_assist_calls


def test_cli_can_explicitly_disable_parser_llm_assist(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "demo.txt"
    input_path.write_text("项目概况\n采购需求详见附件。", encoding="utf-8")

    parser_assist_calls: list[str] = []

    class RecordingEnhancer:
        def __init__(self, timeout: float | None = None) -> None:
            self.timeout = timeout

        def enhance(self, report):
            return replace(report, summary="增强完成", llm_enhanced=True)

    class RecordingParserAssistant:
        def __init__(self, timeout: float | None = None) -> None:
            parser_assist_calls.append(f"init:{timeout}")

        def assist(self, parse_result, document_profile):
            parser_assist_calls.append("assist")
            return parse_result, ParserSemanticTrace(activated=False, activation_reasons=["disabled"])

    artifacts_dir = tmp_path / "runs"
    monkeypatch.setattr("agent_review.cli.QwenReviewEnhancer", RecordingEnhancer)
    monkeypatch.setattr("agent_review.cli.QwenParserSemanticAssistant", RecordingParserAssistant)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent_review",
            "--input",
            str(input_path),
            "--disable-parser-llm-assist",
            "--artifacts-dir",
            str(artifacts_dir),
            "--format",
            "markdown",
        ],
    )

    assert main() == 0
    capsys.readouterr()

    assert parser_assist_calls == []

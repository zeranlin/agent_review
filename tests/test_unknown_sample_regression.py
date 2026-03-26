from __future__ import annotations

import json
from pathlib import Path

from agent_review.eval.unknown_sample_regression import (
    FileRegressionSummary,
    RegressionRunOptions,
    build_manifest_text,
    run_unknown_sample_regression,
)


def _make_summary_item(path: Path, *, document_name: str, procurement_kind: str) -> FileRegressionSummary:
    return FileRegressionSummary(
        document_name=document_name,
        source_path=str(path),
        status="ok",
        parse_summary={
            "parser_name": "mock",
            "source_format": "docx",
            "document_node_count": 1,
            "semantic_zone_count": 1,
            "clause_unit_count": 1,
            "extracted_clause_count": 1,
            "warning_count": 0,
        },
        document_profile={
            "document_id": str(path),
            "procurement_kind": procurement_kind,
            "summary": f"{document_name} 画像",
        },
        domain_profile={
            "document_id": str(path),
            "procurement_kind": procurement_kind,
            "top_candidates": [{"profile_id": procurement_kind, "confidence": 0.91}],
            "summary": f"{document_name} 领域候选",
        },
        quality_gate_summary={
            "count": 1,
            "status_counts": {"passed": 1},
            "top_items": [],
        },
        formal_summary={
            "mode": "actual",
            "count": 1,
            "included_count": 1,
            "manual_confirmation_count": 0,
            "top_included": [],
        },
        review_point_summary={
            "count": 1,
            "applicable_count": 1,
            "catalog_ids": ["RP-001"],
            "task_titles": ["示例审查点"],
            "applicability_preview": [],
            "applicability_match": {},
        },
        evaluation_summary={
            "input_chars": 12,
            "document_node_count": 1,
            "clause_unit_count": 1,
            "extracted_clause_count": 1,
            "review_point_count": 1,
            "applicable_count": 1,
            "quality_gate_count": 1,
            "quality_gate_status_counts": {"passed": 1},
            "formal_included_count": 1,
            "formal_mode": "actual",
            "domain_candidate_count": 1,
        },
    )


def test_build_manifest_text_sorts_and_deduplicates_paths() -> None:
    a_path = Path("/tmp/a.docx").expanduser().resolve()
    z_path = Path("/tmp/z.docx").expanduser().resolve()
    manifest_text = build_manifest_text(
        [Path("/tmp/z.docx"), Path("/tmp/a.docx"), Path("/tmp/a.docx")],
        label="baseline",
    )

    assert manifest_text.splitlines() == [
        "# agent_review unknown sample regression manifest",
        "# label: baseline",
        "# count: 2",
        str(a_path),
        str(z_path),
    ]


def test_unknown_sample_regression_writes_batch_summary_and_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    input_a = tmp_path / "b.docx"
    input_b = tmp_path / "a.docx"
    input_a.write_text("a", encoding="utf-8")
    input_b.write_text("b", encoding="utf-8")

    fake_results = {
        str(input_a.resolve()): _make_summary_item(input_a.resolve(), document_name="b.docx", procurement_kind="unknown"),
        str(input_b.resolve()): _make_summary_item(input_b.resolve(), document_name="a.docx", procurement_kind="mixed"),
    }

    monkeypatch.setattr(
        "agent_review.eval.unknown_sample_regression._run_single_file",
        lambda path, options: fake_results[str(path.resolve())],
    )

    options = RegressionRunOptions(
        input_paths=[input_a, input_b],
        output_dir=tmp_path / "runs",
        write_outputs=True,
        emit_manifest=True,
        manifest_label="baseline",
    )
    summary = run_unknown_sample_regression(options)

    batch_summary_path = options.output_dir / "batch_summary.json"
    batch_summary_md_path = options.output_dir / "batch_summary.md"
    manifest_txt_path = options.output_dir / "baseline_manifest.txt"
    manifest_json_path = options.output_dir / "baseline_manifest.json"

    batch_summary = json.loads(batch_summary_path.read_text(encoding="utf-8"))
    manifest_text = manifest_txt_path.read_text(encoding="utf-8")
    manifest_json = json.loads(manifest_json_path.read_text(encoding="utf-8"))
    batch_summary_md = batch_summary_md_path.read_text(encoding="utf-8")

    assert summary.input_count == 2
    assert [item.source_path for item in summary.items] == sorted(
        [str(input_a.resolve()), str(input_b.resolve())]
    )
    assert batch_summary["input_count"] == 2
    assert batch_summary["succeeded_count"] == 2
    assert batch_summary["failed_count"] == 0
    assert batch_summary["aggregate"]["result_status_counts"] == {"ok": 2}
    assert batch_summary["aggregate"]["procurement_kind_counts"] == {"mixed": 1, "unknown": 1}
    assert batch_summary["evaluation_summary"]["average_input_chars"] == 12.0
    assert batch_summary["evaluation_summary"]["quality_gate_status_counts"] == {"passed": 2}
    assert batch_summary_md.startswith("# 未知品目真实样本回归摘要")
    assert "- 输入数量：2" in batch_summary_md
    assert manifest_text.splitlines()[-2:] == [str(input_b.resolve()), str(input_a.resolve())]
    assert manifest_json["label"] == "baseline"
    assert manifest_json["count"] == 2
    assert manifest_json["paths"] == [str(input_b.resolve()), str(input_a.resolve())]

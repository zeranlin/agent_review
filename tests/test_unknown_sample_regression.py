from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from agent_review.eval.unknown_sample_regression import (
    FileRegressionSummary,
    RegressionRunOptions,
    build_manifest_text,
    run_unknown_sample_regression,
)
from agent_review.models import ReviewMode, TaskRecord, TaskStatus


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
            "routing_mode": "unknown_conservative" if procurement_kind == "unknown" else "standard",
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
            "llm_enhanced": False,
            "llm_warning_count": 0,
            "llm_task_status_counts": {"completed": 1},
            "review_planning_contract": {
                "routing_mode": "unknown_conservative" if procurement_kind == "unknown" else "standard",
                "activation_reason_count": 2,
                "activated_risk_family_count": 2,
                "suppressed_risk_family_count": 1,
                "planned_catalog_count": 2,
                "target_zone_count": 2,
                "base_extraction_demand_count": 3,
                "required_task_extraction_demand_count": 1,
                "optional_enhancement_extraction_demand_count": 1,
                "high_value_field_count": 2,
                "matched_extraction_field_count": 2,
                "base_hit_field_count": 1,
                "required_hit_field_count": 1,
                "optional_hit_field_count": 0,
                "unknown_fallback_hit_field_count": 0,
                "clause_unit_targeted_count": 2,
                "text_fallback_clause_count": 0,
                "unknown_fallback_extraction_demand_count": 0,
            },
            "parser_semantic_assist": {
                "activated": procurement_kind == "unknown",
                "candidate_count": 2 if procurement_kind == "unknown" else 0,
                "reviewed_count": 2 if procurement_kind == "unknown" else 0,
                "applied_count": 1 if procurement_kind == "unknown" else 0,
                "warning_count": 0,
            },
            "prompt_volume": {
                "task_char_counts": {"scenario_review": 100},
                "total_chars": 100,
                "largest_task": "scenario_review",
            },
            "task_duration": {
                "tasks_with_duration": 1,
                "tasks_without_duration": 0,
                "task_seconds": {"llm_scenario_review": 1.25},
                "total_seconds": 1.25,
                "average_seconds": 1.25,
                "max_seconds": 1.25,
            },
            "dynamic_task_counts": {
                "scenario_review_task_count": 1,
                "scoring_review_task_count": 0,
                "total_dynamic_review_task_count": 1,
            },
            "semantic_review": {
                "clause_supplement_count": 0,
                "role_review_count": 0,
                "evidence_review_count": 0,
                "applicability_review_count": 0,
                "verdict_review_present": False,
            },
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
    assert batch_summary["aggregate"]["routing_mode_counts"] == {"standard": 1, "unknown_conservative": 1}
    assert batch_summary["evaluation_summary"]["average_input_chars"] == 12.0
    assert batch_summary["evaluation_summary"]["quality_gate_status_counts"] == {"passed": 2}
    assert batch_summary["evaluation_summary"]["average_total_prompt_chars"] == 100.0
    assert batch_summary["evaluation_summary"]["average_planned_catalog_count"] == 2.0
    assert batch_summary["aggregate"]["evaluation"]["parser_semantic_assist_activated_count"] == 1
    assert batch_summary["aggregate"]["evaluation"]["parser_semantic_assist_applied_count"] == 1
    assert batch_summary["aggregate"]["evaluation"]["average_target_zone_count"] == 2.0
    assert batch_summary["aggregate"]["evaluation"]["average_matched_extraction_field_count"] == 2.0
    assert batch_summary["aggregate"]["evaluation"]["average_base_hit_field_count"] == 1.0
    assert batch_summary["aggregate"]["evaluation"]["average_required_hit_field_count"] == 1.0
    assert batch_summary["aggregate"]["evaluation"]["average_optional_hit_field_count"] == 0.0
    assert batch_summary["aggregate"]["evaluation"]["average_unknown_fallback_hit_field_count"] == 0.0
    assert batch_summary["aggregate"]["evaluation"]["average_clause_unit_targeted_count"] == 2.0
    assert batch_summary["aggregate"]["evaluation"]["average_text_fallback_clause_count"] == 0.0
    assert batch_summary["evaluation_summary"]["routing_mode_counts"] == {"standard": 1, "unknown_conservative": 1}
    assert batch_summary["evaluation_summary"]["parser_semantic_assist_activated_count"] == 1
    assert batch_summary["evaluation_summary"]["parser_semantic_assist_applied_count"] == 1
    assert batch_summary["evaluation_summary"]["average_target_zone_count"] == 2.0
    assert batch_summary["evaluation_summary"]["average_matched_extraction_field_count"] == 2.0
    assert batch_summary["evaluation_summary"]["average_base_hit_field_count"] == 1.0
    assert batch_summary["evaluation_summary"]["average_required_hit_field_count"] == 1.0
    assert batch_summary["evaluation_summary"]["average_optional_hit_field_count"] == 0.0
    assert batch_summary["evaluation_summary"]["average_unknown_fallback_hit_field_count"] == 0.0
    assert batch_summary["evaluation_summary"]["average_clause_unit_targeted_count"] == 2.0
    assert batch_summary["evaluation_summary"]["average_text_fallback_clause_count"] == 0.0
    assert batch_summary["evaluation_summary"]["llm_task_status_counts"] == {"completed": 2}
    assert batch_summary["aggregate"]["evaluation"]["largest_prompt_name_counts"] == {"scenario_review": 2}
    assert batch_summary_md.startswith("# 未知品目真实样本回归摘要")
    assert "- 输入数量：2" in batch_summary_md
    assert "- routing_mode_counts：" in batch_summary_md
    assert "- parser_semantic_assist：activated=1, applied=1" in batch_summary_md
    assert "- planning_hits：target_zones=2.0, matched_fields=2.0, base_hits=1.0, required_hits=1.0, optional_hits=0.0, unknown_fallback_hits=0.0" in batch_summary_md
    assert "- clause_targeting：clause_unit_targeted=2.0, text_fallback_clause=0.0" in batch_summary_md
    assert manifest_text.splitlines()[-2:] == [str(input_b.resolve()), str(input_a.resolve())]
    assert manifest_json["label"] == "baseline"
    assert manifest_json["count"] == 2
    assert manifest_json["paths"] == [str(input_b.resolve()), str(input_a.resolve())]


def test_unknown_sample_regression_enhanced_mode_uses_review_report_metrics(tmp_path: Path) -> None:
    input_path = tmp_path / "demo.txt"
    input_path.write_text(
        """
        项目属性：服务
        采购标的：驻场运维服务
        评分标准：综合评分法
        本项目专门面向中小企业采购。
        """,
        encoding="utf-8",
    )

    class FakeEnhancer:
        def __init__(self, timeout: float | None = None) -> None:
            self.timeout = timeout

        def enhance(self, report):
            return replace(
                report,
                review_mode=ReviewMode.enhanced,
                llm_enhanced=True,
                task_records=[
                    *report.task_records,
                    TaskRecord(
                        task_name="llm_scenario_review",
                        status=TaskStatus.completed,
                        detail="任务已完成。预算 1800.0 秒，截止 2026-03-26T00:00:00。耗时 1.50 秒。",
                        item_count=1,
                    ),
                ],
            )

    summary = run_unknown_sample_regression(
        RegressionRunOptions(
            input_paths=[input_path],
            output_dir=tmp_path / "runs",
            review_mode=ReviewMode.enhanced,
            llm_timeout=1800.0,
            review_enhancer_factory=lambda timeout: FakeEnhancer(timeout),
        )
    )

    item = summary.items[0]
    assert item.status == "ok"
    assert item.evaluation_summary["llm_enhanced"] is True
    assert item.evaluation_summary["review_planning_contract"]["planned_catalog_count"] >= 1
    assert item.evaluation_summary["prompt_volume"]["total_chars"] > 0
    assert item.evaluation_summary["task_duration"]["total_seconds"] == 1.5
    assert item.evaluation_summary["llm_task_status_counts"]["completed"] >= 1
    assert summary.evaluation_summary["llm_enhanced_count"] == 1

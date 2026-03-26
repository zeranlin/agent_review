from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from agent_review.engine import TenderReviewEngine
from agent_review.llm.prompts import build_scenario_review_prompt
from agent_review.models import (
    LLMSemanticReview,
    ReviewMode,
    ReviewPointDefinition,
    Severity,
    TaskRecord,
    TaskStatus,
)
from agent_review.outputs import write_review_artifacts


def test_write_review_artifacts_emits_evaluation_summary(tmp_path: Path) -> None:
    text = """
    项目属性：服务
    采购标的：驻场运维服务
    评分标准：综合评分法。
    付款方式：按月支付。
    """
    base_report = TenderReviewEngine(review_mode=ReviewMode.fast).review_text(
        text,
        document_name="demo.txt",
    )
    enhanced_report = replace(
        base_report,
        review_mode=ReviewMode.enhanced,
        llm_enhanced=True,
        llm_semantic_review=LLMSemanticReview(
            dynamic_review_tasks=[
                ReviewPointDefinition(
                    catalog_id="RP-DYN-001",
                    title="项目属性与采购内容结构错配",
                    dimension="项目结构风险",
                    default_severity=Severity.high,
                    task_type="structure",
                    scenario_tags=["dynamic", "structure"],
                    evidence_hints=["项目属性", "采购标的"],
                    rebuttal_templates=[["仅供货", "不含人工服务"]],
                    enhancement_fields=["项目属性", "采购标的"],
                    basis_hint="结构错配。",
                )
            ],
            scoring_dynamic_review_tasks=[
                ReviewPointDefinition(
                    catalog_id="RP-DYN-SCORE-001",
                    title="评分分档主观性与量化充分性复核",
                    dimension="评审标准明确性",
                    default_severity=Severity.high,
                    task_type="scoring",
                    scenario_tags=["dynamic", "scoring"],
                    evidence_hints=["评分方法", "样品分"],
                    rebuttal_templates=[["法定强制认证", "中标后提交"]],
                    enhancement_fields=["评分方法", "样品分"],
                    basis_hint="评分量化。",
                )
            ],
        ),
        task_records=[
            TaskRecord(
                task_name="llm_scenario_review",
                status=TaskStatus.completed,
                detail="任务已完成。预算 1800.0 秒，截止 2026-03-26T00:00:00。耗时 1.25 秒。",
                item_count=1,
            ),
            TaskRecord(
                task_name="llm_scoring_review",
                status=TaskStatus.completed,
                detail="任务已完成。预算 1800.0 秒，截止 2026-03-26T00:00:00。耗时 2.75 秒。",
                item_count=1,
            ),
        ],
    )

    bundle = write_review_artifacts(enhanced_report, base_report, tmp_path)
    manifest = json.loads(Path(bundle.manifest_path).read_text(encoding="utf-8"))
    evaluation_summary = json.loads(Path(bundle.evaluation_summary_path).read_text(encoding="utf-8"))
    llm_tasks = json.loads(Path(bundle.llm_tasks_path).read_text(encoding="utf-8"))

    assert Path(bundle.evaluation_summary_path).exists()
    assert manifest["artifact_paths"]["evaluation_summary"] == bundle.evaluation_summary_path
    assert manifest["evaluation_summary"]["prompt_volume"]["total_chars"] > 0
    assert manifest["evaluation_summary"]["task_duration"]["total_seconds"] == 4.0
    assert manifest["evaluation_summary"]["dynamic_task_counts"]["total_dynamic_review_task_count"] == 2
    assert manifest["evaluation_summary"]["quality_gates"]["count"] == len(enhanced_report.quality_gates)
    assert evaluation_summary["prompt_volume"]["largest_task"]
    assert evaluation_summary["task_duration"]["task_seconds"]["llm_scenario_review"] == 1.25
    assert evaluation_summary["task_duration"]["task_seconds"]["llm_scoring_review"] == 2.75
    assert evaluation_summary["dynamic_task_counts"]["scenario_review_task_count"] == 1
    assert llm_tasks["evaluation_summary"]["quality_gates"]["count"] == len(enhanced_report.quality_gates)
    assert "review_point_metadata" in evaluation_summary
    assert "parser_semantic_assist" in evaluation_summary
    assert "review_planning_contract" in evaluation_summary
    assert evaluation_summary["review_point_metadata"]["required_field_count"] >= 1
    assert evaluation_summary["prompt_volume"]["task_char_counts"]["scenario_review"] == len(
        build_scenario_review_prompt(enhanced_report)
    )

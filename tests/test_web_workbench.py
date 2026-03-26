from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from agent_review.engine import TenderReviewEngine
from agent_review.models import ReviewMode, TaskRecord, TaskStatus
from agent_review.web import ReviewJob, ReviewWebApp


def test_review_web_run_job_populates_workbench_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    upload_path = tmp_path / "demo.txt"
    upload_path.write_text(
        "\n".join(
            [
                "项目名称：示例项目",
                "项目编号：SZCG-100",
                "采购人：某学校",
                "预算金额（元）：120000.00",
                "项目属性：服务",
                "评分标准见附表。",
                "付款方式：以正式合同为准。",
            ]
        ),
        encoding="utf-8",
    )

    base_report = TenderReviewEngine(review_mode=ReviewMode.fast).review_file(upload_path)
    enhanced_report = replace(
        base_report,
        review_mode=ReviewMode.enhanced,
        llm_enhanced=True,
        task_records=[
            TaskRecord(task_name="llm_scenario_review", status=TaskStatus.completed),
            TaskRecord(task_name="llm_scoring_review", status=TaskStatus.completed),
            TaskRecord(task_name="llm_review_point_second_review", status=TaskStatus.completed),
        ],
    )

    class FakeEnhancer:
        def __init__(self, timeout: float | None = None) -> None:
            self.timeout = timeout

    class FakeEngine:
        def __init__(self, dimensions=None, review_enhancer=None, review_mode: ReviewMode = ReviewMode.fast) -> None:
            self.review_mode = review_mode

        def review_file(self, path: str | Path):
            return enhanced_report if self.review_mode == ReviewMode.enhanced else base_report

    monkeypatch.setattr("agent_review.web.QwenReviewEnhancer", FakeEnhancer)
    monkeypatch.setattr("agent_review.web.TenderReviewEngine", FakeEngine)

    app = ReviewWebApp(llm_timeout=12.0)
    app._base_dir = tmp_path
    job = ReviewJob(job_id="job-1", filename=upload_path.name, upload_path=str(upload_path))
    app._jobs[job.job_id] = job

    app._run_review_job(job.job_id)

    stored = app._jobs[job.job_id]
    assert stored.status == "completed"
    assert stored.review_mode == "enhanced"
    assert stored.overall_conclusion
    assert stored.run_dir
    assert stored.header_info["project_name"] == "示例项目"
    assert "procurement_kind" in stored.document_profile
    assert isinstance(stored.domain_profile_candidates, list)
    assert "reviewer_report" in stored.artifact_paths
    assert stored.llm_status["enhanced"] is True


def test_review_web_completed_page_renders_workbench_sections_and_artifact_page(tmp_path: Path) -> None:
    reviewer_report_path = tmp_path / "reviewer_report.md"
    reviewer_report_path.write_text("**招标文件合规审查意见书**", encoding="utf-8")
    evaluation_path = tmp_path / "evaluation_summary.json"
    evaluation_path.write_text('{"ok": true}', encoding="utf-8")

    app = ReviewWebApp()
    completed_job = ReviewJob(
        job_id="done-job",
        filename="demo.txt",
        upload_path="/tmp/demo.txt",
        status="completed",
        review_mode="enhanced",
        overall_conclusion="存在个别条款待完善，建议优化后发出",
        run_dir=str(tmp_path),
        reviewer_report_path=str(reviewer_report_path),
        reviewer_report_markdown="**招标文件合规审查意见书**\n\n**一、审查结论**\n存在风险。",
        header_info={"project_name": "示例项目", "purchaser_name": "某学校"},
        document_profile={
            "procurement_kind": "service",
            "procurement_kind_confidence": 0.8,
            "routing_mode": "standard",
            "primary_review_types": ["评分", "合同"],
            "structure_flags": ["heavy_scoring_tables"],
            "quality_flags": [],
            "unknown_structure_flags": [],
            "dominant_zones": [{"zone_type": "scoring", "ratio": 0.3, "unit_count": 3}],
            "domain_profile_candidates": [{"profile_id": "generic_service", "confidence": 0.84, "reasons": ["服务"]}],
        },
        planning_summary={
            "target_zones": ["scoring", "contract"],
            "target_primary_review_types": ["评分", "合同"],
            "activated_risk_families": ["scoring", "contract"],
            "planned_catalog_ids": ["RP-001"],
            "high_value_fields": ["付款节点"],
            "matched_extraction_fields": ["付款节点"],
            "summary": "已规划 1 个审查点。",
        },
        high_risk_items=[{"title": "评分规则不清晰", "severity": "high", "source": "review_point", "reason": "量化不足"}],
        pending_confirmation_items=[{"title": "付款条件待复核", "severity": "medium", "source": "review_point", "reason": "证据不足"}],
        llm_tasks=[{"task_name": "llm_scenario_review", "status": "completed", "item_count": 1, "detail": "完成"}],
        llm_status={"enhanced": True, "warnings": [], "task_count": 1},
        artifact_paths={
            "reviewer_report": str(reviewer_report_path),
            "evaluation_summary": str(evaluation_path),
        },
    )
    app._jobs[completed_job.job_id] = completed_job

    responses: list[tuple[str, list[tuple[str, str]]]] = []

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        responses.append((status, headers))

    completed_payload = b"".join(app._handle_review_page(completed_job.job_id, start_response)).decode("utf-8")
    artifact_payload = b"".join(
        app._handle_artifact_page(completed_job.job_id, "evaluation_summary", start_response)
    ).decode("utf-8")

    assert responses[0][0] == "200 OK"
    assert "审查工作台" in completed_payload
    assert "头部信息" in completed_payload
    assert "结构画像" in completed_payload
    assert "审查规划" in completed_payload
    assert "风险工作台" in completed_payload
    assert "增强状态" in completed_payload
    assert "运行产物" in completed_payload
    assert "示例项目" in completed_payload
    assert "/artifact/done-job/evaluation_summary" in completed_payload
    assert "evaluation_summary" in artifact_payload
    assert "{&quot;ok&quot;: true}" in artifact_payload

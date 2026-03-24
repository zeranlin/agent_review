from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from ..models import ReviewReport
from ..reporting import render_json, render_markdown


@dataclass(slots=True)
class ArtifactBundle:
    run_dir: str
    base_json_path: str
    base_markdown_path: str
    final_json_path: str
    final_markdown_path: str
    manifest_path: str
    llm_tasks_path: str
    specialist_table_paths: dict[str, dict[str, str]]


def write_review_artifacts(
    report: ReviewReport,
    base_report: ReviewReport,
    output_dir: str | Path | None = None,
) -> ArtifactBundle:
    document_stem = Path(report.file_info.document_name).stem
    target_dir = Path(output_dir or Path.cwd() / "runs" / document_stem).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    base_json_path = target_dir / "base_report.json"
    base_markdown_path = target_dir / "base_report.md"
    final_json_path = target_dir / "enhanced_report.json"
    final_markdown_path = target_dir / "enhanced_report.md"

    base_json_path.write_text(render_json(base_report), encoding="utf-8")
    base_markdown_path.write_text(render_markdown(base_report), encoding="utf-8")
    final_json_path.write_text(render_json(report), encoding="utf-8")
    final_markdown_path.write_text(render_markdown(report), encoding="utf-8")
    specialist_table_paths = _write_specialist_tables(
        target_dir=target_dir,
        base_report=base_report,
        report=report,
    )
    llm_tasks_path = target_dir / "llm_tasks.json"
    llm_tasks_path.write_text(
        json.dumps(_build_llm_tasks_payload(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest_path = target_dir / "run_manifest.json"
    manifest_payload = _build_run_manifest(
        target_dir=target_dir,
        base_report=base_report,
        report=report,
        specialist_table_paths=specialist_table_paths,
        base_json_path=base_json_path,
        base_markdown_path=base_markdown_path,
        final_json_path=final_json_path,
        final_markdown_path=final_markdown_path,
        llm_tasks_path=llm_tasks_path,
    )
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return ArtifactBundle(
        run_dir=str(target_dir),
        base_json_path=str(base_json_path),
        base_markdown_path=str(base_markdown_path),
        final_json_path=str(final_json_path),
        final_markdown_path=str(final_markdown_path),
        manifest_path=str(manifest_path),
        llm_tasks_path=str(llm_tasks_path),
        specialist_table_paths=specialist_table_paths,
    )


def _write_specialist_tables(
    target_dir: Path,
    base_report: ReviewReport,
    report: ReviewReport,
) -> dict[str, dict[str, str]]:
    table_names = [
        "project_structure",
        "sme_policy",
        "personnel_boundary",
        "contract_performance",
        "template_conflicts",
    ]
    outputs: dict[str, dict[str, str]] = {}
    for table_name in table_names:
        base_path = target_dir / f"{table_name}_table.base.json"
        final_path = target_dir / f"{table_name}_table.json"
        base_payload = _table_payload(base_report, table_name)
        final_payload = _table_payload(report, table_name)
        base_path.write_text(json.dumps(base_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        final_path.write_text(json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs[table_name] = {
            "base": str(base_path),
            "final": str(final_path),
        }
    return outputs


def _table_payload(report: ReviewReport, table_name: str) -> dict[str, object]:
    rows = getattr(report.specialist_tables, table_name)
    return {
        "table_name": table_name,
        "document_name": report.file_info.document_name,
        "review_mode": report.review_mode.value,
        "llm_enhanced": report.llm_enhanced,
        "summary": report.specialist_tables.summaries.get(table_name, ""),
        "rows": [item.to_dict() for item in rows],
    }


def _build_run_manifest(
    target_dir: Path,
    base_report: ReviewReport,
    report: ReviewReport,
    specialist_table_paths: dict[str, dict[str, str]],
    base_json_path: Path,
    base_markdown_path: Path,
    final_json_path: Path,
    final_markdown_path: Path,
    llm_tasks_path: Path,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "run_dir": str(target_dir),
        "document_name": report.file_info.document_name,
        "review_mode": report.review_mode.value,
        "overall_conclusion": report.overall_conclusion.value,
        "llm": {
            "requested": report.review_mode.value == "enhanced",
            "enhanced": report.llm_enhanced,
            "warnings": report.llm_warnings,
            "tasks_path": str(llm_tasks_path),
            "tasks": [item.to_dict() for item in report.task_records if item.task_name.startswith("llm_")],
            "semantic_review": {
                "clause_supplement_count": len(report.llm_semantic_review.clause_supplements),
                "specialist_finding_count": len(report.llm_semantic_review.specialist_findings),
                "consistency_finding_count": len(report.llm_semantic_review.consistency_findings),
                "verdict_review": report.llm_semantic_review.verdict_review,
            },
        },
        "parse_summary": {
            "parser_name": report.parse_result.parser_name,
            "source_format": report.parse_result.source_format,
            "page_count": report.parse_result.page_count,
            "table_count": len(report.parse_result.tables),
            "warnings": report.parse_result.warnings,
        },
        "stage_records": [item.to_dict() for item in report.stage_records],
        "task_records": [item.to_dict() for item in report.task_records],
        "artifact_paths": {
            "base_report": {
                "json": str(base_json_path),
                "markdown": str(base_markdown_path),
                "review_mode": base_report.review_mode.value,
            },
            "final_report": {
                "json": str(final_json_path),
                "markdown": str(final_markdown_path),
                "review_mode": report.review_mode.value,
            },
            "specialist_tables": specialist_table_paths,
            "llm_tasks": str(llm_tasks_path),
        },
    }


def _build_llm_tasks_payload(report: ReviewReport) -> dict[str, object]:
    return {
        "document_name": report.file_info.document_name,
        "review_mode": report.review_mode.value,
        "llm_enhanced": report.llm_enhanced,
        "warnings": report.llm_warnings,
        "tasks": [item.to_dict() for item in report.task_records if item.task_name.startswith("llm_")],
    }

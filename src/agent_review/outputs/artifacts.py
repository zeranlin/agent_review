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

    return ArtifactBundle(
        run_dir=str(target_dir),
        base_json_path=str(base_json_path),
        base_markdown_path=str(base_markdown_path),
        final_json_path=str(final_json_path),
        final_markdown_path=str(final_markdown_path),
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

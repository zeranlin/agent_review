from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..models import ReviewReport
from ..reporting import render_json, render_markdown


@dataclass(slots=True)
class ArtifactBundle:
    run_dir: str
    base_json_path: str
    base_markdown_path: str
    final_json_path: str
    final_markdown_path: str


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

    return ArtifactBundle(
        run_dir=str(target_dir),
        base_json_path=str(base_json_path),
        base_markdown_path=str(base_markdown_path),
        final_json_path=str(final_json_path),
        final_markdown_path=str(final_markdown_path),
    )

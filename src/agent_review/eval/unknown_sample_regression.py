from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import argparse
import json
from pathlib import Path
from typing import Sequence

from ..adjudication import build_review_points_from_task_library, build_formal_adjudication
from ..applicability import build_applicability_checks
from ..domain_profiles import (
    build_document_profile as build_domain_profile,
    profile_activation_tags,
)
from ..extractors import classify_extracted_clauses, extract_clauses, extract_clauses_from_units
from ..models import FormalAdjudication, QualityGateStatus, ReviewMode
from ..parsers import load_document
from ..review_quality_gate import build_review_quality_gates
from ..structure.document_profile import build_document_profile as build_structure_profile


@dataclass(slots=True)
class RegressionRunOptions:
    input_paths: list[Path] = field(default_factory=list)
    output_dir: Path = Path("runs/unknown_sample_regression")
    review_mode: ReviewMode = ReviewMode.fast
    max_candidates: int = 3
    write_outputs: bool = True
    emit_manifest: bool = False
    manifest_label: str = "baseline"


@dataclass(slots=True)
class FileRegressionSummary:
    document_name: str
    source_path: str
    status: str
    parse_summary: dict[str, object]
    document_profile: dict[str, object]
    domain_profile: dict[str, object]
    quality_gate_summary: dict[str, object]
    formal_summary: dict[str, object]
    review_point_summary: dict[str, object]
    evaluation_summary: dict[str, object]
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "source_path": self.source_path,
            "status": self.status,
            "parse_summary": self.parse_summary,
            "document_profile": self.document_profile,
            "domain_profile": self.domain_profile,
            "quality_gate_summary": self.quality_gate_summary,
            "formal_summary": self.formal_summary,
            "review_point_summary": self.review_point_summary,
            "evaluation_summary": self.evaluation_summary,
            "error": self.error,
        }


@dataclass(slots=True)
class BatchRegressionSummary:
    generated_at: str
    review_mode: str
    input_count: int
    succeeded_count: int
    failed_count: int
    items: list[FileRegressionSummary]
    aggregate: dict[str, object]
    evaluation_summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "review_mode": self.review_mode,
            "input_count": self.input_count,
            "succeeded_count": self.succeeded_count,
            "failed_count": self.failed_count,
            "aggregate": self.aggregate,
            "evaluation_summary": self.evaluation_summary,
            "items": [item.to_dict() for item in self.items],
        }


def run_unknown_sample_regression(options: RegressionRunOptions) -> BatchRegressionSummary:
    input_paths = _canonicalize_paths(options.input_paths)
    if not input_paths:
        raise ValueError("至少需要提供一个未知品目样本文件。")

    results = [_run_single_file(path, options) for path in input_paths]
    results.sort(key=lambda item: (item.source_path, item.document_name))
    summary = BatchRegressionSummary(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        review_mode=options.review_mode.value,
        input_count=len(results),
        succeeded_count=sum(1 for item in results if item.status == "ok"),
        failed_count=sum(1 for item in results if item.status != "ok"),
        items=results,
        aggregate=_build_aggregate_summary(results),
        evaluation_summary=_build_batch_evaluation_summary(results),
    )

    if options.write_outputs:
        _write_outputs(summary, options.output_dir)
    if options.emit_manifest:
        _write_manifest(
            summary,
            options.output_dir,
            label=options.manifest_label,
        )
    return summary


def _run_single_file(path: Path, options: RegressionRunOptions) -> FileRegressionSummary:
    target = Path(path).expanduser().resolve()
    document_name, parse_result = load_document(target)
    extracted_clauses = _build_extracted_clauses(parse_result)
    structure_profile = parse_result.document_profile or build_structure_profile(parse_result, document_name)
    domain_profile = build_domain_profile(
        parse_result.text,
        extracted_clauses,
        document_id=parse_result.source_path or str(target),
        source_path=parse_result.source_path or str(target),
    )

    review_points = build_review_points_from_task_library(parse_result.text, extracted_clauses)
    applicability_checks = build_applicability_checks(review_points, extracted_clauses)
    quality_gates = build_review_quality_gates(review_points, extracted_clauses)

    formal_summary, formal_items, formal_error = _build_formal_summary(
        review_points,
        applicability_checks,
        quality_gates,
        parse_result.text,
        extracted_clauses,
        parse_result.tables,
    )

    return FileRegressionSummary(
        document_name=document_name,
        source_path=str(target),
        status="ok" if not formal_error else "partial",
        parse_summary=_build_parse_summary(parse_result, len(extracted_clauses)),
        document_profile=_build_structure_profile_summary(structure_profile),
        domain_profile=_build_domain_profile_summary(domain_profile, options.max_candidates),
        quality_gate_summary=_build_quality_gate_summary(quality_gates),
        formal_summary={
            **formal_summary,
            "items": formal_items[: options.max_candidates],
        },
        review_point_summary=_build_review_point_summary(review_points, applicability_checks),
        evaluation_summary=_build_file_evaluation_summary(
            parse_result,
            extracted_clauses,
            review_points,
            applicability_checks,
            quality_gates,
            formal_summary,
            domain_profile,
        ),
        error=formal_error,
    )


def _build_extracted_clauses(parse_result):
    clause_units = parse_result.clause_units or []
    clauses = extract_clauses_from_units(clause_units) if clause_units else []
    fallback_clauses = extract_clauses(parse_result.text)
    clauses = _merge_clauses(clauses, fallback_clauses)
    return classify_extracted_clauses(clauses)


def _merge_clauses(primary, fallback):
    seen: set[tuple[str, str, str]] = set()
    merged = []
    for clause in [*primary, *fallback]:
        key = (clause.field_name, clause.source_anchor, clause.content)
        if key in seen:
            continue
        seen.add(key)
        merged.append(clause)
    return merged


def _build_parse_summary(parse_result, extracted_clause_count: int) -> dict[str, object]:
    return {
        "parser_name": parse_result.parser_name,
        "source_format": parse_result.source_format,
        "page_count": parse_result.page_count,
        "document_node_count": len(parse_result.document_nodes),
        "semantic_zone_count": len(parse_result.semantic_zones),
        "clause_unit_count": len(parse_result.clause_units),
        "extracted_clause_count": extracted_clause_count,
        "warning_count": len(parse_result.warnings),
    }


def _build_structure_profile_summary(profile) -> dict[str, object]:
    return {
        "document_id": profile.document_id,
        "procurement_kind": profile.procurement_kind,
        "procurement_kind_confidence": profile.procurement_kind_confidence,
        "domain_profile_candidates": [
            item.to_dict() for item in profile.domain_profile_candidates[:3]
        ],
        "structure_flags": profile.structure_flags,
        "quality_flags": profile.quality_flags,
        "unknown_structure_flags": profile.unknown_structure_flags,
        "risk_activation_hints": profile.risk_activation_hints,
        "summary": profile.summary,
    }


def _build_domain_profile_summary(profile, max_candidates: int) -> dict[str, object]:
    return {
        "document_id": profile.document_id,
        "procurement_kind": profile.procurement_kind,
        "procurement_kind_confidence": profile.procurement_kind_confidence,
        "top_candidates": [item.to_dict() for item in profile.domain_profile_candidates[:max_candidates]],
        "activation_tags": sorted(profile_activation_tags(profile)),
        "structure_flags": profile.structure_flags,
        "quality_flags": profile.quality_flags,
        "unknown_structure_flags": profile.unknown_structure_flags,
        "summary": profile.summary,
    }


def _build_quality_gate_summary(quality_gates) -> dict[str, object]:
    counts = Counter(item.status.value for item in quality_gates)
    return {
        "count": len(quality_gates),
        "status_counts": dict(counts),
        "top_items": [
            {
                "point_id": item.point_id,
                "status": item.status.value,
                "duplicate_of": item.duplicate_of,
                "reasons": item.reasons[:3],
            }
            for item in quality_gates[:3]
        ],
    }


def _build_review_point_summary(review_points, applicability_checks) -> dict[str, object]:
    applicability_map = {item.point_id: item for item in applicability_checks}
    return {
        "count": len(review_points),
        "applicable_count": sum(1 for item in applicability_checks if item.applicable),
        "catalog_ids": [item.catalog_id for item in review_points[:10]],
        "task_titles": [item.title for item in review_points[:10]],
        "applicability_preview": [
            {
                "point_id": item.point_id,
                "catalog_id": item.catalog_id,
                "applicable": item.applicable,
                "summary": item.summary,
            }
            for item in applicability_checks[:5]
        ],
        "applicability_match": {
            point_id: applicability_map[point_id].summary
            for point_id in list(applicability_map)[:5]
        },
    }


def _build_file_evaluation_summary(
    parse_result,
    extracted_clauses,
    review_points,
    applicability_checks,
    quality_gates,
    formal_summary,
    domain_profile,
) -> dict[str, object]:
    quality_counts = Counter(item.status.value for item in quality_gates)
    applicable_count = sum(1 for item in applicability_checks if item.applicable)
    formal_included_count = int(formal_summary.get("included_count", 0) or 0)
    return {
        "input_chars": len(parse_result.text),
        "document_node_count": len(parse_result.document_nodes),
        "clause_unit_count": len(parse_result.clause_units),
        "extracted_clause_count": len(extracted_clauses),
        "review_point_count": len(review_points),
        "applicable_count": applicable_count,
        "quality_gate_count": len(quality_gates),
        "quality_gate_status_counts": _sorted_counter_dict(quality_counts),
        "formal_included_count": formal_included_count,
        "formal_mode": formal_summary.get("mode", "unknown"),
        "domain_candidate_count": len(domain_profile.get("top_candidates", [])),
    }


def _build_formal_summary(
    review_points,
    applicability_checks,
    quality_gates,
    report_text: str,
    extracted_clauses,
    parse_tables,
) -> tuple[dict[str, object], list[dict[str, object]], str]:
    try:
        adjudications: list[FormalAdjudication] = build_formal_adjudication(
            review_points,
            applicability_checks,
            quality_gates,
            report_text,
            extracted_clauses,
            parse_tables,
        )
        return _summarize_formal_adjudication(adjudications, mode="actual"), [
            _formal_item_to_dict(item) for item in adjudications
        ], ""
    except Exception as exc:  # pragma: no cover - fallback path is useful in broken pipelines
        formal_error = f"{type(exc).__name__}: {exc}"
        return _summarize_formal_fallback(review_points, applicability_checks, quality_gates), [], formal_error


def _summarize_formal_adjudication(adjudications: list[FormalAdjudication], *, mode: str) -> dict[str, object]:
    counts = Counter(item.disposition.value for item in adjudications)
    included = [item for item in adjudications if item.included_in_formal]
    manual = [item for item in adjudications if item.disposition.value == "manual_confirmation"]
    return {
        "mode": mode,
        "count": len(adjudications),
        "disposition_counts": dict(counts),
        "included_count": len(included),
        "manual_confirmation_count": len(manual),
        "top_included": [
            {
                "point_id": item.point_id,
                "catalog_id": item.catalog_id,
                "title": item.title,
                "disposition": item.disposition.value,
                "primary_quote": item.primary_quote,
                "section_hint": item.section_hint,
            }
            for item in included[:5]
        ],
    }


def _summarize_formal_fallback(review_points, applicability_checks, quality_gates) -> dict[str, object]:
    quality_map = {item.point_id: item for item in quality_gates}
    applicability_map = {item.point_id: item for item in applicability_checks}
    ready = []
    blocked = []
    manual = []
    for point in review_points:
        quality = quality_map.get(point.point_id)
        applicability = applicability_map.get(point.point_id)
        quality_status = quality.status.value if quality else "unknown"
        applicable = bool(applicability.applicable) if applicability else False
        if quality_status == QualityGateStatus.filtered.value:
            blocked.append(point)
        elif quality_status == QualityGateStatus.manual_confirmation.value or not applicable:
            manual.append(point)
        else:
            ready.append(point)
    return {
        "mode": "fallback",
        "count": len(review_points),
        "included_count": len(ready),
        "manual_confirmation_count": len(manual),
        "filtered_count": len(blocked),
        "top_ready": [
            {
                "point_id": item.point_id,
                "catalog_id": item.catalog_id,
                "title": item.title,
                "severity": item.severity.value,
            }
            for item in ready[:5]
        ],
    }


def _formal_item_to_dict(item: FormalAdjudication) -> dict[str, object]:
    return {
        "point_id": item.point_id,
        "catalog_id": item.catalog_id,
        "title": item.title,
        "disposition": item.disposition.value,
        "included_in_formal": item.included_in_formal,
        "quality_gate_status": item.quality_gate_status.value,
        "evidence_sufficient": item.evidence_sufficient,
        "review_reason": item.review_reason,
        "primary_quote": item.primary_quote,
        "section_hint": item.section_hint,
    }


def _build_aggregate_summary(results: list[FileRegressionSummary]) -> dict[str, object]:
    procurement_counter = Counter(item.document_profile.get("procurement_kind", "unknown") for item in results)
    domain_counter = Counter(
        candidate["profile_id"]
        for item in results
        for candidate in item.domain_profile.get("top_candidates", [])
    )
    quality_gate_counter = Counter()
    for item in results:
        quality_gate_counter.update(item.quality_gate_summary.get("status_counts", {}))
    formal_mode_counter = Counter(item.formal_summary.get("mode", "unknown") for item in results)
    evaluation_gate_counter = Counter()
    for item in results:
        evaluation_gate_counter.update(item.evaluation_summary.get("quality_gate_status_counts", {}))
    average_input_chars = _average(item.evaluation_summary.get("input_chars", 0) for item in results)
    average_review_points = _average(item.evaluation_summary.get("review_point_count", 0) for item in results)
    average_quality_gates = _average(item.evaluation_summary.get("quality_gate_count", 0) for item in results)
    return {
        "procurement_kind_counts": _sorted_counter_dict(procurement_counter),
        "domain_profile_hit_counts": _sorted_counter_dict(domain_counter),
        "quality_gate_status_counts": _sorted_counter_dict(quality_gate_counter),
        "formal_modes": _sorted_counter_dict(formal_mode_counter),
        "formal_error_count": sum(1 for item in results if item.error),
        "result_status_counts": _sorted_counter_dict(Counter(item.status for item in results)),
        "evaluation": {
            "average_input_chars": average_input_chars,
            "average_review_point_count": average_review_points,
            "average_quality_gate_count": average_quality_gates,
            "quality_gate_status_counts": _sorted_counter_dict(evaluation_gate_counter),
        },
    }


def _build_batch_evaluation_summary(results: list[FileRegressionSummary]) -> dict[str, object]:
    quality_counts = Counter()
    input_chars = []
    review_points = []
    quality_gate_counts = []
    formal_included = []
    for item in results:
        evaluation = item.evaluation_summary
        quality_counts.update(evaluation.get("quality_gate_status_counts", {}))
        input_chars.append(evaluation.get("input_chars", 0))
        review_points.append(evaluation.get("review_point_count", 0))
        quality_gate_counts.append(evaluation.get("quality_gate_count", 0))
        formal_included.append(evaluation.get("formal_included_count", 0))

    total_quality_gates = sum(float(item) for item in quality_gate_counts)
    total_manual_or_filtered = sum(
        float(count) for key, count in quality_counts.items() if key in {"manual_confirmation", "filtered"}
    )
    return {
        "file_count": len(results),
        "average_input_chars": _average(input_chars),
        "average_review_point_count": _average(review_points),
        "average_quality_gate_count": _average(quality_gate_counts),
        "average_formal_included_count": _average(formal_included),
        "quality_gate_status_counts": _sorted_counter_dict(quality_counts),
        "manual_or_filtered_rate": round(total_manual_or_filtered / total_quality_gates, 3)
        if total_quality_gates
        else 0.0,
    }


def _write_outputs(summary: BatchRegressionSummary, output_dir: Path) -> None:
    target_dir = output_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "batch_summary.json").write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (target_dir / "batch_summary.md").write_text(
        _render_markdown(summary),
        encoding="utf-8",
    )
    file_dir = target_dir / "files"
    file_dir.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(summary.items, start=1):
        safe_name = _safe_name(item.document_name)
        (file_dir / f"{index:03d}_{safe_name}.json").write_text(
            json.dumps(item.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _write_manifest(summary: BatchRegressionSummary, output_dir: Path, *, label: str) -> None:
    target_dir = output_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_paths = _canonicalize_paths(Path(item.source_path) for item in summary.items)
    manifest_text = build_manifest_text(manifest_paths, label=label)
    (target_dir / "baseline_manifest.txt").write_text(manifest_text, encoding="utf-8")
    (target_dir / "baseline_manifest.json").write_text(
        json.dumps(
            {
                "label": label,
                "count": len(manifest_paths),
                "paths": [str(path) for path in manifest_paths],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def build_manifest_text(paths: Sequence[Path], *, label: str = "baseline") -> str:
    canonical_paths = _canonicalize_paths(paths)
    lines = [
        "# agent_review unknown sample regression manifest",
        f"# label: {label}",
        f"# count: {len(canonical_paths)}",
    ]
    lines.extend(str(path) for path in canonical_paths)
    return "\n".join(lines) + "\n"


def _render_markdown(summary: BatchRegressionSummary) -> str:
    lines = [
        "# 未知品目真实样本回归摘要",
        "",
        f"- 生成时间：{summary.generated_at}",
        f"- 运行模式：{summary.review_mode}",
        f"- 输入数量：{summary.input_count}",
        f"- 成功：{summary.succeeded_count}",
        f"- 失败/降级：{summary.failed_count}",
        "",
        "## 聚合摘要",
    ]
    for key, value in summary.aggregate.items():
        lines.append(f"- {key}：{value}")
    lines.extend(
        [
            "",
            "## 评测闭环",
            "",
            f"- evaluation_summary：{summary.evaluation_summary}",
        ]
    )
    lines.append("")
    for item in summary.items:
        lines.extend(
            [
                f"## {item.document_name}",
                f"- 路径：{item.source_path}",
                f"- 状态：{item.status}",
                f"- 画像：{item.document_profile.get('procurement_kind', 'unknown')} / {item.document_profile.get('summary', '')}",
                f"- 领域：{_compact_profile_candidates(item.domain_profile.get('top_candidates', []))}",
                f"- quality gate：{item.quality_gate_summary.get('status_counts', {})}",
                f"- formal：{item.formal_summary.get('mode', 'unknown')} / {item.formal_summary.get('count', 0)}",
                f"- eval：{item.evaluation_summary}",
            ]
        )
        if item.error:
            lines.append(f"- 错误：{item.error}")
        lines.append("")
    return "\n".join(lines)


def _compact_profile_candidates(candidates: list[dict[str, object]]) -> str:
    if not candidates:
        return "none"
    return ", ".join(f"{item.get('profile_id')}:{item.get('confidence')}" for item in candidates[:3])


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name)
    return cleaned.strip("_") or "sample"


def _canonicalize_paths(paths: Sequence[Path]) -> list[Path]:
    deduped: list[Path] = []
    seen: set[str] = set()
    for raw_path in paths:
        resolved = Path(raw_path).expanduser().resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(resolved)
    deduped.sort(key=lambda item: str(item))
    return deduped


def _sorted_counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _average(values) -> float:
    numbers = [float(item) for item in values]
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 3)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量运行未知品目真实样本回归。")
    parser.add_argument("paths", nargs="*", help="待审查文件路径。")
    parser.add_argument("--manifest", help="换行分隔的文件清单。")
    parser.add_argument("--output-dir", default="runs/unknown_sample_regression", help="输出目录。")
    parser.add_argument(
        "--review-mode",
        choices=[item.value for item in ReviewMode],
        default=ReviewMode.fast.value,
        help="运行模式，默认 fast。",
    )
    parser.add_argument("--max-candidates", type=int, default=3, help="保留的领域候选上限。")
    parser.add_argument("--no-write-outputs", action="store_true", help="仅打印，不落盘。")
    parser.add_argument("--emit-manifest", action="store_true", help="写出规范化 baseline manifest。")
    parser.add_argument("--manifest-label", default="baseline", help="写出 manifest 时使用的标签。")
    return parser.parse_args(argv)


def load_paths_from_manifest(manifest: str | Path | None) -> list[Path]:
    if not manifest:
        return []
    path = Path(manifest).expanduser().resolve()
    entries: list[Path] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        candidate = Path(line).expanduser()
        if not candidate.is_absolute():
            candidate = (path.parent / candidate).resolve()
        entries.append(candidate)
    return _canonicalize_paths(entries)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    input_paths = _canonicalize_paths([Path(item).expanduser() for item in args.paths] + load_paths_from_manifest(args.manifest))
    options = RegressionRunOptions(
        input_paths=input_paths,
        output_dir=Path(args.output_dir),
        review_mode=ReviewMode(args.review_mode),
        max_candidates=args.max_candidates,
        write_outputs=not args.no_write_outputs,
        emit_manifest=args.emit_manifest,
        manifest_label=args.manifest_label,
    )
    summary = run_unknown_sample_regression(options)
    print(_render_markdown(summary))
    return 0 if summary.failed_count == 0 else 1

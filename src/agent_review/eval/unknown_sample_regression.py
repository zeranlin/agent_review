from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import argparse
import json
from pathlib import Path
from typing import Callable, Sequence

from ..domain_profiles import profile_activation_tags
from ..engine import TenderReviewEngine
from ..enhancement import run_review_enhancement_with_watchdog
from ..llm import QwenReviewEnhancer
from ..models import ReviewMode
from ..outputs import build_output_evaluation_summary


@dataclass(slots=True)
class RegressionRunOptions:
    input_paths: list[Path] = field(default_factory=list)
    output_dir: Path = Path("runs/unknown_sample_regression")
    review_mode: ReviewMode = ReviewMode.fast
    llm_timeout: float = 1800.0
    max_candidates: int = 3
    write_outputs: bool = True
    emit_manifest: bool = False
    manifest_label: str = "baseline"
    review_enhancer_factory: Callable[[float], object] | None = None


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
    try:
        report = _build_review_report(target, options)
    except Exception as exc:  # pragma: no cover - regression should preserve batch progress on broken samples
        return FileRegressionSummary(
            document_name=target.name,
            source_path=str(target),
            status="failed",
            parse_summary={},
            document_profile={},
            domain_profile={},
            quality_gate_summary={},
            formal_summary={},
            review_point_summary={},
            evaluation_summary={},
            error=f"{type(exc).__name__}: {exc}",
        )

    parse_result = report.parse_result
    structure_profile = parse_result.document_profile
    domain_profile = structure_profile
    formal_summary = _build_formal_summary(report)
    formal_items = [_formal_item_to_dict(item) for item in report.formal_adjudication]
    return FileRegressionSummary(
        document_name=report.file_info.document_name,
        source_path=str(target),
        status=_build_file_status(report),
        parse_summary=_build_parse_summary(report),
        document_profile=_build_structure_profile_summary(structure_profile),
        domain_profile=_build_domain_profile_summary(domain_profile, options.max_candidates),
        quality_gate_summary=_build_quality_gate_summary(report.quality_gates),
        formal_summary={
            **formal_summary,
            "items": formal_items[: options.max_candidates],
        },
        review_point_summary=_build_review_point_summary(report.review_points, report.applicability_checks),
        evaluation_summary=_build_file_evaluation_summary(report, domain_profile),
        error="; ".join(report.llm_warnings),
    )


def _build_review_report(target: Path, options: RegressionRunOptions):
    base_report = TenderReviewEngine(review_mode=ReviewMode.fast).review_file(target)
    if options.review_mode != ReviewMode.enhanced:
        return base_report

    enhancer_factory = options.review_enhancer_factory or (lambda timeout: QwenReviewEnhancer(timeout=timeout))
    enhancer = enhancer_factory(options.llm_timeout)
    report, _ = run_review_enhancement_with_watchdog(
        base_report=base_report,
        enhancer=enhancer,
        timeout_seconds=options.llm_timeout,
    )
    return report


def _build_file_status(report) -> str:
    if report.review_mode == ReviewMode.enhanced and report.llm_warnings:
        return "partial"
    return "ok"


def _build_parse_summary(report) -> dict[str, object]:
    parse_result = report.parse_result
    return {
        "parser_name": parse_result.parser_name,
        "source_format": parse_result.source_format,
        "page_count": parse_result.page_count,
        "document_node_count": len(parse_result.document_nodes),
        "semantic_zone_count": len(parse_result.semantic_zones),
        "clause_unit_count": len(parse_result.clause_units),
        "extracted_clause_count": len(report.extracted_clauses),
        "warning_count": len(parse_result.warnings),
    }


def _build_structure_profile_summary(profile) -> dict[str, object]:
    if profile is None:
        return {
            "document_id": "",
            "procurement_kind": "unknown",
            "procurement_kind_confidence": 0.0,
            "domain_profile_candidates": [],
            "structure_flags": [],
            "quality_flags": [],
            "unknown_structure_flags": [],
            "risk_activation_hints": [],
            "summary": "未生成文档画像。",
        }
    return {
        "document_id": profile.document_id,
        "procurement_kind": profile.procurement_kind,
        "procurement_kind_confidence": profile.procurement_kind_confidence,
        "routing_mode": profile.routing_mode,
        "routing_reasons": profile.routing_reasons,
        "domain_profile_candidates": [
            item.to_dict() for item in profile.domain_profile_candidates[:3]
        ],
        "structure_flags": profile.structure_flags,
        "quality_flags": profile.quality_flags,
        "unknown_structure_flags": profile.unknown_structure_flags,
        "parser_semantic_assist_activated": profile.parser_semantic_assist_activated,
        "parser_semantic_assist_reviewed_count": profile.parser_semantic_assist_reviewed_count,
        "parser_semantic_assist_applied_count": profile.parser_semantic_assist_applied_count,
        "risk_activation_hints": profile.risk_activation_hints,
        "summary": profile.summary,
    }


def _build_domain_profile_summary(profile, max_candidates: int) -> dict[str, object]:
    if profile is None:
        return {
            "document_id": "",
            "procurement_kind": "unknown",
            "procurement_kind_confidence": 0.0,
            "top_candidates": [],
            "activation_tags": [],
            "structure_flags": [],
            "quality_flags": [],
            "unknown_structure_flags": [],
            "summary": "未生成领域画像候选。",
        }
    return {
        "document_id": profile.document_id,
        "procurement_kind": profile.procurement_kind,
        "procurement_kind_confidence": profile.procurement_kind_confidence,
        "routing_mode": profile.routing_mode,
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


def _build_file_evaluation_summary(report, domain_profile) -> dict[str, object]:
    parse_result = report.parse_result
    quality_counts = Counter(item.status.value for item in report.quality_gates)
    applicable_count = sum(1 for item in report.applicability_checks if item.applicable)
    formal_included_count = sum(1 for item in report.formal_adjudication if item.included_in_formal)
    planning_contract = report.review_planning_contract
    planning_counts = {
        "routing_mode": planning_contract.routing_mode if planning_contract else "",
        "route_tag_count": len(planning_contract.route_tags) if planning_contract else 0,
        "routing_flag_count": len(planning_contract.routing_flags) if planning_contract else 0,
        "activation_reason_count": len(planning_contract.activation_reasons) if planning_contract else 0,
        "activated_risk_family_count": len(planning_contract.activated_risk_families) if planning_contract else 0,
        "suppressed_risk_family_count": len(planning_contract.suppressed_risk_families) if planning_contract else 0,
        "planned_catalog_count": len(planning_contract.planned_catalog_ids) if planning_contract else 0,
        "priority_dimension_count": len(planning_contract.priority_dimensions) if planning_contract else 0,
        "target_zone_count": len(planning_contract.target_zones) if planning_contract else 0,
        "base_extraction_demand_count": len(planning_contract.base_extraction_demands) if planning_contract else 0,
        "required_task_extraction_demand_count": (
            len(planning_contract.required_task_extraction_demands) if planning_contract else 0
        ),
        "optional_enhancement_extraction_demand_count": (
            len(planning_contract.optional_enhancement_extraction_demands) if planning_contract else 0
        ),
        "enhancement_extraction_demand_count": (
            len(planning_contract.enhancement_extraction_demands) if planning_contract else 0
        ),
        "unknown_fallback_extraction_demand_count": (
            len(planning_contract.unknown_fallback_extraction_demands) if planning_contract else 0
        ),
        "high_value_field_count": len(planning_contract.high_value_fields) if planning_contract else 0,
        "matched_extraction_field_count": len(planning_contract.matched_extraction_fields) if planning_contract else 0,
        "base_hit_field_count": len(planning_contract.base_hit_fields) if planning_contract else 0,
        "required_hit_field_count": len(planning_contract.required_hit_fields) if planning_contract else 0,
        "optional_hit_field_count": len(planning_contract.optional_hit_fields) if planning_contract else 0,
        "unknown_fallback_hit_field_count": len(planning_contract.unknown_fallback_hit_fields) if planning_contract else 0,
        "clause_unit_targeted_count": planning_contract.clause_unit_targeted_count if planning_contract else 0,
        "text_fallback_clause_count": planning_contract.text_fallback_clause_count if planning_contract else 0,
        "total_extraction_demand_count": len(planning_contract.extraction_demands) if planning_contract else 0,
    }
    output_evaluation = build_output_evaluation_summary(report)
    llm_task_status_counts = Counter(
        item.status.value for item in report.task_records if item.task_name.startswith("llm_")
    )
    return {
        "input_chars": len(parse_result.text),
        "document_node_count": len(parse_result.document_nodes),
        "clause_unit_count": len(parse_result.clause_units),
        "extracted_clause_count": len(report.extracted_clauses),
        "review_point_count": len(report.review_points),
        "applicable_count": applicable_count,
        "quality_gate_count": len(report.quality_gates),
        "quality_gate_status_counts": _sorted_counter_dict(quality_counts),
        "formal_included_count": formal_included_count,
        "formal_mode": "actual",
        "domain_candidate_count": len(domain_profile.domain_profile_candidates) if domain_profile else 0,
        "llm_enhanced": report.llm_enhanced,
        "llm_warning_count": len(report.llm_warnings),
        "llm_task_status_counts": _sorted_counter_dict(llm_task_status_counts),
        "review_planning_contract": planning_counts,
        "parser_semantic_assist": output_evaluation.get("parser_semantic_assist", {}),
        "prompt_volume": output_evaluation["prompt_volume"],
        "task_duration": output_evaluation["task_duration"],
        "dynamic_task_counts": output_evaluation["dynamic_task_counts"],
        "semantic_review": output_evaluation["semantic_review"],
    }


def _build_formal_summary(report) -> dict[str, object]:
    adjudications = report.formal_adjudication
    counts = Counter(item.disposition.value for item in adjudications)
    included = [item for item in adjudications if item.included_in_formal]
    manual = [item for item in adjudications if item.disposition.value == "manual_confirmation"]
    return {
        "mode": "actual",
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


def _formal_item_to_dict(item) -> dict[str, object]:
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
    routing_mode_counter = Counter(item.document_profile.get("routing_mode", "unknown") for item in results)
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
    largest_prompt_counter = Counter()
    llm_task_status_counter = Counter()
    parser_semantic_assist_activated_count = 0
    parser_semantic_assist_applied_total = 0
    for item in results:
        evaluation_gate_counter.update(item.evaluation_summary.get("quality_gate_status_counts", {}))
        largest_prompt = item.evaluation_summary.get("prompt_volume", {}).get("largest_task", "")
        if largest_prompt:
            largest_prompt_counter.update([largest_prompt])
        llm_task_status_counter.update(item.evaluation_summary.get("llm_task_status_counts", {}))
        parser_semantic_assist = item.evaluation_summary.get("parser_semantic_assist", {})
        if parser_semantic_assist.get("activated"):
            parser_semantic_assist_activated_count += 1
        parser_semantic_assist_applied_total += int(parser_semantic_assist.get("applied_count", 0))
    average_input_chars = _average(item.evaluation_summary.get("input_chars", 0) for item in results)
    average_review_points = _average(item.evaluation_summary.get("review_point_count", 0) for item in results)
    average_quality_gates = _average(item.evaluation_summary.get("quality_gate_count", 0) for item in results)
    average_prompt_chars = _average(
        item.evaluation_summary.get("prompt_volume", {}).get("total_chars", 0) for item in results
    )
    average_planned_catalogs = _average(
        item.evaluation_summary.get("review_planning_contract", {}).get("planned_catalog_count", 0)
        for item in results
    )
    average_target_zones = _average(
        item.evaluation_summary.get("review_planning_contract", {}).get("target_zone_count", 0)
        for item in results
    )
    average_matched_fields = _average(
        item.evaluation_summary.get("review_planning_contract", {}).get("matched_extraction_field_count", 0)
        for item in results
    )
    average_base_hit_fields = _average(
        item.evaluation_summary.get("review_planning_contract", {}).get("base_hit_field_count", 0)
        for item in results
    )
    average_required_hit_fields = _average(
        item.evaluation_summary.get("review_planning_contract", {}).get("required_hit_field_count", 0)
        for item in results
    )
    average_optional_hit_fields = _average(
        item.evaluation_summary.get("review_planning_contract", {}).get("optional_hit_field_count", 0)
        for item in results
    )
    average_unknown_fallback_hit_fields = _average(
        item.evaluation_summary.get("review_planning_contract", {}).get("unknown_fallback_hit_field_count", 0)
        for item in results
    )
    average_clause_unit_targeted = _average(
        item.evaluation_summary.get("review_planning_contract", {}).get("clause_unit_targeted_count", 0)
        for item in results
    )
    average_text_fallback_clauses = _average(
        item.evaluation_summary.get("review_planning_contract", {}).get("text_fallback_clause_count", 0)
        for item in results
    )
    return {
        "procurement_kind_counts": _sorted_counter_dict(procurement_counter),
        "routing_mode_counts": _sorted_counter_dict(routing_mode_counter),
        "domain_profile_hit_counts": _sorted_counter_dict(domain_counter),
        "quality_gate_status_counts": _sorted_counter_dict(quality_gate_counter),
        "formal_modes": _sorted_counter_dict(formal_mode_counter),
        "formal_error_count": sum(1 for item in results if item.error),
        "result_status_counts": _sorted_counter_dict(Counter(item.status for item in results)),
        "evaluation": {
            "average_input_chars": average_input_chars,
            "average_review_point_count": average_review_points,
            "average_quality_gate_count": average_quality_gates,
            "average_total_prompt_chars": average_prompt_chars,
            "average_planned_catalog_count": average_planned_catalogs,
            "parser_semantic_assist_activated_count": parser_semantic_assist_activated_count,
            "parser_semantic_assist_applied_count": parser_semantic_assist_applied_total,
            "average_target_zone_count": average_target_zones,
            "average_matched_extraction_field_count": average_matched_fields,
            "average_base_hit_field_count": average_base_hit_fields,
            "average_required_hit_field_count": average_required_hit_fields,
            "average_optional_hit_field_count": average_optional_hit_fields,
            "average_unknown_fallback_hit_field_count": average_unknown_fallback_hit_fields,
            "average_clause_unit_targeted_count": average_clause_unit_targeted,
            "average_text_fallback_clause_count": average_text_fallback_clauses,
            "quality_gate_status_counts": _sorted_counter_dict(evaluation_gate_counter),
            "largest_prompt_name_counts": _sorted_counter_dict(largest_prompt_counter),
            "llm_task_status_counts": _sorted_counter_dict(llm_task_status_counter),
        },
    }


def _build_batch_evaluation_summary(results: list[FileRegressionSummary]) -> dict[str, object]:
    quality_counts = Counter()
    llm_task_status_counts = Counter()
    largest_prompt_name_counts = Counter()
    routing_mode_counts = Counter()
    input_chars = []
    review_points = []
    quality_gate_counts = []
    formal_included = []
    prompt_chars = []
    planned_catalog_counts = []
    base_demand_counts = []
    required_demand_counts = []
    optional_demand_counts = []
    fallback_demand_counts = []
    target_zone_counts = []
    matched_field_counts = []
    base_hit_field_counts = []
    required_hit_field_counts = []
    optional_hit_field_counts = []
    unknown_fallback_hit_field_counts = []
    clause_unit_targeted_counts = []
    text_fallback_clause_counts = []
    dynamic_task_totals = []
    llm_total_seconds = []
    llm_average_seconds = []
    llm_warning_counts = []
    llm_enhanced_count = 0
    parser_semantic_assist_activated_count = 0
    parser_semantic_assist_applied_count = 0
    for item in results:
        evaluation = item.evaluation_summary
        quality_counts.update(evaluation.get("quality_gate_status_counts", {}))
        llm_task_status_counts.update(evaluation.get("llm_task_status_counts", {}))
        largest_prompt = evaluation.get("prompt_volume", {}).get("largest_task", "")
        if largest_prompt:
            largest_prompt_name_counts.update([largest_prompt])
        input_chars.append(evaluation.get("input_chars", 0))
        review_points.append(evaluation.get("review_point_count", 0))
        quality_gate_counts.append(evaluation.get("quality_gate_count", 0))
        formal_included.append(evaluation.get("formal_included_count", 0))
        prompt_chars.append(evaluation.get("prompt_volume", {}).get("total_chars", 0))
        planning = evaluation.get("review_planning_contract", {})
        routing_mode = planning.get("routing_mode", "")
        if routing_mode:
            routing_mode_counts.update([routing_mode])
        planned_catalog_counts.append(planning.get("planned_catalog_count", 0))
        base_demand_counts.append(planning.get("base_extraction_demand_count", 0))
        required_demand_counts.append(planning.get("required_task_extraction_demand_count", 0))
        optional_demand_counts.append(planning.get("optional_enhancement_extraction_demand_count", 0))
        fallback_demand_counts.append(planning.get("unknown_fallback_extraction_demand_count", 0))
        target_zone_counts.append(planning.get("target_zone_count", 0))
        matched_field_counts.append(planning.get("matched_extraction_field_count", 0))
        base_hit_field_counts.append(planning.get("base_hit_field_count", 0))
        required_hit_field_counts.append(planning.get("required_hit_field_count", 0))
        optional_hit_field_counts.append(planning.get("optional_hit_field_count", 0))
        unknown_fallback_hit_field_counts.append(planning.get("unknown_fallback_hit_field_count", 0))
        clause_unit_targeted_counts.append(planning.get("clause_unit_targeted_count", 0))
        text_fallback_clause_counts.append(planning.get("text_fallback_clause_count", 0))
        dynamic_task_totals.append(
            evaluation.get("dynamic_task_counts", {}).get("total_dynamic_review_task_count", 0)
        )
        llm_total_seconds.append(evaluation.get("task_duration", {}).get("total_seconds", 0))
        llm_average_seconds.append(evaluation.get("task_duration", {}).get("average_seconds", 0))
        llm_warning_counts.append(evaluation.get("llm_warning_count", 0))
        parser_semantic_assist = evaluation.get("parser_semantic_assist", {})
        if parser_semantic_assist.get("activated"):
            parser_semantic_assist_activated_count += 1
        parser_semantic_assist_applied_count += int(parser_semantic_assist.get("applied_count", 0))
        if evaluation.get("llm_enhanced"):
            llm_enhanced_count += 1

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
        "average_total_prompt_chars": _average(prompt_chars),
        "average_planned_catalog_count": _average(planned_catalog_counts),
        "average_base_extraction_demand_count": _average(base_demand_counts),
        "average_required_task_extraction_demand_count": _average(required_demand_counts),
        "average_optional_enhancement_extraction_demand_count": _average(optional_demand_counts),
        "average_unknown_fallback_extraction_demand_count": _average(fallback_demand_counts),
        "average_target_zone_count": _average(target_zone_counts),
        "average_matched_extraction_field_count": _average(matched_field_counts),
        "average_base_hit_field_count": _average(base_hit_field_counts),
        "average_required_hit_field_count": _average(required_hit_field_counts),
        "average_optional_hit_field_count": _average(optional_hit_field_counts),
        "average_unknown_fallback_hit_field_count": _average(unknown_fallback_hit_field_counts),
        "average_clause_unit_targeted_count": _average(clause_unit_targeted_counts),
        "average_text_fallback_clause_count": _average(text_fallback_clause_counts),
        "average_dynamic_review_task_count": _average(dynamic_task_totals),
        "average_llm_total_seconds": _average(llm_total_seconds),
        "average_llm_task_seconds": _average(llm_average_seconds),
        "average_llm_warning_count": _average(llm_warning_counts),
        "llm_enhanced_count": llm_enhanced_count,
        "routing_mode_counts": _sorted_counter_dict(routing_mode_counts),
        "parser_semantic_assist_activated_count": parser_semantic_assist_activated_count,
        "parser_semantic_assist_applied_count": parser_semantic_assist_applied_count,
        "quality_gate_status_counts": _sorted_counter_dict(quality_counts),
        "llm_task_status_counts": _sorted_counter_dict(llm_task_status_counts),
        "largest_prompt_name_counts": _sorted_counter_dict(largest_prompt_name_counts),
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
            f"- routing_mode_counts：{summary.evaluation_summary.get('routing_mode_counts', {})}",
            f"- parser_semantic_assist：activated={summary.evaluation_summary.get('parser_semantic_assist_activated_count', 0)}, applied={summary.evaluation_summary.get('parser_semantic_assist_applied_count', 0)}",
            f"- planning_hits：target_zones={summary.evaluation_summary.get('average_target_zone_count', 0.0)}, matched_fields={summary.evaluation_summary.get('average_matched_extraction_field_count', 0.0)}, base_hits={summary.evaluation_summary.get('average_base_hit_field_count', 0.0)}, required_hits={summary.evaluation_summary.get('average_required_hit_field_count', 0.0)}, optional_hits={summary.evaluation_summary.get('average_optional_hit_field_count', 0.0)}, unknown_fallback_hits={summary.evaluation_summary.get('average_unknown_fallback_hit_field_count', 0.0)}",
            f"- clause_targeting：clause_unit_targeted={summary.evaluation_summary.get('average_clause_unit_targeted_count', 0.0)}, text_fallback_clause={summary.evaluation_summary.get('average_text_fallback_clause_count', 0.0)}",
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
    parser.add_argument("--llm-timeout", type=float, default=1800.0, help="LLM 单次调用超时时间（秒），默认 1800。")
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
        llm_timeout=args.llm_timeout,
        max_candidates=args.max_candidates,
        write_outputs=not args.no_write_outputs,
        emit_manifest=args.emit_manifest,
        manifest_label=args.manifest_label,
    )
    summary = run_unknown_sample_regression(options)
    print(_render_markdown(summary))
    return 0 if summary.failed_count == 0 else 1

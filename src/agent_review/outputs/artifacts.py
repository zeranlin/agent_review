from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from pathlib import Path
import json

from ..models import ReviewReport
from ..reporting import (
    render_formal_review_opinion,
    render_json,
    render_markdown,
    render_opinion_letter,
    render_reviewer_report,
)
from ..llm.prompts import (
    build_applicability_review_prompt,
    build_clause_supplement_prompt,
    build_consistency_review_prompt,
    build_evidence_review_prompt,
    build_review_point_second_review_prompt,
    build_role_review_prompt,
    build_scoring_review_prompt,
    build_scenario_review_prompt,
    build_specialist_review_prompt,
    build_verdict_review_prompt,
)


@dataclass(slots=True)
class ArtifactBundle:
    run_dir: str
    base_json_path: str
    base_markdown_path: str
    final_json_path: str
    final_markdown_path: str
    opinion_letter_path: str
    formal_review_opinion_path: str
    reviewer_report_path: str
    manifest_path: str
    llm_tasks_path: str
    high_risk_review_path: str
    pending_confirmation_path: str
    enhancement_trace_path: str
    evaluation_summary_path: str
    review_point_trace_path: str
    document_profile_path: str
    domain_profile_match_path: str
    specialist_table_paths: dict[str, dict[str, str]]


def write_review_artifacts(
    report: ReviewReport,
    base_report: ReviewReport,
    output_dir: str | Path | None = None,
    enhancement_trace: dict[str, object] | None = None,
) -> ArtifactBundle:
    document_stem = Path(report.file_info.document_name).stem
    target_dir = Path(output_dir or Path.cwd() / "runs" / document_stem).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    base_json_path = target_dir / "base_report.json"
    base_markdown_path = target_dir / "base_report.md"
    final_json_path = target_dir / "enhanced_report.json"
    final_markdown_path = target_dir / "enhanced_report.md"
    opinion_letter_path = target_dir / "opinion_letter.md"
    formal_review_opinion_path = target_dir / "formal_review_opinion.md"
    reviewer_report_path = target_dir / "reviewer_report.md"

    base_json_path.write_text(render_json(base_report), encoding="utf-8")
    base_markdown_path.write_text(render_markdown(base_report), encoding="utf-8")
    final_json_path.write_text(render_json(report), encoding="utf-8")
    final_markdown_path.write_text(render_markdown(report), encoding="utf-8")
    opinion_letter_path.write_text(render_opinion_letter(report), encoding="utf-8")
    formal_review_opinion_path.write_text(render_formal_review_opinion(report), encoding="utf-8")
    reviewer_report_path.write_text(render_reviewer_report(report), encoding="utf-8")
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
    high_risk_review_path = target_dir / "high_risk_review_checklist.json"
    pending_confirmation_path = target_dir / "pending_confirmation_items.json"
    high_risk_review_path.write_text(
        json.dumps(_build_work_items_payload(report.high_risk_review_items), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pending_confirmation_path.write_text(
        json.dumps(_build_work_items_payload(report.pending_confirmation_items), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    enhancement_trace_path = target_dir / "enhancement_trace.json"
    enhancement_trace_path.write_text(
        json.dumps(
            _build_enhancement_trace_payload(
                report=report,
                base_report=base_report,
                enhancement_trace=enhancement_trace,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    evaluation_summary_path = target_dir / "evaluation_summary.json"
    evaluation_summary_path.write_text(
        json.dumps(_build_evaluation_summary(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    review_point_trace_path = target_dir / "review_point_trace.json"
    review_point_trace_path.write_text(
        json.dumps(_build_review_point_trace_payload(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    document_profile_path = target_dir / "document_profile.json"
    document_profile_path.write_text(
        json.dumps(_build_document_profile_payload(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    domain_profile_match_path = target_dir / "domain_profile_match.json"
    domain_profile_match_path.write_text(
        json.dumps(_build_domain_profile_match_payload(report), ensure_ascii=False, indent=2),
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
        opinion_letter_path=opinion_letter_path,
        formal_review_opinion_path=formal_review_opinion_path,
        reviewer_report_path=reviewer_report_path,
        llm_tasks_path=llm_tasks_path,
        high_risk_review_path=high_risk_review_path,
        pending_confirmation_path=pending_confirmation_path,
        enhancement_trace_path=enhancement_trace_path,
        evaluation_summary_path=evaluation_summary_path,
        review_point_trace_path=review_point_trace_path,
        document_profile_path=document_profile_path,
        domain_profile_match_path=domain_profile_match_path,
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
        opinion_letter_path=str(opinion_letter_path),
        formal_review_opinion_path=str(formal_review_opinion_path),
        reviewer_report_path=str(reviewer_report_path),
        manifest_path=str(manifest_path),
        llm_tasks_path=str(llm_tasks_path),
        high_risk_review_path=str(high_risk_review_path),
        pending_confirmation_path=str(pending_confirmation_path),
        enhancement_trace_path=str(enhancement_trace_path),
        evaluation_summary_path=str(evaluation_summary_path),
        review_point_trace_path=str(review_point_trace_path),
        document_profile_path=str(document_profile_path),
        domain_profile_match_path=str(domain_profile_match_path),
        specialist_table_paths=specialist_table_paths,
    )


def build_output_evaluation_summary(report: ReviewReport) -> dict[str, object]:
    return _build_evaluation_summary(report)


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
        "source_documents": [item.to_dict() for item in report.source_documents],
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
    opinion_letter_path: Path,
    formal_review_opinion_path: Path,
    reviewer_report_path: Path,
    llm_tasks_path: Path,
    high_risk_review_path: Path,
    pending_confirmation_path: Path,
    enhancement_trace_path: Path,
    evaluation_summary_path: Path,
    review_point_trace_path: Path,
    document_profile_path: Path,
    domain_profile_match_path: Path,
) -> dict[str, object]:
    formal_items = [item for item in report.formal_adjudication if item.included_in_formal]
    return {
        "schema_version": "1.0",
        "run_dir": str(target_dir),
        "document_name": report.file_info.document_name,
        "review_mode": report.review_mode.value,
        "overall_conclusion": report.overall_conclusion.value,
        "llm_enhanced": report.llm_enhanced,
        "review_points_count": len(report.review_points),
        "formal_count": len(formal_items),
        "formal_adjudication": [item.to_dict() for item in formal_items],
        "llm": {
            "requested": report.review_mode.value == "enhanced",
            "enhanced": report.llm_enhanced,
            "warnings": report.llm_warnings,
            "tasks_path": str(llm_tasks_path),
            "tasks": [item.to_dict() for item in report.task_records if item.task_name.startswith("llm_")],
            "semantic_review": {
                "scenario_review_summary": report.llm_semantic_review.scenario_review_summary,
                "scoring_review_summary": report.llm_semantic_review.scoring_review_summary,
                "dynamic_review_task_count": len(report.llm_semantic_review.dynamic_review_tasks),
                "scoring_dynamic_review_task_count": len(report.llm_semantic_review.scoring_dynamic_review_tasks),
                "clause_supplement_count": len(report.llm_semantic_review.clause_supplements),
                "role_review_count": len(report.llm_semantic_review.role_review_notes),
                "evidence_review_count": len(report.llm_semantic_review.evidence_review_notes),
                "applicability_review_count": len(report.llm_semantic_review.applicability_review_notes),
                "review_point_second_review_count": len(report.llm_semantic_review.review_point_second_reviews),
                "specialist_finding_count": len(report.llm_semantic_review.specialist_findings),
                "consistency_finding_count": len(report.llm_semantic_review.consistency_findings),
                "verdict_review": report.llm_semantic_review.verdict_review,
            },
        },
        "evaluation_summary": _build_evaluation_summary(report),
        "parse_summary": {
            "parser_name": report.parse_result.parser_name,
            "source_format": report.parse_result.source_format,
            "page_count": report.parse_result.page_count,
            "table_count": len(report.parse_result.tables),
            "warnings": report.parse_result.warnings,
        },
        "document_profile": _build_document_profile_payload(report),
        "debug_summary": _build_debug_summary(report),
        "rule_selection": report.rule_selection.to_dict(),
        "review_point_summary": {
            "count": len(report.review_points),
            "catalog_count": len(report.review_point_catalog),
            "applicability_count": len(report.applicability_checks),
            "quality_gate_count": len(report.quality_gates),
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
            "opinion_letter": str(opinion_letter_path),
            "formal_review_opinion": str(formal_review_opinion_path),
            "reviewer_report": str(reviewer_report_path),
            "specialist_tables": specialist_table_paths,
            "llm_tasks": str(llm_tasks_path),
            "high_risk_review_checklist": str(high_risk_review_path),
            "pending_confirmation_items": str(pending_confirmation_path),
            "enhancement_trace": str(enhancement_trace_path),
            "evaluation_summary": str(evaluation_summary_path),
            "review_point_trace": str(review_point_trace_path),
            "document_profile": str(document_profile_path),
            "domain_profile_match": str(domain_profile_match_path),
        },
    }


def _build_llm_tasks_payload(report: ReviewReport) -> dict[str, object]:
    return {
        "document_name": report.file_info.document_name,
        "review_mode": report.review_mode.value,
        "llm_enhanced": report.llm_enhanced,
        "warnings": report.llm_warnings,
        "tasks": [item.to_dict() for item in report.task_records if item.task_name.startswith("llm_")],
        "evaluation_summary": _build_evaluation_summary(report),
    }


def _build_work_items_payload(items) -> dict[str, object]:
    return {
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


def _build_enhancement_trace_payload(
    report: ReviewReport,
    base_report: ReviewReport,
    enhancement_trace: dict[str, object] | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "document_name": report.file_info.document_name,
        "requested_mode": report.review_mode.value,
        "base_mode": base_report.review_mode.value,
        "final_mode": report.review_mode.value,
        "status": (
            "completed"
            if report.llm_enhanced
            else ("fallback" if report.llm_warnings else "not_requested")
        ),
        "fallback_applied": bool(report.llm_warnings and not report.llm_enhanced),
        "llm_enhanced": report.llm_enhanced,
        "warnings": report.llm_warnings,
        "task_records": [
            item.to_dict()
            for item in report.task_records
            if item.task_name.startswith("llm_")
        ],
        "stage_records": [
            item.to_dict()
            for item in report.stage_records
            if item.stage_name.startswith("llm_")
        ],
    }
    if enhancement_trace:
        payload.update(enhancement_trace)
    return payload


def _build_evaluation_summary(report: ReviewReport) -> dict[str, object]:
    prompt_payloads = {
        "scenario_review": build_scenario_review_prompt(report),
        "scoring_review": build_scoring_review_prompt(report),
        "clause_supplement": build_clause_supplement_prompt(report),
        "role_review": build_role_review_prompt(report),
        "evidence_review": build_evidence_review_prompt(report),
        "applicability_review": build_applicability_review_prompt(report),
        "review_point_second_review": build_review_point_second_review_prompt(report),
        "specialist_review": build_specialist_review_prompt(report),
        "consistency_review": build_consistency_review_prompt(report),
        "verdict_review": build_verdict_review_prompt(report),
    }
    prompt_volume = {
        "task_char_counts": {name: len(text) for name, text in prompt_payloads.items()},
        "total_chars": sum(len(text) for text in prompt_payloads.values()),
        "largest_task": max(prompt_payloads, key=lambda name: len(prompt_payloads[name]), default=""),
    }

    durations: dict[str, float] = {}
    for item in report.task_records:
        if not item.task_name.startswith("llm_"):
            continue
        duration = _extract_task_duration_seconds(item.detail)
        if duration is not None:
            durations[item.task_name] = duration

    duration_values = list(durations.values())
    duration_summary = {
        "tasks_with_duration": len(durations),
        "tasks_without_duration": sum(
            1 for item in report.task_records if item.task_name.startswith("llm_") and item.task_name not in durations
        ),
        "task_seconds": durations,
        "total_seconds": round(sum(duration_values), 3) if duration_values else 0.0,
        "average_seconds": round(sum(duration_values) / len(duration_values), 3) if duration_values else 0.0,
        "max_seconds": round(max(duration_values), 3) if duration_values else 0.0,
    }

    dynamic_task_counts = {
        "scenario_review_task_count": len(report.llm_semantic_review.dynamic_review_tasks),
        "scoring_review_task_count": len(report.llm_semantic_review.scoring_dynamic_review_tasks),
        "total_dynamic_review_task_count": len(report.llm_semantic_review.dynamic_review_tasks)
        + len(report.llm_semantic_review.scoring_dynamic_review_tasks),
        "review_point_second_review_count": len(report.llm_semantic_review.review_point_second_reviews),
        "specialist_finding_count": len(report.llm_semantic_review.specialist_findings),
        "consistency_finding_count": len(report.llm_semantic_review.consistency_findings),
    }

    quality_summary = _build_quality_gate_summary(report)
    return {
        "document_name": report.file_info.document_name,
        "review_mode": report.review_mode.value,
        "llm_enhanced": report.llm_enhanced,
        "prompt_volume": prompt_volume,
        "task_duration": duration_summary,
        "dynamic_task_counts": dynamic_task_counts,
        "quality_gates": quality_summary,
        "semantic_review": {
            "clause_supplement_count": len(report.llm_semantic_review.clause_supplements),
            "role_review_count": len(report.llm_semantic_review.role_review_notes),
            "evidence_review_count": len(report.llm_semantic_review.evidence_review_notes),
            "applicability_review_count": len(report.llm_semantic_review.applicability_review_notes),
            "verdict_review_present": bool(report.llm_semantic_review.verdict_review),
        },
    }


def _build_review_point_trace_payload(report: ReviewReport) -> dict[str, object]:
    applicability_map = {item.point_id: item for item in report.applicability_checks}
    quality_gate_map = {item.point_id: item for item in report.quality_gates}
    formal_map = {item.point_id: item for item in report.formal_adjudication}
    return {
        "document_name": report.file_info.document_name,
        "review_mode": report.review_mode.value,
        "llm_enhanced": report.llm_enhanced,
        "count": len(report.review_points),
        "summary": _build_debug_summary(report),
        "items": [
            _build_review_point_trace_item(
                point=point,
                applicability=applicability_map.get(point.point_id),
                quality_gate=quality_gate_map.get(point.point_id),
                formal_adjudication=formal_map.get(point.point_id),
            )
            for point in report.review_points
        ],
    }


def _build_document_profile_payload(report: ReviewReport) -> dict[str, object]:
    profile = report.parse_result.document_profile
    summary = _build_document_profile_summary(profile)
    return {
        "document_name": report.file_info.document_name,
        "review_mode": report.review_mode.value,
        "document_profile": profile.to_dict() if profile else None,
        "summary": summary,
    }


def _build_domain_profile_match_payload(report: ReviewReport) -> dict[str, object]:
    profile = report.parse_result.document_profile
    candidates = profile.domain_profile_candidates if profile else []
    summary = _build_domain_profile_match_summary(profile, candidates)
    return {
        "document_name": report.file_info.document_name,
        "review_mode": report.review_mode.value,
        "procurement_kind": profile.procurement_kind if profile else "unknown",
        "unknown_structure_flags": profile.unknown_structure_flags if profile else [],
        "risk_activation_hints": profile.risk_activation_hints if profile else [],
        "count": len(candidates),
        "items": [item.to_dict() for item in candidates],
        "summary": summary,
    }


def _build_debug_summary(report: ReviewReport) -> dict[str, object]:
    profile = report.parse_result.document_profile
    return {
        "document_profile": _build_document_profile_summary(profile),
        "domain_profile_match": _build_domain_profile_match_summary(
            profile,
            profile.domain_profile_candidates if profile else [],
        ),
        "quality_gates": _build_quality_gate_summary(report),
    }


def _build_document_profile_summary(profile) -> dict[str, object]:
    if profile is None:
        return {
            "present": False,
            "candidate_count": 0,
            "summary": "未生成文档画像。",
        }
    candidates = profile.domain_profile_candidates[:3]
    return {
        "present": True,
        "document_id": profile.document_id,
        "procurement_kind": profile.procurement_kind,
        "procurement_kind_confidence": profile.procurement_kind_confidence,
        "candidate_count": len(profile.domain_profile_candidates),
        "top_candidates": [item.to_dict() for item in candidates],
        "dominant_zones": [item.to_dict() for item in profile.dominant_zones[:3]],
        "effect_distribution": [item.to_dict() for item in profile.effect_distribution[:3]],
        "clause_semantic_distribution": [item.to_dict() for item in profile.clause_semantic_distribution[:3]],
        "structure_flags": profile.structure_flags[:5],
        "quality_flags": profile.quality_flags[:5],
        "unknown_structure_flags": profile.unknown_structure_flags[:5],
        "representative_anchors": profile.representative_anchors[:5],
        "summary": profile.summary,
    }


def _build_domain_profile_match_summary(profile, candidates) -> dict[str, object]:
    if profile is None:
        return {
            "present": False,
            "candidate_count": 0,
            "summary": "未生成域匹配结果。",
        }
    top_candidate = candidates[0].to_dict() if candidates else None
    return {
        "present": True,
        "procurement_kind": profile.procurement_kind,
        "candidate_count": len(candidates),
        "top_candidate": top_candidate,
        "top_candidates": [item.to_dict() for item in candidates[:3]],
        "risk_activation_hints": profile.risk_activation_hints[:5],
        "unknown_structure_flags": profile.unknown_structure_flags[:5],
        "summary": profile.summary,
    }


def _build_quality_gate_summary(report: ReviewReport) -> dict[str, object]:
    counts = Counter(item.status.value for item in report.quality_gates)
    return {
        "count": len(report.quality_gates),
        "status_counts": {
            "passed": counts.get("passed", 0),
            "manual_confirmation": counts.get("manual_confirmation", 0),
            "filtered": counts.get("filtered", 0),
        },
        "sample": [
            {
                "point_id": item.point_id,
                "status": item.status.value,
                "reasons": item.reasons[:3],
            }
            for item in report.quality_gates[:3]
        ],
    }


def _build_review_point_trace_item(
    *,
    point,
    applicability,
    quality_gate,
    formal_adjudication,
) -> dict[str, object]:
    direct_evidence = point.evidence_bundle.direct_evidence
    supporting_evidence = point.evidence_bundle.supporting_evidence
    return {
        "point_id": point.point_id,
        "catalog_id": point.catalog_id,
        "title": point.title,
        "dimension": point.dimension,
        "severity": point.severity.value,
        "status": point.status.value,
        "source_findings": point.source_findings,
        "source_types": _summarize_source_types(point.source_findings),
        "rationale": point.rationale,
        "evidence": {
            "level": point.evidence_bundle.evidence_level.value,
            "score": point.evidence_bundle.evidence_score,
            "direct_count": len(direct_evidence),
            "supporting_count": len(supporting_evidence),
            "conflicting_count": len(point.evidence_bundle.conflicting_evidence),
            "rebuttal_count": len(point.evidence_bundle.rebuttal_evidence),
            "missing_note_count": len(point.evidence_bundle.missing_evidence_notes),
            "primary_quotes": [item.quote for item in direct_evidence[:3]],
            "supporting_quotes": [item.quote for item in supporting_evidence[:2]],
            "missing_notes": point.evidence_bundle.missing_evidence_notes[:3],
            "clause_roles": [item.value for item in point.evidence_bundle.clause_roles],
            "sufficiency_summary": point.evidence_bundle.sufficiency_summary,
        },
        "applicability": applicability.to_dict() if applicability is not None else None,
        "quality_gate": quality_gate.to_dict() if quality_gate is not None else None,
        "formal_adjudication": formal_adjudication.to_dict() if formal_adjudication is not None else None,
    }


def _summarize_source_types(source_findings: list[str]) -> list[str]:
    ordered_types: list[str] = []
    for item in source_findings:
        source_type = item.split(":", 1)[0].strip() if item else ""
        if source_type and source_type not in ordered_types:
            ordered_types.append(source_type)
    return ordered_types


def _extract_task_duration_seconds(detail: str) -> float | None:
    match = re.search(r"耗时\s+([0-9]+(?:\.[0-9]+)?)\s+秒", detail or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None

from __future__ import annotations

from pathlib import Path

from .header_info import resolve_header_info_from_parse_result
from .models import (
    ClauseEvidenceRef,
    ParseResult,
    ParsedTenderDocument,
    ParsedTenderSection,
    ParserConfidenceSummary,
    ParserWarning,
)


def build_parsed_tender_document(
    parse_result: ParseResult,
    *,
    document_name: str | None = None,
) -> ParsedTenderDocument:
    resolved_name = document_name or Path(parse_result.source_path).name or "unknown"
    zone_index = {item.node_id: item for item in parse_result.semantic_zones}
    effect_index = {item.node_id: item for item in parse_result.effect_tag_results}
    sections = [
        ParsedTenderSection(
            section_id=f"section-{index + 1}",
            node_id=node.node_id,
            title=node.title or _short_preview(node.text),
            path=node.path,
            node_type=node.node_type.value,
            zone_type=zone_index[node.node_id].zone_type.value if node.node_id in zone_index else "",
            effect_tags=[item.value for item in effect_index[node.node_id].effect_tags] if node.node_id in effect_index else [],
            anchor=node.anchor,
            text_preview=_short_preview(node.text),
        )
        for index, node in enumerate(parse_result.document_nodes)
    ]
    anchors = [
        ClauseEvidenceRef(
            clause_unit_id=unit.unit_id,
            source_node_id=unit.source_node_id,
            path=unit.path,
            zone_type=unit.zone_type.value,
            clause_semantic_type=unit.clause_semantic_type.value,
            anchor=unit.anchor,
        )
        for unit in parse_result.clause_units
    ]
    warnings = _build_parser_warnings(parse_result)
    confidence_summary = _build_parser_confidence_summary(parse_result)
    return ParsedTenderDocument(
        document_id=resolved_name,
        source_path=parse_result.source_path,
        document_name=resolved_name,
        document_type=parse_result.source_format,
        parser_name=parse_result.parser_name,
        source_format=parse_result.source_format,
        normalized_text=parse_result.text,
        page_count=parse_result.page_count,
        header_info=resolve_header_info_from_parse_result(parse_result, document_name=resolved_name),
        document_profile=parse_result.document_profile,
        sections=sections,
        document_nodes=list(parse_result.document_nodes),
        tables=list(parse_result.tables),
        semantic_zones=list(parse_result.semantic_zones),
        effect_tags=list(parse_result.effect_tag_results),
        clause_units=list(parse_result.clause_units),
        anchors=anchors,
        parser_warnings=warnings,
        parser_confidence_summary=confidence_summary,
    )


def _build_parser_warnings(parse_result: ParseResult) -> list[ParserWarning]:
    warnings: list[ParserWarning] = []
    for index, message in enumerate(parse_result.warnings, start=1):
        warnings.append(
            ParserWarning(
                code=f"parser_warning_{index}",
                message=message,
                severity="low",
            )
        )
    trace = parse_result.parser_semantic_trace
    if trace:
        for index, message in enumerate(trace.warnings, start=1):
            warnings.append(
                ParserWarning(
                    code=f"parser_semantic_warning_{index}",
                    message=message,
                    severity="medium",
                )
            )
    return warnings


def _build_parser_confidence_summary(parse_result: ParseResult) -> ParserConfidenceSummary:
    zone_confidences = [item.confidence for item in parse_result.semantic_zones]
    effect_confidences = [item.confidence for item in parse_result.effect_tag_results]
    clause_confidences = [item.confidence for item in parse_result.clause_units]
    trace = parse_result.parser_semantic_trace
    values = [*zone_confidences, *effect_confidences, *clause_confidences]
    return ParserConfidenceSummary(
        overall_confidence=_average(values),
        zone_average_confidence=_average(zone_confidences),
        effect_average_confidence=_average(effect_confidences),
        clause_unit_average_confidence=_average(clause_confidences),
        low_confidence_zone_count=sum(1 for item in zone_confidences if item < 0.6),
        low_confidence_clause_unit_count=sum(1 for item in clause_confidences if item < 0.6),
        parser_semantic_assist_activated=bool(trace and trace.activated),
        parser_semantic_assist_applied_count=trace.applied_count if trace else 0,
    )


def _average(values: list[float]) -> float:
    valid = [item for item in values if item > 0]
    if not valid:
        return 0.0
    return round(sum(valid) / len(valid), 4)


def _short_preview(text: str, limit: int = 80) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 3] + "..."

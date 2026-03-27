from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import sys

from .models import ParsedTenderDocument


def _ensure_agent_compliance_importable() -> None:
    repo_parent = Path(__file__).resolve().parents[3]
    compliance_src = repo_parent / "agent_compliance" / "src"
    compliance_src_str = str(compliance_src)
    if compliance_src.exists() and compliance_src_str not in sys.path:
        sys.path.insert(0, compliance_src_str)


_ensure_agent_compliance_importable()

from agent_compliance.agents.compliance_review.pipeline import ComplianceReviewRunResult  # type: ignore  # noqa: E402
from agent_compliance.agents.compliance_review.pipelines.llm_enhance import enhance_review_result  # type: ignore  # noqa: E402
from agent_compliance.agents.compliance_review.pipelines.llm_review import apply_llm_review_tasks  # type: ignore  # noqa: E402
from agent_compliance.agents.compliance_review.pipelines.render import write_review_outputs  # type: ignore  # noqa: E402
from agent_compliance.agents.compliance_review.pipelines.review import build_review_result  # type: ignore  # noqa: E402
from agent_compliance.agents.compliance_review.pipelines.rule_scan import run_rule_scan  # type: ignore  # noqa: E402
from agent_compliance.core.config import LLMConfig, detect_llm_config, detect_tender_parser_mode  # type: ignore  # noqa: E402
from agent_compliance.core.parsers.pagination import build_page_map  # type: ignore  # noqa: E402
from agent_compliance.core.schemas import Clause, NormalizedDocument  # type: ignore  # noqa: E402


@dataclass(frozen=True)
class AgentComplianceBridgeArtifacts:
    parsed_tender_document_id: str
    clause_source: str
    clause_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "parsed_tender_document_id": self.parsed_tender_document_id,
            "clause_source": self.clause_source,
            "clause_count": self.clause_count,
        }


def build_agent_compliance_normalized_document(
    parsed_tender_document: ParsedTenderDocument,
) -> tuple[NormalizedDocument, AgentComplianceBridgeArtifacts]:
    text = parsed_tender_document.normalized_text or ""
    file_hash = sha256(text.encode("utf-8")).hexdigest()
    page_map = build_page_map(text)
    clauses, clause_source = _build_clauses(parsed_tender_document, page_map=page_map)
    normalized = NormalizedDocument(
        source_path=parsed_tender_document.source_path,
        document_name=parsed_tender_document.document_name,
        file_hash=file_hash,
        normalized_text_path=parsed_tender_document.source_path,
        clause_count=len(clauses),
        clauses=clauses,
        page_map=page_map,
    )
    return normalized, AgentComplianceBridgeArtifacts(
        parsed_tender_document_id=parsed_tender_document.document_id,
        clause_source=clause_source,
        clause_count=len(clauses),
    )


def run_agent_compliance_review_from_parsed_tender_document(
    parsed_tender_document: ParsedTenderDocument,
    *,
    llm_config: LLMConfig | None = None,
    parser_mode: str | None = None,
    output_stem: str | None = None,
    write_outputs: bool = False,
) -> ComplianceReviewRunResult:
    normalized, bridge_artifacts = build_agent_compliance_normalized_document(parsed_tender_document)
    resolved_llm_config = llm_config or detect_llm_config()
    resolved_parser_mode = parser_mode or detect_tender_parser_mode(default="assist")
    hits = run_rule_scan(normalized)
    review = build_review_result(normalized, hits, parser_mode=resolved_parser_mode)
    review = enhance_review_result(review, resolved_llm_config)
    artifact_stem = output_stem or normalized.file_hash[:12]
    review, llm_artifacts = apply_llm_review_tasks(
        normalized,
        review,
        resolved_llm_config,
        output_stem=artifact_stem,
    )
    llm_artifacts.llm_node_summary = {
        **(llm_artifacts.llm_node_summary or {}),
        "bridge": bridge_artifacts.to_dict(),
    }
    json_path = None
    markdown_path = None
    if write_outputs:
        json_path, markdown_path = write_review_outputs(review, artifact_stem)
    return ComplianceReviewRunResult(
        normalized=normalized,
        review=review,
        llm_artifacts=llm_artifacts,
        cache_enabled=False,
        cache_used=False,
        cache_key=f"parsed-bridge:{normalized.file_hash}:{resolved_parser_mode}",
        parser_mode=resolved_parser_mode,
        llm_config=resolved_llm_config,
        json_path=json_path,
        markdown_path=markdown_path,
    )


def _build_clauses(
    parsed_tender_document: ParsedTenderDocument,
    *,
    page_map,
) -> tuple[list[Clause], str]:
    if parsed_tender_document.clause_units:
        clauses = [_clause_from_unit(unit) for unit in parsed_tender_document.clause_units]
        return clauses, "clause_units"
    clauses = []
    for index, node in enumerate(parsed_tender_document.document_nodes, start=1):
        text = node.text.strip()
        if not text:
            continue
        line_no = _line_no_from_hint(node.anchor.line_hint) or node.anchor.paragraph_no or index
        clauses.append(
            Clause(
                clause_id=f"node-{index:04d}",
                text=text,
                line_start=line_no,
                line_end=line_no,
                source_section=node.title or node.path or "",
                section_path=node.path or node.title or "",
                table_or_item_label=None,
                page_hint=_page_hint_for_line(line_no, page_map),
                document_structure_type=_map_zone_to_structure_type(""),
            )
        )
    return clauses, "document_nodes"


def _clause_from_unit(unit) -> Clause:
    line_no = _line_no_from_hint(unit.anchor.line_hint) or unit.anchor.paragraph_no or unit.anchor.block_no or 1
    return Clause(
        clause_id=unit.unit_id,
        text=unit.text,
        line_start=line_no,
        line_end=line_no,
        source_section=_source_section_from_path(unit.path),
        section_path=unit.path or None,
        table_or_item_label=_table_label(unit),
        page_hint=_page_hint_from_anchor(unit.anchor),
        document_structure_type=_map_zone_to_structure_type(unit.zone_type.value),
        risk_scope=_map_zone_to_risk_scope(unit.zone_type.value),
        scope_reason=f"bridge_from_parsed_tender_document:{unit.zone_type.value}",
        scope_type=_map_scope_type(unit),
        clause_function=_map_clause_function(unit),
        effect_strength=_map_effect_strength(unit),
        is_effective_requirement=_is_effective_requirement(unit),
        is_high_weight_requirement=_is_high_weight_requirement(unit),
        scope_confidence=_scope_confidence(unit.confidence),
    )


def _source_section_from_path(path: str) -> str | None:
    if not path:
        return None
    return path.split(" > ")[0].strip() or None


def _table_label(unit) -> str | None:
    title_hint = str(unit.table_context.get("title_hint", "")).strip()
    if title_hint:
        return title_hint
    row_label = str(unit.table_context.get("row_label", "")).strip()
    return row_label or None


def _page_hint_from_anchor(anchor) -> str | None:
    if anchor.page_no is not None:
        return f"第{anchor.page_no}页"
    return None


def _page_hint_for_line(line_no: int, page_map) -> str | None:
    for item in page_map:
        if item.line_start <= line_no <= item.line_end:
            return f"第{item.page_number}页"
    return None


def _line_no_from_hint(line_hint: str | None) -> int | None:
    if not line_hint:
        return None
    prefix = "line:"
    if line_hint.startswith(prefix):
        try:
            return int(line_hint[len(prefix) :])
        except ValueError:
            return None
    return None


def _map_zone_to_structure_type(zone_type: str) -> str:
    mapping = {
        "administrative_info": "notice_info",
        "qualification": "qualification_review",
        "conformity_review": "conformity_review",
        "technical": "technical_requirements",
        "business": "commercial_requirements",
        "scoring": "scoring_rules",
        "contract": "contract_terms",
        "policy_explanation": "bidder_instructions",
        "template": "attachments_templates",
        "appendix_reference": "attachments_templates",
        "catalog_or_navigation": "bidder_instructions",
        "public_copy_or_noise": "attachments_templates",
        "mixed_or_uncertain": "technical_requirements",
    }
    return mapping.get(zone_type, "technical_requirements")


def _map_zone_to_risk_scope(zone_type: str) -> str:
    if zone_type in {"qualification", "technical", "business", "scoring", "contract"}:
        return "core_risk_scope"
    if zone_type in {"conformity_review", "administrative_info", "policy_explanation"}:
        return "supporting_risk_scope"
    return "out_of_scope"


def _map_scope_type(unit) -> str:
    legal_effect = unit.legal_effect_type.value
    if legal_effect == "qualification_gate":
        return "requirement_body"
    if legal_effect == "scoring_factor":
        return "scoring_rule"
    if legal_effect == "technical_requirement":
        return "technical_requirement"
    if legal_effect == "business_requirement":
        return "commercial_requirement"
    if legal_effect == "contract_obligation":
        return "commercial_requirement"
    if legal_effect == "evidence_source_requirement":
        return "acceptance_requirement"
    if legal_effect in {"template_instruction", "reference_notice"}:
        return "template_text"
    return "requirement_body"


def _map_clause_function(unit) -> str:
    legal_effect = unit.legal_effect_type.value
    mapping = {
        "qualification_gate": "qualification_gate",
        "scoring_factor": "scoring_factor",
        "technical_requirement": "technical_parameter",
        "business_requirement": "commercial_term",
        "contract_obligation": "commercial_term",
        "evidence_source_requirement": "proof_requirement",
        "policy_statement": "reference_note",
        "template_instruction": "template_residue_candidate",
        "reference_notice": "reference_note",
    }
    return mapping.get(legal_effect, "reference_note")


def _map_effect_strength(unit) -> str:
    if any(tag.value in {"template", "reference_only", "public_copy_noise"} for tag in unit.effect_tags):
        return "reference_only"
    if unit.legal_effect_type.value in {
        "qualification_gate",
        "scoring_factor",
        "technical_requirement",
        "business_requirement",
        "contract_obligation",
        "evidence_source_requirement",
    }:
        return "strong_binding"
    return "weak_binding"


def _is_effective_requirement(unit) -> bool:
    return _map_effect_strength(unit) == "strong_binding"


def _is_high_weight_requirement(unit) -> bool:
    return unit.zone_type.value in {"qualification", "technical", "business", "scoring", "contract"}


def _scope_confidence(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.55:
        return "medium"
    return "low"

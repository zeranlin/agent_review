from __future__ import annotations

from dataclasses import dataclass, field

from .authority_bindings import list_authority_bindings, list_bindings_for_point
from .external_data import (
    load_external_authorities_index,
    load_external_clause_index,
    load_review_point_authority_map,
)


@dataclass(frozen=True)
class EmbeddedAuthorityRecord:
    reference_id: str
    clause_id: str
    source_name: str
    article_hint: str
    summary: str
    basis_type: str = "规范性依据"
    legal_proposition: str = ""


@dataclass(frozen=True)
class EmbeddedIssueAuthorityBinding:
    issue_type: str
    point_ids: tuple[str, ...] = ()
    clause_ids: tuple[str, ...] = ()
    legal_proposition: str = ""


@dataclass
class EmbeddedAuthorityResolution:
    issue_type: str
    point_ids: list[str] = field(default_factory=list)
    authority_records: list[EmbeddedAuthorityRecord] = field(default_factory=list)
    human_review_reasons: list[str] = field(default_factory=list)
    legal_proposition: str | None = None

    @property
    def authority_reference_ids(self) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()
        for item in self.authority_records:
            if not item.reference_id or item.reference_id in seen:
                continue
            seen.add(item.reference_id)
            results.append(item.reference_id)
        return results

    @property
    def authority_clause_ids(self) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()
        for item in self.authority_records:
            if not item.clause_id or item.clause_id in seen:
                continue
            seen.add(item.clause_id)
            results.append(item.clause_id)
        return results

    @property
    def authority_summary(self) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()
        for item in self.authority_records:
            summary = item.summary.strip()
            if not summary or summary in seen:
                continue
            seen.add(summary)
            results.append(summary)
        return results


EMBEDDED_ISSUE_AUTHORITY_BINDINGS: dict[str, EmbeddedIssueAuthorityBinding] = {
    "geographic_restriction": EmbeddedIssueAuthorityBinding(
        issue_type="geographic_restriction",
        point_ids=("RP-QUAL-004",),
    ),
    "excessive_supplier_qualification": EmbeddedIssueAuthorityBinding(
        issue_type="excessive_supplier_qualification",
        point_ids=("RP-QUAL-003",),
    ),
    "irrelevant_certification_or_award": EmbeddedIssueAuthorityBinding(
        issue_type="irrelevant_certification_or_award",
        point_ids=("RP-QUAL-003", "RP-SCORE-005"),
        legal_proposition="企业荣誉、信用等级和政策认定结果应避免替代与采购标的直接相关的履约能力要求或评分因素。",
    ),
    "qualification_domain_mismatch": EmbeddedIssueAuthorityBinding(
        issue_type="qualification_domain_mismatch",
        point_ids=("RP-QUAL-003", "RP-SCORE-005"),
        legal_proposition="资格和评分要求应与采购标的及履约能力直接相关，避免模板残留或跨行业错配。",
    ),
    "qualification_scoring_overlap": EmbeddedIssueAuthorityBinding(
        issue_type="qualification_scoring_overlap",
        point_ids=("RP-QUAL-004", "RP-SCORE-005"),
        legal_proposition="同一事项不宜既作为资格门槛又作为评分因素重复放大。",
    ),
    "scoring_content_mismatch": EmbeddedIssueAuthorityBinding(
        issue_type="scoring_content_mismatch",
        point_ids=("RP-SCORE-005",),
    ),
    "narrow_technical_parameter": EmbeddedIssueAuthorityBinding(
        issue_type="narrow_technical_parameter",
        clause_ids=("LEGAL-001-ART-007", "LEGAL-001-ART-009", "LEGAL-001-ART-031"),
        legal_proposition="技术参数和区间设置应符合项目实际需要，客观、量化且避免不合理指向特定产品或技术路线。",
    ),
    "technical_justification_needed": EmbeddedIssueAuthorityBinding(
        issue_type="technical_justification_needed",
        point_ids=("RP-REST-004",),
        clause_ids=("LEGAL-001-ART-007", "LEGAL-001-ART-009"),
        legal_proposition="刚性技术标准、专利或证明来源限制应以项目必要性、可替代性和市场调查为基础。",
    ),
    "evidence_source_restriction": EmbeddedIssueAuthorityBinding(
        issue_type="evidence_source_restriction",
        point_ids=("RP-EVID-001",),
    ),
    "payment_acceptance_linkage": EmbeddedIssueAuthorityBinding(
        issue_type="payment_acceptance_linkage",
        point_ids=("RP-CONTRACT-011",),
    ),
    "one_sided_commercial_term": EmbeddedIssueAuthorityBinding(
        issue_type="one_sided_commercial_term",
        point_ids=("RP-CONTRACT-005", "RP-CONTRACT-012", "RP-CONTRACT-013"),
        legal_proposition="合同责任、保证金、检测费用和解释权安排应公平、适度，并与责任来源和风险分配相匹配。",
    ),
    "bid_price_floor": EmbeddedIssueAuthorityBinding(
        issue_type="bid_price_floor",
        point_ids=("RP-COMP-001",),
    ),
    "delivery_period_restriction": EmbeddedIssueAuthorityBinding(
        issue_type="delivery_period_restriction",
        clause_ids=("LEGAL-001-ART-006", "LEGAL-001-ART-023"),
        legal_proposition="交付期限和履行方式应与采购标的复杂度、供应周期和合同履行安排相匹配。",
    ),
}


def resolve_embedded_issue_authority(issue_type: str) -> EmbeddedAuthorityResolution:
    normalized_issue_type = issue_type.strip()
    binding = EMBEDDED_ISSUE_AUTHORITY_BINDINGS.get(
        normalized_issue_type,
        EmbeddedIssueAuthorityBinding(issue_type=normalized_issue_type),
    )
    point_ids = _collect_point_ids(normalized_issue_type, binding)
    records: list[EmbeddedAuthorityRecord] = []
    reasons: list[str] = []
    proposition = binding.legal_proposition.strip() or None

    for point_id in point_ids:
        records.extend(_records_from_authority_bindings(point_id))
        entry = load_review_point_authority_map().get(point_id)
        if entry:
            records.extend(_records_from_external_point_entry(entry, fallback_proposition=proposition or ""))
            reasons.extend(
                str(item).strip()
                for item in entry.get("requires_human_review_when", [])
                if str(item).strip()
            )

    for clause_id in binding.clause_ids:
        record = _record_from_clause_id(str(clause_id).strip(), legal_proposition=proposition or "")
        if record is not None:
            records.append(record)

    deduped_records = _dedupe_records(records)
    if proposition is None:
        for record in deduped_records:
            if record.legal_proposition.strip():
                proposition = record.legal_proposition.strip()
                break

    return EmbeddedAuthorityResolution(
        issue_type=normalized_issue_type,
        point_ids=point_ids,
        authority_records=deduped_records,
        human_review_reasons=_dedupe_strings(reasons),
        legal_proposition=proposition,
    )


def _collect_point_ids(issue_type: str, binding: EmbeddedIssueAuthorityBinding) -> list[str]:
    point_ids: list[str] = []
    for point_id in binding.point_ids:
        normalized = str(point_id).strip()
        if normalized and normalized not in point_ids:
            point_ids.append(normalized)
    for point_id, entry in load_review_point_authority_map().items():
        if str(entry.get("source_issue_type", "")).strip() != issue_type:
            continue
        if point_id not in point_ids:
            point_ids.append(point_id)
    return point_ids


def _records_from_authority_bindings(point_id: str) -> list[EmbeddedAuthorityRecord]:
    clause_index = load_external_clause_index()
    authority_index = load_external_authorities_index()
    results: list[EmbeddedAuthorityRecord] = []
    for item in list_bindings_for_point(point_id):
        clause = clause_index.get(item.clause_id, {})
        authority = authority_index.get(item.authority_id, {})
        summary = str(clause.get("clause_text", "")).strip() or item.legal_proposition.strip()
        results.append(
            EmbeddedAuthorityRecord(
                reference_id=item.authority_id,
                clause_id=item.clause_id,
                source_name=str(authority.get("reference_title", "")).strip() or item.doc_title,
                article_hint=str(clause.get("article_label", "")).strip() or item.article_label,
                summary=summary,
                basis_type=str(clause.get("authority_level", "")).strip() or item.norm_level or "规范性依据",
                legal_proposition=item.legal_proposition,
            )
        )
    return results


def _records_from_external_point_entry(
    entry: dict[str, object],
    *,
    fallback_proposition: str,
) -> list[EmbeddedAuthorityRecord]:
    results: list[EmbeddedAuthorityRecord] = []
    for clause_id in [*entry.get("primary_clause_ids", []), *entry.get("secondary_clause_ids", [])]:
        record = _record_from_clause_id(
            str(clause_id).strip(),
            legal_proposition=fallback_proposition or str(entry.get("review_point_title", "")).strip(),
        )
        if record is not None:
            results.append(record)
    return results


def _record_from_clause_id(clause_id: str, *, legal_proposition: str) -> EmbeddedAuthorityRecord | None:
    clause = load_external_clause_index().get(clause_id)
    if clause is None:
        return None
    reference_id = str(clause.get("reference_id", "")).strip()
    authority = load_external_authorities_index().get(reference_id, {})
    return EmbeddedAuthorityRecord(
        reference_id=reference_id,
        clause_id=clause_id,
        source_name=str(authority.get("reference_title", "")).strip() or str(clause.get("doc_title", "")).strip() or "法规依据",
        article_hint=str(clause.get("article_label") or clause.get("chapter_label") or "").strip(),
        summary=str(clause.get("clause_text", "")).strip(),
        basis_type=str(clause.get("authority_level", "")).strip() or "规范性依据",
        legal_proposition=legal_proposition,
    )


def _dedupe_records(records: list[EmbeddedAuthorityRecord]) -> list[EmbeddedAuthorityRecord]:
    results: list[EmbeddedAuthorityRecord] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in records:
        key = (item.reference_id, item.clause_id, item.source_name, item.article_hint)
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def _dedupe_strings(values: list[str]) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for item in values:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        results.append(normalized)
    return results


def list_embedded_issue_authority_bindings() -> list[EmbeddedIssueAuthorityBinding]:
    return list(EMBEDDED_ISSUE_AUTHORITY_BINDINGS.values())


def list_embedded_point_authority_gaps() -> list[str]:
    bound_points = {item.point_id for item in list_authority_bindings()}
    external_points = set(load_review_point_authority_map().keys())
    return sorted(external_points - bound_points)

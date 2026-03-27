from agent_review.embedded_compliance_authorities import (
    list_embedded_point_authority_gaps,
    resolve_embedded_issue_authority,
)


def test_resolve_embedded_issue_authority_uses_structured_bindings_and_external_index() -> None:
    resolution = resolve_embedded_issue_authority("evidence_source_restriction")

    assert resolution.issue_type == "evidence_source_restriction"
    assert "RP-EVID-001" in resolution.point_ids
    assert resolution.authority_reference_ids
    assert "LEGAL-001-ART-018" in resolution.authority_clause_ids
    assert resolution.authority_records
    assert any(record.legal_proposition for record in resolution.authority_records)


def test_resolve_embedded_issue_authority_can_fallback_to_clause_only_mapping() -> None:
    resolution = resolve_embedded_issue_authority("delivery_period_restriction")

    assert resolution.issue_type == "delivery_period_restriction"
    assert resolution.authority_clause_ids
    assert "LEGAL-001-ART-023" in resolution.authority_clause_ids
    assert resolution.legal_proposition
    assert resolution.authority_summary


def test_list_embedded_point_authority_gaps_highlights_external_only_points() -> None:
    gaps = list_embedded_point_authority_gaps()

    assert "RP-REST-004" in gaps

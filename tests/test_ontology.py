from agent_review.ontology import (
    ClauseSemanticType,
    ConstraintType,
    EffectTag,
    LegalEffectType,
    LegalPrincipleTag,
    NodeType,
    RestrictionAxis,
    SemanticZoneType,
    ZONE_ONTOLOGY_VERSION,
    build_zone_ontology_payload,
)


def test_ontology_enums_are_importable_and_stable() -> None:
    assert SemanticZoneType.qualification.value == "qualification"
    assert ClauseSemanticType.scoring_rule.value == "scoring_rule"
    assert EffectTag.template.value == "template"
    assert NodeType.table_row.value == "table_row"
    assert LegalEffectType.qualification_gate.value == "qualification_gate"
    assert LegalPrincipleTag.qualification_necessity.value == "qualification_necessity"
    assert ConstraintType.performance_experience.value == "performance_experience"
    assert RestrictionAxis.geographic_region.value == "geographic_region"


def test_ontology_enum_values_are_unique() -> None:
    for enum_cls in [
        SemanticZoneType,
        ClauseSemanticType,
        EffectTag,
        NodeType,
        LegalEffectType,
        LegalPrincipleTag,
        ConstraintType,
        RestrictionAxis,
    ]:
        values = [item.value for item in enum_cls]
        assert len(values) == len(set(values))


def test_zone_ontology_payload_covers_core_review_types() -> None:
    payload = build_zone_ontology_payload()

    assert payload["version"] == ZONE_ONTOLOGY_VERSION
    zone_map = {item["zone_type"]: item for item in payload["zones"]}
    assert zone_map["qualification"]["primary_review_type"] == "资格"
    assert zone_map["technical"]["primary_review_type"] == "技术"
    assert zone_map["business"]["primary_review_type"] == "商务"
    assert zone_map["scoring"]["primary_review_type"] == "评分"
    assert zone_map["contract"]["primary_review_type"] == "合同"
    assert zone_map["template"]["primary_review_type"] == "模板"
    assert zone_map["appendix_reference"]["primary_review_type"] == "附件"
    assert zone_map["public_copy_or_noise"]["primary_review_type"] == "无关内容"
    legal_effects = {item["effect_type"] for item in payload["legal_effects"]}
    principles = {item["principle_tag"] for item in payload["legal_principles"]}
    assert "qualification_gate" in legal_effects
    assert "evidence_source_requirement" in legal_effects
    assert "qualification_nondiscrimination" in principles
    assert "internal_consistency" in principles

from agent_review.ontology import ClauseSemanticType, EffectTag, NodeType, SemanticZoneType


def test_ontology_enums_are_importable_and_stable() -> None:
    assert SemanticZoneType.qualification.value == "qualification"
    assert ClauseSemanticType.scoring_rule.value == "scoring_rule"
    assert EffectTag.template.value == "template"
    assert NodeType.table_row.value == "table_row"


def test_ontology_enum_values_are_unique() -> None:
    for enum_cls in [SemanticZoneType, ClauseSemanticType, EffectTag, NodeType]:
        values = [item.value for item in enum_cls]
        assert len(values) == len(set(values))

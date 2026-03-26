from agent_review.authority_bindings import get_authority_binding, list_bindings_for_point
from agent_review.models import AuthorityBinding, LegalFactCandidate, ReviewPointContract, RuleDefinition
from agent_review.review_point_contract_registry import get_review_point_contract, list_review_point_contracts
from agent_review.rule_definitions import get_rule_definition, list_rules_for_point


def test_new_contract_models_are_serializable() -> None:
    fact = LegalFactCandidate(
        fact_id="LF-doc-001",
        document_id="doc-1",
        source_unit_id="u-1",
        fact_type="qualification_requirement",
        zone_type="qualification",
        clause_semantic_type="qualification_condition",
        effect_tags=["binding"],
        subject="投标人",
        predicate="须具备",
        object_text="高新技术企业证书",
        normalized_terms=["高新技术企业"],
        constraint_type="mandatory",
        constraint_value={"certificate": "高新技术企业证书"},
        confidence=0.91,
        needs_llm_disambiguation=False,
    )
    rule = RuleDefinition(
        rule_id="RULE-DEMO-001",
        version="v1",
        name="演示规则",
        point_id="RP-QUAL-003",
    )
    contract = ReviewPointContract(
        point_id="RP-QUAL-003",
        title="资格条件可能缺乏履约必要性或带有歧视性门槛",
    )
    binding = AuthorityBinding(
        binding_id="AUTH-DEMO-001",
        authority_id="LEGAL-001",
        clause_id="LEGAL-001-ART-018",
        doc_title="政府采购需求管理办法",
        article_label="第二十一条",
        norm_level="ministerial_order",
    )

    assert fact.to_dict()["constraint_value"]["certificate"] == "高新技术企业证书"
    assert rule.to_dict()["rule_id"] == "RULE-DEMO-001"
    assert contract.to_dict()["point_id"] == "RP-QUAL-003"
    assert binding.to_dict()["authority_id"] == "LEGAL-001"


def test_review_point_contract_registry_exposes_sample_contracts() -> None:
    contract = get_review_point_contract("RP-SCORE-005")

    assert contract is not None
    assert contract.legal_theme == "评分相关性"
    assert "评分项明细" in contract.required_fields
    assert any(item.point_id == "RP-CONTRACT-009" for item in list_review_point_contracts())


def test_rule_definitions_registry_supports_point_lookup() -> None:
    rule = get_rule_definition("RULE-QUAL-PERF-REGION-001")
    point_rules = list_rules_for_point("RP-QUAL-004")

    assert rule is not None
    assert "performance_requirement" in rule.applicable_fact_types
    assert any(item.rule_id == "RULE-QUAL-PERF-DUP-001" for item in point_rules)


def test_authority_bindings_registry_supports_point_lookup() -> None:
    binding = get_authority_binding("AUTH-RP-CONTRACT-009-001")
    point_bindings = list_bindings_for_point("RP-QUAL-003")

    assert binding is not None
    assert "验收标准" in binding.legal_proposition
    assert any("特殊法定必要性" in item for item in point_bindings[0].requires_human_review_when)

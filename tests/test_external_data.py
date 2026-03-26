from agent_review.external_data import (
    external_profile_planning_hints,
    load_external_authorities_index,
    load_external_catalog_knowledge_profiles,
    load_external_clause_index,
    load_review_point_authority_map,
    lookup_external_manual_review_boundary,
    lookup_external_legal_basis,
    match_external_domain_profile_candidates,
)


def test_external_legal_authority_assets_can_load() -> None:
    authorities = load_external_authorities_index()
    clauses = load_external_clause_index()
    mapping = load_review_point_authority_map()

    assert "LEGAL-001" in authorities
    assert "LEGAL-001-ART-018" in clauses
    assert "RP-SCORE-005" in mapping


def test_lookup_external_legal_basis_supports_review_point_catalog() -> None:
    bases = lookup_external_legal_basis(catalog_id="RP-SCORE-005")

    assert bases
    assert any(item.source_name == "政府采购需求管理办法" for item in bases)
    assert any("第二十一条" in item.article_hint or "第九条" in item.article_hint for item in bases)


def test_external_catalog_profiles_can_match_medical_device_text() -> None:
    profiles = load_external_catalog_knowledge_profiles()
    candidates = match_external_domain_profile_candidates(
        text="医疗器械 检测报告 手术机械臂 教学培训 外科机器人",
        procurement_kind="goods",
    )

    assert profiles
    assert candidates
    assert any(item.profile_id in {"medical_device", "medical_device_goods", "CAT-MEDICAL-DEVICE"} or "medical" in item.profile_id for item in candidates)


def test_external_manual_review_boundary_exposes_authority_and_reasons() -> None:
    boundary = lookup_external_manual_review_boundary(catalog_id="RP-CONTRACT-009")

    assert boundary["reasons"]
    assert any("法定验收标准" in item or "第三方检测" in item for item in boundary["reasons"])
    assert any("政府采购需求管理办法" in item for item in boundary["authority_refs"])


def test_external_profile_planning_hints_map_profile_to_existing_fields() -> None:
    hints = external_profile_planning_hints("medical_device_goods")

    assert "scoring" in hints["route_tags"]
    assert "contract" in hints["route_tags"]
    assert "qualification" in hints["route_tags"]
    assert "评分项明细" in hints["preferred_fields"]
    assert "是否要求检测报告" in hints["preferred_fields"]
    assert "external_profile:medical_device_goods:scoring" in hints["activation_reasons"]

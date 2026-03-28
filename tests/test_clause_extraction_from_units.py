from agent_review.extractors import extract_clauses, extract_clauses_from_units
from agent_review.extractors.clause_units import build_clause_units
from agent_review.models import DocumentNode, EffectTagResult, SemanticZone, SourceAnchor
from agent_review.ontology import EffectTag, NodeType, SemanticZoneType


def _build_nodes() -> tuple[list[DocumentNode], list[SemanticZone], list[EffectTagResult]]:
    nodes = [
        DocumentNode(
            node_id="root",
            node_type=NodeType.volume,
            title="ROOT",
            text="",
            path="ROOT",
        ),
        DocumentNode(
            node_id="n-1",
            node_type=NodeType.paragraph,
            title="关键信息",
            text="关键信息",
            path="ROOT > 关键信息",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:1"),
        ),
        DocumentNode(
            node_id="n-2",
            node_type=NodeType.paragraph,
            title="项目属性：货物",
            text="项目属性：货物",
            path="ROOT > 关键信息 > 项目属性：货物",
            parent_id="n-1",
            anchor=SourceAnchor(line_hint="line:2"),
        ),
        DocumentNode(
            node_id="n-3",
            node_type=NodeType.section,
            title="综合评分法评标信息",
            text="综合评分法评标信息",
            path="ROOT > 评分办法 > 综合评分法评标信息",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:4"),
        ),
        DocumentNode(
            node_id="n-4",
            node_type=NodeType.table_row,
            title="评分项 | 分值 | 评分标准",
            text="评分项 | 分值 | 评分标准",
            path="ROOT > 评分办法 > 综合评分法评标信息 > row:1",
            parent_id="t-1",
            anchor=SourceAnchor(table_no=1, row_no=1, line_hint="line:5"),
            metadata={"row_index": 1, "is_header": True, "table_kind": "scoring"},
        ),
        DocumentNode(
            node_id="n-5",
            node_type=NodeType.table_row,
            title="检测报告 | 5 | 提供得分",
            text="检测报告 | 5 | 提供得分",
            path="ROOT > 评分办法 > 综合评分法评标信息 > row:2",
            parent_id="t-1",
            anchor=SourceAnchor(table_no=1, row_no=2, line_hint="line:6"),
            metadata={"row_index": 2, "is_header": False, "table_kind": "scoring"},
        ),
        DocumentNode(
            node_id="n-6",
            node_type=NodeType.section,
            title="第四章 合同条款",
            text="第四章 合同条款",
            path="ROOT > 第四章 合同条款",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:8"),
        ),
        DocumentNode(
            node_id="n-7",
            node_type=NodeType.paragraph,
            title="付款方式：验收合格后10个工作日内一次性付清。",
            text="付款方式：验收合格后10个工作日内一次性付清。",
            path="ROOT > 第四章 合同条款 > 付款方式：验收合格后10个工作日内一次性付清。",
            parent_id="n-6",
            anchor=SourceAnchor(line_hint="line:9"),
        ),
    ]

    zones = [
        SemanticZone("root", SemanticZoneType.catalog_or_navigation, 1.0, ["root"]),
        SemanticZone("n-1", SemanticZoneType.administrative_info, 0.9, ["info"]),
        SemanticZone("n-2", SemanticZoneType.administrative_info, 0.92, ["project_property"]),
        SemanticZone("n-3", SemanticZoneType.scoring, 0.92, ["scoring_heading"]),
        SemanticZone("n-4", SemanticZoneType.scoring, 0.95, ["scoring_header"]),
        SemanticZone("n-5", SemanticZoneType.scoring, 0.94, ["scoring_row"]),
        SemanticZone("n-6", SemanticZoneType.contract, 0.91, ["contract_heading"]),
        SemanticZone("n-7", SemanticZoneType.contract, 0.93, ["contract_clause"]),
    ]

    effects = [
        EffectTagResult("root", [EffectTag.catalog], 1.0, ["root"]),
        EffectTagResult("n-1", [EffectTag.binding], 0.7, ["binding"]),
        EffectTagResult("n-2", [EffectTag.binding], 0.84, ["binding"]),
        EffectTagResult("n-3", [EffectTag.binding], 0.8, ["binding"]),
        EffectTagResult("n-4", [EffectTag.binding], 0.78, ["binding"]),
        EffectTagResult("n-5", [EffectTag.binding], 0.88, ["binding"]),
        EffectTagResult("n-6", [EffectTag.binding], 0.81, ["binding"]),
        EffectTagResult("n-7", [EffectTag.binding], 0.9, ["binding"]),
    ]

    return nodes, zones, effects


def test_extract_clauses_from_units_can_extract_structured_fields() -> None:
    nodes, zones, effects = _build_nodes()
    units = build_clause_units(nodes, zones, effects)
    clauses = extract_clauses_from_units(units)

    field_names = {item.field_name for item in clauses}
    contents = [item.content for item in clauses]

    assert "项目属性" in field_names
    assert "评分方法" in field_names
    assert "付款节点" in field_names
    assert "验收标准" in field_names
    assert any(field_name in field_names for field_name in {"一般资格要求", "资格条件明细"})
    assert any(field_name in field_names for field_name in {"评分项明细", "评分方法"})
    assert any(item.source_anchor == "line:2" for item in clauses)
    assert any("检测报告" in content for content in contents)
    assert all("目录" not in content for content in contents)


def test_extractors_can_follow_target_field_demands() -> None:
    nodes, zones, effects = _build_nodes()
    units = build_clause_units(nodes, zones, effects)

    unit_clauses = extract_clauses_from_units(units, field_names={"付款节点"})
    text_clauses = extract_clauses(
        "\n".join(unit.text for unit in units),
        field_names={"项目属性"},
    )

    assert {item.field_name for item in unit_clauses} == {"付款节点"}
    assert any(item.field_name == "项目属性" for item in text_clauses)


def test_extract_clauses_from_units_marks_qualification_gate_details() -> None:
    nodes = [
        DocumentNode(
            node_id="root",
            node_type=NodeType.volume,
            title="ROOT",
            text="",
            path="ROOT",
        ),
        DocumentNode(
            node_id="q-head",
            node_type=NodeType.section,
            title="申请人的资格要求",
            text="申请人的资格要求",
            path="ROOT > 第一章 招标公告 > 申请人的资格要求",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:10"),
        ),
        DocumentNode(
            node_id="q-1",
            node_type=NodeType.list_item,
            title="10.投标人须为全国科技型中小企业；",
            text="10.投标人须为全国科技型中小企业；",
            path="ROOT > 第一章 招标公告 > 10.投标人须为全国科技型中小企业；",
            parent_id="q-head",
            anchor=SourceAnchor(line_hint="line:11"),
        ),
        DocumentNode(
            node_id="q-2",
            node_type=NodeType.list_item,
            title="13.投标人须成立满5年以上，并提供营业执照复印件；",
            text="13.投标人须成立满5年以上，并提供营业执照复印件；",
            path="ROOT > 第一章 招标公告 > 13.投标人须成立满5年以上，并提供营业执照复印件；",
            parent_id="q-head",
            anchor=SourceAnchor(line_hint="line:12"),
        ),
    ]
    zones = [
        SemanticZone("root", SemanticZoneType.catalog_or_navigation, 1.0, ["root"]),
        SemanticZone("q-head", SemanticZoneType.qualification, 0.95, ["title:申请人的资格要求"]),
        SemanticZone("q-1", SemanticZoneType.qualification, 0.92, ["parent_qualification_context"]),
        SemanticZone("q-2", SemanticZoneType.qualification, 0.92, ["parent_qualification_context"]),
    ]
    effects = [
        EffectTagResult("root", [EffectTag.catalog], 1.0, ["root"]),
        EffectTagResult("q-head", [EffectTag.binding], 0.85, ["binding"]),
        EffectTagResult("q-1", [EffectTag.binding], 0.88, ["binding"]),
        EffectTagResult("q-2", [EffectTag.binding], 0.88, ["binding"]),
    ]

    units = build_clause_units(nodes, zones, effects)
    clauses = extract_clauses_from_units(units)

    gate_clauses = [item for item in clauses if item.field_name == "资格门槛明细"]

    assert len(gate_clauses) >= 2
    assert any("科技型中小企业" in item.content for item in gate_clauses)
    assert any("成立满5年以上" in item.content for item in gate_clauses)
    assert all(item.legal_effect_type.value == "qualification_gate" for item in gate_clauses)
    assert any("qualification_necessity" in [tag.value for tag in item.legal_principle_tags] for item in gate_clauses)


def test_extract_clauses_from_units_builds_constraint_axes_for_regional_performance_gate() -> None:
    nodes = [
        DocumentNode(
            node_id="root",
            node_type=NodeType.volume,
            title="ROOT",
            text="",
            path="ROOT",
        ),
        DocumentNode(
            node_id="q-head",
            node_type=NodeType.section,
            title="申请人的资格要求",
            text="申请人的资格要求",
            path="ROOT > 第一章 招标公告 > 申请人的资格要求",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:20"),
        ),
        DocumentNode(
            node_id="q-1",
            node_type=NodeType.list_item,
            title="投标人须具备广州市医疗器械行业同类项目业绩不少于2个。",
            text="投标人须具备广州市医疗器械行业同类项目业绩不少于2个。",
            path="ROOT > 第一章 招标公告 > 投标人须具备广州市医疗器械行业同类项目业绩不少于2个。",
            parent_id="q-head",
            anchor=SourceAnchor(line_hint="line:21"),
        ),
    ]
    zones = [
        SemanticZone("root", SemanticZoneType.catalog_or_navigation, 1.0, ["root"]),
        SemanticZone("q-head", SemanticZoneType.qualification, 0.95, ["title:申请人的资格要求"]),
        SemanticZone("q-1", SemanticZoneType.qualification, 0.92, ["parent_qualification_context"]),
    ]
    effects = [
        EffectTagResult("root", [EffectTag.catalog], 1.0, ["root"]),
        EffectTagResult("q-head", [EffectTag.binding], 0.85, ["binding"]),
        EffectTagResult("q-1", [EffectTag.binding], 0.88, ["binding"]),
    ]

    units = build_clause_units(nodes, zones, effects)
    clauses = extract_clauses_from_units(units)
    regional_gate = next(item for item in clauses if item.field_name == "资格门槛明细")

    assert regional_gate.legal_effect_type.value == "qualification_gate"
    assert "performance_experience" in [item.value for item in regional_gate.clause_constraint.constraint_types]
    assert "geographic_region" in [item.value for item in regional_gate.clause_constraint.restriction_axes]
    assert "industry_segment" in [item.value for item in regional_gate.clause_constraint.restriction_axes]


def test_extract_clauses_from_units_can_normalize_mixed_scoring_and_guarantee_units() -> None:
    nodes = [
        DocumentNode(node_id="root", node_type=NodeType.volume, title="ROOT", text="", path="ROOT"),
        DocumentNode(
            node_id="s-1",
            node_type=NodeType.paragraph,
            title="投标人具有有效的ITSS证书得5分。",
            text="投标人具有有效的ITSS证书得5分。",
            path="ROOT > 评分标准 > 投标人具有有效的ITSS证书得5分。",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:30"),
        ),
        DocumentNode(
            node_id="c-1",
            node_type=NodeType.paragraph,
            title="履约担保：合同总价的5%作为质量保证金，须以银行转账方式缴纳，质保期满后无息退还。",
            text="履约担保：合同总价的5%作为质量保证金，须以银行转账方式缴纳，质保期满后无息退还。",
            path="ROOT > 合同条款 > 履约担保：合同总价的5%作为质量保证金，须以银行转账方式缴纳，质保期满后无息退还。",
            parent_id="root",
            anchor=SourceAnchor(paragraph_no=31, line_hint="line:31"),
        ),
    ]
    zones = [
        SemanticZone("root", SemanticZoneType.catalog_or_navigation, 1.0, ["root"]),
        SemanticZone("s-1", SemanticZoneType.mixed_or_uncertain, 0.62, ["low_confidence_scoring"]),
        SemanticZone("c-1", SemanticZoneType.contract, 0.9, ["contract_clause"]),
    ]
    effects = [
        EffectTagResult("root", [EffectTag.catalog], 1.0, ["root"]),
        EffectTagResult("s-1", [EffectTag.binding], 0.72, ["binding"]),
        EffectTagResult("c-1", [EffectTag.binding], 0.9, ["binding"]),
    ]

    units = build_clause_units(nodes, zones, effects)
    clauses = extract_clauses_from_units(units)
    clause_map = {item.field_name: item for item in clauses if item.field_name}

    assert "行业相关性存疑评分项" in clause_map
    assert "ITSS" in clause_map["行业相关性存疑评分项"].content
    assert clause_map["行业相关性存疑评分项"].semantic_zone == SemanticZoneType.scoring
    assert "履约保证金" in clause_map
    assert "质量保证金" in clause_map["履约保证金"].content
    assert clause_map["履约保证金"].semantic_zone == SemanticZoneType.contract
    assert clause_map["履约保证金"].source_anchor == "line:31"


def test_text_extractors_capture_qualification_gate_and_scoring_mismatch_terms() -> None:
    text = """
    申请人的资格要求：
    投标人须为全国科技型中小企业；
    投标人须具备高新技术企业证书；
    投标人须提供纳税信用A级证明；
    投标人须具备广州市医疗器械行业同类项目业绩不少于2个。
    评分标准：
    投标人具备人力资源测评师；
    投标人具备非金属矿采矿许可证；
    """
    clauses = extract_clauses(text)
    clause_map = {item.field_name: item for item in clauses if item.field_name}

    assert "资格门槛明细" in clause_map
    assert "科技型中小企业" in clause_map["资格门槛明细"].content
    assert "高新技术企业" in clause_map["资格门槛明细"].content
    assert "行业相关性存疑评分项" in clause_map
    assert "人力资源测评师" in clause_map["行业相关性存疑评分项"].content
    assert "非金属矿采矿许可证" in clause_map["行业相关性存疑评分项"].content


def test_unit_normalizers_can_recover_project_type_cert_scope_and_invoice_payment_from_filtered_zones() -> None:
    nodes = [
        DocumentNode(node_id="root", node_type=NodeType.volume, title="ROOT", text="", path="ROOT"),
        DocumentNode(
            node_id="p-1",
            node_type=NodeType.table_row,
            title="项目类型： | 服务类",
            text="项目类型： | 服务类",
            path="ROOT > 评标信息 > 评分标准 > row:1",
            parent_id="root",
            anchor=SourceAnchor(table_no=1, row_no=1, line_hint="line:1"),
            metadata={"row_index": 1, "is_header": False, "table_kind": ""},
        ),
        DocumentNode(
            node_id="s-1",
            node_type=NodeType.table_row,
            title="投标人同时具有有效的质量管理体系认证证书（认证范围为：客户服务、园区保洁）的，得3分。",
            text="投标人同时具有有效的质量管理体系认证证书（认证范围为：客户服务、园区保洁）的，得3分。",
            path="ROOT > 评标信息 > 评分标准 > row:2",
            parent_id="root",
            anchor=SourceAnchor(table_no=1, row_no=2, line_hint="line:2"),
            metadata={"row_index": 2, "is_header": False, "table_kind": ""},
        ),
        DocumentNode(
            node_id="c-1",
            node_type=NodeType.paragraph,
            title="采购人应当自收到发票后20日内将资金支付到合同约定的中标供应商账户。",
            text="采购人应当自收到发票后20日内将资金支付到合同约定的中标供应商账户。",
            path="ROOT > 第三章 用户需求书 > 四、实质性条款 > 项目审核要求 > 采购人应当自收到发票后20日内将资金支付到合同约定的中标供应商账户。",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:3"),
        ),
    ]
    zones = [
        SemanticZone("root", SemanticZoneType.catalog_or_navigation, 1.0, ["root"]),
        SemanticZone("p-1", SemanticZoneType.catalog_or_navigation, 0.8, ["table_header_like"]),
        SemanticZone("s-1", SemanticZoneType.catalog_or_navigation, 0.76, ["scoring_table_header_like"]),
        SemanticZone("c-1", SemanticZoneType.conformity_review, 0.88, ["review_procedure_noise_with_contract_tail"]),
    ]
    effects = [
        EffectTagResult("root", [EffectTag.catalog], 1.0, ["root"]),
        EffectTagResult("p-1", [EffectTag.binding], 0.72, ["binding"]),
        EffectTagResult("s-1", [EffectTag.binding], 0.8, ["binding"]),
        EffectTagResult("c-1", [EffectTag.binding], 0.86, ["binding"]),
    ]

    units = build_clause_units(nodes, zones, effects)
    clauses = extract_clauses_from_units(units, field_names={"项目属性", "体系认证范围要求", "付款时限"})
    clause_map = {item.field_name: item for item in clauses if item.field_name}

    assert clause_map["项目属性"].normalized_value == "服务"
    assert clause_map["项目属性"].semantic_zone == SemanticZoneType.administrative_info
    assert clause_map["体系认证范围要求"].normalized_value == "存在"
    assert clause_map["体系认证范围要求"].semantic_zone == SemanticZoneType.scoring
    assert clause_map["付款时限"].normalized_value == "20"
    assert clause_map["付款时限"].semantic_zone == SemanticZoneType.contract

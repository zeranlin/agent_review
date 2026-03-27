from agent_review.extractors.clause_units import build_clause_units
from agent_review.models import DocumentNode, EffectTagResult, SemanticZone, SourceAnchor
from agent_review.ontology import ClauseSemanticType, EffectTag, NodeType, SemanticZoneType
from agent_review.structure.effect_tagger import tag_effects
from agent_review.structure.zone_classifier import classify_semantic_zones


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
            node_type=NodeType.section,
            title="投标人资格要求",
            text="投标人须具备相关资质。",
            path="ROOT > 第一章 招标公告 > 投标人资格要求",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:2"),
        ),
        DocumentNode(
            node_id="n-2",
            node_type=NodeType.section,
            title="综合评分法评标信息",
            text="综合评分法评标信息",
            path="ROOT > 第二章 评分办法 > 综合评分法评标信息",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:4"),
        ),
        DocumentNode(
            node_id="n-3",
            node_type=NodeType.table_row,
            title="评分项 | 分值 | 评分标准",
            text="评分项 | 分值 | 评分标准",
            path="ROOT > 第二章 评分办法 > 综合评分法评标信息 > row:1",
            parent_id="t-1",
            anchor=SourceAnchor(table_no=1, row_no=1, line_hint="line:5"),
            metadata={"row_index": 1, "is_header": True, "table_kind": "scoring"},
        ),
        DocumentNode(
            node_id="n-4",
            node_type=NodeType.table_row,
            title="检测报告 | 5 | 提供得分",
            text="检测报告 | 5 | 提供得分",
            path="ROOT > 第二章 评分办法 > 综合评分法评标信息 > row:2",
            parent_id="t-1",
            anchor=SourceAnchor(table_no=1, row_no=2, line_hint="line:6"),
            metadata={"row_index": 2, "is_header": False, "table_kind": "scoring"},
        ),
        DocumentNode(
            node_id="n-5",
            node_type=NodeType.section,
            title="第三章 投标文件格式、附件",
            text="第三章 投标文件格式、附件",
            path="ROOT > 第三章 投标文件格式、附件",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:8"),
        ),
        DocumentNode(
            node_id="n-6",
            node_type=NodeType.paragraph,
            title="中小企业声明函（格式）",
            text="中小企业声明函（格式）",
            path="ROOT > 第三章 投标文件格式、附件 > 中小企业声明函（格式）",
            parent_id="n-5",
            anchor=SourceAnchor(line_hint="line:9"),
        ),
        DocumentNode(
            node_id="n-7",
            node_type=NodeType.paragraph,
            title="详见附件2。",
            text="详见附件2。",
            path="ROOT > 第三章 投标文件格式、附件 > 详见附件2。",
            parent_id="n-5",
            anchor=SourceAnchor(line_hint="line:10"),
        ),
    ]

    zones = [
        SemanticZone("root", SemanticZoneType.catalog_or_navigation, 1.0, ["root"]),
        SemanticZone("n-1", SemanticZoneType.qualification, 0.92, ["qualification"]),
        SemanticZone("n-2", SemanticZoneType.scoring, 0.9, ["scoring_heading"]),
        SemanticZone("n-3", SemanticZoneType.scoring, 0.96, ["scoring_header"]),
        SemanticZone("n-4", SemanticZoneType.scoring, 0.94, ["scoring_row"]),
        SemanticZone("n-5", SemanticZoneType.template, 0.9, ["template_heading"]),
        SemanticZone("n-6", SemanticZoneType.template, 0.95, ["template_clause"]),
        SemanticZone("n-7", SemanticZoneType.appendix_reference, 0.86, ["appendix_reference"]),
    ]

    effects = [
        EffectTagResult("root", [EffectTag.catalog], 1.0, ["root"]),
        EffectTagResult("n-1", [EffectTag.binding], 0.82, ["binding"]),
        EffectTagResult("n-2", [EffectTag.binding], 0.8, ["binding"]),
        EffectTagResult("n-3", [EffectTag.binding], 0.78, ["binding"]),
        EffectTagResult("n-4", [EffectTag.binding], 0.9, ["binding"]),
        EffectTagResult("n-5", [EffectTag.template], 0.92, ["template"]),
        EffectTagResult("n-6", [EffectTag.template], 0.96, ["template"]),
        EffectTagResult("n-7", [EffectTag.reference_only], 0.88, ["reference_only"]),
    ]

    return nodes, zones, effects


def test_clause_unit_builder_creates_units_for_paragraphs_and_table_rows() -> None:
    nodes, zones, effects = _build_nodes()
    units = build_clause_units(nodes, zones, effects)

    qualification_unit = next(unit for unit in units if unit.source_node_id == "n-1")
    header_unit = next(unit for unit in units if unit.source_node_id == "n-3")
    scoring_unit = next(unit for unit in units if unit.source_node_id == "n-4")

    assert qualification_unit.path == "ROOT > 第一章 招标公告 > 投标人资格要求"
    assert qualification_unit.anchor.line_hint == "line:2"
    assert qualification_unit.primary_review_type == "资格"
    assert qualification_unit.clause_semantic_type == ClauseSemanticType.qualification_condition

    assert header_unit.zone_type == SemanticZoneType.catalog_or_navigation
    assert header_unit.primary_review_type == "导航"
    assert header_unit.clause_semantic_type == ClauseSemanticType.catalog_clause
    assert header_unit.table_context["row_role"] == "header"
    assert header_unit.table_context["cells"] == ["评分项", "分值", "评分标准"]
    assert header_unit.confidence <= 0.38

    assert scoring_unit.zone_type == SemanticZoneType.scoring
    assert scoring_unit.primary_review_type == "评分"
    assert scoring_unit.clause_semantic_type == ClauseSemanticType.scoring_rule
    assert scoring_unit.path == "ROOT > 第二章 评分办法 > 综合评分法评标信息 > row:2"
    assert scoring_unit.anchor.line_hint == "line:6"
    assert scoring_unit.table_context["row_role"] == "data"
    assert scoring_unit.table_context["row_label"] == "检测报告"
    assert scoring_unit.confidence <= 0.86


def test_clause_unit_builder_marks_template_units() -> None:
    nodes, zones, effects = _build_nodes()
    units = build_clause_units(nodes, zones, effects)

    template_unit = next(unit for unit in units if unit.source_node_id == "n-6")
    reference_unit = next(unit for unit in units if unit.source_node_id == "n-7")

    assert template_unit.clause_semantic_type == ClauseSemanticType.declaration_template
    assert template_unit.path.endswith("中小企业声明函（格式）")
    assert template_unit.table_context["heading_context"] == "ROOT > 第三章 投标文件格式、附件"
    assert template_unit.confidence <= 0.62

    assert reference_unit.clause_semantic_type == ClauseSemanticType.reference_clause
    assert reference_unit.path.endswith("详见附件2。")
    assert reference_unit.table_context["heading_context"] == "ROOT > 第三章 投标文件格式、附件"
    assert reference_unit.confidence <= 0.5


def test_clause_unit_marks_generic_sme_price_matrix_as_conditional_policy() -> None:
    nodes = [
        DocumentNode(node_id="root", node_type=NodeType.volume, title="ROOT", text="", path="ROOT"),
        DocumentNode(
            node_id="p-1",
            node_type=NodeType.paragraph,
            title="中小企业政策说明",
            text="（1）专门面向中小企业采购的项目，不再执行价格扣除比例。",
            path="ROOT > 政策说明 > 中小企业政策说明",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:12"),
        ),
    ]
    zones = [SemanticZone("p-1", SemanticZoneType.policy_explanation, 0.95, ["policy"])]
    effects = [EffectTagResult("p-1", [EffectTag.binding], 0.8, ["binding"])]

    units = build_clause_units(nodes, zones, effects)
    unit = units[0]

    assert unit.clause_semantic_type == ClauseSemanticType.conditional_policy
    assert unit.conditional_context["conditional_policy"] == "true"
    assert unit.conditional_context["project_binding"] == "false"
    assert unit.conditional_context["policy_branch"] == "set_aside"


def test_clause_unit_builder_resolves_parser_regression_samples() -> None:
    nodes = [
        DocumentNode(node_id="root", node_type=NodeType.volume, title="ROOT", text="", path="ROOT"),
        DocumentNode(
            node_id="q-head",
            node_type=NodeType.paragraph,
            title="资格性审查表",
            text="资格性审查表",
            path="ROOT > 招标文件信息 > 资格性审查表",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:4"),
        ),
        DocumentNode(
            node_id="warn",
            node_type=NodeType.paragraph,
            title="警示条款",
            text="警示条款",
            path="ROOT > 评标信息 > （2021） > 警示条款",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:18"),
        ),
        DocumentNode(
            node_id="score-sub",
            node_type=NodeType.subsection,
            title="（二）技术保障措施（可选）",
            text="（二）技术保障措施（可选）",
            path="ROOT > 第一册 专用条款 > 三、投标人情况及资格证明文件 > （二）技术保障措施（可选）",
            parent_id="root",
            children_ids=["score-child"],
            anchor=SourceAnchor(line_hint="line:266"),
        ),
        DocumentNode(
            node_id="score-child",
            node_type=NodeType.paragraph,
            title="特别提示",
            text="投标人须按本招标文件评标信息中“技术保障措施”这一评审因素要求，提供证明资料。",
            path="ROOT > 第一册 专用条款 > 三、投标人情况及资格证明文件 > （二）技术保障措施（可选） > 特别提示",
            parent_id="score-sub",
            anchor=SourceAnchor(line_hint="line:267"),
        ),
    ]

    zones = classify_semantic_zones(nodes)
    effects = tag_effects(nodes, zones)
    units = build_clause_units(nodes, zones, effects)
    by_id = {unit.source_node_id: unit for unit in units}

    assert by_id["q-head"].zone_type == SemanticZoneType.qualification
    assert by_id["q-head"].clause_semantic_type == ClauseSemanticType.qualification_condition

    assert by_id["warn"].zone_type == SemanticZoneType.policy_explanation
    assert by_id["warn"].clause_semantic_type == ClauseSemanticType.policy_clause
    assert EffectTag.policy_background in by_id["warn"].effect_tags

    assert by_id["score-sub"].zone_type == SemanticZoneType.scoring
    assert by_id["score-sub"].clause_semantic_type == ClauseSemanticType.scoring_factor


def test_clause_unit_builder_assigns_administrative_and_catalog_semantics() -> None:
    nodes = [
        DocumentNode(node_id="root", node_type=NodeType.volume, title="ROOT", text="", path="ROOT"),
        DocumentNode(
            node_id="info",
            node_type=NodeType.paragraph,
            title="招标文件信息",
            text="招标文件信息",
            path="ROOT > 招标文件信息",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:1"),
        ),
        DocumentNode(
            node_id="chapter",
            node_type=NodeType.chapter,
            title="第一章 招标公告",
            text="第一章 招标公告",
            path="ROOT > 第一章 招标公告",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:2"),
        ),
        DocumentNode(
            node_id="policy",
            node_type=NodeType.list_item,
            title="1、关于享受优惠政策的主体及价格扣除比例",
            text="1、关于享受优惠政策的主体及价格扣除比例",
            path="ROOT > 二、其他关键信息 > 1、关于享受优惠政策的主体及价格扣除比例",
            parent_id="root",
            anchor=SourceAnchor(line_hint="line:3"),
        ),
    ]
    zones = [
        SemanticZone("root", SemanticZoneType.catalog_or_navigation, 1.0, ["root"]),
        SemanticZone("info", SemanticZoneType.administrative_info, 0.92, ["title:招标文件信息"]),
        SemanticZone("chapter", SemanticZoneType.catalog_or_navigation, 0.9, ["structural_heading"]),
        SemanticZone("policy", SemanticZoneType.policy_explanation, 0.86, ["policy_signal"]),
    ]
    effects = [
        EffectTagResult("root", [EffectTag.catalog], 1.0, ["root"]),
        EffectTagResult("info", [EffectTag.binding], 0.75, ["binding"]),
        EffectTagResult("chapter", [EffectTag.catalog], 0.92, ["catalog"]),
        EffectTagResult("policy", [EffectTag.policy_background], 0.86, ["policy_background"]),
    ]

    units = build_clause_units(nodes, zones, effects)
    by_id = {unit.source_node_id: unit for unit in units}

    assert by_id["info"].clause_semantic_type == ClauseSemanticType.administrative_clause
    assert by_id["chapter"].clause_semantic_type == ClauseSemanticType.catalog_clause
    assert by_id["policy"].clause_semantic_type == ClauseSemanticType.policy_clause

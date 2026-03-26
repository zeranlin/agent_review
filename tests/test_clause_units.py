from agent_review.extractors.clause_units import build_clause_units
from agent_review.models import DocumentNode, EffectTagResult, SemanticZone, SourceAnchor
from agent_review.ontology import ClauseSemanticType, EffectTag, NodeType, SemanticZoneType


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
    assert qualification_unit.clause_semantic_type == ClauseSemanticType.qualification_condition

    assert header_unit.zone_type == SemanticZoneType.catalog_or_navigation
    assert header_unit.clause_semantic_type == ClauseSemanticType.catalog_clause
    assert header_unit.table_context["row_role"] == "header"
    assert header_unit.table_context["cells"] == ["评分项", "分值", "评分标准"]
    assert header_unit.confidence <= 0.38

    assert scoring_unit.zone_type == SemanticZoneType.scoring
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

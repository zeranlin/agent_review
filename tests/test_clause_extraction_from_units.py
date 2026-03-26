from agent_review.extractors import extract_clauses_from_units
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
    ]

    zones = [
        SemanticZone("root", SemanticZoneType.catalog_or_navigation, 1.0, ["root"]),
        SemanticZone("n-1", SemanticZoneType.administrative_info, 0.9, ["info"]),
        SemanticZone("n-2", SemanticZoneType.administrative_info, 0.92, ["project_property"]),
        SemanticZone("n-3", SemanticZoneType.scoring, 0.92, ["scoring_heading"]),
        SemanticZone("n-4", SemanticZoneType.scoring, 0.95, ["scoring_header"]),
        SemanticZone("n-5", SemanticZoneType.scoring, 0.94, ["scoring_row"]),
    ]

    effects = [
        EffectTagResult("root", [EffectTag.catalog], 1.0, ["root"]),
        EffectTagResult("n-1", [EffectTag.binding], 0.7, ["binding"]),
        EffectTagResult("n-2", [EffectTag.binding], 0.84, ["binding"]),
        EffectTagResult("n-3", [EffectTag.binding], 0.8, ["binding"]),
        EffectTagResult("n-4", [EffectTag.binding], 0.78, ["binding"]),
        EffectTagResult("n-5", [EffectTag.binding], 0.88, ["binding"]),
    ]

    return nodes, zones, effects


def test_extract_clauses_from_units_can_extract_structured_fields() -> None:
    nodes, zones, effects = _build_nodes()
    units = build_clause_units(nodes, zones, effects)
    clauses = extract_clauses_from_units(units)

    field_names = {item.field_name for item in clauses}
    contents = [item.content for item in clauses]

    assert "项目属性" in field_names
    assert any(item.source_anchor == "line:2" for item in clauses)
    assert all("评分项" not in content for content in contents)

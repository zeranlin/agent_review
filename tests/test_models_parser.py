from agent_review.models import (
    ClauseUnit,
    DocumentNode,
    EffectTagResult,
    HeaderInfo,
    ParseResult,
    RawBlock,
    RawCell,
    RawTable,
    ReviewPlanningContract,
    SemanticZone,
    SourceAnchor,
)
from agent_review.ontology import ClauseSemanticType, EffectTag, NodeType, SemanticZoneType, ZONE_ONTOLOGY_VERSION


def test_parser_models_to_dict_are_serializable() -> None:
    anchor = SourceAnchor(source_path="/tmp/demo.docx", block_no=1, line_hint="line:1")
    cell = RawCell(row_index=1, col_index=1, text="评分项", is_header=True, anchor=anchor)
    table = RawTable(table_id="t-1", rows=[[cell]], anchor=anchor, title_hint="评分表")
    block = RawBlock(
        block_id="p-1",
        block_type="paragraph",
        text="第一章 招标公告",
        style_name="Heading 1",
        numbering="第一章",
        anchor=anchor,
        metadata={"heading_candidate": True},
    )
    node = DocumentNode(
        node_id="n-1",
        node_type=NodeType.chapter,
        title="第一章 招标公告",
        text="第一章 招标公告",
        path="第一章 招标公告",
        anchor=anchor,
    )
    zone = SemanticZone(
        node_id="n-1",
        zone_type=SemanticZoneType.administrative_info,
        confidence=0.9,
        classification_basis=["title"],
    )
    effect = EffectTagResult(
        node_id="n-1",
        effect_tags=[EffectTag.binding],
        confidence=0.8,
        evidence=["章节标题"],
    )
    unit = ClauseUnit(
        unit_id="u-1",
        source_node_id="n-1",
        text="投标人资格要求：具备相关资质。",
        path="第一章 招标公告 > 投标人资格要求",
        anchor=anchor,
        zone_type=SemanticZoneType.qualification,
        clause_semantic_type=ClauseSemanticType.qualification_condition,
        effect_tags=[EffectTag.binding],
        confidence=0.88,
        primary_review_type="资格",
    )

    payload = {
        "anchor": anchor.to_dict(),
        "cell": cell.to_dict(),
        "table": table.to_dict(),
        "block": block.to_dict(),
        "node": node.to_dict(),
        "zone": zone.to_dict(),
        "effect": effect.to_dict(),
        "unit": unit.to_dict(),
    }

    assert payload["anchor"]["source_path"] == "/tmp/demo.docx"
    assert payload["cell"]["is_header"] is True
    assert payload["table"]["rows"][0][0]["text"] == "评分项"
    assert payload["block"]["metadata"]["heading_candidate"] is True
    assert payload["node"]["node_type"] == NodeType.chapter.value
    assert payload["zone"]["zone_type"] == SemanticZoneType.administrative_info.value
    assert payload["effect"]["effect_tags"] == [EffectTag.binding.value]
    assert payload["unit"]["clause_semantic_type"] == ClauseSemanticType.qualification_condition.value
    assert payload["unit"]["ontology_version"] == ZONE_ONTOLOGY_VERSION
    assert payload["unit"]["primary_review_type"] == "资格"


def test_parse_result_supports_optional_raw_parser_artifacts() -> None:
    anchor = SourceAnchor(source_path="/tmp/demo.docx", block_no=1)
    block = RawBlock(block_id="p-1", block_type="paragraph", text="项目概况", anchor=anchor)
    result = ParseResult(
        parser_name="docx",
        source_path="/tmp/demo.docx",
        source_format="docx",
        page_count=1,
        text="项目概况",
        raw_blocks=[block],
        raw_tables=[],
    )

    payload = result.to_dict()

    assert payload["raw_blocks"][0]["text"] == "项目概况"
    assert payload["raw_tables"] == []
    assert payload["legal_fact_candidates"] == []
    assert payload["rule_hits"] == []
    assert payload["review_point_instances"] == []


def test_header_info_and_review_planning_contract_expose_ontology_fields() -> None:
    header = HeaderInfo(
        project_name="某采购项目",
        purchaser_name="某学校",
        source_evidence={"project_name": "resolver"},
        confidence={"project_name": 1.0},
    )
    contract = ReviewPlanningContract(
        document_id="doc-1",
        procurement_kind="goods",
        target_zones=["qualification", "scoring"],
        target_primary_review_types=["资格", "评分"],
    )

    header_payload = header.to_dict()
    contract_payload = contract.to_dict()

    assert header_payload["ontology_version"] == ZONE_ONTOLOGY_VERSION
    assert header_payload["source_evidence"]["project_name"] == "resolver"
    assert contract_payload["ontology_version"] == ZONE_ONTOLOGY_VERSION
    assert contract_payload["target_primary_review_types"] == ["资格", "评分"]

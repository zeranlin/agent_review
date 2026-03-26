from pathlib import Path

from agent_review.extractors import extract_clauses_from_units
from agent_review.ontology import EffectTag, SemanticZoneType
from agent_review.parsers import load_document


def test_sprint1_parser_pipeline_keeps_government_procurement_regions_distinct(tmp_path: Path) -> None:
    file_path = tmp_path / "gov_procurement_structure.txt"
    file_path.write_text(
        "\n".join(
            [
                "第一章 招标公告",
                "投标人资格要求",
                "投标人须具备与本项目相适应的供货能力。",
                "第二章 采购需求",
                "技术要求",
                "课桌椅板材应符合国家环保标准。",
                "商务要求",
                "交货期为合同签订后30日内。",
                "第三章 评分办法",
                "评分项 | 分值 | 评分标准",
                "检测报告 | 5 | 提供得分",
                "第四章 投标文件格式、附件",
                "中小企业声明函（格式）",
                "详见附件1。",
            ]
        ),
        encoding="utf-8",
    )

    _, parse_result = load_document(file_path)

    assert parse_result.document_nodes
    assert parse_result.semantic_zones
    assert parse_result.effect_tag_results
    assert parse_result.clause_units

    zone_by_node = {item.node_id: item.zone_type for item in parse_result.semantic_zones}
    effect_by_node = {item.node_id: item.effect_tags for item in parse_result.effect_tag_results}

    qualification_node = next(item for item in parse_result.document_nodes if item.title == "投标人资格要求")
    technical_node = next(item for item in parse_result.document_nodes if item.title == "技术要求")
    business_node = next(item for item in parse_result.document_nodes if item.title == "商务要求")
    template_node = next(item for item in parse_result.document_nodes if item.title == "中小企业声明函（格式）")
    appendix_node = next(item for item in parse_result.document_nodes if item.text == "详见附件1。")

    assert zone_by_node[qualification_node.node_id] == SemanticZoneType.qualification
    assert zone_by_node[technical_node.node_id] == SemanticZoneType.technical
    assert zone_by_node[business_node.node_id] == SemanticZoneType.business
    assert zone_by_node[template_node.node_id] == SemanticZoneType.template
    assert zone_by_node[appendix_node.node_id] == SemanticZoneType.appendix_reference

    assert EffectTag.binding in effect_by_node[qualification_node.node_id]
    assert EffectTag.binding in effect_by_node[technical_node.node_id]
    assert EffectTag.binding in effect_by_node[business_node.node_id]
    assert EffectTag.template in effect_by_node[template_node.node_id]
    assert EffectTag.reference_only in effect_by_node[appendix_node.node_id]

    assert any(unit.zone_type == SemanticZoneType.scoring and "检测报告" in unit.text for unit in parse_result.clause_units)
    assert any(unit.zone_type == SemanticZoneType.template and EffectTag.template in unit.effect_tags for unit in parse_result.clause_units)
    assert all(unit.anchor.line_hint or unit.path for unit in parse_result.clause_units)


def test_sprint1_parser_marks_catalog_and_noise_as_non_binding(tmp_path: Path) -> None:
    file_path = tmp_path / "catalog_noise.txt"
    file_path.write_text(
        "\n".join(
            [
                "目录",
                "第一章 招标公告",
                "第二章 采购需求",
                "深圳政府采购网 信息公开",
                "第一章 招标公告",
                "项目概况",
                "预算金额：100000元",
            ]
        ),
        encoding="utf-8",
    )

    _, parse_result = load_document(file_path)

    zone_by_node = {item.node_id: item.zone_type for item in parse_result.semantic_zones}
    effect_by_node = {item.node_id: item.effect_tags for item in parse_result.effect_tag_results}

    catalog_node = next(item for item in parse_result.document_nodes if item.node_type.value == "catalog_entry")
    noise_node = next(item for item in parse_result.document_nodes if "深圳政府采购网" in item.text)

    assert zone_by_node[catalog_node.node_id] == SemanticZoneType.catalog_or_navigation
    assert effect_by_node[catalog_node.node_id] == [EffectTag.catalog]
    assert zone_by_node[noise_node.node_id] == SemanticZoneType.public_copy_or_noise
    assert EffectTag.public_copy_noise in effect_by_node[noise_node.node_id]


def test_parser_recognizes_administrative_header_fields_for_purchaser_and_agency(tmp_path: Path) -> None:
    file_path = tmp_path / "header_fields.txt"
    file_path.write_text(
        "\n".join(
            [
                "项目名称：某采购项目",
                "项目编号：SZCG-003",
                "采购人：某学校",
                "采购代理机构：某公共资源交易中心",
                "预算金额（元）：1000000.00元",
                "最高限价（元）：900000.00元",
            ]
        ),
        encoding="utf-8",
    )

    _, parse_result = load_document(file_path)
    extracted = extract_clauses_from_units(parse_result.clause_units)

    assert any(
        zone.zone_type == SemanticZoneType.administrative_info
        for zone in parse_result.semantic_zones
    )
    assert any(item.field_name == "采购人" for item in extracted)
    assert any(item.field_name == "采购代理机构" for item in extracted)
    assert any(item.field_name == "预算金额" for item in extracted)
    assert any(item.field_name == "最高限价" for item in extracted)

from pathlib import Path

from agent_review.parsers import load_document
from agent_review.ontology import EffectTag, SemanticZoneType


def test_text_parser_builds_blocks_tables_and_scoring_tree(tmp_path: Path) -> None:
    file_path = tmp_path / "scoring.txt"
    file_path.write_text(
        "\n".join(
            [
                "第一章 采购需求",
                "综合评分法评标信息",
                "评分项 | 分值 | 评分标准",
                "检测报告 | 5 | 提供得分",
                "第二章 合同条款",
                "付款方式：按合同约定支付。",
            ]
        ),
        encoding="utf-8",
    )

    _, parse_result = load_document(file_path)

    assert parse_result.raw_blocks
    assert parse_result.raw_tables
    table_node = next(item for item in parse_result.document_nodes if item.node_type.value == "table")
    assert table_node.path.startswith("ROOT > 第一章 采购需求 > 综合评分法评标信息")
    assert parse_result.semantic_zones
    table_zone = next(item for item in parse_result.semantic_zones if item.node_id == table_node.node_id)
    assert table_zone.zone_type == SemanticZoneType.scoring
    table_effect = next(item for item in parse_result.effect_tag_results if item.node_id == table_node.node_id)
    assert EffectTag.binding in table_effect.effect_tags


def test_text_parser_marks_appendix_and_template_regions(tmp_path: Path) -> None:
    file_path = tmp_path / "template.txt"
    file_path.write_text(
        "\n".join(
            [
                "第三章 投标文件格式、附件",
                "中小企业声明函（格式）",
                "投标人应按以下格式填写并盖章。",
                "附表1 评审资料清单",
                "详见附件一。",
            ]
        ),
        encoding="utf-8",
    )

    _, parse_result = load_document(file_path)

    appendix_nodes = [item for item in parse_result.document_nodes if item.node_type.value == "appendix"]
    assert appendix_nodes
    assert any(zone.zone_type in {SemanticZoneType.template, SemanticZoneType.appendix_reference} for zone in parse_result.semantic_zones if zone.node_id in {item.node_id for item in appendix_nodes})
    assert any(EffectTag.template in item.effect_tags or EffectTag.reference_only in item.effect_tags for item in parse_result.effect_tag_results if item.node_id in {node.node_id for node in appendix_nodes})

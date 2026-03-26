from pathlib import Path

from docx import Document

from agent_review.parsers import load_document


def test_build_document_tree_generates_paths_and_catalog_entries(tmp_path: Path) -> None:
    file_path = tmp_path / "tree.docx"
    document = Document()
    document.add_paragraph("目录", style="Title")
    document.add_paragraph("第一章 招标公告")
    document.add_paragraph("第二章 招标项目需求")
    document.add_paragraph("项目说明正文开始。")
    document.add_paragraph("第一章 招标公告", style="Heading 1")
    document.add_paragraph("一、投标人资格要求", style="Heading 2")
    document.add_paragraph("投标人须具备相关资质。")
    document.add_paragraph("第二章 招标项目需求", style="Heading 1")
    document.add_paragraph("四、具体技术要求", style="Heading 2")
    document.add_paragraph("提供符合标准的家具产品。")
    document.save(file_path)

    _, parse_result = load_document(file_path)

    assert parse_result.document_nodes
    catalog_nodes = [item for item in parse_result.document_nodes if item.node_type.value == "catalog_entry"]
    assert catalog_nodes
    chapter_nodes = [item for item in parse_result.document_nodes if item.node_type.value == "chapter"]
    assert any("第一章 招标公告" in item.path for item in chapter_nodes)
    assert any("第二章 招标项目需求" in item.path for item in chapter_nodes)
    assert any("四、具体技术要求" in item.path for item in parse_result.document_nodes)


def test_document_tree_keeps_table_rows_as_nodes(tmp_path: Path) -> None:
    file_path = tmp_path / "table_tree.docx"
    document = Document()
    document.add_paragraph("综合评分法评标信息", style="Heading 1")
    table = document.add_table(rows=2, cols=3)
    table.rows[0].cells[0].text = "评分项"
    table.rows[0].cells[1].text = "分值"
    table.rows[0].cells[2].text = "评分标准"
    table.rows[1].cells[0].text = "检测报告"
    table.rows[1].cells[1].text = "5"
    table.rows[1].cells[2].text = "提供得分"
    document.save(file_path)

    _, parse_result = load_document(file_path)

    assert any(item.node_type.value == "table" for item in parse_result.document_nodes)
    assert any(item.node_type.value == "table_row" for item in parse_result.document_nodes)

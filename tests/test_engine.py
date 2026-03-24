from pathlib import Path

from docx import Document
from PIL import Image

from agent_review.engine import TenderReviewEngine
from agent_review.models import ConclusionLevel, FileType, FindingType, Recommendation, ReviewMode
from agent_review.outputs import write_review_artifacts
from agent_review.parsers import load_document
from agent_review.reporting import render_markdown


def test_detects_manual_review_for_attachment_markers() -> None:
    text = """
    项目概况
    采购需求详见附件。
    供应商资格要求：具有相关资质。
    评分标准见附表。
    提交截止时间：2026年4月1日。
    付款方式：以正式合同为准。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")

    assert any(
        item.finding_type == FindingType.manual_review_required for item in report.findings
    )
    assert report.manual_review_queue
    assert report.scope_statement
    assert report.file_info.file_type in {
        FileType.complete_tender,
        FileType.procurement_requirement,
        FileType.mixed_document,
    }


def test_detects_restrictive_terms_warning() -> None:
    text = """
    采购需求
    本项目要求原厂服务团队，本地注册地供应商优先。
    资格要求
    供应商应具备相关资质。
    评分标准
    采用综合评分法。
    提交截止时间：2026年4月1日。
    付款方式：按合同执行。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")

    assert any(item.title == "发现潜在限制性竞争表述" for item in report.findings)
    assert any(item.rule_name == "指定品牌/原厂限制" for item in report.risk_hits)
    assert not any(item.rule_name == "主观评分表述" for item in report.risk_hits)
    assert report.overall_conclusion in {ConclusionLevel.revise, ConclusionLevel.reject}


def test_detects_sme_personnel_and_contract_risks() -> None:
    text = """
    项目名称：某服务项目
    项目属性：服务
    中小企业声明函：制造商声明
    本项目专门面向中小企业采购，仍适用价格扣除。
    年龄要求35岁以下，限女性，身高160以上。
    人员更换须经采购人同意，采购人有权直接指挥现场人员。
    采购人拥有最终解释权。
    尾款根据采购人满意度考核后支付。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")
    titles = {item.title for item in report.findings}

    assert "专门面向中小企业却仍保留价格扣除" in titles
    assert "服务项目声明函类型疑似错用货物模板" in titles
    assert "性别限制" in titles
    assert "采购人直接指挥" in titles
    assert "采购人单方解释或决定条款" in titles
    assert "尾款支付与考核条款联动风险" in titles


def test_detects_project_structure_and_template_conflicts() -> None:
    text = """
    项目名称：某物业服务项目
    采购标的：物业管理服务
    品目名称：办公家具
    项目属性：服务
    所属行业：工业
    中小企业声明函：制造商声明
    本项目专门面向中小企业采购，仍适用价格扣除。
    合同条款中写明质保期2年。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")
    titles = {item.title for item in report.findings}

    assert "项目属性与所属行业口径疑似不一致" in titles
    assert "项目属性与声明函模板口径冲突" in titles
    assert "服务项目保留货物类声明函模板" in titles
    assert "专门面向中小企业却保留价格扣除模板" in titles
    assert "项目属性 vs 品目名称" in titles
    assert "项目属性 vs 所属行业" in titles
    assert "项目属性 vs 中小企业声明函" in titles


def test_missing_dimension_generates_missing_evidence() -> None:
    text = "这是一份极短的文本，只提到项目概况。"
    report = TenderReviewEngine().review_text(text, document_name="short.txt")

    assert any(item.finding_type == FindingType.missing_evidence for item in report.findings)
    assert report.section_index
    assert isinstance(report.relative_strengths, list)


def test_load_document_supports_docx(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.docx"
    document = Document()
    document.add_paragraph("项目概况")
    document.add_paragraph("采购需求：提供运维服务。")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "预算金额"
    table.rows[0].cells[1].text = "100000"
    document.save(file_path)

    document_name, parse_result = load_document(file_path)
    assert document_name == "sample.docx"
    assert parse_result.source_format == "docx"
    assert "项目概况" in parse_result.text
    assert parse_result.tables


def test_load_document_supports_image_ocr_with_warning_when_tesseract_missing(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image = Image.new("RGB", (120, 40), color="white")
    image.save(image_path)

    document_name, parse_result = load_document(image_path)
    assert document_name == "sample.png"
    assert parse_result.source_format == "png"
    assert parse_result.page_count == 1
    assert isinstance(parse_result.warnings, list)


class FakeEnhancer:
    def enhance(self, report):
        report.summary = "这是经过LLM增强的结论摘要。"
        report.llm_enhanced = True
        report.specialist_tables.summaries["sme_policy"] = "这是经过LLM增强的中小企业政策专项摘要。"
        report.recommendations = [
            Recommendation(related_issue="测试问题", suggestion="这是经过LLM增强的建议。")
        ]
        return report


def test_engine_can_apply_llm_enhancer() -> None:
    text = """
    项目概况
    采购需求详见附件。
    评分标准见附表。
    """
    engine = TenderReviewEngine(review_enhancer=FakeEnhancer(), review_mode=ReviewMode.enhanced)
    report = engine.review_text(text, document_name="demo.txt")

    assert report.llm_enhanced is True
    assert report.summary == "这是经过LLM增强的结论摘要。"
    assert report.recommendations[0].suggestion == "这是经过LLM增强的建议。"
    assert report.specialist_tables.summaries["sme_policy"] == "这是经过LLM增强的中小企业政策专项摘要。"


def test_fast_mode_skips_enhancer() -> None:
    text = "项目概况\n采购需求详见附件。"
    engine = TenderReviewEngine(review_enhancer=FakeEnhancer(), review_mode=ReviewMode.fast)
    report = engine.review_text(text, document_name="demo.txt")

    assert report.review_mode == ReviewMode.fast
    assert report.llm_enhanced is False


def test_write_review_artifacts_outputs_base_and_final(tmp_path: Path) -> None:
    text = "项目概况\n采购需求详见附件。"
    base_engine = TenderReviewEngine(review_mode=ReviewMode.fast)
    base_report = base_engine.review_text(text, document_name="demo.txt")

    enhanced_engine = TenderReviewEngine(review_enhancer=FakeEnhancer(), review_mode=ReviewMode.enhanced)
    enhanced_report = enhanced_engine.review_text(text, document_name="demo.txt")

    bundle = write_review_artifacts(enhanced_report, base_report, tmp_path)

    assert Path(bundle.base_json_path).exists()
    assert Path(bundle.base_markdown_path).exists()
    assert Path(bundle.final_json_path).exists()
    assert Path(bundle.final_markdown_path).exists()
    assert Path(bundle.specialist_table_paths["sme_policy"]["base"]).exists()
    assert Path(bundle.specialist_table_paths["sme_policy"]["final"]).exists()


def test_write_review_artifacts_outputs_specialist_table_files(tmp_path: Path) -> None:
    text = """
    项目属性：服务
    中小企业声明函：制造商声明
    本项目专门面向中小企业采购，仍适用价格扣除。
    年龄要求35岁以下。
    采购人拥有最终解释权。
    """
    base_report = TenderReviewEngine(review_mode=ReviewMode.fast).review_text(text, document_name="demo.txt")
    enhanced_report = TenderReviewEngine(
        review_enhancer=FakeEnhancer(),
        review_mode=ReviewMode.enhanced,
    ).review_text(text, document_name="demo.txt")

    bundle = write_review_artifacts(enhanced_report, base_report, tmp_path)

    for table_name in [
        "project_structure",
        "sme_policy",
        "personnel_boundary",
        "contract_performance",
        "template_conflicts",
    ]:
        assert Path(bundle.specialist_table_paths[table_name]["base"]).exists()
        assert Path(bundle.specialist_table_paths[table_name]["final"]).exists()


def test_markdown_report_uses_v2_sections() -> None:
    text = """
    项目属性：服务
    本项目专门面向中小企业采购，仍适用价格扣除。
    年龄要求35岁以下。
    采购人拥有最终解释权。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")
    markdown = render_markdown(report)

    assert "## 高风险问题" in markdown
    assert "## 中风险问题" in markdown
    assert "## 审查边界说明" in markdown
    assert "## 中小企业政策一致性表" in markdown


def test_report_contains_specialist_tables() -> None:
    text = """
    项目属性：服务
    中小企业声明函：制造商声明
    本项目专门面向中小企业采购，仍适用价格扣除。
    年龄要求35岁以下。
    采购人拥有最终解释权。
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")

    assert report.specialist_tables.sme_policy
    assert report.specialist_tables.personnel_boundary
    assert report.specialist_tables.contract_performance


def test_markdown_can_render_specialist_summary() -> None:
    text = """
    项目属性：服务
    中小企业声明函：制造商声明
    本项目专门面向中小企业采购，仍适用价格扣除。
    """
    engine = TenderReviewEngine(review_enhancer=FakeEnhancer(), review_mode=ReviewMode.enhanced)
    report = engine.review_text(text, document_name="demo.txt")
    markdown = render_markdown(report)

    assert "中小企业政策一致性表摘要" in markdown
    assert "这是经过LLM增强的中小企业政策专项摘要。" in markdown

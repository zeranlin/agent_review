from pathlib import Path

from docx import Document
from PIL import Image

from agent_review.engine import TenderReviewEngine
from agent_review.models import ConclusionLevel, FileType, FindingType, Recommendation, ReviewMode
from agent_review.outputs import write_review_artifacts
from agent_review.parsers import load_document


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

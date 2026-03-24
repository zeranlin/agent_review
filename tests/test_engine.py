from agent_review.engine import TenderReviewEngine
from agent_review.models import FindingType


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


def test_missing_dimension_generates_missing_evidence() -> None:
    text = "这是一份极短的文本，只提到项目概况。"
    report = TenderReviewEngine().review_text(text, document_name="short.txt")

    assert any(item.finding_type == FindingType.missing_evidence for item in report.findings)

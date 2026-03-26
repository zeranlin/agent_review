from agent_review.engine import TenderReviewEngine
from agent_review.reporting import render_markdown, render_reviewer_report


def test_reporting_surfaces_rule_hit_and_review_point_instance_sections() -> None:
    text = """
    申请人的资格要求：
    投标人须成立满5年以上。
    投标人须具备广州市医疗器械行业同类项目业绩不少于2个。
    """
    report = TenderReviewEngine().review_text(text, document_name="report_trace_demo.txt")

    markdown = render_markdown(report)
    reviewer = render_reviewer_report(report)

    assert "## RuleHit" in markdown
    assert "## ReviewPointInstance" in markdown
    assert "LLM增强状态：" not in reviewer
    assert "新链摘要：RuleHit" not in reviewer

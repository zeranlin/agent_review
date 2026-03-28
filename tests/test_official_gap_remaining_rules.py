from agent_review.engine import TenderReviewEngine
from agent_review.parser_engine.extractors.clauses import extract_clauses
from agent_review.reporting import render_reviewer_report


def test_parser_extracts_remaining_gap_fields() -> None:
    text = """
    资格要求：
    不接受个体工商户及其他组织形式参与投标。
    评分标准：
    投标人具有质量管理体系认证证书且认证范围包含医疗器械维修服务的，得3分。
    投标人具有特种设备安全管理和作业人员证书的，得2分。
    价格权重：9%
    合同条款：
    采购人应在收到发票后20个工作日内完成资金支付。
    合同履行期限：38个月。
    """
    extracted = extract_clauses(text)
    field_map = {item.field_name: item for item in extracted}

    assert "供应商组织形式限制" in field_map
    assert "体系认证范围要求" in field_map
    assert "准入类证书评分项" in field_map
    assert field_map["价格权重"].normalized_value.startswith("9")
    assert field_map["付款时限"].normalized_value == "20"
    assert field_map["服务期限月数"].normalized_value == "38"


def test_remaining_gap_rules_enter_formal_and_report() -> None:
    text = """
    项目属性：服务
    资格要求：
    不接受个体工商户及其他组织形式参与投标。
    评分标准：
    投标人具有质量管理体系认证证书且认证范围包含医疗器械维修服务的，得3分。
    投标人具有特种设备安全管理和作业人员证书的，得2分。
    价格权重：9%
    合同条款：
    采购人应在收到发票后20个工作日内完成资金支付。
    合同履行期限：38个月。
    """
    report = TenderReviewEngine().review_text(text, document_name="remaining_gap_rules.txt")
    formal_titles = {
        item.title
        for item in report.formal_adjudication
        if item.included_in_formal
    }
    reviewer = render_reviewer_report(report)

    assert "不得限定供应商组织形式" in formal_titles
    assert "体系认证证书不得要求特定认证范围" in formal_titles
    assert "不得将准入类、行政许可类资格职业证书设置为评分项" in formal_titles
    assert "依法设定价格分值" in formal_titles
    assert "采购人应当在收到发票后N个工作日内完成资金支付/采购人应当在收到发票后N个工作日或Y日内完成资金支付" in formal_titles
    assert "合理设置合同履行期限" in formal_titles

    assert "不得限定供应商组织形式" in reviewer
    assert "体系认证证书不得要求特定认证范围" in reviewer
    assert "不得将准入类、行政许可类资格职业证书设置为评分项" in reviewer
    assert "依法设定价格分值" in reviewer
    assert "采购人应当在收到发票后N个工作日内完成资金支付/采购人应当在收到发票后N个工作日或Y日内完成资金支付" in reviewer
    assert "合理设置合同履行期限" in reviewer


def test_contract_duration_placeholder_is_treated_as_term_clarity_risk() -> None:
    text = """
    项目属性：服务
    合同条款：
    合同履行期限：本项目建设周期为12个月，自合同签订之日起至终验止（即 年 月 日至 年 月 日）。
    """
    report = TenderReviewEngine().review_text(text, document_name="service_term_placeholder.txt")
    formal_map = {item.title: item for item in report.formal_adjudication}
    adjudication = formal_map["合理设置合同履行期限"]

    assert adjudication.legal_basis_applicable is True
    assert adjudication.included_in_formal is True

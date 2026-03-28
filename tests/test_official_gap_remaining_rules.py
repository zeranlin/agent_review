from agent_review.engine import TenderReviewEngine
from agent_review.parser_engine.extractors.clauses import extract_clauses
from agent_review.quality import evidence_supports_title
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


def test_contract_linkage_title_rejects_function_requirement_quote() -> None:
    quote = "支持审核人员外呼号码配置、工单外呼、未拨打电话原因审核、通话记录、录音存储等功能。"
    assert evidence_supports_title("尾款支付与考核条款联动风险", quote) is False


def test_function_requirement_rows_do_not_trigger_tail_payment_assessment_risk() -> None:
    text = """
    项目属性：服务
    技术功能需求：
    支持考核中心外呼模块、账号切换权限管理、通话记录、录音存储等功能。
    系统应支持同时打开多个管理窗口以对不同任务进行并行的操作。
    合同条款：
    测试用例通过用户审核后，甲方支付首期款；终验后支付尾款。
    """
    report = TenderReviewEngine().review_text(text, document_name="function_requirement_false_positive.txt")
    formal_map = {item.title: item for item in report.formal_adjudication}
    adjudication = formal_map["尾款支付与考核条款联动风险"]

    assert adjudication.included_in_formal is False


def test_function_requirement_rows_do_not_trigger_assessment_payment_control_risk() -> None:
    text = """
    项目属性：服务
    项目背景：
    提出要全面提升市民满意度，提高“一件事”办理质量，完善知识库运营机制，完善绩效考核监测功能。
    技术功能需求：
    支持考核中心外呼模块、账号切换权限管理、通话记录、录音存储等功能。
    系统应支持同时打开多个管理窗口以对不同任务进行并行的操作。
    合同条款：
    付款方式：终验后支付尾款。
    """
    report = TenderReviewEngine().review_text(text, document_name="assessment_payment_false_positive.txt")
    formal_map = {item.title: item for item in report.formal_adjudication}
    adjudication = formal_map["考核条款可能控制付款或履约评价"]

    assert adjudication.included_in_formal is False


def test_p1_bundle_rules_enter_formal_and_report_with_refined_quotes() -> None:
    text = """
    资格要求：投标人须具备深圳市医疗器械行业同类项目业绩不少于2个（提供合同扫描件）。
    评分标准：同类项目业绩每增加1个加2分，最高6分。
    验收条款：验收时产生的第三方检测费用由中标人承担，无论检测结果是否合格。
    技术要求：产品须符合GB/T 99999-2024《医疗机器人通用技术规范》要求；产品响应时间：100ms。设备重量≤500kg(不允许正偏离)。设备重量允许±10%偏差。系统应具有良好的操作体验，界面友好美观。
    """
    report = TenderReviewEngine().review_text(text, document_name="p1_bundle.txt")
    formal_titles = {item.title for item in report.formal_adjudication if item.included_in_formal}
    reviewer = render_reviewer_report(report)

    assert "资格业绩要求可能存在地域限定、行业口径过窄或与评分重复" in formal_titles
    assert "第三方检测费用无论结果均由中标人承担" in formal_titles
    assert "疑似使用不存在的技术标准" in formal_titles
    assert "技术参数区间说明不足" in formal_titles
    assert "同一技术参数区间说明冲突" in formal_titles
    assert "技术要求存在主观描述" in formal_titles

    assert "深圳市医疗器械行业同类项目业绩不少于2个" in reviewer
    assert "第三方检测费用由中标人承担，无论检测结果是否合格" in reviewer
    assert "GB/T 99999-2024《医疗机器人通用技术规范》要求" in reviewer
    assert "响应时间：100ms" in reviewer or "设备重量≤500kg(不允许正偏离)" in reviewer
    assert "良好的操作体验，界面友好美观" in reviewer
    assert "第三方检测费用由中标人承担，无论检测结果是否合格。技术要求" not in reviewer

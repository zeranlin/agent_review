from agent_review.engine import TenderReviewEngine
from agent_review.reporting import render_reviewer_report
from agent_review.rules.risk_rules import match_risk_rules


def test_risk_rules_detect_hku300_first_batch_scoring_and_technical_gaps() -> None:
    text = """
    产品须符合GB/T 99999-2024《医疗机器人通用技术规范》要求；
    产品响应时间：100ms
    手术机械臂精度：0.1-0.5mm
    位置A:设备重量≤500kg(不允许正偏离)
    位置B:设备重量允许±10%偏差
    投标人资产总额达到5000万元以上的，得5分；达到1亿元以上得8分。
    投标人从业人员超过50人的，得2分；超过100人的，得5分。
    投标人近三年年均纳税额达到200万元以上的，得5分。
    投标人成立时间满5年的得3分，满10年的得5分，满15年的得8分。
    价格分计算方法：采用中间价优先法计算，即去掉最高价和最低价后，取剩余投标报价的算术平均值作为评标基准价，其价格分为满分。
    手术机械人系统应具有良好的操作体验，界面友好美观。
    """
    hits = {item.rule_name for item in match_risk_rules(text)}

    assert "疑似使用不存在的技术标准" in hits
    assert "技术参数区间说明不足" in hits
    assert "同一技术参数区间说明冲突" in hits
    assert "资产总额被设为评分因素" in hits
    assert "从业人员被设为评分因素" in hits
    assert "纳税额被设为评分因素" in hits
    assert "成立年限被设为评分因素" in hits
    assert "综合评分法价格分未采用低价优先法" in hits
    assert "技术要求存在主观描述" in hits


def test_engine_surfaces_hku300_first_batch_new_rule_findings() -> None:
    text = """
    项目属性：货物
    产品须符合GB/T 99999-2024《医疗机器人通用技术规范》要求；
    手术机械臂精度：0.1-0.5mm
    位置A:设备重量≤500kg(不允许正偏离)
    位置B:设备重量允许±10%偏差
    投标人资产总额达到5000万元以上的，得5分；达到1亿元以上得8分。
    价格分计算方法：采用中间价优先法计算，即去掉最高价和最低价后，取剩余投标报价的算术平均值作为评标基准价，其价格分为满分。
    手术机械人系统应具有良好的操作体验，界面友好美观。
    """
    report = TenderReviewEngine().review_text(text, document_name="hku300_gap.txt")
    titles = {item.title for item in report.findings}

    assert "疑似使用不存在的技术标准" in titles
    assert "同一技术参数区间说明冲突" in titles
    assert "资产总额被设为评分因素" in titles
    assert "综合评分法价格分未采用低价优先法" in titles
    assert "技术要求存在主观描述" in titles


def test_first_batch_new_rules_enter_formal_and_reviewer_report() -> None:
    text = """
    产品须符合GB/T 99999-2024《医疗机器人通用技术规范》要求；
    产品响应时间：100ms
    手术机械臂精度：0.1-0.5mm
    设备重量≤500kg(不允许正偏离)
    设备重量允许±10%偏差
    投标人资产总额达到5000万元以上的，得5分；达到1亿元以上得8分。
    投标人从业人员超过50人的，得2分；超过100人的，得5分。
    投标人近三年年均纳税额达到200万元以上的，得5分。
    投标人成立时间满5年的得3分，满10年的得5分，满15年的得8分。
    价格分计算方法：采用中间价优先法计算，即去掉最高价和最低价后，取剩余投标报价的算术平均值作为评标基准价，其价格分为满分。
    手术机械人系统应具有良好的操作体验，界面友好美观。
    """
    report = TenderReviewEngine().review_text(text, document_name="hku300_formal.txt")
    formal_titles = {
        item.title
        for item in report.formal_adjudication
        if item.included_in_formal
    }
    reviewer = render_reviewer_report(report)

    assert "疑似使用不存在的技术标准" in formal_titles
    assert "技术参数区间说明不足" in formal_titles
    assert "同一技术参数区间说明冲突" in formal_titles
    assert "资产总额被设为评分因素" in formal_titles
    assert "从业人员被设为评分因素" in formal_titles
    assert "纳税额被设为评分因素" in formal_titles
    assert "成立年限被设为评分因素" in formal_titles
    assert "综合评分法价格分未采用低价优先法" in formal_titles
    assert "技术要求存在主观描述" in formal_titles

    assert "资产总额被设为评分因素" in reviewer
    assert "从业人员被设为评分因素" in reviewer
    assert "纳税额被设为评分因素" in reviewer
    assert "成立年限被设为评分因素" in reviewer
    assert "综合评分法价格分未采用低价优先法" in reviewer
    assert "疑似使用不存在的技术标准" in reviewer
    assert "技术参数区间说明不足" in reviewer
    assert "同一技术参数区间说明冲突" in reviewer
    assert "技术要求存在主观描述" in reviewer

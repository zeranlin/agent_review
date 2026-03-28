from agent_review.report_engine.reporting import _prune_reviewer_entries


def _entry(title: str, quote: str = "") -> dict[str, object]:
    return {
        "问题标题": title,
        "问题定性": "高风险",
        "审查类型": "测试",
        "原文位置": "第1行",
        "原文摘录": [quote or title],
        "风险判断": "测试",
        "法律/政策依据": ["测试依据"],
    }


def test_parent_titles_yield_to_specific_child_titles() -> None:
    entries = [
        _entry("履约保证金转质量保证金或长期无息占压"),
        _entry("明确说明保证金缴纳方式"),
        _entry("不得违规设置质量保证金"),
        _entry("投标阶段证书或检测报告负担过重"),
        _entry("不得缺失“超出检测机构能力范围”处理的相关说明"),
        _entry("证明材料来源可能被限定为特定机构或特定出具口径"),
        _entry("资格条件与政策适用口径可能自相矛盾"),
        _entry("不得将资产总额的隐性限制证书设置为资格条件"),
        _entry("资格条件可能缺乏履约必要性或带有歧视性门槛"),
        _entry("特定资质或证书要求超必要限度"),
    ]

    titles = {item["问题标题"] for item in _prune_reviewer_entries(entries)}

    assert "履约保证金转质量保证金或长期无息占压" not in titles
    assert "投标阶段证书或检测报告负担过重" not in titles
    assert "资格条件与政策适用口径可能自相矛盾" not in titles
    assert "资格条件可能缺乏履约必要性或带有歧视性门槛" not in titles
    assert "明确说明保证金缴纳方式" in titles
    assert "不得违规设置质量保证金" in titles
    assert "不得缺失“超出检测机构能力范围”处理的相关说明" in titles
    assert "特定资质或证书要求超必要限度" in titles


def test_overlap_parent_title_suppressed_only_without_direct_qualification_quote() -> None:
    entries = [
        _entry("资格条件与评分因素重复设门槛", "评分内容：投标人具备ISO9001证书，未提供的不得分。"),
        _entry("资产总额被设为评分因素"),
        _entry("不得将资产总额的隐性限制证书设置为资格条件"),
    ]
    titles = {item["问题标题"] for item in _prune_reviewer_entries(entries)}
    assert "资格条件与评分因素重复设门槛" not in titles

    entries_with_direct_gate = [
        _entry("资格条件与评分因素重复设门槛", "申请人的资格要求：投标人须具备相关证书；评分中未提供的不得分。"),
        _entry("资产总额被设为评分因素"),
    ]
    titles_with_direct_gate = {item["问题标题"] for item in _prune_reviewer_entries(entries_with_direct_gate)}
    assert "资格条件与评分因素重复设门槛" in titles_with_direct_gate

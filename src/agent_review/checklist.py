from __future__ import annotations

from .models import ReviewDimension


DEFAULT_DIMENSIONS: list[ReviewDimension] = [
    ReviewDimension(
        key="scope_clarity",
        display_name="采购范围清晰度",
        description="检查采购标的、数量、技术需求和服务边界是否明确。",
        triggers=["采购内容", "采购需求", "服务范围", "项目概况", "技术要求"],
        missing_markers=["详见附件", "另册", "未提供"],
        risk_hint="采购范围不清会导致供应商无法形成可比报价。",
    ),
    ReviewDimension(
        key="bidder_qualification",
        display_name="供应商资格条件",
        description="检查资格条件是否与项目特点相适应，是否存在过度门槛。",
        triggers=["资格要求", "供应商资格", "特定资格", "业绩要求", "资质要求"],
        missing_markers=["原件备查", "以附件为准"],
        risk_hint="资格条件过严或与采购需求无关，可能形成限制竞争。",
    ),
    ReviewDimension(
        key="evaluation_criteria",
        display_name="评审标准明确性",
        description="检查评分因素、权重、评审方法是否清楚且可操作。",
        triggers=["评分标准", "评标办法", "综合评分", "价格分", "技术分"],
        missing_markers=["见附表", "详见评分细则"],
        risk_hint="评分标准不明确可能导致评审自由裁量过大。",
    ),
    ReviewDimension(
        key="restrictive_terms",
        display_name="限制性条款筛查",
        description="检查是否存在指向特定品牌、地区、所有制或历史合作关系的限制。",
        triggers=["指定品牌", "原厂", "本地", "注册地", "唯一", "同类项目"],
        missing_markers=[],
        risk_hint="限制性或歧视性条款会直接影响公平竞争。",
    ),
    ReviewDimension(
        key="process_timeline",
        display_name="时间与流程完整性",
        description="检查公告、报名、答疑、提交、开标和质疑救济等流程要素是否齐备。",
        triggers=["提交截止", "开标时间", "答疑", "质疑", "公告期限", "地点"],
        missing_markers=["另行通知"],
        risk_hint="流程信息缺失会影响供应商参与权和救济权。",
    ),
    ReviewDimension(
        key="contract_terms",
        display_name="合同条款风险",
        description="检查付款、验收、违约、知识产权和风险分配是否明显失衡。",
        triggers=["付款方式", "验收", "违约责任", "知识产权", "风险承担"],
        missing_markers=["合同另签", "以正式合同为准"],
        risk_hint="失衡合同条款可能实质性影响投标决策。",
    ),
]

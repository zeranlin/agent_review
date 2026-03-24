from __future__ import annotations

from ..models import ClauseRole, ExtractedClause


def extract_clauses(text: str) -> list[ExtractedClause]:
    patterns = [
        ("项目基本信息", "项目名称", ["项目名称"]),
        ("项目基本信息", "项目编号", ["项目编号"]),
        ("项目基本信息", "采购方式", ["采购方式", "公开招标", "竞争性磋商", "竞争性谈判"]),
        ("项目基本信息", "采购标的", ["采购标的", "采购内容", "采购需求"]),
        ("项目基本信息", "品目名称", ["品目名称"]),
        ("项目基本信息", "项目属性", ["货物", "工程", "服务"]),
        ("项目基本信息", "预算金额", ["预算金额"]),
        ("项目基本信息", "最高限价", ["最高限价"]),
        ("项目基本信息", "合同履行期限", ["合同履行期限"]),
        ("资格条款", "一般资格要求", ["资格要求", "供应商资格"]),
        ("资格条款", "特定资格要求", ["特定资格要求", "资质要求"]),
        ("资格条款", "信用要求", ["信用要求"]),
        ("资格条款", "是否允许联合体", ["联合体"]),
        ("资格条款", "是否允许分包", ["分包"]),
        ("技术条款", "样品要求", ["样品"]),
        ("技术条款", "现场演示要求", ["演示"]),
        ("技术条款", "是否指定品牌", ["品牌", "原厂"]),
        ("技术条款", "是否要求专利", ["专利"]),
        ("技术条款", "是否要求检测报告", ["检测报告"]),
        ("技术条款", "是否要求认证证书", ["认证证书", "证书"]),
        ("技术条款", "是否设置★实质性条款", ["★"]),
        ("技术条款", "是否有限制产地厂家商标", ["产地", "厂家", "商标"]),
        ("评分条款", "评分方法", ["评分方法", "综合评分", "评标办法"]),
        ("评分条款", "价格分", ["价格分"]),
        ("评分条款", "技术分", ["技术分"]),
        ("评分条款", "商务分", ["商务分"]),
        ("评分条款", "证书加分", ["证书加分", "证书"]),
        ("评分条款", "业绩加分", ["业绩加分", "业绩"]),
        ("评分条款", "方案评分", ["方案评分", "实施方案"]),
        ("评分条款", "售后加分", ["售后"]),
        ("评分条款", "财务指标加分", ["财务指标", "利润率", "营业收入", "注册资本", "资产规模"]),
        ("评分条款", "人员评分要求", ["项目负责人", "人员配置", "社保", "学历", "职称"]),
        ("评分条款", "样品分", ["样品分"]),
        ("合同条款", "付款节点", ["付款方式", "付款节点"]),
        ("合同条款", "验收标准", ["验收标准", "验收"]),
        ("合同条款", "争议解决方式", ["争议解决"]),
        ("合同条款", "违约责任", ["违约责任"]),
        ("合同条款", "质保期", ["质保期"]),
        ("合同条款", "履约保证金", ["履约保证金"]),
        ("合同条款", "考核条款", ["考核", "绩效考核"]),
        ("合同条款", "扣款条款", ["扣款", "扣罚", "罚款"]),
        ("合同条款", "解约条款", ["解约", "解除合同"]),
        ("合同条款", "单方解释权", ["解释权", "以采购人意见为准", "以采购人解释为准"]),
        ("人员条款", "性别限制", ["男性", "女性", "性别"]),
        ("人员条款", "年龄限制", ["年龄"]),
        ("人员条款", "身高限制", ["身高"]),
        ("人员条款", "容貌体形要求", ["容貌", "体形", "五官端正"]),
        ("人员条款", "学历职称要求", ["学历", "职称"]),
        ("人员条款", "采购人审批录用", ["采购人审批", "批准录用", "录用审批"]),
        ("人员条款", "采购人批准更换", ["批准更换", "人员更换须经采购人同意"]),
        ("人员条款", "采购人直接指挥", ["采购人有权直接指挥", "服从采购人安排"]),
        ("政策条款", "是否专门面向中小企业", ["专门面向中小企业", "中小企业"]),
        ("政策条款", "是否为预留份额采购", ["预留份额"]),
        ("政策条款", "是否允许分包落实中小企业政策", ["分包", "中小企业政策"]),
        ("政策条款", "所属行业划分", ["所属行业"]),
        ("政策条款", "中小企业声明函类型", ["中小企业声明函", "承接方", "制造商"]),
        ("政策条款", "是否仍保留价格扣除条款", ["价格扣除"]),
        ("政策条款", "是否涉及进口产品", ["进口产品"]),
        ("政策条款", "分包比例", ["分包比例", "预留比例", "小微企业比例"]),
    ]
    lines = text.splitlines()
    clauses: list[ExtractedClause] = []
    for category, field_name, keywords in patterns:
        for line_no, line in enumerate(lines, start=1):
            if any(keyword in line for keyword in keywords):
                clauses.append(
                    ExtractedClause(
                        category=category,
                        field_name=field_name,
                        content=line[:120],
                        source_anchor=f"line:{line_no}",
                        clause_role=classify_clause_role(line),
                    )
                )
                break
    return clauses


def classify_extracted_clauses(clauses: list[ExtractedClause]) -> list[ExtractedClause]:
    for clause in clauses:
        clause.clause_role = classify_clause_role(clause.content)
    return clauses


def classify_clause_role(text: str) -> ClauseRole:
    normalized = text.strip()
    if not normalized:
        return ClauseRole.unknown

    form_markers = [
        "证明书",
        "格式",
        "以下格式文件由供应商根据需要选用",
        "单位名称（盖章）",
        "法定代表人",
        "投标人代表",
        "联合体共同投标协议书",
    ]
    if (
        any(marker in normalized for marker in form_markers)
        or "____" in normalized
        or "______" in normalized
        or normalized.endswith("声明函")
        or normalized.startswith("声明函")
        or normalized.startswith("中小企业声明函")
        or normalized.startswith("残疾人福利性单位声明函")
    ):
        return ClauseRole.form_template

    if "详见附件" in normalized or "附表" in normalized or "附件" in normalized:
        return ClauseRole.appendix_reference

    if any(marker in normalized for marker in ["名词解释", "采购代理机构：", "采购人：", "投标人：", "评标委员会"]):
        return ClauseRole.document_definition

    if any(marker in normalized for marker in ["根据《", "依据《", "管理办法", "通知》", "实施条例", "政府采购法"]) and any(
        marker in normalized for marker in ["规定", "说明", "政策", "扶持", "扣除"]
    ):
        return ClauseRole.policy_explanation

    if any(marker in normalized for marker in ["付款", "验收", "违约", "解约", "质保", "履约", "安装", "调试"]):
        return ClauseRole.contract_term

    if any(marker in normalized for marker in ["资格要求", "评分", "综合评分", "评标", "分值", "业绩", "证书", "样品", "技术要求", "商务要求"]):
        return ClauseRole.qualification_or_scoring

    if any(marker in normalized for marker in ["不接受联合体", "不允许合同分包", "采购包", "中小企业", "价格扣除", "采购需求", "货物", "服务", "工程"]):
        return ClauseRole.procurement_requirement

    return ClauseRole.unknown

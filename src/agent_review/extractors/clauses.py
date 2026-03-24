from __future__ import annotations

import re
from collections.abc import Callable

from ..models import ClauseRole, ExtractedClause


ClauseExtractor = Callable[[list[str]], ExtractedClause | None]


def extract_clauses(text: str) -> list[ExtractedClause]:
    lines = text.splitlines()
    clauses: list[ExtractedClause] = []
    for category, field_name, extractor in FIELD_EXTRACTORS:
        clause = extractor(lines)
        if clause is None:
            continue
        clauses.append(
            ExtractedClause(
                category=category,
                field_name=field_name,
                content=clause.content,
                source_anchor=clause.source_anchor,
                normalized_value=clause.normalized_value,
                relation_tags=clause.relation_tags,
                clause_role=classify_clause_role(clause.content),
            )
        )
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


def _simple_keyword_extractor(keywords: list[str]) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if any(keyword in line for keyword in keywords):
                return _build_clause(line, line_no)
        return None

    return extractor


def _property_type_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["项目属性", "货物", "工程", "服务"]):
            continue
        value = ""
        if "货物" in line:
            value = "货物"
        elif "服务" in line:
            value = "服务"
        elif "工程" in line:
            value = "工程"
        if value:
            return _build_clause(line, line_no, normalized_value=value, relation_tags=[value])
    return None


def _allowance_extractor(keywords: list[str], disallow_tokens: list[str], allow_tokens: list[str]) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if not any(keyword in line for keyword in keywords):
                continue
            normalized_value = ""
            relation_tags: list[str] = []
            if any(token in line for token in disallow_tokens):
                normalized_value = "不允许"
                relation_tags.append("禁止")
            elif any(token in line for token in allow_tokens):
                normalized_value = "允许"
                relation_tags.append("允许")
            return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
        return None

    return extractor


def _boolean_policy_extractor(keywords: list[str], positive_tokens: list[str]) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if not any(keyword in line for keyword in keywords):
                continue
            normalized_value = "是" if any(token in line for token in positive_tokens) else ""
            tags = ["是"] if normalized_value == "是" else []
            return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=tags)
        return None

    return extractor


def _declaration_type_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if "中小企业声明函" not in line and "制造商" not in line and "承接方" not in line:
            continue
        normalized_value = ""
        relation_tags: list[str] = []
        if "制造商" in line or "声明函（货物）" in line or "全部货物" in line:
            normalized_value = "货物/制造商"
            relation_tags.extend(["货物模板", "制造商口径"])
        if "承接" in line or "服务全部由" in line or "声明函（工程、服务）" in line:
            normalized_value = "服务/承接方" if not normalized_value else f"{normalized_value}+服务/承接方"
            relation_tags.extend(["服务模板", "承接方口径"])
        if "施工单位" in line:
            relation_tags.append("工程口径")
        return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
    return None


def _price_deduction_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if "价格扣除" not in line:
            continue
        normalized_value = "是"
        relation_tags = ["价格扣除保留"]
        if "不适用" in line or "不再适用" in line:
            normalized_value = "否"
            relation_tags = ["价格扣除不适用"]
        return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
    return None


def _percentage_extractor(keywords: list[str]) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if not any(keyword in line for keyword in keywords):
                continue
            match = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
            normalized_value = match.group(1) + "%" if match else ""
            relation_tags = [normalized_value] if normalized_value else []
            return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
        return None

    return extractor


def _payment_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["付款方式", "付款节点", "支付"]):
            continue
        relation_tags: list[str] = []
        if "尾款" in line:
            relation_tags.append("尾款")
        if any(token in line for token in ["验收后", "验收合格后"]):
            relation_tags.append("验收触发")
        if any(token in line for token in ["考核", "满意度", "评价"]):
            relation_tags.append("考核联动")
        return _build_clause(line, line_no, normalized_value="存在", relation_tags=relation_tags)
    return None


def _assessment_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["考核", "绩效考核", "满意度"]):
            continue
        relation_tags = ["存在"]
        if any(token in line for token in ["付款", "支付", "尾款"]):
            relation_tags.append("关联付款")
        if "满意度" in line:
            relation_tags.append("满意度")
        return _build_clause(line, line_no, normalized_value="存在", relation_tags=relation_tags)
    return None


def _acceptance_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["验收标准", "验收"]):
            continue
        relation_tags = ["存在"]
        if any(token in line for token in ["满意度", "采购人确认"]):
            relation_tags.append("主观验收")
        return _build_clause(line, line_no, normalized_value="存在", relation_tags=relation_tags)
    return None


def _personnel_line_extractor(keywords: list[str], normalized_value: str, relation_tags: list[str] | None = None) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if any(keyword in line for keyword in keywords):
                return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags or [])
        return None

    return extractor


def _build_clause(
    line: str,
    line_no: int,
    *,
    normalized_value: str = "",
    relation_tags: list[str] | None = None,
) -> ExtractedClause:
    return ExtractedClause(
        category="",
        field_name="",
        content=line[:160],
        source_anchor=f"line:{line_no}",
        normalized_value=normalized_value,
        relation_tags=relation_tags or [],
    )


FIELD_EXTRACTORS: list[tuple[str, str, ClauseExtractor]] = [
    ("项目基本信息", "项目名称", _simple_keyword_extractor(["项目名称"])),
    ("项目基本信息", "项目编号", _simple_keyword_extractor(["项目编号"])),
    ("项目基本信息", "采购方式", _simple_keyword_extractor(["采购方式", "公开招标", "竞争性磋商", "竞争性谈判"])),
    ("项目基本信息", "采购标的", _simple_keyword_extractor(["采购标的", "采购内容", "采购需求"])),
    ("项目基本信息", "品目名称", _simple_keyword_extractor(["品目名称"])),
    ("项目基本信息", "项目属性", _property_type_extractor),
    ("项目基本信息", "预算金额", _simple_keyword_extractor(["预算金额"])),
    ("项目基本信息", "最高限价", _simple_keyword_extractor(["最高限价"])),
    ("项目基本信息", "合同履行期限", _simple_keyword_extractor(["合同履行期限"])),
    ("资格条款", "一般资格要求", _simple_keyword_extractor(["资格要求", "供应商资格"])),
    ("资格条款", "特定资格要求", _simple_keyword_extractor(["特定资格要求", "资质要求"])),
    ("资格条款", "信用要求", _simple_keyword_extractor(["信用要求"])),
    ("资格条款", "是否允许联合体", _allowance_extractor(["联合体"], ["不接受联合体", "不允许联合体"], ["允许联合体", "接受联合体"])),
    ("资格条款", "是否允许分包", _allowance_extractor(["分包"], ["不允许合同分包", "不得分包", "不允许分包"], ["允许分包", "可以分包"])),
    ("技术条款", "样品要求", _simple_keyword_extractor(["样品"])),
    ("技术条款", "现场演示要求", _simple_keyword_extractor(["演示"])),
    ("技术条款", "是否指定品牌", _simple_keyword_extractor(["品牌", "原厂"])),
    ("技术条款", "是否要求专利", _simple_keyword_extractor(["专利"])),
    ("技术条款", "是否要求检测报告", _simple_keyword_extractor(["检测报告"])),
    ("技术条款", "是否要求认证证书", _simple_keyword_extractor(["认证证书", "证书"])),
    ("技术条款", "是否设置★实质性条款", _simple_keyword_extractor(["★"])),
    ("技术条款", "是否有限制产地厂家商标", _simple_keyword_extractor(["产地", "厂家", "商标"])),
    ("评分条款", "评分方法", _simple_keyword_extractor(["评分方法", "综合评分", "评标办法"])),
    ("评分条款", "价格分", _simple_keyword_extractor(["价格分"])),
    ("评分条款", "技术分", _simple_keyword_extractor(["技术分"])),
    ("评分条款", "商务分", _simple_keyword_extractor(["商务分"])),
    ("评分条款", "证书加分", _simple_keyword_extractor(["证书加分", "证书"])),
    ("评分条款", "业绩加分", _simple_keyword_extractor(["业绩加分", "业绩"])),
    ("评分条款", "方案评分", _simple_keyword_extractor(["方案评分", "实施方案"])),
    ("评分条款", "售后加分", _simple_keyword_extractor(["售后"])),
    ("评分条款", "财务指标加分", _simple_keyword_extractor(["财务指标", "利润率", "营业收入", "注册资本", "资产规模"])),
    ("评分条款", "人员评分要求", _simple_keyword_extractor(["项目负责人", "人员配置", "社保", "学历", "职称"])),
    ("评分条款", "样品分", _simple_keyword_extractor(["样品分"])),
    ("合同条款", "付款节点", _payment_extractor),
    ("合同条款", "验收标准", _acceptance_extractor),
    ("合同条款", "争议解决方式", _simple_keyword_extractor(["争议解决"])),
    ("合同条款", "违约责任", _simple_keyword_extractor(["违约责任"])),
    ("合同条款", "质保期", _simple_keyword_extractor(["质保期"])),
    ("合同条款", "履约保证金", _simple_keyword_extractor(["履约保证金"])),
    ("合同条款", "考核条款", _assessment_extractor),
    ("合同条款", "扣款条款", _simple_keyword_extractor(["扣款", "扣罚", "罚款"])),
    ("合同条款", "解约条款", _simple_keyword_extractor(["解约", "解除合同"])),
    ("合同条款", "单方解释权", _simple_keyword_extractor(["解释权", "以采购人意见为准", "以采购人解释为准"])),
    ("人员条款", "性别限制", _personnel_line_extractor(["男性", "女性", "限女性", "限男性"], "存在", ["性别限制"])),
    ("人员条款", "年龄限制", _personnel_line_extractor(["年龄", "岁以下", "岁以上"], "存在", ["年龄限制"])),
    ("人员条款", "身高限制", _personnel_line_extractor(["身高"], "存在", ["身高限制"])),
    ("人员条款", "容貌体形要求", _personnel_line_extractor(["容貌", "体形", "五官端正"], "存在", ["容貌体形要求"])),
    ("人员条款", "学历职称要求", _personnel_line_extractor(["学历", "职称"], "存在", ["学历职称要求"])),
    ("人员条款", "采购人审批录用", _personnel_line_extractor(["采购人审批", "批准录用", "录用审批"], "存在", ["采购人审批录用"])),
    ("人员条款", "采购人批准更换", _personnel_line_extractor(["批准更换", "人员更换须经采购人同意"], "存在", ["采购人批准更换"])),
    ("人员条款", "采购人直接指挥", _personnel_line_extractor(["采购人有权直接指挥", "服从采购人安排"], "存在", ["采购人直接指挥"])),
    ("政策条款", "是否专门面向中小企业", _boolean_policy_extractor(["专门面向中小企业", "中小微企业采购"], ["专门面向中小企业", "面向中小微企业"])),
    ("政策条款", "是否为预留份额采购", _boolean_policy_extractor(["预留份额"], ["预留份额"])),
    ("政策条款", "是否允许分包落实中小企业政策", _allowance_extractor(["分包", "中小企业政策"], ["不允许"], ["允许", "可以"])),
    ("政策条款", "所属行业划分", _simple_keyword_extractor(["所属行业"])),
    ("政策条款", "中小企业声明函类型", _declaration_type_extractor),
    ("政策条款", "是否仍保留价格扣除条款", _price_deduction_extractor),
    ("政策条款", "是否涉及进口产品", _boolean_policy_extractor(["进口产品"], ["进口产品"])),
    ("政策条款", "分包比例", _percentage_extractor(["分包比例", "预留比例", "小微企业比例"])),
]

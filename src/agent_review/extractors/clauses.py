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

    if any(
        marker in normalized
        for marker in [
            "付款",
            "验收",
            "违约",
            "解约",
            "质保",
            "履约",
            "安装",
            "调试",
            "团队稳定",
            "人员更换",
            "更换",
            "替换",
        ]
    ):
        return ClauseRole.contract_term

    if any(
        marker in normalized
        for marker in [
            "资格要求",
            "评分",
            "综合评分",
            "评标",
            "分值",
            "业绩",
            "证书",
            "样品",
            "技术要求",
            "商务要求",
            "信用评价",
            "信用分",
            "信用等级",
            "征信",
        ]
    ):
        return ClauseRole.qualification_or_scoring

    if any(marker in normalized for marker in ["不接受联合体", "不允许合同分包", "采购包", "中小企业", "价格扣除", "采购需求", "货物", "服务", "工程"]):
        return ClauseRole.procurement_requirement

    return ClauseRole.unknown


def _simple_keyword_extractor(keywords: list[str], *, exclude_tokens: list[str] | None = None) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if exclude_tokens and any(token in line for token in exclude_tokens):
                continue
            if any(keyword in line for keyword in keywords):
                return _build_clause(line, line_no)
        return None

    return extractor


def _brand_requirement_extractor(lines: list[str]) -> ExtractedClause | None:
    requirement_tokens = ["指定", "限定", "必须", "须", "应", "要求", "采用", "提供"]
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["品牌", "原厂"]):
            continue
        if any(token in line for token in ["相同品牌产品", "同品牌投标人", "同品牌"]):
            continue
        if any(token in line for token in ["原厂服务", "原厂服务团队", "原厂售后"]):
            return _build_clause(line, line_no, normalized_value="存在", relation_tags=["指定品牌/原厂限制"])
        if "原厂正品" in line and not any(token in line for token in ["指定品牌", "指定原厂", "原厂授权", "原厂证明"]):
            continue
        if any(token in line for token in ["声明函", "商标权", "知识产权", "注册商标"]):
            continue
        if not any(token in line for token in requirement_tokens):
            continue
        return _build_clause(line, line_no, normalized_value="存在", relation_tags=["指定品牌/原厂限制"])
    return None


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


def _material_stage_extractor(keywords: list[str]) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if not any(keyword in line for keyword in keywords):
                continue
            relation_tags: list[str] = []
            normalized_value = ""
            if any(token in line for token in ["投标文件", "响应文件", "评审", "评分", "加分", "资格审查", "投标阶段"]):
                normalized_value = "投标阶段"
                relation_tags.append("投标阶段")
            elif any(token in line for token in ["中标后", "供货时", "交货时", "履约", "验收", "验收时", "签约后"]):
                normalized_value = "履约/验收阶段"
                relation_tags.append("履约/验收阶段")
            else:
                normalized_value = "未明确"
                relation_tags.append("未明确阶段")
            return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
        return None

    return extractor


def _material_burden_extractor(lines: list[str]) -> ExtractedClause | None:
    burden_terms = ["检测报告", "认证证书", "管理体系认证", "环境标志", "环保产品认证"]
    requirement_terms = ["需", "须", "必须", "提供", "提交", "具备"]
    matched_lines: list[str] = []
    anchors: list[int] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        matched = [term for term in burden_terms if term in line]
        if not matched:
            continue
        if not any(term in line for term in requirement_terms):
            continue
        anchors.append(line_no)
        matched_lines.append(line[:80])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:320],
        source_anchor=f"line:{anchors[0]}",
        normalized_value=";".join(dict.fromkeys(matched_terms)),
        relation_tags=["材料负担要求", *dict.fromkeys(matched_terms)],
    )


def _scoring_item_details_extractor(lines: list[str]) -> ExtractedClause | None:
    anchors: list[int] = []
    matched_lines: list[str] = []
    relation_tags: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["分", "得分", "评分", "评审"]):
            continue
        if not any(
            token in line
            for token in [
                "实施方案",
                "售后服务方案",
                "资质证书",
                "管理体系认证",
                "检测报告",
                "财务",
                "利润率",
                "项目整体",
                "方案",
            ]
        ):
            continue
        anchors.append(line_no)
        matched_lines.append(line[:120])
        if "实施方案" in line or "项目整体" in line:
            relation_tags.append("实施方案评分项")
        if "售后服务方案" in line or "售后" in line:
            relation_tags.append("售后评分项")
        if "资质证书" in line:
            relation_tags.append("资质证书评分项")
        if "管理体系认证" in line or "认证证书" in line:
            relation_tags.append("认证证书评分项")
        if "检测报告" in line:
            relation_tags.append("检测报告评分项")
        if "财务" in line or "利润率" in line:
            relation_tags.append("财务指标评分项")
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:480],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["评分项明细", *dict.fromkeys(relation_tags)],
    )


def _demand_survey_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if "需求调查" not in line:
            continue
        normalized_value = "未明确"
        relation_tags = ["需求调查结论"]
        if any(token in line for token in ["不需要需求调查", "无需需求调查", "未开展需求调查"]):
            normalized_value = "不需要"
            relation_tags.append("不需要")
        elif any(token in line for token in ["需要需求调查", "应开展需求调查", "已开展需求调查"]):
            normalized_value = "需要"
            relation_tags.append("需要")
        return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
    return None


def _expert_review_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["专家论证", "论证意见", "需求论证"]):
            continue
        normalized_value = "未明确"
        relation_tags = ["专家论证结论"]
        if any(token in line for token in ["不需要", "无需", "未进行", "不组织", "未组织"]):
            normalized_value = "不需要"
            relation_tags.append("不需要")
        elif any(token in line for token in ["需要", "应当", "已组织", "已开展"]):
            normalized_value = "需要"
            relation_tags.append("需要")
        return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
    return None


def _amount_extractor(keywords: list[str]) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if not any(keyword in line for keyword in keywords):
                continue
            normalized_line = line.replace("，", ",")
            candidate_tokens = re.findall(r"\d[\d,]*(?:\.\d+)?", normalized_line)
            normalized_value = ""
            if candidate_tokens:
                # Prefer the longest numeric token to avoid OCR fragments like "268" winning over "2680443.18".
                best = max(candidate_tokens, key=lambda token: (len(token.replace(",", "")), "." in token))
                normalized_value = best.replace(",", "")
            return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=[normalized_value] if normalized_value else [])
        return None

    return extractor


def _contract_type_extractor(lines: list[str]) -> ExtractedClause | None:
    contract_types = ["承揽合同", "买卖合同", "服务合同", "施工合同", "采购合同"]
    # Prefer explicit contract type declarations over generic "政府采购合同" process wording.
    for line_no, line in enumerate(lines, start=1):
        if "合同类型" not in line:
            continue
        for contract_type in contract_types:
            if contract_type in line:
                return _build_clause(line, line_no, normalized_value=contract_type, relation_tags=[contract_type])
    for line_no, line in enumerate(lines, start=1):
        if "是否属于签订不超过3年履行期限政府采购合同的项目" in line:
            continue
        if any(
            token in line
            for token in [
                "销售或服务合同",
                "服务合同复印件",
                "销售合同复印件",
                "政府采购合同",
                "采购合同履约",
                "采购合同复印件",
                "补充合同",
                "签订合同",
                "签订采购合同",
            ]
        ):
            continue
        if "采购合同" in line and "合同类型" not in line:
            continue
        for contract_type in contract_types:
            if contract_type in line:
                return _build_clause(line, line_no, normalized_value=contract_type, relation_tags=[contract_type])
    return None


def _certificate_score_weight_extractor(lines: list[str]) -> ExtractedClause | None:
    total = 0.0
    anchors: list[int] = []
    matched_titles: list[str] = []
    score_pattern = re.compile(r"\((\d+(?:\.\d+)?)分\)")
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["资质证书", "认证情况", "认证证书", "检测报告"]):
            continue
        if not any(token in line for token in ["评分", "评审", "得", "分)"]):
            continue
        match = score_pattern.search(line)
        if not match:
            continue
        total += float(match.group(1))
        anchors.append(line_no)
        matched_titles.append(line[:40])
    if total <= 0:
        return None
    anchor = f"line:{anchors[0]}"
    quote = "；".join(dict.fromkeys(matched_titles))
    return ExtractedClause(
        category="",
        field_name="",
        content=quote[:160],
        source_anchor=anchor,
        normalized_value=f"{total:.1f}",
        relation_tags=["证书类评分总分", f"{total:.1f}分"],
    )


def _credit_evaluation_scoring_extractor(lines: list[str]) -> ExtractedClause | None:
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        if any(token in line for token in ["信用中国", "企业信用信息公示系统", "失信被执行人"]):
            continue
        matched = [term for term in ["信用评价", "信用分", "信用等级", "信用评分", "征信"] if term in line]
        if not matched:
            continue
        if not any(token in line for token in ["分", "评分", "评审", "加分", "得分"]):
            continue
        anchors.append(line_no)
        matched_lines.append(line[:120])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:320],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["信用评价评分项", *dict.fromkeys(matched_terms)],
    )


def _service_content_extractor(lines: list[str]) -> ExtractedClause | None:
    service_terms = [
        "人工管护",
        "清林整地",
        "栽植",
        "连续三年施肥",
        "施肥",
        "幼林抚育",
        "成林管护",
        "机械运水",
        "抚育",
        "管护",
        "运水",
    ]
    for line_no, line in enumerate(lines, start=1):
        matched = [term for term in service_terms if term in line]
        if not matched:
            continue
        relation_tags = ["持续性作业服务", *matched[:5]]
        return _build_clause(line, line_no, normalized_value="是", relation_tags=relation_tags)
    return None


def _industry_mismatch_scoring_extractor(lines: list[str]) -> ExtractedClause | None:
    mismatch_terms = ["软件企业认定证书", "ITSS", "运行维护服务证书", "利润率", "财务报告"]
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        matched = [term for term in mismatch_terms if term in line]
        if not matched:
            continue
        if not any(token in line for token in ["分", "评分", "评审", "得分", "证书", "财务报告", "利润率"]):
            continue
        anchors.append(line_no)
        matched_lines.append(line[:80])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:320],
        source_anchor=f"line:{anchors[0]}",
        normalized_value=";".join(dict.fromkeys(matched_terms)),
        relation_tags=["行业相关性存疑评分项", *dict.fromkeys(matched_terms)],
    )


def _plan_scoring_quant_extractor(lines: list[str]) -> ExtractedClause | None:
    keywords = ["无缺陷得满分", "每缺项扣", "每处缺陷扣", "缺陷扣", "扣2.5分", "缺项扣分", "完全满足且优于", "完全满足项目要求", "不完全满足项目要求"]
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        matched = [token for token in keywords if token in line]
        if not matched:
            continue
        anchors.append(line_no)
        matched_lines.append(line[:100])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:400],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["方案量化不足", *dict.fromkeys(matched_terms)],
    )


def _team_stability_requirement_extractor(lines: list[str]) -> ExtractedClause | None:
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        matched = [term for term in ["团队稳定", "核心团队", "人员稳定", "稳定性", "团队成员"] if term in line]
        if not matched:
            continue
        if not any(token in line for token in ["要求", "不得", "保持", "稳定", "更换", "人员"]):
            continue
        anchors.append(line_no)
        matched_lines.append(line[:120])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return _build_clause(
        "；".join(dict.fromkeys(matched_lines))[:320],
        anchors[0],
        normalized_value="存在",
        relation_tags=["团队稳定性要求", *dict.fromkeys(matched_terms)],
    )


def _personnel_change_limit_extractor(lines: list[str]) -> ExtractedClause | None:
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["更换", "替换", "变更", "调整", "撤换"]):
            continue
        if not any(
            token in line
            for token in [
                "人员",
                "岗位",
                "团队",
                "项目负责人",
                "采购人同意",
                "采购人批准",
                "须经采购人",
                "不得更换",
                "未经采购人同意",
            ]
        ):
            continue
        matched = [term for term in ["更换", "替换", "变更", "调整", "撤换", "采购人同意", "采购人批准"] if term in line]
        anchors.append(line_no)
        matched_lines.append(line[:120])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return _build_clause(
        "；".join(dict.fromkeys(matched_lines))[:320],
        anchors[0],
        normalized_value="存在",
        relation_tags=["人员更换限制", *dict.fromkeys(matched_terms)],
    )


def _contract_result_template_extractor(lines: list[str]) -> ExtractedClause | None:
    keywords = [
        "项目成果",
        "成果交付",
        "成果保密",
        "移作他用",
        "泄露本项目成果",
        "提交全部符合项目合同要求的项目成果",
    ]
    for line_no, line in enumerate(lines, start=1):
        matched = [token for token in keywords if token in line]
        if not matched:
            continue
        return _build_clause(
            line,
            line_no,
            normalized_value="存在",
            relation_tags=["成果模板术语", *matched],
        )
    return None


def _contract_template_residue_extractor(lines: list[str]) -> ExtractedClause | None:
    keywords = ["X年", "事件发生后天内", "设计、测试、验收", "设计、测试", "免费质保服务", "于事件发生后"]
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        matched = [token for token in keywords if token in line]
        if not matched:
            continue
        anchors.append(line_no)
        matched_lines.append(line[:160])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:320],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["合同模板残留", *dict.fromkeys(matched_terms)],
    )


def _flexible_acceptance_extractor(lines: list[str]) -> ExtractedClause | None:
    keywords = ["优胜的原则", "由采购人按", "确定验收标准", "比较优胜"]
    for line_no, line in enumerate(lines, start=1):
        matched = [token for token in keywords if token in line]
        if not matched:
            continue
        return _build_clause(
            line,
            line_no,
            normalized_value="存在",
            relation_tags=["验收弹性条款", *matched],
        )
    return None


def _deduction_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["扣款", "扣罚", "罚款"]):
            continue
        if any(token in line for token in ["较大数额罚款", "行政处罚", "经营活动", "刑事处罚"]):
            continue
        return _build_clause(line, line_no, normalized_value="存在", relation_tags=["扣款机制"])
    return None


def _patent_requirement_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if "专利" not in line:
            continue
        relation_tags = ["专利要求"]
        normalized_value = "存在"
        strong_gate = any(token in line for token in ["必须具备", "须具备", "应具备", "必须具有", "须具有"])
        if strong_gate:
            normalized_value = "刚性门槛"
            relation_tags.append("刚性门槛")
        elif any(token in line for token in ["专利权", "知识产权", "侵犯", "纠纷", "不会产生"]):
            continue
        return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
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
            if not any(keyword in line for keyword in keywords):
                continue
            if any(token in line for token in ["法定代表人", "身份证号码", "退休年龄", "参保", "保险", "联合体形式投标"]):
                continue
            if normalized_value == "存在" and relation_tags:
                if "采购人审批录用" in relation_tags and not any(token in line for token in ["录用", "聘用", "上岗", "应聘"]):
                    continue
                if "容貌体形要求" in relation_tags:
                    if "联合体形式" in line or "联合体" in line:
                        continue
                    if not any(token in line for token in ["容貌", "体形", "五官", "仪容", "端庄"]):
                        continue
                if "采购人批准更换" in relation_tags and not any(token in line for token in ["更换", "替换", "变更", "调整"]):
                    continue
                return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags or [])
        return None

    return extractor


def _origin_brand_restriction_extractor(lines: list[str]) -> ExtractedClause | None:
    requirement_tokens = ["指定", "限定", "采用", "必须", "应当", "要求", "提供"]
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["产地", "厂家", "商标", "品牌", "原厂"]):
            continue
        if any(token in line for token in ["原产地证明", "进口设备", "相同品牌产品", "同品牌投标人", "同品牌"]):
            continue
        if any(token in line for token in ["商标权", "知识产权", "声明函", "残疾人福利性单位", "注册商标", "不会产生", "侵权", "厂家出厂标准", "原厂正品"]):
            continue
        if not any(token in line for token in requirement_tokens):
            continue
        return _build_clause(line, line_no, normalized_value="存在", relation_tags=["限制产地厂家商标"])
    return None


def _age_restriction_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["岁以下", "岁以上", "年龄"]):
            continue
        if any(token in line for token in ["法定代表人", "身份证号码", "退休年龄", "参保", "保险"]):
            continue
        if "年龄" in line and not any(token in line for token in ["岁以下", "岁以上", "年龄要求", "限", "不得超过"]):
            continue
        return _build_clause(line, line_no, normalized_value="存在", relation_tags=["年龄限制"])
    return None


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
    ("项目基本信息", "预算金额", _amount_extractor(["预算金额"])),
    ("项目基本信息", "最高限价", _amount_extractor(["最高限价"])),
    ("项目基本信息", "合同履行期限", _simple_keyword_extractor(["合同履行期限"])),
    ("项目基本信息", "合同类型", _contract_type_extractor),
    ("项目基本信息", "采购内容构成", _service_content_extractor),
    ("项目基本信息", "是否含持续性服务", _service_content_extractor),
    ("项目基本信息", "需求调查结论", _demand_survey_extractor),
    ("项目基本信息", "专家论证结论", _expert_review_extractor),
    ("资格条款", "一般资格要求", _simple_keyword_extractor(["资格要求", "供应商资格"])),
    ("资格条款", "特定资格要求", _simple_keyword_extractor(["特定资格要求", "资质要求"])),
    ("资格条款", "信用要求", _simple_keyword_extractor(["信用要求"])),
    ("资格条款", "是否允许联合体", _allowance_extractor(["联合体"], ["不接受联合体", "不允许联合体"], ["允许联合体", "接受联合体"])),
    ("资格条款", "是否允许分包", _allowance_extractor(["分包"], ["不允许合同分包", "不得分包", "不允许分包"], ["允许分包", "可以分包"])),
    ("技术条款", "样品要求", _simple_keyword_extractor(["样品"])),
    ("技术条款", "现场演示要求", _simple_keyword_extractor(["演示"])),
    ("技术条款", "是否指定品牌", _brand_requirement_extractor),
    ("技术条款", "是否要求专利", _patent_requirement_extractor),
    ("技术条款", "是否要求检测报告", _simple_keyword_extractor(["检测报告"])),
    ("技术条款", "是否要求认证证书", _simple_keyword_extractor(["认证证书", "证书"])),
    ("技术条款", "证书检测报告负担特征", _material_burden_extractor),
    ("技术条款", "检测报告适用阶段", _material_stage_extractor(["检测报告"])),
    ("技术条款", "证书材料适用阶段", _material_stage_extractor(["认证证书", "证书"])),
    ("技术条款", "是否设置★实质性条款", _simple_keyword_extractor(["★"])),
    ("技术条款", "是否有限制产地厂家商标", _origin_brand_restriction_extractor),
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
    ("评分条款", "评分项明细", _scoring_item_details_extractor),
    ("评分条款", "证书类评分总分", _certificate_score_weight_extractor),
    ("评分条款", "信用评价要求", _credit_evaluation_scoring_extractor),
    ("评分条款", "行业相关性存疑评分项", _industry_mismatch_scoring_extractor),
    ("评分条款", "方案评分扣分模式", _plan_scoring_quant_extractor),
    ("合同条款", "付款节点", _payment_extractor),
    ("合同条款", "验收标准", _acceptance_extractor),
    ("合同条款", "争议解决方式", _simple_keyword_extractor(["争议解决"])),
    ("合同条款", "违约责任", _simple_keyword_extractor(["违约责任"])),
    ("合同条款", "质保期", _simple_keyword_extractor(["质保期"])),
    ("合同条款", "履约保证金", _simple_keyword_extractor(["履约保证金"])),
    ("合同条款", "考核条款", _assessment_extractor),
    ("合同条款", "扣款条款", _deduction_extractor),
    ("合同条款", "解约条款", _simple_keyword_extractor(["解约", "解除合同"])),
    ("合同条款", "单方解释权", _simple_keyword_extractor(["解释权", "以采购人意见为准", "以采购人解释为准"])),
    ("合同条款", "合同成果模板术语", _contract_result_template_extractor),
    ("合同条款", "合同模板残留", _contract_template_residue_extractor),
    ("合同条款", "验收弹性条款", _flexible_acceptance_extractor),
    ("人员条款", "性别限制", _personnel_line_extractor(["男性", "女性", "限女性", "限男性"], "存在", ["性别限制"])),
    ("人员条款", "年龄限制", _age_restriction_extractor),
    ("人员条款", "身高限制", _personnel_line_extractor(["身高"], "存在", ["身高限制"])),
    ("人员条款", "容貌体形要求", _personnel_line_extractor(["容貌", "体形", "五官端正"], "存在", ["容貌体形要求"])),
    ("人员条款", "学历职称要求", _personnel_line_extractor(["学历", "职称"], "存在", ["学历职称要求"])),
    ("人员条款", "采购人审批录用", _personnel_line_extractor(["批准录用", "录用审批", "录用须经采购人审批", "聘用须经采购人审批"], "存在", ["采购人审批录用"])),
    ("人员条款", "采购人批准更换", _personnel_line_extractor(["批准更换", "人员更换须经采购人同意"], "存在", ["采购人批准更换"])),
    ("人员条款", "团队稳定性要求", _team_stability_requirement_extractor),
    ("人员条款", "人员更换限制", _personnel_change_limit_extractor),
    ("人员条款", "采购人直接指挥", _personnel_line_extractor(["采购人有权直接指挥", "服从采购人安排"], "存在", ["采购人直接指挥"])),
    ("政策条款", "是否专门面向中小企业", _boolean_policy_extractor(["专门面向中小企业", "中小微企业采购"], ["专门面向中小企业", "面向中小微企业"])),
    ("政策条款", "是否为预留份额采购", _boolean_policy_extractor(["预留份额"], ["预留份额"])),
    ("政策条款", "是否允许分包落实中小企业政策", _allowance_extractor(["分包", "中小企业政策"], ["不允许"], ["允许", "可以"])),
    ("政策条款", "所属行业划分", _simple_keyword_extractor(["所属行业"])),
    ("政策条款", "中小企业声明函类型", _declaration_type_extractor),
    ("政策条款", "是否仍保留价格扣除条款", _price_deduction_extractor),
    ("政策条款", "是否涉及进口产品", _boolean_policy_extractor(["进口产品"], ["进口产品"])),
    ("政策条款", "分包比例", _percentage_extractor(["分包比例", "预留比例", "小微企业比例"])),
    ("政策条款", "面向中小企业采购金额", _amount_extractor(["面向中小企业采购金额"])),
]

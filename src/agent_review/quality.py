from __future__ import annotations

import re

from .models import ClauseRole, ConclusionLevel, ExtractedClause, Finding, FindingType, Severity


def derive_conclusion_by_evidence(
    findings: list[Finding],
    report_text: str,
    extracted_clauses: list[ExtractedClause],
) -> ConclusionLevel:
    qualified_high = _dedupe_qualified_high_findings(findings, report_text, extracted_clauses)
    qualified_confirmed = [
        item for item in qualified_high if item.finding_type == FindingType.confirmed_issue
    ]
    raw_high_count = sum(1 for item in findings if item.severity in {Severity.high, Severity.critical})

    if any(item.severity == Severity.critical for item in qualified_high):
        return ConclusionLevel.reject
    if len(qualified_confirmed) >= 2:
        return ConclusionLevel.reject
    if qualified_high:
        return ConclusionLevel.revise
    if any(
        item.finding_type in {FindingType.warning, FindingType.manual_review_required, FindingType.missing_evidence}
        for item in findings
    ):
        return ConclusionLevel.optimize
    if raw_high_count >= 1:
        return ConclusionLevel.optimize
    return ConclusionLevel.ready


def _dedupe_qualified_high_findings(
    findings: list[Finding],
    report_text: str,
    extracted_clauses: list[ExtractedClause],
) -> list[Finding]:
    results: list[Finding] = []
    seen: set[str] = set()
    for item in findings:
        if item.severity not in {Severity.high, Severity.critical}:
            continue
        if not is_formal_eligible(item, report_text, extracted_clauses):
            continue
        section_hint, quote = resolve_formal_evidence(report_text, item)
        key = f"{section_hint}|{quote}"
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def is_formal_eligible(
    finding: Finding,
    report_text: str,
    extracted_clauses: list[ExtractedClause],
) -> bool:
    if not finding.evidence:
        return False

    section_hint, quote = resolve_formal_evidence(report_text, finding)
    if section_hint in {"未明确定位", "keyword_match", "restrictive_term"}:
        return False
    if not quote or quote == "当前自动抽取未定位到可直接引用的原文。":
        return False

    roles = infer_evidence_roles(report_text, extracted_clauses, finding)
    if roles and all(
        role in {
            ClauseRole.form_template,
            ClauseRole.policy_explanation,
            ClauseRole.document_definition,
            ClauseRole.appendix_reference,
            ClauseRole.unknown,
        }
        for role in roles
    ):
        return False

    if not evidence_supports_title(finding.title, quote):
        return False

    return True


def resolve_formal_evidence(report_text: str, finding: Finding) -> tuple[str, str]:
    section_hint = "；".join(item.section_hint for item in finding.evidence if item.section_hint) or "未明确定位"
    raw_quote = "；".join(item.quote for item in finding.evidence if item.quote).strip()

    if not finding.evidence:
        return section_hint, "当前自动抽取未定位到可直接引用的原文。"

    primary_hint = finding.evidence[0].section_hint if finding.evidence else ""
    line_quote = clause_window_from_anchor(report_text, primary_hint)
    if raw_quote and " / " in raw_quote:
        parts = [part.strip() for part in raw_quote.split("/") if part.strip()]
        supplemental = []
        for part in parts:
            matched = search_line_by_keyword(report_text, part, prefer_window=True)
            if matched:
                supplemental.append(matched)
        if line_quote:
            supplemental.insert(0, line_quote)
        if supplemental:
            return section_hint, "；".join(dict.fromkeys(supplemental))

    if line_quote:
        return section_hint, line_quote
    if raw_quote:
        return section_hint, raw_quote
    return section_hint, "当前自动抽取未定位到可直接引用的原文。"


def infer_evidence_roles(
    report_text: str,
    extracted_clauses: list[ExtractedClause],
    finding: Finding,
) -> list[ClauseRole]:
    roles: list[ClauseRole] = []
    for evidence in finding.evidence:
        matched_roles = [
            clause.clause_role
            for clause in extracted_clauses
            if clause.source_anchor == evidence.section_hint or clause.content == evidence.quote
        ]
        roles.extend(matched_roles)
        if not matched_roles:
            inferred = infer_role_from_text(evidence.quote)
            if inferred != ClauseRole.unknown:
                roles.append(inferred)
    return roles


def infer_role_from_text(text: str) -> ClauseRole:
    normalized = text.strip()
    if not normalized:
        return ClauseRole.unknown
    if any(marker in normalized for marker in ["声明函", "证明书", "单位名称（盖章）", "法定代表人", "____"]):
        return ClauseRole.form_template
    if any(marker in normalized for marker in ["采购代理机构：", "采购人：", "投标人：", "名词解释"]):
        return ClauseRole.document_definition
    if "附件" in normalized or "附表" in normalized:
        return ClauseRole.appendix_reference
    if any(marker in normalized for marker in ["根据《", "管理办法", "通知》", "实施条例"]):
        return ClauseRole.policy_explanation
    return ClauseRole.unknown


def evidence_supports_title(title: str, quote: str) -> bool:
    checks = {
        "性别限制": [["性别", "男性", "女性"]],
        "年龄限制": [["年龄", "岁以下", "岁以上"]],
        "身高限制": [["身高"]],
        "容貌体形要求": [["容貌", "体形", "五官"]],
        "团队稳定性要求过强": [["团队稳定", "核心团队", "人员稳定", "团队成员"], ["不得", "保持", "稳定", "更换", "要求"]],
        "人员更换限制较强": [["人员更换", "更换", "替换", "变更", "调整"], ["采购人同意", "采购人批准", "须经", "不得更换", "未经采购人同意"]],
        "产地厂家商标限制": [["产地", "厂家", "商标", "品牌", "原厂"]],
        "刚性门槛型专利要求": [["专利", "是否要求专利"], ["必须具备", "须具备", "应具备", "必须具有", "刚性门槛"]],
        "投标阶段证书或检测报告负担过重": [["检测报告", "认证证书", "管理体系认证"], ["提供", "提交", "具备", "评分", "评审"]],
        "证书类评分分值偏高": [["资质证书", "管理体系认证", "认证证书", "证书类评分总分"], ["分"]],
        "信用评价作为评分因素": [["信用评价", "信用分", "征信"], ["评分", "得分", "分"]],
        "评分项与采购标的不相关": [["利润率", "软件企业认定证书", "ITSS", "财务报告", "信用评价"]],
        "方案评分主观性过强，量化不足": [["无缺陷", "完全满足且优于", "不完全满足", "缺陷", "扣分"]],
        "合同文本存在明显模板残留": [["X年", "事件发生后", "设计、测试", "免费质保服务"]],
        "合同条款存在明显模板错配": [["项目成果", "研究成果", "技术文档", "移作他用", "泄露本项目成果"]],
        "验收标准表述过于弹性": [["优胜的原则", "比较优胜", "确定该项的约定标准"]],
        "货物保修表述与项目实际履约内容不匹配": [["货物质保期", "质量保修范围和保修期"], ["人工管护", "1095日", "抚育", "运水"]],
        "中小企业采购金额口径不一致": [["预算金额"], ["面向中小企业采购金额"], ["最高限价"]],
        "项目属性与采购内容、合同类型不一致": [["项目所属分类", "项目属性", "货物"], ["人工管护", "清林整地", "抚育", "运水", "持续性作业"], ["合同类型", "承揽合同"]],
        "货物服务属性冲突": [["货物"], ["服务", "实施", "运维", "承接"]],
        "货物项目混入大量服务履约内容": [["货物"], ["服务", "实施", "运维", "承接"]],
        "项目属性 vs 履约内容": [["货物"], ["服务", "实施", "运维", "承接"]],
        "项目属性与所属行业口径疑似不一致": [["行业", "工业"], ["服务", "工程", "声明函", "错配", "不一致"]],
        "项目属性与声明函模板口径冲突": [["声明函", "制造商", "货物", "服务"], ["错配", "冲突", "不一致"]],
        "专门面向中小企业却仍保留价格扣除": [["中小企业"], ["价格扣除"]],
        "专门面向中小企业却保留价格扣除模板": [["中小企业"], ["价格扣除"]],
        "中小企业政策 vs 价格扣除政策": [["中小企业"], ["价格扣除"]],
        "验收标准 vs 付款条件": [["验收"], ["付款", "支付", "尾款"]],
        "采购人单方解释或决定条款": [["解释权", "采购人意见", "采购人解释", "采购人说了算"]],
    }
    groups = checks.get(title)
    if not groups:
        return True
    if title == "年龄限制" and any(token in quote for token in ["退休年龄", "参保", "保险", "法定代表人", "身份证号码"]):
        return False
    if title == "产地厂家商标限制" and any(token in quote for token in ["商标权", "知识产权", "声明函", "残疾人福利性单位", "注册商标", "不会产生", "侵权"]):
        return False
    if title == "产地厂家商标限制" and any(token in quote for token in ["厂家出厂标准", "原厂正品", "原产地证明", "进口设备"]):
        return False
    if title == "指定品牌/原厂限制" and any(token in quote for token in ["相同品牌产品", "同品牌投标人"]):
        return False
    if title == "专利要求" and any(token in quote for token in ["专利权", "知识产权", "侵犯", "纠纷", "不会产生"]):
        return False
    if title in {"团队稳定性要求过强", "人员更换限制较强"} and any(
        token in quote for token in ["项目名称", "采购单位", "预算金额", "联合体", "项目概况", "不分包采购"]
    ):
        return False
    if title == "刚性门槛型专利要求" and any(token in quote for token in ["专利权", "知识产权", "侵犯", "纠纷", "不会产生"]):
        if not any(token in quote for token in ["必须具备", "须具备", "应具备", "必须具有", "刚性门槛"]):
            return False
    if title == "投标阶段证书或检测报告负担过重" and all(token not in quote for token in ["检测报告", "认证证书", "管理体系认证", "证书检测报告负担特征"]):
        return False
    if title == "证书类评分分值偏高" and "证书类评分总分=" in quote:
        return True
    if title == "刚性门槛型专利要求" and "是否要求专利=刚性门槛" in quote:
        return True
    if title == "项目属性与合同类型口径疑似不一致" and "合同类型=采购合同" in quote:
        return False
    if title == "项目属性与声明函模板口径冲突" and all(
        token not in quote for token in ["声明函", "制造商", "货物", "服务", "模板"]
    ):
        return False
    if title == "验收标准 vs 付款条件" and all(
        token not in quote for token in ["验收", "付款", "支付", "尾款"]
    ):
        return False
    if title == "采购人单方解释或决定条款" and "采购代理机构" in quote:
        return False
    return all(any(token in quote for token in group) for group in groups)


def line_text_from_anchor(text: str, anchor: str) -> str:
    match = re.match(r"line:(\d+)", anchor or "")
    if not match:
        return ""
    line_no = int(match.group(1))
    lines = text.splitlines()
    if 1 <= line_no <= len(lines):
        return lines[line_no - 1].strip()
    return ""


def clause_window_from_anchor(text: str, anchor: str, before: int = 1, after: int = 4) -> str:
    match = re.match(r"line:(\d+)", anchor or "")
    if not match:
        return ""
    line_no = int(match.group(1))
    lines = text.splitlines()
    if not (1 <= line_no <= len(lines)):
        return ""

    index = line_no - 1
    start = index
    end = index

    current = lines[index].strip()
    if _looks_like_fragment_start(current):
        while start > 0:
            candidate = lines[start - 1].strip()
            if not candidate:
                break
            start -= 1
            if _looks_like_clause_boundary(candidate) or len(candidate) >= 20:
                break
        start = max(0, start - before + 1)

    while end + 1 < len(lines) and end - start < after:
        next_line = lines[end + 1].strip()
        if not next_line:
            break
        if _is_clause_complete(lines[end].strip()) and _looks_like_clause_boundary(next_line):
            break
        end += 1
        if _is_clause_complete(lines[end].strip()) and len(_join_clause_lines(lines[start : end + 1])) >= 28:
            break

    window = _join_clause_lines(lines[start : end + 1])
    return window or current


def search_line_by_keyword(text: str, keyword: str, prefer_window: bool = False) -> str:
    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        if keyword and keyword in line:
            if prefer_window:
                return clause_window_from_anchor(text, f"line:{idx}")
            return line.strip()
    return ""


def _looks_like_fragment_start(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) <= 12:
        return True
    return stripped[0] in {"的", "及", "、", "（", "(", ",", "，", "）", ")", "须", "由"}


def _looks_like_clause_boundary(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return bool(
        re.match(r"^(\d+[\.\、\)]|[一二三四五六七八九十]+[、\)]|[（(]?\d+[）)].*|[A-Za-z]+\d*[\.\)]|第.+[章节条款])", stripped)
    )


def _is_clause_complete(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return stripped.endswith(("。", "；", "!", "！", "?", "？", "：", ":", "）", ")"))


def _join_clause_lines(lines: list[str]) -> str:
    parts = [item.strip() for item in lines if item.strip()]
    if not parts:
        return ""
    text = "".join(parts)
    text = re.sub(r"\s+", " ", text).strip()
    return text

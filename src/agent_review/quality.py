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
    line_quote = line_text_from_anchor(report_text, primary_hint)
    if raw_quote and " / " in raw_quote:
        parts = [part.strip() for part in raw_quote.split("/") if part.strip()]
        supplemental = []
        for part in parts:
            matched = search_line_by_keyword(report_text, part)
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
        "产地厂家商标限制": [["产地", "厂家", "商标", "品牌", "原厂"]],
        "刚性门槛型专利要求": [["专利"], ["必须具备", "须具备", "应具备", "必须具有"]],
        "投标阶段证书或检测报告负担过重": [["检测报告", "认证证书", "管理体系认证"], ["提供", "提交", "具备", "评分", "评审"]],
        "证书类评分分值偏高": [["资质证书", "管理体系认证", "认证证书"], ["分"]],
        "合同文本存在明显模板残留": [["X年", "事件发生后", "设计、测试", "免费质保服务"]],
        "货物服务属性冲突": [["货物"], ["服务", "实施", "运维", "承接"]],
        "货物项目混入大量服务履约内容": [["货物"], ["服务", "实施", "运维", "承接"]],
        "项目属性 vs 履约内容": [["货物"], ["服务", "实施", "运维", "承接"]],
        "专门面向中小企业却仍保留价格扣除": [["中小企业"], ["价格扣除"]],
        "专门面向中小企业却保留价格扣除模板": [["中小企业"], ["价格扣除"]],
        "中小企业政策 vs 价格扣除政策": [["中小企业"], ["价格扣除"]],
        "采购人单方解释或决定条款": [["解释权", "采购人意见", "采购人解释", "采购人说了算"]],
    }
    groups = checks.get(title)
    if not groups:
        return True
    if title == "年龄限制" and any(token in quote for token in ["退休年龄", "参保", "保险", "法定代表人", "身份证号码"]):
        return False
    if title == "产地厂家商标限制" and any(token in quote for token in ["商标权", "知识产权", "声明函", "残疾人福利性单位", "注册商标", "不会产生", "侵权"]):
        return False
    if title == "产地厂家商标限制" and any(token in quote for token in ["厂家出厂标准", "原厂正品"]):
        return False
    if title == "专利要求" and any(token in quote for token in ["专利权", "知识产权", "侵犯", "纠纷", "不会产生"]):
        return False
    if title == "刚性门槛型专利要求" and any(token in quote for token in ["专利权", "知识产权", "侵犯", "纠纷", "不会产生"]):
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


def search_line_by_keyword(text: str, keyword: str) -> str:
    for line in text.splitlines():
        if keyword and keyword in line:
            return line.strip()
    return ""

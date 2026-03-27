from __future__ import annotations

from typing import Iterable

from ..models import (
    ConclusionLevel,
    ConsistencyCheck,
    ExtractedClause,
    Finding,
    FindingType,
    SectionIndex,
    Severity,
    SourceDocument,
)
from ..parser_engine import detect_file_type


def check_consistency(
    text: str,
    clauses: list[ExtractedClause] | None = None,
    source_documents: list[SourceDocument] | None = None,
) -> list[ConsistencyCheck]:
    mapping = _clause_map(clauses or [])
    project_type = _first_content(mapping, "项目属性")
    category_name = _first_content(mapping, "品目名称")
    industry = _first_content(mapping, "所属行业划分")
    statement_type = _first_content(mapping, "中小企业声明函类型")

    checks: list[ConsistencyCheck] = []
    checks.append(
        ConsistencyCheck(
            topic="项目属性 vs 履约内容",
            status="issue" if ("货物" in project_type and ("运维" in text or "实施" in text)) else "ok",
            detail=(
                "文本同时出现货物属性与运维/实施服务内容，需核查项目属性定性。"
                if ("货物" in project_type and ("运维" in text or "实施" in text))
                else "未发现明显属性与履约内容冲突。"
            ),
        )
    )
    checks.append(
        ConsistencyCheck(
            topic="项目属性 vs 品目名称",
            status="issue" if ("服务" in project_type and "家具" in category_name) else "ok",
            detail="项目属性与品目名称疑似不一致，需核查项目结构是否存在货物/服务混用。"
            if ("服务" in project_type and "家具" in category_name)
            else "项目属性与品目名称未见明显冲突。",
        )
    )
    checks.append(
        ConsistencyCheck(
            topic="项目属性 vs 所属行业",
            status="issue" if ("服务" in project_type and "工业" in industry) else "ok",
            detail="服务项目中出现工业等疑似货物类行业口径，需复核所属行业填写。"
            if ("服务" in project_type and "工业" in industry)
            else "项目属性与所属行业未见明显冲突。",
        )
    )
    checks.append(
        ConsistencyCheck(
            topic="项目属性 vs 中小企业声明函",
            status="issue" if ("服务" in project_type and "制造商" in statement_type) else "ok",
            detail="服务项目与中小企业声明函中的制造商口径不一致，可能存在模板混用。"
            if ("服务" in project_type and "制造商" in statement_type)
            else "项目属性与中小企业声明函未见明显冲突。",
        )
    )
    checks.append(
        ConsistencyCheck(
            topic="预算金额 vs 最高限价",
            status="issue" if ("最高限价" in text and "预算金额" not in text) else "ok",
            detail="出现最高限价但未发现预算金额，建议复核金额口径一致性。"
            if ("最高限价" in text and "预算金额" not in text)
            else "预算与限价未见明显冲突。",
        )
    )
    checks.append(
        ConsistencyCheck(
            topic="中小企业政策 vs 价格扣除政策",
            status="issue" if _project_bound_policy_conflict(mapping) else "ok",
            detail="专门面向中小企业项目仍出现价格扣除条款，可能存在政策口径冲突。"
            if _project_bound_policy_conflict(mapping)
            else "未发现明显中小企业政策冲突。",
        )
    )
    checks.append(
        ConsistencyCheck(
            topic="技术要求 vs 评分标准",
            status="issue" if ("综合评分" in text and "技术要求" not in text) else "ok",
            detail="出现综合评分，但技术要求定位不足，需核查评分依据。"
            if ("综合评分" in text and "技术要求" not in text)
            else "技术要求与评分标准未见明显脱节。",
        )
    )
    checks.append(
        ConsistencyCheck(
            topic="评分标准 vs 合同要求",
            status="issue" if ("评分" in text and "考核" in text and "合同" in text) else "ok",
            detail="评分标准与合同考核要求同时出现，需核查是否将主观考核逻辑前置或后置叠加。"
            if ("评分" in text and "考核" in text and "合同" in text)
            else "评分标准与合同要求未见明显冲突。",
        )
    )
    checks.append(
        ConsistencyCheck(
            topic="验收标准 vs 付款条件",
            status="issue" if ("验收" in text and ("满意" in text or "考核" in text) and ("付款" in text or "支付" in text)) else "ok",
            detail="验收与付款条件联动中含有满意度或考核口径，需核查是否存在主观控制付款风险。"
            if ("验收" in text and ("满意" in text or "考核" in text) and ("付款" in text or "支付" in text))
            else "验收标准与付款条件未见明显冲突。",
        )
    )
    checks.append(
        ConsistencyCheck(
            topic="中小企业政策 vs 分包条款",
            status="issue" if ("专门面向中小企业" in text and "分包" in text and "价格扣除" in text) else "ok",
            detail="中小企业政策、分包条款与价格扣除模板并存，需复核政策执行口径是否自洽。"
            if ("专门面向中小企业" in text and "分包" in text and "价格扣除" in text)
            else "中小企业政策与分包条款未见明显冲突。",
        )
    )
    checks.append(
        ConsistencyCheck(
            topic="服务要求 vs 人员评分要求",
            status="issue" if ("服务" in project_type and ("学历" in text or "职称" in text) and "评分" in text) else "ok",
            detail="服务项目中存在学历、职称等人员评分要求，需核查其与实际履职是否直接相关。"
            if ("服务" in project_type and ("学历" in text or "职称" in text) and "评分" in text)
            else "服务要求与人员评分要求未见明显冲突。",
        )
    )
    checks.append(
        ConsistencyCheck(
            topic="联合体/分包条款前后一致性",
            status="issue" if ("联合体" in text and "分包" in text and "不得" in text and "允许" in text) else "ok",
            detail="联合体与分包条款中出现允许/禁止混用，需要人工核对前后文。"
            if ("联合体" in text and "分包" in text and "不得" in text and "允许" in text)
            else "未发现明显联合体/分包条款冲突。",
        )
    )
    checks.extend(_check_cross_document_consistency(text, source_documents or []))
    return checks


def convert_consistency_checks_to_findings(
    checks: Iterable[ConsistencyCheck],
) -> list[Finding]:
    results: list[Finding] = []
    for check in checks:
        if check.status != "issue":
            continue
        results.append(
            Finding(
                dimension="跨条款一致性检查",
                finding_type=FindingType.warning,
                severity=Severity.high,
                title=check.topic,
                rationale=check.detail,
                evidence=[],
                legal_basis=check.legal_basis,
                confidence=0.74,
                next_action="核查相关章节并统一项目属性、金额口径、政策口径或合同表述。",
            )
        )
    return results


def collect_relative_strengths(
    section_index: list[SectionIndex], findings: list[Finding]
) -> list[str]:
    strengths: list[str] = []
    located_count = sum(1 for item in section_index if item.located)
    if located_count >= 4:
        strengths.append("关键章节已有一定覆盖，便于后续复核。")
    if not any(item.finding_type == FindingType.confirmed_issue for item in findings):
        strengths.append("当前文本未命中明确的实质性不合规强信号。")
    if not strengths:
        strengths.append("已形成结构化问题清单，便于采购人定向修改。")
    return strengths


def derive_conclusion(findings: list[Finding]) -> ConclusionLevel:
    high_count = sum(1 for item in findings if item.severity in {Severity.high, Severity.critical})
    confirmed_count = sum(1 for item in findings if item.finding_type == FindingType.confirmed_issue)
    if confirmed_count >= 3 or any(item.severity == Severity.critical for item in findings):
        return ConclusionLevel.reject
    if high_count >= 2:
        return ConclusionLevel.revise
    if any(
        item.finding_type in {FindingType.warning, FindingType.manual_review_required, FindingType.missing_evidence}
        for item in findings
    ):
        return ConclusionLevel.optimize
    return ConclusionLevel.ready


def _check_cross_document_consistency(
    text: str,
    source_documents: list[SourceDocument],
) -> list[ConsistencyCheck]:
    if len(source_documents) <= 1:
        return []

    snippets = _split_document_snippets(text)
    roles = {
        item.document_name: detect_file_type(snippets.get(item.document_name, ""))
        for item in source_documents
    }
    tender_docs = [
        name
        for name, role in roles.items()
        if role.value in {"完整招标文件", "混合型文件", "未知类型", "采购需求文件"}
    ]
    scoring_docs = [name for name, role in roles.items() if role.value == "评分细则文件"]
    contract_docs = [name for name, role in roles.items() if role.value == "合同草案"]

    checks: list[ConsistencyCheck] = []
    for tender_doc in tender_docs:
        tender_text = snippets.get(tender_doc, "")
        for scoring_doc in scoring_docs:
            scoring_text = snippets.get(scoring_doc, "")
            issue = ("专门面向中小企业" in tender_text and "价格扣除" in scoring_text) or (
                "评分" in scoring_text and "技术要求" not in tender_text
            )
            checks.append(
                ConsistencyCheck(
                    topic="正文 vs 评分细则跨文件一致性",
                    status="issue" if issue else "ok",
                    detail=(
                        f"《{tender_doc}》与《{scoring_doc}》之间存在政策口径或评分依据不一致，需核查正文与评分细则是否同步更新。"
                        if issue
                        else f"《{tender_doc}》与《{scoring_doc}》未发现明显跨文件评分冲突。"
                    ),
                )
            )
        for contract_doc in contract_docs:
            contract_text = snippets.get(contract_doc, "")
            issue = ("付款" in contract_text and ("满意" in contract_text or "考核" in contract_text)) or (
                "验收" in contract_text and "验收标准" not in tender_text
            )
            checks.append(
                ConsistencyCheck(
                    topic="正文 vs 合同草案跨文件一致性",
                    status="issue" if issue else "ok",
                    detail=(
                        f"《{tender_doc}》与《{contract_doc}》之间存在付款、验收或考核口径不一致，需核查正文承诺与合同草案是否衔接。"
                        if issue
                        else f"《{tender_doc}》与《{contract_doc}》未发现明显跨文件合同冲突。"
                    ),
                )
            )
    return checks


def _split_document_snippets(text: str) -> dict[str, str]:
    snippets: dict[str, list[str]] = {}
    current_name = ""
    for line in text.splitlines():
        if line.startswith("## 文档："):
            current_name = line.replace("## 文档：", "", 1).strip()
            snippets.setdefault(current_name, [])
            continue
        if current_name:
            snippets[current_name].append(line)
    return {name: "\n".join(lines).strip() for name, lines in snippets.items()}


def _clause_map(clauses: list[ExtractedClause]) -> dict[str, list[ExtractedClause]]:
    mapping: dict[str, list[ExtractedClause]] = {}
    for clause in clauses:
        mapping.setdefault(clause.field_name, []).append(clause)
    return mapping


def _first_content(mapping: dict[str, list[ExtractedClause]], key: str) -> str:
    items = mapping.get(key) or []
    return items[0].content if items else ""


def _project_bound_policy_conflict(mapping: dict[str, list[ExtractedClause]]) -> bool:
    sme_clause = _first_project_bound(mapping, "是否专门面向中小企业")
    price_clause = _first_effective_price_clause(mapping, "是否仍保留价格扣除条款")
    return bool(
        sme_clause is not None
        and price_clause is not None
        and sme_clause.normalized_value == "是"
        and price_clause.normalized_value == "是"
    )


def _first_project_bound(mapping: dict[str, list[ExtractedClause]], key: str) -> ExtractedClause | None:
    for clause in mapping.get(key) or []:
        if "项目事实绑定" in clause.relation_tags:
            return clause
        compact = "".join((clause.content or "").split())
        if any(token in compact for token in ["本项目", "本包", "本采购包", "本次采购"]):
            return clause
    return None


def _first_effective_price_clause(mapping: dict[str, list[ExtractedClause]], key: str) -> ExtractedClause | None:
    for clause in mapping.get(key) or []:
        compact = "".join((clause.content or "").split())
        if "专门面向中小企业采购的项目" in compact or "非专门面向中小企业采购的项目" in compact:
            continue
        if "价格扣除比例及采购标的所属行业的说明" in compact:
            continue
        if "项目事实绑定" in clause.relation_tags:
            return clause
        if any(tag in clause.relation_tags for tag in ["价格扣除保留", "价格扣除不适用"]):
            return clause
        if "价格扣除" in compact and any(token in compact for token in ["给予", "扣除", "参与评审", "不适用", "不再适用"]):
            return clause
    return None

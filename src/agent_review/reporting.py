from __future__ import annotations

import json

from .models import FindingType, ReviewReport


def render_json(report: ReviewReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render_markdown(report: ReviewReport) -> str:
    issue_findings = [
        item
        for item in report.findings
        if item.finding_type != FindingType.pass_
    ]
    issue_findings.sort(
        key=lambda item: {"critical": 0, "high": 1, "medium": 2, "low": 3}[item.severity.value]
    )
    high_risk_findings = [item for item in issue_findings if item.severity.value in {"critical", "high"}]
    medium_risk_findings = [item for item in issue_findings if item.severity.value == "medium"]

    lines = [
        f"# 招标文件审查报告",
        "",
        "## 文件解析",
        "",
        f"- 运行模式: {report.review_mode.value}",
        f"- 解析器: {report.parse_result.parser_name}",
        f"- 源文件格式: {report.parse_result.source_format}",
        f"- 页数: {report.parse_result.page_count if report.parse_result.page_count is not None else '未提供'}",
        f"- 表格数: {len(report.parse_result.tables)}",
        f"- 核心规则: {', '.join(report.rule_selection.core_modules) if report.rule_selection.core_modules else '未记录'}",
        f"- 场景增强规则: {', '.join(report.rule_selection.enhancement_modules) if report.rule_selection.enhancement_modules else '未命中'}",
        f"- 场景标签: {', '.join(report.rule_selection.scenario_tags) if report.rule_selection.scenario_tags else '未命中'}",
        "",
        "## 审查范围说明",
        "",
        f"- 文档: {report.file_info.document_name}",
        f"- 文件类型: {report.file_info.file_type.value}",
        f"- 审查范围: {report.file_info.review_scope}",
        "",
        "## 总体结论",
        "",
        f"- 结论等级: {report.overall_conclusion.value}",
        f"- 摘要: {report.summary}",
        f"- LLM增强: {'是' if report.llm_enhanced else '否'}",
        "",
        "## 高风险问题",
    ]

    for index, finding in enumerate(high_risk_findings, start=1):
        lines.append(f"### {index}. {finding.title}")
        lines.append(f"- 维度: {finding.dimension}")
        lines.append(f"- 类型: {finding.finding_type.value}")
        lines.append(f"- 严重程度: {finding.severity.value}")
        lines.append(f"- 置信度: {finding.confidence:.2f}")
        lines.append(f"- 理由: {finding.rationale}")
        if finding.evidence:
            evidence_text = "；".join(
                f"“{item.quote}”({item.section_hint})" for item in finding.evidence
            )
            lines.append(f"- 证据: {evidence_text}")
        else:
            lines.append("- 证据: 当前文本中未抽取到直接证据。")
        lines.append(f"- 建议动作: {finding.next_action}")
        lines.append("")

    lines.append("## 中风险问题")
    for index, finding in enumerate(medium_risk_findings, start=1):
        lines.append(f"### {index}. {finding.title}")
        lines.append(f"- 维度: {finding.dimension}")
        lines.append(f"- 类型: {finding.finding_type.value}")
        lines.append(f"- 严重程度: {finding.severity.value}")
        lines.append(f"- 置信度: {finding.confidence:.2f}")
        lines.append(f"- 理由: {finding.rationale}")
        if finding.evidence:
            evidence_text = "；".join(
                f"“{item.quote}”({item.section_hint})" for item in finding.evidence
            )
            lines.append(f"- 证据: {evidence_text}")
        else:
            lines.append("- 证据: 当前文本中未抽取到直接证据。")
        lines.append(f"- 建议动作: {finding.next_action}")
        lines.append("")

    lines.append("## 相对规范项")
    for item in report.relative_strengths:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 修改建议")
    for item in report.recommendations:
        lines.append(f"- {item.related_issue}: {item.suggestion}")
    lines.append("")

    lines.append("## 章节定位")
    for item in report.section_index:
        status = "已定位" if item.located else "未定位"
        anchor = item.anchor or "未发现"
        lines.append(f"- {item.section_name}: {status}（{anchor}）")
    lines.append("")

    lines.append("## 条款抽取")
    for item in report.extracted_clauses:
        lines.append(f"- [{item.category}] {item.field_name}: {item.content}（{item.source_anchor}）")
    lines.append("")

    if report.llm_semantic_review.clause_supplements:
        lines.append("## LLM补充条款")
        for item in report.llm_semantic_review.clause_supplements:
            lines.append(f"- [{item.category}] {item.field_name}: {item.content}（{item.source_anchor}）")
        lines.append("")

    _append_specialist_table(lines, "项目结构一致性表", report.specialist_tables.project_structure)
    _append_specialist_summary(lines, "项目结构一致性表", report.specialist_tables.summaries.get("project_structure"))
    _append_specialist_table(lines, "中小企业政策一致性表", report.specialist_tables.sme_policy)
    _append_specialist_summary(lines, "中小企业政策一致性表", report.specialist_tables.summaries.get("sme_policy"))
    _append_specialist_table(lines, "人员与用工边界风险表", report.specialist_tables.personnel_boundary)
    _append_specialist_summary(lines, "人员与用工边界风险表", report.specialist_tables.summaries.get("personnel_boundary"))
    _append_specialist_table(lines, "合同履约风险表", report.specialist_tables.contract_performance)
    _append_specialist_summary(lines, "合同履约风险表", report.specialist_tables.summaries.get("contract_performance"))
    _append_specialist_table(lines, "模板残留与冲突表", report.specialist_tables.template_conflicts)
    _append_specialist_summary(lines, "模板残留与冲突表", report.specialist_tables.summaries.get("template_conflicts"))

    if report.parse_result.warnings:
        lines.append("## 解析提示")
        for item in report.parse_result.warnings:
            lines.append(f"- {item}")
        lines.append("")

    if report.llm_warnings:
        lines.append("## LLM提示")
        for item in report.llm_warnings:
            lines.append(f"- {item}")
        lines.append("")

    if report.llm_semantic_review.specialist_findings:
        lines.append("## LLM专项语义复核")
        for item in report.llm_semantic_review.specialist_findings:
            lines.append(f"- {item.title}: {item.severity.value}，{item.rationale}")
        lines.append("")

    if report.llm_semantic_review.consistency_findings:
        lines.append("## LLM深层一致性复核")
        for item in report.llm_semantic_review.consistency_findings:
            lines.append(f"- {item.title}: {item.severity.value}，{item.rationale}")
        lines.append("")

    if report.llm_semantic_review.verdict_review:
        lines.append("## LLM裁决复核")
        lines.append(f"- {report.llm_semantic_review.verdict_review}")
        lines.append("")

    lines.append("## 一致性检查")
    for item in report.consistency_checks:
        lines.append(f"- {item.topic}: {item.status}，{item.detail}")
    lines.append("")

    if report.manual_review_queue:
        lines.append("## 人工复核清单")
        for item in report.manual_review_queue:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## 审查边界说明")
    lines.append(f"- {report.file_info.review_boundary}")
    if report.parse_result.warnings:
        for item in report.parse_result.warnings:
            lines.append(f"- {item}")
    if report.manual_review_queue:
        lines.append("- 当前仍存在需补充附件、补充材料或人工复核后方可完整定性的内容。")
    lines.append("")

    lines.append("## 已审查维度")
    lines.append(f"- {', '.join(report.reviewed_dimensions)}")

    return "\n".join(lines)


def _append_specialist_table(lines: list[str], title: str, rows) -> None:
    lines.append(f"## {title}")
    if rows:
        for row in rows:
            lines.append(
                f"- {row.item_name}: {row.severity.value}，{row.detail}（{row.source_anchor}）"
            )
    else:
        lines.append("- 本次未命中该专项表的结构化风险项。")
    lines.append("")


def _append_specialist_summary(lines: list[str], title: str, summary: str | None) -> None:
    if summary:
        lines.append(f"### {title}摘要")
        lines.append(f"- {summary}")
        lines.append("")

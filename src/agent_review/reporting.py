from __future__ import annotations

import json

from .models import FindingType, ReviewReport


def render_json(report: ReviewReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render_markdown(report: ReviewReport) -> str:
    lines = [
        f"# 招标文件审查报告",
        "",
        "## 审查范围说明",
        "",
        f"- 文档: {report.file_info.document_name}",
        f"- 文件类型: {report.file_info.file_type.value}",
        f"- 审查范围: {report.file_info.review_scope}",
        f"- 审查边界: {report.file_info.review_boundary}",
        "",
        "## 总体结论",
        "",
        f"- 结论等级: {report.overall_conclusion.value}",
        f"- 摘要: {report.summary}",
        "",
        "## 主要问题",
    ]

    issue_findings = [
        item
        for item in report.findings
        if item.finding_type != FindingType.pass_
    ]
    issue_findings.sort(
        key=lambda item: {"critical": 0, "high": 1, "medium": 2, "low": 3}[item.severity.value]
    )
    for index, finding in enumerate(issue_findings, start=1):
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

    lines.append("## 一致性检查")
    for item in report.consistency_checks:
        lines.append(f"- {item.topic}: {item.status}，{item.detail}")
    lines.append("")

    if report.manual_review_queue:
        lines.append("## 人工复核清单")
        for item in report.manual_review_queue:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## 已审查维度")
    lines.append(f"- {', '.join(report.reviewed_dimensions)}")

    return "\n".join(lines)

from __future__ import annotations

import json

from .models import FindingType, ReviewReport


def render_json(report: ReviewReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render_markdown(report: ReviewReport) -> str:
    lines = [
        f"# 招标文件审查报告",
        "",
        f"- 文档: {report.document_name}",
        f"- 摘要: {report.summary}",
        f"- 已审查维度: {', '.join(report.reviewed_dimensions)}",
        "",
        "## 审查结果",
    ]

    for index, finding in enumerate(report.findings, start=1):
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

    if report.manual_review_queue:
        lines.append("## 人工复核清单")
        for item in report.manual_review_queue:
            lines.append(f"- {item}")
        lines.append("")

    high_risk = [
        finding
        for finding in report.findings
        if finding.finding_type != FindingType.pass_ and finding.severity.value in {"high", "critical"}
    ]
    lines.append("## 结论")
    if high_risk:
        lines.append("当前文本已触发高风险或需复核项，建议在正式发布前完成专项复审。")
    else:
        lines.append("当前版本完成了基础筛查，但仍建议结合法规条款和完整附件进行正式复核。")

    return "\n".join(lines)

from __future__ import annotations

import json

from ..models import FindingType, ReviewReport


REVIEW_ENHANCER_SYSTEM_PROMPT = """你是政府采购招标文件合规审查助手。

你的任务不是重新发明事实，而是根据已经抽取好的结构化审查结果：
1. 用正式、克制、审慎的中文生成总体结论摘要。
2. 为问题生成更自然、可执行的修改建议。

要求：
1. 只能根据输入的结构化结果回答，不要虚构文件中没有的信息。
2. 不要把“待完善”写成“违法”。
3. 不要弱化明确的高风险问题。
4. 输出必须是 JSON，不要使用 Markdown。
"""


def build_review_enhancer_prompt(report: ReviewReport) -> str:
    issue_findings = [
        {
            "title": item.title,
            "dimension": item.dimension,
            "severity": item.severity.value,
            "finding_type": item.finding_type.value,
            "rationale": item.rationale,
        }
        for item in report.findings
        if item.finding_type != FindingType.pass_
    ]
    base_recommendations = [
        {"related_issue": item.related_issue, "suggestion": item.suggestion}
        for item in report.recommendations
    ]
    payload = {
        "document_name": report.file_info.document_name,
        "file_type": report.file_info.file_type.value,
        "scope_statement": report.scope_statement,
        "overall_conclusion": report.overall_conclusion.value,
        "summary": report.summary,
        "issues": issue_findings,
        "relative_strengths": report.relative_strengths,
        "recommendations": base_recommendations,
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "summary": "一段正式、克制、适合审查意见书的总体结论摘要",
  "recommendations": [
    {{
      "related_issue": "问题标题",
      "suggestion": "更自然、可执行的修改建议"
    }}
  ]
}}
"""

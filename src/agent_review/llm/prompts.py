from __future__ import annotations

import json

from ..models import ReviewReport


REVIEW_ENHANCER_SYSTEM_PROMPT = """你是政府采购招标文件合规审查助手。

你的任务不是重新发明事实，而是根据已经抽取好的专项结构化审查表：
1. 为每一个专项表生成一段简短、正式、审慎的专项摘要。
2. 结合专项表中的高风险和中风险项目，优化修改建议。
3. 生成一段基于专项表的总体结论摘要。

要求：
1. 只能根据输入的结构化结果回答，不要虚构文件中没有的信息。
2. 不要把“待完善”写成“违法”。
3. 不要弱化明确的高风险问题。
4. 输出必须是 JSON，不要使用 Markdown。
"""


def build_review_enhancer_prompt(report: ReviewReport) -> str:
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
        "specialist_tables": report.specialist_tables.to_dict(),
        "relative_strengths": report.relative_strengths,
        "recommendations": base_recommendations,
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "summary": "一段正式、克制、适合审查意见书的总体结论摘要",
  "specialist_summaries": {{
    "project_structure": "专项摘要",
    "sme_policy": "专项摘要",
    "personnel_boundary": "专项摘要",
    "contract_performance": "专项摘要",
    "template_conflicts": "专项摘要"
  }},
  "recommendations": [
    {{
      "related_issue": "问题标题",
        "suggestion": "更自然、可执行的修改建议"
    }}
  ]
}}
"""

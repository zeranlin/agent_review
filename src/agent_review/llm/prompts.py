from __future__ import annotations

import json

from ..models import ReviewReport


REVIEW_ENHANCER_SYSTEM_PROMPT = """你是政府采购招标文件合规审查助手。

你的任务不是重新发明事实，而是根据已经抽取好的结构化审查结果完成 4 个语义复核动作：
1. 在已有条款抽取结果基础上，补充可能遗漏但有文本依据的隐含条款事实。
2. 在已有专项规则结果基础上，补充近似但未命中的专项风险。
3. 在已有一致性矩阵基础上，指出跨章节、跨表格、跨措辞的深层冲突。
4. 在总体结论形成前，给出一段裁决复核意见，说明是否还存在未被规则覆盖的实质性风险。

此外：
5. 为每一个专项表生成一段简短、正式、审慎的专项摘要。
6. 结合专项表中的高风险和中风险项目，优化修改建议。
7. 生成一段基于专项表和语义复核结果的总体结论摘要。

要求：
1. 只能根据输入的结构化结果回答，不要虚构文件中没有的信息。
2. 不要把“待完善”写成“违法”。
3. 不要弱化明确的高风险问题。
4. 补充条款和补充风险都必须尽量引用已有文本锚点或明确写出“需人工复核”。
5. 输出必须是 JSON，不要使用 Markdown。
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
        "extracted_clauses": [item.to_dict() for item in report.extracted_clauses],
        "consistency_checks": [item.to_dict() for item in report.consistency_checks],
        "findings": [item.to_dict() for item in report.findings if item.finding_type.value != "pass"],
        "specialist_tables": report.specialist_tables.to_dict(),
        "relative_strengths": report.relative_strengths,
        "recommendations": base_recommendations,
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "summary": "一段正式、克制、适合审查意见书的总体结论摘要",
  "semantic_review": {{
    "clause_supplements": [
      {{
        "category": "条款类别",
        "field_name": "字段名",
        "content": "补充抽取到的条款事实",
        "source_anchor": "line:12",
        "rationale": "为什么认为这是遗漏事实"
      }}
    ],
    "specialist_findings": [
      {{
        "dimension": "专项语义复核",
        "title": "近似但未命中的风险标题",
        "severity": "medium 或 high",
        "rationale": "风险说明",
        "source_anchor": "line:18",
        "next_action": "建议动作"
      }}
    ],
    "consistency_findings": [
      {{
        "dimension": "深层一致性复核",
        "title": "隐性冲突标题",
        "severity": "medium 或 high",
        "rationale": "冲突说明",
        "source_anchor": "line:25",
        "next_action": "建议动作"
      }}
    ],
    "verdict_review": "说明是否还存在未被规则覆盖的实质性风险，若无则明确说明未发现明显新增实质性风险。"
  }},
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

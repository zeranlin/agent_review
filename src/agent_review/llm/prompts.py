from __future__ import annotations

import json

from ..models import ReviewReport


CLAUSE_SUPPLEMENT_SYSTEM_PROMPT = """你是政府采购招标文件合规审查助手。

你的任务是基于已经抽取好的结构化条款和已有审查结果，补充可能遗漏但有文本依据的条款事实。

要求：
1. 只能补充文本中确有依据的事实，不要虚构。
2. 只输出新增条款，不要重复已有抽取结果。
3. 对每一条补充结果标记 adoption_status，只能是“可直接采用”或“需人工确认”。
3. 输出必须是 JSON，不要使用 Markdown。
"""

SPECIALIST_REVIEW_SYSTEM_PROMPT = """你是政府采购招标文件合规审查助手。

你的任务是基于专项检查表，补充近似但未命中的专项风险，并生成专项摘要和修改建议。

要求：
1. 只能基于输入的结构化事实和专项表回答。
2. 不要弱化明确的高风险问题。
3. 对每一条补充风险标记 adoption_status，只能是“可直接采用”或“需人工确认”。
3. 输出必须是 JSON，不要使用 Markdown。
"""

CONSISTENCY_REVIEW_SYSTEM_PROMPT = """你是政府采购招标文件合规审查助手。

你的任务是在现有一致性矩阵基础上，补充跨章节、跨表格、跨措辞的深层冲突。

要求：
1. 只补充现有规则矩阵未显式命中的隐性冲突。
2. 保持审慎，不要把待完善问题夸大成违法结论。
3. 对每一条补充冲突标记 adoption_status，只能是“可直接采用”或“需人工确认”。
3. 输出必须是 JSON，不要使用 Markdown。
"""

VERDICT_REVIEW_SYSTEM_PROMPT = """你是政府采购招标文件合规审查助手。

你的任务是在总体结论形成前，基于现有结构化审查结果给出裁决复核意见，并生成最终摘要。

要求：
1. 说明是否仍存在未被规则覆盖的实质性风险。
2. 不要直接推翻已明确命中的高风险结论。
3. 输出必须是 JSON，不要使用 Markdown。
"""


def build_clause_supplement_prompt(report: ReviewReport) -> str:
    payload = {
        "document_name": report.file_info.document_name,
        "file_type": report.file_info.file_type.value,
        "scope_statement": report.scope_statement,
        "extracted_clauses": [item.to_dict() for item in report.extracted_clauses],
        "section_index": [item.to_dict() for item in report.section_index],
        "findings": [item.to_dict() for item in report.findings if item.finding_type.value != "pass"],
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "clause_supplements": [
    {{
      "category": "条款类别",
      "field_name": "字段名",
      "content": "补充抽取到的条款事实",
      "source_anchor": "line:12",
      "adoption_status": "可直接采用 或 需人工确认",
      "review_note": "如需人工确认，说明原因"
    }}
  ]
}}
"""


def build_specialist_review_prompt(report: ReviewReport) -> str:
    base_recommendations = [
        {"related_issue": item.related_issue, "suggestion": item.suggestion}
        for item in report.recommendations
    ]
    payload = {
        "document_name": report.file_info.document_name,
        "specialist_tables": report.specialist_tables.to_dict(),
        "findings": [item.to_dict() for item in report.findings if item.finding_type.value != "pass"],
        "recommendations": base_recommendations,
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "specialist_findings": [
    {{
      "dimension": "专项语义复核",
      "title": "近似但未命中的风险标题",
      "severity": "medium 或 high",
      "rationale": "风险说明",
      "source_anchor": "line:18",
      "next_action": "建议动作",
      "confidence": 0.0,
      "adoption_status": "可直接采用 或 需人工确认",
      "review_note": "如需人工确认，说明原因"
    }}
  ],
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


def build_consistency_review_prompt(report: ReviewReport) -> str:
    payload = {
        "document_name": report.file_info.document_name,
        "consistency_checks": [item.to_dict() for item in report.consistency_checks],
        "extracted_clauses": [item.to_dict() for item in report.extracted_clauses],
        "findings": [item.to_dict() for item in report.findings if item.finding_type.value != "pass"],
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "consistency_findings": [
    {{
      "dimension": "深层一致性复核",
      "title": "隐性冲突标题",
      "severity": "medium 或 high",
      "rationale": "冲突说明",
      "source_anchor": "line:25",
      "next_action": "建议动作",
      "confidence": 0.0,
      "adoption_status": "可直接采用 或 需人工确认",
      "review_note": "如需人工确认，说明原因"
    }}
  ]
}}
"""


def build_verdict_review_prompt(report: ReviewReport) -> str:
    payload = {
        "document_name": report.file_info.document_name,
        "overall_conclusion": report.overall_conclusion.value,
        "summary": report.summary,
        "findings": [item.to_dict() for item in report.findings if item.finding_type.value != "pass"],
        "relative_strengths": report.relative_strengths,
        "specialist_tables": report.specialist_tables.to_dict(),
        "consistency_checks": [item.to_dict() for item in report.consistency_checks],
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "summary": "一段正式、克制、适合审查意见书的总体结论摘要",
  "verdict_review": "说明是否还存在未被规则覆盖的实质性风险，若无则明确说明未发现明显新增实质性风险。"
}}
"""

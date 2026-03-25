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

ROLE_REVIEW_SYSTEM_PROMPT = """你是政府采购招标文件合规审查助手。

你的任务是对现有 ReviewPoint 的条款角色判断做复核，识别是否存在模板、定义说明、附件引用被误判成采购约束条款的情况。

要求：
1. 保持审慎，只指出有明确理由的角色误判风险。
2. 输出必须是 JSON，不要使用 Markdown。
"""

EVIDENCE_REVIEW_SYSTEM_PROMPT = """你是政府采购招标文件合规审查助手。

你的任务是对现有 ReviewPoint 的证据包做复核，指出哪些审查点证据充分，哪些仍缺关键直接证据或存在反证风险。

要求：
1. 不要重复生成已有 finding。
2. 只输出面向复核的说明，不直接替代 formal 裁决。
3. 输出必须是 JSON，不要使用 Markdown。
"""

APPLICABILITY_REVIEW_SYSTEM_PROMPT = """你是政府采购招标文件合规审查助手。

你的任务是对现有审查点的适法性判断做复核，判断当前事实是否足以支撑法规要件成立。

要求：
1. 仅基于输入的审查点、证据和适法性结果回答。
2. 如果要件不足，应明确指出不足点。
3. 输出必须是 JSON，不要使用 Markdown。
"""

SCENARIO_REVIEW_SYSTEM_PROMPT = """你是政府采购招标文件合规审查助手。

你的任务是识别当前项目的采购场景，并补充建议的动态审查任务。重点不是重复已有通用任务，而是识别行业或项目结构带来的特殊审查重点。

要求：
1. 只基于输入文本和结构化条款判断场景，不要虚构事实。
2. 动态审查任务应尽量映射为跨行业可复用的“审查母题”，不要写成过于狭窄的一次性描述。
3. 每个动态任务最多给出 2 组关键信号，每组 2-5 个词。
4. 每个动态任务都要优先给出证据采集提示，说明后续应优先补哪些字段或条款。
5. 每个动态任务都要尽量给出反证模板，帮助后续避免过度定性。
6. 每个动态任务都要给出一组组证增强字段，供后续触发专属组证增强。
7. 每个动态任务都要给出 task_type，只能从 structure、scoring、contract、template、policy、restrictive、personnel、consistency、generic 中选择。
8. 输出必须是 JSON，不要使用 Markdown。
"""

SCORING_REVIEW_SYSTEM_PROMPT = """你是政府采购招标文件评分标准审查助手。

你的任务是专门分析评分章节或评分相关条款的语义风险，并补充建议的动态评分审查任务。评分动态任务原则上优先细化成两类母题：
1. 评分主观性/量化不足；
2. 证书、检测报告、财务指标权重偏重或负担过重。

同时重点关注：
1. 评分因素是否与项目履约能力直接相关；
2. 评分分档是否主观、量化不足；
3. 证书、检测报告、财务指标等是否被过度使用或权重偏高；
4. 评分语言是否存在“完全满足且优于/完全满足/不完全满足”“横向比较”“每处缺陷扣分”等裁量空间较大的模式。

要求：
1. 只基于输入的评分相关条款和项目基本信息判断，不要虚构事实。
2. 动态任务应优先围绕上述两类“评分母题”组织，不要重复已有固定任务标题。
3. 如两类母题都有依据，优先同时输出两条动态任务，而不是合并成一条宽泛标题。
4. “主观性/量化不足”侧重分档、裁量空间、缺陷定义、横向比较；“权重偏重/负担过重”侧重证书、检测报告、财务指标、分值权重、提交阶段负担。
3. 每个动态任务最多给出 2 组关键信号，每组 2-5 个词。
4. 每个动态任务都要给出证据采集提示、反证模板和组证增强字段。
5. 每个动态任务的 task_type 必须填写为 scoring。
6. 输出必须是 JSON，不要使用 Markdown。
"""

REVIEW_POINT_SECOND_REVIEW_SYSTEM_PROMPT = """你是政府采购招标文件合规复核审查员。

你的任务是以 ReviewPoint 为单位进行二审，不做泛化总结。你需要逐个审查点判断：
1. 当前条款角色判断是否可靠；
2. 当前证据是否足以支撑该审查点；
3. 当前适法性要件链是否成立；
4. 当前 formal 裁决建议是 include、manual_confirmation 还是 filtered_out。

要求：
1. 审慎、克制，只基于输入的 ReviewPoint、证据包、适法性与质量关卡结果作答。
2. 不要虚构新证据，也不要扩大结论。
3. 对动态审查任务，要结合 task_type 和 second_review_focus 做差异化二审：
   - structure：重点看项目属性、采购内容、合同类型是否真的错配；
   - scoring：重点看评分项与履约能力、量化性、相关性；
   - contract：重点看付款、验收、考核、解约是否形成实质联动；
   - template：重点看模板语言是否只是残留，还是已经实质影响资格/评审/履约；
   - policy：重点看政策适用条件和金额/声明函口径是否闭合；
   - restrictive：重点看条款是否真的构成限制竞争，而非普通承诺或说明；
   - personnel：重点看对象是否真是履约人员要求，而非一般劳动合规或表单字段；
   - consistency：重点看冲突是否为镜像重复，还是足以单独成立。
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


def build_role_review_prompt(report: ReviewReport) -> str:
    payload = {
        "document_name": report.file_info.document_name,
        "review_points": [item.to_dict() for item in report.review_points],
        "extracted_clauses": [item.to_dict() for item in report.extracted_clauses],
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "role_review_notes": [
    "对某个 ReviewPoint 的角色复核说明"
  ]
}}
"""


def build_evidence_review_prompt(report: ReviewReport) -> str:
    payload = {
        "document_name": report.file_info.document_name,
        "review_points": [item.to_dict() for item in report.review_points],
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "evidence_review_notes": [
    "对某个 ReviewPoint 的证据复核说明"
  ]
}}
"""


def build_applicability_review_prompt(report: ReviewReport) -> str:
    payload = {
        "document_name": report.file_info.document_name,
        "review_points": [item.to_dict() for item in report.review_points],
        "applicability_checks": [item.to_dict() for item in report.applicability_checks],
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "applicability_review_notes": [
    "对某个 ReviewPoint 适法性判断的复核说明"
  ]
}}
"""


def build_scenario_review_prompt(report: ReviewReport) -> str:
    payload = {
        "document_name": report.file_info.document_name,
        "file_type": report.file_info.file_type.value,
        "review_scope": report.file_info.review_scope,
        "summary": report.summary,
        "extracted_clauses": [item.to_dict() for item in report.extracted_clauses[:40]],
        "existing_catalog": [
            {
                "catalog_id": item.catalog_id,
                "title": item.title,
                "dimension": item.dimension,
            }
            for item in report.review_point_catalog[:40]
        ],
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "scenario_review_summary": "对当前采购场景的简短判断",
  "dynamic_review_tasks": [
    {{
      "catalog_id": "RP-DYN-001",
      "title": "建议新增的动态审查任务标题",
      "dimension": "项目结构风险",
      "severity": "medium 或 high",
      "task_type": "structure",
      "scenario_tags": ["dynamic", "domain"],
      "focus_fields": ["项目属性", "采购标的"],
      "signal_groups": [
        ["人工管护", "抚育", "运水"],
        ["承揽合同"]
      ],
      "evidence_hints": [
        "优先采集项目属性、采购内容、合同类型和履约周期条款"
      ],
      "rebuttal_templates": [
        ["买卖合同", "仅供货"],
        ["货物验收", "不含人工服务"]
      ],
      "enhancement_fields": ["项目属性", "采购标的", "合同履行期限"],
      "basis_hint": "该任务关注的审查理由"
    }}
  ]
}}
"""


def build_scoring_review_prompt(report: ReviewReport) -> str:
    scoring_keywords = (
        "评分",
        "评审",
        "分值",
        "分档",
        "方案",
        "证书",
        "检测报告",
        "财务",
        "样品",
        "售后",
    )
    scoring_clauses = [
        item.to_dict()
        for item in report.extracted_clauses
        if any(token in f"{item.category}{item.field_name}{item.content}" for token in scoring_keywords)
    ][:30]
    scoring_catalog = [
        {
            "catalog_id": item.catalog_id,
            "title": item.title,
            "dimension": item.dimension,
        }
        for item in report.review_point_catalog
        if item.task_type == "scoring" or "评分" in item.title or "评审" in item.title
    ][:20]
    payload = {
        "document_name": report.file_info.document_name,
        "file_type": report.file_info.file_type.value,
        "project_context": {
            "review_scope": report.file_info.review_scope,
            "document_name": report.file_info.document_name,
        },
        "scoring_clauses": scoring_clauses,
        "existing_scoring_catalog": scoring_catalog,
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "scoring_review_summary": "对评分章节风险特征的简短判断",
  "dynamic_review_tasks": [
    {{
      "catalog_id": "RP-DYN-SCORE-001",
      "title": "评分分档主观性与量化充分性复核",
      "dimension": "评审标准明确性",
      "severity": "medium 或 high",
      "task_type": "scoring",
      "scenario_tags": ["dynamic", "scoring"],
      "focus_fields": ["评分方法", "采购标的"],
      "signal_groups": [
        ["完全满足且优于", "完全满足", "不完全满足"],
        ["证书", "财务", "检测报告"]
      ],
      "evidence_hints": [
        "优先采集评分方法、评分项名称、分值、采购标的和证书/报告要求条款"
      ],
      "rebuttal_templates": [
        ["中标后提交", "供货验收材料"],
        ["与履约能力直接相关", "法定强制认证"]
      ],
      "enhancement_fields": ["评分方法", "采购标的", "行业相关性存疑评分项", "方案评分扣分模式"],
      "basis_hint": "该任务关注评分主观性、量化充分性和裁量空间。"
    }},
    {{
      "catalog_id": "RP-DYN-SCORE-002",
      "title": "证书检测报告及财务指标权重合理性复核",
      "dimension": "评审标准明确性",
      "severity": "medium 或 high",
      "task_type": "scoring",
      "scenario_tags": ["dynamic", "scoring"],
      "focus_fields": ["评分方法", "采购标的"],
      "signal_groups": [
        ["证书", "检测报告", "财务"],
        ["分值", "加分"]
      ],
      "evidence_hints": [
        "优先采集证书类评分项、检测报告要求、财务指标评分项、分值和项目标的条款"
      ],
      "rebuttal_templates": [
        ["法定强制认证", "履约直接相关"],
        ["中标后提交", "验收材料"]
      ],
      "enhancement_fields": ["评分方法", "采购标的", "行业相关性存疑评分项", "财务指标加分"],
      "basis_hint": "该任务关注证书、检测报告和财务指标的必要性、相关性与权重强度。"
    }}
  ]
}}
"""


def build_review_point_second_review_prompt(report: ReviewReport) -> str:
    selected_points = _select_second_review_points(report)
    selected_ids = {item.point_id for item in selected_points}
    catalog_index = {item.catalog_id: item for item in report.review_point_catalog}
    dynamic_index = _build_dynamic_task_context_index(report)
    payload = {
        "document_name": report.file_info.document_name,
        "review_points": [
            {
                **item.to_dict(),
                "task_type": _resolve_review_point_task_type(item, catalog_index, dynamic_index),
                "second_review_focus": _build_second_review_focus(
                    _resolve_review_point_task_type(item, catalog_index, dynamic_index)
                ),
            }
            for item in selected_points
        ],
        "applicability_checks": [item.to_dict() for item in report.applicability_checks if item.point_id in selected_ids],
        "quality_gates": [item.to_dict() for item in report.quality_gates if item.point_id in selected_ids],
        "formal_adjudication": [item.to_dict() for item in report.formal_adjudication if item.point_id in selected_ids],
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "review_point_second_reviews": [
    {{
      "point_id": "RP-001",
      "title": "审查点标题",
      "role_judgment": "角色判断结论",
      "evidence_judgment": "证据充分性结论",
      "applicability_judgment": "适法性结论",
      "intensity_judgment": "判断属于一般要求、偏重要求、刚性门槛、裁量过大或证据不足",
      "suggested_disposition": "include 或 manual_confirmation 或 filtered_out",
      "rationale": "二审理由",
      "adoption_status": "可直接采用 或 需人工确认"
    }}
  ]
}}
"""


def _select_second_review_points(report: ReviewReport, limit: int = 12) -> list:
    dynamic_titles = {item.title for item in report.llm_semantic_review.dynamic_review_tasks}
    dynamic_points = [
        item
        for item in report.review_points
        if item.catalog_id.startswith("RP-DYN-")
        or any(source.startswith("task_library:RP-DYN-") for source in item.source_findings)
        or item.title in dynamic_titles
    ]
    other_points = [item for item in report.review_points if item not in dynamic_points]
    selected: list = []
    seen: set[str] = set()
    for item in [*dynamic_points, *other_points]:
        if item.point_id in seen:
            continue
        seen.add(item.point_id)
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _build_second_review_focus(task_type: str) -> str:
    focus_map = {
        "structure": "重点复核项目属性、采购内容、合同类型、履约周期之间是否真实错配，并判断整体主线是否仍然自洽。",
        "scoring": "重点复核评分因素是否与履约能力相关、是否量化、是否存在行业错配，并判断属于一般提示、权重偏重还是裁量过大。",
        "contract": "重点复核付款、验收、考核、扣款、解约之间是否形成实质联动，并判断条款失衡强度。",
        "template": "重点复核模板语句是否只是残留，还是已实质影响资格、评审或履约，并判断是否足以进入formal。",
        "policy": "重点复核政策适用条件、声明函口径、金额口径和价格扣除是否闭合，并判断冲突强度。",
        "restrictive": "重点复核条款是否真的构成限制竞争，而非普通承诺、声明或说明，并判断属于一般要求、偏重要求还是刚性门槛。",
        "personnel": "重点复核对象是否确为履约人员要求，而非一般劳动合规或表单字段。",
        "consistency": "重点复核冲突是否可独立成立，还是仅为镜像重复或待补证问题，并判断formal强度。",
        "generic": "重点复核证据、角色、适法性和formal裁决是否一致，并明确风险强度。",
    }
    return focus_map.get(task_type, focus_map["generic"])


def _build_dynamic_task_context_index(report: ReviewReport) -> dict[str, str]:
    index: dict[str, str] = {}
    for item in report.llm_semantic_review.dynamic_review_tasks:
        index[item.title] = item.task_type
        index[item.catalog_id] = item.task_type
    return index


def _resolve_review_point_task_type(point, catalog_index: dict, dynamic_index: dict[str, str]) -> str:
    if point.catalog_id in dynamic_index:
        return dynamic_index[point.catalog_id]
    if point.title in dynamic_index:
        return dynamic_index[point.title]
    for source in point.source_findings:
        if source.startswith("task_library:"):
            _, _, catalog_id = source.partition(":")
            if catalog_id in dynamic_index:
                return dynamic_index[catalog_id]
    if catalog_index.get(point.catalog_id):
        return catalog_index[point.catalog_id].task_type
    return "generic"


def build_verdict_review_prompt(report: ReviewReport) -> str:
    payload = {
        "document_name": report.file_info.document_name,
        "overall_conclusion": report.overall_conclusion.value,
        "summary": report.summary,
        "findings": [item.to_dict() for item in report.findings if item.finding_type.value != "pass"],
        "relative_strengths": report.relative_strengths,
        "specialist_tables": report.specialist_tables.to_dict(),
        "consistency_checks": [item.to_dict() for item in report.consistency_checks],
        "formal_adjudication": [item.to_dict() for item in report.formal_adjudication],
    }
    return f"""请根据以下结构化审查结果，输出 JSON：

{json.dumps(payload, ensure_ascii=False, indent=2)}

输出格式：
{{
  "summary": "一段正式、克制、适合审查意见书的总体结论摘要",
  "verdict_review": "说明是否还存在未被规则覆盖的实质性风险，若无则明确说明未发现明显新增实质性风险。"
}}
"""

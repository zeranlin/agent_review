from __future__ import annotations

import json

from .quality import evidence_supports_title
from .models import FindingType, ReviewReport


def render_json(report: ReviewReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render_formal_review_opinion(report: ReviewReport) -> str:
    items = _build_formal_review_items(report)
    review_items = _build_review_review_items(report)
    lines = [
        "# 招标文件高风险正式审查意见",
        "",
        f"- 审查对象: {report.file_info.document_name}",
        f"- 结论等级: {report.overall_conclusion.value}",
        f"- 输出范围: 正式高风险 + 建议复核",
        "",
    ]

    if not items and not review_items:
        lines.extend(
            [
                "## 审查结果",
                "",
                "当前未形成具备正式审查意见结构的高风险问题项。",
            ]
        )
        return "\n".join(lines)

    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"## {index}. {item['问题标题']}",
                "",
                f"- 问题标题: {item['问题标题']}",
                f"- 条款位置: {item['条款位置']}",
                f"- 原文摘录: {item['原文摘录']}",
                f"- 问题类型: {item['问题类型']}",
                f"- 风险等级: {item['风险等级']}",
                f"- 合规判断: {item['合规判断']}",
                f"- 法律/政策依据: {item['法律/政策依据']}",
                "",
            ]
        )

    if review_items:
        lines.extend(
            [
                "## 建议复核问题",
                "",
            ]
        )
        for index, item in enumerate(review_items, start=1):
            lines.extend(
                [
                    f"### {index}. {item['问题标题']}",
                    "",
                    f"- 问题标题: {item['问题标题']}",
                    f"- 条款位置: {item['条款位置']}",
                    f"- 原文摘录: {item['原文摘录']}",
                    f"- 问题类型: {item['问题类型']}",
                    f"- 风险等级: {item['风险等级']}",
                    f"- 复核判断: {item['合规判断']}",
                    f"- 法律/政策依据: {item['法律/政策依据']}",
                    "",
                ]
            )

    return "\n".join(lines)


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
    ]

    if report.source_documents:
        lines.extend(
            [
                "## 联合审查文件",
                "",
            ]
        )
        for item in report.source_documents:
            page_text = item.page_count if item.page_count is not None else "未提供"
            lines.append(
                f"- {item.document_name}: {item.source_format}，解析器 {item.parser_name}，页数 {page_text}"
            )
        lines.append("")

    lines.extend(
        [
        "## 总体结论",
        "",
        f"- 结论等级: {report.overall_conclusion.value}",
        f"- 摘要: {report.summary}",
        f"- LLM增强: {'是' if report.llm_enhanced else '否'}",
        "",
        "## 高风险问题",
        ]
    )

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
        if finding.legal_basis:
            basis_text = "；".join(
                f"{item.source_name}{(' ' + item.article_hint) if item.article_hint else ''}：{item.summary}"
                for item in finding.legal_basis
            )
            lines.append(f"- 法规依据: {basis_text}")
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
        if finding.legal_basis:
            basis_text = "；".join(
                f"{item.source_name}{(' ' + item.article_hint) if item.article_hint else ''}：{item.summary}"
                for item in finding.legal_basis
            )
            lines.append(f"- 法规依据: {basis_text}")
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

    if report.high_risk_review_items:
        lines.append("## 高风险复核清单")
        for item in report.high_risk_review_items:
            lines.append(f"- {item.title}: {item.severity}，{item.reason}")
        lines.append("")

    if report.pending_confirmation_items:
        lines.append("## 待确认问题单")
        for item in report.pending_confirmation_items:
            lines.append(f"- {item.title}: {item.reason}")
        lines.append("")

    if report.review_points:
        lines.append("## ReviewPoint")
        for item in report.review_points[:10]:
            lines.append(
                f"- {item.point_id} [{item.catalog_id}] {item.title}: {item.status.value}，{item.evidence_bundle.sufficiency_summary}"
            )
        lines.append("")

    if report.review_point_catalog:
        lines.append("## 审查点目录")
        for item in report.review_point_catalog[:10]:
            lines.append(
                f"- [{item.catalog_id}] {item.title}: 默认等级 {item.default_severity.value}，适用场景 {', '.join(item.scenario_tags) if item.scenario_tags else '通用'}"
            )
        lines.append("")

    if report.applicability_checks:
        lines.append("## 适法性检查")
        for item in report.applicability_checks[:10]:
            lines.append(
                f"- {item.point_id}: {'适用' if item.applicable else '待确认'}，{item.summary}"
            )
        lines.append("")

    if report.quality_gates:
        lines.append("## 质量关卡")
        for item in report.quality_gates[:10]:
            lines.append(
                f"- {item.point_id}: {item.status.value}，{'；'.join(item.reasons)}"
            )
        lines.append("")

    if report.formal_adjudication:
        lines.append("## Formal Adjudication")
        for item in report.formal_adjudication[:10]:
            lines.append(
                f"- {item.point_id} [{item.catalog_id}] {item.title}: {item.disposition.value}，{item.rationale}"
            )
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
            lines.append(
                f"- [{item.category}] {item.field_name}: {item.content}（{item.source_anchor}，{item.adoption_status.value}）"
            )
        lines.append("")

    scoring_task_ids = {
        (item.catalog_id, item.title) for item in report.llm_semantic_review.scoring_dynamic_review_tasks
    }
    scenario_dynamic_tasks = [
        item
        for item in report.llm_semantic_review.dynamic_review_tasks
        if (item.catalog_id, item.title) not in scoring_task_ids
    ]

    if report.llm_semantic_review.scenario_review_summary or scenario_dynamic_tasks:
        lines.append("## LLM场景识别与动态任务")
        if report.llm_semantic_review.scenario_review_summary:
            lines.append(f"- 场景判断：{report.llm_semantic_review.scenario_review_summary}")
        for item in scenario_dynamic_tasks:
            lines.append(f"- [{item.catalog_id}] {item.title}：{item.dimension}")
            if item.evidence_hints:
                lines.append(f"  证据提示：{'；'.join(item.evidence_hints)}")
            if item.rebuttal_templates:
                lines.append(
                    "  反证模板："
                    + " / ".join("、".join(group) for group in item.rebuttal_templates)
                )
        lines.append("")

    if report.llm_semantic_review.scoring_review_summary or report.llm_semantic_review.scoring_dynamic_review_tasks:
        lines.append("## LLM评分语义分析与动态任务")
        if report.llm_semantic_review.scoring_review_summary:
            lines.append(f"- 评分判断：{report.llm_semantic_review.scoring_review_summary}")
        for item in report.llm_semantic_review.scoring_dynamic_review_tasks:
            lines.append(f"- [{item.catalog_id}] {item.title}：{item.dimension}")
            if item.evidence_hints:
                lines.append(f"  证据提示：{'；'.join(item.evidence_hints)}")
            if item.rebuttal_templates:
                lines.append(
                    "  反证模板："
                    + " / ".join("、".join(group) for group in item.rebuttal_templates)
                )
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
            lines.append(
                f"- {item.title}: {item.severity.value}，{item.rationale}（{item.adoption_status.value}）"
            )
        lines.append("")

    if report.llm_semantic_review.consistency_findings:
        lines.append("## LLM深层一致性复核")
        for item in report.llm_semantic_review.consistency_findings:
            lines.append(
                f"- {item.title}: {item.severity.value}，{item.rationale}（{item.adoption_status.value}）"
            )
        lines.append("")

    if report.llm_semantic_review.verdict_review:
        lines.append("## LLM裁决复核")
        lines.append(f"- {report.llm_semantic_review.verdict_review}")
        lines.append("")

    if report.llm_semantic_review.role_review_notes:
        lines.append("## LLM角色复核")
        for item in report.llm_semantic_review.role_review_notes:
            lines.append(f"- {item}")
        lines.append("")

    if report.llm_semantic_review.evidence_review_notes:
        lines.append("## LLM证据复核")
        for item in report.llm_semantic_review.evidence_review_notes:
            lines.append(f"- {item}")
        lines.append("")

    if report.llm_semantic_review.applicability_review_notes:
        lines.append("## LLM适法性复核")
        for item in report.llm_semantic_review.applicability_review_notes:
            lines.append(f"- {item}")
        lines.append("")

    if report.llm_semantic_review.review_point_second_reviews:
        lines.append("## LLM审查点二审")
        for item in report.llm_semantic_review.review_point_second_reviews:
            intensity = f"，强度判断：{item.intensity_judgment}" if item.intensity_judgment else ""
            primary = f"，主证据：{item.primary_evidence_judgment}" if item.primary_evidence_judgment else ""
            supporting = f"，辅助证据：{item.supporting_evidence_judgment}" if item.supporting_evidence_judgment else ""
            lines.append(
                f"- {item.point_id} {item.title}: 建议 {item.suggested_disposition or 'manual_confirmation'}，"
                f"{item.rationale}{intensity}{primary}{supporting}（{item.adoption_status.value}）"
            )
        lines.append("")

    cross_file_checks = [
        item for item in report.consistency_checks if "跨文件" in item.topic
    ]
    if cross_file_checks:
        lines.append("## 跨文件一致性专项")
        for item in cross_file_checks:
            lines.append(f"- {item.topic}: {item.status}，{item.detail}")
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


def render_opinion_letter(report: ReviewReport) -> str:
    document_list = report.source_documents or []
    point_index = {item.point_id: item for item in report.review_points}
    formal_included = [
        item for item in report.formal_adjudication if item.included_in_formal
    ]
    formal_manual = [
        item for item in report.formal_adjudication if item.disposition.value == "manual_confirmation"
    ]

    lines = [
        "# 招标文件审查意见书",
        "",
        "## 一、审查对象",
        "",
        f"本次审查对象为《{report.file_info.document_name}》。",
    ]
    if document_list:
        lines.append("联合审查材料包括：")
        for item in document_list:
            lines.append(f"- {item.document_name}（{item.source_format}）")
    lines.extend(
        [
            "",
            "## 二、审查范围",
            "",
            f"根据当前提交材料，审查范围为：{report.file_info.review_scope}",
            "",
            "## 三、审查结论",
            "",
            f"经按既定规则链路、专项检查、一致性检查及必要的 LLM 语义复核进行审查，初步结论为：{report.overall_conclusion.value}。",
            f"摘要如下：{report.summary}",
            "",
            "## 四、主要审查意见",
            "",
        ]
    )

    if not formal_included and not formal_manual:
        lines.append("本次审查未形成可直接写入正式意见的确认问题项。")
    if formal_included:
        lines.append("### （一）高风险问题")
        for index, adjudication in enumerate(formal_included, start=1):
            point = point_index.get(adjudication.point_id)
            if point is None:
                continue
            lines.append(f"{index}. [{point.catalog_id}] {point.title}")
            lines.append(f"问题说明：{point.rationale}")
            lines.append(f"事实要件：{adjudication.applicability_summary}")
            lines.append(f"证据摘录：{adjudication.primary_quote or '当前未形成稳定原文摘录。'}")
            if point.legal_basis:
                basis_text = "；".join(
                    f"{item.source_name}{(' ' + item.article_hint) if item.article_hint else ''}：{item.summary}"
                    for item in point.legal_basis
                )
                lines.append(f"依据提示：{basis_text}")
            lines.append("处理建议：建议按 formal 审查意见优先整改，并复核关联条款及附件。")
            lines.append("")

    if formal_manual:
        lines.append("### （二）待进一步核定的问题")
        for index, adjudication in enumerate(formal_manual, start=1):
            point = point_index.get(adjudication.point_id)
            if point is None:
                continue
            lines.append(f"{index}. [{point.catalog_id}] {point.title}")
            lines.append(f"问题说明：{point.rationale}")
            lines.append(f"待核定原因：{adjudication.rationale}")
            lines.append(f"要件判断：{adjudication.applicability_summary}")
            lines.append("")

    lines.extend(
        [
            "## 五、修改建议",
            "",
        ]
    )
    if report.recommendations:
        for index, item in enumerate(report.recommendations, start=1):
            lines.append(f"{index}. {item.related_issue}：{item.suggestion}")
    else:
        lines.append("建议结合正式发布版本再做一次发布前复核。")

    lines.extend(
        [
            "",
            "## 六、人工复核提示",
            "",
        ]
    )
    if report.high_risk_review_items:
        lines.append("高风险复核事项：")
        for item in report.high_risk_review_items:
            lines.append(f"- {item.title}：{item.reason}")
    if report.pending_confirmation_items:
        lines.append("待确认事项：")
        for item in report.pending_confirmation_items:
            lines.append(f"- {item.title}：{item.reason}")
    if not report.high_risk_review_items and not report.pending_confirmation_items and not report.manual_review_queue:
        lines.append("当前未形成单独的人工复核事项。")
    if report.manual_review_queue:
        lines.append("基础人工复核队列：")
        for item in report.manual_review_queue:
            lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## 七、审查边界说明",
            "",
            report.file_info.review_boundary,
        ]
    )
    if report.parse_result.warnings:
        lines.append("另有以下解析提示需注意：")
        for item in report.parse_result.warnings:
            lines.append(f"- {item}")
    if report.llm_warnings:
        lines.append("LLM 增强提示：")
        for item in report.llm_warnings:
            lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "本意见书为基于当前提交材料形成的结构化审查意见，供采购人修改文件和复核使用。",
        ]
    )
    return "\n".join(lines)


def _build_formal_review_items(report: ReviewReport) -> list[dict[str, str]]:
    point_index = {item.point_id: item for item in report.review_points}
    items: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for adjudication in report.formal_adjudication:
        if not adjudication.included_in_formal:
            continue
        point = point_index.get(adjudication.point_id)
        if point is None or point.severity.value not in {"critical", "high"}:
            continue
        title = point.title.strip()
        section_hint = adjudication.section_hint or "未明确定位"
        quote = adjudication.primary_quote or "当前自动抽取未定位到可直接引用的原文。"
        basis_text = (
            "；".join(
                f"{item.source_name}{(' ' + item.article_hint) if item.article_hint else ''}：{item.summary}"
                for item in point.legal_basis
            )
            or "当前结果未自动挂接明确法规依据，建议结合原始条款进一步复核。"
        )
        dedupe_key = f"{section_hint}|{quote}"
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        issue_type = point.dimension or "高风险问题"
        compliance = _build_compliance_judgment(point.status.value)
        items.append(
            {
                "问题标题": title,
                "条款位置": section_hint,
                "原文摘录": quote,
                "问题类型": issue_type,
                "风险等级": "高风险" if point.severity.value == "high" else "严重风险",
                "合规判断": f"{compliance}；要件判断：{adjudication.applicability_summary}",
                "法律/政策依据": basis_text,
            }
        )
    return items


def _build_review_review_items(report: ReviewReport) -> list[dict[str, str]]:
    point_index = {item.point_id: item for item in report.review_points}
    formal_titles = {item.title.strip() for item in report.formal_adjudication if item.included_in_formal}
    formal_families = {_review_family_key(title) for title in formal_titles}
    items: list[dict[str, str]] = []
    seen_families: set[str] = set()
    for adjudication in report.formal_adjudication:
        if not adjudication.recommended_for_review:
            continue
        point = point_index.get(adjudication.point_id)
        if point is None or point.severity.value not in {"critical", "high"}:
            continue
        title = point.title.strip()
        if not title or title in formal_titles:
            continue
        family_key = _review_family_key(title)
        if family_key in formal_families or family_key in seen_families:
            continue
        section_hint = adjudication.section_hint or "未明确定位"
        quote = adjudication.primary_quote or "当前自动抽取未定位到可直接引用的原文。"
        if _should_suppress_review_item(title, quote, adjudication.review_reason, formal_families):
            continue
        basis_text = (
            "；".join(
                f"{item.source_name}{(' ' + item.article_hint) if item.article_hint else ''}：{item.summary}"
                for item in point.legal_basis
            )
            or "当前结果未自动挂接明确法规依据，建议结合原始条款进一步复核。"
        )
        seen_families.add(family_key)
        items.append(
            {
                "问题标题": title,
                "条款位置": section_hint,
                "原文摘录": quote,
                "问题类型": point.dimension or "建议复核问题",
                "风险等级": "建议复核",
                "合规判断": f"{adjudication.review_reason or '当前风险方向已识别，但正式定性条件尚未闭合。'}；要件判断：{adjudication.applicability_summary}",
                "法律/政策依据": basis_text,
            }
        )
    items.sort(key=lambda item: (item["风险等级"], item["问题标题"]))
    return items[:8]


def _review_family_key(title: str) -> str:
    family_rules = [
        ("policy_price", ["价格扣除", "中小企业"]),
        ("scoring_quant", ["方案评分", "量化不足", "评分分档主观性", "评分量化"]),
        ("scoring_weight", ["证书类评分分值偏高", "检测报告负担", "证书检测报告及财务指标权重合理性复核", "行业无关证书", "财务指标"]),
        ("contract_template", ["合同文本存在明显模板残留", "成果模板", "模板残留"]),
        ("contract_single_party", ["单方解释", "单方决定", "采购人意见为准"]),
        ("structure_mismatch", ["项目属性", "合同类型", "持续性作业服务", "结构错配"]),
        ("prudential", ["需求调查", "专家论证", "程序审慎性"]),
    ]
    for family, tokens in family_rules:
        if any(token in title for token in tokens):
            return family
    return title


def _should_suppress_review_item(
    title: str,
    quote: str,
    review_reason: str,
    formal_families: set[str],
) -> bool:
    if quote != "当前自动抽取未定位到可直接引用的原文。" and not evidence_supports_title(title, quote):
        if not any(token in title for token in ["需求调查", "专家论证", "程序审慎性"]):
            return True
    if quote == "当前自动抽取未定位到可直接引用的原文。":
        if _review_family_key(title) in formal_families:
            return True
        if any(token in title for token in ["评审方法出现但评分标准不够清晰", "指定品牌/原厂限制", "产地厂家商标限制", "联合体/分包", "服务项目声明函类型"]):
            return True
    if title.startswith("服务项目") and "货物" in quote:
        return True
    if title in {"发现潜在限制性竞争表述", "尾款支付与考核条款联动风险", "扣款机制可能过度依赖单方考核"}:
        return True
    if any(token in review_reason for token in ["镜像重复", "与 formal 同题", "主证据代表性不足"]) and _review_family_key(title) in formal_families:
        return True
    return False


def _build_compliance_judgment(point_status: str) -> str:
    if point_status == "confirmed":
        return "经系统规则审查，相关条款存在明显不合规风险，原则上不应直接保留。"
    if point_status == "suspected":
        return "相关条款存在较高合规风险，建议按不利于合规的口径先行整改并复核。"
    if point_status == "manual_confirmation":
        return "当前条款存在高风险信号，但仍需结合完整附件或上下文进一步核定。"
    return "相关条款存在高风险合规疑点，建议优先整改。"


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

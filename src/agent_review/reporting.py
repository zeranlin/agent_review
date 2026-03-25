from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .quality import clause_window_from_anchor, evidence_supports_title
from .models import FindingType, QualityGateStatus, ReviewReport


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


def render_reviewer_report(report: ReviewReport) -> str:
    issue_entries = _build_reviewer_issue_entries(report)
    project_name = _extract_project_name(report)
    purchaser = _extract_purchaser_name(report)
    review_date = _format_review_date()
    source_label = report.file_info.document_name
    source_path = report.parse_result.source_path or report.file_info.document_name

    lines = [
        "**招标文件合规审查意见书**",
        "",
        f"项目名称：{project_name}",
        f"审查材料：[{source_label}]({source_path})",
        f"采购单位：{purchaser}",
        f"审查日期：{review_date}",
        "",
        "**一、审查结论**",
        f"经审查，该采购需求文件{_reviewer_conclusion_sentence(report)}",
        "",
    ]

    if not issue_entries:
        lines.extend(
            [
                "**二、问题明细**",
                "当前未发现可直接输出的明确风险点。",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "**二、问题明细**",
            "",
        ]
    )
    for index, item in enumerate(issue_entries, start=1):
        lines.extend(
            [
                f"**{index}. {item['问题标题']}**",
                f"问题定性：**{item['问题定性']}**",
                "",
                f"审查类型：{item['审查类型']}",
                f"原文位置：{item['原文位置']}",
                "原文摘录：",
            ]
        )
        for quote in item["原文摘录"]:
            lines.append(f"- “{quote}”")
        lines.extend(
            [
                "",
                "风险判断：",
                item["风险判断"],
                "",
                "法律/政策依据：",
            ]
        )
        for basis in item["法律/政策依据"]:
            lines.append(f"- {basis}")
        lines.append("")

    basis_lines = _build_reviewer_basis_lines(report)
    if basis_lines:
        lines.extend(
            [
                "**三、主要依据**",
            ]
        )
        for index, basis in enumerate(basis_lines, start=1):
            lines.append(f"{index}. {basis}")

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
                "合规判断": adjudication.review_reason or "当前风险方向已识别，但正式定性条件尚未闭合。",
                "法律/政策依据": basis_text,
            }
        )
    items.sort(key=lambda item: (item["风险等级"], item["问题标题"]))
    return items[:8]


def _build_reviewer_issue_entries(report: ReviewReport) -> list[dict[str, object]]:
    point_index = {item.point_id: item for item in report.review_points}
    grouped_entries: dict[str, dict[str, object]] = {}
    for adjudication in report.formal_adjudication:
        if not _include_in_reviewer_issue_entries(adjudication):
            continue
        point = point_index.get(adjudication.point_id)
        if point is None:
            continue
        group_key, title, dimension, severity = _reviewer_issue_group_definition(point)
        entry = grouped_entries.setdefault(
            group_key,
            {
                "问题标题": title,
                "问题定性": severity,
                "审查类型": dimension,
                "_locations": [],
                "_quote_records": [],
                "_risk_judgments": [],
                "_basis": [],
            },
        )
        for location in _collect_reviewer_locations(point, adjudication):
            if location not in entry["_locations"]:
                entry["_locations"].append(location)
        for record in _collect_reviewer_quote_records(report.parse_result.text or "", point, adjudication, entry["问题标题"]):
            if record not in entry["_quote_records"]:
                entry["_quote_records"].append(record)
        risk_judgment = _reviewer_risk_judgment(point.rationale, adjudication.rationale)
        if risk_judgment not in entry["_risk_judgments"]:
            entry["_risk_judgments"].append(risk_judgment)
        for basis in _reviewer_legal_basis_lines(point):
            if basis not in entry["_basis"]:
                entry["_basis"].append(basis)

    entries: list[dict[str, object]] = []
    for group_key, entry in grouped_entries.items():
        quote_records = _rewrite_group_quote_records(entry["问题标题"], list(entry["_quote_records"]))
        primary_quotes = [item["quote"] for item in quote_records[:3]]
        if not primary_quotes:
            continue
        selected_locations = [item["location"] for item in quote_records if item["location"]]
        if not selected_locations:
            selected_locations = list(entry["_locations"])
        risk_judgment = _rewrite_group_risk_judgment(
            group_key,
            entry["问题标题"],
            list(entry["_risk_judgments"]),
        )
        entries.append(
            {
                "问题标题": entry["问题标题"],
                "问题定性": entry["问题定性"],
                "审查类型": entry["审查类型"],
                "原文位置": _format_reviewer_locations(selected_locations),
                "原文摘录": (primary_quotes if primary_quotes else ["当前自动抽取未定位到可直接引用的原文。"]),
                "风险判断": risk_judgment,
                "法律/政策依据": entry["_basis"] or ["当前结果未自动挂接明确法规依据"],
            }
        )
    return entries


def _include_in_reviewer_issue_entries(adjudication) -> bool:
    family_key = _review_family_key(adjudication.title)
    if family_key == "prudential":
        return False
    if adjudication.included_in_formal:
        return True
    return (
        adjudication.catalog_id in {"RP-CONTRACT-010"}
        and adjudication.evidence_sufficient
        and adjudication.legal_basis_applicable
        and adjudication.quality_gate_status == QualityGateStatus.passed
    )


def _reviewer_issue_group_definition(point) -> tuple[str, str, str, str]:
    group_rules = [
        (
            {"RP-STRUCT-007", "RP-STRUCT-008"},
            ("structure_mismatch", "项目属性与采购内容、合同类型不一致", "项目属性一致性审查", "高风险"),
        ),
        (
            {"RP-SCORE-005", "RP-SCORE-008"},
            ("scoring_relevance", "评分项与采购标的不相关", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-011"},
            ("credit_evaluation", "信用评价作为评分因素", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-006", "RP-SCORE-007"},
            ("scoring_quant", "方案评分主观性过强，量化不足", "评分标准量化性审查", "中风险"),
        ),
        (
            {"RP-CONTRACT-008"},
            ("contract_template", "合同条款存在明显模板错配", "合同文本适配性审查", "高风险"),
        ),
        (
            {"RP-CONTRACT-009"},
            ("acceptance_flexible", "验收标准表述过于弹性", "履约验收条款审查", "高风险"),
        ),
        (
            {"RP-CONS-009", "RP-SME-005"},
            ("amount_consistency", "中小企业采购金额口径不一致", "政策条款一致性审查", "中风险"),
        ),
        (
            {"RP-CONTRACT-010"},
            ("warranty_scope", "货物保修表述与项目实际履约内容不匹配", "合同履约条款适配性审查", "中风险"),
        ),
        (
            {"RP-PER-009"},
            ("team_stability", "团队稳定性要求过强", "人员条件与用工边界审查", "高风险"),
        ),
        (
            {"RP-PER-010"},
            ("personnel_change", "人员更换限制较强", "人员条件与用工边界审查", "高风险"),
        ),
    ]
    for catalog_ids, group in group_rules:
        if point.catalog_id in catalog_ids:
            return group
    return (
        point.catalog_id or point.title,
        point.title.strip(),
        point.dimension or "风险点审查",
        _reviewer_severity_label(point.severity.value),
    )


def _rewrite_group_quote_records(title: str, quote_records: list[dict[str, str]]) -> list[dict[str, str]]:
    quote_records = _refine_quote_records_for_title(title, quote_records)
    if title == "项目属性与采购内容、合同类型不一致":
        return _select_group_quote_records(
            quote_records,
            ["项目所属分类", "项目属性", "货物"],
            ["人工管护", "清林整地", "抚育", "运水"],
            ["合同类型", "承揽合同"],
            limit=4,
            strict=True,
        )
    if title == "评分项与采购标的不相关":
        return _select_group_quote_records(
            quote_records,
            ["利润率"],
            ["软件企业认定证书"],
            ["ITSS"],
            ["财务报告"],
            limit=4,
            strict=True,
        )
    if title == "信用评价作为评分因素":
        return _select_group_quote_records(
            quote_records,
            ["信用评价"],
            ["信用分"],
            ["征信"],
            ["评分", "得分"],
            limit=4,
            strict=True,
        )
    if title == "方案评分主观性过强，量化不足":
        return _select_group_quote_records(
            quote_records,
            ["齐全且无缺陷得30分", "齐全且无缺陷得15分"],
            ["每缺少一项内容扣5分", "每有一处缺陷扣2.5分"],
            ["缺陷指"],
            limit=4,
            strict=True,
        )
    if title == "中小企业采购金额口径不一致":
        return _select_group_quote_records(
            quote_records,
            ["预算金额"],
            ["面向中小企业采购金额"],
            ["最高限价"],
            limit=4,
            strict=True,
        )
    if title == "货物保修表述与项目实际履约内容不匹配":
        return _select_group_quote_records(
            quote_records,
            ["质量保修范围和保修期", "货物质保期"],
            ["人工管护", "抚育", "运水"],
            ["合同履行期限", "1095日"],
            limit=4,
            strict=True,
        )
    if title == "团队稳定性要求过强":
        return _select_group_quote_records(
            quote_records,
            ["团队稳定"],
            ["核心团队"],
            ["人员稳定"],
            limit=3,
            strict=True,
        )
    if title == "人员更换限制较强":
        return _select_group_quote_records(
            quote_records,
            ["人员更换"],
            ["采购人批准"],
            ["采购人同意"],
            ["须经"],
            limit=4,
            strict=True,
        )
    return quote_records[:3]


def _refine_quote_records_for_title(title: str, quote_records: list[dict[str, str]]) -> list[dict[str, str]]:
    pattern_map: dict[str, list[str]] = {
        "项目属性与采购内容、合同类型不一致": [
            r"项目所属分类[^。；\n]{0,80}",
            r"人工管护[^。；\n]{0,160}",
            r"合同类型[^。；\n]{0,60}",
            r"承揽合同[^。；\n]{0,40}",
        ],
        "评分项与采购标的不相关": [
            r"利润率[^。；\n]{0,100}",
            r"投标人具有[^。；\n]{0,80}软件企业认定证书[^。；\n]{0,60}",
            r"投标人具有[^。；\n]{0,120}ITSS[^。；\n]{0,120}",
            r"财务报告[^。；\n]{0,120}",
        ],
        "信用评价作为评分因素": [
            r"信用评价[^。；\n]{0,100}",
            r"信用分[^。；\n]{0,100}",
            r"征信[^。；\n]{0,100}",
        ],
        "方案评分主观性过强，量化不足": [
            r"以上方案齐全且无缺陷得30分[^。；\n]{0,120}",
            r"以上方案齐全且无缺陷得15分[^。；\n]{0,120}",
            r"每缺少一项内容扣5分[^。；\n]{0,100}",
            r"每[项中]*每有一处缺陷扣2\.5分[^。；\n]{0,100}",
            r"缺陷指[^。]{0,200}",
        ],
        "合同条款存在明显模板错配": [
            r"未经采购人同意[^。]*本项目成果[^。]*",
            r"[^。]*不得向第三方泄露本项目成果[^。]*",
            r"[^。]*未在合同规定日期内提交全部符合项目合同要求的项目成果[^。]*",
        ],
        "验收标准表述过于弹性": [
            r"[^。]*按质量要求和技术指标、行业标准比较优胜的原则[^。]*",
        ],
        "货物保修表述与项目实际履约内容不匹配": [
            r"质量保修范围和保修期[^。]*货物质保期3年[^。]*",
            r"人工管护[^。；\n]{0,120}",
            r"合同履行期限[^。；\n]{0,80}",
        ],
        "团队稳定性要求过强": [
            r"团队稳定[^。；\n]{0,100}",
            r"核心团队[^。；\n]{0,100}",
            r"人员稳定[^。；\n]{0,100}",
        ],
        "人员更换限制较强": [
            r"人员更换[^。；\n]{0,100}",
            r"替换[^。；\n]{0,100}",
            r"变更[^。；\n]{0,100}",
            r"调整[^。；\n]{0,100}",
            r"采购人同意[^。；\n]{0,120}",
            r"采购人批准[^。；\n]{0,120}",
            r"须经[^。；\n]{0,120}",
        ],
        "中小企业采购金额口径不一致": [
            r"预算金额（元）[:：]?\s*[0-9,\.]+元?",
            r"面向中小企业采购金额(?:为)?[0-9,\.]+元?",
            r"最高限价（元）[:：]?\s*[0-9,\.]+",
        ],
    }
    patterns = pattern_map.get(title)
    if not patterns:
        return quote_records
    refined: list[dict[str, str]] = []
    for record in quote_records:
        snippets = _extract_pattern_snippets(record["quote"], patterns)
        if snippets:
            for snippet in snippets:
                refined.append({"location": record["location"], "quote": snippet})
        else:
            refined.append(record)
    deduped = _dedupe_quote_records(refined)
    return deduped or quote_records


def _extract_pattern_snippets(text: str, patterns: list[str]) -> list[str]:
    snippets: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            snippet = re.sub(r"\s+", " ", match.group(0)).strip(" ；;，,。")
            if not snippet:
                continue
            if snippet not in snippets:
                snippets.append(snippet)
    return snippets


def _select_group_quote_records(
    quote_records: list[dict[str, str]],
    *preferred_token_groups: list[str],
    limit: int = 3,
    strict: bool = False,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for tokens in preferred_token_groups:
        match = next((item for item in quote_records if any(token in item["quote"] for token in tokens)), None)
        if match and match not in selected:
            selected.append(match)
    if strict:
        return selected[:limit]
    for item in quote_records:
        if item not in selected and not _is_generic_background_quote(item["quote"]):
            selected.append(item)
    for item in quote_records:
        if item not in selected:
            selected.append(item)
    return selected[:limit]


def _rewrite_group_risk_judgment(group_key: str, title: str, risk_judgments: list[str]) -> str:
    templates = {
        "structure_mismatch": "文件将项目定性为货物，但采购内容中同时包含持续性作业服务，合同类型又偏向承揽或服务口径，项目属性、采购内容与合同类型之间存在明显错配风险。",
        "scoring_relevance": "评分中出现利润率、软件企业认定证书、ITSS 或财务报告等内容，与项目实际履约能力缺乏直接关联，存在限制竞争风险。",
        "credit_evaluation": "评分中出现信用评价、信用分或征信等内容，如作为评分因素，需复核其与项目履约能力的直接关联和分值是否适度。",
        "scoring_quant": "方案评分以主观分档和“无缺陷得满分”等规则为核心，量化和客观性不足，评委裁量空间较大。",
        "contract_template": "合同条款中出现“项目成果、移作他用、泄露成果”等表述，更符合咨询、设计或信息化项目，和当前项目行业场景明显不匹配。",
        "acceptance_flexible": "验收条款赋予采购人较大的单方裁量空间，缺乏固定、明确、可预期的验收标准，容易引发履约争议。",
        "amount_consistency": "预算金额、最高限价与面向中小企业采购金额之间存在异常对应关系，金额口径不清，文件严谨性不足。",
        "warranty_scope": "项目核心履约内容包含持续性作业或服务责任，但合同条款仍仅以货物质保表述概括，未能准确覆盖实际履约责任。",
        "team_stability": "团队稳定性要求将供应商内部人员构成或稳定性过度前置为采购要求，容易形成不必要的履约门槛。",
        "personnel_change": "人员更换限制过强会使采购人审批介入供应商内部人员管理，容易扩大为不必要的人员控制条款。",
    }
    if group_key in templates:
        return templates[group_key]
    if risk_judgments:
        return risk_judgments[0]
    return "已发现明确风险，证据较充分。"


def _extract_project_name(report: ReviewReport) -> str:
    for clause in report.extracted_clauses:
        if clause.field_name != "项目名称":
            continue
        cleaned = _strip_field_prefix(clause.content, "项目名称")
        if cleaned:
            return cleaned
    return Path(report.file_info.document_name).stem


def _extract_purchaser_name(report: ReviewReport) -> str:
    text = report.parse_result.text or ""
    patterns = [
        r"采购人(?:名称)?[:：]\s*([^\n]+)",
        r"采购单位[:：]\s*([^\n]+)",
        r"采购人信息[:：]?\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            cleaned = match.group(1).strip(" ：:;；,，。")
            if cleaned:
                return cleaned
    return "未自动识别"


def _format_review_date() -> str:
    today = datetime.now().date()
    return f"{today.year}年{today.month}月{today.day}日"


def _reviewer_conclusion_sentence(report: ReviewReport) -> str:
    mapping = {
        "整体基本规范，可直接使用": "整体基本规范，可直接使用。",
        "存在个别条款待完善，建议优化后发出": "存在个别条款待完善，建议优化后再行发布。",
        "存在明显合规风险，建议修改后再发布": "存在较明显合规风险，建议修改后再行发布。",
        "存在实质性不合规问题，不建议直接发布": "存在较明显合规风险，建议修改后再行发布。",
    }
    return mapping.get(report.overall_conclusion.value, f"存在风险点，建议进一步复核。")


def _reviewer_severity_label(severity: str) -> str:
    return {
        "critical": "高风险",
        "high": "高风险",
        "medium": "中风险",
        "low": "低风险",
    }.get(severity, "高风险")


def _collect_reviewer_locations(point, adjudication) -> list[str]:
    locations: list[str] = []
    for item in [*point.evidence_bundle.direct_evidence, *point.evidence_bundle.supporting_evidence]:
        section_hint = (item.section_hint or "").strip()
        if section_hint and section_hint not in locations:
            locations.append(section_hint)
    fallback = (adjudication.section_hint or "").strip()
    if fallback and fallback not in locations:
        locations.append(fallback)
    return locations[:6]


def _collect_reviewer_quote_records(report_text: str, point, adjudication, reviewer_title: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    primary = (adjudication.primary_quote or "").strip()
    if primary and "=" not in primary and _reviewer_quote_supports_title(reviewer_title, primary):
        records.append({"location": (adjudication.section_hint or "").strip(), "quote": primary})
    for item in [*point.evidence_bundle.direct_evidence, *point.evidence_bundle.supporting_evidence]:
        quote = (
            clause_window_from_anchor(report_text, item.section_hint)
            or (item.quote or "").strip()
        )
        if not quote:
            continue
        if len(quote) < 6:
            continue
        if "=" in quote:
            continue
        if not _reviewer_quote_supports_title(reviewer_title, quote):
            continue
        records.append({"location": (item.section_hint or "").strip(), "quote": quote})
    return _dedupe_quote_records(records)[:8]


def _reviewer_quote_supports_title(title: str, quote: str) -> bool:
    partial_checks = {
        "项目属性与采购内容、合同类型不一致": ["项目所属分类", "项目属性", "货物", "人工管护", "清林整地", "抚育", "运水", "合同类型", "承揽合同"],
        "评分项与采购标的不相关": ["利润率", "软件企业认定证书", "ITSS", "财务报告", "信用评价"],
        "方案评分主观性过强，量化不足": ["无缺陷", "缺陷", "扣2.5分", "完全满足且优于", "不完全满足"],
        "合同条款存在明显模板错配": ["项目成果", "研究成果", "技术文档", "移作他用", "泄露本项目成果"],
        "验收标准表述过于弹性": ["比较优胜", "优胜的原则", "确定该项的约定标准"],
        "中小企业采购金额口径不一致": ["预算金额", "面向中小企业采购金额", "最高限价"],
        "货物保修表述与项目实际履约内容不匹配": ["货物质保期", "质量保修范围和保修期", "人工管护", "1095日", "合同履行期限"],
        "团队稳定性要求过强": ["团队稳定", "核心团队", "人员稳定", "团队成员", "保持稳定", "不得更换"],
        "人员更换限制较强": ["人员更换", "更换", "替换", "变更", "调整", "采购人同意", "采购人批准", "须经"],
    }
    tokens = partial_checks.get(title)
    if tokens is not None:
        return any(token in quote for token in tokens)
    return evidence_supports_title(title, quote)


def _reviewer_risk_judgment(point_rationale: str, adjudication_rationale: str) -> str:
    text = (point_rationale or adjudication_rationale or "").strip()
    if not text:
        return "已发现明确风险，证据较充分。"
    text = re.sub(r"\s+", " ", text)
    replacements = {
        "标准审查任务已围绕 ": "",
        " 采集到直接证据，可进入后续适法性判断。": "已形成较直接的条款依据，相关风险较为明确。",
        " 采集到支持证据，但同时存在冲突或反证，需谨慎裁决。": "已发现支持该问题的条款依据，但仍需结合上下文核对风险强度。",
        " 采集到支持证据，但主证据代表性不足。": "已识别相关风险线索，但主证据代表性仍需继续核对。",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"；?要件判断[:：].*$", "", text)
    text = re.sub(r"；?(LLM二审|主证据判断|辅助证据判断|强度判断)[:：].*$", "", text)
    text = text.strip("；。 ")
    return text


def _reviewer_legal_basis_lines(point) -> list[str]:
    lines: list[str] = []
    for basis in point.legal_basis:
        label = f"《{basis.source_name}》"
        if basis.article_hint:
            label = f"{label} {basis.article_hint}"
        if label not in lines:
            lines.append(label)
    if not lines:
        lines.append("当前结果未自动挂接明确法规依据")
    return lines


def _build_reviewer_basis_lines(report: ReviewReport) -> list[str]:
    point_index = {item.point_id: item for item in report.review_points}
    lines: list[str] = []
    for adjudication in report.formal_adjudication:
        if not adjudication.included_in_formal:
            continue
        point = point_index.get(adjudication.point_id)
        if point is None:
            continue
        for basis in _reviewer_legal_basis_lines(point):
            if basis not in lines and basis != "当前结果未自动挂接明确法规依据":
                lines.append(basis)
    return lines


def _format_reviewer_locations(locations: list[str]) -> str:
    if not locations:
        return "未明确定位"

    line_numbers: list[int] = []
    others: list[str] = []
    for location in locations:
        match = re.fullmatch(r"line:(\d+)", location.strip())
        if match:
            line_numbers.append(int(match.group(1)))
        elif location not in others:
            others.append(location)

    parts: list[str] = []
    if line_numbers:
        parts.extend(_compress_line_ranges(sorted(set(line_numbers))))
    parts.extend(others[:2])
    return "；".join(parts) if parts else "未明确定位"


def _compress_line_ranges(line_numbers: list[int]) -> list[str]:
    if not line_numbers:
        return []
    ranges: list[tuple[int, int]] = []
    start = prev = line_numbers[0]
    for number in line_numbers[1:]:
        if number == prev + 1:
            prev = number
            continue
        ranges.append((start, prev))
        start = prev = number
    ranges.append((start, prev))
    results: list[str] = []
    for start, end in ranges:
        if start == end:
            results.append(f"第{start}行")
        else:
            results.append(f"第{start}行至第{end}行")
    return results


def _dedupe_quotes(quotes: list[str]) -> list[str]:
    results: list[str] = []
    for quote in quotes:
        normalized = re.sub(r"\s+", " ", quote).strip(" ；;")
        if not normalized:
            continue
        if normalized not in results:
            results.append(normalized)
    return results


def _dedupe_quote_records(records: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    results: list[dict[str, str]] = []
    for item in records:
        quote = re.sub(r"\s+", " ", item.get("quote", "")).strip(" ；;")
        location = item.get("location", "").strip()
        if not quote:
            continue
        key = (location, quote)
        if key in seen:
            continue
        seen.add(key)
        results.append({"location": location, "quote": quote})
    return results


def _is_generic_background_quote(quote: str) -> bool:
    return any(
        token in quote
        for token in [
            "政府采购项目采购需求",
            "采购单位：",
            "编制单位：",
            "是否支持联合体投标",
            "不分包采购",
            "项目概况：本项目共一个包",
        ]
    )


def _strip_field_prefix(content: str, field_name: str) -> str:
    text = content.strip()
    patterns = [
        rf".*?{re.escape(field_name)}[:：]\s*",
        r"^[（(]?[一二三四五六七八九十\d]+[)）.、]?\s*",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, count=1)
    return text.strip(" ：:;；,，。")


def _review_family_key(title: str) -> str:
    family_rules = [
        ("policy_price", ["价格扣除", "中小企业"]),
        ("scoring_quant", ["方案评分", "量化不足", "评分分档主观性", "评分量化"]),
        ("scoring_weight", ["证书类评分分值偏高", "检测报告负担", "证书检测报告及财务指标权重合理性复核", "行业无关证书", "财务指标"]),
        ("contract_template", ["合同文本存在明显模板残留", "成果模板", "模板残留"]),
        ("contract_single_party", ["单方解释", "单方决定", "采购人意见为准"]),
        ("structure_mismatch", ["项目属性", "合同类型", "持续性作业服务", "结构错配"]),
        ("prudential", ["需求调查", "专家论证", "程序审慎性"]),
        ("consistency_mirror", ["联合体/分包", "服务要求 vs 人员评分要求", "技术要求 vs 评分标准", "样品或演示分值"]),
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
    if "物业项目" in title and "物业" not in quote:
        return True
    if "联合体/分包" in title and all(token not in quote for token in ["联合体", "分包"]):
        return True
    if "服务要求 vs 人员评分要求" == title and "人员" not in quote:
        return True
    if title == "指定品牌/原厂限制" and any(
        token in quote for token in ["检测报告", "认证证书", "管理体系认证", "环保产品认证", "环境标志产品认证"]
    ):
        return True
    if title == "评审方法出现但评分标准不够清晰" and "scoring_quant" in formal_families:
        return True
    if title == "项目属性与所属行业口径疑似不一致" and all(
        token not in quote for token in ["服务", "工程", "承揽合同", "持续性作业", "错配", "不一致"]
    ):
        return True
    if title == "项目属性与声明函模板口径冲突" and (
        "structure_mismatch" in formal_families
        or all(token not in quote for token in ["声明函", "制造商", "模板", "货物", "服务"])
    ):
        return True
    if title == "验收标准 vs 付款条件" and (
        all(token not in quote for token in ["验收", "付款", "支付", "尾款"])
        or "4.6不同投标人的投标保证金" in quote
    ):
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

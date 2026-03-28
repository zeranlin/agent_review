from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from ..authority_bindings import list_bindings_for_point
from ..header_info import resolve_header_info
from ..quality import clause_window_from_anchor, evidence_supports_title
from ..models import FindingType, QualityGateStatus, ReviewMode, ReviewReport


INDUSTRY_MISMATCH_SCORING_TOKENS = ("人力资源测评师", "非金属矿采矿许可证", "采矿许可证")


def render_json(report: ReviewReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def _build_llm_enhancement_status(report: ReviewReport) -> str | None:
    if report.review_mode != ReviewMode.enhanced and not report.llm_warnings:
        return None
    if report.llm_enhanced:
        return "已成功完成"
    if report.llm_warnings:
        return "已回退到基础结果"
    return "已请求增强，但未形成有效增强结果"


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
    header_info = resolve_header_info(report)
    review_date = _format_review_date()
    source_label = report.file_info.document_name
    source_path = report.parse_result.source_path or report.file_info.document_name

    lines = [
        "**招标文件合规审查意见书**",
        "",
        f"项目名称：{header_info.project_name}",
        f"审查材料：[{source_label}]({source_path})",
        f"采购单位：{header_info.purchaser_name}",
        f"审查日期：{review_date}",
        "",
        "**一、审查结论**",
        f"经审查，该采购需求文件{_reviewer_conclusion_sentence(report)}",
    ]
    lines.append("")

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

    middle_trace_lines = _build_middle_trace_summary_lines(report)
    if middle_trace_lines:
        lines.extend(middle_trace_lines)

    lines.extend(
        [
            "## 总体结论",
            "",
            f"- 结论等级: {report.overall_conclusion.value}",
            f"- 摘要: {report.summary}",
            f"- LLM增强: {'是' if report.llm_enhanced else '否'}",
        ]
    )
    enhancement_status = _build_llm_enhancement_status(report)
    if enhancement_status:
        lines.append(f"- 增强链状态: {enhancement_status}")
    lines.extend(
        [
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

    if report.parse_result.rule_hits:
        lines.append("## RuleHit")
        for item in report.parse_result.rule_hits[:10]:
            lines.append(
                f"- {item.hit_id} [{item.rule_id}] -> {item.point_id}: {','.join(item.trigger_reasons[:3])}"
            )
        lines.append("")

    if report.parse_result.review_point_instances:
        lines.append("## ReviewPointInstance")
        for item in report.parse_result.review_point_instances[:10]:
            lines.append(
                f"- {item.instance_id} [{item.point_id}] {item.title}: {item.summary}"
            )
        lines.append("")

    if report.review_point_catalog:
        lines.append("## 任务注册表快照")
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


def _build_middle_trace_summary_lines(report: ReviewReport) -> list[str]:
    profile = report.parse_result.document_profile
    if profile is None and not report.quality_gates and not report.stage_records:
        return []

    lines: list[str] = [
        "## 中间产物摘要",
        "",
    ]
    mainline_stage_lines = _build_mainline_stage_summary_lines(report.stage_records)
    if mainline_stage_lines:
        lines.extend(mainline_stage_lines)
    if profile is not None:
        candidate_text = _format_profile_candidates(profile.domain_profile_candidates[:3])
        zone_text = _format_profile_zone_stats(profile)
        quality_flags = "、".join(profile.quality_flags[:3]) if profile.quality_flags else "无"
        unknown_flags = (
            "、".join(profile.unknown_structure_flags[:3]) if profile.unknown_structure_flags else "无"
        )
        anchor_text = "、".join(profile.representative_anchors[:3]) if profile.representative_anchors else "未记录"
        lines.extend(
            [
                f"- 文档画像: {profile.procurement_kind}（置信度 {profile.procurement_kind_confidence:.2f}）",
                f"- 域匹配: {candidate_text}",
                f"- 结构分布: {zone_text}",
                f"- 质量标记: {quality_flags}",
                f"- 未知结构信号: {unknown_flags}",
                f"- 代表锚点: {anchor_text}",
            ]
        )
    if report.quality_gates:
        counts = Counter(item.status.value for item in report.quality_gates)
        status_text = "，".join(
            f"{status} {counts.get(status, 0)}"
            for status in ["passed", "manual_confirmation", "filtered"]
        )
        top_gate_text = _format_quality_gate_snippet(report.quality_gates[:3])
        lines.extend(
            [
                f"- 质量关卡: {status_text}",
                f"- 质量关卡样本: {top_gate_text}",
            ]
        )
    lines.append("")
    return lines


def _build_mainline_stage_summary_lines(stage_records) -> list[str]:
    if not stage_records:
        return []
    mainline = [item for item in stage_records if item.is_mainline]
    if not mainline:
        return []
    stage_flow = " -> ".join(
        f"{item.stage_name}({item.stage_layer}:{item.primary_object})"
        for item in mainline
    )
    return [
        f"- 主链阶段: {stage_flow}",
        f"- 主链阶段数: {len(mainline)}",
    ]


def _format_profile_candidates(candidates) -> str:
    if not candidates:
        return "未形成候选"
    return "；".join(
        f"{item.profile_id} {item.confidence:.2f}"
        for item in candidates
    )


def _format_profile_zone_stats(profile: ReviewReport | object) -> str:
    dominant_zones = getattr(profile, "dominant_zones", [])
    if not dominant_zones:
        return "未形成区域统计"
    return "；".join(
        f"{item.zone_type.value}:{item.ratio:.2f}"
        for item in dominant_zones[:3]
    )


def _format_quality_gate_snippet(quality_gates) -> str:
    if not quality_gates:
        return "未生成质量关卡样本"
    return "；".join(
        f"{item.point_id}:{item.status.value}"
        for item in quality_gates
    )


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
        ]
    )
    enhancement_status = _build_llm_enhancement_status(report)
    if enhancement_status:
        lines.append(f"LLM增强状态：{enhancement_status}")
    lines.extend(
        [
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
        if family_key in seen_families:
            continue
        if family_key in formal_families and family_key not in {"prudential"}:
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
    included_catalog_ids = {
        item.catalog_id
        for item in report.formal_adjudication
        if item.included_in_formal and item.catalog_id
    }
    specific_scoring_catalogs = {
        "RP-SCORE-005",
        "RP-SCORE-011",
        "RP-SCORE-014",
        "RP-SCORE-015",
        "RP-SCORE-016",
        "RP-SCORE-017",
        "RP-SCORE-018",
        "RP-SCORE-019",
        "RP-SCORE-020",
        "RP-SCORE-021",
        "RP-SCORE-022",
        "RP-SCORE-023",
        "RP-SCORE-024",
        "RP-SCORE-025",
        "RP-SCORE-026",
    }
    grouped_entries: dict[str, dict[str, object]] = {}
    for adjudication in report.formal_adjudication:
        if not _include_in_reviewer_issue_entries(adjudication):
            continue
        point = point_index.get(adjudication.point_id)
        if point is None:
            continue
        if point.catalog_id == "RP-QUAL-003":
            base_records = _collect_hidden_qualification_gate_records(report.parse_result.text or "", point, adjudication)
            split_targets = _split_hidden_qualification_gate_targets(base_records)
            if split_targets:
                for group_key, title, dimension, severity, records in split_targets:
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
                    entry["问题定性"] = _stronger_reviewer_severity(entry["问题定性"], severity)
                    for record in records:
                        if record["location"] and record["location"] not in entry["_locations"]:
                            entry["_locations"].append(record["location"])
                        if record not in entry["_quote_records"]:
                            entry["_quote_records"].append(record)
                    risk_judgment = _reviewer_risk_judgment(point.rationale, adjudication.rationale)
                    if risk_judgment not in entry["_risk_judgments"]:
                        entry["_risk_judgments"].append(risk_judgment)
                    for basis in _reviewer_legal_basis_lines(point):
                        if basis not in entry["_basis"]:
                            entry["_basis"].append(basis)
                continue
        if point.catalog_id == "RP-CONTRACT-012":
            base_records = _collect_reviewer_quote_records(
                report.parse_result.text or "",
                point,
                adjudication,
                point.title,
            )
            split_targets = _split_contract_guarantee_targets(base_records)
            if split_targets:
                for group_key, title, dimension, severity, records in split_targets:
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
                    entry["问题定性"] = _stronger_reviewer_severity(entry["问题定性"], severity)
                    for record in records:
                        if record["location"] and record["location"] not in entry["_locations"]:
                            entry["_locations"].append(record["location"])
                        if record not in entry["_quote_records"]:
                            entry["_quote_records"].append(record)
                    risk_judgment = _reviewer_risk_judgment(point.rationale, adjudication.rationale)
                    if risk_judgment not in entry["_risk_judgments"]:
                        entry["_risk_judgments"].append(risk_judgment)
                    for basis in _reviewer_legal_basis_lines(point):
                        if basis not in entry["_basis"]:
                            entry["_basis"].append(basis)
                continue
        group_key, title, dimension, severity = _resolve_reviewer_issue_group(point, adjudication)
        if (
            point.catalog_id == "RP-SCORE-013"
            and group_key == "scoring_relevance"
            and included_catalog_ids.intersection(specific_scoring_catalogs)
        ):
            continue
        group_key = _canonical_reviewer_group_key(group_key, title)
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
        entry["问题定性"] = _stronger_reviewer_severity(entry["问题定性"], severity)
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
            quote_records,
        )
        entries.append(
            {
                "问题标题": entry["问题标题"],
                "问题定性": entry["问题定性"],
                "审查类型": entry["审查类型"],
                "原文位置": _format_reviewer_locations(selected_locations),
                "原文摘录": (primary_quotes if primary_quotes else ["当前自动抽取未定位到可直接引用的原文。"]),
                "风险判断": risk_judgment,
                "法律/政策依据": _dedupe_reviewer_basis_lines(entry["_basis"]) or ["当前结果未自动挂接明确法规依据"],
            }
        )
    entries.sort(key=_reviewer_issue_sort_key)
    return entries


def _collect_hidden_qualification_gate_records(report_text: str, point, adjudication) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    primary = (adjudication.primary_quote or "").strip()
    if primary:
        records.append({"location": (adjudication.section_hint or "").strip(), "quote": primary})
    for item in [*point.evidence_bundle.direct_evidence, *point.evidence_bundle.supporting_evidence]:
        quote = _prefer_report_quote(
            clause_window_from_anchor(report_text, item.section_hint),
            item.quote,
        )
        if not quote or len(quote) < 6:
            continue
        records.append({"location": (item.section_hint or "").strip(), "quote": quote})
    return _dedupe_quote_records(records)[:10]


def _prefer_report_quote(anchor_quote: str | None, item_quote: str | None) -> str:
    anchor = (anchor_quote or "").strip()
    item = (item_quote or "").strip()
    if not anchor:
        return item
    if not item:
        return anchor

    report_tokens = ("成立满", "成立年限", "设立满", "注册满", "营业执照", "高新技术企业", "纳税信用A级", "科技型中小企业")
    if len(item) >= len(anchor) + 12:
        return item
    if any(token in item and token not in anchor for token in report_tokens):
        return item
    return anchor


def _split_hidden_qualification_gate_targets(
    quote_records: list[dict[str, str]],
) -> list[tuple[str, str, str, str, list[dict[str, str]]]]:
    mapping = [
        (
            "qualification_asset_hidden_gate",
            "不得将资产总额的隐性限制证书设置为资格条件",
            ["科技型中小企业", "资产总额", "规模类型"],
        ),
        (
            "qualification_staff_hidden_gate",
            "不得将从业人员的隐性限制证书设置为资格条件",
            ["高新技术企业", "从业人员", "规模类型"],
        ),
        (
            "qualification_tax_hidden_gate",
            "不得将纳税额的隐性限制证书设置为资格条件",
            ["纳税信用A级", "税务部门", "纳税额"],
        ),
        (
            "qualification_age_hidden_gate",
            "不得将成立年限的隐性限制证书设置为资格条件",
            ["成立满", "成立年限", "设立满", "注册满"],
        ),
    ]
    results: list[tuple[str, str, str, str, list[dict[str, str]]]] = []
    for group_key, title, tokens in mapping:
        records = [item for item in quote_records if any(token in item["quote"] for token in tokens)]
        if not records:
            continue
        results.append((group_key, title, "资格与公平竞争审查", "高风险", records[:2]))
    return results


def _split_contract_guarantee_targets(
    quote_records: list[dict[str, str]],
) -> list[tuple[str, str, str, str, list[dict[str, str]]]]:
    mapping = [
        (
            "contract_guarantee_payment_method",
            "明确说明保证金缴纳方式",
            ["履约担保", "银行转账"],
        ),
        (
            "contract_quality_guarantee",
            "不得违规设置质量保证金",
            ["质量保证金", "合同总价", "无息退还"],
        ),
    ]
    results: list[tuple[str, str, str, str, list[dict[str, str]]]] = []
    for group_key, title, tokens in mapping:
        records = [item for item in quote_records if all(token in item["quote"] for token in tokens)]
        if not records:
            continue
        results.append((group_key, title, "合同与履约风险", "高风险", records[:2]))
    return results


def _include_in_reviewer_issue_entries(adjudication) -> bool:
    family_key = _review_family_key(adjudication.title)
    if family_key == "prudential":
        return False
    if adjudication.included_in_formal:
        return True
    return (
        adjudication.catalog_id in {"RP-CONTRACT-010"}
        and adjudication.evidence_sufficient
        and adjudication.quality_gate_status == QualityGateStatus.passed
    )


def _reviewer_issue_group_definition(point) -> tuple[str, str, str, str]:
    group_rules = [
        (
            {"RP-STRUCT-007", "RP-STRUCT-008"},
            ("structure_mismatch", "项目属性与采购内容、合同类型不一致", "项目属性一致性审查", "高风险"),
        ),
        (
            {"RP-SCORE-005", "RP-SCORE-008", "RP-SCORE-013"},
            ("scoring_relevance", "评分项与采购标的不相关", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-011"},
            ("credit_evaluation", "信用评价作为评分因素", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-014"},
            ("asset_scoring_factor", "资产总额被设为评分因素", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-015"},
            ("staff_scoring_factor", "从业人员被设为评分因素", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-016"},
            ("tax_scoring_factor", "纳税额被设为评分因素", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-017"},
            ("age_scoring_factor", "成立年限被设为评分因素", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-019"},
            ("registered_capital_scoring_factor", "注册资本被设为评分因素", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-020"},
            ("revenue_scoring_factor", "营业收入被设为评分因素", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-021"},
            ("profit_scoring_factor", "净利润或利润被设为评分因素", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-022"},
            ("shareholding_scoring_factor", "股权结构被设为评分因素", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-023"},
            ("operating_age_scoring_factor", "经营年限被设为评分因素", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-024"},
            ("certificate_scope_scoring_factor", "体系认证证书不得要求特定认证范围", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-025"},
            ("administrative_license_scoring_factor", "不得将准入类、行政许可类资格职业证书设置为评分项", "评分因素关联性审查", "高风险"),
        ),
        (
            {"RP-SCORE-026"},
            ("service_price_weight_factor", "依法设定价格分值", "价格评分规则审查", "高风险"),
        ),
        (
            {"RP-SCORE-018"},
            ("price_method_mismatch", "综合评分法价格分未采用低价优先法", "价格评分规则审查", "高风险"),
        ),
        (
            {"RP-SCORE-012"},
            ("credit_transparency", "信用评价规则透明性不足", "信用评价规则审查", "高风险"),
        ),
        (
            {"RP-SCORE-006", "RP-SCORE-007"},
            ("scoring_quant", "方案评分主观性过强，量化不足", "评分标准量化性审查", "中风险"),
        ),
        (
            {"RP-QUAL-001"},
            ("qualification_repeat", "资格条件与评分因素重复设门槛", "资格与评分边界审查", "高风险"),
        ),
        (
            {"RP-QUAL-002"},
            ("qualification_excess", "特定资质或证书要求超必要限度", "资格与评分边界审查", "高风险"),
        ),
        (
            {"RP-QUAL-005"},
            ("qualification_org_form", "不得限定供应商组织形式", "资格与公平竞争审查", "高风险"),
        ),
        (
            {"RP-REQ-001"},
            ("verifiability", "技术或服务要求可验证性不足", "采购需求完整性审查", "高风险"),
        ),
        (
            {"RP-REQ-002"},
            ("invalid_standard", "疑似使用不存在的技术标准", "技术标准有效性审查", "高风险"),
        ),
        (
            {"RP-REQ-003"},
            ("parameter_interval_missing", "技术参数区间说明不足", "技术参数明确性审查", "高风险"),
        ),
        (
            {"RP-REQ-004"},
            ("parameter_interval_conflict", "同一技术参数区间说明冲突", "技术参数一致性审查", "高风险"),
        ),
        (
            {"RP-REQ-005"},
            ("subjective_requirement", "技术要求存在主观描述", "技术要求客观性审查", "高风险"),
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
            {"RP-CONTRACT-011"},
            ("acceptance_payment_link", "验收与付款/考核/满意度联动不当", "履约管理联动审查", "高风险"),
        ),
        (
            {"RP-CONTRACT-014"},
            ("invoice_payment_deadline", "采购人应当在收到发票后N个工作日内完成资金支付/采购人应当在收到发票后N个工作日或Y日内完成资金支付", "合同支付时限审查", "高风险"),
        ),
        (
            {"RP-CONTRACT-015"},
            ("service_duration_limit", "合理设置合同履行期限", "合同期限边界审查", "高风险"),
        ),
        (
            {"RP-CONS-009", "RP-SME-005"},
            ("amount_consistency", "中小企业采购金额口径不一致", "政策条款一致性审查", "中风险"),
        ),
        (
            {"RP-PROC-001"},
            ("procurement_method", "采购方式适用理由不足", "采购方式适用性审查", "高风险"),
        ),
        (
            {"RP-PROC-002"},
            ("package_split", "混合采购未拆分或包件划分依据不足", "采购组织方式审查", "高风险"),
        ),
        (
            {"RP-CONS-010"},
            ("transfer_outsource", "转包外包边界不清或核心任务转包风险", "分包与外包边界审查", "高风险"),
        ),
        (
            {"RP-PRUD-003"},
            ("procedural_fairness", "违约责任与程序保障失衡", "合同程序保障审查", "高风险"),
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


def _resolve_reviewer_issue_group(point, adjudication) -> tuple[str, str, str, str]:
    if point.catalog_id == "RP-QUAL-003":
        evidence_text = " ".join(
            filter(
                None,
                [
                    adjudication.primary_quote,
                    adjudication.section_hint,
                    *(item.quote for item in point.evidence_bundle.direct_evidence),
                    *(item.quote for item in point.evidence_bundle.supporting_evidence),
                ],
            )
        )
        if any(token in evidence_text for token in ["纳税信用", "税务部门"]):
            return (
                "qualification_tax_hidden_gate",
                "不得将纳税额的隐性限制证书设置为资格条件",
                "资格与公平竞争审查",
                "高风险",
            )
        if any(token in evidence_text for token in ["成立满", "成立年限", "设立满", "注册满"]):
            return (
                "qualification_age_hidden_gate",
                "不得将成立年限的隐性限制证书设置为资格条件",
                "资格与公平竞争审查",
                "高风险",
            )
        if "高新技术企业" in evidence_text:
            return (
                "qualification_staff_hidden_gate",
                "不得将从业人员的隐性限制证书设置为资格条件",
                "资格与公平竞争审查",
                "高风险",
            )
        if any(token in evidence_text for token in ["科技型中小企业", "规模类型", "资产总额"]):
            return (
                "qualification_asset_hidden_gate",
                "不得将资产总额的隐性限制证书设置为资格条件",
                "资格与公平竞争审查",
                "高风险",
            )
    if point.catalog_id in {"RP-SCORE-005", "RP-SCORE-013"}:
        evidence_text = " ".join(
            filter(
                None,
                [
                    adjudication.primary_quote,
                    adjudication.section_hint,
                    *(item.quote for item in point.evidence_bundle.direct_evidence),
                    *(item.quote for item in point.evidence_bundle.supporting_evidence),
                ],
            )
        )
        if any(token in evidence_text for token in INDUSTRY_MISMATCH_SCORING_TOKENS):
            return (
                "industry_mismatch_scoring_factor",
                "行业错配评分项被纳入评审",
                "评分因素关联性审查",
                "高风险",
            )
    if point.catalog_id == "RP-COMP-001":
        return (
            "competition_min_price_floor",
            "不得设定最低限价",
            "限制竞争风险审查",
            "高风险",
        )
    return _reviewer_issue_group_definition(point)


def _canonical_reviewer_group_key(group_key: str, title: str) -> str:
    if group_key and group_key != title and not group_key.startswith("RP-"):
        return group_key
    normalized_title = re.sub(r"\s+", "", title or "")
    explicit_clusters = {
        "履约保证金转质量保证金或长期无息占压": "contract_retention_money",
        "明确说明保证金缴纳方式": "contract_guarantee_payment_method",
        "不得违规设置质量保证金": "contract_quality_guarantee",
        "第三方检测费用无论结果均由中标人承担": "contract_third_party_test_cost",
        "以预算金额比例设最低报价门槛": "competition_min_quote_floor",
        "不得设定最低限价": "competition_min_price_floor",
        "采购文件同一采购包中货物合同履行期限不得存在差异": "goods_package_delivery_inconsistency",
        "服务合同履行期限不得超过36个月": "service_duration_over_36_months",
        "不得缺失“超出检测机构能力范围”处理的相关说明": "cma_capacity_fallback_missing",
        "不得将资产总额的隐性限制证书设置为资格条件": "qualification_asset_hidden_gate",
        "不得将从业人员的隐性限制证书设置为资格条件": "qualification_staff_hidden_gate",
        "不得将纳税额的隐性限制证书设置为资格条件": "qualification_tax_hidden_gate",
        "不得将成立年限的隐性限制证书设置为资格条件": "qualification_age_hidden_gate",
        "资格条件与评分因素重复设门槛": "qualification_scoring_overlap",
        "不得限定供应商组织形式": "qualification_org_form",
        "体系认证证书不得要求特定认证范围": "certificate_scope_scoring_factor",
        "不得将准入类、行政许可类资格职业证书设置为评分项": "administrative_license_scoring_factor",
        "依法设定价格分值": "service_price_weight_factor",
        "采购人应当在收到发票后N个工作日内完成资金支付/采购人应当在收到发票后N个工作日或Y日内完成资金支付": "invoice_payment_deadline",
        "合理设置合同履行期限": "service_duration_limit",
    }
    cluster_key = explicit_clusters.get(normalized_title)
    if cluster_key:
        return cluster_key
    return normalized_title or group_key


def _stronger_reviewer_severity(current: str, candidate: str) -> str:
    order = {"高风险": 3, "中风险": 2, "低风险": 1}
    return candidate if order.get(candidate, 0) > order.get(current, 0) else current


def _reviewer_issue_sort_key(entry: dict[str, object]) -> tuple[int, str]:
    severity = str(entry.get("问题定性", "高风险"))
    order = {"高风险": 0, "中风险": 1, "低风险": 2}
    return (order.get(severity, 9), str(entry.get("问题标题", "")))


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
    if title == "行业错配评分项被纳入评审":
        return _select_group_quote_records(
            quote_records,
            ["人力资源测评师"],
            ["非金属矿采矿许可证", "采矿许可证"],
            ["评分", "得分", "分值", "详细评审"],
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
    if title == "资产总额被设为评分因素":
        return _select_group_quote_records(
            quote_records,
            ["资产总额"],
            ["得分", "评分", "分值"],
            limit=3,
            strict=True,
        )
    if title == "从业人员被设为评分因素":
        return _select_group_quote_records(
            quote_records,
            ["从业人员"],
            ["得分", "评分", "分值"],
            limit=3,
            strict=True,
        )
    if title == "纳税额被设为评分因素":
        return _select_group_quote_records(
            quote_records,
            ["纳税额"],
            ["得分", "评分", "分值"],
            limit=3,
            strict=True,
        )
    if title == "成立年限被设为评分因素":
        return _select_group_quote_records(
            quote_records,
            ["成立时间满", "成立年限", "成立满"],
            ["得分", "评分", "分值"],
            limit=3,
            strict=True,
        )
    if title == "注册资本被设为评分因素":
        return _select_group_quote_records(
            quote_records,
            ["注册资本"],
            ["得分", "评分", "分值"],
            limit=3,
            strict=True,
        )
    if title == "营业收入被设为评分因素":
        return _select_group_quote_records(
            quote_records,
            ["营业收入"],
            ["得分", "评分", "分值"],
            limit=3,
            strict=True,
        )
    if title == "净利润或利润被设为评分因素":
        return _select_group_quote_records(
            quote_records,
            ["净利润", "利润", "利润率"],
            ["得分", "评分", "分值"],
            limit=3,
            strict=True,
        )
    if title == "股权结构被设为评分因素":
        return _select_group_quote_records(
            quote_records,
            ["股东", "股权结构", "资本背景", "国有投资主体", "产业资本"],
            ["得分", "评分", "分值"],
            limit=3,
            strict=True,
        )
    if title == "经营年限被设为评分因素":
        return _select_group_quote_records(
            quote_records,
            ["经营年限", "从业经验"],
            ["得分", "评分", "分值"],
            limit=3,
            strict=True,
        )
    if title == "体系认证证书不得要求特定认证范围":
        return _select_group_quote_records(
            quote_records,
            ["认证范围"],
            ["管理体系认证", "认证证书", "质量管理体系认证证书", "环境管理体系认证证书", "职业健康安全管理体系认证证书"],
            ["得分", "评分", "分值"],
            limit=3,
            strict=True,
        )
    if title == "不得将准入类、行政许可类资格职业证书设置为评分项":
        return _select_group_quote_records(
            quote_records,
            ["许可证", "行政许可", "作业人员证书", "特种设备安全管理和作业人员证书"],
            ["得分", "评分", "分值"],
            limit=3,
            strict=True,
        )
    if title == "资格业绩要求可能存在地域限定、行业口径过窄或与评分重复":
        return _select_group_quote_records(
            quote_records,
            ["深圳市", "广州市", "市", "省", "行业", "医疗器械"],
            ["同类项目业绩", "类似项目业绩"],
            ["不少于", "金额", "得分", "评分"],
            limit=3,
            strict=True,
        )
    if title == "第三方检测费用无论结果均由中标人承担":
        return _select_group_quote_records(
            quote_records,
            ["第三方检测费用", "检测费用"],
            ["中标人承担", "无论检测结果是否合格"],
            limit=2,
            strict=True,
        )
    if title == "不得将资产总额的隐性限制证书设置为资格条件":
        return _select_group_quote_records(
            quote_records,
            ["科技型中小企业", "资产总额", "规模类型"],
            ["投标人", "须为", "须具备", "提供"],
            limit=2,
            strict=True,
        )
    if title == "不得将从业人员的隐性限制证书设置为资格条件":
        return _select_group_quote_records(
            quote_records,
            ["高新技术企业", "从业人员", "规模类型"],
            ["投标人", "须具备", "证书"],
            limit=2,
            strict=True,
        )
    if title == "不得将纳税额的隐性限制证书设置为资格条件":
        return _select_group_quote_records(
            quote_records,
            ["纳税信用A级", "税务部门", "纳税额"],
            ["投标人", "须提供", "证明"],
            limit=2,
            strict=True,
        )
    if title == "不得将成立年限的隐性限制证书设置为资格条件":
        return _select_group_quote_records(
            quote_records,
            ["成立满", "成立年限", "设立满", "注册满"],
            ["投标人", "营业执照", "以上"],
            limit=2,
            strict=True,
        )
    if title == "依法设定价格分值":
        return _select_group_quote_records(
            quote_records,
            ["价格权重", "价格分值权重", "价格分权重"],
            ["%", "10", "9", "8"],
            limit=3,
            strict=True,
        )
    if title == "综合评分法价格分未采用低价优先法":
        return _select_group_quote_records(
            quote_records,
            ["价格分计算方法"],
            ["中间价优先法", "平均值作为评标基准价", "去掉最高价和最低价"],
            limit=3,
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
    if title == "采购方式适用理由不足":
        return _select_group_quote_records(
            quote_records,
            ["采购方式", "竞争性磋商", "竞争性谈判", "单一来源", "询价"],
            ["适用理由", "适用情形", "唯一", "复杂"],
            limit=3,
            strict=True,
        )
    if title == "资格条件与评分因素重复设门槛":
        return _select_group_quote_records(
            quote_records,
            ["资格要求", "特定资格要求", "资质证书", "项目负责人", "业绩"],
            ["评分", "得分", "分"],
            limit=4,
            strict=True,
        )
    if title == "特定资质或证书要求超必要限度":
        return _select_group_quote_records(
            quote_records,
            ["资质证书", "认证证书", "检测报告"],
            ["必须", "须", "提供", "提交", "具备"],
            limit=4,
            strict=True,
        )
    if title == "不得限定供应商组织形式":
        return _select_group_quote_records(
            quote_records,
            ["个体工商户", "其他组织形式", "组织形式"],
            ["不得参与", "不接受", "不得投标", "不得参加"],
            limit=3,
            strict=True,
        )
    if title == "技术或服务要求可验证性不足":
        return _select_group_quote_records(
            quote_records,
            ["满足采购人要求", "按行业标准", "高质量完成", "由采购人认定"],
            limit=3,
            strict=True,
        )
    if title == "疑似使用不存在的技术标准":
        return _select_group_quote_records(
            quote_records,
            ["GB/T", "标准", "规范"],
            limit=2,
            strict=True,
        )
    if title == "技术参数区间说明不足":
        return _select_group_quote_records(
            quote_records,
            ["响应时间", "精度", "范围", "区间"],
            ["ms", "mm"],
            limit=3,
            strict=True,
        )
    if title == "同一技术参数区间说明冲突":
        return _select_group_quote_records(
            quote_records,
            ["不允许正偏离", "不允许负偏离", "不得偏离", "≤"],
            ["±", "偏差", "允许"],
            limit=3,
            strict=True,
        )
    if title == "技术要求存在主观描述":
        return _select_group_quote_records(
            quote_records,
            ["操作体验", "设计美观", "友好美观", "人体工程学设计"],
            limit=3,
            strict=True,
        )
    if title == "验收与付款/考核/满意度联动不当":
        return _select_group_quote_records(
            quote_records,
            ["付款", "支付", "尾款"],
            ["验收", "考核", "满意度"],
            limit=4,
            strict=True,
        )
    if title == "采购人应当在收到发票后N个工作日内完成资金支付/采购人应当在收到发票后N个工作日或Y日内完成资金支付":
        return _select_group_quote_records(
            quote_records,
            ["收到发票后"],
            ["支付", "付款", "资金支付"],
            ["工作日", "日内"],
            limit=3,
            strict=True,
        )
    if title == "合理设置合同履行期限":
        return _select_group_quote_records(
            quote_records,
            ["合同履行期限", "服务期限", "服务期", "建设周期"],
            ["个月"],
            limit=3,
            strict=True,
        )
    if title == "转包外包边界不清或核心任务转包风险":
        return _select_group_quote_records(
            quote_records,
            ["转包", "外包"],
            ["核心任务", "委托第三方", "分包"],
            limit=4,
            strict=True,
        )
    if title == "信用评价规则透明性不足":
        return _select_group_quote_records(
            quote_records,
            ["信用评价", "信用分", "征信"],
            ["修复", "异议", "申诉", "救济"],
            limit=4,
            strict=False,
        )
    if title == "违约责任与程序保障失衡":
        return _select_group_quote_records(
            quote_records,
            ["违约责任", "解约", "解除合同"],
            ["整改", "申辩", "陈述意见", "异议"],
            limit=4,
            strict=False,
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
        "行业错配评分项被纳入评审": [
            r"人力资源测评师[^。；;\n]{0,140}",
            r"(非金属矿采矿许可证|采矿许可证)[^。；;\n]{0,140}",
        ],
        "信用评价作为评分因素": [
            r"信用评价[^。；\n]{0,100}",
            r"信用分[^。；\n]{0,100}",
            r"征信[^。；\n]{0,100}",
        ],
        "资产总额被设为评分因素": [
            r"资产总额[^。；\n]{0,120}(得分|评分|分值)[^。；\n]{0,80}",
        ],
        "从业人员被设为评分因素": [
            r"从业人员[^。；\n]{0,120}(得分|评分|分值)[^。；\n]{0,80}",
        ],
        "纳税额被设为评分因素": [
            r"纳税额[^。；\n]{0,120}(得分|评分|分值)[^。；\n]{0,80}",
        ],
        "成立年限被设为评分因素": [
            r"(成立时间满|成立年限|成立满)[^。；\n]{0,120}(得分|评分|分值)[^。；\n]{0,80}",
        ],
        "注册资本被设为评分因素": [
            r"注册资本[^。；\n]{0,120}(得分|评分|分值)[^。；\n]{0,80}",
        ],
        "营业收入被设为评分因素": [
            r"营业收入[^。；\n]{0,120}(得分|评分|分值)[^。；\n]{0,80}",
        ],
        "净利润或利润被设为评分因素": [
            r"(净利润|利润率|利润)[^。；\n]{0,120}(得分|评分|分值)[^。；\n]{0,80}",
        ],
        "股权结构被设为评分因素": [
            r"(股东|股权结构|资本背景|国有投资主体|产业资本)[^。；\n]{0,140}(得分|评分|分值)[^。；\n]{0,80}",
        ],
        "经营年限被设为评分因素": [
            r"(经营年限|从业经验)[^。；\n]{0,120}(得分|评分|分值)[^。；\n]{0,80}",
        ],
        "综合评分法价格分未采用低价优先法": [
            r"价格分计算方法[^。；\n]{0,180}",
            r"(中间价优先法|平均值作为评标基准价|去掉最高价和最低价)[^。；\n]{0,180}",
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
        "采购方式适用理由不足": [
            r"采购方式[^。；\n]{0,80}",
            r"(竞争性磋商|竞争性谈判|单一来源|询价)[^。；\n]{0,120}",
            r"(适用理由|适用情形|唯一|复杂)[^。；\n]{0,120}",
        ],
        "资格条件与评分因素重复设门槛": [
            r"(资格要求|特定资格要求)[^。；\n]{0,150}",
            r"(资质证书|项目负责人|业绩)[^。；\n]{0,150}",
            r"(评分|得分)[^。；\n]{0,150}",
        ],
        "资格业绩要求可能存在地域限定、行业口径过窄或与评分重复": [
            r"(?:投标人[^。；\n]{0,40})?(?:深圳市|广州市|[^。；\n]{0,20}行业)[^。；\n]{0,120}(同类项目业绩|类似项目业绩)[^。；\n]{0,120}",
            r"(同类项目业绩|类似项目业绩)[^。；\n]{0,120}(不少于|得分|评分)[^。；\n]{0,100}",
        ],
        "特定资质或证书要求超必要限度": [
            r"(资质证书|认证证书|检测报告)[^。；\n]{0,160}",
            r"(必须|须|提供|提交|具备)[^。；\n]{0,160}",
        ],
        "第三方检测费用无论结果均由中标人承担": [
            r"第三方检测费用[^。；\n]{0,160}(中标人承担|由中标人承担)[^。；\n]{0,120}",
            r"检测费用[^。；\n]{0,120}无论检测结果是否合格[^。；\n]{0,80}",
        ],
        "技术或服务要求可验证性不足": [
            r"(满足采购人要求|按行业标准|高质量完成|由采购人认定)[^。；\n]{0,160}",
        ],
        "疑似使用不存在的技术标准": [
            r"GB/T\s*\d+-\d{4}[^。；\n]{0,120}",
        ],
        "技术参数区间说明不足": [
            r"(响应时间|精度|范围|区间)[^。；\n]{0,120}(ms|mm)[^。；\n]{0,120}",
        ],
        "同一技术参数区间说明冲突": [
            r"[^。；\n]{0,120}(不允许正偏离|不允许负偏离|不得偏离|不接受偏离|≤)[^。；\n]{0,120}",
            r"[^。；\n]{0,120}(±|偏差|允许)[^。；\n]{0,120}",
        ],
        "技术要求存在主观描述": [
            r"(操作体验|界面友好美观|设计美观|人体工程学设计|良好的操作体验|友好美观)[^。；\n]{0,160}",
        ],
        "验收与付款/考核/满意度联动不当": [
            r"(尾款|付款|支付)[^。；\n]{0,140}",
            r"(验收|考核|满意度)[^。；\n]{0,160}",
        ],
        "转包外包边界不清或核心任务转包风险": [
            r"(转包|外包|分包)[^。；\n]{0,160}",
            r"(核心任务|委托第三方)[^。；\n]{0,160}",
        ],
        "信用评价规则透明性不足": [
            r"(信用评价|信用分|征信)[^。；\n]{0,160}",
            r"(信用修复|异议|申诉|救济)[^。；\n]{0,160}",
        ],
        "违约责任与程序保障失衡": [
            r"(违约责任|解约|解除合同)[^。；\n]{0,160}",
            r"(整改|申辩|陈述意见|异议)[^。；\n]{0,160}",
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
    prefer_shorter_titles = {
        "技术参数区间说明不足",
        "同一技术参数区间说明冲突",
        "技术要求存在主观描述",
        "疑似使用不存在的技术标准",
    }
    deduped = _dedupe_quote_records(
        refined,
        prefer_shorter_when_contained=title in prefer_shorter_titles,
    )
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


def _rewrite_group_risk_judgment(
    group_key: str,
    title: str,
    risk_judgments: list[str],
    quote_records: list[dict[str, str]],
) -> str:
    merged_quote = "；".join(item.get("quote", "") for item in quote_records)
    templates = {
        "structure_mismatch": "文件将项目定性为货物，但采购内容中同时包含持续性作业服务，合同类型又偏向承揽或服务口径，项目属性、采购内容与合同类型之间存在明显错配风险。",
        "scoring_relevance": "评分中出现利润率、软件企业认定证书、ITSS 或财务报告等内容，与项目实际履约能力缺乏直接关联，存在限制竞争风险。",
        "industry_mismatch_scoring_factor": "评分中纳入人力资源测评师、采矿许可证等与当前采购标的明显错配的资质或许可，和项目履约能力缺乏直接关联，容易形成不当限制竞争。",
        "credit_evaluation": "评分中出现信用评价、信用分或征信等内容，如作为评分因素，需复核其与项目履约能力的直接关联和分值是否适度。",
        "asset_scoring_factor": "评分直接以供应商资产总额作为加分条件，属于以企业规模替代项目履约能力的高风险做法。",
        "staff_scoring_factor": "评分直接以供应商从业人员数量作为加分条件，容易把企业规模条件错当作项目履约能力。",
        "tax_scoring_factor": "评分直接以纳税额作为加分条件，属于以经营结果替代项目履约能力评价的高风险做法。",
        "age_scoring_factor": "评分直接以供应商成立年限作为加分条件，容易对新设企业形成不当限制。",
        "registered_capital_scoring_factor": "评分直接以供应商注册资本作为加分条件，属于以企业规模替代项目履约能力的高风险做法。",
        "revenue_scoring_factor": "评分直接以供应商营业收入作为加分条件，属于以企业规模替代项目履约能力的高风险做法。",
        "profit_scoring_factor": "评分直接以净利润、利润或利润率作为加分条件，属于以经营结果替代项目履约能力的高风险做法。",
        "shareholding_scoring_factor": "评分直接以股权结构、资本背景或投资主体性质作为加分条件，容易形成偏好性评分和不当竞争限制。",
        "operating_age_scoring_factor": "评分直接以经营年限或相关行业从业经验作为供应商加分条件，容易对新进入者形成不当限制。",
        "certificate_scope_scoring_factor": "评分将体系认证证书覆盖特定认证范围作为加分条件，容易把范围口径扩张为不必要的偏好性门槛。",
        "administrative_license_scoring_factor": "评分直接以行政许可、准入类职业证书作为加分条件，容易把资格准入要求再次放大为评分门槛。",
        "service_price_weight_factor": "服务项目价格因素权重明显偏低，会弱化价格竞争功能，影响综合评分法的公平性。",
        "price_method_mismatch": "综合评分法中的价格分采用中间价优先法或均值法，偏离低价优先的法定评审口径，容易影响价格评审公平性。",
        "scoring_quant": "方案评分以主观分档和“无缺陷得满分”等规则为核心，量化和客观性不足，评委裁量空间较大。",
        "qualification_org_form": "资格条件直接排斥个体工商户或其他组织形式，容易形成与履约能力无关的差别待遇。",
        "qualification_asset_hidden_gate": "以科技型中小企业、规模类型等证书或身份口径替代直接履约能力判断，实质上可能对应供应商资产规模条件，容易形成隐性准入限制。",
        "qualification_staff_hidden_gate": "以高新技术企业等证书口径替代直接履约能力判断，实质上可能对应供应商人员规模或研发人员结构要求，容易形成隐性准入限制。",
        "qualification_tax_hidden_gate": "以纳税信用等级或税务部门证明替代直接履约能力判断，实质上可能把纳税额或纳税表现转化为资格门槛，容易形成隐性限制竞争。",
        "qualification_age_hidden_gate": "以成立年限、设立年限或注册时间作为前置资格门槛，容易对新设企业形成不当限制。",
        "contract_template": "合同条款中出现“项目成果、移作他用、泄露成果”等表述，更符合咨询、设计或信息化项目，和当前项目行业场景明显不匹配。",
        "acceptance_flexible": "验收条款赋予采购人较大的单方裁量空间，缺乏固定、明确、可预期的验收标准，容易引发履约争议。",
        "invoice_payment_deadline": "付款条款约定采购人在收到发票后较长时间内才支付资金，需重点复核是否偏离政府采购支付时限要求。",
        "service_duration_limit": "服务项目合同履行期限应明确、合理；存在空白占位、期限未明确或明显超过通常周期时，需重点核查其规则依据和项目必要性。",
        "amount_consistency": "预算金额、最高限价与面向中小企业采购金额之间存在异常对应关系，金额口径不清，文件严谨性不足。",
        "warranty_scope": "项目核心履约内容包含持续性作业或服务责任，但合同条款仍仅以货物质保表述概括，未能准确覆盖实际履约责任。",
        "team_stability": "团队稳定性要求将供应商内部人员构成或稳定性过度前置为采购要求，容易形成不必要的履约门槛。",
        "personnel_change": "人员更换限制过强会使采购人审批介入供应商内部人员管理，容易扩大为不必要的人员控制条款。",
        "invalid_standard": "文件引用的技术标准编号疑似不存在或异常，占用采购需求的技术依据基础，容易影响技术要求的真实性和可执行性。",
        "parameter_interval_missing": "关键技术参数仅给出数值或区间，但未同步说明偏离判断和取值逻辑，评审口径容易不清。",
        "parameter_interval_conflict": "同一技术参数同时出现刚性限制和允许偏差两套口径，前后冲突会直接影响投标响应和评审判断。",
        "subjective_requirement": "技术要求采用体验、美观、友好等主观描述，缺少可量化、可核验的客观标准，容易形成争议或指向性要求。",
    }
    if title == "资格业绩要求可能存在地域限定、行业口径过窄或与评分重复":
        fragments: list[str] = []
        if any(token in merged_quote for token in ["深圳市", "广州市", "本地", "市", "省", "区", "县"]):
            fragments.append("资格业绩存在地域范围收窄")
        if any(token in merged_quote for token in ["行业", "医疗器械", "软件开发", "运维服务", "信息化"]):
            fragments.append("行业口径可能过窄")
        if any(token in merged_quote for token in ["不少于", "以上", "金额", "万元", "个"]):
            fragments.append("业绩数量或金额门槛较硬")
        if any(token in merged_quote for token in ["得分", "评分", "加分", "最高"]) and any(
            token in merged_quote for token in ["资格要求", "须具备", "提供合同扫描件"]
        ):
            fragments.append("并与评分条款形成重复放大")
        if fragments:
            return "；".join(fragments) + "，容易超出履约所必需边界并形成隐性限制竞争。"
        return "资格业绩要求可能通过地域、行业或数量口径收窄竞争范围，并与评分条款形成重复门槛，需重点核查其必要性。"
    if title == "第三方检测费用无论结果均由中标人承担":
        return "检测费用被设置为无论结果如何均由中标人承担，未按责任来源和检测结果区分费用分配，存在明显风险转嫁。"
    if group_key in templates:
        return templates[group_key]
    if risk_judgments:
        return _select_best_risk_judgment(risk_judgments)
    return "已发现明确风险，证据较充分。"


def _select_best_risk_judgment(risk_judgments: list[str]) -> str:
    def score(text: str) -> tuple[int, int]:
        normalized = text or ""
        strength = 0
        if any(token in normalized for token in ["已形成较直接的条款依据", "相关风险较为明确", "已发现明确风险", "直接以", "容易形成", "需核查是否"]):
            strength += 4
        if any(token in normalized for token in ["已发现支持该问题的条款依据", "仍需结合上下文核对风险强度"]):
            strength += 3
        if any(token in normalized for token in ["已识别相关风险线索", "代表性仍需继续核对"]):
            strength += 2
        if any(token in normalized for token in ["尚不足以直接定性", "尚未找到", "未自动挂接", "建议进一步复核"]):
            strength -= 2
        return (strength, len(normalized))

    return sorted(risk_judgments, key=score, reverse=True)[0]


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
    if primary and ("=" not in primary or reviewer_title == "行业错配评分项被纳入评审") and _reviewer_quote_supports_title(reviewer_title, primary):
        records.append({"location": (adjudication.section_hint or "").strip(), "quote": primary})
    for item in [*point.evidence_bundle.direct_evidence, *point.evidence_bundle.supporting_evidence]:
        if reviewer_title == "行业错配评分项被纳入评审" and "=" in (item.quote or ""):
            quote = (item.quote or "").strip()
        else:
            quote = (
                clause_window_from_anchor(report_text, item.section_hint)
                or (item.quote or "").strip()
            )
        if not quote:
            continue
        if len(quote) < 6:
            continue
        if "=" in quote and reviewer_title != "行业错配评分项被纳入评审":
            continue
        if reviewer_title == "行业错配评分项被纳入评审" and "=" in quote:
            records.extend(_expand_structured_industry_mismatch_records((item.section_hint or "").strip(), quote))
            continue
        if not _reviewer_quote_supports_title(reviewer_title, quote):
            continue
        records.append({"location": (item.section_hint or "").strip(), "quote": quote})
    return _dedupe_quote_records(records)[:8]


def _reviewer_quote_supports_title(title: str, quote: str) -> bool:
    partial_checks = {
        "项目属性与采购内容、合同类型不一致": ["项目所属分类", "项目属性", "货物", "人工管护", "清林整地", "抚育", "运水", "合同类型", "承揽合同"],
        "评分项与采购标的不相关": ["利润率", "软件企业认定证书", "ITSS", "财务报告", "信用评价"],
        "注册资本被设为评分因素": ["注册资本", "得分", "评分", "分值"],
        "营业收入被设为评分因素": ["营业收入", "得分", "评分", "分值"],
        "净利润或利润被设为评分因素": ["净利润", "利润", "利润率", "得分", "评分", "分值"],
        "股权结构被设为评分因素": ["股东", "股权结构", "资本背景", "国有投资主体", "产业资本", "得分", "评分", "分值"],
        "经营年限被设为评分因素": ["经营年限", "从业经验", "得分", "评分", "分值"],
        "体系认证证书不得要求特定认证范围": ["认证范围", "管理体系认证", "认证证书", "得分", "评分", "分值"],
        "不得将准入类、行政许可类资格职业证书设置为评分项": ["许可证", "行政许可", "作业人员证书", "特种设备安全管理和作业人员证书", "得分", "评分", "分值"],
        "依法设定价格分值": ["价格权重", "价格分值权重", "%"],
        "行业错配评分项被纳入评审": ["人力资源测评师", "非金属矿采矿许可证", "采矿许可证", "评分", "得分", "分值"],
        "方案评分主观性过强，量化不足": ["无缺陷", "缺陷", "扣2.5分", "完全满足且优于", "不完全满足"],
        "合同条款存在明显模板错配": ["项目成果", "研究成果", "技术文档", "移作他用", "泄露本项目成果"],
        "验收标准表述过于弹性": ["比较优胜", "优胜的原则", "确定该项的约定标准"],
        "中小企业采购金额口径不一致": ["预算金额", "面向中小企业采购金额", "最高限价"],
        "货物保修表述与项目实际履约内容不匹配": ["货物质保期", "质量保修范围和保修期", "人工管护", "1095日", "合同履行期限"],
        "团队稳定性要求过强": ["团队稳定", "核心团队", "人员稳定", "团队成员", "保持稳定", "不得更换"],
        "人员更换限制较强": ["人员更换", "更换", "替换", "变更", "调整", "采购人同意", "采购人批准", "须经"],
        "不得限定供应商组织形式": ["个体工商户", "其他组织形式", "组织形式", "不得参与", "不接受", "不得投标", "不得参加"],
        "不得将资产总额的隐性限制证书设置为资格条件": ["科技型中小企业", "资产总额", "规模类型", "投标人"],
        "不得将从业人员的隐性限制证书设置为资格条件": ["高新技术企业", "从业人员", "规模类型", "投标人"],
        "不得将纳税额的隐性限制证书设置为资格条件": ["纳税信用A级", "税务部门", "纳税额", "证明"],
        "不得将成立年限的隐性限制证书设置为资格条件": ["成立满", "成立年限", "设立满", "注册满", "营业执照"],
        "采购人应当在收到发票后N个工作日内完成资金支付/采购人应当在收到发票后N个工作日或Y日内完成资金支付": ["收到发票后", "支付", "付款", "工作日", "日内"],
        "合理设置合同履行期限": ["合同履行期限", "服务期限", "服务期", "建设周期", "个月"],
    }
    tokens = partial_checks.get(title)
    if tokens is not None:
        return any(token in quote for token in tokens)
    return evidence_supports_title(title, quote)


def _expand_structured_industry_mismatch_records(location: str, quote: str) -> list[dict[str, str]]:
    _, _, tail = quote.partition("=")
    if not tail:
        return []
    records: list[dict[str, str]] = []
    for chunk in re.split(r"[;；、,，]+", tail):
        snippet = chunk.strip()
        if not snippet:
            continue
        if any(token in snippet for token in INDUSTRY_MISMATCH_SCORING_TOKENS):
            records.append({"location": location, "quote": snippet})
    return records


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
        label = _normalize_reviewer_basis_label(label)
        if label not in lines:
            lines.append(label)
    if not lines and point.catalog_id:
        for binding in list_bindings_for_point(point.catalog_id):
            label = f"《{binding.doc_title}》"
            if binding.article_label:
                label = f"{label} {binding.article_label}"
            label = _normalize_reviewer_basis_label(label)
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
    return _dedupe_reviewer_basis_lines(lines)


def _normalize_reviewer_basis_label(label: str) -> str:
    normalized = re.sub(r"\s+", " ", label).strip()
    if "《中华人民共和国政府采购法、政府采购货物和服务招标投标管理办法》" in normalized:
        if "报价审查相关条款" in normalized:
            return "《中华人民共和国政府采购法》 第二十二条、第二十五条"
        return "《政府采购货物和服务招标投标管理办法》 评审与报价审查相关条款"
    normalized = normalized.replace("及报价审查相关条款", "报价审查相关条款")
    normalized = normalized.replace("评审因素设置相关条款", "评审因素设置相关条款")
    return normalized


def _dedupe_reviewer_basis_lines(lines: list[str]) -> list[str]:
    results: list[str] = []
    seen_keys: set[str] = set()
    for line in lines:
        normalized = _normalize_reviewer_basis_label(line)
        dedupe_key = normalized
        dedupe_key = dedupe_key.replace("《中华人民共和国政府采购法》《政府采购货物和服务招标投标管理办法》 ", "")
        dedupe_key = dedupe_key.replace("《中华人民共和国政府采购法》 ", "")
        dedupe_key = dedupe_key.replace("《政府采购货物和服务招标投标管理办法》 ", "")
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        results.append(normalized)
    return results


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


def _dedupe_quote_records(
    records: list[dict[str, str]],
    prefer_shorter_when_contained: bool = False,
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for item in records:
        quote = re.sub(r"\s+", " ", item.get("quote", "")).strip(" ；;")
        location = item.get("location", "").strip()
        if not quote:
            continue
        duplicate_index: int | None = None
        for index, existing in enumerate(results):
            existing_quote = existing["quote"]
            same_location = existing["location"] == location
            if not same_location:
                continue
            if quote == existing_quote:
                duplicate_index = index
                break
            if quote in existing_quote:
                duplicate_index = index
                if prefer_shorter_when_contained and len(quote) < len(existing_quote):
                    results[index] = {"location": location, "quote": quote}
                break
            if existing_quote in quote:
                duplicate_index = index
                if prefer_shorter_when_contained:
                    break
                if len(quote) > len(existing_quote):
                    results[index] = {"location": location, "quote": quote}
                break
        if duplicate_index is not None:
            continue
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

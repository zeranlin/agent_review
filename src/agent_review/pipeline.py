from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .checklist import DEFAULT_DIMENSIONS
from .consistency import (
    check_consistency,
    collect_relative_strengths,
    convert_consistency_checks_to_findings,
    derive_conclusion,
)
from .extractors import extract_clauses
from .merge import (
    build_specialist_tables,
    dedupe_findings,
    dedupe_recommendations,
    dedupe_risk_hits,
    dedupe_strings,
)
from .models import (
    ConclusionLevel,
    Evidence,
    FileInfo,
    Finding,
    FindingType,
    ParseResult,
    ParsedPage,
    Recommendation,
    ReviewDimension,
    ReviewMode,
    ReviewReport,
    RuleSelection,
    RunStageRecord,
    SectionIndex,
    Severity,
    SourceDocument,
    TaskRecord,
    TaskStatus,
)
from .rules import build_recommendations, convert_risk_hits_to_findings, execute_rule_registry
from .structure import build_file_info, build_scope_statement, detect_file_type, locate_sections


@dataclass(slots=True)
class ReviewPipelineState:
    document_name: str
    parse_result: ParseResult
    normalized_text: str
    source_documents: list[SourceDocument] = field(default_factory=list)
    file_info: FileInfo | None = None
    scope_statement: str = ""
    section_index: list[SectionIndex] = field(default_factory=list)
    extracted_clauses: list = field(default_factory=list)
    risk_hits: list = field(default_factory=list)
    consistency_checks: list = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    relative_strengths: list[str] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    manual_review_queue: list[str] = field(default_factory=list)
    reviewed_dimensions: list[str] = field(default_factory=list)
    specialist_tables: object | None = None
    rule_selection: RuleSelection = field(default_factory=RuleSelection)
    overall_conclusion: ConclusionLevel | None = None
    summary: str = ""
    stage_records: list[RunStageRecord] = field(default_factory=list)


class ReviewPipeline:
    def __init__(
        self,
        dimensions: list[ReviewDimension] | None = None,
    ) -> None:
        self.dimensions = dimensions or DEFAULT_DIMENSIONS
        self.stages = (
            self._stage_document_structure,
            self._stage_clause_extraction,
            self._stage_dimension_review,
            self._stage_rule_evaluation,
            self._stage_consistency_review,
            self._stage_finalize_report,
        )

    def run(
        self,
        parse_result: ParseResult,
        document_name: str,
        review_mode: ReviewMode,
        source_documents: list[SourceDocument] | None = None,
    ) -> ReviewReport:
        state = ReviewPipelineState(
            document_name=document_name,
            parse_result=parse_result,
            normalized_text=parse_result.text,
            source_documents=source_documents or [],
        )
        for stage in self.stages:
            stage(state)

        return ReviewReport(
            review_mode=review_mode,
            parse_result=state.parse_result,
            file_info=state.file_info,
            scope_statement=state.scope_statement,
            overall_conclusion=state.overall_conclusion,
            summary=state.summary,
            llm_enhanced=False,
            llm_warnings=[],
            findings=state.findings,
            relative_strengths=state.relative_strengths,
            section_index=state.section_index,
            extracted_clauses=state.extracted_clauses,
            risk_hits=state.risk_hits,
            specialist_tables=state.specialist_tables,
            consistency_checks=state.consistency_checks,
            recommendations=state.recommendations,
            manual_review_queue=state.manual_review_queue,
            reviewed_dimensions=state.reviewed_dimensions,
            source_documents=state.source_documents,
            stage_records=state.stage_records,
            task_records=[
                TaskRecord(
                    task_name=item.stage_name,
                    status=TaskStatus.completed if item.status == "completed" else TaskStatus.failed,
                    detail=item.detail,
                    item_count=item.item_count,
                )
                for item in state.stage_records
            ],
            rule_selection=state.rule_selection,
        )

    def _stage_document_structure(self, state: ReviewPipelineState) -> None:
        file_type = detect_file_type(state.normalized_text)
        state.file_info = build_file_info(state.document_name, state.normalized_text, file_type)
        state.scope_statement = build_scope_statement(state.file_info)
        state.section_index = locate_sections(state.normalized_text)
        state.stage_records.append(
            RunStageRecord(
                stage_name="document_structure",
                status="completed",
                item_count=len(state.section_index),
                detail=f"识别文件类型并定位 {len(state.section_index)} 个章节锚点。",
            )
        )

    def _stage_clause_extraction(self, state: ReviewPipelineState) -> None:
        state.extracted_clauses = extract_clauses(state.normalized_text)
        state.stage_records.append(
            RunStageRecord(
                stage_name="clause_extraction",
                status="completed",
                item_count=len(state.extracted_clauses),
                detail=f"抽取 {len(state.extracted_clauses)} 条结构化条款。",
            )
        )

    def _stage_dimension_review(self, state: ReviewPipelineState) -> None:
        findings: list[Finding] = []
        manual_review_queue: list[str] = []
        reviewed_dimensions: list[str] = []
        for dimension in self.dimensions:
            reviewed_dimensions.append(dimension.display_name)
            dimension_findings = _review_dimension(state.normalized_text, dimension)
            findings.extend(dimension_findings)
            for finding in dimension_findings:
                if finding.finding_type == FindingType.manual_review_required:
                    manual_review_queue.append(finding.title)
        state.findings.extend(findings)
        state.manual_review_queue.extend(manual_review_queue)
        state.reviewed_dimensions = reviewed_dimensions
        state.stage_records.append(
            RunStageRecord(
                stage_name="dimension_review",
                status="completed",
                item_count=len(findings),
                detail=f"完成 {len(reviewed_dimensions)} 个维度的基础筛查。",
            )
        )

    def _stage_rule_evaluation(self, state: ReviewPipelineState) -> None:
        risk_hits, rule_selection = execute_rule_registry(
            text=state.normalized_text,
            clauses=state.extracted_clauses,
        )
        state.rule_selection = rule_selection
        state.risk_hits = dedupe_risk_hits(risk_hits)
        state.findings.extend(convert_risk_hits_to_findings(state.risk_hits))
        state.specialist_tables = build_specialist_tables(state.risk_hits)
        executed_modules = rule_selection.core_modules + rule_selection.enhancement_modules
        state.stage_records.append(
            RunStageRecord(
                stage_name="rule_evaluation",
                status="completed",
                item_count=len(state.risk_hits),
                detail=(
                    f"执行核心规则 {len(rule_selection.core_modules)} 个，"
                    f"场景增强规则 {len(rule_selection.enhancement_modules)} 个，"
                    f"共命中 {len(state.risk_hits)} 条风险。"
                ),
            )
        )

    def _stage_consistency_review(self, state: ReviewPipelineState) -> None:
        state.consistency_checks = check_consistency(state.normalized_text, state.extracted_clauses)
        consistency_findings = convert_consistency_checks_to_findings(state.consistency_checks)
        state.findings.extend(consistency_findings)
        issue_count = sum(1 for item in state.consistency_checks if item.status == "issue")
        state.stage_records.append(
            RunStageRecord(
                stage_name="consistency_review",
                status="completed",
                item_count=issue_count,
                detail=f"完成一致性矩阵检查，发现 {issue_count} 条需关注项。",
            )
        )

    def _stage_finalize_report(self, state: ReviewPipelineState) -> None:
        state.findings = dedupe_findings(state.findings)
        state.manual_review_queue = dedupe_strings(state.manual_review_queue)
        state.relative_strengths = dedupe_strings(
            collect_relative_strengths(state.section_index, state.findings)
        )
        state.recommendations = dedupe_recommendations(build_recommendations(state.findings))
        state.overall_conclusion = derive_conclusion(state.findings)
        state.summary = _build_summary(
            findings=state.findings,
            manual_review_queue=state.manual_review_queue,
            overall_conclusion=state.overall_conclusion,
        )
        state.stage_records.append(
            RunStageRecord(
                stage_name="finalize_report",
                status="completed",
                item_count=len(state.findings),
                detail=f"完成结果归并，形成 {len(state.findings)} 条最终审查结果。",
            )
        )


def build_parse_result_for_text(text: str, document_name: str) -> ParseResult:
    suffix = Path(document_name).suffix.lower().lstrip(".") or "txt"
    return ParseResult(
        parser_name="text",
        source_path=document_name,
        source_format=suffix,
        page_count=1,
        text=text,
        pages=[ParsedPage(page_index=1, text=text, source="text")],
        tables=[],
        warnings=[],
    )


def _review_dimension(text: str, dimension: ReviewDimension) -> list[Finding]:
    lowered = text.lower()
    matched_triggers = [item for item in dimension.triggers if item.lower() in lowered]
    matched_missing_markers = [item for item in dimension.missing_markers if item.lower() in lowered]

    if not matched_triggers:
        return [
            Finding(
                dimension=dimension.display_name,
                finding_type=FindingType.missing_evidence,
                severity=Severity.medium,
                title=f"{dimension.display_name}信息可能缺失",
                rationale=(
                    "未在文档文本中定位到该审查维度的常见触发词，"
                    "可能表示相关条款缺失、表达方式异常，或当前文本并不完整。"
                ),
                evidence=[],
                confidence=0.45,
                next_action="补充完整招标文件正文及附件后重新审查。",
            )
        ]

    evidence = [Evidence(quote=item, section_hint="keyword_match") for item in matched_triggers[:3]]

    findings: list[Finding] = []
    if matched_missing_markers:
        findings.append(
            Finding(
                dimension=dimension.display_name,
                finding_type=FindingType.manual_review_required,
                severity=Severity.medium,
                title=f"{dimension.display_name}依赖附件或外部材料",
                rationale=(
                    "文档中出现了依赖附件、另册或后续文件的表达，"
                    "自动审查无法仅凭当前文本形成完整结论。"
                ),
                evidence=[
                    Evidence(quote=item, section_hint="missing_marker")
                    for item in matched_missing_markers[:3]
                ],
                confidence=0.72,
                next_action="核验被引用附件、附表或正式合同文本。",
            )
        )

    if dimension.key == "restrictive_terms":
        restrictive_hits = [
            item
            for item in ["指定品牌", "原厂", "本地", "注册地", "唯一"]
            if item.lower() in lowered
        ]
        if restrictive_hits:
            findings.append(
                Finding(
                    dimension=dimension.display_name,
                    finding_type=FindingType.warning,
                    severity=Severity.high,
                    title="发现潜在限制性竞争表述",
                    rationale=(
                        "文档中命中了常见限制性或歧视性表述关键词，"
                        "需要进一步判断是否具备合法、必要、可替代的依据。"
                    ),
                    evidence=[
                        Evidence(quote=item, section_hint="restrictive_term")
                        for item in restrictive_hits[:3]
                    ],
                    confidence=0.78,
                    next_action="核查该条款是否与采购需求直接相关且不排斥潜在供应商。",
                )
            )

    if dimension.key == "evaluation_criteria":
        if "综合评分" in text and "评分标准" not in text:
            findings.append(
                Finding(
                    dimension=dimension.display_name,
                    finding_type=FindingType.warning,
                    severity=Severity.high,
                    title="评审方法出现但评分标准不够清晰",
                    rationale="文本提到综合评分，但未同时发现清晰的评分标准触发词。",
                    evidence=[Evidence(quote="综合评分", section_hint="keyword_match")],
                    confidence=0.70,
                    next_action="核查是否存在完整评分细则、分值和量化口径。",
                )
            )

    if not findings:
        findings.append(
            Finding(
                dimension=dimension.display_name,
                finding_type=FindingType.pass_,
                severity=Severity.low,
                title=f"{dimension.display_name}已完成基础筛查",
                rationale=dimension.risk_hint or "已完成基础关键词覆盖检查，未发现明显异常。",
                evidence=evidence,
                confidence=0.60,
                next_action="如需正式结论，建议结合具体法规条文进行二次复核。",
            )
        )

    return findings


def _build_summary(
    findings: list[Finding],
    manual_review_queue: list[str],
    overall_conclusion: ConclusionLevel,
) -> str:
    issue_count = sum(
        1
        for item in findings
        if item.finding_type
        in {
            FindingType.confirmed_issue,
            FindingType.warning,
            FindingType.manual_review_required,
            FindingType.missing_evidence,
        }
    )
    if manual_review_queue:
        return (
            f"审查结论为“{overall_conclusion.value}”。共生成 {len(findings)} 条审查结果，"
            f"其中 {issue_count} 条需要重点关注，{len(manual_review_queue)} 条需要人工复核。"
        )
    return (
        f"审查结论为“{overall_conclusion.value}”。共生成 {len(findings)} 条审查结果，"
        f"其中 {issue_count} 条需要关注。"
    )

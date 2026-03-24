from __future__ import annotations

from pathlib import Path

from .checklist import DEFAULT_DIMENSIONS
from .models import ConclusionLevel
from .consistency import (
    check_consistency,
    collect_relative_strengths,
    convert_consistency_checks_to_findings,
    derive_conclusion,
)
from .extractors import extract_clauses
from .llm import NullReviewEnhancer
from .models import (
    Evidence,
    Finding,
    FindingType,
    ReviewDimension,
    ReviewReport,
    Severity,
)
from .parsers import load_document, normalize_text
from .rules import build_recommendations, convert_risk_hits_to_findings, match_risk_rules
from .structure import build_file_info, build_scope_statement, detect_file_type, locate_sections


class TenderReviewEngine:
    """A minimal deterministic review harness.

    This is intentionally simple: it makes the review loop executable before
    integrating OCR, retrieval, or LLM-backed reasoning.
    """

    def __init__(
        self,
        dimensions: list[ReviewDimension] | None = None,
        review_enhancer: object | None = None,
    ) -> None:
        self.dimensions = dimensions or DEFAULT_DIMENSIONS
        self.review_enhancer = review_enhancer or NullReviewEnhancer()

    def review_text(self, text: str, document_name: str = "input.txt") -> ReviewReport:
        normalized_text = normalize_text(text)
        file_type = detect_file_type(normalized_text)
        file_info = build_file_info(document_name, normalized_text, file_type)
        scope_statement = build_scope_statement(file_info)
        section_index = locate_sections(normalized_text)
        extracted_clauses = extract_clauses(normalized_text)
        risk_hits = match_risk_rules(normalized_text)
        consistency_checks = check_consistency(normalized_text)
        findings: list[Finding] = []
        manual_review_queue: list[str] = []
        reviewed_dimensions: list[str] = []

        for dimension in self.dimensions:
            reviewed_dimensions.append(dimension.display_name)
            dimension_findings = self._review_dimension(normalized_text, dimension)
            findings.extend(dimension_findings)
            for finding in dimension_findings:
                if finding.finding_type == FindingType.manual_review_required:
                    manual_review_queue.append(finding.title)

        findings.extend(convert_risk_hits_to_findings(risk_hits))
        findings.extend(convert_consistency_checks_to_findings(consistency_checks))

        manual_review_queue = list(dict.fromkeys(manual_review_queue))
        relative_strengths = collect_relative_strengths(section_index, findings)
        recommendations = build_recommendations(findings)
        overall_conclusion = derive_conclusion(findings)
        summary = self._build_summary(findings, manual_review_queue, overall_conclusion)
        report = ReviewReport(
            parse_result=_build_parse_result_for_text(normalized_text, document_name),
            file_info=file_info,
            scope_statement=scope_statement,
            overall_conclusion=overall_conclusion,
            summary=summary,
            llm_enhanced=False,
            llm_warnings=[],
            findings=findings,
            relative_strengths=relative_strengths,
            section_index=section_index,
            extracted_clauses=extracted_clauses,
            risk_hits=risk_hits,
            consistency_checks=consistency_checks,
            recommendations=recommendations,
            manual_review_queue=manual_review_queue,
            reviewed_dimensions=reviewed_dimensions,
        )
        return self.review_enhancer.enhance(report)

    def review_file(self, path: str | Path) -> ReviewReport:
        document_name, parse_result = load_document(path)
        normalized_text = normalize_text(parse_result.text)
        file_type = detect_file_type(normalized_text)
        file_info = build_file_info(document_name, normalized_text, file_type)
        scope_statement = build_scope_statement(file_info)
        section_index = locate_sections(normalized_text)
        extracted_clauses = extract_clauses(normalized_text)
        risk_hits = match_risk_rules(normalized_text)
        consistency_checks = check_consistency(normalized_text)
        findings: list[Finding] = []
        manual_review_queue: list[str] = []
        reviewed_dimensions: list[str] = []

        for dimension in self.dimensions:
            reviewed_dimensions.append(dimension.display_name)
            dimension_findings = self._review_dimension(normalized_text, dimension)
            findings.extend(dimension_findings)
            for finding in dimension_findings:
                if finding.finding_type == FindingType.manual_review_required:
                    manual_review_queue.append(finding.title)

        findings.extend(convert_risk_hits_to_findings(risk_hits))
        findings.extend(convert_consistency_checks_to_findings(consistency_checks))

        manual_review_queue = list(dict.fromkeys(manual_review_queue))
        relative_strengths = collect_relative_strengths(section_index, findings)
        recommendations = build_recommendations(findings)
        overall_conclusion = derive_conclusion(findings)
        summary = self._build_summary(findings, manual_review_queue, overall_conclusion)
        report = ReviewReport(
            parse_result=parse_result,
            file_info=file_info,
            scope_statement=scope_statement,
            overall_conclusion=overall_conclusion,
            summary=summary,
            llm_enhanced=False,
            llm_warnings=[],
            findings=findings,
            relative_strengths=relative_strengths,
            section_index=section_index,
            extracted_clauses=extracted_clauses,
            risk_hits=risk_hits,
            consistency_checks=consistency_checks,
            recommendations=recommendations,
            manual_review_queue=manual_review_queue,
            reviewed_dimensions=reviewed_dimensions,
        )
        return self.review_enhancer.enhance(report)

    @staticmethod
    def _check_consistency(text: str) -> list[ConsistencyCheck]:
        checks: list[ConsistencyCheck] = []
        checks.append(
            ConsistencyCheck(
                topic="项目属性 vs 履约内容",
                status="issue" if ("货物" in text and ("运维" in text or "实施" in text)) else "ok",
                detail=(
                    "文本同时出现货物属性与运维/实施服务内容，需核查项目属性定性。"
                    if ("货物" in text and ("运维" in text or "实施" in text))
                    else "未发现明显属性与履约内容冲突。"
                ),
            )
        )
        checks.append(
            ConsistencyCheck(
                topic="预算金额 vs 最高限价",
                status="issue" if ("最高限价" in text and "预算金额" not in text) else "ok",
                detail="出现最高限价但未发现预算金额，建议复核金额口径一致性。"
                if ("最高限价" in text and "预算金额" not in text)
                else "预算与限价未见明显冲突。",
            )
        )
        checks.append(
            ConsistencyCheck(
                topic="中小企业政策 vs 价格扣除政策",
                status="issue" if ("专门面向中小企业" in text and "价格扣除" in text) else "ok",
                detail="专门面向中小企业项目仍出现价格扣除条款，可能存在政策口径冲突。"
                if ("专门面向中小企业" in text and "价格扣除" in text)
                else "未发现明显中小企业政策冲突。",
            )
        )
        checks.append(
            ConsistencyCheck(
                topic="技术要求 vs 评分标准",
                status="issue" if ("综合评分" in text and "技术要求" not in text) else "ok",
                detail="出现综合评分，但技术要求定位不足，需核查评分依据。"
                if ("综合评分" in text and "技术要求" not in text)
                else "技术要求与评分标准未见明显脱节。",
            )
        )
        checks.append(
            ConsistencyCheck(
                topic="联合体/分包条款前后一致性",
                status="issue" if ("联合体" in text and "分包" in text and "不得" in text and "允许" in text) else "ok",
                detail="联合体与分包条款中出现允许/禁止混用，需要人工核对前后文。"
                if ("联合体" in text and "分包" in text and "不得" in text and "允许" in text)
                else "未发现明显联合体/分包条款冲突。",
            )
        )
        return checks

    def _review_dimension(self, text: str, dimension: ReviewDimension) -> list[Finding]:
        lowered = text.lower()
        matched_triggers = [item for item in dimension.triggers if item.lower() in lowered]
        matched_missing_markers = [
            item for item in dimension.missing_markers if item.lower() in lowered
        ]

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

    @staticmethod
    def _build_summary(
        findings: list[Finding],
        manual_review_queue: list[str],
        overall_conclusion,
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


def _build_parse_result_for_text(text: str, document_name: str):
    from .models import ParseResult, ParsedPage

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

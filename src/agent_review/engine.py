from __future__ import annotations

from pathlib import Path

from .checklist import DEFAULT_DIMENSIONS
from .models import Evidence, Finding, FindingType, ReviewDimension, ReviewReport, Severity


class TenderReviewEngine:
    """A minimal deterministic review harness.

    This is intentionally simple: it makes the review loop executable before
    integrating OCR, retrieval, or LLM-backed reasoning.
    """

    def __init__(self, dimensions: list[ReviewDimension] | None = None) -> None:
        self.dimensions = dimensions or DEFAULT_DIMENSIONS

    def review_text(self, text: str, document_name: str = "input.txt") -> ReviewReport:
        normalized_text = self._normalize_text(text)
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

        summary = self._build_summary(findings, manual_review_queue)
        return ReviewReport(
            document_name=document_name,
            summary=summary,
            findings=findings,
            manual_review_queue=manual_review_queue,
            reviewed_dimensions=reviewed_dimensions,
        )

    def review_file(self, path: str | Path) -> ReviewReport:
        target = Path(path)
        text = target.read_text(encoding="utf-8")
        return self.review_text(text=text, document_name=target.name)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())

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
    def _build_summary(findings: list[Finding], manual_review_queue: list[str]) -> str:
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
                f"共生成 {len(findings)} 条审查结果，其中 {issue_count} 条需要重点关注，"
                f"{len(manual_review_queue)} 条需要人工复核。"
            )
        return f"共生成 {len(findings)} 条审查结果，其中 {issue_count} 条需要关注。"

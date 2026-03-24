from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class FileType(str, Enum):
    complete_tender = "完整招标文件"
    procurement_requirement = "采购需求文件"
    scoring_detail = "评分细则文件"
    contract_draft = "合同草案"
    mixed_document = "混合型文件"
    unknown = "未知类型"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class FindingType(str, Enum):
    confirmed_issue = "confirmed_issue"
    warning = "warning"
    missing_evidence = "missing_evidence"
    manual_review_required = "manual_review_required"
    pass_ = "pass"


class ConclusionLevel(str, Enum):
    ready = "整体基本规范，可直接使用"
    optimize = "存在个别条款待完善，建议优化后发出"
    revise = "存在明显合规风险，建议修改后再发布"
    reject = "存在实质性不合规问题，不建议直接发布"


@dataclass(slots=True)
class Evidence:
    quote: str
    section_hint: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class Finding:
    dimension: str
    finding_type: FindingType
    severity: Severity
    title: str
    rationale: str
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.0
    next_action: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["finding_type"] = self.finding_type.value
        payload["severity"] = self.severity.value
        payload["evidence"] = [item.to_dict() for item in self.evidence]
        return payload


@dataclass(slots=True)
class ReviewDimension:
    key: str
    display_name: str
    description: str
    triggers: list[str]
    missing_markers: list[str] = field(default_factory=list)
    risk_hint: str = ""


@dataclass(slots=True)
class ParsedPage:
    page_index: int
    text: str
    source: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ParsedTable:
    table_index: int
    row_count: int
    rows: list[list[str]]
    source: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ParseResult:
    parser_name: str
    source_path: str
    source_format: str
    page_count: int | None
    text: str
    pages: list[ParsedPage] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "parser_name": self.parser_name,
            "source_path": self.source_path,
            "source_format": self.source_format,
            "page_count": self.page_count,
            "text": self.text,
            "pages": [item.to_dict() for item in self.pages],
            "tables": [item.to_dict() for item in self.tables],
            "warnings": self.warnings,
        }


@dataclass(slots=True)
class FileInfo:
    document_name: str
    format_hint: str
    text_length: int
    file_type: FileType
    review_scope: str
    review_boundary: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["file_type"] = self.file_type.value
        return payload


@dataclass(slots=True)
class SectionIndex:
    section_name: str
    located: bool
    anchor: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ExtractedClause:
    category: str
    field_name: str
    content: str
    source_anchor: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class RiskHit:
    risk_group: str
    rule_name: str
    severity: Severity
    matched_text: str
    rationale: str
    source_anchor: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["severity"] = self.severity.value
        return payload


@dataclass(slots=True)
class ConsistencyCheck:
    topic: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class Recommendation:
    related_issue: str
    suggestion: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class ReviewReport:
    parse_result: ParseResult
    file_info: FileInfo
    scope_statement: str
    overall_conclusion: ConclusionLevel
    summary: str
    llm_enhanced: bool
    llm_warnings: list[str]
    findings: list[Finding]
    relative_strengths: list[str]
    section_index: list[SectionIndex]
    extracted_clauses: list[ExtractedClause]
    risk_hits: list[RiskHit]
    consistency_checks: list[ConsistencyCheck]
    recommendations: list[Recommendation]
    manual_review_queue: list[str]
    reviewed_dimensions: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "parse_result": self.parse_result.to_dict(),
            "file_info": self.file_info.to_dict(),
            "scope_statement": self.scope_statement,
            "overall_conclusion": self.overall_conclusion.value,
            "summary": self.summary,
            "llm_enhanced": self.llm_enhanced,
            "llm_warnings": self.llm_warnings,
            "findings": [finding.to_dict() for finding in self.findings],
            "relative_strengths": self.relative_strengths,
            "section_index": [item.to_dict() for item in self.section_index],
            "extracted_clauses": [item.to_dict() for item in self.extracted_clauses],
            "risk_hits": [item.to_dict() for item in self.risk_hits],
            "consistency_checks": [item.to_dict() for item in self.consistency_checks],
            "recommendations": [item.to_dict() for item in self.recommendations],
            "manual_review_queue": self.manual_review_queue,
            "reviewed_dimensions": self.reviewed_dimensions,
        }

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


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
class ReviewReport:
    document_name: str
    summary: str
    findings: list[Finding]
    manual_review_queue: list[str]
    reviewed_dimensions: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "summary": self.summary,
            "findings": [finding.to_dict() for finding in self.findings],
            "manual_review_queue": self.manual_review_queue,
            "reviewed_dimensions": self.reviewed_dimensions,
        }

from __future__ import annotations

from .models import (
    ExtractedClause,
    Finding,
    Recommendation,
    RiskHit,
    SpecialistTableRow,
    SpecialistTables,
)


def dedupe_risk_hits(risk_hits: list[RiskHit]) -> list[RiskHit]:
    results: list[RiskHit] = []
    seen: set[tuple[str, str, str, str]] = set()
    for hit in risk_hits:
        key = (hit.risk_group, hit.rule_name, hit.source_anchor, hit.matched_text)
        if key in seen:
            continue
        seen.add(key)
        results.append(hit)
    return results


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    results: list[Finding] = []
    seen: set[tuple[str, str, str, str, str, tuple[tuple[str, str], ...]]] = set()
    for finding in findings:
        evidence_key = tuple((item.quote, item.section_hint) for item in finding.evidence)
        key = (
            finding.dimension,
            finding.title,
            finding.finding_type.value,
            finding.severity.value,
            finding.adoption_status.value,
            evidence_key,
        )
        if key in seen:
            continue
        seen.add(key)
        results.append(finding)
    return results


def dedupe_recommendations(recommendations: list[Recommendation]) -> list[Recommendation]:
    results: list[Recommendation] = []
    seen: set[str] = set()
    for recommendation in recommendations:
        if recommendation.related_issue in seen:
            continue
        seen.add(recommendation.related_issue)
        results.append(recommendation)
    return results


def dedupe_extracted_clauses(clauses: list[ExtractedClause]) -> list[ExtractedClause]:
    results: list[ExtractedClause] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for clause in clauses:
        key = (
            clause.category,
            clause.field_name,
            clause.content,
            clause.source_anchor,
            clause.adoption_status.value,
        )
        if key in seen:
            continue
        seen.add(key)
        results.append(clause)
    return results


def dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def build_specialist_tables(risk_hits: list[RiskHit]) -> SpecialistTables:
    tables = SpecialistTables()
    group_map = {
        "项目结构风险": "project_structure",
        "中小企业政策风险": "sme_policy",
        "人员条件与用工边界风险": "personnel_boundary",
        "合同与履约风险": "contract_performance",
        "模板残留与冲突风险": "template_conflicts",
    }
    for hit in risk_hits:
        target = group_map.get(hit.risk_group)
        if not target:
            continue
        getattr(tables, target).append(
            SpecialistTableRow(
                item_name=hit.rule_name,
                severity=hit.severity,
                detail=hit.rationale,
                source_anchor=hit.source_anchor,
            )
        )
    for table_name in group_map.values():
        rows = getattr(tables, table_name)
        setattr(tables, table_name, _dedupe_specialist_rows(rows))
    return tables


def _dedupe_specialist_rows(rows: list[SpecialistTableRow]) -> list[SpecialistTableRow]:
    results: list[SpecialistTableRow] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (row.item_name, row.detail, row.source_anchor)
        if key in seen:
            continue
        seen.add(key)
        results.append(row)
    return results

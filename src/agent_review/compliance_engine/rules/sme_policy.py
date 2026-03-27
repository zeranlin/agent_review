from __future__ import annotations

from ...models import RiskHit, Severity
from .common import clause_map, first_effective_price_deduction_clause, first_project_bound_clause


def match_sme_policy_risks(text: str, clauses) -> list[RiskHit]:
    mapping = clause_map(clauses)
    hits: list[RiskHit] = []

    special_sme_clause = first_project_bound_clause(mapping, "是否专门面向中小企业")
    price_deduction_clause = first_effective_price_deduction_clause(mapping, "是否仍保留价格扣除条款")
    if (
        special_sme_clause is not None
        and price_deduction_clause is not None
        and special_sme_clause.normalized_value == "是"
        and price_deduction_clause.normalized_value == "是"
    ):
        anchor = _anchor(mapping, "是否专门面向中小企业", "是否仍保留价格扣除条款")
        hits.append(
            RiskHit(
                risk_group="中小企业政策风险",
                rule_name="专门面向中小企业却仍保留价格扣除",
                severity=Severity.high,
                matched_text=f"{special_sme_clause.content} {price_deduction_clause.content}".strip(),
                rationale="专门面向中小企业采购项目仍保留价格扣除模板，政策口径明显冲突。",
                source_anchor=anchor,
            )
        )

    statement_type_clause = _first_content(mapping, "中小企业声明函类型")
    project_type_clause = _first_content(mapping, "项目属性")
    if project_type_clause and statement_type_clause:
        if "服务" in project_type_clause and "制造商" in statement_type_clause:
            hits.append(
                RiskHit(
                    risk_group="中小企业政策风险",
                    rule_name="服务项目声明函类型疑似错用货物模板",
                    severity=Severity.high,
                    matched_text=statement_type_clause,
                    rationale="服务项目中出现制造商口径，疑似误用货物类中小企业声明函模板。",
                    source_anchor=_anchor(mapping, "中小企业声明函类型"),
                )
            )
        if "货物" in project_type_clause and "承接方" in statement_type_clause and "制造商" not in statement_type_clause:
            hits.append(
                RiskHit(
                    risk_group="中小企业政策风险",
                    rule_name="货物项目声明函类型不完整",
                    severity=Severity.medium,
                    matched_text=statement_type_clause,
                    rationale="货物项目声明函仅体现承接方口径，未见制造商表述，需复核模板是否完整。",
                    source_anchor=_anchor(mapping, "中小企业声明函类型"),
                )
            )

    if "预留份额" in text and "分包比例" not in text and "预留比例" not in text:
        hits.append(
            RiskHit(
                risk_group="中小企业政策风险",
                rule_name="预留份额采购但比例信息不明确",
                severity=Severity.medium,
                matched_text="预留份额",
                rationale="文件提到预留份额采购，但未明确分包比例或预留比例，可能影响政策执行。",
                source_anchor=_anchor(mapping, "是否为预留份额采购"),
            )
        )

    return hits


def _first_content(mapping: dict[str, list], key: str) -> str:
    items = mapping.get(key) or []
    return items[0].content if items else ""


def _anchor(mapping: dict[str, list], *keys: str) -> str:
    for key in keys:
        items = mapping.get(key) or []
        if items:
            return items[0].source_anchor
    return "keyword_match"

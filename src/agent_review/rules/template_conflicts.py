from __future__ import annotations

from ..models import RiskHit, Severity
from .common import clause_map, first_effective_price_deduction_clause, first_project_bound_clause


def match_template_conflict_risks(text: str, clauses) -> list[RiskHit]:
    mapping = clause_map(clauses)
    hits: list[RiskHit] = []

    low_risk_terms = ["待定", "空白", "另行通知"]
    if any(term in text for term in low_risk_terms):
        hits.append(
            RiskHit(
                risk_group="模板残留与冲突风险",
                rule_name="一般模板残留",
                severity=Severity.low,
                matched_text=" / ".join(term for term in low_risk_terms if term in text),
                rationale="存在空白、待定或另行通知等一般模板残留，建议清理但通常不直接影响核心执行。",
                source_anchor="keyword_match",
            )
        )

    project_type = _first_content(mapping, "项目属性")
    statement_type = _first_content(mapping, "中小企业声明函类型")
    if "服务" in project_type and "制造商" in statement_type:
        hits.append(
            RiskHit(
                risk_group="模板残留与冲突风险",
                rule_name="服务项目保留货物类声明函模板",
                severity=Severity.high,
                matched_text=statement_type,
                rationale="服务项目仍保留货物类声明函模板，已影响中小企业政策适用和执行。",
                source_anchor=_anchor(mapping, "中小企业声明函类型"),
            )
        )

    special_sme_clause = first_project_bound_clause(mapping, "是否专门面向中小企业")
    price_deduction_clause = first_effective_price_deduction_clause(mapping, "是否仍保留价格扣除条款")
    if (
        special_sme_clause is not None
        and price_deduction_clause is not None
        and special_sme_clause.normalized_value == "是"
        and price_deduction_clause.normalized_value == "是"
    ):
        hits.append(
            RiskHit(
                risk_group="模板残留与冲突风险",
                rule_name="专门面向中小企业却保留价格扣除模板",
                severity=Severity.high,
                matched_text=f"{special_sme_clause.content} {price_deduction_clause.content}".strip(),
                rationale="政策模板冲突已直接影响评审口径和政策执行，应按高风险处理。",
                source_anchor=_anchor(mapping, "是否专门面向中小企业", "是否仍保留价格扣除条款"),
            )
        )

    procurement_subject = _first_content(mapping, "采购标的")
    if "物业" in procurement_subject and "质保期" in text:
        hits.append(
            RiskHit(
                risk_group="模板残留与冲突风险",
                rule_name="物业项目出现货物化模板术语",
                severity=Severity.high,
                matched_text=procurement_subject,
                rationale="物业项目出现质保期等货物化术语，可能影响合同和验收口径。",
                source_anchor=_anchor(mapping, "采购标的", "质保期"),
            )
        )

    if "家具" in procurement_subject and any(token in text for token in ["设计", "测试"]):
        hits.append(
            RiskHit(
                risk_group="模板残留与冲突风险",
                rule_name="家具项目出现不相关模板术语",
                severity=Severity.medium,
                matched_text=procurement_subject,
                rationale="家具项目出现设计、测试等不相关术语，需核查是否存在旧模板未清理。",
                source_anchor=_anchor(mapping, "采购标的"),
            )
        )

    contract_template_residue = _first_content(mapping, "合同模板残留")
    if contract_template_residue:
        hits.append(
            RiskHit(
                risk_group="模板残留与冲突风险",
                rule_name="合同文本存在明显模板残留",
                severity=Severity.high,
                matched_text=contract_template_residue,
                rationale="合同文本中保留了占位符、错行业术语或明显旧模板残留，已影响合同明确性和可执行性。",
                source_anchor=_anchor(mapping, "合同模板残留"),
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

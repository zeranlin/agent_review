from __future__ import annotations

from ...models import ExtractedClause


def clause_map(clauses: list[ExtractedClause]) -> dict[str, list[ExtractedClause]]:
    mapping: dict[str, list[ExtractedClause]] = {}
    for clause in clauses:
        mapping.setdefault(clause.field_name, []).append(clause)
    return mapping


def first_project_bound_clause(mapping: dict[str, list[ExtractedClause]], field_name: str) -> ExtractedClause | None:
    for clause in mapping.get(field_name, []):
        if "项目事实绑定" in clause.relation_tags:
            return clause
        compact = "".join((clause.content or "").split())
        if any(token in compact for token in ["本项目", "本包", "本采购包", "本次采购"]):
            return clause
    return None


def first_effective_price_deduction_clause(mapping: dict[str, list[ExtractedClause]], field_name: str) -> ExtractedClause | None:
    for clause in mapping.get(field_name, []):
        compact = "".join((clause.content or "").split())
        if "专门面向中小企业采购的项目" in compact or "非专门面向中小企业采购的项目" in compact:
            continue
        if "价格扣除比例及采购标的所属行业的说明" in compact:
            continue
        if "项目事实绑定" in clause.relation_tags:
            return clause
        if any(tag in clause.relation_tags for tag in ["价格扣除保留", "价格扣除不适用"]):
            return clause
        if "价格扣除" in compact and any(token in compact for token in ["给予", "扣除", "参与评审", "不适用", "不再适用"]):
            return clause
    return None

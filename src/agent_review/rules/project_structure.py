from __future__ import annotations

from ..models import RiskHit, Severity
from .common import clause_map


def match_project_structure_risks(text: str, clauses) -> list[RiskHit]:
    mapping = clause_map(clauses)
    hits: list[RiskHit] = []

    project_type = _first_content(mapping, "项目属性")
    industry = _first_content(mapping, "所属行业划分")
    statement_type = _first_content(mapping, "中小企业声明函类型")
    procurement_subject = _first_content(mapping, "采购标的")
    goods_terms = any(token in text for token in ["规格型号", "制造商", "质保期", "货物验收"])
    service_terms = any(token in text for token in ["运维", "实施", "服务内容", "驻场"])

    if "货物" in project_type and service_terms:
        hits.append(
            RiskHit(
                risk_group="项目结构风险",
                rule_name="货物项目混入大量服务履约内容",
                severity=Severity.high,
                matched_text=project_type or "货物 / 运维 / 实施",
                rationale="项目属性定性为货物，但文本中存在明显运维、实施或服务履约内容，需核查采购结构是否错配。",
                source_anchor=_anchor(mapping, "项目属性", "采购标的"),
            )
        )

    if "服务" in project_type and goods_terms:
        hits.append(
            RiskHit(
                risk_group="项目结构风险",
                rule_name="服务项目混入货物化履约口径",
                severity=Severity.high,
                matched_text=project_type or "服务 / 规格型号 / 制造商",
                rationale="项目属性定性为服务，但文本中大量出现制造商、规格型号、质保期等货物类表述，需核查项目结构是否混用模板。",
                source_anchor=_anchor(mapping, "项目属性"),
            )
        )

    if "服务" in project_type and "工业" in industry:
        hits.append(
            RiskHit(
                risk_group="项目结构风险",
                rule_name="项目属性与所属行业口径疑似不一致",
                severity=Severity.high,
                matched_text=industry,
                rationale="服务项目中出现工业等疑似货物类行业口径，需核查所属行业填写是否准确。",
                source_anchor=_anchor(mapping, "所属行业划分"),
            )
        )

    if procurement_subject and "家具" in procurement_subject and any(token in text for token in ["设计", "测试"]):
        hits.append(
            RiskHit(
                risk_group="项目结构风险",
                rule_name="家具项目出现非典型结构性术语",
                severity=Severity.medium,
                matched_text=procurement_subject,
                rationale="家具采购项目中出现设计、测试等非典型口径，需核查是否存在模板残留或采购结构混杂。",
                source_anchor=_anchor(mapping, "采购标的"),
            )
        )

    if "服务" in project_type and "制造商" in statement_type:
        hits.append(
            RiskHit(
                risk_group="项目结构风险",
                rule_name="项目属性与声明函模板口径冲突",
                severity=Severity.high,
                matched_text=statement_type,
                rationale="服务项目中出现制造商声明口径，说明项目属性与声明函模板存在结构性冲突。",
                source_anchor=_anchor(mapping, "中小企业声明函类型"),
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

from __future__ import annotations

from ...models import RiskHit, Severity
from .common import clause_map


def match_personnel_boundary_risks(text: str, clauses) -> list[RiskHit]:
    mapping = clause_map(clauses)
    hits: list[RiskHit] = []

    high_risk_terms = {
        "性别限制": "出现性别限制表述，若与岗位核心履职无直接关系，属于高风险。",
        "年龄限制": "出现年龄限制表述，若与履职无直接关系，属于高风险。",
        "身高限制": "出现身高限制表述，若与履职无直接关系，属于高风险。",
        "容貌体形要求": "出现容貌或体形要求，通常超出合理履职条件边界。",
    }
    for field_name, rationale in high_risk_terms.items():
        for clause in mapping.get(field_name, []):
            if any(token in clause.content for token in ["法定代表人", "身份证号码", "退休年龄", "参保", "保险"]):
                continue
            if field_name == "容貌体形要求" and not any(token in clause.content for token in ["容貌", "体形", "五官", "仪容", "端庄"]):
                continue
            hits.append(
                RiskHit(
                    risk_group="人员条件与用工边界风险",
                    rule_name=field_name,
                    severity=Severity.high,
                    matched_text=clause.content,
                    rationale=rationale,
                    source_anchor=clause.source_anchor,
                )
            )

    for field_name in ["采购人审批录用", "采购人批准更换", "采购人直接指挥"]:
        for clause in mapping.get(field_name, []):
            if field_name == "采购人审批录用" and not any(token in clause.content for token in ["录用", "聘用", "上岗"]):
                continue
            hits.append(
                RiskHit(
                    risk_group="人员条件与用工边界风险",
                    rule_name=field_name,
                    severity=Severity.high,
                    matched_text=clause.content,
                    rationale="采购人对供应商内部录用、任免或日常指挥介入过深，可能突破合同管理边界。",
                    source_anchor=clause.source_anchor,
                )
            )

    if "社保" in text and ("学历" in text or "职称" in text):
        hits.append(
            RiskHit(
                risk_group="人员条件与用工边界风险",
                rule_name="人员证明材料负担偏重",
                severity=Severity.medium,
                matched_text="社保 / 学历 / 职称",
                rationale="人员评分或资格证明中叠加社保、学历、职称等材料，可能显著增加投标负担。",
                source_anchor=_anchor(mapping, "人员评分要求", "学历职称要求"),
            )
        )

    return hits


def _anchor(mapping: dict[str, list], *keys: str) -> str:
    for key in keys:
        items = mapping.get(key) or []
        if items:
            return items[0].source_anchor
    return "keyword_match"

from __future__ import annotations

from ...models import RiskHit, Severity
from .common import clause_map


def match_contract_performance_risks(text: str, clauses) -> list[RiskHit]:
    mapping = clause_map(clauses)
    hits: list[RiskHit] = []

    for clause in mapping.get("单方解释权", []):
        hits.append(
            RiskHit(
                risk_group="合同与履约风险",
                rule_name="采购人单方解释或决定条款",
                severity=Severity.high,
                matched_text=clause.content,
                rationale="合同或验收条款存在采购人单方解释或单方决定倾向，可能影响合同公平性。",
                source_anchor=clause.source_anchor,
            )
        )

    for clause in mapping.get("考核条款", []):
        if not any(token in clause.content for token in ["付款", "支付", "尾款", "满意度", "扣款", "评价"]):
            continue
        severity = Severity.high if "满意" in clause.content or any(token in clause.content for token in ["付款", "支付", "尾款", "扣款"]) else Severity.medium
        hits.append(
            RiskHit(
                risk_group="合同与履约风险",
                rule_name="考核条款可能控制付款或履约评价",
                severity=severity,
                matched_text=clause.content,
                rationale="存在考核条款，需要核查考核标准是否量化、是否与付款和扣款联动。",
                source_anchor=clause.source_anchor,
            )
        )

    for clause in mapping.get("扣款条款", []):
        severity = Severity.high if "采购人" in clause.content or "满意" in clause.content else Severity.medium
        hits.append(
            RiskHit(
                risk_group="合同与履约风险",
                rule_name="扣款机制可能过度依赖单方考核",
                severity=severity,
                matched_text=clause.content,
                rationale="存在扣款条款，需要核查扣款公式、触发条件和程序保障是否明确。",
                source_anchor=clause.source_anchor,
            )
        )

    for clause in mapping.get("解约条款", []):
        severity = Severity.high if any(token in clause.content for token in ["不满意", "投诉多", "不配合"]) else Severity.medium
        hits.append(
            RiskHit(
                risk_group="合同与履约风险",
                rule_name="解约条件可能过宽",
                severity=severity,
                matched_text=clause.content,
                rationale="解约条款需核查是否存在宽泛触发条件，以及是否具备通知、整改和申辩程序。",
                source_anchor=clause.source_anchor,
            )
        )

    if ("付款" in text or "支付" in text) and "考核" in text and "尾款" in text:
        hits.append(
            RiskHit(
                risk_group="合同与履约风险",
                rule_name="尾款支付与考核条款联动风险",
                severity=Severity.high,
                matched_text="付款或支付 / 考核 / 尾款",
                rationale="文件同时出现付款、考核和尾款控制要素，需重点核查是否由采购人单方主观评价决定大额尾款。",
                source_anchor=_anchor(mapping, "付款节点", "考核条款", "扣款条款"),
            )
        )

    for clause in mapping.get("合同成果模板术语", []):
        hits.append(
            RiskHit(
                risk_group="合同与履约风险",
                rule_name="合同条款出现非本行业成果模板表述",
                severity=Severity.high,
                matched_text=clause.content,
                rationale="合同中出现成果交付、成果泄露等偏咨询、设计或信息化项目的模板术语，需核查与当前采购场景是否匹配。",
                source_anchor=clause.source_anchor,
            )
        )

    for clause in mapping.get("验收弹性条款", []):
        hits.append(
            RiskHit(
                risk_group="合同与履约风险",
                rule_name="验收标准存在优胜原则或单方弹性判断",
                severity=Severity.high,
                matched_text=clause.content,
                rationale="验收条款出现优胜原则或单方弹性判断口径，可能导致验收标准不客观、不可预期。",
                source_anchor=clause.source_anchor,
            )
        )

    return hits


def _anchor(mapping: dict[str, list], *keys: str) -> str:
    for key in keys:
        items = mapping.get(key) or []
        if items:
            return items[0].source_anchor
    return "keyword_match"

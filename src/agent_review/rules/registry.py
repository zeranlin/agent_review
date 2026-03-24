from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..models import ExtractedClause, RiskHit
from .contract_performance import match_contract_performance_risks
from .personnel_boundary import match_personnel_boundary_risks
from .project_structure import match_project_structure_risks
from .risk_rules import match_risk_rules
from .sme_policy import match_sme_policy_risks
from .template_conflicts import match_template_conflict_risks

RuleMatcher = Callable[[str, list[ExtractedClause]], list[RiskHit]]


@dataclass(frozen=True, slots=True)
class RuleModule:
    name: str
    matcher: RuleMatcher


def build_default_rule_registry() -> tuple[RuleModule, ...]:
    return (
        RuleModule(
            name="baseline_risk_rules",
            matcher=lambda text, _clauses: match_risk_rules(text),
        ),
        RuleModule(name="project_structure", matcher=match_project_structure_risks),
        RuleModule(name="sme_policy", matcher=match_sme_policy_risks),
        RuleModule(name="personnel_boundary", matcher=match_personnel_boundary_risks),
        RuleModule(name="contract_performance", matcher=match_contract_performance_risks),
        RuleModule(name="template_conflicts", matcher=match_template_conflict_risks),
    )


def execute_rule_registry(
    text: str,
    clauses: list[ExtractedClause],
    registry: tuple[RuleModule, ...] | None = None,
) -> tuple[list[RiskHit], list[str]]:
    modules = registry or build_default_rule_registry()
    risk_hits: list[RiskHit] = []
    executed_modules: list[str] = []
    for module in modules:
        risk_hits.extend(module.matcher(text, clauses))
        executed_modules.append(module.name)
    return risk_hits, executed_modules

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ...models import ExtractedClause, RiskHit, RuleSelection
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


CORE_RULE_MODULES: tuple[RuleModule, ...] = (
    RuleModule(
        name="baseline_risk_rules",
        matcher=lambda text, _clauses: match_risk_rules(text),
    ),
    RuleModule(name="sme_policy", matcher=match_sme_policy_risks),
    RuleModule(name="template_conflicts", matcher=match_template_conflict_risks),
)

SCENARIO_RULE_MODULES: dict[str, tuple[RuleModule, ...]] = {
    "goods": (
        RuleModule(name="project_structure", matcher=match_project_structure_risks),
        RuleModule(name="contract_performance", matcher=match_contract_performance_risks),
    ),
    "service": (
        RuleModule(name="project_structure", matcher=match_project_structure_risks),
        RuleModule(name="personnel_boundary", matcher=match_personnel_boundary_risks),
        RuleModule(name="contract_performance", matcher=match_contract_performance_risks),
    ),
    "contract": (
        RuleModule(name="contract_performance", matcher=match_contract_performance_risks),
    ),
    "furniture": (
        RuleModule(name="project_structure", matcher=match_project_structure_risks),
    ),
    "property": (
        RuleModule(name="personnel_boundary", matcher=match_personnel_boundary_risks),
        RuleModule(name="contract_performance", matcher=match_contract_performance_risks),
    ),
    "it": (
        RuleModule(name="project_structure", matcher=match_project_structure_risks),
        RuleModule(name="contract_performance", matcher=match_contract_performance_risks),
    ),
}


def build_default_rule_registry() -> tuple[RuleModule, ...]:
    modules: list[RuleModule] = list(CORE_RULE_MODULES)
    for group in SCENARIO_RULE_MODULES.values():
        for module in group:
            if module.name not in {item.name for item in modules}:
                modules.append(module)
    return tuple(modules)


def execute_rule_registry(
    text: str,
    clauses: list[ExtractedClause],
) -> tuple[list[RiskHit], RuleSelection]:
    selection = select_rule_modules(text=text, clauses=clauses)
    risk_hits: list[RiskHit] = []
    for module in _ordered_modules(selection):
        risk_hits.extend(module.matcher(text, clauses))
    return risk_hits, selection


def select_rule_modules(text: str, clauses: list[ExtractedClause]) -> RuleSelection:
    scenario_tags = detect_scenarios(text=text, clauses=clauses)
    core_modules = [item.name for item in CORE_RULE_MODULES]
    enhancement_modules: list[str] = []
    for tag in scenario_tags:
        for module in SCENARIO_RULE_MODULES.get(tag, ()):
            if module.name not in enhancement_modules and module.name not in core_modules:
                enhancement_modules.append(module.name)
            elif module.name not in enhancement_modules:
                enhancement_modules.append(module.name)
    return RuleSelection(
        core_modules=core_modules,
        enhancement_modules=enhancement_modules,
        scenario_tags=scenario_tags,
    )


def detect_scenarios(text: str, clauses: list[ExtractedClause]) -> list[str]:
    clause_text = "\n".join(item.content for item in clauses)
    corpus = f"{text}\n{clause_text}"
    tags: list[str] = []
    if any(token in corpus for token in ["项目属性：货物", "货物", "制造商", "规格型号"]):
        tags.append("goods")
    if any(token in corpus for token in ["项目属性：服务", "服务", "驻场", "运维", "物业"]):
        tags.append("service")
    if any(token in corpus for token in ["合同条款", "付款方式", "验收标准", "违约责任", "解约"]):
        tags.append("contract")
    if any(token in corpus for token in ["家具", "办公家具", "桌", "椅", "柜"]):
        tags.append("furniture")
    if any(token in corpus for token in ["物业", "保洁", "安保", "秩序维护"]):
        tags.append("property")
    if any(token in corpus for token in ["信息化", "系统", "软件", "平台", "网络"]):
        tags.append("it")
    return list(dict.fromkeys(tags))


def _ordered_modules(selection: RuleSelection) -> tuple[RuleModule, ...]:
    module_lookup = {item.name: item for item in build_default_rule_registry()}
    ordered_names = list(dict.fromkeys(selection.core_modules + selection.enhancement_modules))
    return tuple(module_lookup[name] for name in ordered_names if name in module_lookup)

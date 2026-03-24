"""规则与风险层。"""

from .contract_performance import match_contract_performance_risks
from .personnel_boundary import match_personnel_boundary_risks
from .project_structure import match_project_structure_risks
from .registry import RuleModule, build_default_rule_registry, execute_rule_registry
from .risk_rules import build_recommendations, convert_risk_hits_to_findings, match_risk_rules
from .sme_policy import match_sme_policy_risks
from .template_conflicts import match_template_conflict_risks

__all__ = [
    "RuleModule",
    "build_recommendations",
    "build_default_rule_registry",
    "convert_risk_hits_to_findings",
    "execute_rule_registry",
    "match_contract_performance_risks",
    "match_personnel_boundary_risks",
    "match_project_structure_risks",
    "match_risk_rules",
    "match_sme_policy_risks",
    "match_template_conflict_risks",
]

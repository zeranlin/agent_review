"""ComplianceEngine 入口包。"""

from ..adjudication_core import (
    build_applicability_checks,
    build_formal_adjudication,
    build_review_quality_gates,
    get_authority_binding,
    list_bindings_for_point,
)
from ..compliance import (
    resolve_embedded_issue_authority,
    run_agent_compliance_review_from_parsed_tender_document,
    run_embedded_compliance_review,
)
from ..fact_collectors import collect_task_facts
from ..review_point_contract_registry import get_review_point_contract
from ..rule_runtime import build_review_point_instances, generate_rule_hits
from .routing import (
    build_routing_profile,
    external_routing_hints,
    match_routing_domain_candidates,
)

__all__ = [
    "build_routing_profile",
    "external_routing_hints",
    "match_routing_domain_candidates",
    "generate_rule_hits",
    "build_review_point_instances",
    "collect_task_facts",
    "build_applicability_checks",
    "build_review_quality_gates",
    "build_formal_adjudication",
    "get_authority_binding",
    "list_bindings_for_point",
    "resolve_embedded_issue_authority",
    "run_embedded_compliance_review",
    "run_agent_compliance_review_from_parsed_tender_document",
    "get_review_point_contract",
]

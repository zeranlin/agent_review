"""ComplianceEngine.routing 子模块。"""

from __future__ import annotations

from .compliance.external_data import (
    external_profile_activation_tags,
    external_profile_planning_hints,
    match_external_domain_profile_candidates,
)
from ..parser_engine.structure import build_document_profile


def build_routing_profile(*args, **kwargs):
    return build_document_profile(*args, **kwargs)


def match_routing_domain_candidates(*args, **kwargs):
    return match_external_domain_profile_candidates(*args, **kwargs)


def external_routing_hints(profile_id: str) -> dict[str, object]:
    return {
        "activation_tags": sorted(external_profile_activation_tags(profile_id)),
        "planning_hints": external_profile_planning_hints(profile_id),
    }


__all__ = [
    "build_routing_profile",
    "match_routing_domain_candidates",
    "external_routing_hints",
]

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from ..models import DomainProfileCandidate, LegalBasis


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _data_path(*parts: str) -> Path:
    return _repo_root().joinpath("data", *parts)


def _load_json(path: Path) -> dict | list:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def load_external_authorities_index() -> dict[str, dict[str, object]]:
    payload = _load_json(_data_path("legal-authorities", "index", "authorities.json"))
    authorities = payload.get("authorities", []) if isinstance(payload, dict) else []
    return {
        str(item.get("reference_id", "")).strip(): item
        for item in authorities
        if str(item.get("reference_id", "")).strip()
    }


@lru_cache(maxsize=1)
def load_external_clause_index() -> dict[str, dict[str, object]]:
    payload = _load_json(_data_path("legal-authorities", "index", "clause-index.json"))
    clauses = payload.get("clauses", []) if isinstance(payload, dict) else []
    return {
        str(item.get("clause_id", "")).strip(): item
        for item in clauses
        if str(item.get("clause_id", "")).strip()
    }


@lru_cache(maxsize=1)
def load_review_point_authority_map() -> dict[str, dict[str, object]]:
    payload = _load_json(_data_path("legal-authorities", "index", "review-point-authority-map.json"))
    mappings = payload.get("mappings", []) if isinstance(payload, dict) else []
    return {
        str(item.get("catalog_id", "")).strip(): item
        for item in mappings
        if str(item.get("catalog_id", "")).strip()
    }


def lookup_external_manual_review_boundary(
    *,
    catalog_id: str = "",
    title: str = "",
) -> dict[str, list[str]]:
    mapping = load_review_point_authority_map()
    target = mapping.get(catalog_id) if catalog_id else None
    if target is None and title:
        normalized_title = title.strip()
        for item in mapping.values():
            if str(item.get("review_point_title", "")).strip() == normalized_title:
                target = item
                break
    if target is None:
        return {"reasons": [], "authority_refs": []}

    clause_index = load_external_clause_index()
    authority_refs: list[str] = []
    for clause_id in target.get("primary_clause_ids", []):
        clause = clause_index.get(str(clause_id).strip())
        if clause is None:
            continue
        doc_title = str(clause.get("doc_title", "")).strip()
        article_label = str(clause.get("article_label") or clause.get("chapter_label") or "").strip()
        parts = [item for item in [doc_title, article_label] if item]
        if parts:
            authority_refs.append(" ".join(parts))
    return {
        "reasons": [
            str(item).strip()
            for item in target.get("requires_human_review_when", [])
            if str(item).strip()
        ],
        "authority_refs": authority_refs,
    }


def lookup_external_legal_basis(
    *,
    catalog_id: str = "",
    title: str = "",
) -> list[LegalBasis]:
    mapping = load_review_point_authority_map()
    target = mapping.get(catalog_id) if catalog_id else None
    if target is None and title:
        normalized_title = title.strip()
        for item in mapping.values():
            if str(item.get("review_point_title", "")).strip() == normalized_title:
                target = item
                break
    if target is None:
        return []

    authority_index = load_external_authorities_index()
    clause_index = load_external_clause_index()
    results: list[LegalBasis] = []
    seen: set[tuple[str, str, str]] = set()
    for clause_id in [*target.get("primary_clause_ids", []), *target.get("secondary_clause_ids", [])]:
        clause = clause_index.get(str(clause_id))
        if clause is None:
            continue
        authority = authority_index.get(str(clause.get("reference_id", "")).strip(), {})
        source_name = str(authority.get("reference_title") or clause.get("doc_title") or "外部法规索引").strip()
        article_hint = str(clause.get("article_label") or clause.get("chapter_label") or "").strip()
        summary = str(clause.get("clause_text", "")).strip()
        if not summary:
            continue
        key = (source_name, article_hint, summary)
        if key in seen:
            continue
        seen.add(key)
        results.append(
            LegalBasis(
                source_name=source_name,
                article_hint=article_hint,
                summary=summary,
                basis_type=str(clause.get("authority_level") or "外部法规索引"),
            )
        )
    return results


@lru_cache(maxsize=1)
def load_external_catalog_knowledge_profiles() -> list[dict[str, object]]:
    payload = _load_json(_data_path("procurement-catalog", "catalog-knowledge-profiles.json"))
    return payload.get("profiles", []) if isinstance(payload, dict) else []


@lru_cache(maxsize=1)
def load_external_review_domain_map() -> list[dict[str, object]]:
    payload = _load_json(_data_path("procurement-catalog", "review-domain-map.json"))
    return payload.get("entries", []) if isinstance(payload, dict) else []


def match_external_domain_profile_candidates(
    *,
    text: str,
    procurement_kind: str,
    limit: int = 3,
) -> list[DomainProfileCandidate]:
    haystack = text.strip()
    if not haystack:
        return []
    candidates: list[DomainProfileCandidate] = []
    for profile in load_external_catalog_knowledge_profiles():
        score, reasons = _score_external_profile(profile, haystack, procurement_kind)
        if score <= 0:
            continue
        candidates.append(
            DomainProfileCandidate(
                profile_id=str(profile.get("review_domain_key") or profile.get("catalog_id") or "").strip(),
                confidence=round(min(0.95, score), 3),
                reasons=reasons[:4],
            )
        )
    candidates.sort(key=lambda item: item.confidence, reverse=True)
    deduped: list[DomainProfileCandidate] = []
    seen: set[str] = set()
    for item in candidates:
        if not item.profile_id or item.profile_id in seen:
            continue
        seen.add(item.profile_id)
        deduped.append(item)
    return deduped[:limit]


def external_profile_activation_tags(profile_id: str) -> set[str]:
    for profile in load_external_catalog_knowledge_profiles():
        current_id = str(profile.get("review_domain_key") or profile.get("catalog_id") or "").strip()
        if current_id != profile_id:
            continue
        tags: set[str] = set()
        category_type = str(profile.get("category_type", "")).strip()
        if category_type == "goods":
            tags.add("goods")
        elif category_type == "service":
            tags.add("service")
        elif category_type == "mixed":
            tags.update({"structure", "consistency"})
        text = " ".join(
            str(token)
            for key in [
                "catalog_name",
                "review_domain_key",
                "high_risk_patterns",
                "scoring_risk_markers",
                "scoring_mismatch_markers",
                "commercial_lifecycle_markers",
                "mixed_scope_markers",
            ]
            for token in (
                profile.get(key, []) if isinstance(profile.get(key), list) else [profile.get(key, "")]
            )
        )
        if any(token in text for token in ["家具", "课桌", "桌椅", "档案柜", "床"]):
            tags.add("furniture")
        if any(token in text for token in ["医疗", "器械", "检测报告", "院感"]):
            tags.update({"qualification", "scoring"})
        if any(token in text for token in ["评分", "得分", "证书", "财务"]):
            tags.add("scoring")
        if any(token in text for token in ["验收", "付款", "质保", "售后", "履约"]):
            tags.add("contract")
        if any(token in text for token in ["模板", "声明函", "错位", "错配"]):
            tags.add("template")
        return tags
    return set()


def external_profile_planning_hints(profile_id: str) -> dict[str, list[str]]:
    for profile in load_external_catalog_knowledge_profiles():
        current_id = str(profile.get("review_domain_key") or profile.get("catalog_id") or "").strip()
        if current_id != profile_id:
            continue

        route_tags = set(external_profile_activation_tags(profile_id))
        preferred_fields: list[str] = []
        fallback_fields: list[str] = []
        activation_reasons: list[str] = []

        category_type = str(profile.get("category_type", "")).strip()
        if category_type == "goods":
            _append_unique(preferred_fields, ["交货期限", "验收标准", "质保期"])
        elif category_type == "service":
            _append_unique(preferred_fields, ["服务期限", "考核要求", "付款节点"])
        elif category_type == "mixed":
            _append_unique(fallback_fields, ["采购包数量", "采购内容构成", "合同类型"])

        scoring_markers = [str(item).strip() for item in profile.get("scoring_evidence_markers", []) if str(item).strip()]
        lifecycle_markers = [str(item).strip() for item in profile.get("commercial_lifecycle_markers", []) if str(item).strip()]
        mixed_markers = [str(item).strip() for item in profile.get("mixed_scope_markers", []) if str(item).strip()]
        template_markers = [str(item).strip() for item in profile.get("template_scope_markers", []) if str(item).strip()]
        theme_markers = [str(item).strip() for item in profile.get("scoring_theme_markers", []) if str(item).strip()]

        if scoring_markers or theme_markers:
            route_tags.add("scoring")
            _append_unique(preferred_fields, ["评分方法", "评分项明细"])
            activation_reasons.append(f"external_profile:{current_id}:scoring")
        if lifecycle_markers:
            route_tags.add("contract")
            _append_unique(preferred_fields, ["合同履行期限", "付款节点", "验收标准"])
            activation_reasons.append(f"external_profile:{current_id}:lifecycle")
        if mixed_markers:
            route_tags.update({"structure", "consistency"})
            _append_unique(fallback_fields, ["采购包划分说明", "采购内容构成"])
            activation_reasons.append(f"external_profile:{current_id}:mixed_scope")
        if template_markers:
            route_tags.add("template")
            _append_unique(fallback_fields, ["投标文件格式", "附件引用"])
            activation_reasons.append(f"external_profile:{current_id}:template_scope")

        profile_text = " ".join(
            [
                str(profile.get("catalog_name", "")).strip(),
                " ".join(scoring_markers),
                " ".join(lifecycle_markers),
                " ".join(mixed_markers),
                " ".join(template_markers),
                " ".join(theme_markers),
            ]
        )
        if any(token in profile_text for token in ["医疗", "器械", "检测报告", "CMA", "CNAS"]):
            route_tags.add("qualification")
            _append_unique(preferred_fields, ["证明来源要求", "是否要求检测报告", "证书材料适用阶段"])
        if any(token in profile_text for token in ["家具", "桌", "椅", "样品"]):
            _append_unique(preferred_fields, ["样品要求", "质保期"])
        if any(token in profile_text for token in ["系统", "接口", "演示", "驻场"]):
            _append_unique(preferred_fields, ["系统对接要求", "演示要求", "驻场要求"])
        if any(token in profile_text for token in ["物业", "考核", "满意度"]):
            _append_unique(preferred_fields, ["考核要求", "满意度评价机制"])

        return {
            "route_tags": list(route_tags),
            "preferred_fields": preferred_fields,
            "fallback_fields": fallback_fields,
            "activation_reasons": activation_reasons,
        }
    return {
        "route_tags": [],
        "preferred_fields": [],
        "fallback_fields": [],
        "activation_reasons": [],
    }


def _score_external_profile(
    profile: dict[str, object],
    text: str,
    procurement_kind: str,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    keyword_hits = _collect_keyword_hits(
        text,
        [
            str(profile.get("catalog_name", "")),
            *[str(item) for item in profile.get("reasonable_requirements", [])],
            *[str(item) for item in profile.get("core_delivery_capabilities", [])],
            *[str(item) for item in profile.get("mixed_scope_core_markers", [])],
            *[str(item) for item in profile.get("scoring_theme_markers", [])],
            *[str(item) for item in profile.get("scoring_evidence_markers", [])],
            *[str(item) for item in profile.get("template_scope_markers", [])],
        ],
    )
    mismatch_hits = _collect_keyword_hits(
        text,
        [
            *[str(item) for item in profile.get("common_mismatch_clues", [])],
            *[str(item) for item in profile.get("domain_mismatch_markers", [])],
            *[str(item) for item in profile.get("scoring_mismatch_markers", [])],
        ],
    )
    if not keyword_hits and not mismatch_hits:
        return 0.0, []
    category_type = str(profile.get("category_type", "")).strip()
    if category_type and category_type == procurement_kind:
        score += 0.24
        reasons.append(f"category_type={category_type}")
    if category_type == "mixed" and procurement_kind == "mixed":
        score += 0.24
        reasons.append("mixed_scope_match")
    if keyword_hits:
        score += min(0.42, 0.08 * len(keyword_hits))
        reasons.append(f"keyword_hits={','.join(keyword_hits[:3])}")
    if mismatch_hits:
        score += min(0.22, 0.06 * len(mismatch_hits))
        reasons.append(f"mismatch_hits={','.join(mismatch_hits[:3])}")
    return score, reasons


def _collect_keyword_hits(text: str, terms: list[str]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        current = term.strip()
        if len(current) < 2:
            continue
        if current in text and current not in hits:
            hits.append(current)
    return hits


def _append_unique(target: list[str], items: list[str]) -> None:
    for item in items:
        current = item.strip()
        if current and current not in target:
            target.append(current)

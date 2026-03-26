from agent_review.domain_profiles import build_document_profile, get_domain_profile, profile_activation_tags
from agent_review.models import ExtractedClause
from agent_review.ontology import EffectTag, SemanticZoneType
from agent_review.review_point_catalog import select_standard_review_tasks


def test_domain_profile_registry_contains_requested_minimal_profiles() -> None:
    assert get_domain_profile("generic_goods") is not None
    assert get_domain_profile("generic_service") is not None
    assert get_domain_profile("mixed_procurement") is not None
    assert get_domain_profile("furniture") is not None


def test_build_document_profile_detects_furniture_candidate_from_clause_terms() -> None:
    clauses = [
        ExtractedClause(
            category="技术",
            field_name="采购标的",
            content="课桌椅、书柜、会议桌，附样品要求与环保检测说明。",
            source_anchor="line:12",
            semantic_zone=SemanticZoneType.technical,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="商务",
            field_name="履约要求",
            content="安装、验收、质保与售后服务按约定执行。",
            source_anchor="line:18",
            semantic_zone=SemanticZoneType.business,
            effect_tags=[EffectTag.binding],
        ),
    ]

    profile = build_document_profile("本项目为货物采购，详见附件说明。", clauses)
    candidate_ids = [item.profile_id for item in profile.domain_profile_candidates]

    assert profile.procurement_kind == "goods"
    assert "furniture" in candidate_ids
    assert "furniture" in profile_activation_tags(profile)


def test_template_heavy_profile_enhances_task_activation() -> None:
    clauses = [
        ExtractedClause(
            category="模板",
            field_name="附录一",
            content="示例文本A：本页为格式参考。",
            source_anchor="line:4",
            semantic_zone=SemanticZoneType.template,
            effect_tags=[EffectTag.template, EffectTag.example],
        ),
        ExtractedClause(
            category="模板",
            field_name="附录二",
            content="示例文本B：请按附件格式填写。",
            source_anchor="line:5",
            semantic_zone=SemanticZoneType.template,
            effect_tags=[EffectTag.template, EffectTag.example],
        ),
        ExtractedClause(
            category="模板",
            field_name="附录三",
            content="示例文本C：以下内容仅供参考。",
            source_anchor="line:6",
            semantic_zone=SemanticZoneType.template,
            effect_tags=[EffectTag.template, EffectTag.example],
        ),
        ExtractedClause(
            category="模板",
            field_name="附录四",
            content="示例文本D：请勿直接删除。",
            source_anchor="line:7",
            semantic_zone=SemanticZoneType.template,
            effect_tags=[EffectTag.template, EffectTag.example],
        ),
    ]

    profile = build_document_profile("本项目为货物采购。", clauses)
    tasks = select_standard_review_tasks("本项目为货物采购。", clauses)
    titles = {item.title for item in tasks}

    assert "heavy_template_pollution" in profile.structure_flags
    assert "template" in profile_activation_tags(profile)
    assert "一般模板残留" in titles

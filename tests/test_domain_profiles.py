from agent_review.domain_profiles import build_document_profile, get_domain_profile, profile_activation_tags
from agent_review.models import ExtractedClause
from agent_review.ontology import EffectTag, SemanticZoneType
from agent_review.review_point_catalog import select_standard_review_tasks


def test_domain_profile_registry_contains_requested_minimal_profiles() -> None:
    assert get_domain_profile("generic_goods") is not None
    assert get_domain_profile("generic_service") is not None
    assert get_domain_profile("mixed_procurement") is not None
    assert get_domain_profile("furniture") is not None

    profile = get_domain_profile("generic_goods")
    assert profile is not None
    assert "technical" in profile.supported_zone_types
    assert "技术" in profile.primary_review_types


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


def test_informationized_service_sample_does_not_activate_furniture_profile() -> None:
    clauses = [
        ExtractedClause(
            category="技术",
            field_name="采购标的",
            content="信息化系统开发、接口对接、数据迁移服务，提供测试报告与验收材料。",
            source_anchor="line:11",
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

    profile = build_document_profile("本项目为服务采购，信息化系统开发与运维支撑服务。", clauses)
    tags = profile_activation_tags(profile)

    assert profile.procurement_kind == "service"
    assert "service" in tags
    assert "furniture" not in tags
    assert all(item.profile_id != "furniture" or item.confidence < 0.38 for item in profile.domain_profile_candidates)


def test_informationized_goods_sample_prefers_generic_goods_over_furniture() -> None:
    clauses = [
        ExtractedClause(
            category="技术",
            field_name="采购标的",
            content="视频监控摄像机、存储服务器、平台软件及网络交换设备采购。",
            source_anchor="line:8",
            semantic_zone=SemanticZoneType.technical,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="评分",
            field_name="评分项明细",
            content="投标人提供检测报告、实施方案和交付说明。",
            source_anchor="line:16",
            semantic_zone=SemanticZoneType.scoring,
            effect_tags=[EffectTag.binding],
        ),
    ]

    profile = build_document_profile("项目属性：货物。本项目为信息化设备及平台建设。", clauses)
    candidate_ids = [item.profile_id for item in profile.domain_profile_candidates]

    assert profile.procurement_kind in {"goods", "mixed"}
    assert "generic_goods" in candidate_ids
    assert "furniture" not in candidate_ids[:2]


def test_build_document_profile_keeps_unknown_documents_on_conservative_activation() -> None:
    profile = build_document_profile("本文件仅供说明相关事项。", [])
    tags = profile_activation_tags(profile)
    candidate_ids = [item.profile_id for item in profile.domain_profile_candidates]

    assert profile.procurement_kind == "unknown"
    assert profile.routing_mode == "unknown_conservative"
    assert "unknown_procurement_kind" in profile.routing_reasons
    assert "generic_goods" in candidate_ids
    assert "generic_service" in candidate_ids
    assert "unknown_document" in profile.risk_activation_hints
    assert "unknown_procurement_kind" in profile.unknown_structure_flags
    assert "goods" not in tags
    assert "service" not in tags
    assert "structure" not in tags
    assert "scoring" not in tags


def test_unknown_document_can_pick_up_common_block_signals_without_goods_specific_activation() -> None:
    clauses = [
        ExtractedClause(
            category="资格",
            field_name="资格条件明细",
            content="投标人须具备合法经营资格。",
            source_anchor="line:3",
            semantic_zone=SemanticZoneType.qualification,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="评分",
            field_name="评分方法",
            content="评分方法采用综合评分，样品与检测报告仅作佐证。",
            source_anchor="line:6",
            semantic_zone=SemanticZoneType.scoring,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="合同",
            field_name="付款节点",
            content="验收后按进度付款。",
            source_anchor="line:9",
            semantic_zone=SemanticZoneType.contract,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="模板",
            field_name="声明函格式",
            content="声明函模板仅供参考。",
            source_anchor="line:12",
            semantic_zone=SemanticZoneType.template,
            effect_tags=[EffectTag.template, EffectTag.example],
        ),
    ]

    profile = build_document_profile("本文件仅供说明相关事项，详见附件。", clauses)
    tags = profile_activation_tags(profile)

    assert profile.procurement_kind == "unknown"
    assert "unknown_document" in profile.risk_activation_hints
    assert "scoring" in tags
    assert "contract" in tags
    assert "template" in tags
    assert "goods" not in tags
    assert "service" not in tags
    assert "furniture" not in tags
    assert "structure" not in tags


def test_build_document_profile_distinguishes_goods_service_and_mixed_profiles() -> None:
    goods_clauses = [
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
    service_clauses = [
        ExtractedClause(
            category="商务",
            field_name="人员要求",
            content="项目团队需驻场服务，人员更换须经采购人同意。",
            source_anchor="line:4",
            semantic_zone=SemanticZoneType.business,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="合同",
            field_name="付款方式",
            content="验收后按季度支付服务费用。",
            source_anchor="line:8",
            semantic_zone=SemanticZoneType.contract,
            effect_tags=[EffectTag.binding],
        ),
    ]
    mixed_clauses = [
        ExtractedClause(
            category="结构",
            field_name="采购包划分说明",
            content="货物与服务分包采购，分别设置采购包。",
            source_anchor="line:2",
            semantic_zone=SemanticZoneType.administrative_info,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="合同",
            field_name="采购内容构成",
            content="货物、安装与后续服务并存。",
            source_anchor="line:6",
            semantic_zone=SemanticZoneType.mixed_or_uncertain,
            effect_tags=[EffectTag.binding],
        ),
    ]

    goods_profile = build_document_profile("本项目为货物采购，家具、课桌椅、检测报告、样品、参数齐全。", goods_clauses)
    service_profile = build_document_profile("本项目为服务采购，驻场、运维、人员更换、验收、付款条款明确。", service_clauses)
    mixed_profile = build_document_profile("本项目包含货物与服务，采购包分开管理。", mixed_clauses)

    assert goods_profile.procurement_kind == "goods"
    assert "goods" in profile_activation_tags(goods_profile)
    assert "service" not in profile_activation_tags(goods_profile)
    assert any(item.profile_id in {"generic_goods", "furniture"} for item in goods_profile.domain_profile_candidates)

    assert service_profile.procurement_kind == "service"
    assert "service" in profile_activation_tags(service_profile)
    assert "goods" not in profile_activation_tags(service_profile)
    assert any(item.profile_id == "generic_service" for item in service_profile.domain_profile_candidates)

    assert mixed_profile.procurement_kind == "mixed"
    assert "structure" in profile_activation_tags(mixed_profile)
    assert "consistency" in profile_activation_tags(mixed_profile)
    assert any(item.profile_id == "mixed_procurement" for item in mixed_profile.domain_profile_candidates)


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

from agent_review.pipeline import ReviewPipeline, ReviewPipelineState, build_parse_result_for_text


def _build_profile_state(text: str, document_name: str) -> tuple[ReviewPipeline, ReviewPipelineState]:
    parse_result = build_parse_result_for_text(text, document_name)
    pipeline = ReviewPipeline()
    state = ReviewPipelineState(
        document_name=document_name,
        parse_result=parse_result,
        normalized_text=parse_result.text,
    )
    pipeline._stage_document_structure(state)
    pipeline._stage_document_profiling(state)
    return pipeline, state


def test_document_profile_is_built_before_review_task_planning() -> None:
    text = """
    项目属性：货物
    综合评分法评标信息
    评分项 | 分值 | 评分标准
    检测报告 | 5 | 提供得分
    第三章 投标文件格式、附件
    中小企业声明函（格式）
    """

    pipeline, state = _build_profile_state(text, "profile.txt")
    profile = state.parse_result.document_profile

    assert profile is not None
    assert profile.procurement_kind in {"goods", "mixed"}
    assert profile.domain_profile_candidates
    assert "heavy_scoring_tables" in profile.structure_flags
    assert "scoring_dense_structure" in profile.structure_flags
    assert "scoring_quantification" in profile.risk_activation_hints
    assert profile.representative_anchors[0] in {"line:3", "line:4"}
    assert any(anchor in {"line:5", "line:6", "line:7"} for anchor in profile.representative_anchors)
    assert state.parse_result.to_dict()["document_profile"]["procurement_kind"] == profile.procurement_kind

    stage_names = [item.__name__ for item in pipeline.stages]
    assert stage_names.index("_stage_document_profiling") < stage_names.index("_stage_review_task_planning")


def test_document_profile_marks_unknown_documents_and_retains_candidates() -> None:
    text = """
    采购说明
    本文件用于说明相关事项。
    附件一 见附表
    """

    _, state = _build_profile_state(text, "unknown.txt")
    profile = state.parse_result.document_profile

    assert profile is not None
    assert profile.procurement_kind == "unknown"
    assert profile.domain_profile_candidates
    assert "unknown_procurement_kind" in profile.unknown_structure_flags
    assert "unknown_document_first" in profile.structure_flags
    assert "unknown_document_first" in profile.risk_activation_hints
    assert "unknown_attachment_driven_structure" in profile.unknown_structure_flags
    assert "weak_source_support" in profile.quality_flags
    assert "unknown_low_clause_support" in profile.unknown_structure_flags
    assert profile.summary.startswith("文件《unknown.txt》初步画像")


def test_document_profile_prioritizes_scoring_template_and_attachment_anchors() -> None:
    text = """
    采购说明
    综合评分法评标信息
    评分项 | 分值 | 评分标准
    检测报告 | 5 | 提供得分
    第三章 投标文件格式、附件
    中小企业声明函（格式）
    附件二 售后承诺
    """

    _, state = _build_profile_state(text, "anchor_priority.txt")
    profile = state.parse_result.document_profile

    assert profile is not None
    assert profile.procurement_kind == "unknown"
    assert "scoring_dense_structure" in profile.structure_flags
    assert "template_pollution" in profile.structure_flags
    assert "attachment_driven_structure" in profile.structure_flags
    assert "unknown_scoring_dense_structure" in profile.unknown_structure_flags
    assert "unknown_template_pollution" in profile.unknown_structure_flags
    assert "unknown_attachment_driven_structure" in profile.unknown_structure_flags
    assert "unknown_document_first" in profile.risk_activation_hints
    assert "scoring_dense_structure" in profile.risk_activation_hints
    assert "template_pollution" in profile.risk_activation_hints
    assert "attachment_driven_structure" in profile.risk_activation_hints
    assert profile.representative_anchors[0] in {"line:3", "line:4"}
    assert any(anchor in {"line:5", "line:6", "line:7"} for anchor in profile.representative_anchors)


def test_document_profile_marks_directory_template_and_attachment_noise_as_unknown_first() -> None:
    text = """
    目录
    第一章 招标公告
    第二章 采购需求
    第三章 投标文件格式、附件
    中小企业声明函（格式）
    法定代表人授权书（格式）
    附件一 售后承诺
    附件二 见附件
    """

    _, state = _build_profile_state(text, "directory_noise.txt")
    profile = state.parse_result.document_profile

    assert profile is not None
    assert profile.procurement_kind == "unknown"
    assert "catalog_navigation_heavy" in profile.structure_flags
    assert "directory_driven_structure" in profile.structure_flags
    assert "template_pollution" in profile.structure_flags
    assert "attachment_driven_structure" in profile.structure_flags
    assert "catalog_navigation_high" in profile.quality_flags
    assert "template_appendix_mix_high" in profile.quality_flags
    assert "unknown_catalog_navigation" in profile.unknown_structure_flags
    assert "unknown_template_pollution" in profile.unknown_structure_flags
    assert "unknown_attachment_driven_structure" in profile.unknown_structure_flags
    assert "unknown_low_clause_support" in profile.unknown_structure_flags
    assert "unknown_document_first" in profile.risk_activation_hints
    assert "catalog_navigation" in profile.risk_activation_hints
    assert "directory_navigation" in profile.risk_activation_hints
    assert "template_conflict" in profile.risk_activation_hints


def test_document_profile_keeps_known_goods_documents_out_of_unknown_flags() -> None:
    text = """
    目录
    第一章 招标公告
    第二章 采购需求
    第三章 投标文件格式、附件
    项目属性：货物
    课桌椅、书柜、检测报告、样品、安装验收。
    """

    _, state = _build_profile_state(text, "goods_with_directory_noise.txt")
    profile = state.parse_result.document_profile

    assert profile is not None
    assert profile.procurement_kind == "goods"
    assert "unknown_document_first" not in profile.structure_flags
    assert "unknown_catalog_navigation" not in profile.unknown_structure_flags
    assert "unknown_template_pollution" not in profile.unknown_structure_flags
    assert "unknown_attachment_driven_structure" not in profile.unknown_structure_flags


def test_document_profile_does_not_surface_furniture_candidate_for_informationized_goods_sample() -> None:
    text = """
    项目属性：货物
    采购标的：视频监控摄像机、存储服务器、网络交换机及平台软件。
    投标人需提供实施方案、系统接口对接和数据迁移说明。
    """

    _, state = _build_profile_state(text, "it_goods_profile.txt")
    profile = state.parse_result.document_profile

    assert profile is not None
    candidate_ids = [item.profile_id for item in profile.domain_profile_candidates[:3]]
    assert "furniture" not in candidate_ids


def test_document_profile_keeps_furniture_candidate_for_real_furniture_goods_sample() -> None:
    text = """
    项目属性：货物
    本项目采购学生课桌椅、书柜、讲桌及配套家具。
    供应商需完成安装、调试、验收和质保服务。
    """

    _, state = _build_profile_state(text, "furniture_goods_profile.txt")
    profile = state.parse_result.document_profile

    assert profile is not None
    candidate_ids = [item.profile_id for item in profile.domain_profile_candidates[:3]]
    assert "generic_goods" in candidate_ids
    assert "furniture" in candidate_ids


def test_document_profile_treats_catalog_template_and_appendix_as_non_body_structure() -> None:
    text = """
    目录
    第一章 投标文件格式
    第二章 投标文件附件
    附件一 声明函（格式）
    附件二 说明
    详见附件
    """

    _, state = _build_profile_state(text, "non_body_structure.txt")
    profile = state.parse_result.document_profile

    assert profile is not None
    assert profile.procurement_kind == "unknown"
    assert "unknown_document_first" in profile.structure_flags
    assert "template_pollution" in profile.structure_flags or "heavy_template_pollution" in profile.structure_flags
    assert "attachment_driven_structure" in profile.structure_flags
    assert "template_ratio_high" in profile.quality_flags
    assert "reference_ratio_high" in profile.quality_flags
    assert "non_body_structure_dominant" in profile.quality_flags
    assert "non_body_structure_dominant" in profile.unknown_structure_flags
    assert "attachment_first_structure" in profile.unknown_structure_flags
    assert "unknown_template_pollution" in profile.unknown_structure_flags
    assert "unknown_attachment_driven_structure" in profile.unknown_structure_flags
    assert "unknown_document_first" in profile.risk_activation_hints
    assert "template_conflict" in profile.risk_activation_hints
    assert "attachment_driven_structure" in profile.risk_activation_hints
    assert "catalog_noise_present" in profile.risk_activation_hints

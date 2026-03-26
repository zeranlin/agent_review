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
    assert any(flag in profile.structure_flags for flag in ["heavy_scoring_tables", "heavy_template_pollution"])
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
    assert profile.unknown_structure_flags
    assert profile.summary.startswith("文件《unknown.txt》初步画像")

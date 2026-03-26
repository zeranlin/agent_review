from agent_review.adjudication import build_formal_adjudication
from agent_review.engine import TenderReviewEngine
from agent_review.models import (
    ApplicabilityCheck,
    ClauseRole,
    EffectTagResult,
    Evidence,
    EvidenceBundle,
    ExtractedClause,
    FormalDisposition,
    QualityGateStatus,
    ReviewPoint,
    ReviewPointStatus,
    SemanticZoneType,
    Severity,
    SourceAnchor,
)
from agent_review.ontology import EffectTag
from agent_review.review_quality_gate import build_review_quality_gates


def test_pipeline_clause_extraction_prefers_clause_units() -> None:
    text = """
    关键信息
    项目属性：货物
    第一章 招标公告
    投标人资格要求
    投标人须具备相关资质。
    综合评分法评标信息
    评分项 | 分值 | 评分标准
    检测报告 | 5 | 提供得分
    """
    report = TenderReviewEngine().review_text(text, document_name="demo.txt")

    assert report.parse_result.clause_units
    assert any(item.field_name == "项目属性" for item in report.extracted_clauses)
    clause_stage = next(item for item in report.stage_records if item.stage_name == "clause_extraction")
    assert "ClauseUnit" in clause_stage.detail


def test_template_effect_tags_filter_quality_gate_and_formal_adjudication() -> None:
    point = ReviewPoint(
        point_id="RP-001",
        catalog_id="RP-REST-002",
        title="产地厂家商标限制",
        dimension="A.限制竞争风险",
        severity=Severity.high,
        status=ReviewPointStatus.confirmed,
        rationale="模板中出现品牌相关示例文本。",
        evidence_bundle=EvidenceBundle(
            direct_evidence=[Evidence(quote="中小企业声明函（格式）品牌填写示例", section_hint="line:12")],
            clause_roles=[ClauseRole.form_template],
        ),
    )
    extracted_clause = ExtractedClause(
        category="模板",
        field_name="模板示例",
        content="中小企业声明函（格式）品牌填写示例",
        source_anchor="line:12",
        clause_role=ClauseRole.form_template,
        semantic_zone=SemanticZoneType.template,
        effect_tags=[EffectTag.template, EffectTag.example],
    )
    quality_gates = build_review_quality_gates([point], [extracted_clause])
    assert quality_gates[0].status == QualityGateStatus.filtered

    formal = build_formal_adjudication(
        [point],
        [
            ApplicabilityCheck(
                point_id="RP-001",
                catalog_id="RP-REST-002",
                applicable=True,
                requirement_chain_complete=True,
                summary="要件链成立。",
            )
        ],
        quality_gates,
        "中小企业声明函（格式）品牌填写示例",
        [extracted_clause],
        [],
    )
    assert formal[0].disposition != FormalDisposition.include

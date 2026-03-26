from agent_review.applicability import build_applicability_checks
from agent_review.fact_collectors import collect_task_facts
from agent_review.models import (
    ClauseRole,
    EvidenceBundle,
    ExtractedClause,
    ReviewPoint,
    ReviewPointStatus,
    SemanticZoneType,
    Severity,
)
from agent_review.ontology import EffectTag
from agent_review.review_point_catalog import resolve_review_point_definition, select_standard_review_tasks


def test_template_scoring_phrase_does_not_activate_scoring_tasks() -> None:
    clauses = [
        ExtractedClause(
            category="模板",
            field_name="中小企业声明函类型",
            content="中小企业声明函（格式），以下评分示例仅供参考。",
            source_anchor="line:5",
            clause_role=ClauseRole.form_template,
            semantic_zone=SemanticZoneType.template,
            effect_tags=[EffectTag.template, EffectTag.example],
        )
    ]

    tasks = select_standard_review_tasks("中小企业声明函（格式），以下评分示例仅供参考。", clauses)
    titles = {item.title for item in tasks}

    assert "方案评分主观性过强，量化不足" not in titles
    assert "证书类评分分值偏高" not in titles


def test_qualification_boundary_prefers_real_scoring_clause_over_template_phrase() -> None:
    definition = resolve_review_point_definition(
        "资格条件与评分因素重复设门槛",
        "资格与评分边界风险",
        Severity.high,
    )
    clauses = [
        ExtractedClause(
            category="资格",
            field_name="资格条件明细",
            content="投标人须具备项目经理证书，否则将视为非实质性响应。",
            source_anchor="line:12",
            clause_role=ClauseRole.qualification_or_scoring,
            semantic_zone=SemanticZoneType.qualification,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="模板",
            field_name="评分项明细",
            content="评分表示例：项目经理证书得2分。",
            source_anchor="line:30",
            clause_role=ClauseRole.form_template,
            semantic_zone=SemanticZoneType.template,
            effect_tags=[EffectTag.template, EffectTag.example],
        ),
        ExtractedClause(
            category="评分",
            field_name="评分项明细",
            content="项目经理证书：具备得2分，最高得2分。",
            source_anchor="line:42",
            clause_role=ClauseRole.qualification_or_scoring,
            semantic_zone=SemanticZoneType.scoring,
            effect_tags=[EffectTag.binding],
        ),
    ]

    bundle, status, _ = collect_task_facts(definition, clauses)
    quotes = [item.quote for item in bundle.direct_evidence + bundle.supporting_evidence]

    assert status != ReviewPointStatus.identified
    assert any("项目经理证书：具备得2分" in quote for quote in quotes)
    assert all("评分表示例" not in quote for quote in quotes)


def test_applicability_does_not_close_on_template_only_policy_clauses() -> None:
    point = ReviewPoint(
        point_id="RP-SME-TPL",
        catalog_id="RP-SME-001",
        title="专门面向中小企业却仍保留价格扣除",
        dimension="中小企业政策风险",
        severity=Severity.high,
        status=ReviewPointStatus.suspected,
        rationale="当前仅在模板说明中出现中小企业和价格扣除字样。",
        evidence_bundle=EvidenceBundle(),
        legal_basis=[],
        source_findings=[],
    )
    clauses = [
        ExtractedClause(
            category="模板",
            field_name="是否专门面向中小企业",
            content="声明函模板：本项目专门面向中小企业采购。",
            source_anchor="line:7",
            normalized_value="是",
            clause_role=ClauseRole.form_template,
            semantic_zone=SemanticZoneType.template,
            effect_tags=[EffectTag.template, EffectTag.example],
        ),
        ExtractedClause(
            category="模板",
            field_name="是否仍保留价格扣除条款",
            content="声明函模板示例：对小微企业给予价格扣除。",
            source_anchor="line:8",
            normalized_value="是",
            clause_role=ClauseRole.form_template,
            semantic_zone=SemanticZoneType.template,
            effect_tags=[EffectTag.template, EffectTag.example],
        ),
    ]

    checks = build_applicability_checks([point], clauses)

    assert checks[0].applicable is False
    assert checks[0].requirement_chain_complete is False
    assert any("弱来源" in item.detail for item in checks[0].requirement_results)

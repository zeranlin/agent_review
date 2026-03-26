from agent_review.applicability import build_applicability_checks
from agent_review.domain_profiles import build_document_profile
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


def test_unknown_document_uses_common_block_signals_without_goods_specific_tasks() -> None:
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
            content="项目按进度付款。",
            source_anchor="line:9",
            semantic_zone=SemanticZoneType.contract,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="合同",
            field_name="验收标准",
            content="验收标准为合格。",
            source_anchor="line:10",
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
    tasks = select_standard_review_tasks(
        "本文件仅供说明相关事项，详见附件。",
        clauses,
        document_profile=profile,
    )
    titles = {item.title for item in tasks}

    assert profile.procurement_kind == "unknown"
    assert "unknown_document" in profile.risk_activation_hints
    assert "资格条件与评分因素重复设门槛" in titles
    assert "评审方法出现但评分标准不够清晰" in titles
    assert "验收与付款/考核/满意度联动不当" in titles
    assert "指定品牌/原厂限制" not in titles
    assert "产地厂家商标限制" not in titles
    assert "专利要求" not in titles
    assert "刚性门槛型专利要求" not in titles
    assert "服务项目保留货物类声明函模板" not in titles
    assert "家具项目出现不相关模板术语" not in titles
    assert "货物项目混入大量服务履约内容" not in titles


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


def test_applicability_ignores_citation_like_policy_noise() -> None:
    point = ReviewPoint(
        point_id="RP-SME-CITE",
        catalog_id="RP-SME-001",
        title="专门面向中小企业却仍保留价格扣除",
        dimension="中小企业政策风险",
        severity=Severity.high,
        status=ReviewPointStatus.suspected,
        rationale="当前仅在法规引用中出现中小企业和价格扣除字样。",
        evidence_bundle=EvidenceBundle(),
        legal_basis=[],
        source_findings=[],
    )
    clauses = [
        ExtractedClause(
            category="法规引用",
            field_name="是否专门面向中小企业",
            content="一、《中华人民共和国政府采购法》第二十二条 供应商应当具备下列条件之一。",
            source_anchor="line:21",
            normalized_value="是",
            clause_role=ClauseRole.policy_explanation,
            semantic_zone=SemanticZoneType.policy_explanation,
            effect_tags=[EffectTag.reference_only],
        ),
        ExtractedClause(
            category="法规引用",
            field_name="是否仍保留价格扣除条款",
            content="二、《财政部文件》规定价格扣除按政策执行。",
            source_anchor="line:22",
            normalized_value="是",
            clause_role=ClauseRole.policy_explanation,
            semantic_zone=SemanticZoneType.policy_explanation,
            effect_tags=[EffectTag.reference_only],
        ),
    ]

    checks = build_applicability_checks([point], clauses)

    assert checks[0].applicable is False
    assert checks[0].requirement_chain_complete is False
    assert any("弱来源" in item.detail for item in checks[0].requirement_results)

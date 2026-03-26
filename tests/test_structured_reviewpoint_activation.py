from agent_review.applicability import build_applicability_checks
from agent_review.domain_profiles import build_document_profile
from agent_review.fact_collectors import collect_task_facts
from agent_review.legal_semantics import infer_clause_constraint, infer_legal_effect, infer_legal_principle_tags
from agent_review.models import (
    ClauseRole,
    EvidenceBundle,
    ExtractedClause,
    ReviewPoint,
    ReviewPointStatus,
    SemanticZoneType,
    Severity,
)
from agent_review.ontology import ClauseSemanticType, EffectTag
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


def test_unknown_document_routes_structure_noise_into_structure_tasks() -> None:
    text = """
    目录
    第一章 招标公告
    第二章 采购需求
    第三章 投标文件格式、附件
    中小企业声明函（格式）
    法定代表人授权书（格式）
    附件一 说明
    附件二 见附件
    """

    profile = build_document_profile(text, [])
    tasks = select_standard_review_tasks(text, [], document_profile=profile)
    titles = {item.title for item in tasks}

    assert profile.procurement_kind == "unknown"
    assert "项目属性与声明函模板口径冲突" in titles
    assert "项目属性与合同类型口径疑似不一致" in titles or "项目结构与合同类型口径疑似不一致" in titles
    assert "一般模板残留" in titles


def test_unknown_conservative_routing_suppresses_personnel_family_without_strong_fields() -> None:
    clauses = [
        ExtractedClause(
            category="评分",
            field_name="评分方法",
            content="采用综合评分法。",
            source_anchor="line:3",
            semantic_zone=SemanticZoneType.scoring,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="合同",
            field_name="付款节点",
            content="按进度付款。",
            source_anchor="line:8",
            semantic_zone=SemanticZoneType.contract,
            effect_tags=[EffectTag.binding],
        ),
    ]

    profile = build_document_profile("本文件仅供说明相关事项，详见附件。", clauses)
    tasks = select_standard_review_tasks("本文件仅供说明相关事项，详见附件。", clauses, document_profile=profile)
    titles = {item.title for item in tasks}

    assert profile.routing_mode == "unknown_conservative"
    assert "团队稳定性要求过强" not in titles


def test_unknown_conservative_routing_keeps_personnel_family_with_override_fields() -> None:
    clauses = [
        ExtractedClause(
            category="商务",
            field_name="团队稳定性要求",
            content="核心团队成员在服务期间不得更换。",
            source_anchor="line:5",
            semantic_zone=SemanticZoneType.business,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="评分",
            field_name="人员评分要求",
            content="项目负责人具备相关经验得2分。",
            source_anchor="line:9",
            semantic_zone=SemanticZoneType.scoring,
            effect_tags=[EffectTag.binding],
        ),
    ]

    profile = build_document_profile("本文件仅供说明相关事项，详见附件。", clauses)
    tasks = select_standard_review_tasks("本文件仅供说明相关事项，详见附件。", clauses, document_profile=profile)
    titles = {item.title for item in tasks}

    assert profile.routing_mode == "unknown_conservative"
    assert "团队稳定性要求过强" in titles


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


def test_applicability_requires_project_binding_for_conditional_policy_matrix() -> None:
    point = ReviewPoint(
        point_id="RP-SME-COND",
        catalog_id="RP-SME-001",
        title="专门面向中小企业却仍保留价格扣除",
        dimension="中小企业政策风险",
        severity=Severity.high,
        status=ReviewPointStatus.suspected,
        rationale="当前仅看到条件政策矩阵，尚未看到本项目路径绑定。",
        evidence_bundle=EvidenceBundle(),
        legal_basis=[],
        source_findings=[],
    )
    clauses = [
        ExtractedClause(
            category="政策条款",
            field_name="是否专门面向中小企业",
            content="（1）专门面向中小企业采购的项目，不再执行价格扣除比例。",
            source_anchor="line:30",
            normalized_value="",
            relation_tags=["conditional_policy", "条件政策说明", "专门面向中小企业路径", "价格扣除不适用"],
            clause_role=ClauseRole.policy_explanation,
            semantic_zone=SemanticZoneType.policy_explanation,
            effect_tags=[],
        ),
        ExtractedClause(
            category="政策条款",
            field_name="是否仍保留价格扣除条款",
            content="（2）非专门面向中小企业采购的项目，应执行价格扣除比例。",
            source_anchor="line:31",
            normalized_value="",
            relation_tags=["conditional_policy", "条件政策说明", "非专门面向中小企业路径", "价格扣除保留"],
            clause_role=ClauseRole.policy_explanation,
            semantic_zone=SemanticZoneType.policy_explanation,
            effect_tags=[],
        ),
    ]

    checks = build_applicability_checks([point], clauses)

    assert checks[0].applicable is False
    assert checks[0].requirement_chain_complete is False
    assert any("条件政策说明" in item.detail or "本项目事实绑定" in item.detail for item in checks[0].requirement_results)


def test_qualification_gate_tasks_activate_for_excessive_threshold_clauses() -> None:
    clauses = [
        ExtractedClause(
            category="资格条款",
            field_name="资格门槛明细",
            content="10.投标人须为全国科技型中小企业；",
            source_anchor="line:80",
            clause_role=ClauseRole.qualification_or_scoring,
            semantic_zone=SemanticZoneType.qualification,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="资格条款",
            field_name="资格门槛明细",
            content="12.投标人须提供纳税信用A级证明（提供税务部门出具的证明扫描件）；",
            source_anchor="line:82",
            clause_role=ClauseRole.qualification_or_scoring,
            semantic_zone=SemanticZoneType.qualification,
            effect_tags=[EffectTag.binding],
        ),
        ExtractedClause(
            category="资格条款",
            field_name="资格门槛明细",
            content="14.投标人须具备广州市医疗器械行业同类项目业绩不少于2个（提供合同扫描件）。",
            source_anchor="line:84",
            clause_role=ClauseRole.qualification_or_scoring,
            semantic_zone=SemanticZoneType.qualification,
            effect_tags=[EffectTag.binding],
        ),
    ]
    for clause in clauses:
        clause.legal_effect_type = infer_legal_effect(
            text=clause.content,
            zone_type=clause.semantic_zone,
            clause_semantic_type=ClauseSemanticType.qualification_condition,
            field_name=clause.field_name,
        )
        clause.clause_constraint = infer_clause_constraint(clause.content, clause.legal_effect_type)
        clause.legal_principle_tags = infer_legal_principle_tags(
            clause.content,
            clause.legal_effect_type,
            clause.clause_constraint,
        )

    tasks = select_standard_review_tasks("申请人的资格要求", clauses)
    titles = {item.title for item in tasks}

    assert "资格条件可能缺乏履约必要性或带有歧视性门槛" in titles
    assert "资格业绩要求可能存在地域限定、行业口径过窄或与评分重复" in titles

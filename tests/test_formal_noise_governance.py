from agent_review.adjudication import build_formal_adjudication
from agent_review.applicability import build_applicability_checks
from agent_review.models import (
    ApplicabilityCheck,
    ClauseRole,
    Evidence,
    EvidenceBundle,
    EvidenceLevel,
    ExtractedClause,
    LegalBasis,
    ParsedTable,
    QualityGateStatus,
    ReviewPoint,
    ReviewPointStatus,
    Severity,
)
from agent_review.ontology import EffectTag, SemanticZoneType
from agent_review.review_quality_gate import build_review_quality_gates


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


def test_quality_gate_filters_legal_citation_like_noise() -> None:
    point = ReviewPoint(
        point_id="RP-NOISE-001",
        catalog_id="RP-CONTRACT-003",
        title="扣款机制可能过度依赖单方考核",
        dimension="合同与履约风险",
        severity=Severity.high,
        status=ReviewPointStatus.confirmed,
        rationale="测试法规引用误报。",
        evidence_bundle=EvidenceBundle(
            direct_evidence=[
                Evidence(
                    quote="一、《深圳经济特区政府采购条例》第五十七条 供应商在政府采购中，有下列行为之一的，一至三年内禁止其参与本市政府采购，并由主管部门记入供应商诚信档案。",
                    section_hint="line:20",
                )
            ],
            supporting_evidence=[],
            conflicting_evidence=[],
            rebuttal_evidence=[],
            missing_evidence_notes=[],
            clause_roles=[ClauseRole.policy_explanation],
            sufficiency_summary="证据较充分。",
            evidence_level=EvidenceLevel.strong,
            evidence_score=0.9,
        ),
        legal_basis=[
            LegalBasis(
                source_name="中华人民共和国民法典",
                article_hint="合同编公平原则",
                summary="扣款机制应当明确触发条件、计算方式和程序保障。",
            )
        ],
    )
    gates = build_review_quality_gates([point], [])
    checks = [
        ApplicabilityCheck(
            point_id="RP-NOISE-001",
            catalog_id="RP-CONTRACT-003",
            applicable=True,
            requirement_results=[],
            exclusion_results=[],
            satisfied_conditions=[],
            missing_conditions=[],
            blocking_conditions=[],
            requirement_chain_complete=True,
            summary="要件链成立。",
        )
    ]

    adjudications = build_formal_adjudication([point], checks, gates, "无关文本", [], [])

    assert gates[0].status == QualityGateStatus.filtered
    assert any("法规引用" in reason or "表格残片" in reason or "清单串接" in reason for reason in gates[0].reasons)
    assert adjudications[0].quality_gate_status == QualityGateStatus.filtered
    assert adjudications[0].included_in_formal is False
    assert adjudications[0].primary_quote == "当前自动抽取未定位到可直接引用的原文。"


def test_quality_gate_filters_policy_background_and_catalog_noise() -> None:
    policy_point = ReviewPoint(
        point_id="RP-POLICY-NOISE",
        catalog_id="RP-SME-001",
        title="政策背景说明串接",
        dimension="中小企业政策风险",
        severity=Severity.high,
        status=ReviewPointStatus.suspected,
        rationale="测试政策背景噪声。",
        evidence_bundle=EvidenceBundle(
            direct_evidence=[Evidence(quote="根据财政部文件规定，相关事项按通知执行。", section_hint="line:10")],
            supporting_evidence=[],
            conflicting_evidence=[],
            rebuttal_evidence=[],
            missing_evidence_notes=[],
            clause_roles=[ClauseRole.policy_explanation],
            sufficiency_summary="证据较充分。",
            evidence_level=EvidenceLevel.strong,
            evidence_score=0.8,
        ),
        legal_basis=[],
        source_findings=[],
    )
    catalog_point = ReviewPoint(
        point_id="RP-CATALOG-NOISE",
        catalog_id="RP-CONTRACT-003",
        title="采购人单方解释或决定条款",
        dimension="合同与履约风险",
        severity=Severity.high,
        status=ReviewPointStatus.confirmed,
        rationale="测试目录串接噪声。",
        evidence_bundle=EvidenceBundle(
            direct_evidence=[Evidence(quote="目录 第一章 招标公告 第二章 采购需求 第三章 评分办法", section_hint="line:1")],
            supporting_evidence=[],
            conflicting_evidence=[],
            rebuttal_evidence=[],
            missing_evidence_notes=[],
            clause_roles=[ClauseRole.document_definition],
            sufficiency_summary="证据较充分。",
            evidence_level=EvidenceLevel.strong,
            evidence_score=0.8,
        ),
        legal_basis=[],
        source_findings=[],
    )

    policy_gates = build_review_quality_gates([policy_point], [])
    catalog_gates = build_review_quality_gates([catalog_point], [])

    policy_checks = [
        ApplicabilityCheck(
            point_id="RP-POLICY-NOISE",
            catalog_id="RP-SME-001",
            applicable=True,
            requirement_results=[],
            exclusion_results=[],
            satisfied_conditions=[],
            missing_conditions=[],
            blocking_conditions=[],
            requirement_chain_complete=True,
            summary="要件链成立。",
        )
    ]
    catalog_checks = [
        ApplicabilityCheck(
            point_id="RP-CATALOG-NOISE",
            catalog_id="RP-CONTRACT-003",
            applicable=True,
            requirement_results=[],
            exclusion_results=[],
            satisfied_conditions=[],
            missing_conditions=[],
            blocking_conditions=[],
            requirement_chain_complete=True,
            summary="要件链成立。",
        )
    ]

    policy_formal = build_formal_adjudication([policy_point], policy_checks, policy_gates, "无关文本", [], [])
    catalog_formal = build_formal_adjudication([catalog_point], catalog_checks, catalog_gates, "目录 第一章 招标公告 第二章 采购需求 第三章 评分办法", [], [])

    assert policy_gates[0].status == QualityGateStatus.filtered
    assert any("模板" in reason or "附件" in reason or "政策" in reason for reason in policy_gates[0].reasons)
    assert policy_formal[0].quality_gate_status == QualityGateStatus.filtered
    assert policy_formal[0].included_in_formal is False

    assert catalog_gates[0].status == QualityGateStatus.filtered
    assert any("目录" in reason or "噪声" in reason for reason in catalog_gates[0].reasons)
    assert catalog_formal[0].quality_gate_status == QualityGateStatus.filtered
    assert catalog_formal[0].included_in_formal is False


def test_quality_gate_keeps_real_policy_clause_with_project_specific_terms() -> None:
    point = ReviewPoint(
        point_id="RP-POLICY-KEEP",
        catalog_id="RP-SME-002",
        title="专门面向中小企业却仍保留价格扣除",
        dimension="中小企业政策风险",
        severity=Severity.high,
        status=ReviewPointStatus.confirmed,
        rationale="保留真实政策证据。",
        evidence_bundle=EvidenceBundle(
            direct_evidence=[Evidence(quote="本项目专门面向中小企业采购，仍适用价格扣除。", section_hint="line:18")],
            supporting_evidence=[],
            conflicting_evidence=[],
            rebuttal_evidence=[],
            missing_evidence_notes=[],
            clause_roles=[ClauseRole.policy_explanation],
            sufficiency_summary="证据较充分。",
            evidence_level=EvidenceLevel.strong,
            evidence_score=0.8,
        ),
        legal_basis=[],
        source_findings=[],
    )
    clause = ExtractedClause(
        category="政策说明",
        field_name="中小企业政策说明",
        content="本项目专门面向中小企业采购，仍适用价格扣除。",
        source_anchor="line:18",
        clause_role=ClauseRole.policy_explanation,
        semantic_zone=SemanticZoneType.policy_explanation,
        effect_tags=[EffectTag.policy_background],
    )

    gates = build_review_quality_gates([point], [clause])

    assert gates[0].status == QualityGateStatus.passed
    assert any("通过质量关卡" in reason for reason in gates[0].reasons)


def test_quality_gate_filters_attachment_reference_and_template_noise() -> None:
    point = ReviewPoint(
        point_id="RP-ATTACH-NOISE",
        catalog_id="RP-CONTRACT-009",
        title="附件引用噪声",
        dimension="合同与履约风险",
        severity=Severity.high,
        status=ReviewPointStatus.confirmed,
        rationale="测试附件和模板痕迹。",
        evidence_bundle=EvidenceBundle(
            direct_evidence=[Evidence(quote="资格要求详见附件一，评分办法见附表。", section_hint="line:8")],
            supporting_evidence=[],
            conflicting_evidence=[],
            rebuttal_evidence=[],
            missing_evidence_notes=[],
            clause_roles=[ClauseRole.appendix_reference],
            sufficiency_summary="证据较充分。",
            evidence_level=EvidenceLevel.strong,
            evidence_score=0.8,
        ),
        legal_basis=[],
        source_findings=[],
    )

    gates = build_review_quality_gates([point], [])

    assert gates[0].status == QualityGateStatus.filtered
    assert any("附件" in reason or "模板" in reason or "目录" in reason for reason in gates[0].reasons)


def test_quality_gate_keeps_real_qualification_and_technical_burden_with_weak_roles() -> None:
    point = ReviewPoint(
        point_id="RP-KEEP-QUAL-TECH",
        catalog_id="RP-QUAL-009",
        title="资格和技术负担证据",
        dimension="资格与技术风险",
        severity=Severity.high,
        status=ReviewPointStatus.confirmed,
        rationale="保留真实资格和技术约束证据。",
        evidence_bundle=EvidenceBundle(
            direct_evidence=[Evidence(quote="投标人应具备独立法人资格，项目经理须驻场服务，并提供售后响应方案。", section_hint="line:15")],
            supporting_evidence=[],
            conflicting_evidence=[],
            rebuttal_evidence=[],
            missing_evidence_notes=[],
            clause_roles=[ClauseRole.document_definition],
            sufficiency_summary="证据较充分。",
            evidence_level=EvidenceLevel.strong,
            evidence_score=0.85,
        ),
        legal_basis=[],
        source_findings=[],
    )
    clause = ExtractedClause(
        category="说明文本",
        field_name="资格和技术要求",
        content="投标人应具备独立法人资格，项目经理须驻场服务，并提供售后响应方案。",
        source_anchor="line:15",
        clause_role=ClauseRole.document_definition,
        semantic_zone=SemanticZoneType.appendix_reference,
        effect_tags=[EffectTag.reference_only],
    )

    gates = build_review_quality_gates([point], [clause])
    checks = [
        ApplicabilityCheck(
            point_id="RP-KEEP-QUAL-TECH",
            catalog_id="RP-QUAL-009",
            applicable=True,
            requirement_results=[],
            exclusion_results=[],
            satisfied_conditions=[],
            missing_conditions=[],
            blocking_conditions=[],
            requirement_chain_complete=True,
            summary="要件链成立。",
        )
    ]
    formal = build_formal_adjudication([point], checks, gates, "无关文本", [clause], [])

    assert gates[0].status == QualityGateStatus.passed
    assert formal[0].quality_gate_status == QualityGateStatus.passed


def test_quality_gate_filters_template_noise_even_with_procurement_keywords() -> None:
    point = ReviewPoint(
        point_id="RP-TEMPLATE-KEYWORD-NOISE",
        catalog_id="RP-QUAL-010",
        title="资格要求模板示意",
        dimension="资格与技术风险",
        severity=Severity.high,
        status=ReviewPointStatus.confirmed,
        rationale="模板示意不应被采购关键词救回。",
        evidence_bundle=EvidenceBundle(
            direct_evidence=[
                Evidence(
                    quote="资格要求示例：投标人应具备相关资质；技术要求示例：项目经理须驻场服务。",
                    section_hint="line:6",
                )
            ],
            supporting_evidence=[],
            conflicting_evidence=[],
            rebuttal_evidence=[],
            missing_evidence_notes=[],
            clause_roles=[ClauseRole.form_template],
            sufficiency_summary="证据较充分。",
            evidence_level=EvidenceLevel.strong,
            evidence_score=0.8,
        ),
        legal_basis=[],
        source_findings=[],
    )
    clause = ExtractedClause(
        category="模板",
        field_name="资格要求",
        content="资格要求示例：投标人应具备相关资质；技术要求示例：项目经理须驻场服务。",
        source_anchor="line:6",
        clause_role=ClauseRole.form_template,
        semantic_zone=SemanticZoneType.template,
        effect_tags=[EffectTag.template, EffectTag.example],
    )
    gates = build_review_quality_gates([point], [clause])
    checks = [
        ApplicabilityCheck(
            point_id="RP-TEMPLATE-KEYWORD-NOISE",
            catalog_id="RP-QUAL-010",
            applicable=True,
            requirement_results=[],
            exclusion_results=[],
            satisfied_conditions=[],
            missing_conditions=[],
            blocking_conditions=[],
            requirement_chain_complete=True,
            summary="要件链成立。",
        )
    ]
    formal = build_formal_adjudication([point], checks, gates, "资格要求示例：投标人应具备相关资质；技术要求示例：项目经理须驻场服务。", [clause], [])

    assert gates[0].status == QualityGateStatus.filtered
    assert any("模板" in reason or "弱来源" in reason for reason in gates[0].reasons)
    assert formal[0].quality_gate_status == QualityGateStatus.filtered
    assert formal[0].included_in_formal is False


def test_formal_adjudication_keeps_real_scoring_row_evidence() -> None:
    point = ReviewPoint(
        point_id="RP-SCORE-KEEP",
        catalog_id="RP-SCORE-008",
        title="证书检测报告及财务指标权重合理性复核",
        dimension="B.评分不规范风险",
        severity=Severity.high,
        status=ReviewPointStatus.confirmed,
        rationale="已识别证书类评分负担。",
        evidence_bundle=EvidenceBundle(
            direct_evidence=[Evidence(quote="软件企业认定证书 / ITSS", section_hint="line:1")],
            supporting_evidence=[],
            conflicting_evidence=[],
            rebuttal_evidence=[],
            missing_evidence_notes=[],
            sufficiency_summary="证据较充分。",
            clause_roles=[],
            evidence_level=EvidenceLevel.strong,
            evidence_score=0.9,
        ),
        legal_basis=[
            LegalBasis(
                source_name="政府采购需求管理办法",
                article_hint="相关条款",
                summary="评分因素应与项目实际需要相适应。",
            )
        ],
    )
    checks = [
        ApplicabilityCheck(
            point_id="RP-SCORE-KEEP",
            catalog_id="RP-SCORE-008",
            applicable=True,
            requirement_results=[],
            exclusion_results=[],
            satisfied_conditions=["存在证书报告或财务指标评分信号"],
            missing_conditions=[],
            blocking_conditions=[],
            requirement_chain_complete=True,
            summary="要件链成立。",
        )
    ]
    gates = [build_review_quality_gates([point], [])[0]]
    tables = [
        ParsedTable(
            table_index=1,
            row_count=1,
            rows=[["履约能力", "投标人具有行政单位颁发的软件企业认定证书（5分）"]],
            source="ocr_table",
        )
    ]

    adjudications = build_formal_adjudication([point], checks, gates, "评审项编号 一级评审项 二级评审项 详细要求 分值 6 详细评审 履约能力 投标人具有行政单位颁发的软件企业认定证书（5分）。", [], tables)

    assert gates[0].status == QualityGateStatus.passed
    assert adjudications[0].included_in_formal is True
    assert "详细评审 履约能力" in adjudications[0].primary_quote
    assert "软件企业认定证书（5分）" in adjudications[0].primary_quote
    assert "ITSS证书（2分）" in adjudications[0].primary_quote

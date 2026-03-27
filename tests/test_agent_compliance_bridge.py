from agent_review.agent_compliance_bridge import (
    build_agent_compliance_normalized_document,
    run_agent_compliance_review_from_parsed_tender_document,
)
from agent_review.embedded_compliance_engine import EmbeddedLLMConfig
from agent_review.models import (
    ClauseUnit,
    ParsedTenderDocument,
    ParsedTenderSection,
    SourceAnchor,
)
from agent_review.ontology import ClauseSemanticType, EffectTag, LegalEffectType, SemanticZoneType


class _FakeLLMClient:
    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        del system_prompt
        del user_prompt
        return """
        [
          {
            "clause_id": "u-6",
            "issue_type": "evidence_source_restriction",
            "problem_title": "指定单一检测机构出具报告",
            "why_it_is_risky": "条款要求由单一检测机构出具检测报告，可能形成证明来源限制。",
            "rewrite_suggestion": "改为接受具备资质的同类检测机构出具的等效报告。",
            "needs_human_review": false,
            "human_review_reason": ""
          }
        ]
        """


def _build_demo_parsed_tender_document() -> ParsedTenderDocument:
    anchor1 = SourceAnchor(source_path="/tmp/demo.docx", page_no=1, paragraph_no=1, line_hint="line:1")
    anchor2 = SourceAnchor(source_path="/tmp/demo.docx", page_no=1, paragraph_no=2, line_hint="line:2")
    anchor3 = SourceAnchor(source_path="/tmp/demo.docx", page_no=1, paragraph_no=3, line_hint="line:3")
    units = [
        ClauseUnit(
            unit_id="u-1",
            source_node_id="n-1",
            text="项目名称：智慧校园设备采购",
            path="第一章 招标公告 > 项目概况",
            anchor=anchor1,
            zone_type=SemanticZoneType.administrative_info,
            clause_semantic_type=ClauseSemanticType.administrative_clause,
            effect_tags=[EffectTag.binding],
            confidence=0.92,
        ),
        ClauseUnit(
            unit_id="u-2",
            source_node_id="n-2",
            text="投标人须具备高新技术企业证书。",
            path="第三章 资格要求 > 供应商资格条件",
            anchor=anchor2,
            zone_type=SemanticZoneType.qualification,
            clause_semantic_type=ClauseSemanticType.qualification_condition,
            effect_tags=[EffectTag.binding],
            confidence=0.94,
            legal_effect_type=LegalEffectType.qualification_gate,
        ),
        ClauseUnit(
            unit_id="u-3",
            source_node_id="n-3",
            text="评分项：高新技术企业证书，提供得5分。",
            path="第四章 评标信息 > 评分标准",
            anchor=anchor3,
            zone_type=SemanticZoneType.scoring,
            clause_semantic_type=ClauseSemanticType.scoring_rule,
            effect_tags=[EffectTag.binding],
            confidence=0.9,
            legal_effect_type=LegalEffectType.scoring_factor,
        ),
    ]
    sections = [
        ParsedTenderSection(
            section_id="section-1",
            node_id="n-1",
            title="项目概况",
            path="第一章 招标公告 > 项目概况",
            node_type="paragraph",
            zone_type=SemanticZoneType.administrative_info.value,
            effect_tags=[EffectTag.binding.value],
            anchor=anchor1,
            text_preview="项目名称：智慧校园设备采购",
        )
    ]
    return ParsedTenderDocument(
        document_id="demo.docx",
        source_path="/tmp/demo.docx",
        document_name="demo.docx",
        document_type="docx",
        parser_name="docx",
        source_format="docx",
        normalized_text="\n".join(unit.text for unit in units),
        page_count=1,
        sections=sections,
        clause_units=units,
    )


def _build_extended_parsed_tender_document() -> ParsedTenderDocument:
    base = _build_demo_parsed_tender_document()
    extra_anchor = SourceAnchor(source_path="/tmp/demo.docx", page_no=1, paragraph_no=4, line_hint="line:4")
    base.clause_units.extend(
        [
            ClauseUnit(
                unit_id="u-4",
                source_node_id="n-4",
                text="投标人须提供深圳市医疗器械检测中心出具的产品检测报告。",
                path="第五章 技术要求 > 检测要求",
                anchor=extra_anchor,
                zone_type=SemanticZoneType.technical,
                clause_semantic_type=ClauseSemanticType.technical_requirement,
                effect_tags=[EffectTag.binding],
                confidence=0.91,
                legal_effect_type=LegalEffectType.evidence_source_requirement,
            ),
            ClauseUnit(
                unit_id="u-5",
                source_node_id="n-5",
                text="投标报价不得低于预算金额的80%，低于此价格的投标将被视为无效投标。",
                path="第六章 商务要求 > 报价要求",
                anchor=SourceAnchor(source_path="/tmp/demo.docx", page_no=1, paragraph_no=5, line_hint="line:5"),
                zone_type=SemanticZoneType.business,
                clause_semantic_type=ClauseSemanticType.business_requirement,
                effect_tags=[EffectTag.binding],
                confidence=0.9,
                legal_effect_type=LegalEffectType.business_requirement,
            ),
            ClauseUnit(
                unit_id="u-6",
                source_node_id="n-6",
                text="供应商须提供指定机构出具的检测报告。",
                path="第五章 技术要求 > 检测要求补充说明",
                anchor=SourceAnchor(source_path="/tmp/demo.docx", page_no=1, paragraph_no=6, line_hint="line:6"),
                zone_type=SemanticZoneType.technical,
                clause_semantic_type=ClauseSemanticType.technical_requirement,
                effect_tags=[EffectTag.binding],
                confidence=0.82,
                legal_effect_type=LegalEffectType.evidence_source_requirement,
            ),
        ]
    )
    base.normalized_text = "\n".join(unit.text for unit in base.clause_units)
    return base


def test_build_agent_compliance_normalized_document_from_parsed_tender_document() -> None:
    parsed = _build_demo_parsed_tender_document()

    normalized, artifacts = build_agent_compliance_normalized_document(parsed)

    assert normalized.document_name == "demo.docx"
    assert normalized.clause_count == 3
    assert artifacts.clause_source == "clause_units"
    assert normalized.clauses[1].document_structure_type == "qualification_review"
    assert normalized.clauses[1].risk_scope == "core_risk_scope"
    assert normalized.clauses[1].clause_function == "qualification_gate"
    assert normalized.clauses[2].document_structure_type == "scoring_rules"


def test_run_agent_compliance_review_from_parsed_tender_document() -> None:
    parsed = _build_demo_parsed_tender_document()

    result = run_agent_compliance_review_from_parsed_tender_document(
        parsed,
        write_outputs=False,
    )

    assert result.normalized.document_name == "demo.docx"
    assert result.parser_mode in {"assist", "off", "required"}
    assert result.llm_artifacts.llm_node_summary is not None
    bridge = result.llm_artifacts.llm_node_summary.get("bridge", {})
    assert bridge.get("clause_source") == "clause_units"


def test_embedded_rule_set_covers_extended_high_frequency_risks() -> None:
    parsed = _build_extended_parsed_tender_document()

    result = run_agent_compliance_review_from_parsed_tender_document(parsed, write_outputs=False)
    issue_types = {item.issue_type for item in result.review.findings}

    assert "irrelevant_certification_or_award" in issue_types
    assert "evidence_source_restriction" in issue_types
    assert "bid_price_floor" in issue_types


def test_embedded_llm_review_can_add_findings_without_external_repo_dependency() -> None:
    parsed = _build_extended_parsed_tender_document()

    result = run_agent_compliance_review_from_parsed_tender_document(
        parsed,
        llm_config=EmbeddedLLMConfig(
            enabled=True,
            base_url="http://local.test/v1",
            model="fake-qwen",
            api_key="test",
            timeout_seconds=30,
        ),
        llm_client=_FakeLLMClient(),
        write_outputs=False,
    )

    assert result.llm_artifacts.llm_node_summary is not None
    assert result.llm_artifacts.llm_node_summary.get("status") == "ok"
    assert any(item.issue_type == "evidence_source_restriction" for item in result.llm_artifacts.added_findings)
    assert any(item.problem_title == "指定单一检测机构出具报告" for item in result.review.findings)

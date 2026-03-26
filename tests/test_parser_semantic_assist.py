from agent_review.engine import TenderReviewEngine
from agent_review.models import (
    ClauseUnit,
    DocumentNode,
    DocumentProfile,
    EffectTagResult,
    ParseResult,
    ParserSemanticTrace,
    SemanticZone,
    SourceAnchor,
)
from agent_review.ontology import ClauseSemanticType, EffectTag, NodeType, SemanticZoneType
from agent_review.structure.parser_semantic_assist import QwenParserSemanticAssistant


class _FakeParserClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        return self.response


def _build_ambiguous_parse_result() -> ParseResult:
    anchor = SourceAnchor(source_path="demo.txt", block_no=1, line_hint="line:1")
    node = DocumentNode(
        node_id="n-1",
        node_type=NodeType.paragraph,
        title="投标人须具备相关资质。",
        text="投标人须具备相关资质。",
        path="第一章 招标公告 > 投标人资格要求",
        anchor=anchor,
    )
    return ParseResult(
        parser_name="text",
        source_path="demo.txt",
        source_format="txt",
        page_count=1,
        text="投标人须具备相关资质。",
        document_nodes=[node],
        semantic_zones=[
            SemanticZone(
                node_id="n-1",
                zone_type=SemanticZoneType.mixed_or_uncertain,
                confidence=0.42,
                classification_basis=["rule_conflict"],
            )
        ],
        effect_tag_results=[
            EffectTagResult(
                node_id="n-1",
                effect_tags=[EffectTag.uncertain_effect],
                confidence=0.41,
                evidence=["low_rule_support"],
            )
        ],
        clause_units=[
            ClauseUnit(
                unit_id="cu-0001",
                source_node_id="n-1",
                text="投标人须具备相关资质。",
                path="第一章 招标公告 > 投标人资格要求",
                anchor=anchor,
                zone_type=SemanticZoneType.mixed_or_uncertain,
                clause_semantic_type=ClauseSemanticType.unknown_clause,
                effect_tags=[EffectTag.uncertain_effect],
                confidence=0.46,
            )
        ],
    )


def test_qwen_parser_semantic_assistant_only_adjusts_low_confidence_candidates() -> None:
    parse_result = _build_ambiguous_parse_result()
    profile = DocumentProfile(
        document_id="demo.txt",
        source_path="demo.txt",
        procurement_kind="unknown",
        procurement_kind_confidence=0.31,
        unknown_structure_flags=["unknown_procurement_kind", "mixed_zone_dense"],
    )
    client = _FakeParserClient(
        """
        {
          "resolutions": [
            {
              "node_id": "n-1",
              "zone_type": "qualification",
              "clause_semantic_type": "qualification_condition",
              "effect_tags": ["binding"],
              "confidence": 0.92,
              "reason": "该句属于资格要求正文"
            }
          ]
        }
        """
    )

    assisted_result, trace = QwenParserSemanticAssistant(client=client).assist(parse_result, profile)

    zone = assisted_result.semantic_zones[0]
    effect = assisted_result.effect_tag_results[0]
    unit = assisted_result.clause_units[0]
    assert client.calls == 1
    assert trace.activated is True
    assert trace.applied_count == 1
    assert zone.zone_type == SemanticZoneType.qualification
    assert unit.clause_semantic_type == ClauseSemanticType.qualification_condition
    assert unit.effect_tags == [EffectTag.binding]
    assert effect.effect_tags == [EffectTag.binding]


def test_qwen_parser_semantic_assistant_skips_confident_documents() -> None:
    parse_result = _build_ambiguous_parse_result()
    parse_result.semantic_zones[0].zone_type = SemanticZoneType.qualification
    parse_result.semantic_zones[0].confidence = 0.95
    parse_result.effect_tag_results[0].effect_tags = [EffectTag.binding]
    parse_result.effect_tag_results[0].confidence = 0.94
    parse_result.clause_units[0].zone_type = SemanticZoneType.qualification
    parse_result.clause_units[0].clause_semantic_type = ClauseSemanticType.qualification_condition
    parse_result.clause_units[0].effect_tags = [EffectTag.binding]
    parse_result.clause_units[0].confidence = 0.93
    profile = DocumentProfile(
        document_id="demo.txt",
        source_path="demo.txt",
        procurement_kind="goods",
        procurement_kind_confidence=0.88,
    )
    client = _FakeParserClient('{"resolutions": []}')

    _, trace = QwenParserSemanticAssistant(client=client).assist(parse_result, profile)

    assert client.calls == 0
    assert trace.activated is False
    assert trace.candidate_count == 0


class _FakeParserSemanticAssistant:
    def assist(self, parse_result: ParseResult, document_profile: DocumentProfile | None):
        parse_result.parser_semantic_trace = ParserSemanticTrace(
            activated=True,
            activation_reasons=["unknown_procurement_kind"],
            candidate_count=2,
            reviewed_count=2,
            applied_count=1,
        )
        return parse_result, parse_result.parser_semantic_trace


def test_engine_records_parser_semantic_assist_stage() -> None:
    report = TenderReviewEngine(
        parser_semantic_assistant=_FakeParserSemanticAssistant(),
    ).review_text("项目概况\n采购需求详见附件。", document_name="demo.txt")

    assist_stage = next(item for item in report.stage_records if item.stage_name == "parser_semantic_assist")
    assert report.parse_result.parser_semantic_trace is not None
    assert report.parse_result.parser_semantic_trace.activated is True
    assert assist_stage.item_count == 1
    assert "unknown_procurement_kind" in assist_stage.detail

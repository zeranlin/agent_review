from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from .adjudication import (
    build_formal_adjudication,
    build_point_applicability_checks,
    build_point_quality_gates,
    build_review_point_catalog_snapshot,
    build_review_points_from_instances,
    build_review_points_from_task_library,
    build_review_points_from_consistency_checks,
    build_review_points_from_findings,
    build_review_points_from_risk_hits,
    convert_review_points_to_findings,
    merge_review_points,
)
from .domain_profiles import profile_activation_tags
from .external_data import external_profile_planning_hints
from .checklist import DEFAULT_DIMENSIONS
from .consistency import (
    check_consistency,
    collect_relative_strengths,
)
from .extractors import classify_extracted_clauses, extract_clauses, extract_clauses_from_units
from .extractors import extract_legal_facts_from_units
from .legal_basis import annotate_consistency_checks, annotate_findings, annotate_review_points, annotate_risk_hits
from .merge import (
    build_specialist_tables,
    dedupe_findings,
    dedupe_recommendations,
    dedupe_risk_hits,
    dedupe_strings,
)
from .models import (
    AdoptionStatus,
    ApplicabilityCheck,
    ConclusionLevel,
    Evidence,
    FileInfo,
    Finding,
    FindingType,
    DocumentProfile,
    ParseResult,
    ParsedPage,
    Recommendation,
    ReviewPlanningContract,
    ReviewDimension,
    ReviewMode,
    ReviewReport,
    ReviewPoint,
    ReviewWorkItem,
    ReviewQualityGate,
    RuleSelection,
    RunStageRecord,
    SectionIndex,
    Severity,
    SourceDocument,
    TaskRecord,
    TaskStatus,
)
from .ontology import SemanticZoneType, ZONE_PRIMARY_REVIEW_TYPES
from .parsed_tender_document import build_parsed_tender_document
from .quality import derive_conclusion_by_evidence
from .rules import build_recommendations, execute_rule_registry
from .review_point_catalog import resolve_review_point_definition
from .review_point_contract_registry import get_review_point_contract
from .rule_definitions import list_rules_for_point
from .rule_runtime import build_review_point_instances, generate_rule_hits
from .structure import (
    NullParserSemanticAssistant,
    build_file_info,
    build_document_profile,
    build_scope_statement,
    detect_file_type,
    enrich_parse_result_structure,
    locate_sections,
)


@dataclass(slots=True)
class ReviewPipelineState:
    document_name: str
    parse_result: ParseResult
    normalized_text: str
    source_documents: list[SourceDocument] = field(default_factory=list)
    file_info: FileInfo | None = None
    document_profile: DocumentProfile | None = None
    scope_statement: str = ""
    section_index: list[SectionIndex] = field(default_factory=list)
    legal_fact_candidates: list = field(default_factory=list)
    rule_hits: list = field(default_factory=list)
    review_point_instances: list = field(default_factory=list)
    extracted_clauses: list = field(default_factory=list)
    risk_hits: list = field(default_factory=list)
    consistency_checks: list = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    relative_strengths: list[str] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    manual_review_queue: list[str] = field(default_factory=list)
    reviewed_dimensions: list[str] = field(default_factory=list)
    review_points: list = field(default_factory=list)
    review_point_catalog: list = field(default_factory=list)
    review_planning_contract: ReviewPlanningContract | None = None
    applicability_checks: list[ApplicabilityCheck] = field(default_factory=list)
    quality_gates: list[ReviewQualityGate] = field(default_factory=list)
    formal_adjudication: list = field(default_factory=list)
    specialist_tables: object | None = None
    rule_selection: RuleSelection = field(default_factory=RuleSelection)
    overall_conclusion: ConclusionLevel | None = None
    summary: str = ""
    stage_records: list[RunStageRecord] = field(default_factory=list)


class ReviewPipeline:
    STAGE_BOUNDARIES: dict[str, dict[str, object]] = {
        "document_structure": {"stage_layer": "parser", "primary_object": "DocumentNode/SectionIndex", "owned_by": "parser", "is_mainline": True},
        "document_profiling": {"stage_layer": "planning", "primary_object": "DocumentProfile", "owned_by": "planning", "is_mainline": True},
        "parser_semantic_assist": {"stage_layer": "parser", "primary_object": "ClauseUnit/Zone", "owned_by": "parser", "is_mainline": False},
        "legal_fact_extraction": {"stage_layer": "fact", "primary_object": "LegalFactCandidate", "owned_by": "fact", "is_mainline": True},
        "rule_hit_generation": {"stage_layer": "rule", "primary_object": "RuleHit", "owned_by": "rule", "is_mainline": True},
        "review_point_instance_assembly": {"stage_layer": "rule", "primary_object": "ReviewPointInstance", "owned_by": "rule", "is_mainline": True},
        "clause_extraction": {"stage_layer": "fact", "primary_object": "ExtractedClause", "owned_by": "fact", "is_mainline": True},
        "clause_role_classification": {"stage_layer": "fact", "primary_object": "ExtractedClause", "owned_by": "fact", "is_mainline": False},
        "review_task_planning": {"stage_layer": "planning", "primary_object": "ReviewPlanningContract", "owned_by": "planning", "is_mainline": True},
        "planning_guided_extraction": {"stage_layer": "planning", "primary_object": "ExtractedClause", "owned_by": "planning", "is_mainline": True},
        "dimension_review": {"stage_layer": "legacy", "primary_object": "ReviewPoint", "owned_by": "legacy_fallback", "is_mainline": False},
        "rule_evaluation": {"stage_layer": "legacy", "primary_object": "RiskHit", "owned_by": "legacy_fallback", "is_mainline": False},
        "consistency_review": {"stage_layer": "legacy", "primary_object": "ConsistencyCheck", "owned_by": "legacy_fallback", "is_mainline": False},
        "review_point_assembly": {"stage_layer": "adjudication", "primary_object": "ReviewPoint", "owned_by": "adjudication", "is_mainline": True},
        "applicability_check": {"stage_layer": "adjudication", "primary_object": "ApplicabilityCheck", "owned_by": "adjudication", "is_mainline": True},
        "review_quality_gate": {"stage_layer": "adjudication", "primary_object": "ReviewQualityGate", "owned_by": "adjudication", "is_mainline": True},
        "formal_adjudication": {"stage_layer": "adjudication", "primary_object": "FormalAdjudication", "owned_by": "adjudication", "is_mainline": True},
        "finalize_report": {"stage_layer": "output", "primary_object": "ReviewReport", "owned_by": "output", "is_mainline": True},
        "llm_semantic_review": {"stage_layer": "llm", "primary_object": "LLMSemanticReview", "owned_by": "llm_enhancement", "is_mainline": False},
    }

    def __init__(
        self,
        dimensions: list[ReviewDimension] | None = None,
        parser_semantic_assistant: object | None = None,
    ) -> None:
        self.dimensions = dimensions or DEFAULT_DIMENSIONS
        self.parser_semantic_assistant = parser_semantic_assistant or NullParserSemanticAssistant()
        self.stages = (
            self._stage_document_structure,
            self._stage_document_profiling,
            self._stage_parser_semantic_assist,
            self._stage_legal_fact_extraction,
            self._stage_rule_hit_generation,
            self._stage_review_point_instance_assembly,
            self._stage_clause_extraction,
            self._stage_clause_role_classification,
            self._stage_review_task_planning,
            self._stage_planning_guided_extraction,
            self._stage_dimension_review,
            self._stage_rule_evaluation,
            self._stage_consistency_review,
            self._stage_review_point_assembly,
            self._stage_applicability_check,
            self._stage_review_quality_gate,
            self._stage_formal_adjudication,
            self._stage_finalize_report,
        )

    def run(
        self,
        parse_result: ParseResult,
        document_name: str,
        review_mode: ReviewMode,
        source_documents: list[SourceDocument] | None = None,
    ) -> ReviewReport:
        state = ReviewPipelineState(
            document_name=document_name,
            parse_result=parse_result,
            normalized_text=parse_result.text,
            source_documents=source_documents or [],
        )
        for stage in self.stages:
            stage(state)
        state.stage_records = [self._enrich_stage_record(item) for item in state.stage_records]

        return ReviewReport(
            review_mode=review_mode,
            parse_result=state.parse_result,
            file_info=state.file_info,
            scope_statement=state.scope_statement,
            overall_conclusion=state.overall_conclusion,
            summary=state.summary,
            llm_enhanced=False,
            llm_warnings=[],
            findings=state.findings,
            relative_strengths=state.relative_strengths,
            section_index=state.section_index,
            extracted_clauses=state.extracted_clauses,
            risk_hits=state.risk_hits,
            specialist_tables=state.specialist_tables,
            consistency_checks=state.consistency_checks,
            recommendations=state.recommendations,
            manual_review_queue=state.manual_review_queue,
            reviewed_dimensions=state.reviewed_dimensions,
            source_documents=state.source_documents,
            review_points=state.review_points,
            review_point_catalog=state.review_point_catalog,
            review_planning_contract=state.review_planning_contract,
            applicability_checks=state.applicability_checks,
            quality_gates=state.quality_gates,
            formal_adjudication=state.formal_adjudication,
            high_risk_review_items=_build_high_risk_review_items(state.findings),
            pending_confirmation_items=_build_pending_confirmation_items(
                state.findings,
                state.extracted_clauses,
                state.manual_review_queue,
            ),
            stage_records=state.stage_records,
            task_records=[
                TaskRecord(
                    task_name=item.stage_name,
                    status=TaskStatus.completed if item.status == "completed" else TaskStatus.failed,
                    detail=item.detail,
                    item_count=item.item_count,
                    stage_layer=item.stage_layer,
                    primary_object=item.primary_object,
                    owned_by=item.owned_by,
                    is_mainline=item.is_mainline,
                )
                for item in state.stage_records
            ],
            rule_selection=state.rule_selection,
        )

    def _enrich_stage_record(self, record: RunStageRecord) -> RunStageRecord:
        metadata = self.STAGE_BOUNDARIES.get(record.stage_name, {})
        return replace(
            record,
            stage_layer=str(metadata.get("stage_layer", record.stage_layer)),
            primary_object=str(metadata.get("primary_object", record.primary_object)),
            owned_by=str(metadata.get("owned_by", record.owned_by)),
            is_mainline=bool(metadata.get("is_mainline", record.is_mainline)),
        )

    def _stage_document_structure(self, state: ReviewPipelineState) -> None:
        state.parse_result = enrich_parse_result_structure(state.parse_result)
        state.parse_result.parsed_tender_document = build_parsed_tender_document(
            state.parse_result,
            document_name=state.document_name,
        )
        file_type = detect_file_type(state.normalized_text)
        state.file_info = build_file_info(state.document_name, state.normalized_text, file_type)
        state.scope_statement = build_scope_statement(state.file_info)
        state.section_index = locate_sections(state.normalized_text)
        state.stage_records.append(
            RunStageRecord(
                stage_name="document_structure",
                status="completed",
                item_count=len(state.section_index),
                detail=f"识别文件类型并定位 {len(state.section_index)} 个章节锚点。",
            )
        )

    def _stage_document_profiling(self, state: ReviewPipelineState) -> None:
        state.document_profile = build_document_profile(state.parse_result, state.document_name)
        state.parse_result.document_profile = state.document_profile
        state.parse_result.parsed_tender_document = build_parsed_tender_document(
            state.parse_result,
            document_name=state.document_name,
        )
        candidate_count = len(state.document_profile.domain_profile_candidates)
        state.stage_records.append(
            RunStageRecord(
                stage_name="document_profiling",
                status="completed",
                item_count=candidate_count,
                detail=(
                    f"完成文档画像，识别 {state.document_profile.procurement_kind} 倾向，"
                    f"形成 {candidate_count} 个领域候选，"
                    f"当前路由模式为 {state.document_profile.routing_mode}。"
                ),
            )
        )

    def _stage_parser_semantic_assist(self, state: ReviewPipelineState) -> None:
        parse_result, trace = self.parser_semantic_assistant.assist(state.parse_result, state.document_profile)
        state.parse_result = parse_result
        state.parse_result.parser_semantic_trace = trace
        if trace.warnings:
            state.parse_result.warnings.extend(
                item for item in trace.warnings if item not in state.parse_result.warnings
            )
        if trace.applied_count > 0:
            state.document_profile = build_document_profile(state.parse_result, state.document_name)
            state.parse_result.document_profile = state.document_profile
        state.parse_result.parsed_tender_document = build_parsed_tender_document(
            state.parse_result,
            document_name=state.document_name,
        )
        detail = (
            "parser 语义补偿未激活，继续沿用规则主链结果。"
            if not trace.activated
            else (
                f"parser 语义补偿已审查 {trace.reviewed_count} 个低置信度节点，"
                f"应用 {trace.applied_count} 处标签修正。"
            )
        )
        if trace.activation_reasons:
            detail += f" 触发原因：{','.join(trace.activation_reasons[:3])}。"
        state.stage_records.append(
            RunStageRecord(
                stage_name="parser_semantic_assist",
                status="completed",
                item_count=trace.applied_count,
                detail=detail,
            )
        )

    def _stage_clause_extraction(self, state: ReviewPipelineState) -> None:
        if state.parse_result.clause_units:
            unit_clauses = extract_clauses_from_units(state.parse_result.clause_units)
            fallback_clauses = extract_clauses(state.normalized_text)
            state.extracted_clauses = _merge_extracted_clauses(unit_clauses, fallback_clauses)
        else:
            state.extracted_clauses = extract_clauses(state.normalized_text)
        state.stage_records.append(
            RunStageRecord(
                stage_name="clause_extraction",
                status="completed",
                item_count=len(state.extracted_clauses),
                detail=(
                    f"抽取 {len(state.extracted_clauses)} 条结构化条款。"
                    + (
                        "当前优先基于 ClauseUnit 抽取，并由全文抽取补位。"
                        if state.parse_result.clause_units
                        else "当前基于全文回退抽取。"
                    )
                ),
            )
        )

    def _stage_legal_fact_extraction(self, state: ReviewPipelineState) -> None:
        if state.parse_result.clause_units:
            state.legal_fact_candidates = extract_legal_facts_from_units(
                state.parse_result.clause_units,
                document_id=state.document_name,
                raw_text=state.parse_result.text,
            )
        else:
            state.legal_fact_candidates = extract_legal_facts_from_units(
                [],
                document_id=state.document_name,
                raw_text=state.parse_result.text,
            )
        state.parse_result.legal_fact_candidates = state.legal_fact_candidates
        fact_types = _ordered_unique(item.fact_type for item in state.legal_fact_candidates)
        preview = ",".join(fact_types[:4])
        state.stage_records.append(
            RunStageRecord(
                stage_name="legal_fact_extraction",
                status="completed",
                item_count=len(state.legal_fact_candidates),
                detail=(
                    f"基于 ClauseUnit 抽取 {len(state.legal_fact_candidates)} 条 LegalFactCandidate。"
                    + (f" 事实类型：{preview}。" if preview else "")
                ),
            )
        )

    def _stage_rule_hit_generation(self, state: ReviewPipelineState) -> None:
        state.rule_hits = generate_rule_hits(state.legal_fact_candidates)
        state.parse_result.rule_hits = state.rule_hits
        preview = ",".join(_ordered_unique(item.rule_id for item in state.rule_hits)[:4])
        state.stage_records.append(
            RunStageRecord(
                stage_name="rule_hit_generation",
                status="completed",
                item_count=len(state.rule_hits),
                detail=(
                    f"基于 LegalFactCandidate 生成 {len(state.rule_hits)} 条 RuleHit。"
                    + (f" 命中规则：{preview}。" if preview else "")
                ),
            )
        )

    def _stage_review_point_instance_assembly(self, state: ReviewPipelineState) -> None:
        state.review_point_instances = build_review_point_instances(state.rule_hits)
        state.parse_result.review_point_instances = state.review_point_instances
        preview = ",".join(_ordered_unique(item.point_id for item in state.review_point_instances)[:4])
        state.stage_records.append(
            RunStageRecord(
                stage_name="review_point_instance_assembly",
                status="completed",
                item_count=len(state.review_point_instances),
                detail=(
                    f"由 RuleHit 聚合出 {len(state.review_point_instances)} 个 ReviewPointInstance。"
                    + (f" 聚合点位：{preview}。" if preview else "")
                ),
            )
        )

    def _stage_clause_role_classification(self, state: ReviewPipelineState) -> None:
        state.extracted_clauses = classify_extracted_clauses(state.extracted_clauses)
        identified_count = sum(1 for item in state.extracted_clauses if item.clause_role.value != "未识别")
        state.stage_records.append(
            RunStageRecord(
                stage_name="clause_role_classification",
                status="completed",
                item_count=identified_count,
                detail=f"完成条款角色识别，{identified_count} 条条款已获得角色标签。",
            )
        )

    def _stage_review_task_planning(self, state: ReviewPipelineState) -> None:
        planned_points = build_review_points_from_task_library(
            state.normalized_text,
            state.extracted_clauses,
            document_profile=state.document_profile,
            review_point_instances=state.review_point_instances,
        )
        state.review_points.extend(planned_points)
        state.review_planning_contract = _build_review_planning_contract(
            state.document_profile,
            planned_points,
            state.legal_fact_candidates,
            state.review_point_instances,
        )
        profile_summary = state.document_profile.procurement_kind if state.document_profile else "unknown"
        activation_hint_summary = ",".join(state.document_profile.risk_activation_hints[:3]) if state.document_profile else ""
        demand_count = len(state.review_planning_contract.extraction_demands) if state.review_planning_contract else 0
        base_count = len(state.review_planning_contract.base_extraction_demands) if state.review_planning_contract else 0
        required_count = len(state.review_planning_contract.required_task_extraction_demands) if state.review_planning_contract else 0
        optional_count = len(state.review_planning_contract.optional_enhancement_extraction_demands) if state.review_planning_contract else 0
        enhancement_count = len(state.review_planning_contract.enhancement_extraction_demands) if state.review_planning_contract else 0
        fallback_count = len(state.review_planning_contract.unknown_fallback_extraction_demands) if state.review_planning_contract else 0
        activated_family_count = len(state.review_planning_contract.activated_risk_families) if state.review_planning_contract else 0
        suppressed_family_count = len(state.review_planning_contract.suppressed_risk_families) if state.review_planning_contract else 0
        state.stage_records.append(
            RunStageRecord(
                stage_name="review_task_planning",
                status="completed",
                item_count=len(planned_points),
                detail=(
                    f"已基于 {profile_summary} 画像与 activation hints 规划 {len(planned_points)} 个待执行审查点，"
                    f"形成 {demand_count} 项抽取需求。"
                    f" 激活母题 {activated_family_count} 个，抑制母题 {suppressed_family_count} 个。"
                    f" 需求分层：基础必抽 {base_count}、任务必需 {required_count}、可选增强 {optional_count}、unknown fallback {fallback_count}。"
                    f" 任务增强合计 {enhancement_count}。"
                    + (f" 关键提示：{activation_hint_summary}。" if activation_hint_summary else "")
                ),
            )
        )

    def _stage_planning_guided_extraction(self, state: ReviewPipelineState) -> None:
        target_fields = set(state.review_planning_contract.extraction_demands) if state.review_planning_contract else set()
        if not target_fields:
            state.stage_records.append(
                RunStageRecord(
                    stage_name="planning_guided_extraction",
                    status="completed",
                    item_count=0,
                    detail="当前 review planning 未生成额外 extraction demand，保持现有抽取结果。",
                )
            )
            return

        before_count = len(state.extracted_clauses)
        target_zones = set(state.review_planning_contract.target_zones) if state.review_planning_contract else set()
        if state.parse_result.clause_units:
            unit_targeted = extract_clauses_from_units(
                state.parse_result.clause_units,
                field_names=target_fields,
                target_zones=target_zones or None,
            )
            matched_unit_fields = {item.field_name for item in unit_targeted if item.field_name}
            missing_fields = target_fields - matched_unit_fields
            text_targeted = extract_clauses(
                state.normalized_text,
                field_names=missing_fields or set(),
            ) if missing_fields else []
            targeted = _merge_extracted_clauses(unit_targeted, text_targeted)
        else:
            targeted = extract_clauses(
                state.normalized_text,
                field_names=target_fields,
            )
            unit_targeted = []
            text_targeted = targeted
        state.extracted_clauses = classify_extracted_clauses(
            _merge_extracted_clauses(state.extracted_clauses, targeted)
        )
        added_count = len(state.extracted_clauses) - before_count
        matched_fields = _ordered_unique(item.field_name for item in targeted if item.field_name)
        if state.review_planning_contract:
            state.review_planning_contract.matched_extraction_fields = matched_fields
            state.review_planning_contract.base_hit_fields = _ordered_unique(
                field for field in matched_fields if field in state.review_planning_contract.base_extraction_demands
            )
            state.review_planning_contract.required_hit_fields = _ordered_unique(
                field for field in matched_fields if field in state.review_planning_contract.required_task_extraction_demands
            )
            state.review_planning_contract.optional_hit_fields = _ordered_unique(
                field for field in matched_fields if field in state.review_planning_contract.optional_enhancement_extraction_demands
            )
            state.review_planning_contract.unknown_fallback_hit_fields = _ordered_unique(
                field for field in matched_fields if field in state.review_planning_contract.unknown_fallback_extraction_demands
            )
            state.review_planning_contract.clause_unit_targeted_count = len(unit_targeted)
            state.review_planning_contract.text_fallback_clause_count = len(text_targeted)
        base_preview = ",".join(state.review_planning_contract.base_extraction_demands[:3])
        required_preview = ",".join(state.review_planning_contract.required_task_extraction_demands[:3])
        optional_preview = ",".join(state.review_planning_contract.optional_enhancement_extraction_demands[:3])
        fallback_preview = ",".join(state.review_planning_contract.unknown_fallback_extraction_demands[:3])
        state.stage_records.append(
            RunStageRecord(
                stage_name="planning_guided_extraction",
                status="completed",
                item_count=added_count,
                detail=(
                    f"按 review planning 的 extraction demand 定向抽取 {len(target_fields)} 个字段，"
                    f"目标 zone {len(target_zones)} 个，新增 {added_count} 条结构化条款。"
                    f" ClauseUnit命中 {len(unit_targeted)} 条，文本fallback {len(text_targeted)} 条。"
                    + (f" 基础必抽：{base_preview}。" if base_preview else "")
                    + (f" 任务必需：{required_preview}。" if required_preview else "")
                    + (f" 可选增强：{optional_preview}。" if optional_preview else "")
                    + (f" unknown fallback：{fallback_preview}。" if fallback_preview else "")
                ),
            )
        )

    def _stage_dimension_review(self, state: ReviewPipelineState) -> None:
        review_points = []
        manual_review_queue: list[str] = []
        reviewed_dimensions: list[str] = []
        for dimension in self.dimensions:
            reviewed_dimensions.append(dimension.display_name)
            dimension_findings = _review_dimension(state.normalized_text, dimension)
            review_points.extend(
                build_review_points_from_findings(
                    dimension_findings,
                    state.parse_result.text,
                    state.extracted_clauses,
                )
            )
            for finding in dimension_findings:
                if finding.finding_type == FindingType.manual_review_required:
                    manual_review_queue.append(finding.title)
        state.review_points.extend(review_points)
        state.manual_review_queue.extend(manual_review_queue)
        state.reviewed_dimensions = reviewed_dimensions
        state.stage_records.append(
            RunStageRecord(
                stage_name="dimension_review",
                status="completed",
                item_count=len(review_points),
                detail=f"完成 {len(reviewed_dimensions)} 个维度的基础筛查。",
            )
        )

    def _stage_rule_evaluation(self, state: ReviewPipelineState) -> None:
        risk_hits, rule_selection = execute_rule_registry(
            text=state.normalized_text,
            clauses=state.extracted_clauses,
        )
        state.rule_selection = rule_selection
        state.risk_hits = annotate_risk_hits(dedupe_risk_hits(risk_hits))
        state.review_points.extend(build_review_points_from_risk_hits(state.risk_hits, state.extracted_clauses))
        state.specialist_tables = build_specialist_tables(state.risk_hits)
        state.stage_records.append(
            RunStageRecord(
                stage_name="rule_evaluation",
                status="completed",
                item_count=len(state.risk_hits),
                detail=(
                    f"执行核心规则 {len(rule_selection.core_modules)} 个，"
                    f"场景增强规则 {len(rule_selection.enhancement_modules)} 个，"
                    f"共命中 {len(state.risk_hits)} 条风险。"
                ),
            )
        )

    def _stage_consistency_review(self, state: ReviewPipelineState) -> None:
        state.consistency_checks = annotate_consistency_checks(
            check_consistency(
                state.normalized_text,
                state.extracted_clauses,
                state.source_documents,
            )
        )
        state.review_points.extend(
            build_review_points_from_consistency_checks(state.consistency_checks)
        )
        issue_count = sum(1 for item in state.consistency_checks if item.status == "issue")
        state.stage_records.append(
            RunStageRecord(
                stage_name="consistency_review",
                status="completed",
                item_count=issue_count,
                detail=f"完成一致性矩阵检查，发现 {issue_count} 条需关注项。",
            )
        )

    def _stage_review_point_assembly(self, state: ReviewPipelineState) -> None:
        state.review_points.extend(
            build_review_points_from_instances(
                state.review_point_instances,
                state.legal_fact_candidates,
            )
        )
        state.review_points = annotate_review_points(merge_review_points(state.review_points))
        state.review_point_catalog = build_review_point_catalog_snapshot(
            state.review_points,
            state.review_point_instances,
        )
        state.stage_records.append(
            RunStageRecord(
                stage_name="review_point_assembly",
                status="completed",
                item_count=len(state.review_points),
                detail=(
                    f"已从审查结果组装 {len(state.review_points)} 个 ReviewPoint，"
                    f"并同步吸收 {len(state.review_point_instances)} 个 ReviewPointInstance 的目录元数据。"
                ),
            )
        )

    def _stage_applicability_check(self, state: ReviewPipelineState) -> None:
        state.applicability_checks = build_point_applicability_checks(
            state.review_points,
            state.extracted_clauses,
            state.review_point_instances,
        )
        applicable_count = sum(1 for item in state.applicability_checks if item.applicable)
        state.stage_records.append(
            RunStageRecord(
                stage_name="applicability_check",
                status="completed",
                item_count=applicable_count,
                detail=f"完成 {len(state.applicability_checks)} 个审查点的适法性检查，其中 {applicable_count} 个当前满足适用条件。",
            )
        )

    def _stage_review_quality_gate(self, state: ReviewPipelineState) -> None:
        state.quality_gates = build_point_quality_gates(state.review_points, state.extracted_clauses)
        passed_count = sum(1 for item in state.quality_gates if item.status.value == "passed")
        state.stage_records.append(
            RunStageRecord(
                stage_name="review_quality_gate",
                status="completed",
                item_count=passed_count,
                detail=f"完成 review_quality_gate，{passed_count} 个审查点通过质量关卡。",
            )
        )

    def _stage_formal_adjudication(self, state: ReviewPipelineState) -> None:
        state.formal_adjudication = build_formal_adjudication(
            state.review_points,
            state.applicability_checks,
            state.quality_gates,
            state.parse_result.text,
            state.extracted_clauses,
            state.parse_result.tables,
            state.review_point_instances,
        )
        included_count = sum(1 for item in state.formal_adjudication if item.included_in_formal)
        state.stage_records.append(
            RunStageRecord(
                stage_name="formal_adjudication",
                status="completed",
                item_count=included_count,
                detail=f"已完成 formal_adjudication，{included_count} 个审查点可进入正式意见。",
            )
        )

    def _stage_finalize_report(self, state: ReviewPipelineState) -> None:
        state.findings = annotate_findings(
            dedupe_findings(convert_review_points_to_findings(state.review_points))
        )
        state.manual_review_queue = dedupe_strings(state.manual_review_queue)
        state.relative_strengths = dedupe_strings(
            collect_relative_strengths(state.section_index, state.findings)
        )
        state.recommendations = dedupe_recommendations(build_recommendations(state.findings))
        state.overall_conclusion = derive_conclusion_by_evidence(
            state.findings,
            state.parse_result.text,
            state.extracted_clauses,
        )
        state.summary = _build_summary(
            findings=state.findings,
            manual_review_queue=state.manual_review_queue,
            overall_conclusion=state.overall_conclusion,
        )
        state.stage_records.append(
            RunStageRecord(
                stage_name="finalize_report",
                status="completed",
                item_count=len(state.findings),
                detail=f"完成结果归并，形成 {len(state.findings)} 条最终审查结果。",
            )
        )


def build_parse_result_for_text(text: str, document_name: str) -> ParseResult:
    suffix = Path(document_name).suffix.lower().lstrip(".") or "txt"
    raw_blocks = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        metadata = {
            "heading_candidate": bool(stripped == "目录" or stripped.startswith("第") or stripped.startswith("一、") or stripped.startswith("（")),
            "catalog_candidate": bool(stripped == "目录"),
            "numbering_level_guess": 1 if stripped.startswith("第") else 2 if stripped.startswith("一、") else 3 if stripped.startswith("（") else 0,
        }
        from .models import RawBlock, SourceAnchor

        raw_blocks.append(
            RawBlock(
                block_id=f"p-{index}",
                block_type="paragraph",
                text=stripped,
                anchor=SourceAnchor(source_path=document_name, block_no=index, paragraph_no=index, line_hint=f"line:{index}"),
                metadata=metadata,
            )
        )
    return ParseResult(
        parser_name="text",
        source_path=document_name,
        source_format=suffix,
        page_count=1,
        text=text,
        pages=[ParsedPage(page_index=1, text=text, source="text")],
        tables=[],
        raw_blocks=raw_blocks,
        warnings=[],
    )


def _merge_extracted_clauses(
    primary: list,
    fallback: list,
) -> list:
    merged: list = []
    seen: set[tuple[str, str, str]] = set()
    for clause in primary + fallback:
        key = (clause.field_name, clause.source_anchor, clause.content[:120])
        if key in seen:
            continue
        seen.add(key)
        merged.append(clause)
    return merged


def _review_dimension(text: str, dimension: ReviewDimension) -> list[Finding]:
    lowered = text.lower()
    matched_triggers = [item for item in dimension.triggers if item.lower() in lowered]
    matched_missing_markers = [item for item in dimension.missing_markers if item.lower() in lowered]

    if not matched_triggers:
        return [
            Finding(
                dimension=dimension.display_name,
                finding_type=FindingType.missing_evidence,
                severity=Severity.medium,
                title=f"{dimension.display_name}信息可能缺失",
                rationale=(
                    "未在文档文本中定位到该审查维度的常见触发词，"
                    "可能表示相关条款缺失、表达方式异常，或当前文本并不完整。"
                ),
                evidence=[],
                confidence=0.45,
                next_action="补充完整招标文件正文及附件后重新审查。",
            )
        ]

    evidence = [Evidence(quote=item, section_hint="keyword_match") for item in matched_triggers[:3]]

    findings: list[Finding] = []
    if matched_missing_markers:
        findings.append(
            Finding(
                dimension=dimension.display_name,
                finding_type=FindingType.manual_review_required,
                severity=Severity.medium,
                title=f"{dimension.display_name}依赖附件或外部材料",
                rationale=(
                    "文档中出现了依赖附件、另册或后续文件的表达，"
                    "自动审查无法仅凭当前文本形成完整结论。"
                ),
                evidence=[
                    Evidence(quote=item, section_hint="missing_marker")
                    for item in matched_missing_markers[:3]
                ],
                confidence=0.72,
                next_action="核验被引用附件、附表或正式合同文本。",
            )
        )

    if dimension.key == "restrictive_terms":
        restrictive_hits = [
            item
            for item in ["指定品牌", "原厂", "本地", "注册地", "唯一"]
            if item.lower() in lowered
        ]
        if restrictive_hits:
            findings.append(
                Finding(
                    dimension=dimension.display_name,
                    finding_type=FindingType.warning,
                    severity=Severity.high,
                    title="发现潜在限制性竞争表述",
                    rationale=(
                        "文档中命中了常见限制性或歧视性表述关键词，"
                        "需要进一步判断是否具备合法、必要、可替代的依据。"
                    ),
                    evidence=[
                        Evidence(quote=item, section_hint="restrictive_term")
                        for item in restrictive_hits[:3]
                    ],
                    confidence=0.78,
                    next_action="核查该条款是否与采购需求直接相关且不排斥潜在供应商。",
                )
            )

    if dimension.key == "evaluation_criteria":
        if "综合评分" in text and "评分标准" not in text:
            findings.append(
                Finding(
                    dimension=dimension.display_name,
                    finding_type=FindingType.warning,
                    severity=Severity.high,
                    title="评审方法出现但评分标准不够清晰",
                    rationale="文本提到综合评分，但未同时发现清晰的评分标准触发词。",
                    evidence=[Evidence(quote="综合评分", section_hint="keyword_match")],
                    confidence=0.70,
                    next_action="核查是否存在完整评分细则、分值和量化口径。",
                )
            )

    if not findings:
        findings.append(
            Finding(
                dimension=dimension.display_name,
                finding_type=FindingType.pass_,
                severity=Severity.low,
                title=f"{dimension.display_name}已完成基础筛查",
                rationale=dimension.risk_hint or "已完成基础关键词覆盖检查，未发现明显异常。",
                evidence=evidence,
                confidence=0.60,
                next_action="如需正式结论，建议结合具体法规条文进行二次复核。",
            )
        )

    return findings


def _build_summary(
    findings: list[Finding],
    manual_review_queue: list[str],
    overall_conclusion: ConclusionLevel,
) -> str:
    issue_count = sum(
        1
        for item in findings
        if item.finding_type
        in {
            FindingType.confirmed_issue,
            FindingType.warning,
            FindingType.manual_review_required,
            FindingType.missing_evidence,
        }
    )
    if manual_review_queue:
        return (
            f"审查结论为“{overall_conclusion.value}”。共生成 {len(findings)} 条审查结果，"
            f"其中 {issue_count} 条需要重点关注，{len(manual_review_queue)} 条需要人工复核。"
        )
    return (
        f"审查结论为“{overall_conclusion.value}”。共生成 {len(findings)} 条审查结果，"
        f"其中 {issue_count} 条需要关注。"
    )


def _build_high_risk_review_items(findings: list[Finding]) -> list[ReviewWorkItem]:
    items: list[ReviewWorkItem] = []
    for finding in findings:
        if finding.severity not in {Severity.high, Severity.critical}:
            continue
        items.append(
            ReviewWorkItem(
                item_type="finding",
                title=finding.title,
                severity=finding.severity.value,
                source=finding.dimension,
                reason=finding.rationale,
                action=finding.next_action,
            )
        )
    return items


def _build_pending_confirmation_items(
    findings: list[Finding],
    clauses: list,
    manual_review_queue: list[str],
) -> list[ReviewWorkItem]:
    items: list[ReviewWorkItem] = []
    for finding in findings:
        if finding.adoption_status != AdoptionStatus.manual:
            continue
        items.append(
            ReviewWorkItem(
                item_type="llm_finding",
                title=finding.title,
                severity=finding.severity.value,
                source=finding.dimension,
                reason=finding.review_note or finding.rationale,
                action=finding.next_action,
            )
        )
    for clause in clauses:
        if clause.adoption_status.value != "需人工确认":
            continue
        items.append(
            ReviewWorkItem(
                item_type="llm_clause",
                title=f"{clause.field_name}补充抽取",
                severity="medium",
                source=clause.category,
                reason=clause.review_note or clause.content,
                action="结合原文或附件核实后决定是否纳入正式条款抽取。",
            )
        )
    for title in manual_review_queue:
        items.append(
            ReviewWorkItem(
                item_type="manual_queue",
                title=title,
                severity="medium",
                source="基础人工复核",
                reason="当前文本存在附件依赖、外部材料依赖或自动判断边界。",
                action="补齐相关附件、补遗或合同文本后复核。",
            )
        )
    seen: set[tuple[str, str, str]] = set()
    deduped: list[ReviewWorkItem] = []
    for item in items:
        key = (item.item_type, item.title, item.source)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _build_review_planning_contract(
    document_profile: DocumentProfile | None,
    review_points: list[ReviewPoint],
    legal_fact_candidates: list[object] | None = None,
    review_point_instances: list[object] | None = None,
) -> ReviewPlanningContract | None:
    if document_profile is None:
        return None
    definitions = [
        resolve_review_point_definition(point.title, point.dimension, point.severity)
        for point in review_points
    ]
    contracts = [
        contract
        for point_id in _ordered_unique(
            [
                *(point.catalog_id for point in review_points),
                *(getattr(instance, "point_id", "") for instance in (review_point_instances or [])),
            ]
        )
        for contract in [get_review_point_contract(point_id)]
        if contract is not None
    ]
    fact_type_counts = _count_fact_types(legal_fact_candidates or [])
    external_route_tags, external_preferred_fields, external_fallback_fields, external_activation_reasons = (
        _collect_external_profile_planning_hints(document_profile)
    )
    route_tags = _ordered_unique(
        list(profile_activation_tags(document_profile))
        + list(document_profile.risk_activation_hints)
        + _route_tags_from_profile(document_profile)
        + external_route_tags
    )
    routing_flags = _ordered_unique(
        list(document_profile.structure_flags)
        + list(document_profile.quality_flags)
        + list(document_profile.unknown_structure_flags)
    )
    planned_catalog_ids = _ordered_unique(
        [
            *(point.catalog_id for point in review_points),
            *(getattr(instance, "point_id", "") for instance in (review_point_instances or [])),
        ]
    )
    priority_dimensions = _ordered_unique(point.dimension for point in review_points)
    activated_risk_families = _ordered_unique(definition.risk_family for definition in definitions if definition.risk_family)
    activated_risk_families = _ordered_unique(
        [
            *activated_risk_families,
            *(contract.risk_family for contract in contracts if contract.risk_family),
        ]
    )
    suppressed_risk_families = _suppressed_risk_families(document_profile, activated_risk_families)
    target_zones = _ordered_unique(
        [
            *(zone for definition in definitions for zone in (definition.target_zones or [])),
            *(zone for contract in contracts for zone in contract.target_zone_types),
        ]
    )
    activation_reasons = _ordered_unique(
        [
            *document_profile.routing_reasons,
            *document_profile.risk_activation_hints,
            *document_profile.unknown_structure_flags,
            *document_profile.quality_flags,
            *external_activation_reasons,
            *(f"review_point_contract:{contract.point_id}" for contract in contracts),
            *(
                f"legal_fact:{fact_type}:{count}"
                for fact_type, count in fact_type_counts.items()
            ),
            *(
                f"rule_definition:{rule.rule_id}"
                for point in review_points
                for rule in list_rules_for_point(point.catalog_id)[:2]
            ),
            *(f"review_point_instance:{getattr(instance, 'point_id', '')}" for instance in (review_point_instances or [])),
        ]
    )
    base_extraction_demands = _build_base_extraction_demands(document_profile, route_tags)
    required_task_extraction_demands = [
        field
        for field in _collect_required_task_extraction_demands(review_points)
        if field not in base_extraction_demands
    ]
    required_task_extraction_demands = _ordered_unique(
        [
            *required_task_extraction_demands,
            *(field for contract in contracts for field in contract.required_fields),
        ]
    )
    required_task_extraction_demands = [
        field for field in required_task_extraction_demands if field not in base_extraction_demands
    ]
    optional_enhancement_extraction_demands = [
        field
        for field in [
            *_collect_optional_enhancement_extraction_demands(review_points),
            *(field for contract in contracts for field in contract.enhancement_fields),
            *external_preferred_fields,
        ]
        if field not in base_extraction_demands and field not in required_task_extraction_demands
    ]
    enhancement_extraction_demands = _ordered_unique(
        [
            *required_task_extraction_demands,
            *optional_enhancement_extraction_demands,
        ]
    )
    unknown_fallback_extraction_demands = [
        field
        for field in [
            *_build_unknown_fallback_extraction_demands(document_profile, route_tags),
            *external_fallback_fields,
        ]
        if field not in base_extraction_demands and field not in enhancement_extraction_demands
    ]
    extraction_demands = _ordered_unique(
        [
            *base_extraction_demands,
            *enhancement_extraction_demands,
            *unknown_fallback_extraction_demands,
        ]
    )
    high_value_fields = _ordered_unique(
        [
            *required_task_extraction_demands,
            *base_extraction_demands[:4],
            *enhancement_extraction_demands[:4],
        ]
    )
    summary = (
        f"已将 {document_profile.procurement_kind} 画像按 {document_profile.routing_mode} 路由转成 "
        f"{len(planned_catalog_ids)} 个待执行审查点，"
        f"激活 {len(activated_risk_families)} 个母题，抑制 {len(suppressed_risk_families)} 个母题，"
        f"并显式暴露 {len(extraction_demands)} 项抽取需求。"
    )
    return ReviewPlanningContract(
        document_id=document_profile.document_id,
        procurement_kind=document_profile.procurement_kind,
        routing_mode=document_profile.routing_mode,
        route_tags=route_tags,
        routing_flags=routing_flags,
        activation_reasons=activation_reasons,
        activated_risk_families=activated_risk_families,
        suppressed_risk_families=suppressed_risk_families,
        target_zones=target_zones,
        target_primary_review_types=_target_primary_review_types(target_zones),
        planned_catalog_ids=planned_catalog_ids,
        priority_dimensions=priority_dimensions,
        base_extraction_demands=base_extraction_demands,
        required_task_extraction_demands=required_task_extraction_demands,
        optional_enhancement_extraction_demands=optional_enhancement_extraction_demands,
        enhancement_extraction_demands=enhancement_extraction_demands,
        unknown_fallback_extraction_demands=unknown_fallback_extraction_demands,
        extraction_demands=extraction_demands,
        high_value_fields=high_value_fields,
        summary=summary,
    )


def _target_primary_review_types(target_zones: list[str]) -> list[str]:
    ordered: list[str] = []
    for zone_name in target_zones:
        try:
            zone_type = SemanticZoneType(zone_name)
        except ValueError:
            continue
        review_type = ZONE_PRIMARY_REVIEW_TYPES.get(zone_type, "")
        if not review_type or review_type in ordered:
            continue
        ordered.append(review_type)
    return ordered


def _route_tags_from_profile(document_profile: DocumentProfile) -> list[str]:
    tags: list[str] = []
    if document_profile.procurement_kind == "unknown":
        tags.extend(["unknown", "structure"])
    if document_profile.routing_mode == "unknown_conservative":
        tags.append("unknown_conservative")
    if document_profile.quality_flags:
        if any(flag in document_profile.quality_flags for flag in ["template_ratio_high", "template_appendix_mix_high"]):
            tags.append("template")
        if any(flag in document_profile.quality_flags for flag in ["catalog_navigation_high", "weak_source_support", "non_body_structure_dominant"]):
            tags.append("consistency")
    if any(flag in document_profile.structure_flags for flag in ["heavy_scoring_tables", "scoring_dense_structure"]):
        tags.append("scoring")
    if any(flag in document_profile.structure_flags for flag in ["heavy_contract_terms"]):
        tags.append("contract")
    if any(flag in document_profile.structure_flags for flag in ["heavy_template_pollution", "template_pollution"]):
        tags.append("template")
    if any(flag in document_profile.structure_flags for flag in ["heavy_appendix_reference", "attachment_driven_structure", "catalog_navigation_heavy", "directory_driven_structure"]):
        tags.append("structure")
    return tags


def _suppressed_risk_families(
    document_profile: DocumentProfile,
    activated_risk_families: list[str],
) -> list[str]:
    if document_profile.routing_mode != "unknown_conservative":
        return []
    conservative_default = ["competition", "personnel"]
    return [family for family in conservative_default if family not in activated_risk_families]


def _collect_required_task_extraction_demands(review_points: list[ReviewPoint]) -> list[str]:
    demands: list[str] = []
    for point in review_points:
        definition = resolve_review_point_definition(point.title, point.dimension, point.severity)
        for field_name in definition.required_fields:
            if field_name and field_name not in demands:
                demands.append(field_name)
    return demands


def _collect_optional_enhancement_extraction_demands(review_points: list[ReviewPoint]) -> list[str]:
    demands: list[str] = []
    for point in review_points:
        definition = resolve_review_point_definition(point.title, point.dimension, point.severity)
        for field_name in definition.enhancement_fields:
            if field_name and field_name not in demands:
                demands.append(field_name)
    return demands


def _build_base_extraction_demands(
    document_profile: DocumentProfile,
    route_tags: list[str],
) -> list[str]:
    demands = ["项目属性", "采购标的", "采购内容构成"]
    route_tag_set = set(route_tags)
    if "contract" in route_tag_set:
        demands.extend(["付款节点", "验收标准", "违约责任"])
    if "scoring" in route_tag_set:
        demands.extend(["评分方法", "评分项明细"])
    if "policy" in route_tag_set:
        demands.extend(["是否专门面向中小企业", "中小企业声明函类型", "是否仍保留价格扣除条款"])
    if "qualification" in route_tag_set:
        demands.extend(["一般资格要求", "特定资格要求", "资格条件明细"])
    if "template" in route_tag_set:
        demands.extend(["投标文件格式", "附件引用"])
    if document_profile.procurement_kind in {"goods", "service"}:
        demands.extend(["采购方式", "合同履行期限"])
    return _ordered_unique(demands)


def _build_unknown_fallback_extraction_demands(
    document_profile: DocumentProfile,
    route_tags: list[str],
) -> list[str]:
    if document_profile.procurement_kind not in {"unknown", "mixed"}:
        return []
    demands = ["采购包数量", "采购包划分说明", "合同类型", "合同履行期限"]
    route_tag_set = set(route_tags)
    if "template" in route_tag_set:
        demands.extend(["投标文件格式", "附件引用"])
    if "structure" in route_tag_set or "consistency" in route_tag_set:
        demands.extend(["预算金额", "最高限价", "采购方式", "采购方式适用理由"])
    if "scoring" in route_tag_set:
        demands.extend(["评分方法", "评分项明细"])
    if "contract" in route_tag_set:
        demands.extend(["付款节点", "验收标准"])
    return _ordered_unique(demands)


def _ordered_unique(items) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _count_fact_types(legal_fact_candidates: list[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in legal_fact_candidates:
        fact_type = str(getattr(item, "fact_type", "")).strip()
        if not fact_type:
            continue
        counts[fact_type] = counts.get(fact_type, 0) + 1
    return counts


def _collect_external_profile_planning_hints(
    document_profile: DocumentProfile,
) -> tuple[list[str], list[str], list[str], list[str]]:
    route_tags: list[str] = []
    preferred_fields: list[str] = []
    fallback_fields: list[str] = []
    activation_reasons: list[str] = []
    for candidate in document_profile.domain_profile_candidates[:2]:
        if candidate.confidence < 0.35:
            continue
        hints = external_profile_planning_hints(candidate.profile_id)
        route_tags.extend(hints.get("route_tags", []))
        preferred_fields.extend(hints.get("preferred_fields", []))
        fallback_fields.extend(hints.get("fallback_fields", []))
        activation_reasons.extend(
            [
                *hints.get("activation_reasons", []),
                f"external_profile_candidate:{candidate.profile_id}:{candidate.confidence:.2f}",
            ]
        )
    return (
        _ordered_unique(route_tags),
        _ordered_unique(preferred_fields),
        _ordered_unique(fallback_fields),
        _ordered_unique(activation_reasons),
    )

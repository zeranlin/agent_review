from __future__ import annotations

from collections.abc import Callable
import re

from .models import (
    ApplicabilityCheck,
    ApplicabilityItem,
    ApplicabilityStatus,
    ExtractedClause,
    ReviewPoint,
)
from .review_point_catalog import resolve_review_point_definition


RelationEvaluator = Callable[[dict[str, list[ExtractedClause]]], tuple[ApplicabilityStatus, list[str]]]


def build_applicability_checks(
    review_points: list[ReviewPoint],
    extracted_clauses: list[ExtractedClause],
) -> list[ApplicabilityCheck]:
    results: list[ApplicabilityCheck] = []
    clause_mapping = _clause_map(extracted_clauses)
    for point in review_points:
        definition = resolve_review_point_definition(point.title, point.dimension, point.severity)
        haystack = _build_haystack(point, clause_mapping)
        requirement_results: list[ApplicabilityItem] = []
        exclusion_results: list[ApplicabilityItem] = []

        for condition in definition.required_conditions:
            status, detail = _evaluate_required_condition(
                definition.catalog_id,
                condition.name,
                clause_mapping,
                haystack,
                condition.clause_fields,
                condition.signal_groups,
            )
            requirement_results.append(
                ApplicabilityItem(name=condition.name, status=status, detail=detail)
            )

        for condition in definition.exclusion_conditions:
            status, detail = _evaluate_exclusion_condition(
                definition.catalog_id,
                condition.name,
                clause_mapping,
                haystack,
                condition.clause_fields,
                condition.signal_groups,
            )
            exclusion_results.append(
                ApplicabilityItem(name=condition.name, status=status, detail=detail)
            )

        rebuttal_reasons = _build_rebuttal_reasons(point)
        satisfied_conditions = [
            item.name for item in requirement_results if item.status == ApplicabilityStatus.satisfied
        ]
        missing_conditions = [
            item.name
            for item in requirement_results
            if item.status in {ApplicabilityStatus.unsatisfied, ApplicabilityStatus.insufficient}
        ]
        blocking_conditions = [
            item.name for item in exclusion_results if item.status == ApplicabilityStatus.excluded
        ] + rebuttal_reasons

        requirement_chain_complete = bool(requirement_results) and not missing_conditions
        applicable = bool(requirement_chain_complete and not blocking_conditions)
        summary = _build_summary(
            satisfied_conditions=satisfied_conditions,
            missing_conditions=missing_conditions,
            blocking_conditions=blocking_conditions,
            applicable=applicable,
            requirement_results=requirement_results,
        )
        results.append(
            ApplicabilityCheck(
                point_id=point.point_id,
                catalog_id=definition.catalog_id,
                applicable=applicable,
                requirement_results=requirement_results,
                exclusion_results=exclusion_results,
                satisfied_conditions=satisfied_conditions,
                missing_conditions=missing_conditions,
                blocking_conditions=blocking_conditions,
                requirement_chain_complete=requirement_chain_complete,
                summary=summary,
            )
        )
    return results


def _build_haystack(point: ReviewPoint, clause_mapping: dict[str, list[ExtractedClause]]) -> str:
    texts = [point.title, point.rationale]
    texts.extend(item.quote for item in point.evidence_bundle.direct_evidence)
    texts.extend(item.quote for item in point.evidence_bundle.supporting_evidence)
    texts.extend(item.quote for item in point.evidence_bundle.conflicting_evidence)
    texts.extend(item.quote for item in point.evidence_bundle.rebuttal_evidence)
    for source in point.source_findings:
        if source.startswith("risk_hit:"):
            texts.append(source.replace("risk_hit:", "", 1))
    texts.extend(
        clause.content
        for clauses in clause_mapping.values()
        for clause in clauses
        if clause.source_anchor in {
            evidence.section_hint
            for evidence in (
                point.evidence_bundle.direct_evidence
                + point.evidence_bundle.supporting_evidence
                + point.evidence_bundle.conflicting_evidence
                + point.evidence_bundle.rebuttal_evidence
            )
        }
    )
    return " ".join(texts)


def _evaluate_required_condition(
    catalog_id: str,
    condition_name: str,
    clause_mapping: dict[str, list[ExtractedClause]],
    haystack: str,
    clause_fields: list[str],
    signal_groups: list[list[str]],
) -> tuple[ApplicabilityStatus, str]:
    relation_match = _evaluate_relation(catalog_id, condition_name, clause_mapping)
    if relation_match is not None:
        return relation_match

    matched_fields = [field for field in clause_fields if clause_mapping.get(field)]
    fields_ok = not clause_fields or len(matched_fields) == len(clause_fields)
    signals_ok = not signal_groups or all(any(token and token in haystack for token in group) for group in signal_groups)

    if fields_ok and signals_ok:
        return ApplicabilityStatus.satisfied, _matched_detail("要件", bool(matched_fields), matched_fields)
    if matched_fields or signals_ok:
        return ApplicabilityStatus.unsatisfied, _contradicted_detail("要件", clause_fields, matched_fields)
    return ApplicabilityStatus.insufficient, _unmatched_detail("要件", clause_fields)


def _evaluate_exclusion_condition(
    catalog_id: str,
    condition_name: str,
    clause_mapping: dict[str, list[ExtractedClause]],
    haystack: str,
    clause_fields: list[str],
    signal_groups: list[list[str]],
) -> tuple[ApplicabilityStatus, str]:
    relation_match = _evaluate_relation(catalog_id, condition_name, clause_mapping)
    if relation_match is not None:
        status, detail = relation_match
        if status == ApplicabilityStatus.satisfied:
            return ApplicabilityStatus.excluded, detail
        return ApplicabilityStatus.not_applicable, detail

    matched_fields = [field for field in clause_fields if clause_mapping.get(field)]
    fields_ok = not clause_fields or len(matched_fields) == len(clause_fields)
    signals_ok = not signal_groups or all(any(token and token in haystack for token in group) for group in signal_groups)
    if fields_ok and signals_ok:
        return ApplicabilityStatus.excluded, _matched_detail("排除条件", bool(matched_fields), matched_fields)
    return ApplicabilityStatus.not_applicable, _unmatched_detail("排除条件", clause_fields)


def _evaluate_relation(
    catalog_id: str,
    condition_name: str,
    clause_mapping: dict[str, list[ExtractedClause]],
) -> tuple[ApplicabilityStatus, str] | None:
    evaluator = RELATION_EVALUATORS.get((catalog_id, condition_name))
    if evaluator is None:
        return None
    status, details = evaluator(clause_mapping)
    return status, "；".join(details)


def _build_summary(
    *,
    satisfied_conditions: list[str],
    missing_conditions: list[str],
    blocking_conditions: list[str],
    applicable: bool,
    requirement_results: list[ApplicabilityItem],
) -> str:
    if applicable:
        return (
            f"要件链成立：已满足 {len(satisfied_conditions)} 项要件，"
            "未命中排除条件或反证，可进入 formal 适法性判断。"
        )
    if blocking_conditions:
        return (
            "要件链被阻断："
            f"已满足 {len(satisfied_conditions)} 项要件，"
            f"阻断因素为 {', '.join(blocking_conditions)}。"
        )
    if requirement_results:
        return (
            "要件链未闭合："
            f"已满足 {len(satisfied_conditions)}/{len(requirement_results)} 项要件，"
            f"仍缺 {', '.join(missing_conditions)}。"
        )
    return "当前目录项尚未配置细化要件，暂按通用审查点处理。"


def _build_rebuttal_reasons(point: ReviewPoint) -> list[str]:
    reasons: list[str] = []
    if any(_is_blocking_conflict(item.quote) for item in point.evidence_bundle.conflicting_evidence):
        reasons.append("存在冲突证据")
    if point.evidence_bundle.rebuttal_evidence:
        reasons.append("存在反证")
    return reasons


def _is_blocking_conflict(quote: str) -> bool:
    return any(token in quote for token in ["=否", "=不允许", "不适用", "禁止"])


def _clause_map(clauses: list[ExtractedClause]) -> dict[str, list[ExtractedClause]]:
    mapping: dict[str, list[ExtractedClause]] = {}
    for clause in clauses:
        mapping.setdefault(clause.field_name, []).append(clause)
    return mapping


def _matched_detail(prefix: str, matched_by_fields: bool, matched_fields: list[str]) -> str:
    if matched_by_fields and matched_fields:
        return f"已通过结构化字段命中该{prefix}：{', '.join(matched_fields)}。"
    return f"已在当前审查点证据或理由中定位到该{prefix}信号。"


def _contradicted_detail(prefix: str, clause_fields: list[str], matched_fields: list[str]) -> str:
    if clause_fields and matched_fields:
        return (
            f"结构化字段已部分出现但未形成完整{prefix}链："
            f"已命中 {', '.join(matched_fields)}，仍缺 {', '.join(field for field in clause_fields if field not in matched_fields)}。"
        )
    return f"当前{prefix}存在部分信号，但不足以闭合要件链。"


def _unmatched_detail(prefix: str, clause_fields: list[str]) -> str:
    if clause_fields:
        return f"当前结构化条款中尚未完整满足该{prefix}字段要求：{', '.join(clause_fields)}。"
    return f"当前审查点证据中尚未完整定位到该{prefix}信号。"


def _first_value(clause_mapping: dict[str, list[ExtractedClause]], field_name: str) -> str:
    clauses = clause_mapping.get(field_name, [])
    for clause in clauses:
        if clause.normalized_value:
            return clause.normalized_value
    return clauses[0].content if clauses else ""


def _first_normalized_or_content(clause_mapping: dict[str, list[ExtractedClause]], field_name: str) -> str:
    clauses = clause_mapping.get(field_name, [])
    if not clauses:
        return ""
    return clauses[0].normalized_value or clauses[0].content


def _collect_tags(clause_mapping: dict[str, list[ExtractedClause]], field_name: str) -> set[str]:
    tags: set[str] = set()
    for clause in clause_mapping.get(field_name, []):
        tags.update(clause.relation_tags)
    return tags


def _equals_relation(field_name: str, expected_value: str, label: str) -> RelationEvaluator:
    def evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
        actual = _first_value(clause_mapping, field_name)
        if actual == expected_value:
            return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：{field_name}={actual}，满足{label}。"]
        if not actual:
            return ApplicabilityStatus.insufficient, [f"结构化字段缺失：{field_name}。"]
        return ApplicabilityStatus.unsatisfied, [f"结构化字段关系未成立：{field_name}={actual}，不满足{label}。"]

    return evaluator


def _contains_relation(field_name: str, expected_fragment: str, label: str) -> RelationEvaluator:
    def evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
        actual = _first_value(clause_mapping, field_name)
        if actual and expected_fragment in actual:
            return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：{field_name} 包含 {expected_fragment}，满足{label}。"]
        if not actual:
            return ApplicabilityStatus.insufficient, [f"结构化字段缺失：{field_name}。"]
        return ApplicabilityStatus.unsatisfied, [f"结构化字段关系未成立：{field_name}={actual}，未体现{expected_fragment}。"]

    return evaluator


def _missing_relation(field_name: str, label: str) -> RelationEvaluator:
    def evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
        actual = _first_value(clause_mapping, field_name)
        if not actual:
            return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：{field_name} 缺失，符合{label}。"]
        return ApplicabilityStatus.unsatisfied, [f"结构化字段关系未成立：{field_name} 已抽取为 {actual}。"]

    return evaluator


def _exists_relation(field_name: str, label: str) -> RelationEvaluator:
    def evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
        actual = _first_value(clause_mapping, field_name)
        if actual:
            return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：{field_name}={actual}，满足{label}。"]
        return ApplicabilityStatus.insufficient, [f"结构化字段缺失：{field_name}。"]

    return evaluator


def _payment_assessment_link_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    payment_value = _first_value(clause_mapping, "付款节点")
    payment_tags = _collect_tags(clause_mapping, "付款节点")
    assessment_value = _first_value(clause_mapping, "考核条款")
    assessment_tags = _collect_tags(clause_mapping, "考核条款")
    if payment_value and assessment_value and (
        "考核联动" in payment_tags or "关联付款" in assessment_tags or "尾款" in payment_tags
    ):
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：付款节点={payment_value}，考核条款={assessment_value}，且存在尾款/考核联动。"]
    if not payment_value or not assessment_value:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：需同时抽取付款节点和考核条款。"]
    return ApplicabilityStatus.unsatisfied, [f"已抽取付款节点与考核条款，但尚未识别尾款/付款联动标签：付款标签={sorted(payment_tags)}，考核标签={sorted(assessment_tags)}。"]


def _contract_type_mismatch_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    project_type = _first_normalized_or_content(clause_mapping, "项目属性")
    contract_type = _first_normalized_or_content(clause_mapping, "合同类型")
    procurement_subject = _first_value(clause_mapping, "采购标的")
    service_tags = _collect_tags(clause_mapping, "采购内容构成") | _collect_tags(clause_mapping, "是否含持续性服务")
    if not project_type or not contract_type:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：需同时抽取项目属性和合同类型。"]
    if project_type == "货物" and contract_type in {"承揽合同", "服务合同"}:
        if "家具" in procurement_subject and "持续性作业服务" not in service_tags:
            return ApplicabilityStatus.unsatisfied, [f"已识别项目属性={project_type}、合同类型={contract_type}，但采购标的={procurement_subject} 仍以典型货物为主，尚不足以直接认定口径错配。"]
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：项目属性={project_type}，合同类型={contract_type}，合同口径偏服务/承揽。"]
    if project_type == "服务" and contract_type == "买卖合同":
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：项目属性={project_type}，合同类型={contract_type}，合同口径偏货物买卖。"]
    if project_type == "货物" and "持续性作业服务" in service_tags:
        return ApplicabilityStatus.unsatisfied, [f"已识别服务作业标签 {sorted(service_tags)}，但合同类型={contract_type} 尚未形成强冲突。"]
    return ApplicabilityStatus.unsatisfied, [f"结构化字段关系未成立：项目属性={project_type}，合同类型={contract_type}。"]


def _continuous_service_in_goods_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    project_type = _first_normalized_or_content(clause_mapping, "项目属性")
    service_flag = _first_normalized_or_content(clause_mapping, "是否含持续性服务")
    service_tags = _collect_tags(clause_mapping, "是否含持续性服务") | _collect_tags(clause_mapping, "采购内容构成")
    if not project_type or not service_flag:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：需同时抽取项目属性和持续性服务内容。"]
    if project_type == "货物" and service_flag == "是":
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：项目属性={project_type}，且采购内容含持续性作业服务 {sorted(service_tags)}。"]
    return ApplicabilityStatus.unsatisfied, [f"结构化字段关系未成立：项目属性={project_type}，持续性服务标记={service_flag}。"]


def _industry_mismatch_scoring_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    suspicious = _first_value(clause_mapping, "行业相关性存疑评分项")
    project_subject = _first_value(clause_mapping, "采购标的") or _first_value(clause_mapping, "项目属性")
    if suspicious:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：评分项 {suspicious} 与当前项目 {project_subject or '项目'} 存在行业相关性疑点。"]
    return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到行业相关性存疑评分项。"]


def _plan_scoring_quant_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    pattern = _first_value(clause_mapping, "方案评分扣分模式")
    if pattern:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：已识别方案评分扣分模式={pattern}，存在量化不足疑点。"]
    return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到方案评分扣分模式。"]


def _subjective_scoring_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    pattern = _first_value(clause_mapping, "方案评分扣分模式")
    scoring_method = _first_value(clause_mapping, "评分方法")
    if pattern:
        return ApplicabilityStatus.satisfied, [
            f"结构化字段关系成立：评分方法={scoring_method or '未单列'}，已识别评分分档/扣分模式={pattern}，存在主观分档和量化不足疑点。"
        ]
    if scoring_method:
        return ApplicabilityStatus.unsatisfied, [f"已识别评分方法={scoring_method}，但尚未抽取到足以支撑主观分档判断的方案评分扣分模式。"]
    return ApplicabilityStatus.insufficient, ["结构化字段不足：需至少抽取评分方法或方案评分扣分模式。"]


def _certificate_weight_scoring_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    suspicious = _first_value(clause_mapping, "行业相关性存疑评分项")
    finance = _first_value(clause_mapping, "财务指标加分")
    cert_stage = _first_value(clause_mapping, "证书材料适用阶段")
    report_stage = _first_value(clause_mapping, "检测报告适用阶段")
    stage_values = {value for value in [cert_stage, report_stage] if value}
    if "投标阶段" in stage_values and suspicious and finance:
        return ApplicabilityStatus.satisfied, [
            f"结构化字段关系成立：已识别行业相关性存疑评分项={suspicious}、财务指标评分={finance}，且证书/报告材料处于投标阶段提交，负担和权重疑似偏重。"
        ]
    if "投标阶段" in stage_values and suspicious:
        return ApplicabilityStatus.satisfied, [
            f"结构化字段关系成立：已识别行业相关性存疑评分项={suspicious}，且证书/报告材料处于投标阶段提交，需重点复核投标门槛和评分权重。"
        ]
    if suspicious and finance:
        return ApplicabilityStatus.satisfied, [
            f"结构化字段关系成立：已识别行业相关性存疑评分项={suspicious}，且存在财务指标评分={finance}，证书/检测报告/财务指标权重疑似偏重。"
        ]
    if suspicious:
        return ApplicabilityStatus.satisfied, [
            f"结构化字段关系成立：已识别行业相关性存疑评分项={suspicious}，需重点复核证书、检测报告或报告类评分权重。"
        ]
    if finance:
        return ApplicabilityStatus.unsatisfied, [f"已识别财务指标评分={finance}，但尚未抽取到证书/检测报告类评分信号。"]
    return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到行业相关性存疑评分项或财务指标评分。"]


def _rigid_patent_requirement_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    patent_value = _first_normalized_or_content(clause_mapping, "是否要求专利")
    project_subject = _first_value(clause_mapping, "采购标的") or _first_value(clause_mapping, "项目属性")
    if not patent_value:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到专利要求条款。"]
    if patent_value == "刚性门槛":
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：在 {project_subject or '当前项目'} 中识别到“必须具备相关专利”等刚性门槛表述。"]
    return ApplicabilityStatus.unsatisfied, [f"已识别专利要求={patent_value}，但尚未达到刚性门槛强度。"]


def _scoring_material_stage_exclusion_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    cert_stage = _first_value(clause_mapping, "证书材料适用阶段")
    report_stage = _first_value(clause_mapping, "检测报告适用阶段")
    stage_values = {value for value in [cert_stage, report_stage] if value}
    if not stage_values:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到证书或检测报告的材料适用阶段。"]
    if "投标阶段" in stage_values:
        return ApplicabilityStatus.not_applicable, [f"已识别材料适用阶段={sorted(stage_values)}，不属于仅履约/验收阶段提交。"]
    if "履约/验收阶段" in stage_values:
        return ApplicabilityStatus.satisfied, ["结构化字段关系成立：证书/检测报告当前更像履约或验收阶段材料，不直接支撑投标阶段负担偏重。"]
    return ApplicabilityStatus.not_applicable, [f"已识别材料适用阶段={sorted(stage_values)}，仍需结合上下文判断。"]


def _bid_stage_material_burden_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    burden = _first_value(clause_mapping, "证书检测报告负担特征")
    cert_stage = _first_value(clause_mapping, "证书材料适用阶段")
    report_stage = _first_value(clause_mapping, "检测报告适用阶段")
    stage_values = {value for value in [cert_stage, report_stage] if value}
    if not burden:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到证书或检测报告负担特征。"]
    if "投标阶段" in stage_values:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：已识别材料负担特征={burden}，且材料适用阶段={sorted(stage_values)}，存在投标阶段门槛偏重疑点。"]
    if "履约/验收阶段" in stage_values:
        return ApplicabilityStatus.unsatisfied, [f"已识别材料负担特征={burden}，但当前更像履约/验收阶段材料。"]
    return ApplicabilityStatus.unsatisfied, [f"已识别材料负担特征={burden}，但材料适用阶段尚未明确为投标阶段。"]


def _certificate_score_weight_value_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    score_raw = _first_value(clause_mapping, "证书类评分总分")
    budget_raw = _first_value(clause_mapping, "预算金额")
    score = _parse_amount(score_raw)
    budget = _parse_amount(budget_raw)
    if score is None:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到证书类评分总分。"]
    if score >= 10:
        if budget is not None:
            return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：证书类评分总分={score_raw}分，预算金额={budget_raw}，证书类评分权重已达到高风险阈值。"]
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：证书类评分总分={score_raw}分，已达到高风险阈值。"]
    if score >= 8 and budget is not None and budget <= 1000000:
        if budget is not None:
            return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：证书类评分总分={score_raw}分，预算金额={budget_raw}，证书类评分权重疑似偏高。"]
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：证书类评分总分={score_raw}分，证书类评分权重疑似偏高。"]
    return ApplicabilityStatus.unsatisfied, [f"已识别证书类评分总分={score_raw}分，当前未达到高权重阈值。"]


def _credit_evaluation_scoring_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    credit_raw = _first_value(clause_mapping, "信用评价要求")
    scoring_items = _first_value(clause_mapping, "评分项明细")
    if not credit_raw:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到信用评价评分项。"]
    if scoring_items:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：信用评价评分项={credit_raw}，且已识别评分项明细={scoring_items}。"]
    return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：信用评价评分项={credit_raw}。"]


def _procurement_method_applicability_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    method = _first_normalized_or_content(clause_mapping, "采购方式")
    reason = _first_normalized_or_content(clause_mapping, "采购方式适用理由")
    if not method:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到采购方式。"]
    if any(token in method for token in ["竞争性磋商", "竞争性谈判", "单一来源", "询价"]):
        if reason:
            return ApplicabilityStatus.unsatisfied, [f"已识别采购方式={method}，且存在适用理由={reason}。"]
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：采购方式={method}，但尚未抽取到明确适用理由。"]
    return ApplicabilityStatus.unsatisfied, [f"已识别采购方式={method}，当前不构成非公开招标方式适用性重点。"]


def _package_split_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    project_type = _first_normalized_or_content(clause_mapping, "项目属性")
    content = _first_normalized_or_content(clause_mapping, "采购内容构成")
    service_flag = _first_normalized_or_content(clause_mapping, "是否含持续性服务")
    package_note = _first_normalized_or_content(clause_mapping, "采购包划分说明")
    package_count = _first_normalized_or_content(clause_mapping, "采购包数量")
    if not project_type and not content:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到项目属性或采购内容构成。"]
    mixed_signal = bool(
        (project_type == "货物" and service_flag == "是")
        or (content and any(token in content for token in ["人工", "运维", "施工", "管护", "服务", "安装"]))
    )
    if mixed_signal and not package_note:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：项目属性={project_type or '未识别'}，采购内容构成={content or '未识别'}，未抽取到包件划分或拆分依据。"]
    if package_note:
        return ApplicabilityStatus.unsatisfied, [f"已识别采购包划分说明={package_note}，采购包数量={package_count or '未识别'}。"]
    return ApplicabilityStatus.unsatisfied, [f"当前未形成明确混合采购未拆分信号：项目属性={project_type or '未识别'}，采购内容构成={content or '未识别'}。"]


def _qualification_scoring_overlap_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    qualification = _first_normalized_or_content(clause_mapping, "资格条件明细")
    scoring = _first_normalized_or_content(clause_mapping, "评分项明细")
    if not qualification or not scoring:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：需同时抽取资格条件明细和评分项明细。"]
    overlap_tokens = [
        token
        for token in ["资质", "证书", "业绩", "项目负责人", "人员", "社保", "信用"]
        if token in qualification and token in scoring
    ]
    if overlap_tokens:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：资格条件与评分项在 {', '.join(overlap_tokens)} 上存在重复门槛。"]
    return ApplicabilityStatus.unsatisfied, [f"已抽取资格条件与评分项，但当前未识别重复门槛：资格条件={qualification}；评分项={scoring}。"]


def _excessive_certificate_requirement_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    qualification = _first_normalized_or_content(clause_mapping, "特定资格要求")
    burden = _first_normalized_or_content(clause_mapping, "证书检测报告负担特征")
    suspicious = _first_normalized_or_content(clause_mapping, "行业相关性存疑评分项")
    cert_stage = _first_normalized_or_content(clause_mapping, "证书材料适用阶段")
    if not qualification and not burden and not suspicious:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到特定资质、证书或检测报告负担信号。"]
    if qualification and (burden or suspicious):
        detail = f"特定资格要求={qualification}"
        if burden:
            detail += f"，材料负担={burden}"
        if suspicious:
            detail += f"，评分疑点={suspicious}"
        if cert_stage:
            detail += f"，材料阶段={cert_stage}"
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：{detail}。"]
    return ApplicabilityStatus.unsatisfied, [f"已识别部分资质/证书要求，但尚未形成超必要限度链：特定资格要求={qualification or '未识别'}，材料负担={burden or '未识别'}，评分疑点={suspicious or '未识别'}。"]


def _technical_service_verifiability_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    signal = _first_normalized_or_content(clause_mapping, "技术服务可验证性信号")
    acceptance = _first_normalized_or_content(clause_mapping, "验收标准")
    if not signal:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到技术或服务要求可验证性信号。"]
    if acceptance:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：已识别可验证性不足信号={signal}，且存在验收标准条款={acceptance}。"]
    return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：已识别技术或服务要求可验证性不足信号={signal}。"]


def _acceptance_payment_linkage_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    payment = _first_normalized_or_content(clause_mapping, "付款节点")
    acceptance = _first_normalized_or_content(clause_mapping, "验收标准")
    assessment = _first_normalized_or_content(clause_mapping, "考核条款")
    satisfaction = _first_normalized_or_content(clause_mapping, "满意度条款")
    pay_tags = _collect_tags(clause_mapping, "付款节点")
    assessment_tags = _collect_tags(clause_mapping, "考核条款")
    satisfaction_tags = _collect_tags(clause_mapping, "满意度条款")
    if not payment:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到付款节点。"]
    linked = (
        "考核联动" in pay_tags
        or "关联付款" in assessment_tags
        or "关联付款" in satisfaction_tags
        or ("尾款" in pay_tags and (assessment or satisfaction))
    )
    if linked and (acceptance or assessment or satisfaction):
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：付款节点={payment}，验收/考核/满意度条款存在联动。"]
    if acceptance or assessment or satisfaction:
        return ApplicabilityStatus.unsatisfied, [f"已抽取付款节点与验收/考核/满意度条款，但尚未识别明确联动：付款={payment}，验收={acceptance or '未识别'}，考核={assessment or '未识别'}，满意度={satisfaction or '未识别'}。"]
    return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到验收、考核或满意度条款。"]


def _transfer_outsource_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    transfer = _first_normalized_or_content(clause_mapping, "转包外包条款")
    allow_subcontract = _first_normalized_or_content(clause_mapping, "是否允许分包")
    if not transfer:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到转包或外包条款。"]
    if any(token in transfer for token in ["转包", "外包", "核心任务", "委托第三方"]):
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：已识别转包外包条款={transfer}，是否允许分包={allow_subcontract or '未识别'}。"]
    return ApplicabilityStatus.unsatisfied, [f"已识别分包条款，但尚未形成明确转包/外包风险：{transfer}。"]


def _credit_transparency_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    credit = _first_normalized_or_content(clause_mapping, "信用评价要求")
    repair = _first_normalized_or_content(clause_mapping, "信用修复条款")
    relief = _first_normalized_or_content(clause_mapping, "异议救济条款")
    if not credit:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到信用评价要求。"]
    if not repair and not relief:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：已识别信用评价要求={credit}，但未抽取到信用修复或异议机制。"]
    return ApplicabilityStatus.unsatisfied, [f"已识别信用评价要求={credit}，且存在修复/异议机制。"]


def _procedural_fairness_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    breach = _first_normalized_or_content(clause_mapping, "违约责任")
    termination = _first_normalized_or_content(clause_mapping, "解约条款")
    rectification = _first_normalized_or_content(clause_mapping, "整改条款")
    defense = _first_normalized_or_content(clause_mapping, "申辩条款")
    if not breach and not termination:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到违约责任或解约条款。"]
    if (breach or termination) and not rectification and not defense:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：违约责任={breach or '未识别'}，解约条款={termination or '未识别'}，未见整改或申辩程序。"]
    return ApplicabilityStatus.unsatisfied, [f"已识别程序保障条款：整改={rectification or '未识别'}，申辩={defense or '未识别'}。"]


def _team_stability_requirement_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    team_raw = _first_value(clause_mapping, "团队稳定性要求")
    project_type = _first_value(clause_mapping, "项目属性")
    if not team_raw:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到团队稳定性要求。"]
    if any(token in team_raw for token in ["团队稳定", "核心团队", "人员稳定", "稳定性"]):
        if project_type:
            return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：项目属性={project_type}，团队稳定性要求={team_raw}。"]
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：团队稳定性要求={team_raw}。"]
    return ApplicabilityStatus.unsatisfied, [f"已识别团队稳定性相关条款={team_raw}，但尚未形成过强约束信号。"]


def _personnel_change_limit_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    change_raw = _first_value(clause_mapping, "人员更换限制")
    approval_raw = _first_value(clause_mapping, "采购人批准更换")
    if not change_raw and not approval_raw:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到人员更换限制。"]
    text = change_raw or approval_raw
    if any(token in text for token in ["采购人同意", "采购人批准", "须经采购人", "未经采购人同意", "不得更换"]):
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：人员更换限制={text}，限制强度较高。"]
    if change_raw:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：人员更换限制={text}。"]
    return ApplicabilityStatus.unsatisfied, [f"已识别采购人批准更换信号={text}，但尚未形成更强的人员更换限制表述。"]


def _goods_baseline_clear_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    project_type = _first_normalized_or_content(clause_mapping, "项目属性")
    procurement_subject = _first_value(clause_mapping, "采购标的")
    continuous_service = _first_normalized_or_content(clause_mapping, "是否含持续性服务")
    contract_type = _first_normalized_or_content(clause_mapping, "合同类型")
    if not project_type or not procurement_subject:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：需同时抽取项目属性和采购标的。"]
    if (
        project_type == "货物"
        and "家具" in procurement_subject
        and continuous_service != "是"
        and contract_type in {"", "采购合同"}
    ):
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：项目属性={project_type}，采购标的={procurement_subject}，未识别持续性服务，文件整体货物主线清楚。"]
    return ApplicabilityStatus.not_applicable, [f"当前未形成可排除结构错配的正向基线：项目属性={project_type or '未识别'}，采购标的={procurement_subject or '未识别'}，合同类型={contract_type or '未识别'}，持续性服务={continuous_service or '未识别'}。"]


def _contract_template_mismatch_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    template_terms = _first_value(clause_mapping, "合同成果模板术语")
    project_subject = _first_value(clause_mapping, "采购标的") or _first_value(clause_mapping, "项目属性")
    if template_terms:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：在 {project_subject or '当前项目'} 中识别到成果模板术语={template_terms}。"]
    return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到合同成果模板术语。"]


def _contract_template_residue_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    residue = _first_value(clause_mapping, "合同模板残留")
    contract_term = _first_value(clause_mapping, "合同履行期限")
    if residue:
        suffix = f" 合同履行期限={contract_term}。" if contract_term else ""
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：已识别合同模板残留={residue}。{suffix}".strip()]
    return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到合同模板残留条款。"]


def _acceptance_flexible_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    acceptance = _first_value(clause_mapping, "验收弹性条款")
    if acceptance:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：已识别验收弹性条款={acceptance}。"]
    return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到验收弹性条款。"]


def _warranty_scope_mismatch_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    project_type = _first_normalized_or_content(clause_mapping, "项目属性")
    service_flag = _first_normalized_or_content(clause_mapping, "是否含持续性服务")
    warranty_clause = _first_value(clause_mapping, "质保期")
    if not project_type or not warranty_clause:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：需同时抽取项目属性和质保/保修条款。"]
    if project_type == "货物" and service_flag == "是" and any(
        token in warranty_clause for token in ["货物质保期", "质量保修范围和保修期", "验收合格之日起计"]
    ):
        return ApplicabilityStatus.satisfied, [
            f"结构化字段关系成立：项目属性={project_type}，存在持续性服务，且质保条款仍以“{warranty_clause}”表述，合同履约条款适配性不足。"
        ]
    if project_type == "货物" and service_flag == "是":
        return ApplicabilityStatus.unsatisfied, [
            f"已识别项目属性={project_type} 且存在持续性服务，但质保条款={warranty_clause} 尚未体现典型货物保修口径。"
        ]
    return ApplicabilityStatus.unsatisfied, [
        f"结构化字段关系未成立：项目属性={project_type}，持续性服务标记={service_flag or '未识别'}，质保条款={warranty_clause}。"
    ]


def _complexity_signal_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    procurement_content = _first_value(clause_mapping, "采购内容构成")
    duration_raw = _first_value(clause_mapping, "合同履行期限")
    service_flag = _first_normalized_or_content(clause_mapping, "是否含持续性服务")
    duration = _parse_amount(duration_raw)
    complexity_reasons: list[str] = []
    if procurement_content and any(token in procurement_content for token in ["、", "及", "含", "人工", "管护", "维保", "运维", "药剂", "标识牌"]):
        complexity_reasons.append(f"采购内容构成={procurement_content}")
    if service_flag == "是":
        complexity_reasons.append("存在持续性服务")
    if duration is not None and duration >= 365:
        complexity_reasons.append(f"合同履行期限={duration_raw}")
    if complexity_reasons:
        return ApplicabilityStatus.satisfied, [f"已识别项目复杂度信号：{'；'.join(complexity_reasons)}。"]
    if procurement_content or duration_raw:
        return ApplicabilityStatus.unsatisfied, [f"已识别采购内容或履约周期，但复杂度信号不足：采购内容构成={procurement_content or '未识别'}，合同履行期限={duration_raw or '未识别'}。"]
    return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到采购内容构成或合同履行期限。"]


def _demand_survey_review_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    demand = _first_normalized_or_content(clause_mapping, "需求调查结论")
    complexity_status, complexity_detail = _complexity_signal_evaluator(clause_mapping)
    if not demand:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到需求调查结论。"]
    if demand == "不需要" and complexity_status == ApplicabilityStatus.satisfied:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：需求调查结论={demand}，且{complexity_detail[0]}"]
    if demand in {"需要", "已开展"}:
        return ApplicabilityStatus.unsatisfied, [f"已识别需求调查结论={demand}，当前不构成程序审慎性复核重点。"]
    return ApplicabilityStatus.unsatisfied, [f"需求调查结论={demand}，但当前复杂度信号不足。"]


def _expert_review_recommendation_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    expert = _first_normalized_or_content(clause_mapping, "专家论证结论")
    complexity_status, complexity_detail = _complexity_signal_evaluator(clause_mapping)
    if not expert:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：尚未抽取到专家论证结论。"]
    if expert == "不需要" and complexity_status == ApplicabilityStatus.satisfied:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：专家论证结论={expert}，且{complexity_detail[0]}"]
    if expert in {"需要", "已开展"}:
        return ApplicabilityStatus.unsatisfied, [f"已识别专家论证结论={expert}，当前不构成程序审慎性复核重点。"]
    return ApplicabilityStatus.unsatisfied, [f"专家论证结论={expert}，但当前复杂度信号不足。"]


def _parse_amount(value: str) -> float | None:
    if not value:
        return None
    cleaned = re.sub(r"[^\d.]", "", value)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _amount_consistency_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    budget_raw = _first_value(clause_mapping, "预算金额")
    max_raw = _first_value(clause_mapping, "最高限价")
    sme_raw = _first_value(clause_mapping, "面向中小企业采购金额")
    budget = _parse_amount(budget_raw)
    max_price = _parse_amount(max_raw)
    sme_amount = _parse_amount(sme_raw)
    if budget is None or max_price is None or sme_amount is None:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：需同时抽取预算金额、最高限价和面向中小企业采购金额。"]
    if sme_amount == max_price and budget != sme_amount:
        return ApplicabilityStatus.satisfied, [f"结构化金额关系成立：预算金额={budget_raw}，面向中小企业采购金额={sme_raw}，且其与最高限价={max_raw} 重合，存在口径混用疑点。"]
    if budget != sme_amount:
        return ApplicabilityStatus.unsatisfied, [f"已识别金额差异：预算金额={budget_raw}，面向中小企业采购金额={sme_raw}，但尚不足以判断与最高限价混用。"]
    return ApplicabilityStatus.unsatisfied, [f"金额关系未形成异常链：预算金额={budget_raw}，最高限价={max_raw}，面向中小企业采购金额={sme_raw}。"]


def _service_template_mismatch_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    project_type = _first_value(clause_mapping, "项目属性")
    declaration = _first_value(clause_mapping, "中小企业声明函类型")
    if project_type == "服务" and "制造商" in declaration:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：项目属性={project_type}，声明函类型={declaration}，出现服务项目套用货物模板。"]
    if not project_type or not declaration:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：需同时抽取项目属性和中小企业声明函类型。"]
    return ApplicabilityStatus.unsatisfied, [f"结构化字段关系未成立：项目属性={project_type}，声明函类型={declaration}。"]


def _goods_template_mismatch_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    project_type = _first_value(clause_mapping, "项目属性")
    declaration = _first_value(clause_mapping, "中小企业声明函类型")
    if project_type == "货物" and declaration and "制造商" not in declaration:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：项目属性={project_type}，声明函类型={declaration}，未体现制造商口径。"]
    if not project_type or not declaration:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：需同时抽取项目属性和中小企业声明函类型。"]
    return ApplicabilityStatus.unsatisfied, [f"结构化字段关系未成立：项目属性={project_type}，声明函类型={declaration}。"]


def _project_statement_conflict_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[ApplicabilityStatus, list[str]]:
    project_type = _first_value(clause_mapping, "项目属性")
    declaration = _first_value(clause_mapping, "中小企业声明函类型")
    if project_type == "服务" and declaration and "制造商" in declaration:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：服务项目对应声明函却出现制造商口径，项目属性={project_type}，声明函类型={declaration}。"]
    if project_type == "货物" and declaration and "制造商" not in declaration:
        return ApplicabilityStatus.satisfied, [f"结构化字段关系成立：货物项目声明函缺少制造商口径，项目属性={project_type}，声明函类型={declaration}。"]
    if not project_type or not declaration:
        return ApplicabilityStatus.insufficient, ["结构化字段不足：需同时抽取项目属性和中小企业声明函类型。"]
    return ApplicabilityStatus.unsatisfied, [f"结构化字段关系未成立：项目属性={project_type}，声明函类型={declaration}。"]


RELATION_EVALUATORS: dict[tuple[str, str], RelationEvaluator] = {
    ("RP-PROC-001", "存在采购方式"): _procurement_method_applicability_evaluator,
    ("RP-PROC-001", "存在非公开招标采购方式信号"): _procurement_method_applicability_evaluator,
    ("RP-PROC-001", "已说明适用理由"): _exists_relation("采购方式适用理由", "已说明适用理由"),
    ("RP-PROC-002", "存在混合采购信号"): _package_split_evaluator,
    ("RP-PROC-002", "已说明包件划分或拆分依据"): _exists_relation("采购包划分说明", "已说明包件划分或拆分依据"),
    ("RP-QUAL-001", "存在资格条件明细"): _qualification_scoring_overlap_evaluator,
    ("RP-QUAL-001", "存在评分项明细"): _qualification_scoring_overlap_evaluator,
    ("RP-QUAL-002", "存在特定资格要求"): _excessive_certificate_requirement_evaluator,
    ("RP-QUAL-002", "存在资质证书或材料负担信号"): _excessive_certificate_requirement_evaluator,
    ("RP-REQ-001", "存在技术或服务要求信号"): _technical_service_verifiability_evaluator,
    ("RP-SME-001", "项目专门面向中小企业"): _equals_relation("是否专门面向中小企业", "是", "项目专门面向中小企业"),
    ("RP-SME-001", "文件仍保留价格扣除"): _equals_relation("是否仍保留价格扣除条款", "是", "文件仍保留价格扣除"),
    ("RP-SME-002", "项目属性为服务"): _equals_relation("项目属性", "服务", "项目属性为服务"),
    ("RP-SME-002", "声明函出现制造商口径"): _contains_relation("中小企业声明函类型", "制造商", "声明函出现制造商口径"),
    ("RP-SME-003", "项目属性为货物"): _equals_relation("项目属性", "货物", "项目属性为货物"),
    ("RP-SME-003", "声明函缺少制造商口径"): _goods_template_mismatch_evaluator,
    ("RP-SME-004", "文件涉及预留份额"): _equals_relation("是否为预留份额采购", "是", "文件涉及预留份额"),
    ("RP-SME-004", "已明确比例信息"): _exists_relation("分包比例", "已明确比例信息"),
    ("RP-CONTRACT-005", "存在付款节点"): _contains_relation("付款节点", "存在", "存在付款节点"),
    ("RP-CONTRACT-005", "存在考核条款"): _payment_assessment_link_evaluator,
    ("RP-CONTRACT-008", "存在成果模板术语"): _contract_template_mismatch_evaluator,
    ("RP-CONTRACT-009", "存在验收弹性条款"): _acceptance_flexible_evaluator,
    ("RP-CONTRACT-010", "项目属性为货物"): _warranty_scope_mismatch_evaluator,
    ("RP-CONTRACT-010", "存在持续性作业服务"): _warranty_scope_mismatch_evaluator,
    ("RP-CONTRACT-010", "存在货物保修表述"): _warranty_scope_mismatch_evaluator,
    ("RP-CONTRACT-011", "存在付款节点"): _acceptance_payment_linkage_evaluator,
    ("RP-CONTRACT-011", "存在验收或考核条款"): _acceptance_payment_linkage_evaluator,
    ("RP-STRUCT-005", "存在项目属性"): _project_statement_conflict_evaluator,
    ("RP-STRUCT-005", "存在声明函类型"): _project_statement_conflict_evaluator,
    ("RP-STRUCT-007", "存在项目属性"): _contract_type_mismatch_evaluator,
    ("RP-STRUCT-007", "存在合同类型"): _contract_type_mismatch_evaluator,
    ("RP-STRUCT-007", "文件整体货物主线清楚"): _goods_baseline_clear_evaluator,
    ("RP-STRUCT-008", "项目属性为货物"): _continuous_service_in_goods_evaluator,
    ("RP-STRUCT-008", "存在持续性作业服务"): _continuous_service_in_goods_evaluator,
    ("RP-REST-004", "专利要求具有刚性门槛特征"): _rigid_patent_requirement_evaluator,
    ("RP-SCORE-005", "评分项存在行业相关性疑点"): _industry_mismatch_scoring_evaluator,
    ("RP-SCORE-006", "存在方案评分扣分模式"): _plan_scoring_quant_evaluator,
    ("RP-SCORE-007", "存在评分分档或方案扣分模式"): _subjective_scoring_evaluator,
    ("RP-SCORE-008", "存在证书报告或财务指标评分信号"): _certificate_weight_scoring_evaluator,
    ("RP-SCORE-008", "证书检测报告仅在履约或验收阶段提交"): _scoring_material_stage_exclusion_evaluator,
    ("RP-SCORE-009", "存在证书检测报告负担特征"): _bid_stage_material_burden_evaluator,
    ("RP-SCORE-009", "证书检测报告仅在履约或验收阶段提交"): _scoring_material_stage_exclusion_evaluator,
    ("RP-SCORE-010", "存在证书类评分总分"): _certificate_score_weight_value_evaluator,
    ("RP-SCORE-011", "存在信用评价评分信号"): _credit_evaluation_scoring_evaluator,
    ("RP-SCORE-011", "存在评分项明细"): _credit_evaluation_scoring_evaluator,
    ("RP-SCORE-012", "存在信用评价评分信号"): _credit_transparency_evaluator,
    ("RP-SCORE-012", "已说明信用修复或异议机制"): _credit_transparency_evaluator,
    ("RP-CONS-009", "存在预算金额"): _amount_consistency_evaluator,
    ("RP-CONS-009", "存在面向中小企业采购金额"): _amount_consistency_evaluator,
    ("RP-CONS-009", "存在最高限价"): _amount_consistency_evaluator,
    ("RP-SME-005", "存在面向中小企业采购金额"): _amount_consistency_evaluator,
    ("RP-SME-005", "存在最高限价"): _amount_consistency_evaluator,
    ("RP-TPL-002", "项目属性为服务"): _service_template_mismatch_evaluator,
    ("RP-TPL-002", "声明函出现制造商口径"): _service_template_mismatch_evaluator,
    ("RP-TPL-003", "项目专门面向中小企业"): _equals_relation("是否专门面向中小企业", "是", "项目专门面向中小企业"),
    ("RP-TPL-003", "保留价格扣除模板"): _equals_relation("是否仍保留价格扣除条款", "是", "保留价格扣除模板"),
    ("RP-TPL-007", "存在合同模板残留"): _contract_template_residue_evaluator,
    ("RP-PRUD-001", "存在需求调查结论"): _demand_survey_review_evaluator,
    ("RP-PRUD-001", "项目存在复杂度信号"): _demand_survey_review_evaluator,
    ("RP-PRUD-001", "已开展需求调查"): _equals_relation("需求调查结论", "需要", "已开展需求调查"),
    ("RP-PRUD-002", "存在专家论证结论"): _expert_review_recommendation_evaluator,
    ("RP-PRUD-002", "项目存在复杂度信号"): _expert_review_recommendation_evaluator,
    ("RP-PRUD-002", "已组织专家论证"): _equals_relation("专家论证结论", "需要", "已组织专家论证"),
    ("RP-PRUD-003", "存在违约或解约条款"): _procedural_fairness_evaluator,
    ("RP-PRUD-003", "已设置整改或申辩程序"): _procedural_fairness_evaluator,
    ("RP-CONS-003", "项目专门面向中小企业"): _equals_relation("是否专门面向中小企业", "是", "项目专门面向中小企业"),
    ("RP-CONS-003", "存在价格扣除"): _equals_relation("是否仍保留价格扣除条款", "是", "存在价格扣除"),
    ("RP-CONS-004", "存在验收标准"): _contains_relation("验收标准", "存在", "存在验收标准"),
    ("RP-CONS-004", "存在付款节点"): _contains_relation("付款节点", "存在", "存在付款节点"),
    ("RP-CONS-005", "存在中小企业政策"): _equals_relation("是否专门面向中小企业", "是", "存在中小企业政策"),
    ("RP-CONS-005", "存在分包条款"): _contains_relation("是否允许分包", "允许", "存在分包条款"),
    ("RP-CONS-007", "存在联合体条款"): _contains_relation("是否允许联合体", "允许", "存在联合体条款"),
    ("RP-CONS-007", "存在分包条款"): _contains_relation("是否允许分包", "允许", "存在分包条款"),
    ("RP-PER-009", "存在团队稳定性要求"): _team_stability_requirement_evaluator,
    ("RP-PER-010", "存在人员更换限制"): _personnel_change_limit_evaluator,
    ("RP-PER-010", "采购人批准更换"): _personnel_change_limit_evaluator,
    ("RP-CONS-010", "存在转包或外包条款"): _transfer_outsource_evaluator,
}

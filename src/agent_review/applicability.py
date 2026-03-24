from __future__ import annotations

from collections.abc import Callable

from .models import (
    ApplicabilityCheck,
    ApplicabilityItem,
    ApplicabilityStatus,
    ExtractedClause,
    ReviewPoint,
)
from .review_point_catalog import resolve_review_point_definition


RelationEvaluator = Callable[[dict[str, list[ExtractedClause]]], tuple[bool, list[str]]]


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
            matched, detail = _evaluate_condition(definition.catalog_id, condition.name, clause_mapping, haystack, condition.clause_fields, condition.signal_groups)
            status = ApplicabilityStatus.satisfied if matched else ApplicabilityStatus.insufficient
            requirement_results.append(ApplicabilityItem(name=condition.name, status=status, detail=detail))

        for condition in definition.exclusion_conditions:
            matched, detail = _evaluate_condition(definition.catalog_id, condition.name, clause_mapping, haystack, condition.clause_fields, condition.signal_groups)
            status = ApplicabilityStatus.excluded if matched else ApplicabilityStatus.not_applicable
            exclusion_results.append(ApplicabilityItem(name=condition.name, status=status, detail=detail))

        applicable = bool(
            (not requirement_results or all(item.status == ApplicabilityStatus.satisfied for item in requirement_results))
            and not any(item.status == ApplicabilityStatus.excluded for item in exclusion_results)
        )
        summary = _build_summary(requirement_results, exclusion_results, applicable)
        results.append(
            ApplicabilityCheck(
                point_id=point.point_id,
                catalog_id=definition.catalog_id,
                applicable=applicable,
                requirement_results=requirement_results,
                exclusion_results=exclusion_results,
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


def _evaluate_condition(
    catalog_id: str,
    condition_name: str,
    clause_mapping: dict[str, list[ExtractedClause]],
    haystack: str,
    clause_fields: list[str],
    signal_groups: list[list[str]],
) -> tuple[bool, str]:
    relation_match = _evaluate_relation(catalog_id, condition_name, clause_mapping)
    if relation_match is not None:
        return relation_match

    matched, matched_by_fields, matched_fields = _matches_condition(
        haystack,
        clause_mapping,
        clause_fields,
        signal_groups,
    )
    if matched:
        return True, _matched_detail("要件", matched_by_fields, matched_fields)
    return False, _unmatched_detail("要件", clause_fields)


def _evaluate_relation(
    catalog_id: str,
    condition_name: str,
    clause_mapping: dict[str, list[ExtractedClause]],
) -> tuple[bool, str] | None:
    evaluator = RELATION_EVALUATORS.get((catalog_id, condition_name))
    if evaluator is None:
        return None
    matched, details = evaluator(clause_mapping)
    return matched, "；".join(details)


def _matches_condition(
    haystack: str,
    clause_mapping: dict[str, list[ExtractedClause]],
    clause_fields: list[str],
    signal_groups: list[list[str]],
) -> tuple[bool, bool, list[str]]:
    matched_fields = [field for field in clause_fields if clause_mapping.get(field)]
    fields_ok = not clause_fields or len(matched_fields) == len(clause_fields)
    signals_ok = not signal_groups or all(any(token and token in haystack for token in group) for group in signal_groups)
    return fields_ok and signals_ok, bool(matched_fields), matched_fields


def _build_summary(
    requirement_results: list[ApplicabilityItem],
    exclusion_results: list[ApplicabilityItem],
    applicable: bool,
) -> str:
    satisfied = sum(1 for item in requirement_results if item.status == ApplicabilityStatus.satisfied)
    excluded = any(item.status == ApplicabilityStatus.excluded for item in exclusion_results)
    if applicable:
        return f"要件满足 {satisfied} 项，未命中排除条件，可进入 formal 适法性判断。"
    if excluded:
        return "已命中排除条件，当前审查点不宜直接 formal 定性。"
    if requirement_results:
        return f"当前仅满足 {satisfied}/{len(requirement_results)} 项要件，需补充证据或人工确认。"
    return "当前目录项尚未配置细化要件，暂按通用审查点处理。"


def _clause_map(clauses: list[ExtractedClause]) -> dict[str, list[ExtractedClause]]:
    mapping: dict[str, list[ExtractedClause]] = {}
    for clause in clauses:
        mapping.setdefault(clause.field_name, []).append(clause)
    return mapping


def _matched_detail(prefix: str, matched_by_fields: bool, matched_fields: list[str]) -> str:
    if matched_by_fields and matched_fields:
        return f"已通过结构化字段命中该{prefix}：{', '.join(matched_fields)}。"
    return f"已在当前审查点证据或理由中定位到该{prefix}信号。"


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


def _collect_tags(clause_mapping: dict[str, list[ExtractedClause]], field_name: str) -> set[str]:
    tags: set[str] = set()
    for clause in clause_mapping.get(field_name, []):
        tags.update(clause.relation_tags)
    return tags


def _equals_relation(field_name: str, expected_value: str, label: str) -> RelationEvaluator:
    def evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[bool, list[str]]:
        actual = _first_value(clause_mapping, field_name)
        if actual == expected_value:
            return True, [f"结构化字段关系成立：{field_name}={actual}，满足{label}。"]
        if not actual:
            return False, [f"结构化字段缺失：{field_name}。"]
        return False, [f"结构化字段关系未成立：{field_name}={actual}，不满足{label}。"]

    return evaluator


def _contains_relation(field_name: str, expected_fragment: str, label: str) -> RelationEvaluator:
    def evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[bool, list[str]]:
        actual = _first_value(clause_mapping, field_name)
        if actual and expected_fragment in actual:
            return True, [f"结构化字段关系成立：{field_name} 包含 {expected_fragment}，满足{label}。"]
        if not actual:
            return False, [f"结构化字段缺失：{field_name}。"]
        return False, [f"结构化字段关系未成立：{field_name}={actual}，未体现{expected_fragment}。"]

    return evaluator


def _missing_relation(field_name: str, label: str) -> RelationEvaluator:
    def evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[bool, list[str]]:
        actual = _first_value(clause_mapping, field_name)
        if not actual:
            return True, [f"结构化字段关系成立：{field_name} 缺失，符合{label}。"]
        return False, [f"结构化字段关系未成立：{field_name} 已抽取为 {actual}。"]

    return evaluator


def _exists_relation(field_name: str, label: str) -> RelationEvaluator:
    def evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[bool, list[str]]:
        actual = _first_value(clause_mapping, field_name)
        if actual:
            return True, [f"结构化字段关系成立：{field_name}={actual}，满足{label}。"]
        return False, [f"结构化字段缺失：{field_name}。"]

    return evaluator


def _payment_assessment_link_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[bool, list[str]]:
    payment_value = _first_value(clause_mapping, "付款节点")
    payment_tags = _collect_tags(clause_mapping, "付款节点")
    assessment_value = _first_value(clause_mapping, "考核条款")
    assessment_tags = _collect_tags(clause_mapping, "考核条款")
    if payment_value and assessment_value and (
        "考核联动" in payment_tags or "关联付款" in assessment_tags or "尾款" in payment_tags
    ):
        return True, [f"结构化字段关系成立：付款节点={payment_value}，考核条款={assessment_value}，且存在尾款/考核联动。"]
    if not payment_value or not assessment_value:
        return False, ["结构化字段不足：需同时抽取付款节点和考核条款。"]
    return False, [f"已抽取付款节点与考核条款，但尚未识别尾款/付款联动标签：付款标签={sorted(payment_tags)}，考核标签={sorted(assessment_tags)}。"]


def _service_template_mismatch_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[bool, list[str]]:
    project_type = _first_value(clause_mapping, "项目属性")
    declaration = _first_value(clause_mapping, "中小企业声明函类型")
    if project_type == "服务" and "制造商" in declaration:
        return True, [f"结构化字段关系成立：项目属性={project_type}，声明函类型={declaration}，出现服务项目套用货物模板。"]
    if not project_type or not declaration:
        return False, ["结构化字段不足：需同时抽取项目属性和中小企业声明函类型。"]
    return False, [f"结构化字段关系未成立：项目属性={project_type}，声明函类型={declaration}。"]


def _goods_template_mismatch_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[bool, list[str]]:
    project_type = _first_value(clause_mapping, "项目属性")
    declaration = _first_value(clause_mapping, "中小企业声明函类型")
    if project_type == "货物" and declaration and "制造商" not in declaration:
        return True, [f"结构化字段关系成立：项目属性={project_type}，声明函类型={declaration}，未体现制造商口径。"]
    if not project_type or not declaration:
        return False, ["结构化字段不足：需同时抽取项目属性和中小企业声明函类型。"]
    return False, [f"结构化字段关系未成立：项目属性={project_type}，声明函类型={declaration}。"]


def _project_statement_conflict_evaluator(clause_mapping: dict[str, list[ExtractedClause]]) -> tuple[bool, list[str]]:
    project_type = _first_value(clause_mapping, "项目属性")
    declaration = _first_value(clause_mapping, "中小企业声明函类型")
    if project_type == "服务" and declaration and "制造商" in declaration:
        return True, [f"结构化字段关系成立：服务项目对应声明函却出现制造商口径，项目属性={project_type}，声明函类型={declaration}。"]
    if project_type == "货物" and declaration and "制造商" not in declaration:
        return True, [f"结构化字段关系成立：货物项目声明函缺少制造商口径，项目属性={project_type}，声明函类型={declaration}。"]
    if not project_type or not declaration:
        return False, ["结构化字段不足：需同时抽取项目属性和中小企业声明函类型。"]
    return False, [f"结构化字段关系未成立：项目属性={project_type}，声明函类型={declaration}。"]


RELATION_EVALUATORS: dict[tuple[str, str], RelationEvaluator] = {
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
    ("RP-STRUCT-005", "存在项目属性"): _project_statement_conflict_evaluator,
    ("RP-STRUCT-005", "存在声明函类型"): _project_statement_conflict_evaluator,
    ("RP-TPL-002", "项目属性为服务"): _service_template_mismatch_evaluator,
    ("RP-TPL-002", "声明函出现制造商口径"): _service_template_mismatch_evaluator,
    ("RP-TPL-003", "项目专门面向中小企业"): _equals_relation("是否专门面向中小企业", "是", "项目专门面向中小企业"),
    ("RP-TPL-003", "保留价格扣除模板"): _equals_relation("是否仍保留价格扣除条款", "是", "保留价格扣除模板"),
    ("RP-CONS-003", "项目专门面向中小企业"): _equals_relation("是否专门面向中小企业", "是", "项目专门面向中小企业"),
    ("RP-CONS-003", "存在价格扣除"): _equals_relation("是否仍保留价格扣除条款", "是", "存在价格扣除"),
    ("RP-CONS-004", "存在验收标准"): _contains_relation("验收标准", "存在", "存在验收标准"),
    ("RP-CONS-004", "存在付款节点"): _contains_relation("付款节点", "存在", "存在付款节点"),
    ("RP-CONS-005", "存在中小企业政策"): _equals_relation("是否专门面向中小企业", "是", "存在中小企业政策"),
    ("RP-CONS-005", "存在分包条款"): _contains_relation("是否允许分包", "允许", "存在分包条款"),
    ("RP-CONS-007", "存在联合体条款"): _contains_relation("是否允许联合体", "允许", "存在联合体条款"),
    ("RP-CONS-007", "存在分包条款"): _contains_relation("是否允许分包", "允许", "存在分包条款"),
}

from __future__ import annotations

from ..fact_collectors import collect_task_facts, enhance_dynamic_task_evidence
from ..models import (
    ExtractedClause,
    ReviewPoint,
    ReviewPointCondition,
    ReviewPointDefinition,
    Severity,
)


def parse_dynamic_review_tasks(raw_items: object) -> list[ReviewPointDefinition]:
    if not isinstance(raw_items, list):
        return []
    results: list[ReviewPointDefinition] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        task_type = _parse_task_type(item, title, str(item.get("dimension", "")).strip())
        dimension = str(item.get("dimension", "")).strip() or _infer_dimension_from_task_type(task_type)
        if not title or not dimension:
            continue
        catalog_id = str(item.get("catalog_id", "")).strip() or f"RP-DYN-{index:03d}"
        focus_fields = [
            str(value).strip()
            for value in item.get("focus_fields", [])
            if str(value).strip()
        ]
        defaults = _default_dynamic_task_config(task_type, title)
        focus_fields = list(dict.fromkeys([*focus_fields, *defaults["focus_fields"]]))
        signal_groups = []
        for group in item.get("signal_groups", []):
            if not isinstance(group, list):
                continue
            cleaned = [str(value).strip() for value in group if str(value).strip()]
            if cleaned:
                signal_groups.append(cleaned)
        signal_groups.extend(group for group in defaults["signal_groups"] if group not in signal_groups)
        rebuttal_templates = []
        for group in item.get("rebuttal_templates", []):
            if not isinstance(group, list):
                continue
            cleaned = [str(value).strip() for value in group if str(value).strip()]
            if cleaned:
                rebuttal_templates.append(cleaned)
        rebuttal_templates.extend(
            group for group in defaults["rebuttal_templates"] if group not in rebuttal_templates
        )

        required_conditions: list[ReviewPointCondition] = []
        if focus_fields:
            required_conditions.append(
                ReviewPointCondition(
                    name="存在关键结构化字段",
                    clause_fields=focus_fields,
                    signal_groups=[],
                )
            )
        for signal_index, group in enumerate(signal_groups, start=1):
            required_conditions.append(
                ReviewPointCondition(
                    name=f"命中场景信号{signal_index}",
                    clause_fields=[],
                    signal_groups=[group],
                )
            )
        if not required_conditions:
            continue

        results.append(
            ReviewPointDefinition(
                catalog_id=catalog_id,
                title=title,
                dimension=dimension,
                default_severity=_parse_severity(item.get("severity")),
                task_type=task_type,
                scenario_tags=[
                    str(value).strip()
                    for value in item.get("scenario_tags", [])
                    if str(value).strip()
                ] or defaults["scenario_tags"],
                required_conditions=required_conditions,
                exclusion_conditions=[],
                evidence_hints=list(
                    dict.fromkeys(
                        [
                            *[
                                str(value).strip()
                                for value in item.get("evidence_hints", [])
                                if str(value).strip()
                            ],
                            *defaults["evidence_hints"],
                        ]
                    )
                ),
                rebuttal_templates=rebuttal_templates,
                enhancement_fields=list(
                    dict.fromkeys(
                        [
                            *[
                                str(value).strip()
                                for value in item.get("enhancement_fields", [])
                                if str(value).strip()
                            ],
                            *defaults["enhancement_fields"],
                        ]
                    )
                ),
                basis_hint=str(item.get("basis_hint", "")).strip() or defaults["basis_hint"],
            )
        )
    return results


def _default_dynamic_task_config(task_type: str, title: str) -> dict[str, object]:
    config = {
        "focus_fields": [],
        "signal_groups": [],
        "rebuttal_templates": [],
        "evidence_hints": [],
        "enhancement_fields": [],
        "scenario_tags": [task_type] if task_type != "generic" else [],
        "basis_hint": "",
    }
    if task_type == "structure":
        config.update(
            {
                "focus_fields": ["项目属性", "采购标的", "采购内容构成", "是否含持续性服务", "合同类型", "合同履行期限"],
                "signal_groups": [["货物", "服务", "承揽合同"], ["人工管护", "安装", "运维", "抚育"]],
                "rebuttal_templates": [["仅供货", "不含服务"], ["买卖合同", "采购合同"]],
                "evidence_hints": ["优先采集项目属性、采购内容、合同类型、履约周期条款。"],
                "enhancement_fields": ["项目属性", "采购标的", "采购内容构成", "合同类型", "合同履行期限"],
                "basis_hint": "应核查项目属性、采购内容结构和合同类型是否形成一致法律关系。",
            }
        )
    elif task_type == "scoring":
        config.update(
            {
                "focus_fields": ["评分方法", "评分项明细", "方案评分扣分模式", "证书类评分总分", "证书检测报告负担特征", "预算金额"],
                "signal_groups": [["完全满足且优于", "不完全满足"], ["资质证书", "管理体系认证", "检测报告", "财务指标"]],
                "rebuttal_templates": [["仅履约阶段提供", "验收时提供"], ["仅作辅助说明", "不计分"]],
                "evidence_hints": ["优先采集评分项名称、分值、分档表述、材料提交阶段和预算金额。"],
                "enhancement_fields": ["评分项明细", "评分方法", "方案评分扣分模式", "证书类评分总分", "证书材料适用阶段", "检测报告适用阶段", "预算金额"],
                "basis_hint": "应复核评分项相关性、量化充分性和证书检测材料权重是否超过必要限度。",
            }
        )
    elif task_type == "contract":
        config.update(
            {
                "focus_fields": ["合同类型", "付款节点", "验收标准", "争议解决方式", "单方解释权", "合同模板残留"],
                "signal_groups": [["以采购人意见为准", "解释权"], ["优胜的原则", "验收标准"]],
                "rebuttal_templates": [["协商解决", "第三方鉴定"], ["按合同约定", "按国家标准"]],
                "evidence_hints": ["优先采集合同类型、争议解决、付款、验收和模板残留条款。"],
                "enhancement_fields": ["合同类型", "付款节点", "验收标准", "争议解决方式", "单方解释权", "合同模板残留", "验收弹性条款"],
                "basis_hint": "应复核合同条款是否失衡、模板是否残留，以及是否影响履约和争议处理。",
            }
        )
    elif task_type == "policy":
        config.update(
            {
                "focus_fields": ["是否专门面向中小企业", "中小企业声明函类型", "是否仍保留价格扣除条款", "面向中小企业采购金额", "最高限价"],
                "signal_groups": [["专门面向中小企业", "价格扣除"], ["声明函", "中小企业采购金额"]],
                "rebuttal_templates": [["非专门面向", "预留份额"], ["仅资格说明", "不参与评标"]],
                "evidence_hints": ["优先采集中小企业政策路径、声明函模板、价格扣除和金额口径。"],
                "enhancement_fields": ["是否专门面向中小企业", "中小企业声明函类型", "是否仍保留价格扣除条款", "面向中小企业采购金额", "最高限价", "预算金额"],
                "basis_hint": "应复核中小企业政策路径、声明函模板和金额口径是否闭合一致。",
            }
        )
    elif task_type == "template":
        config.update(
            {
                "focus_fields": ["合同模板残留", "合同成果模板术语", "合同类型"],
                "signal_groups": [["X年", "事件发生后"], ["设计", "测试", "成果"]],
                "rebuttal_templates": [["已明确替换", "与项目一致"], ["仅示例文本"]],
                "evidence_hints": ["优先采集合同和投标格式中的占位符、旧行业术语和成果模板术语。"],
                "enhancement_fields": ["合同模板残留", "合同成果模板术语", "合同类型"],
                "basis_hint": "应复核合同和模板文本是否保留旧行业术语、空白占位或不可执行表达。",
            }
        )
    elif task_type == "consistency":
        config.update(
            {
                "focus_fields": ["项目属性", "合同类型", "验收标准", "付款节点", "预算金额", "最高限价", "面向中小企业采购金额"],
                "signal_groups": [["预算金额", "最高限价"], ["项目属性", "合同类型"]],
                "rebuttal_templates": [["上下文已澄清", "补充条款已说明"]],
                "evidence_hints": ["优先采集前后条款冲突、金额口径关系和项目属性/合同类型关系。"],
                "enhancement_fields": ["项目属性", "合同类型", "验收标准", "付款节点", "预算金额", "最高限价", "面向中小企业采购金额"],
                "basis_hint": "应复核跨章节、跨金额字段和跨合同结构的一致性。",
            }
        )
    if "需求调查" in title or "专家论证" in title:
        config["focus_fields"] = list(dict.fromkeys([*config["focus_fields"], "需求调查结论", "专家论证结论", "预算金额", "合同履行期限", "采购内容构成"]))
        config["evidence_hints"] = list(dict.fromkeys([*config["evidence_hints"], "优先采集需求调查、专家论证、项目复杂度和履约周期条款。"]))
        config["enhancement_fields"] = list(dict.fromkeys([*config["enhancement_fields"], "需求调查结论", "专家论证结论", "预算金额", "合同履行期限", "采购内容构成"]))
        config["basis_hint"] = str(config["basis_hint"] or "应复核项目复杂度、程序要求与需求调查或专家论证结论是否匹配。")
    return config


def _infer_dimension_from_task_type(task_type: str) -> str:
    mapping = {
        "structure": "C.项目属性错配风险",
        "scoring": "评审标准明确性",
        "contract": "合同与履约风险",
        "template": "模板残留与冲突风险",
        "policy": "中小企业政策风险",
        "restrictive": "A.限制竞争风险",
        "personnel": "人员条件与用工边界风险",
        "consistency": "跨条款一致性检查",
        "generic": "综合风险复核",
    }
    return mapping.get(task_type, "综合风险复核")


def build_dynamic_review_points(
    definitions: list[ReviewPointDefinition],
    extracted_clauses: list[ExtractedClause],
) -> list[ReviewPoint]:
    review_points: list[ReviewPoint] = []
    for index, definition in enumerate(definitions, start=1):
        evidence_bundle, status, rationale = collect_task_facts(definition, extracted_clauses)
        evidence_bundle, status, rationale = enhance_dynamic_task_evidence(
            definition,
            extracted_clauses,
            evidence_bundle,
            status,
            rationale,
        )
        review_points.append(
            ReviewPoint(
                point_id=f"DYN-{index:03d}",
                catalog_id=definition.catalog_id,
                title=definition.title,
                dimension=definition.dimension,
                severity=definition.default_severity,
                status=status,
                rationale=rationale or "LLM 场景识别建议新增该审查任务，待结合结构化事实进一步核定。",
                evidence_bundle=evidence_bundle,
                legal_basis=[],
                source_findings=[f"task_library:{definition.catalog_id}"],
            )
        )
    return review_points


def _parse_severity(raw_value: object) -> Severity:
    value = str(raw_value or "").strip().lower()
    if value == "critical":
        return Severity.critical
    if value == "high":
        return Severity.high
    if value == "low":
        return Severity.low
    return Severity.medium


def _parse_task_type(item: dict[str, object], title: str, dimension: str) -> str:
    value = str(item.get("task_type", "")).strip().lower()
    allowed = {
        "structure",
        "scoring",
        "contract",
        "template",
        "policy",
        "restrictive",
        "personnel",
        "consistency",
        "generic",
    }
    if value in allowed:
        return value
    haystack = f"{title} {dimension}".lower()
    if "结构" in haystack or "属性" in haystack:
        return "structure"
    if "评分" in haystack or "评审" in haystack:
        return "scoring"
    if "合同" in haystack or "付款" in haystack or "验收" in haystack:
        return "contract"
    if "模板" in haystack:
        return "template"
    if "中小企业" in haystack or "政策" in haystack:
        return "policy"
    if "限制竞争" in haystack or "品牌" in haystack:
        return "restrictive"
    if "人员" in haystack or "用工" in haystack:
        return "personnel"
    if "一致性" in haystack or "冲突" in haystack:
        return "consistency"
    return "generic"

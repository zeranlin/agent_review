from __future__ import annotations

import re
from collections.abc import Callable

from ..legal_semantics import infer_clause_constraint, infer_legal_effect, infer_legal_principle_tags
from ..models import AdoptionStatus, ClauseRole, ClauseUnit, ExtractedClause
from ..ontology import ClauseSemanticType, EffectTag, LegalEffectType, SemanticZoneType


ClauseExtractor = Callable[[list[str]], ExtractedClause | None]


def extract_clauses(text: str, field_names: set[str] | None = None) -> list[ExtractedClause]:
    lines = text.splitlines()
    clauses: list[ExtractedClause] = []
    for category, field_name, extractor in FIELD_EXTRACTORS:
        if field_names is not None and field_name not in field_names:
            continue
        clause = extractor(lines)
        if clause is None:
            continue
        clauses.append(
            _enrich_extracted_clause(
                ExtractedClause(
                    category=category,
                    field_name=field_name,
                    content=clause.content,
                    source_anchor=clause.source_anchor,
                    normalized_value=clause.normalized_value,
                    relation_tags=clause.relation_tags,
                    clause_role=classify_clause_role(clause.content),
                    semantic_zone=SemanticZoneType.mixed_or_uncertain,
                    effect_tags=[],
                )
            )
        )
    return clauses


def extract_clauses_from_units(
    clause_units: list[ClauseUnit],
    field_names: set[str] | None = None,
    target_zones: set[str] | None = None,
) -> list[ExtractedClause]:
    filtered_units = [
        unit
        for unit in clause_units
        if unit.zone_type
        in {
            SemanticZoneType.administrative_info,
            SemanticZoneType.qualification,
            SemanticZoneType.technical,
            SemanticZoneType.business,
            SemanticZoneType.scoring,
            SemanticZoneType.contract,
            SemanticZoneType.policy_explanation,
            SemanticZoneType.appendix_reference,
        }
        and EffectTag.catalog not in unit.effect_tags
        and EffectTag.public_copy_noise not in unit.effect_tags
        and (target_zones is None or unit.zone_type.value in target_zones)
    ]
    if not filtered_units:
        return []

    unit_clauses = []
    for unit in filtered_units:
        if not unit.text.strip():
            continue
        clause = _clause_from_unit(unit)
        if field_names is not None and clause.field_name not in field_names:
            continue
        unit_clauses.append(clause)
    synthetic_text = "\n".join(unit.text for unit in filtered_units if unit.text.strip())
    fallback_clauses = extract_clauses(synthetic_text, field_names=field_names)
    return _merge_extracted_clauses(unit_clauses, fallback_clauses)


def classify_extracted_clauses(clauses: list[ExtractedClause]) -> list[ExtractedClause]:
    for clause in clauses:
        clause.clause_role = classify_clause_role(clause.content)
        _enrich_extracted_clause(clause)
    return clauses


def _anchor_to_hint(unit: ClauseUnit) -> str:
    anchor = unit.anchor
    if anchor.line_hint:
        return anchor.line_hint
    if anchor.table_no is not None and anchor.row_no is not None:
        return f"table:{anchor.table_no}:row:{anchor.row_no}"
    if anchor.paragraph_no is not None:
        return f"paragraph:{anchor.paragraph_no}"
    if anchor.block_no is not None:
        return f"block:{anchor.block_no}"
    return unit.path or unit.source_node_id


def _clause_from_unit(unit: ClauseUnit) -> ExtractedClause:
    field_name = _infer_unit_field_name(unit)
    content = unit.text.strip()
    return ExtractedClause(
        category=_infer_unit_category(unit, field_name),
        field_name=field_name,
        content=content,
        source_anchor=unit.anchor.line_hint or _anchor_to_hint(unit),
        normalized_value=_infer_unit_normalized_value(unit, field_name),
        relation_tags=_infer_unit_relation_tags(unit, field_name),
        clause_role=classify_clause_role(content),
        semantic_zone=unit.zone_type,
        effect_tags=list(unit.effect_tags),
        adoption_status=AdoptionStatus.rule_based,
        legal_effect_type=unit.legal_effect_type,
        legal_principle_tags=list(unit.legal_principle_tags),
        clause_constraint=unit.clause_constraint,
    )


def _infer_unit_category(unit: ClauseUnit, field_name: str) -> str:
    if field_name in {"项目名称", "项目编号", "采购人", "采购单位", "采购代理机构", "采购方式", "采购方式适用理由", "采购标的", "品目名称", "项目属性", "预算金额", "最高限价", "合同履行期限", "合同类型", "采购内容构成", "是否含持续性服务", "采购包数量", "采购包划分说明", "需求调查结论", "专家论证结论"}:
        return "项目基本信息"
    if field_name in {"一般资格要求", "特定资格要求", "资格条件明细", "资格门槛明细", "信用要求", "是否允许联合体", "是否允许分包"}:
        return "资格条款"
    if field_name in {"样品要求", "现场演示要求", "是否指定品牌", "是否要求专利", "是否要求检测报告", "是否要求认证证书", "证书检测报告负担特征", "检测报告适用阶段", "证书材料适用阶段", "是否设置★实质性条款", "是否有限制产地厂家商标", "技术服务可验证性信号", "证明来源要求"}:
        return "技术条款"
    if field_name in {"评分方法", "价格分", "技术分", "商务分", "证书加分", "业绩加分", "方案评分", "售后加分", "财务指标加分", "人员评分要求", "样品分", "评分项明细", "证书类评分总分", "信用评价要求", "信用修复条款", "异议救济条款", "行业相关性存疑评分项", "方案评分扣分模式"}:
        return "评分条款"
    if field_name in {"付款节点", "验收标准", "争议解决方式", "违约责任", "质保期", "履约保证金", "考核条款", "满意度条款", "扣款条款", "解约条款", "整改条款", "申辩条款", "单方解释权", "合同成果模板术语", "合同模板残留", "验收弹性条款", "转包外包条款"}:
        return "合同条款"
    if field_name in {"性别限制", "年龄限制", "身高限制", "容貌体形要求", "学历职称要求", "采购人审批录用", "采购人批准更换", "团队稳定性要求", "人员更换限制", "采购人直接指挥"}:
        return "人员条款"
    if field_name in {"是否专门面向中小企业", "是否为预留份额采购", "是否允许分包落实中小企业政策", "所属行业划分", "中小企业声明函类型", "是否仍保留价格扣除条款", "是否涉及进口产品", "分包比例", "面向中小企业采购金额"}:
        return "政策条款"
    if field_name in {"投标文件格式", "附件引用"}:
        return "投标文件模板"
    return {
        SemanticZoneType.administrative_info: "项目基本信息",
        SemanticZoneType.qualification: "资格条款",
        SemanticZoneType.technical: "技术条款",
        SemanticZoneType.business: "商务条款",
        SemanticZoneType.scoring: "评分条款",
        SemanticZoneType.contract: "合同条款",
        SemanticZoneType.policy_explanation: "政策条款",
        SemanticZoneType.appendix_reference: "附件引用",
        SemanticZoneType.template: "投标文件模板",
        SemanticZoneType.catalog_or_navigation: "目录导航",
        SemanticZoneType.public_copy_or_noise: "公开噪声",
        SemanticZoneType.mixed_or_uncertain: "未分类",
    }.get(unit.zone_type, "未分类")


def _infer_unit_field_name(unit: ClauseUnit) -> str:
    text = _unit_text_context(unit)
    title = str(unit.table_context.get("title", "")).strip()
    row_label = str(unit.table_context.get("row_label", "")).strip()
    clause_type = unit.clause_semantic_type

    if clause_type in {ClauseSemanticType.declaration_template, ClauseSemanticType.template_instruction}:
        if "中小企业声明函" in text:
            return "中小企业声明函类型"
        return "投标文件格式"
    if clause_type == ClauseSemanticType.reference_clause:
        return "附件引用"
    if clause_type == ClauseSemanticType.catalog_clause:
        return "目录导航"
    if clause_type == ClauseSemanticType.noise_clause:
        return "公开噪声"

    if unit.zone_type == SemanticZoneType.administrative_info:
        if "项目名称" in text:
            return "项目名称"
        if "项目编号" in text:
            return "项目编号"
        if "采购代理机构" in text:
            return "采购代理机构"
        if "采购单位" in text:
            return "采购单位"
        if "采购人" in text:
            return "采购人"
        if "采购方式" in text:
            return "采购方式适用理由" if any(token in text for token in ["理由", "适用理由"]) else "采购方式"
        if any(token in text for token in ["采购标的", "采购内容", "采购需求"]):
            return "采购标的"
        if "品目名称" in text:
            return "品目名称"
        if "项目属性" in text:
            return "项目属性"
        if "预算金额" in text:
            return "预算金额"
        if "最高限价" in text:
            return "最高限价"
        if "合同履行期限" in text:
            return "合同履行期限"
        if any(token in text for token in ["采购包数量", "第1包", "第2包", "包组"]):
            return "采购包数量"
        if any(token in text for token in ["采购包划分", "不划分采购包", "不分包采购", "划分采购包"]):
            return "采购包划分说明"
        if "需求调查" in text:
            return "需求调查结论"
        if "专家论证" in text:
            return "专家论证结论"

    if unit.zone_type == SemanticZoneType.qualification:
        if "特定资格要求" in text or "资质要求" in text:
            return "特定资格要求"
        if any(token in text for token in ["投标人资格要求", "供应商资格", "一般资格要求", "资格要求"]):
            return "一般资格要求"
        if any(
            token in text
            for token in [
                "科技型中小企业",
                "高新技术企业",
                "纳税信用",
                "成立满",
                "同类项目业绩",
                "业绩不少于",
            ]
        ):
            return "资格门槛明细"
        if any(
            token in text
            for token in ["资质证书", "认证证书", "管理体系认证", "检测报告", "业绩要求", "项目负责人", "项目经理", "项目主管", "保安服务许可证", "职称证书", "信用评价", "信用等级"]
        ):
            return "资格条件明细"

    if unit.zone_type == SemanticZoneType.technical:
        if "样品" in text:
            return "样品要求"
        if "演示" in text:
            return "现场演示要求"
        if "专利" in text:
            return "是否要求专利"
        if any(token in text for token in ["检测中心", "检测机构", "实验室"]) and any(token in text for token in ["出具", "提供"]):
            return "证明来源要求"
        if any(token in text for token in ["检测报告", "认证证书", "证书", "管理体系认证"]):
            return "是否要求检测报告" if "检测报告" in text else "是否要求认证证书"
        if "★" in text:
            return "是否设置★实质性条款"
        if any(token in text for token in ["产地", "厂家", "商标", "品牌", "原厂"]):
            return "是否有限制产地厂家商标"
        if any(token in text for token in ["高质量完成", "满足采购人要求", "由采购人认定", "按行业标准", "优质服务"]):
            return "技术服务可验证性信号"

    if unit.zone_type == SemanticZoneType.scoring:
        if any(token in text for token in ["评分方法", "综合评分", "评标办法"]):
            return "评分方法"
        if any(token in text for token in ["评分项", "评分标准"]):
            return "评分项明细"
        if any(token in text for token in ["检测报告", "认证证书", "资质证书", "管理体系认证", "软件企业认定证书", "ITSS"]):
            return "行业相关性存疑评分项"
        if any(token in text for token in ["财务", "利润率", "营业收入", "注册资本", "资产规模"]):
            return "财务指标加分"
        if any(token in text for token in ["项目负责人", "人员配置", "社保", "学历", "职称", "业绩"]):
            return "人员评分要求"
        if any(token in text for token in ["信用评价", "信用分", "信用等级", "征信"]):
            return "信用评价要求"
        if any(token in text for token in ["方案", "缺陷", "扣分", "无缺陷得满分", "每缺项扣", "每处缺陷扣"]):
            return "方案评分扣分模式"
        if any(token in text for token in ["证书总分", "证书类评分总分", "检测报告总分"]):
            return "证书类评分总分"

    if unit.zone_type == SemanticZoneType.business:
        if any(token in text for token in ["采购内容", "供货", "安装", "驻场", "运维"]):
            return "采购内容构成"
        if any(token in text for token in ["持续性服务", "长期服务", "驻场"]):
            return "是否含持续性服务"
        if "商务要求" in text:
            return "商务要求"

    if unit.zone_type == SemanticZoneType.contract:
        if any(token in text for token in ["付款", "支付", "尾款"]):
            return "付款节点"
        if "验收" in text:
            return "验收标准"
        if "考核" in text:
            return "考核条款"
        if "满意度" in text:
            return "满意度条款"
        if any(token in text for token in ["扣款", "扣罚", "罚款"]):
            return "扣款条款"
        if any(token in text for token in ["解除合同", "解约", "解除"]):
            return "解约条款"
        if "违约" in text:
            return "违约责任"
        if "质保" in text or "保修" in text:
            return "质保期"
        if "履约保证金" in text:
            return "履约保证金"
        if any(token in text for token in ["整改", "限期改正"]):
            return "整改条款"
        if any(token in text for token in ["申辩", "陈述意见", "说明理由"]):
            return "申辩条款"
        if any(token in text for token in ["解释权", "采购人意见为准", "采购人解释"]):
            return "单方解释权"
        if any(token in text for token in ["转包", "外包", "分包"]):
            return "转包外包条款"

    if unit.zone_type == SemanticZoneType.policy_explanation:
        if "价格扣除比例及采购标的所属行业的说明" in text:
            return "所属行业划分"
        if "中小企业声明函" in text:
            return "中小企业声明函类型"
        if "专门面向中小企业" in text:
            return "是否专门面向中小企业"
        if "价格扣除" in text:
            return "是否仍保留价格扣除条款"
        if "预留份额" in text:
            return "是否为预留份额采购"
        if "所属行业" in text:
            return "所属行业划分"
        if "分包比例" in text or "预留比例" in text or "小微企业比例" in text:
            return "分包比例"
        if "面向中小企业采购金额" in text:
            return "面向中小企业采购金额"
        if "是否允许分包" in text:
            return "是否允许分包落实中小企业政策"
        if "进口产品" in text:
            return "是否涉及进口产品"

    if unit.zone_type == SemanticZoneType.qualification and "采购方式" in title and "资格" in text:
        return "一般资格要求"
    if row_label and row_label not in {"评分项", "分值", "评分标准"}:
        if unit.zone_type == SemanticZoneType.scoring and any(token in text for token in ["分值", "得分"]):
            return "评分项明细"
        if unit.zone_type == SemanticZoneType.qualification:
            return "资格条件明细"
        if unit.zone_type == SemanticZoneType.contract:
            return "合同条款"
        if unit.zone_type == SemanticZoneType.business:
            return "商务要求"
        if unit.zone_type == SemanticZoneType.technical:
            return "技术要求"

    if title and len(title) <= 60:
        if unit.zone_type == SemanticZoneType.scoring:
            if any(token in title for token in ["评分办法", "综合评分", "评标办法"]):
                return "评分方法"
            if any(token in title for token in ["评分项", "评分标准"]):
                return "评分项明细"
        if unit.zone_type == SemanticZoneType.contract and "合同条款" in title:
            return "合同条款"
        if unit.zone_type == SemanticZoneType.qualification and any(token in title for token in ["投标人资格", "供应商资格", "资格要求"]):
            return "一般资格要求"
        if unit.zone_type == SemanticZoneType.business and any(token in title for token in ["商务要求", "商务部分"]):
            return "商务要求"
        if unit.zone_type == SemanticZoneType.administrative_info:
            if "采购代理机构" in title:
                return "采购代理机构"
            if "采购单位" in title:
                return "采购单位"
            if "采购人" in title:
                return "采购人"
            if "项目属性" in title:
                return "项目属性"
            if "采购方式" in title:
                return "采购方式"
            if "采购内容" in title or "采购需求" in title:
                return "采购标的"
            if "预算金额" in title:
                return "预算金额"
            if "最高限价" in title:
                return "最高限价"
            if "合同履行期限" in title:
                return "合同履行期限"
    return ""


def _infer_unit_normalized_value(unit: ClauseUnit, field_name: str) -> str:
    text = _unit_text_context(unit)
    if not text:
        return ""
    conditional_context = unit.conditional_context or {}
    if field_name in {"项目属性"}:
        for token in ["货物", "服务", "工程"]:
            if token in text:
                return token
    if field_name in {"采购方式"}:
        for token in ["公开招标", "竞争性磋商", "竞争性谈判", "单一来源", "询价", "框架协议"]:
            if token in text:
                return token
    if field_name in {"是否专门面向中小企业", "是否仍保留价格扣除条款", "是否为预留份额采购", "是否涉及进口产品", "是否允许分包落实中小企业政策"}:
        if conditional_context.get("conditional_policy") == "true" and conditional_context.get("project_binding") != "true":
            return ""
        if field_name == "是否专门面向中小企业" and "非专门面向中小企业" in text:
            return "否"
        if any(token in text for token in ["不适用", "不再适用", "不执行", "否"]):
            return "否"
        if any(token in text for token in ["是", "专门面向", "预留份额", "价格扣除", "进口产品", "允许分包"]):
            return "是"
    if field_name in {"预算金额", "最高限价", "面向中小企业采购金额", "分包比例"}:
        matches = re.findall(r"\d[\d,]*(?:\.\d+)?", text)
        if matches:
            value = max(matches, key=lambda token: (len(token.replace(",", "")), "." in token)).replace(",", "")
            return f"{value}%" if "比例" in field_name or "%" in text else value
    if field_name == "采购包数量":
        match = re.search(r"(\d+)", text)
        if match:
            return match.group(1)
    if field_name in {"是否要求检测报告", "是否要求认证证书", "是否要求专利", "是否设置★实质性条款"}:
        return "存在" if text else ""
    if field_name in {"一般资格要求", "特定资格要求", "资格条件明细", "资格门槛明细", "评分项明细", "是否仍保留价格扣除条款", "是否专门面向中小企业", "是否为预留份额采购", "是否涉及进口产品", "证明来源要求"}:
        return "存在"
    if field_name in {"付款节点", "验收标准", "考核条款", "满意度条款", "扣款条款", "解约条款", "违约责任", "质保期", "履约保证金", "整改条款", "申辩条款", "单方解释权", "转包外包条款"}:
        return "存在"
    return unit.clause_semantic_type.value if unit.clause_semantic_type != ClauseSemanticType.unknown_clause else ""


def _infer_unit_relation_tags(unit: ClauseUnit, field_name: str) -> list[str]:
    tags: list[str] = []
    conditional_context = unit.conditional_context or {}
    if field_name:
        tags.append(field_name)
    if unit.clause_semantic_type != ClauseSemanticType.unknown_clause:
        tags.append(unit.clause_semantic_type.value)
    if unit.legal_effect_type != LegalEffectType.unknown:
        tags.append(unit.legal_effect_type.value)
    if unit.table_context.get("row_label"):
        tags.append(str(unit.table_context.get("row_label")))
    if unit.effect_tags:
        tags.extend(tag.value for tag in unit.effect_tags)
    if unit.clause_constraint.constraint_types:
        tags.extend(item.value for item in unit.clause_constraint.constraint_types)
    if unit.legal_principle_tags:
        tags.extend(item.value for item in unit.legal_principle_tags)
    if conditional_context.get("conditional_policy") == "true":
        tags.append("conditional_policy")
        if conditional_context.get("project_binding") == "true":
            tags.append("项目事实绑定")
        else:
            tags.append("条件政策说明")
        if conditional_context.get("policy_branch") == "set_aside":
            tags.append("专门面向中小企业路径")
        if conditional_context.get("policy_branch") == "non_set_aside":
            tags.append("非专门面向中小企业路径")
        if conditional_context.get("price_deduction_rule") == "allowed":
            tags.append("价格扣除保留")
        if conditional_context.get("price_deduction_rule") == "forbidden":
            tags.append("价格扣除不适用")
    return list(dict.fromkeys(tag for tag in tags if tag))


def _unit_text_context(unit: ClauseUnit) -> str:
    parts = [
        str(unit.table_context.get("title", "")).strip(),
        str(unit.table_context.get("row_label", "")).strip(),
        unit.text.strip(),
        unit.path.strip(),
    ]
    return " ".join(part for part in parts if part)


def _merge_extracted_clauses(primary: list[ExtractedClause], fallback: list[ExtractedClause]) -> list[ExtractedClause]:
    merged: list[ExtractedClause] = []
    seen: set[tuple[str, str, str]] = set()
    for clause in [*primary, *fallback]:
        key = (clause.field_name, clause.source_anchor, clause.content[:120])
        if key in seen:
            continue
        seen.add(key)
        merged.append(clause)
    return merged


def _enrich_extracted_clause(clause: ExtractedClause) -> ExtractedClause:
    if clause.legal_effect_type == LegalEffectType.unknown:
        clause.legal_effect_type = infer_legal_effect(
            text=clause.content,
            zone_type=clause.semantic_zone,
            clause_semantic_type=ClauseSemanticType.unknown_clause,
            field_name=clause.field_name,
        )
    clause.clause_constraint = infer_clause_constraint(clause.content, clause.legal_effect_type)
    clause.legal_principle_tags = infer_legal_principle_tags(
        clause.content,
        clause.legal_effect_type,
        clause.clause_constraint,
    )
    clause.relation_tags = list(
        dict.fromkeys(
            [
                *clause.relation_tags,
                clause.legal_effect_type.value,
                *(item.value for item in clause.legal_principle_tags),
                *(item.value for item in clause.clause_constraint.constraint_types),
                *(item.value for item in clause.clause_constraint.restriction_axes),
            ]
        )
    )
    return clause


def classify_clause_role(text: str) -> ClauseRole:
    normalized = text.strip()
    if not normalized:
        return ClauseRole.unknown

    form_markers = [
        "证明书",
        "格式",
        "以下格式文件由供应商根据需要选用",
        "单位名称（盖章）",
        "法定代表人",
        "投标人代表",
        "联合体共同投标协议书",
    ]
    if (
        any(marker in normalized for marker in form_markers)
        or "____" in normalized
        or "______" in normalized
        or normalized.endswith("声明函")
        or normalized.startswith("声明函")
        or normalized.startswith("中小企业声明函")
        or normalized.startswith("残疾人福利性单位声明函")
    ):
        return ClauseRole.form_template

    if "详见附件" in normalized or "附表" in normalized or "附件" in normalized:
        return ClauseRole.appendix_reference

    if any(marker in normalized for marker in ["名词解释", "采购代理机构：", "采购人：", "投标人：", "评标委员会"]):
        return ClauseRole.document_definition

    if any(marker in normalized for marker in ["根据《", "依据《", "管理办法", "通知》", "实施条例", "政府采购法"]) and any(
        marker in normalized for marker in ["规定", "说明", "政策", "扶持", "扣除"]
    ):
        return ClauseRole.policy_explanation

    if any(
        marker in normalized
        for marker in [
            "付款",
            "验收",
            "违约",
            "解约",
            "质保",
            "履约",
            "安装",
            "调试",
            "团队稳定",
            "人员更换",
            "更换",
            "替换",
        ]
    ):
        return ClauseRole.contract_term

    if any(
        marker in normalized
        for marker in [
            "资格要求",
            "评分",
            "综合评分",
            "评标",
            "分值",
            "业绩",
            "证书",
            "样品",
            "技术要求",
            "商务要求",
            "信用评价",
            "信用分",
            "信用等级",
            "征信",
        ]
    ):
        return ClauseRole.qualification_or_scoring

    if any(marker in normalized for marker in ["不接受联合体", "不允许合同分包", "采购包", "中小企业", "价格扣除", "采购需求", "货物", "服务", "工程"]):
        return ClauseRole.procurement_requirement

    return ClauseRole.unknown


def _simple_keyword_extractor(keywords: list[str], *, exclude_tokens: list[str] | None = None) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if exclude_tokens and any(token in line for token in exclude_tokens):
                continue
            if any(keyword in line for keyword in keywords):
                return _build_clause(line, line_no)
        return None

    return extractor


def _build_window_clause(
    lines: list[str],
    line_no: int,
    *,
    before: int = 0,
    after: int = 2,
    normalized_value: str = "",
    relation_tags: list[str] | None = None,
) -> ExtractedClause:
    start = max(1, line_no - before)
    end = min(len(lines), line_no + after)
    window = [lines[idx - 1].strip() for idx in range(start, end + 1)]
    content = "；".join(item for item in window if item)[:320]
    return ExtractedClause(
        category="",
        field_name="",
        content=content,
        source_anchor=f"line:{line_no}",
        normalized_value=normalized_value,
        relation_tags=relation_tags or [],
    )


def _multi_line_keyword_extractor(
    include_tokens: list[str],
    *,
    require_tokens: list[str] | None = None,
    exclude_tokens: list[str] | None = None,
    max_lines: int = 4,
    normalized_value: str = "存在",
    relation_tags: list[str] | None = None,
) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        anchors: list[int] = []
        matched_lines: list[str] = []
        for line_no, line in enumerate(lines, start=1):
            if exclude_tokens and any(token in line for token in exclude_tokens):
                continue
            if not any(token in line for token in include_tokens):
                continue
            if require_tokens and not any(token in line for token in require_tokens):
                continue
            anchors.append(line_no)
            matched_lines.append(line[:160])
            if len(matched_lines) >= max_lines:
                break
        if not anchors:
            return None
        return ExtractedClause(
            category="",
            field_name="",
            content="；".join(dict.fromkeys(matched_lines))[:480],
            source_anchor=f"line:{anchors[0]}",
            normalized_value=normalized_value,
            relation_tags=relation_tags or [],
        )

    return extractor


def _window_keyword_extractor(
    keywords: list[str],
    *,
    require_tokens: list[str] | None = None,
    exclude_tokens: list[str] | None = None,
    before: int = 0,
    after: int = 2,
    normalized_value: str = "存在",
    relation_tags: list[str] | None = None,
) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if exclude_tokens and any(token in line for token in exclude_tokens):
                continue
            if not any(keyword in line for keyword in keywords):
                continue
            if require_tokens and not any(token in line for token in require_tokens):
                continue
            return _build_window_clause(
                lines,
                line_no,
                before=before,
                after=after,
                normalized_value=normalized_value,
                relation_tags=relation_tags or [],
            )
        return None

    return extractor


def _brand_requirement_extractor(lines: list[str]) -> ExtractedClause | None:
    requirement_tokens = ["指定", "限定", "必须", "须", "应", "要求", "采用", "提供"]
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["品牌", "原厂"]):
            continue
        if any(token in line for token in ["相同品牌产品", "同品牌投标人", "同品牌"]):
            continue
        if any(token in line for token in ["原厂服务", "原厂服务团队", "原厂售后"]):
            return _build_clause(line, line_no, normalized_value="存在", relation_tags=["指定品牌/原厂限制"])
        if "原厂正品" in line and not any(token in line for token in ["指定品牌", "指定原厂", "原厂授权", "原厂证明"]):
            continue
        if any(token in line for token in ["声明函", "商标权", "知识产权", "注册商标"]):
            continue
        if not any(token in line for token in requirement_tokens):
            continue
        return _build_clause(line, line_no, normalized_value="存在", relation_tags=["指定品牌/原厂限制"])
    return None


def _property_type_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["项目属性", "项目类型", "项目所属分类", "货物类", "工程类", "服务类"]):
            continue
        if (
            "项目属性" not in line
            and "项目类型" not in line
            and "项目所属分类" not in line
            and not any(token in line for token in ["货物类", "工程类", "服务类"])
        ):
            continue
        value = ""
        if "货物" in line:
            value = "货物"
        elif "服务" in line:
            value = "服务"
        elif "工程" in line:
            value = "工程"
        if value:
            return _build_clause(line, line_no, normalized_value=value, relation_tags=[value])
    return None


def _procurement_target_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if "采购标的" not in line and "采购内容" not in line and "采购需求" not in line:
            continue
        if any(token in line for token in ["采购标的/服务清单", "采购标的/所投产品/货物（服务）清单"]):
            continue
        if "采购需求" in line and any(token in line for token in ["详见附件", "详见采购需求", "详见招标文件"]):
            continue
        if "采购需求" in line and not any(
            token in line
            for token in ["货物", "服务", "设备", "系统", "平台", "家具", "厨房", "窗帘", "物业", "运维", "供货", "安装"]
        ):
            continue
        return _build_clause(line, line_no, relation_tags=["采购标的"])
    return None


def _allowance_extractor(keywords: list[str], disallow_tokens: list[str], allow_tokens: list[str]) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if not any(keyword in line for keyword in keywords):
                continue
            normalized_value = ""
            relation_tags: list[str] = []
            if any(token in line for token in disallow_tokens):
                normalized_value = "不允许"
                relation_tags.append("禁止")
            elif any(token in line for token in allow_tokens):
                normalized_value = "允许"
                relation_tags.append("允许")
            return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
        return None

    return extractor


def _boolean_policy_extractor(keywords: list[str], positive_tokens: list[str]) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if not any(keyword in line for keyword in keywords):
                continue
            if _is_generic_conditional_policy_line(line):
                continue
            normalized_value = ""
            tags: list[str] = []
            if _is_project_bound_policy_line(line):
                tags.append("项目事实绑定")
            if "非专门面向中小企业" in line:
                normalized_value = "否"
                tags.append("否")
            elif any(token in line for token in positive_tokens):
                normalized_value = "是"
                tags.append("是")
            return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=tags)
        return None

    return extractor


def _declaration_type_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if "中小企业声明函" not in line and "制造商" not in line and "承接方" not in line:
            continue
        normalized_value = ""
        relation_tags: list[str] = []
        if "制造商" in line or "声明函（货物）" in line or "全部货物" in line:
            normalized_value = "货物/制造商"
            relation_tags.extend(["货物模板", "制造商口径"])
        if "承接" in line or "服务全部由" in line or "声明函（工程、服务）" in line:
            normalized_value = "服务/承接方" if not normalized_value else f"{normalized_value}+服务/承接方"
            relation_tags.extend(["服务模板", "承接方口径"])
        if "施工单位" in line:
            relation_tags.append("工程口径")
        return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
    return None


def _price_deduction_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if "价格扣除" not in line:
            continue
        if "价格扣除比例及采购标的所属行业的说明" in line:
            continue
        if _is_generic_conditional_policy_line(line):
            continue
        normalized_value = "是"
        relation_tags = ["价格扣除保留"]
        if _is_project_bound_policy_line(line):
            relation_tags.append("项目事实绑定")
        if any(token in line for token in ["不适用", "不再适用", "不执行"]):
            normalized_value = "否"
            relation_tags = ["价格扣除不适用"]
            if _is_project_bound_policy_line(line):
                relation_tags.append("项目事实绑定")
        return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
    return None


def _is_project_bound_policy_line(line: str) -> bool:
    compact = "".join(line.split())
    return any(token in compact for token in ["本项目", "本包", "本采购包", "本次采购"])


def _is_generic_conditional_policy_line(line: str) -> bool:
    compact = "".join(line.split())
    if _is_project_bound_policy_line(line):
        return False
    return "专门面向中小企业采购的项目" in compact or "非专门面向中小企业采购的项目" in compact


def _percentage_extractor(keywords: list[str]) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if not any(keyword in line for keyword in keywords):
                continue
            match = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
            normalized_value = match.group(1) + "%" if match else ""
            relation_tags = [normalized_value] if normalized_value else []
            return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
        return None

    return extractor


def _payment_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["付款方式", "付款节点", "支付"]):
            continue
        window = _build_window_clause(lines, line_no, after=4)
        window_text = window.content
        relation_tags: list[str] = []
        if "尾款" in window_text:
            relation_tags.append("尾款")
        if any(token in window_text for token in ["验收后", "验收合格后"]):
            relation_tags.append("验收触发")
        if any(token in window_text for token in ["考核", "满意度", "评价"]):
            relation_tags.append("考核联动")
        return ExtractedClause(
            category="",
            field_name="",
            content=window.content,
            source_anchor=window.source_anchor,
            normalized_value="存在",
            relation_tags=relation_tags,
        )
    return None


def _material_stage_extractor(keywords: list[str]) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if not any(keyword in line for keyword in keywords):
                continue
            if "人员证书" in line and not any(token in line for token in ["认证证书", "检测报告", "管理体系认证", "环境标志", "环保产品认证"]):
                continue
            relation_tags: list[str] = []
            normalized_value = ""
            if any(token in line for token in ["投标文件", "响应文件", "评审", "评分", "加分", "资格审查", "投标阶段"]):
                normalized_value = "投标阶段"
                relation_tags.append("投标阶段")
            elif any(token in line for token in ["中标后", "供货时", "交货时", "履约", "验收", "验收时", "签约后"]):
                normalized_value = "履约/验收阶段"
                relation_tags.append("履约/验收阶段")
            else:
                normalized_value = "未明确"
                relation_tags.append("未明确阶段")
            return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
        return None

    return extractor


def _material_burden_extractor(lines: list[str]) -> ExtractedClause | None:
    burden_terms = ["检测报告", "认证证书", "管理体系认证", "环境标志", "环保产品认证"]
    requirement_terms = ["需", "须", "必须", "提供", "提交", "具备", "具有"]
    score_pattern = re.compile(r"(\(\d+(?:\.\d+)?分\)|（\d+(?:\.\d+)?分）|得\d+(?:\.\d+)?分|最高得)")
    excluded_terms = [
        "电子签名和电子印章",
        "CA数字证书",
        "电子认证服务许可证",
        "电子认证服务使用密码许可证",
        "第三方书面声明",
        "资料虚假",
        "隐瞒真实情况",
        "业绩成果",
    ]
    matched_lines: list[str] = []
    anchors: list[int] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        if any(term in line for term in excluded_terms):
            continue
        if score_pattern.search(line):
            continue
        matched = [term for term in burden_terms if term in line]
        if not matched:
            continue
        if not any(term in line for term in requirement_terms):
            continue
        anchors.append(line_no)
        matched_lines.append(line[:180])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:320],
        source_anchor=f"line:{anchors[0]}",
        normalized_value=";".join(dict.fromkeys(matched_terms)),
        relation_tags=["材料负担要求", *dict.fromkeys(matched_terms)],
    )


def _scoring_item_details_extractor(lines: list[str]) -> ExtractedClause | None:
    score_pattern = re.compile(r"(\(\d+(?:\.\d+)?分\)|（\d+(?:\.\d+)?分）|得\d+(?:\.\d+)?分|最高得)")
    excluded_tokens = [
        "电子签名和电子印章",
        "CA数字证书",
        "分支机构",
        "授权书",
        "信用评价分无法使用",
        "联合体共同投标协议书",
        "联合体投标",
        "评审标准不明确",
    ]
    scored_matches: list[tuple[int, int, str, list[str]]] = []
    for line_no, line in enumerate(lines, start=1):
        if any(token in line for token in excluded_tokens):
            continue
        if not any(token in line for token in ["分", "得分", "评分", "评审"]):
            continue
        if not score_pattern.search(line):
            continue
        if not any(
            token in line
            for token in [
                "实施方案",
                "售后服务方案",
                "资质证书",
                "管理体系认证",
                "检测报告",
                "财务",
                "利润率",
                "项目负责人",
                "业绩",
                "信用评价",
                "项目整体",
                "方案",
            ]
        ):
            continue
        score = 1
        if "项目负责人" in line or "项目经理" in line or "项目主管" in line:
            score += 3
        if any(token in line for token in ["资质证书", "管理体系认证", "认证证书", "检测报告", "信用评价"]):
            score += 2
        if "实施方案" in line or "项目整体" in line or "售后服务方案" in line:
            score += 1
        line_tags: list[str] = []
        if "实施方案" in line or "项目整体" in line:
            line_tags.append("实施方案评分项")
        if "售后服务方案" in line or "售后" in line:
            line_tags.append("售后评分项")
        if "资质证书" in line:
            line_tags.append("资质证书评分项")
        if "管理体系认证" in line or "认证证书" in line:
            line_tags.append("认证证书评分项")
        if "检测报告" in line:
            line_tags.append("检测报告评分项")
        if "财务" in line or "利润率" in line:
            line_tags.append("财务指标评分项")
        if "项目负责人" in line or "业绩" in line:
            line_tags.append("业绩人员评分项")
        if "信用评价" in line or "信用分" in line or "信用等级" in line:
            line_tags.append("信用评价评分项")
        scored_matches.append((score, line_no, line[:220], line_tags))
    if not scored_matches:
        return None
    scored_matches.sort(key=lambda item: (-item[0], item[1]))
    anchors = [line_no for _, line_no, _, _ in scored_matches[:5]]
    matched_lines = [line for _, _, line, _ in scored_matches[:5]]
    relation_tags = [tag for _, _, _, tags in scored_matches[:5] for tag in tags]
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:480],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["评分项明细", *dict.fromkeys(relation_tags)],
    )


def _procurement_method_extractor(lines: list[str]) -> ExtractedClause | None:
    method_terms = ["公开招标", "竞争性磋商", "竞争性谈判", "单一来源", "询价", "框架协议"]
    for line_no, line in enumerate(lines, start=1):
        if "公开招标文件" in line and "采购方式" not in line:
            continue
        if not any(term in line for term in method_terms) and "采购方式" not in line:
            continue
        matched = next((term for term in method_terms if term in line), "")
        if matched:
            return _build_window_clause(lines, line_no, after=1, normalized_value=matched, relation_tags=[matched])
        return _build_window_clause(lines, line_no, after=1)
    return None


def _demand_survey_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if "需求调查" not in line:
            continue
        normalized_value = "未明确"
        relation_tags = ["需求调查结论"]
        if any(token in line for token in ["不需要需求调查", "无需需求调查", "未开展需求调查"]):
            normalized_value = "不需要"
            relation_tags.append("不需要")
        elif any(token in line for token in ["需要需求调查", "应开展需求调查", "已开展需求调查"]):
            normalized_value = "需要"
            relation_tags.append("需要")
        return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
    return None


def _procurement_method_reason_extractor(lines: list[str]) -> ExtractedClause | None:
    keywords = ["采用竞争性磋商", "采用竞争性谈判", "采用单一来源", "适用情形", "适用理由", "采购方式适用理由"]
    reason_markers = ["因", "鉴于", "根据", "适用", "理由", "情形", "唯一", "复杂", "无法事先确定", "只能", "没有供应商"]
    for line_no, line in enumerate(lines, start=1):
        window = "；".join(
            item.strip()
            for item in lines[max(0, line_no - 1): min(len(lines), line_no + 3)]
            if item.strip()
        )
        if not any(token in window for token in keywords):
            continue
        if not any(token in window for token in reason_markers):
            continue
        return _build_window_clause(
            lines,
            line_no,
            before=1,
            after=3,
            normalized_value="存在",
            relation_tags=["采购方式适用理由"],
        )
    return None


def _package_count_extractor(lines: list[str]) -> ExtractedClause | None:
    package_lines: list[int] = []
    package_texts: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["采购包", "第1包", "第2包", "包组", "不划分采购包", "不分包采购"]):
            continue
        package_lines.append(line_no)
        package_texts.append(line[:120])
    if not package_lines:
        return None
    numbers = sorted(set(re.findall(r"(?:采购包|第)(\d+)", " ".join(package_texts))))
    count = str(len(numbers) or len(package_lines))
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(package_texts))[:320],
        source_anchor=f"line:{package_lines[0]}",
        normalized_value=count,
        relation_tags=["采购包数量", f"{count}个包"],
    )


def _package_split_extractor(lines: list[str]) -> ExtractedClause | None:
    keywords = ["不划分采购包", "划分采购包", "分包采购", "包组划分", "划分依据", "不分包采购"]
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in keywords):
            continue
        normalized_value = "存在"
        relation_tags = ["采购包划分说明"]
        if any(token in line for token in ["不划分采购包", "不分包采购"]):
            relation_tags.append("未拆分")
        if any(token in line for token in ["划分依据", "采购包划分", "包组划分", "分包采购"]):
            relation_tags.append("已说明划分依据")
        return _build_window_clause(lines, line_no, after=2, normalized_value=normalized_value, relation_tags=relation_tags)
    return None


def _qualification_detail_extractor(lines: list[str]) -> ExtractedClause | None:
    scored_matches: list[tuple[int, int, str]] = []
    strong_specific_tokens = [
        "资质证书",
        "认证证书",
        "管理体系认证",
        "检测报告",
        "项目负责人",
        "项目经理",
        "项目主管",
        "保安服务许可证",
        "职称证书",
        "信用评价",
        "信用等级",
        "业绩要求",
    ]
    specific_tokens = [
        "资格要求",
        "供应商资格",
        "特定资格要求",
        "资质证书",
        "认证证书",
        "管理体系认证",
        "检测报告",
        "业绩要求",
        "项目负责人",
        "项目经理",
        "项目主管",
        "保安服务许可证",
        "职称证书",
        "信用评价",
        "信用等级",
    ]
    requirement_tokens = ["须具备", "应具备", "具有", "取得", "提供", "提交", "满足"]
    mandatory_tokens = ["否则将视为非实质性响应", "不得少于", "须驻场", "持证上岗", "方可上岗", "提供承诺函", "报采购人审核", "经采购人确认"]
    excluded_tokens = [
        "法定代表人",
        "声明函",
        "政府采购法第二十二条",
        "重大违法记录",
        "串通投标",
        "隐瞒真实情况",
        "电子签名和电子印章",
        "CA数字证书",
        "供应商提供承诺函",
        "第三方书面声明",
        "资料虚假",
        "资质证件",
        "业绩成果",
        "投标文件组成部分",
        "分支机构",
        "授权书",
        "营业执照",
        "执业许可证",
        "节能产品",
        "环境标志产品",
    ]
    score_pattern = re.compile(r"(\(\d+(?:\.\d+)?分\)|（\d+(?:\.\d+)?分）|得\d+(?:\.\d+)?分|最高得)")
    for line_no, line in enumerate(lines, start=1):
        if any(token in line for token in excluded_tokens):
            continue
        if not any(token in line for token in specific_tokens):
            continue
        if score_pattern.search(line):
            continue
        if not any(token in line for token in requirement_tokens + mandatory_tokens) and not any(token in line for token in ["资格要求", "供应商资格", "特定资格要求"]):
            continue
        score = 1
        if any(token in line for token in mandatory_tokens):
            score += 3
        if any(token in line for token in ["项目负责人", "项目经理", "项目主管", "保安服务许可证", "职称证书"]):
            score += 3
        if any(token in line for token in ["资质证书", "认证证书", "管理体系认证", "检测报告"]):
            score += 2
        if any(token in line for token in ["资格要求", "供应商资格", "特定资格要求"]):
            score += 1
        after = 12 if any(token in line for token in ["本项目特定的资格要求", "投标人的资格要求", "特定资格要求"]) else 4
        window = _build_window_clause(lines, line_no, after=after, normalized_value="存在", relation_tags=["资格条件明细"])
        if any(token in line for token in ["资格要求", "供应商资格", "特定资格要求"]) and not any(token in window.content for token in strong_specific_tokens):
            continue
        scored_matches.append((score, line_no, window.content))
    if not scored_matches:
        return None
    scored_matches.sort(key=lambda item: (-item[0], item[1]))
    anchors = [line_no for _, line_no, _ in scored_matches[:3]]
    matched_lines = [content for _, _, content in scored_matches[:3]]
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:480],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["资格条件明细"],
    )


def _expert_review_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["专家论证", "论证意见", "需求论证"]):
            continue
        normalized_value = "未明确"
        relation_tags = ["专家论证结论"]
        if any(token in line for token in ["不需要", "无需", "未进行", "不组织", "未组织"]):
            normalized_value = "不需要"
            relation_tags.append("不需要")
        elif any(token in line for token in ["需要", "应当", "已组织", "已开展"]):
            normalized_value = "需要"
            relation_tags.append("需要")
        return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
    return None


def _qualification_gate_extractor(lines: list[str]) -> ExtractedClause | None:
    gate_terms = [
        "科技型中小企业",
        "高新技术企业",
        "纳税信用",
        "成立满",
        "成立时间满",
        "同类项目业绩",
        "业绩不少于",
    ]
    requirement_terms = ["须为", "须具备", "须提供", "应具备", "应提供", "需提供", "不得少于"]
    anchors: list[int] = []
    matched_lines: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        if not any(term in line for term in gate_terms):
            continue
        if not any(term in line for term in requirement_terms):
            continue
        anchors.append(line_no)
        matched_lines.append(line[:180])
        if len(matched_lines) >= 8:
            break
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:1200],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["资格门槛明细"],
    )


def _technical_service_verifiability_extractor(lines: list[str]) -> ExtractedClause | None:
    vague_terms = [
        "满足采购人要求",
        "按行业标准",
        "高质量完成",
        "优质服务",
        "良好服务",
        "由采购人认定",
        "以采购人要求为准",
        "达到项目要求",
    ]
    matched_lines: list[str] = []
    anchors: list[int] = []
    for line_no, line in enumerate(lines, start=1):
        if not any(term in line for term in vague_terms):
            continue
        anchors.append(line_no)
        matched_lines.append(line[:140])
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:420],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["技术服务可验证性不足"],
    )


def _amount_extractor(keywords: list[str]) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if not any(keyword in line for keyword in keywords):
                continue
            normalized_line = line.replace("，", ",")
            candidate_tokens = re.findall(r"\d[\d,]*(?:\.\d+)?", normalized_line)
            normalized_value = ""
            if candidate_tokens:
                # Prefer the longest numeric token to avoid OCR fragments like "268" winning over "2680443.18".
                best = max(candidate_tokens, key=lambda token: (len(token.replace(",", "")), "." in token))
                normalized_value = best.replace(",", "")
            return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=[normalized_value] if normalized_value else [])
        return None

    return extractor


def _contract_type_extractor(lines: list[str]) -> ExtractedClause | None:
    contract_types = ["承揽合同", "买卖合同", "服务合同", "施工合同", "采购合同"]
    # Prefer explicit contract type declarations over generic "政府采购合同" process wording.
    for line_no, line in enumerate(lines, start=1):
        if "合同类型" not in line:
            continue
        for contract_type in contract_types:
            if contract_type in line:
                return _build_clause(line, line_no, normalized_value=contract_type, relation_tags=[contract_type])
    for line_no, line in enumerate(lines, start=1):
        if "是否属于签订不超过3年履行期限政府采购合同的项目" in line:
            continue
        if any(
            token in line
            for token in [
                "销售或服务合同",
                "服务合同复印件",
                "销售合同复印件",
                "政府采购合同",
                "采购合同履约",
                "采购合同复印件",
                "补充合同",
                "签订合同",
                "签订采购合同",
            ]
        ):
            continue
        if "采购合同" in line and "合同类型" not in line:
            continue
        for contract_type in contract_types:
            if contract_type in line:
                return _build_clause(line, line_no, normalized_value=contract_type, relation_tags=[contract_type])
    return None


def _certificate_score_weight_extractor(lines: list[str]) -> ExtractedClause | None:
    total = 0.0
    anchors: list[int] = []
    matched_titles: list[str] = []
    score_pattern = re.compile(r"\((\d+(?:\.\d+)?)分\)")
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["资质证书", "认证情况", "认证证书", "检测报告"]):
            continue
        if not any(token in line for token in ["评分", "评审", "得", "分)"]):
            continue
        match = score_pattern.search(line)
        if not match:
            continue
        total += float(match.group(1))
        anchors.append(line_no)
        matched_titles.append(line[:40])
    if total <= 0:
        return None
    anchor = f"line:{anchors[0]}"
    quote = "；".join(dict.fromkeys(matched_titles))
    return ExtractedClause(
        category="",
        field_name="",
        content=quote[:160],
        source_anchor=anchor,
        normalized_value=f"{total:.1f}",
        relation_tags=["证书类评分总分", f"{total:.1f}分"],
    )


def _credit_evaluation_scoring_extractor(lines: list[str]) -> ExtractedClause | None:
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        matched = [term for term in ["信用评价", "信用分", "信用等级", "信用评分", "征信"] if term in line]
        if not matched:
            continue
        if not any(token in line for token in ["分", "评分", "评审", "加分", "得分"]):
            continue
        anchors.append(line_no)
        matched_lines.append(_build_window_clause(lines, line_no, after=2).content)
        matched_terms.extend(matched)
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:320],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["信用评价评分项", *dict.fromkeys(matched_terms)],
    )


def _credit_relief_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["信用", "失信", "信用中国", "征信"]):
            continue
        if not any(token in line for token in ["修复", "异议", "申诉", "救济", "复核"]):
            continue
        return _build_window_clause(
            lines,
            line_no,
            after=2,
            normalized_value="存在",
            relation_tags=["信用修复或异议机制"],
        )
    return None


def _service_content_extractor(lines: list[str]) -> ExtractedClause | None:
    service_terms = [
        "人工管护",
        "清林整地",
        "栽植",
        "连续三年施肥",
        "施肥",
        "幼林抚育",
        "成林管护",
        "机械运水",
        "抚育",
        "管护",
        "运水",
    ]
    for line_no, line in enumerate(lines, start=1):
        matched = [term for term in service_terms if term in line]
        if not matched:
            continue
        relation_tags = ["持续性作业服务", *matched[:5]]
        return _build_clause(line, line_no, normalized_value="是", relation_tags=relation_tags)
    return None


def _industry_mismatch_scoring_extractor(lines: list[str]) -> ExtractedClause | None:
    mismatch_terms = [
        "软件企业认定证书",
        "ITSS",
        "运行维护服务证书",
        "利润率",
        "财务报告",
        "人力资源测评师",
        "非金属矿采矿许可证",
        "采矿许可证",
    ]
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    boundary_tokens = ["合同条款", "验收条款", "付款", "一般资格要求", "资格要求", "技术要求", "商务要求"]
    scoring_tokens = ["分", "评分", "评审", "得分", "证书", "财务报告", "利润率", "评分标准", "专家打分", "详细评审", "履约能力"]
    for line_no, line in enumerate(lines, start=1):
        matched = [term for term in mismatch_terms if term in line]
        if not matched:
            continue
        context_window = " ".join(lines[max(0, line_no - 3): min(len(lines), line_no + 2)])
        if not any(token in f"{line} {context_window}" for token in scoring_tokens):
            continue
        anchors.append(line_no)
        matched_lines.append(line[:80])
        matched_terms.extend(matched)
    if not anchors:
        return None
    start_index = anchors[0] - 1
    if start_index > 0 and any(token in lines[start_index - 1] for token in ["评分标准", "评分项", "详细评审", "履约能力"]):
        start_index -= 1
    selected: list[str] = []
    fragment_bridge_mode = anchors[-1] - anchors[0] >= 2
    for idx in range(start_index, min(len(lines), anchors[-1] + 1)):
        line = lines[idx].strip()
        if not line:
            if selected:
                break
            continue
        if any(token in line for token in boundary_tokens):
            if selected:
                break
            continue
        if (
            selected
            and not any(token in line for token in scoring_tokens + mismatch_terms)
            and not (fragment_bridge_mode and (idx + 1) < anchors[-1])
        ):
            break
        selected.append(line)
    ordered_selected = list(dict.fromkeys(selected or matched_lines))
    if any(
        len(line.strip()) <= 12
        or line.strip().startswith(("的", "及", "、", "（", "(", ",", "，", "）", ")", "须", "由"))
        or not line.strip().endswith(("。", "；", "!", "！", "?", "？", "：", ":", "）", ")"))
        for line in ordered_selected
    ):
        content = re.sub(r"\s+", " ", "".join(line.strip() for line in ordered_selected if line.strip())).strip()[:320]
    else:
        content = "；".join(ordered_selected)[:320]
    return ExtractedClause(
        category="",
        field_name="",
        content=content,
        source_anchor=f"line:{anchors[0]}",
        normalized_value=";".join(dict.fromkeys(matched_terms)),
        relation_tags=["行业相关性存疑评分项", *dict.fromkeys(matched_terms)],
    )


def _plan_scoring_quant_extractor(lines: list[str]) -> ExtractedClause | None:
    keywords = ["无缺陷得满分", "每缺项扣", "每处缺陷扣", "缺陷扣", "扣2.5分", "缺项扣分", "完全满足且优于", "完全满足项目要求", "不完全满足项目要求"]
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        matched = [token for token in keywords if token in line]
        if not matched:
            continue
        anchors.append(line_no)
        matched_lines.append(line[:100])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:400],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["方案量化不足", *dict.fromkeys(matched_terms)],
    )


def _team_stability_requirement_extractor(lines: list[str]) -> ExtractedClause | None:
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        matched = [term for term in ["团队稳定", "核心团队", "人员稳定", "稳定性", "团队成员"] if term in line]
        if not matched:
            continue
        if not any(token in line for token in ["要求", "不得", "保持", "稳定", "更换", "人员"]):
            continue
        anchors.append(line_no)
        matched_lines.append(line[:120])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return _build_clause(
        "；".join(dict.fromkeys(matched_lines))[:320],
        anchors[0],
        normalized_value="存在",
        relation_tags=["团队稳定性要求", *dict.fromkeys(matched_terms)],
    )


def _personnel_change_limit_extractor(lines: list[str]) -> ExtractedClause | None:
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["更换", "替换", "变更", "调整", "撤换"]):
            continue
        if not any(
            token in line
            for token in [
                "人员",
                "岗位",
                "团队",
                "项目负责人",
                "采购人同意",
                "采购人批准",
                "须经采购人",
                "不得更换",
                "未经采购人同意",
            ]
        ):
            continue
        matched = [term for term in ["更换", "替换", "变更", "调整", "撤换", "采购人同意", "采购人批准"] if term in line]
        anchors.append(line_no)
        matched_lines.append(line[:120])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return _build_clause(
        "；".join(dict.fromkeys(matched_lines))[:320],
        anchors[0],
        normalized_value="存在",
        relation_tags=["人员更换限制", *dict.fromkeys(matched_terms)],
    )


def _contract_result_template_extractor(lines: list[str]) -> ExtractedClause | None:
    keywords = [
        "项目成果",
        "成果交付",
        "成果保密",
        "移作他用",
        "泄露本项目成果",
        "提交全部符合项目合同要求的项目成果",
    ]
    for line_no, line in enumerate(lines, start=1):
        matched = [token for token in keywords if token in line]
        if not matched:
            continue
        return _build_window_clause(
            lines,
            line_no,
            after=1,
            normalized_value="存在",
            relation_tags=["成果模板术语", *matched],
        )
    return None


def _contract_template_residue_extractor(lines: list[str]) -> ExtractedClause | None:
    keywords = ["X年", "事件发生后天内", "设计、测试、验收", "设计、测试", "免费质保服务", "于事件发生后"]
    anchors: list[int] = []
    matched_lines: list[str] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        matched = [token for token in keywords if token in line]
        if not matched:
            continue
        anchors.append(line_no)
        matched_lines.append(line[:160])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:320],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["合同模板残留", *dict.fromkeys(matched_terms)],
    )


def _flexible_acceptance_extractor(lines: list[str]) -> ExtractedClause | None:
    keywords = ["优胜的原则", "由采购人按", "确定验收标准", "比较优胜"]
    for line_no, line in enumerate(lines, start=1):
        matched = [token for token in keywords if token in line]
        if not matched:
            continue
        return _build_clause(
            line,
            line_no,
            normalized_value="存在",
            relation_tags=["验收弹性条款", *matched],
        )
    return None


def _deduction_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["扣款", "扣罚", "罚款"]):
            continue
        if any(token in line for token in ["较大数额罚款", "行政处罚", "经营活动", "刑事处罚"]):
            continue
        return _build_clause(line, line_no, normalized_value="存在", relation_tags=["扣款机制"])
    return None


def _patent_requirement_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if "专利" not in line:
            continue
        relation_tags = ["专利要求"]
        normalized_value = "存在"
        strong_gate = any(token in line for token in ["必须具备", "须具备", "应具备", "必须具有", "须具有"])
        if strong_gate:
            normalized_value = "刚性门槛"
            relation_tags.append("刚性门槛")
        elif any(token in line for token in ["专利权", "知识产权", "侵犯", "纠纷", "不会产生"]):
            continue
        return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags)
    return None


def _assessment_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["考核", "绩效考核", "满意度"]):
            continue
        window = _build_window_clause(lines, line_no, after=2)
        window_text = window.content
        relation_tags = ["存在"]
        if any(token in window_text for token in ["付款", "支付", "尾款"]):
            relation_tags.append("关联付款")
        if "满意度" in window_text:
            relation_tags.append("满意度")
        return ExtractedClause(
            category="",
            field_name="",
            content=window.content,
            source_anchor=window.source_anchor,
            normalized_value="存在",
            relation_tags=relation_tags,
        )
    return None


def _satisfaction_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if "满意度" not in line:
            continue
        window = _build_window_clause(lines, line_no, after=2)
        window_text = window.content
        tags = ["满意度条款"]
        if any(token in window_text for token in ["付款", "支付", "尾款"]):
            tags.append("关联付款")
        if "验收" in window_text:
            tags.append("关联验收")
        return ExtractedClause(
            category="",
            field_name="",
            content=window.content,
            source_anchor=window.source_anchor,
            normalized_value="存在",
            relation_tags=tags,
        )
    return None


def _acceptance_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["验收标准", "验收"]):
            continue
        relation_tags = ["存在"]
        if any(token in line for token in ["满意度", "采购人确认"]):
            relation_tags.append("主观验收")
        return _build_window_clause(lines, line_no, after=3, normalized_value="存在", relation_tags=relation_tags)
    return None


def _subcontract_outsource_extractor(lines: list[str]) -> ExtractedClause | None:
    keywords = ["转包", "外包", "分包", "委托第三方", "核心任务"]
    matched_lines: list[str] = []
    anchors: list[int] = []
    matched_terms: list[str] = []
    for line_no, line in enumerate(lines, start=1):
        matched = [token for token in keywords if token in line]
        if not matched:
            continue
        anchors.append(line_no)
        matched_lines.append(line[:140])
        matched_terms.extend(matched)
    if not anchors:
        return None
    return ExtractedClause(
        category="",
        field_name="",
        content="；".join(dict.fromkeys(matched_lines))[:420],
        source_anchor=f"line:{anchors[0]}",
        normalized_value="存在",
        relation_tags=["转包外包条款", *dict.fromkeys(matched_terms)],
    )


def _rectification_extractor(lines: list[str]) -> ExtractedClause | None:
    return _multi_line_keyword_extractor(
        ["整改", "限期改正", "改正", "补救"],
        relation_tags=["整改程序"],
    )(lines)


def _defense_extractor(lines: list[str]) -> ExtractedClause | None:
    return _multi_line_keyword_extractor(
        ["申辩", "陈述意见", "异议", "说明理由", "书面说明"],
        relation_tags=["申辩程序"],
    )(lines)


def _personnel_line_extractor(keywords: list[str], normalized_value: str, relation_tags: list[str] | None = None) -> ClauseExtractor:
    def extractor(lines: list[str]) -> ExtractedClause | None:
        for line_no, line in enumerate(lines, start=1):
            if not any(keyword in line for keyword in keywords):
                continue
            if any(token in line for token in ["法定代表人", "身份证号码", "退休年龄", "参保", "保险", "联合体形式投标"]):
                continue
            if normalized_value == "存在" and relation_tags:
                if "采购人审批录用" in relation_tags and not any(token in line for token in ["录用", "聘用", "上岗", "应聘"]):
                    continue
                if "容貌体形要求" in relation_tags:
                    if "联合体形式" in line or "联合体" in line:
                        continue
                    if not any(token in line for token in ["容貌", "体形", "五官", "仪容", "端庄"]):
                        continue
                if "采购人批准更换" in relation_tags and not any(token in line for token in ["更换", "替换", "变更", "调整"]):
                    continue
                return _build_clause(line, line_no, normalized_value=normalized_value, relation_tags=relation_tags or [])
        return None

    return extractor


def _origin_brand_restriction_extractor(lines: list[str]) -> ExtractedClause | None:
    requirement_tokens = ["指定", "限定", "采用", "必须", "应当", "要求", "提供"]
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["产地", "厂家", "商标", "品牌", "原厂"]):
            continue
        if any(token in line for token in ["原产地证明", "进口设备", "相同品牌产品", "同品牌投标人", "同品牌"]):
            continue
        if any(token in line for token in ["商标权", "知识产权", "声明函", "残疾人福利性单位", "注册商标", "不会产生", "侵权", "厂家出厂标准", "原厂正品"]):
            continue
        if not any(token in line for token in requirement_tokens):
            continue
        return _build_clause(line, line_no, normalized_value="存在", relation_tags=["限制产地厂家商标"])
    return None


def _age_restriction_extractor(lines: list[str]) -> ExtractedClause | None:
    for line_no, line in enumerate(lines, start=1):
        if not any(token in line for token in ["岁以下", "岁以上", "年龄"]):
            continue
        if any(token in line for token in ["法定代表人", "身份证号码", "退休年龄", "参保", "保险"]):
            continue
        if "年龄" in line and not any(token in line for token in ["岁以下", "岁以上", "年龄要求", "限", "不得超过"]):
            continue
        return _build_clause(line, line_no, normalized_value="存在", relation_tags=["年龄限制"])
    return None


def _build_clause(
    line: str,
    line_no: int,
    *,
    normalized_value: str = "",
    relation_tags: list[str] | None = None,
) -> ExtractedClause:
    return ExtractedClause(
        category="",
        field_name="",
        content=line[:160],
        source_anchor=f"line:{line_no}",
        normalized_value=normalized_value,
        relation_tags=relation_tags or [],
    )


FIELD_EXTRACTORS: list[tuple[str, str, ClauseExtractor]] = [
    ("项目基本信息", "项目名称", _simple_keyword_extractor(["项目名称"])),
    ("项目基本信息", "项目编号", _simple_keyword_extractor(["项目编号"])),
    ("项目基本信息", "采购方式", _procurement_method_extractor),
    ("项目基本信息", "采购方式适用理由", _procurement_method_reason_extractor),
    ("项目基本信息", "采购标的", _procurement_target_extractor),
    ("项目基本信息", "品目名称", _simple_keyword_extractor(["品目名称"])),
    ("项目基本信息", "项目属性", _property_type_extractor),
    ("项目基本信息", "预算金额", _amount_extractor(["预算金额"])),
    ("项目基本信息", "最高限价", _amount_extractor(["最高限价"])),
    ("项目基本信息", "合同履行期限", _simple_keyword_extractor(["合同履行期限"])),
    ("项目基本信息", "合同类型", _contract_type_extractor),
    ("项目基本信息", "采购内容构成", _service_content_extractor),
    ("项目基本信息", "是否含持续性服务", _service_content_extractor),
    ("项目基本信息", "采购包数量", _package_count_extractor),
    ("项目基本信息", "采购包划分说明", _package_split_extractor),
    ("项目基本信息", "需求调查结论", _demand_survey_extractor),
    ("项目基本信息", "专家论证结论", _expert_review_extractor),
    ("资格条款", "一般资格要求", _window_keyword_extractor(["资格要求", "供应商资格"], after=8)),
    ("资格条款", "特定资格要求", _window_keyword_extractor(["特定资格要求", "资质要求"], after=12)),
    ("资格条款", "资格门槛明细", _qualification_gate_extractor),
    ("资格条款", "资格条件明细", _qualification_detail_extractor),
    ("资格条款", "信用要求", _simple_keyword_extractor(["信用要求"])),
    ("资格条款", "是否允许联合体", _allowance_extractor(["联合体"], ["不接受联合体", "不允许联合体"], ["允许联合体", "接受联合体"])),
    ("资格条款", "是否允许分包", _allowance_extractor(["分包"], ["不允许合同分包", "不得分包", "不允许分包"], ["允许分包", "可以分包"])),
    ("技术条款", "样品要求", _simple_keyword_extractor(["样品"])),
    ("技术条款", "现场演示要求", _simple_keyword_extractor(["演示"])),
    ("技术条款", "是否指定品牌", _brand_requirement_extractor),
    ("技术条款", "是否要求专利", _patent_requirement_extractor),
    ("技术条款", "是否要求检测报告", _simple_keyword_extractor(["检测报告"])),
    ("技术条款", "是否要求认证证书", _simple_keyword_extractor(["认证证书", "证书"])),
    ("技术条款", "证明来源要求", _window_keyword_extractor(["检测中心", "检测机构", "实验室", "税务部门"], require_tokens=["出具", "提供"], after=1)),
    ("技术条款", "证书检测报告负担特征", _material_burden_extractor),
    ("技术条款", "检测报告适用阶段", _material_stage_extractor(["检测报告"])),
    ("技术条款", "证书材料适用阶段", _material_stage_extractor(["认证证书", "证书"])),
    ("技术条款", "是否设置★实质性条款", _simple_keyword_extractor(["★"])),
    ("技术条款", "是否有限制产地厂家商标", _origin_brand_restriction_extractor),
    ("技术条款", "技术服务可验证性信号", _technical_service_verifiability_extractor),
    ("评分条款", "评分方法", _simple_keyword_extractor(["评分方法", "综合评分", "评标办法"])),
    ("评分条款", "价格分", _simple_keyword_extractor(["价格分"])),
    ("评分条款", "技术分", _simple_keyword_extractor(["技术分"])),
    ("评分条款", "商务分", _simple_keyword_extractor(["商务分"])),
    ("评分条款", "证书加分", _simple_keyword_extractor(["证书加分", "证书"])),
    ("评分条款", "业绩加分", _simple_keyword_extractor(["业绩加分", "业绩"])),
    ("评分条款", "方案评分", _simple_keyword_extractor(["方案评分", "实施方案"])),
    ("评分条款", "售后加分", _simple_keyword_extractor(["售后"])),
    ("评分条款", "财务指标加分", _simple_keyword_extractor(["财务指标", "利润率", "营业收入", "注册资本", "资产规模"])),
    ("评分条款", "人员评分要求", _simple_keyword_extractor(["项目负责人", "人员配置", "社保", "学历", "职称"])),
    ("评分条款", "样品分", _simple_keyword_extractor(["样品分"])),
    ("评分条款", "评分项明细", _scoring_item_details_extractor),
    ("评分条款", "证书类评分总分", _certificate_score_weight_extractor),
    ("评分条款", "信用评价要求", _credit_evaluation_scoring_extractor),
    ("评分条款", "信用修复条款", _credit_relief_extractor),
    ("评分条款", "异议救济条款", _credit_relief_extractor),
    ("评分条款", "行业相关性存疑评分项", _industry_mismatch_scoring_extractor),
    ("评分条款", "方案评分扣分模式", _plan_scoring_quant_extractor),
    ("合同条款", "付款节点", _payment_extractor),
    ("合同条款", "验收标准", _acceptance_extractor),
    ("合同条款", "争议解决方式", _window_keyword_extractor(["争议解决"], after=2)),
    ("合同条款", "违约责任", _window_keyword_extractor(["违约责任"], after=3)),
    ("合同条款", "质保期", _simple_keyword_extractor(["质保期"])),
    ("合同条款", "履约保证金", _simple_keyword_extractor(["履约保证金"])),
    ("合同条款", "考核条款", _assessment_extractor),
    ("合同条款", "满意度条款", _satisfaction_extractor),
    ("合同条款", "扣款条款", _deduction_extractor),
    ("合同条款", "解约条款", _window_keyword_extractor(["解约", "解除合同"], after=3)),
    ("合同条款", "整改条款", _rectification_extractor),
    ("合同条款", "申辩条款", _defense_extractor),
    ("合同条款", "单方解释权", _simple_keyword_extractor(["解释权", "以采购人意见为准", "以采购人解释为准"])),
    ("合同条款", "合同成果模板术语", _contract_result_template_extractor),
    ("合同条款", "合同模板残留", _contract_template_residue_extractor),
    ("合同条款", "验收弹性条款", _flexible_acceptance_extractor),
    ("合同条款", "转包外包条款", _subcontract_outsource_extractor),
    ("人员条款", "性别限制", _personnel_line_extractor(["男性", "女性", "限女性", "限男性"], "存在", ["性别限制"])),
    ("人员条款", "年龄限制", _age_restriction_extractor),
    ("人员条款", "身高限制", _personnel_line_extractor(["身高"], "存在", ["身高限制"])),
    ("人员条款", "容貌体形要求", _personnel_line_extractor(["容貌", "体形", "五官端正"], "存在", ["容貌体形要求"])),
    ("人员条款", "学历职称要求", _personnel_line_extractor(["学历", "职称"], "存在", ["学历职称要求"])),
    ("人员条款", "采购人审批录用", _personnel_line_extractor(["批准录用", "录用审批", "录用须经采购人审批", "聘用须经采购人审批"], "存在", ["采购人审批录用"])),
    ("人员条款", "采购人批准更换", _personnel_line_extractor(["批准更换", "人员更换须经采购人同意"], "存在", ["采购人批准更换"])),
    ("人员条款", "团队稳定性要求", _team_stability_requirement_extractor),
    ("人员条款", "人员更换限制", _personnel_change_limit_extractor),
    ("人员条款", "采购人直接指挥", _personnel_line_extractor(["采购人有权直接指挥", "服从采购人安排"], "存在", ["采购人直接指挥"])),
    ("政策条款", "是否专门面向中小企业", _boolean_policy_extractor(["专门面向中小企业", "中小微企业采购"], ["专门面向中小企业", "面向中小微企业"])),
    ("政策条款", "是否为预留份额采购", _boolean_policy_extractor(["预留份额"], ["预留份额"])),
    ("政策条款", "是否允许分包落实中小企业政策", _allowance_extractor(["分包", "中小企业政策"], ["不允许"], ["允许", "可以"])),
    ("政策条款", "所属行业划分", _simple_keyword_extractor(["所属行业"])),
    ("政策条款", "中小企业声明函类型", _declaration_type_extractor),
    ("政策条款", "是否仍保留价格扣除条款", _price_deduction_extractor),
    ("政策条款", "是否涉及进口产品", _boolean_policy_extractor(["进口产品"], ["进口产品"])),
    ("政策条款", "分包比例", _percentage_extractor(["分包比例", "预留比例", "小微企业比例"])),
    ("政策条款", "面向中小企业采购金额", _amount_extractor(["面向中小企业采购金额"])),
]

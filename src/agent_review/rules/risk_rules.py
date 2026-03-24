from __future__ import annotations

from typing import Iterable

from ..models import Evidence, Finding, FindingType, Recommendation, RiskHit, Severity


def match_risk_rules(text: str) -> list[RiskHit]:
    keyword_rules = [
        ("A.限制竞争风险", "指定品牌/原厂限制", Severity.high, ["指定品牌", "原厂"], "存在指定品牌或原厂倾向，需核查是否构成排斥竞争。"),
        ("A.限制竞争风险", "产地厂家商标限制", Severity.high, ["产地", "厂家", "商标"], "存在对产地、厂家或商标的倾向性表达。"),
        ("A.限制竞争风险", "专利要求", Severity.high, ["专利"], "出现专利要求，需核查是否属于不必要门槛。"),
        ("A.限制竞争风险", "认证证书要求", Severity.medium, ["认证证书", "证书"], "出现证书要求，需判断是否与项目需求直接相关。"),
        ("A.限制竞争风险", "检测报告要求", Severity.medium, ["检测报告"], "出现检测报告要求，需判断是否必要且合理。"),
        ("B.评分不规范风险", "无缺陷得满分", Severity.medium, ["无缺陷得满分"], "评分裁量口径过宽，缺陷定义不明确。"),
        ("B.评分不规范风险", "业绩加分", Severity.medium, ["业绩加分"], "业绩分需核查与采购需求的关联性和分值合理性。"),
        ("D.合同与验收风险", "采购人单方决定", Severity.high, ["以采购人意见为准", "采购人说了算"], "争议或验收机制明显偏向采购人。"),
        ("D.合同与验收风险", "验收标准不明确", Severity.medium, ["验收标准", "验收"], "需核查验收标准是否清晰、客观、可执行。"),
        ("D.合同与验收风险", "付款节点不明确", Severity.medium, ["付款方式以正式合同为准", "付款节点"], "付款节点需与履约节点匹配并明确。"),
        ("E.模板残留风险", "模板占位或旧模板残留", Severity.low, ["另行通知", "详见附件", "以正式合同为准"], "存在模板依赖或未清理表述，需要人工核验。"),
        ("政策条款风险", "中小企业政策冲突", Severity.medium, ["中小企业", "价格扣除"], "需核查是否存在专门面向中小企业 yet 保留价格扣除的冲突。"),
    ]
    hits: list[RiskHit] = []
    lines = text.splitlines()
    for group, rule_name, severity, keywords, rationale in keyword_rules:
        for line_no, line in enumerate(lines, start=1):
            if any(keyword in line for keyword in keywords):
                hits.append(
                    RiskHit(
                        risk_group=group,
                        rule_name=rule_name,
                        severity=severity,
                        matched_text=line[:120],
                        rationale=rationale,
                        source_anchor=f"line:{line_no}",
                    )
                )
                break

    for line_no, line in enumerate(lines, start=1):
        if ("评分" in line or "评审" in line) and any(token in line for token in ["优", "良", "中", "差"]):
            hits.append(
                RiskHit(
                    risk_group="B.评分不规范风险",
                    rule_name="主观评分表述",
                    severity=Severity.medium,
                    matched_text=line[:120],
                    rationale="评分可能存在主观分档，需要量化标准支撑。",
                    source_anchor=f"line:{line_no}",
                )
            )
            break

    has_goods = "货物" in text
    has_service_delivery = "运维" in text or "实施" in text or "服务" in text
    if has_goods and has_service_delivery:
        for line_no, line in enumerate(lines, start=1):
            if "货物" in line or "运维" in line or "实施" in line or "服务" in line:
                hits.append(
                    RiskHit(
                        risk_group="C.项目属性错配风险",
                        rule_name="货物服务属性冲突",
                        severity=Severity.high,
                        matched_text=line[:120],
                        rationale="项目属性与履约内容可能存在错配。",
                        source_anchor=f"line:{line_no}",
                    )
                )
                break
    return hits


def convert_risk_hits_to_findings(risk_hits: Iterable[RiskHit]) -> list[Finding]:
    results: list[Finding] = []
    for hit in risk_hits:
        finding_type = (
            FindingType.confirmed_issue
            if hit.severity in {Severity.high, Severity.critical}
            else FindingType.warning
        )
        next_action = (
            "对照原条款逐项修改并复核关联章节。"
            if hit.severity in {Severity.high, Severity.critical}
            else "补充量化标准或说明设置依据。"
        )
        results.append(
            Finding(
                dimension=hit.risk_group,
                finding_type=finding_type,
                severity=hit.severity,
                title=hit.rule_name,
                rationale=hit.rationale,
                evidence=[Evidence(quote=hit.matched_text, section_hint=hit.source_anchor)],
                confidence=0.8 if hit.severity in {Severity.high, Severity.critical} else 0.68,
                next_action=next_action,
            )
        )
    return results


def build_recommendations(findings: list[Finding]) -> list[Recommendation]:
    recommendations: list[Recommendation] = []
    mapping = {
        "指定品牌/原厂限制": "删除品牌或原厂倾向性要求，改为描述满足采购需求的功能、性能和服务标准。",
        "产地厂家商标限制": "删除对产地、厂家、商标的倾向性限制，保留必要的技术兼容性表达。",
        "专利要求": "删除“必须具备相关专利”要求，改为要求供应商保证不侵犯第三方知识产权。",
        "认证证书要求": "仅保留与项目直接相关且有必要性的证书要求，并说明设置依据。",
        "检测报告要求": "明确检测报告的适用范围、时间要求和必要性，避免作为普遍门槛。",
        "主观评分表述": "将主观评分细化为可量化、可比对的指标，避免仅用优良中差分档。",
        "业绩加分": "压缩与项目无直接关联的业绩加分项，明确业绩范围、期限与证明口径。",
        "采购人单方决定": "删除“以采购人意见为准”等单方决定表述，改为客观验收和争议解决机制。",
        "付款节点不明确": "将付款节点与履约节点、验收节点一一对应，并写明触发条件。",
        "模板占位或旧模板残留": "清理“详见附件”“另行通知”“以正式合同为准”等模板残留，补足正式条款。",
        "项目属性 vs 履约内容": "统一项目属性与履约内容表述，必要时调整采购方式、合同类型和评分结构。",
        "技术要求 vs 评分标准": "确保评分因素直接对应技术需求，并补足量化评分细则。",
        "预算金额 vs 最高限价": "统一预算金额与最高限价口径，避免金额要素前后缺失或冲突。",
        "中小企业政策 vs 价格扣除政策": "统一中小企业政策口径，专门面向中小企业项目不再适用价格扣除。",
        "专门面向中小企业却仍保留价格扣除": "删除专门面向中小企业项目中的价格扣除模板，统一政策适用口径。",
        "服务项目声明函类型疑似错用货物模板": "按服务项目重置中小企业声明函模板，避免继续沿用制造商口径。",
        "货物项目声明函类型不完整": "补全货物项目声明函中的制造商相关内容，确保声明函类型与项目属性一致。",
        "预留份额采购但比例信息不明确": "补充分包比例、预留比例和小微企业比例要求，确保中小企业政策可执行。",
        "性别限制": "删除与岗位履职无直接关系的性别限制，仅保留合法必要的履职要求。",
        "年龄限制": "删除与岗位履职无直接关系的年龄限制，改为岗位能力和资格要求。",
        "身高限制": "删除与岗位履职无直接关系的身高限制，避免形成人员条件歧视。",
        "容貌体形要求": "删除容貌、体形等与履职无直接关系的要求，改为客观岗位职责描述。",
        "采购人审批录用": "删除采购人对供应商内部录用审批的条款，改为采购人核验关键岗位资格。",
        "采购人批准更换": "将人员更换控制改为关键岗位资格核验，不宜要求采购人审批内部任免。",
        "采购人直接指挥": "删除采购人直接指挥供应商员工的表述，明确双方为合同管理关系。",
        "人员证明材料负担偏重": "精简社保、学历、职称等叠加证明要求，避免不必要抬高投标成本。",
        "采购人单方解释或决定条款": "删除采购人单方解释或决定条款，改为客观标准和双方确认机制。",
        "考核条款可能控制付款或履约评价": "细化考核指标、评分方法和证据要求，避免考核条款成为主观付款控制工具。",
        "扣款机制可能过度依赖单方考核": "明确扣款公式、程序和证据要求，避免由采购人单方主观评价直接扣款。",
        "解约条件可能过宽": "收窄解约触发条件，并补充通知、整改和申辩程序。",
        "尾款支付与考核条款联动风险": "避免大额尾款仅由主观考核决定，需将支付条件绑定客观履约节点和量化指标。",
        "货物项目混入大量服务履约内容": "重新核对项目属性、品目和合同结构，必要时明确混合采购主次关系或调整项目定性。",
        "服务项目混入货物化履约口径": "清理制造商、规格型号、质保期等货物化模板术语，统一服务项目履约口径。",
        "项目属性与所属行业口径疑似不一致": "重新核对所属行业填写与项目属性、声明函模板之间的一致性。",
        "家具项目出现非典型结构性术语": "核查家具项目中设计、测试等术语是否属于旧模板残留，并及时删除或改写。",
        "项目属性与声明函模板口径冲突": "统一项目属性、中小企业声明函和合同口径，避免服务/货物模板混用。",
        "一般模板残留": "清理待定、空白、另行通知等模板性表述，减少执行歧义。",
        "服务项目保留货物类声明函模板": "删除服务项目中的制造商等货物类声明函内容，替换为服务项目适用模板。",
        "专门面向中小企业却保留价格扣除模板": "删除价格扣除模板并统一中小企业政策口径，防止评审执行冲突。",
        "物业项目出现货物化模板术语": "删除与物业服务无关的质保期等货物术语，统一合同与验收口径。",
        "家具项目出现不相关模板术语": "清理与家具采购无关的设计、测试等模板术语，避免影响评审与履约理解。",
    }
    seen: set[str] = set()
    for finding in findings:
        if finding.title in seen:
            continue
        suggestion = mapping.get(finding.title)
        if suggestion:
            recommendations.append(Recommendation(related_issue=finding.title, suggestion=suggestion))
            seen.add(finding.title)
    return recommendations

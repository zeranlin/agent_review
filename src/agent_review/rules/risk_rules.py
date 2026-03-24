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

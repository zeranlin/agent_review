from __future__ import annotations

import re
from typing import Iterable

from ...models import Evidence, Finding, FindingType, Recommendation, RiskHit, Severity


def match_risk_rules(text: str) -> list[RiskHit]:
    keyword_rules = [
        ("A.限制竞争风险", "指定品牌/原厂限制", Severity.high, ["指定品牌", "原厂授权", "原厂证明", "原厂服务", "原厂服务团队"], "存在指定品牌或原厂倾向，需核查是否构成排斥竞争。"),
        ("A.限制竞争风险", "产地厂家商标限制", Severity.high, ["产地", "厂家", "商标"], "存在对产地、厂家或商标的倾向性表达。"),
        ("A.限制竞争风险", "专利要求", Severity.high, ["专利"], "出现专利要求，需核查是否属于不必要门槛。"),
        ("A.限制竞争风险", "刚性门槛型专利要求", Severity.high, ["必须具备", "须具备", "应具备", "必须具有"], "将专利作为刚性门槛，存在明显限制竞争风险。"),
        ("A.限制竞争风险", "认证证书要求", Severity.medium, ["认证证书", "证书"], "出现证书要求，需判断是否与项目需求直接相关。"),
        ("A.限制竞争风险", "检测报告要求", Severity.medium, ["检测报告"], "出现检测报告要求，需判断是否必要且合理。"),
        ("A.限制竞争风险", "投标阶段证书或检测报告负担过重", Severity.high, ["检测报告", "认证证书", "管理体系认证"], "如要求在投标阶段普遍提交检测报告或大量认证证书，可能形成超必要限度门槛。"),
        ("B.评分不规范风险", "无缺陷得满分", Severity.medium, ["无缺陷得满分"], "评分裁量口径过宽，缺陷定义不明确。"),
        ("B.评分不规范风险", "业绩加分", Severity.medium, ["业绩加分"], "业绩分需核查与采购需求的关联性和分值合理性。"),
        ("B.评分不规范风险", "证书类评分分值偏高", Severity.high, ["资质证书", "管理体系认证情况"], "证书类评分分值偏高，可能对中小企业形成不利影响。"),
        ("D.合同与验收风险", "采购人单方决定", Severity.high, ["以采购人意见为准", "采购人说了算"], "争议或验收机制明显偏向采购人。"),
        ("D.合同与验收风险", "验收标准不明确", Severity.medium, ["验收标准", "验收"], "需核查验收标准是否清晰、客观、可执行。"),
        ("D.合同与验收风险", "付款节点不明确", Severity.medium, ["付款方式以正式合同为准", "付款节点"], "付款节点需与履约节点匹配并明确。"),
        ("E.模板残留风险", "模板占位或旧模板残留", Severity.low, ["另行通知", "详见附件", "以正式合同为准"], "存在模板依赖或未清理表述，需要人工核验。"),
        ("E.模板残留风险", "合同文本存在明显模板残留", Severity.high, ["X年", "于事件发生后", "设计、测试、验收"], "合同文本存在明显旧模板占位或错行业术语，影响明确性和可执行性。"),
        ("政策条款风险", "中小企业政策冲突", Severity.medium, ["中小企业", "价格扣除"], "需核查是否存在专门面向中小企业 yet 保留价格扣除的冲突。"),
    ]
    hits: list[RiskHit] = []
    lines = text.splitlines()
    for group, rule_name, severity, keywords, rationale in keyword_rules:
        for line_no, line in enumerate(lines, start=1):
            if rule_name == "产地厂家商标限制":
                if any(token in line for token in ["商标权", "知识产权", "声明函", "残疾人福利性单位", "注册商标", "不会产生", "侵权", "厂家出厂标准", "原厂正品", "原产地证明", "进口设备", "同品牌"]):
                    continue
                if not any(token in line for token in ["指定", "限定", "必须", "要求", "提供", "采用"]):
                    continue
            if rule_name == "专利要求":
                if any(token in line for token in ["专利权", "知识产权", "侵犯", "纠纷", "不会产生"]):
                    continue
            if rule_name == "刚性门槛型专利要求":
                if "专利" not in line:
                    continue
                if any(token in line for token in ["专利权", "知识产权", "侵犯", "纠纷", "不会产生"]):
                    continue
            if rule_name == "投标阶段证书或检测报告负担过重":
                if not any(token in line for token in ["投标文件", "评分", "评审", "提供", "提交", "具备"]):
                    continue
            if rule_name == "证书类评分分值偏高":
                if "分" not in line:
                    continue
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

    for line_no, line in enumerate(lines, start=1):
        if any(token in line for token in ["资产总额", "从业人员", "纳税额", "成立时间满", "成立年限", "成立满"]) and any(
            token in line for token in ["得分", "得5分", "得2分", "得3分", "评分", "评审", "分值", "满分"]
        ):
            metric_rules = [
                ("资产总额", "资产总额被设为评分因素", "将供应商资产总额作为评分因素，属于以企业规模条件替代项目履约能力的高风险做法。"),
                ("从业人员", "从业人员被设为评分因素", "将供应商从业人员数量作为评分因素，属于以企业规模条件替代项目履约能力的高风险做法。"),
                ("纳税额", "纳税额被设为评分因素", "将供应商纳税额作为评分因素，属于以经营结果替代项目履约能力的高风险做法。"),
                ("成立时间满", "成立年限被设为评分因素", "将供应商成立年限作为评分因素，容易形成对新设企业的不当限制。"),
                ("成立年限", "成立年限被设为评分因素", "将供应商成立年限作为评分因素，容易形成对新设企业的不当限制。"),
                ("成立满", "成立年限被设为评分因素", "将供应商成立年限作为评分因素，容易形成对新设企业的不当限制。"),
            ]
            for token, rule_name, rationale in metric_rules:
                if token not in line:
                    continue
                hits.append(
                    RiskHit(
                        risk_group="B.评分不规范风险",
                        rule_name=rule_name,
                        severity=Severity.high,
                        matched_text=line[:160],
                        rationale=rationale,
                        source_anchor=f"line:{line_no}",
                    )
                )

    for line_no, line in enumerate(lines, start=1):
        next_line = lines[line_no] if line_no < len(lines) else ""
        combined_line = f"{line} {next_line}"
        if "价格分计算方法" in line and any(token in combined_line for token in ["中间价优先法", "平均值作为评标基准价", "去掉最高价和最低价"]):
            hits.append(
                RiskHit(
                    risk_group="B.评分不规范风险",
                    rule_name="综合评分法价格分未采用低价优先法",
                    severity=Severity.high,
                    matched_text=combined_line[:180],
                    rationale="综合评分法下价格分采用中间价优先法或平均价法，偏离低价优先法定口径，需优先复核。",
                    source_anchor=f"line:{line_no}",
                )
            )
            break

    for line_no, line in enumerate(lines, start=1):
        if re.search(r"GB/T\s*99999-2024", line):
            hits.append(
                RiskHit(
                    risk_group="技术参数与标准风险",
                    rule_name="疑似使用不存在的技术标准",
                    severity=Severity.high,
                    matched_text=line[:160],
                    rationale="文件中出现疑似不存在或异常占位的标准编号，需核查标准真实性和现行有效性。",
                    source_anchor=f"line:{line_no}",
                )
            )
            break

    interval_conflict_candidates: dict[str, list[tuple[int, str]]] = {}
    for line_no, line in enumerate(lines, start=1):
        compact = re.sub(r"\s+", "", line)
        if "±" in compact and any(token in compact for token in ["偏差", "偏离", "允许"]):
            key = _parameter_subject_key(compact)
            interval_conflict_candidates.setdefault(key, []).append((line_no, line))
        if any(token in compact for token in ["不允许正偏离", "不允许负偏离", "不得偏离", "不接受偏离", "≤"]) and any(
            token in compact for token in ["重量", "精度", "响应时间", "参数"]
        ):
            key = _parameter_subject_key(compact)
            interval_conflict_candidates.setdefault(key, []).append((line_no, line))

    for key, items in interval_conflict_candidates.items():
        has_strict = any(any(token in item[1] for token in ["不允许正偏离", "不允许负偏离", "不得偏离", "不接受偏离", "≤"]) for item in items)
        has_tolerance = any(any(token in item[1] for token in ["±", "偏差", "允许"]) for item in items)
        if has_strict and has_tolerance and len(items) >= 2:
            first_line = items[0][0]
            hits.append(
                RiskHit(
                    risk_group="技术参数与标准风险",
                    rule_name="同一技术参数区间说明冲突",
                    severity=Severity.high,
                    matched_text=f"{items[0][1][:80]} | {items[1][1][:80]}",
                    rationale="同一参数同时出现刚性限制和允许偏差口径，技术参数区间说明前后冲突。",
                    source_anchor=f"line:{first_line}",
                )
            )
            break

    for line_no, line in enumerate(lines, start=1):
        compact = re.sub(r"\s+", "", line)
        if re.search(r"(响应时间|精度)[:：]?\d+(\.\d+)?(?:-\d+(\.\d+)?)?(ms|mm)", compact):
            hits.append(
                RiskHit(
                    risk_group="技术参数与标准风险",
                    rule_name="技术参数区间说明不足",
                    severity=Severity.high,
                    matched_text=line[:160],
                    rationale="响应时间、精度等敏感技术参数直接以具体值或区间表达，但未同步说明设置依据和区间判定逻辑，易形成评审争议。",
                    source_anchor=f"line:{line_no}",
                )
            )
            break
        if re.search(r"(精度|范围|区间)[:：]?\d+(\.\d+)?-\d+(\.\d+)?", compact) or re.search(r"\b\d+(\.\d+)?-\d+(\.\d+)?mm\b", compact):
            if not any(token in text for token in ["区间要求为", "区间说明", "涉及区间的参数", "区间参数"]):
                hits.append(
                    RiskHit(
                        risk_group="技术参数与标准风险",
                        rule_name="技术参数区间说明不足",
                        severity=Severity.high,
                        matched_text=line[:160],
                        rationale="技术参数使用区间表达，但未见对应区间说明、偏离判断或取值逻辑，易导致评审口径不清。",
                        source_anchor=f"line:{line_no}",
                    )
                )
                break

    for line_no, line in enumerate(lines, start=1):
        if any(token in line for token in ["操作体验", "界面友好美观", "设计美观", "人体工程学设计", "良好的操作体验", "友好美观"]):
            hits.append(
                RiskHit(
                    risk_group="技术参数与标准风险",
                    rule_name="技术要求存在主观描述",
                    severity=Severity.high,
                    matched_text=line[:180],
                    rationale="技术要求采用主观审美或体验型描述，缺少可验证、可量化的客观标准，容易形成指向性要求。",
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
    for line_no, line in enumerate(lines, start=1):
        if any(token in line for token in ["软件企业认定证书", "ITSS", "利润率", "财务报告"]) and any(
            token in line for token in ["评分", "评审", "得分", "分值", "分"]
        ):
            hits.append(
                RiskHit(
                    risk_group="B.评分不规范风险",
                    rule_name="行业无关证书或财务指标被纳入评分",
                    severity=Severity.high,
                    matched_text=line[:120],
                    rationale="评分中出现与项目履约能力相关性不足的证书或财务指标，需核查是否构成变相限制竞争。",
                    source_anchor=f"line:{line_no}",
                )
            )
            break

    for line_no, line in enumerate(lines, start=1):
        if any(token in line for token in ["无缺陷得满分", "每缺项扣", "每处缺陷扣", "扣2.5分"]):
            hits.append(
                RiskHit(
                    risk_group="B.评分不规范风险",
                    rule_name="方案评分量化不足",
                    severity=Severity.high,
                    matched_text=line[:120],
                    rationale="方案评分采用缺项/缺陷扣分模板化表述，但缺陷定义和量化标准不足，裁量空间较大。",
                    source_anchor=f"line:{line_no}",
                )
            )
            break
    for line_no, line in enumerate(lines, start=1):
        if "质量保证金" in line and any(token in line for token in ["履约担保", "履约保证金", "无息退还", "银行转账"]):
            hits.append(
                RiskHit(
                    risk_group="D.合同与验收风险",
                    rule_name="履约保证金转质量保证金或长期无息占压",
                    severity=Severity.high,
                    matched_text=line[:180],
                    rationale="履约担保条款同时叠加银行转账、质量保证金和无息退还安排，需核查是否形成异常资金占压或责任转嫁。",
                    source_anchor=f"line:{line_no}",
                )
            )
            break
    for line_no, line in enumerate(lines, start=1):
        if "第三方检测费用" in line and "中标人承担" in line:
            hits.append(
                RiskHit(
                    risk_group="D.合同与验收风险",
                    rule_name="第三方检测费用无论结果均由中标人承担",
                    severity=Severity.high,
                    matched_text=line[:180],
                    rationale="将第三方检测费用无论检测结果如何均由中标人承担，容易形成不对等风险转嫁和验收负担外扩。",
                    source_anchor=f"line:{line_no}",
                )
            )
            break
    for line_no, line in enumerate(lines, start=1):
        if "投标报价不得低于预算金额的" in line and "无效投标" in line:
            hits.append(
                RiskHit(
                    risk_group="A.限制竞争风险",
                    rule_name="以预算金额比例设最低报价门槛",
                    severity=Severity.high,
                    matched_text=line[:180],
                    rationale="直接以预算金额比例设置最低报价门槛并据此否决投标，需核查是否以刚性价格下限替代异常低价审查机制。",
                    source_anchor=f"line:{line_no}",
                )
            )
            break
    certificate_score = 0.0
    for line in lines:
        if not any(token in line for token in ["资质证书", "管理体系认证情况", "认证证书"]):
            continue
        match = re.search(r"\((\d+(?:\.\d+)?)分\)", line)
        if match:
            certificate_score += float(match.group(1))
    if certificate_score >= 8:
        for line_no, line in enumerate(lines, start=1):
            if any(token in line for token in ["资质证书", "管理体系认证情况", "认证证书"]):
                hits.append(
                    RiskHit(
                        risk_group="B.评分不规范风险",
                        rule_name="证书类评分分值偏高",
                        severity=Severity.high,
                        matched_text=line[:120],
                        rationale=f"证书类评分分值累计约 {certificate_score:.1f} 分，权重疑似偏高。",
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
                legal_basis=hit.legal_basis,
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
        "刚性门槛型专利要求": "删除将专利作为刚性门槛的表述，改为要求供应商保证不侵犯第三方知识产权并满足功能质量标准。",
        "认证证书要求": "仅保留与项目直接相关且有必要性的证书要求，并说明设置依据。",
        "检测报告要求": "明确检测报告的适用范围、时间要求和必要性，避免作为普遍门槛。",
        "投标阶段证书或检测报告负担过重": "区分投标阶段与履约验收阶段材料，仅保留必要的投标阶段证明材料要求。",
        "主观评分表述": "将主观评分细化为可量化、可比对的指标，避免仅用优良中差分档。",
        "业绩加分": "压缩与项目无直接关联的业绩加分项，明确业绩范围、期限与证明口径。",
        "行业无关证书或财务指标被纳入评分": "删除与项目履约能力无直接关联的证书、利润率或财务类评分项，仅保留与本项目相关的客观指标。",
        "方案评分量化不足": "将实施方案、保障方案、后续服务等评分项细化为客观、量化、可比的评分标准，避免仅按缺陷扣分。",
        "证书类评分分值偏高": "压缩证书类评分分值，避免证书评分权重明显高于项目实际履约相关性。",
        "资产总额被设为评分因素": "删除以资产总额作为评分因素的条款，改为与项目履约直接相关的能力指标。",
        "从业人员被设为评分因素": "删除以从业人员数量作为评分因素的条款，改为与项目团队配置直接相关的客观要求。",
        "纳税额被设为评分因素": "删除以纳税额作为评分因素的条款，避免将经营结果替代项目履约评价。",
        "成立年限被设为评分因素": "删除以成立年限作为评分因素的条款，避免对新设企业形成不当限制。",
        "综合评分法价格分未采用低价优先法": "将综合评分法中的价格分改回低价优先法，并明确价格基准价计算口径。",
        "采购人单方决定": "删除“以采购人意见为准”等单方决定表述，改为客观验收和争议解决机制。",
        "付款节点不明确": "将付款节点与履约节点、验收节点一一对应，并写明触发条件。",
        "模板占位或旧模板残留": "清理“详见附件”“另行通知”“以正式合同为准”等模板残留，补足正式条款。",
        "合同文本存在明显模板残留": "清理合同中的X年、空白期限、设计测试等旧模板残留，统一为当前项目适用条款。",
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
        "项目属性与合同类型口径疑似不一致": "核对项目属性、采购内容与合同类型的一致性，避免以货物采购名义承接持续性作业服务。",
        "货物采购混入持续性作业服务": "重新核查采购标的构成和项目定性，必要时调整采购属性、合同类型和评审设置。",
        "合同条款出现非本行业成果模板表述": "删除与当前行业场景不匹配的成果交付、成果保密等模板术语，统一合同履约口径。",
        "验收标准存在优胜原则或单方弹性判断": "删除优胜原则或单方弹性判断表述，改为事先明确、客观、可执行的验收标准。",
        "预算金额与面向中小企业采购金额口径异常": "统一预算金额、最高限价和面向中小企业采购金额的口径，避免错填或混用。",
        "面向中小企业采购金额与最高限价疑似混用": "核对面向中小企业采购金额与最高限价字段，防止将最高限价误填为政策金额。",
        "疑似使用不存在的技术标准": "核查标准编号和版本有效性，删除疑似不存在或失效的技术标准引用。",
        "技术参数区间说明不足": "补充区间参数的偏离判断、取值逻辑和评审口径，避免区间表达不清。",
        "同一技术参数区间说明冲突": "统一同一参数的偏差、偏离和取值规则，删除前后冲突的区间说明。",
        "技术要求存在主观描述": "将体验、美观、友好等主观表述改写为可量化、可核验的客观技术指标。",
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


def _parameter_subject_key(text: str) -> str:
    for token in ["设备重量", "重量", "手术机械臂精度", "精度", "产品响应时间", "响应时间"]:
        if token in text:
            return token
    return "generic_parameter"

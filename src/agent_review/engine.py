from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .checklist import DEFAULT_DIMENSIONS
from .models import (
    ConclusionLevel,
    ConsistencyCheck,
    Evidence,
    ExtractedClause,
    FileInfo,
    FileType,
    Finding,
    FindingType,
    Recommendation,
    ReviewDimension,
    ReviewReport,
    RiskHit,
    SectionIndex,
    Severity,
)


class TenderReviewEngine:
    """A minimal deterministic review harness.

    This is intentionally simple: it makes the review loop executable before
    integrating OCR, retrieval, or LLM-backed reasoning.
    """

    def __init__(self, dimensions: list[ReviewDimension] | None = None) -> None:
        self.dimensions = dimensions or DEFAULT_DIMENSIONS

    def review_text(self, text: str, document_name: str = "input.txt") -> ReviewReport:
        normalized_text = self._normalize_text(text)
        file_type = self._detect_file_type(normalized_text)
        file_info = self._build_file_info(document_name, normalized_text, file_type)
        scope_statement = self._build_scope_statement(file_info)
        section_index = self._locate_sections(normalized_text)
        extracted_clauses = self._extract_clauses(normalized_text)
        risk_hits = self._match_risk_rules(normalized_text)
        consistency_checks = self._check_consistency(normalized_text)
        findings: list[Finding] = []
        manual_review_queue: list[str] = []
        reviewed_dimensions: list[str] = []

        for dimension in self.dimensions:
            reviewed_dimensions.append(dimension.display_name)
            dimension_findings = self._review_dimension(normalized_text, dimension)
            findings.extend(dimension_findings)
            for finding in dimension_findings:
                if finding.finding_type == FindingType.manual_review_required:
                    manual_review_queue.append(finding.title)

        findings.extend(self._convert_risk_hits_to_findings(risk_hits))
        findings.extend(self._convert_consistency_checks_to_findings(consistency_checks))

        manual_review_queue = list(dict.fromkeys(manual_review_queue))
        relative_strengths = self._collect_relative_strengths(section_index, findings)
        recommendations = self._build_recommendations(findings)
        overall_conclusion = self._derive_conclusion(findings)
        summary = self._build_summary(findings, manual_review_queue, overall_conclusion)
        return ReviewReport(
            file_info=file_info,
            scope_statement=scope_statement,
            overall_conclusion=overall_conclusion,
            summary=summary,
            findings=findings,
            relative_strengths=relative_strengths,
            section_index=section_index,
            extracted_clauses=extracted_clauses,
            risk_hits=risk_hits,
            consistency_checks=consistency_checks,
            recommendations=recommendations,
            manual_review_queue=manual_review_queue,
            reviewed_dimensions=reviewed_dimensions,
        )

    def review_file(self, path: str | Path) -> ReviewReport:
        target = Path(path)
        text = target.read_text(encoding="utf-8")
        return self.review_text(text=text, document_name=target.name)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())

    @staticmethod
    def _detect_file_type(text: str) -> FileType:
        rules = [
            (FileType.complete_tender, ["投标邀请", "投标人须知", "评标办法", "采购需求"]),
            (FileType.procurement_requirement, ["采购需求", "技术要求", "商务要求"]),
            (FileType.scoring_detail, ["评分标准", "评标办法", "综合评分"]),
            (FileType.contract_draft, ["合同条款", "违约责任", "争议解决"]),
        ]
        scores: dict[FileType, int] = {}
        for file_type, keywords in rules:
            scores[file_type] = sum(1 for item in keywords if item in text)

        best_type = max(scores, key=scores.get, default=FileType.unknown)
        best_score = scores.get(best_type, 0)
        multiple_hits = sum(1 for score in scores.values() if score >= 2)
        if multiple_hits >= 2:
            return FileType.mixed_document
        if best_score == 0:
            return FileType.unknown
        return best_type

    def _build_file_info(self, document_name: str, text: str, file_type: FileType) -> FileInfo:
        suffix = Path(document_name).suffix.lower().lstrip(".") or "txt"
        if file_type == FileType.complete_tender:
            review_scope = "可覆盖招标文件主体结构、资格、评分、合同与流程的完整性审查。"
            review_boundary = "如缺少公告、澄清、附件，仍需对附件依赖条款单独复核。"
        elif file_type == FileType.procurement_requirement:
            review_scope = "以采购需求、技术商务条款和限制竞争风险为主。"
            review_boundary = "不宜对投标须知、废标条款、开标程序作完整定性。"
        elif file_type == FileType.scoring_detail:
            review_scope = "以评分标准、量化口径和评分关联性审查为主。"
            review_boundary = "无法单独评价采购流程和合同条款的完整合规性。"
        elif file_type == FileType.contract_draft:
            review_scope = "以合同风险分配、付款、验收和争议解决条款审查为主。"
            review_boundary = "无法单独评价资格条件、评分办法和投标程序。"
        else:
            review_scope = "当前按可识别文本开展有限范围审查。"
            review_boundary = "文件类型不够明确，结论应结合完整采购材料复核。"

        return FileInfo(
            document_name=document_name,
            format_hint=suffix,
            text_length=len(text),
            file_type=file_type,
            review_scope=review_scope,
            review_boundary=review_boundary,
        )

    @staticmethod
    def _build_scope_statement(file_info: FileInfo) -> str:
        return (
            f"本次审查材料为《{file_info.document_name}》，识别类型为“{file_info.file_type.value}”。"
            f"审查范围：{file_info.review_scope} 审查边界：{file_info.review_boundary}"
        )

    @staticmethod
    def _locate_sections(text: str) -> list[SectionIndex]:
        targets = [
            "项目概况",
            "预算金额",
            "最高限价",
            "资格要求",
            "特定资格要求",
            "技术要求",
            "商务要求",
            "评分标准",
            "合同条款",
            "付款条款",
            "验收条款",
            "违约责任",
            "中小企业政策条款",
            "联合体与分包条款",
            "样品/演示条款",
            "保证金条款",
        ]
        lines = text.splitlines()
        results: list[SectionIndex] = []
        for target in targets:
            anchor = ""
            for line_no, line in enumerate(lines, start=1):
                if any(token in line for token in target.split("/")):
                    anchor = f"line:{line_no}"
                    break
            results.append(SectionIndex(section_name=target, located=bool(anchor), anchor=anchor))
        return results

    @staticmethod
    def _extract_clauses(text: str) -> list[ExtractedClause]:
        patterns = [
            ("项目基本信息", "项目名称", ["项目名称"]),
            ("项目基本信息", "项目编号", ["项目编号"]),
            ("项目基本信息", "采购方式", ["采购方式", "公开招标", "竞争性磋商", "竞争性谈判"]),
            ("项目基本信息", "项目属性", ["货物", "工程", "服务"]),
            ("项目基本信息", "预算金额", ["预算金额"]),
            ("项目基本信息", "最高限价", ["最高限价"]),
            ("项目基本信息", "合同履行期限", ["合同履行期限"]),
            ("资格条款", "一般资格要求", ["资格要求", "供应商资格"]),
            ("资格条款", "特定资格要求", ["特定资格要求", "资质要求"]),
            ("资格条款", "信用要求", ["信用要求"]),
            ("资格条款", "是否允许联合体", ["联合体"]),
            ("资格条款", "是否允许分包", ["分包"]),
            ("技术条款", "是否指定品牌", ["品牌", "原厂"]),
            ("技术条款", "是否要求专利", ["专利"]),
            ("技术条款", "是否要求检测报告", ["检测报告"]),
            ("技术条款", "是否要求认证证书", ["认证证书", "证书"]),
            ("技术条款", "是否设置★实质性条款", ["★"]),
            ("技术条款", "是否有限制产地厂家商标", ["产地", "厂家", "商标"]),
            ("评分条款", "评分方法", ["评分方法", "综合评分", "评标办法"]),
            ("评分条款", "证书加分", ["证书加分", "证书"]),
            ("评分条款", "业绩加分", ["业绩加分", "业绩"]),
            ("评分条款", "方案评分", ["方案评分", "实施方案"]),
            ("评分条款", "售后加分", ["售后"]),
            ("评分条款", "财务指标加分", ["财务指标", "利润率"]),
            ("合同条款", "付款节点", ["付款方式", "付款节点"]),
            ("合同条款", "验收标准", ["验收标准", "验收"]),
            ("合同条款", "争议解决方式", ["争议解决"]),
            ("合同条款", "违约责任", ["违约责任"]),
            ("合同条款", "质保期", ["质保期"]),
            ("合同条款", "履约保证金", ["履约保证金"]),
            ("政策条款", "是否专门面向中小企业", ["中小企业"]),
            ("政策条款", "所属行业划分", ["所属行业"]),
            ("政策条款", "是否仍保留价格扣除条款", ["价格扣除"]),
            ("政策条款", "是否涉及进口产品", ["进口产品"]),
        ]
        lines = text.splitlines()
        clauses: list[ExtractedClause] = []
        for category, field_name, keywords in patterns:
            for line_no, line in enumerate(lines, start=1):
                if any(keyword in line for keyword in keywords):
                    clauses.append(
                        ExtractedClause(
                            category=category,
                            field_name=field_name,
                            content=line[:120],
                            source_anchor=f"line:{line_no}",
                        )
                    )
                    break
        return clauses

    @staticmethod
    def _match_risk_rules(text: str) -> list[RiskHit]:
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

    @staticmethod
    def _check_consistency(text: str) -> list[ConsistencyCheck]:
        checks: list[ConsistencyCheck] = []
        checks.append(
            ConsistencyCheck(
                topic="项目属性 vs 履约内容",
                status="issue" if ("货物" in text and ("运维" in text or "实施" in text)) else "ok",
                detail=(
                    "文本同时出现货物属性与运维/实施服务内容，需核查项目属性定性。"
                    if ("货物" in text and ("运维" in text or "实施" in text))
                    else "未发现明显属性与履约内容冲突。"
                ),
            )
        )
        checks.append(
            ConsistencyCheck(
                topic="预算金额 vs 最高限价",
                status="issue" if ("最高限价" in text and "预算金额" not in text) else "ok",
                detail="出现最高限价但未发现预算金额，建议复核金额口径一致性。"
                if ("最高限价" in text and "预算金额" not in text)
                else "预算与限价未见明显冲突。",
            )
        )
        checks.append(
            ConsistencyCheck(
                topic="中小企业政策 vs 价格扣除政策",
                status="issue" if ("专门面向中小企业" in text and "价格扣除" in text) else "ok",
                detail="专门面向中小企业项目仍出现价格扣除条款，可能存在政策口径冲突。"
                if ("专门面向中小企业" in text and "价格扣除" in text)
                else "未发现明显中小企业政策冲突。",
            )
        )
        checks.append(
            ConsistencyCheck(
                topic="技术要求 vs 评分标准",
                status="issue" if ("综合评分" in text and "技术要求" not in text) else "ok",
                detail="出现综合评分，但技术要求定位不足，需核查评分依据。"
                if ("综合评分" in text and "技术要求" not in text)
                else "技术要求与评分标准未见明显脱节。",
            )
        )
        checks.append(
            ConsistencyCheck(
                topic="联合体/分包条款前后一致性",
                status="issue" if ("联合体" in text and "分包" in text and "不得" in text and "允许" in text) else "ok",
                detail="联合体与分包条款中出现允许/禁止混用，需要人工核对前后文。"
                if ("联合体" in text and "分包" in text and "不得" in text and "允许" in text)
                else "未发现明显联合体/分包条款冲突。",
            )
        )
        return checks

    def _review_dimension(self, text: str, dimension: ReviewDimension) -> list[Finding]:
        lowered = text.lower()
        matched_triggers = [item for item in dimension.triggers if item.lower() in lowered]
        matched_missing_markers = [
            item for item in dimension.missing_markers if item.lower() in lowered
        ]

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

    @staticmethod
    def _convert_risk_hits_to_findings(risk_hits: Iterable[RiskHit]) -> list[Finding]:
        results: list[Finding] = []
        for hit in risk_hits:
            finding_type = FindingType.confirmed_issue if hit.severity in {Severity.high, Severity.critical} else FindingType.warning
            next_action = "对照原条款逐项修改并复核关联章节。" if hit.severity in {Severity.high, Severity.critical} else "补充量化标准或说明设置依据。"
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

    @staticmethod
    def _convert_consistency_checks_to_findings(
        checks: Iterable[ConsistencyCheck],
    ) -> list[Finding]:
        results: list[Finding] = []
        for check in checks:
            if check.status != "issue":
                continue
            results.append(
                Finding(
                    dimension="跨条款一致性检查",
                    finding_type=FindingType.warning,
                    severity=Severity.high,
                    title=check.topic,
                    rationale=check.detail,
                    evidence=[],
                    confidence=0.74,
                    next_action="核查相关章节并统一项目属性、金额口径、政策口径或合同表述。",
                )
            )
        return results

    @staticmethod
    def _collect_relative_strengths(
        section_index: list[SectionIndex], findings: list[Finding]
    ) -> list[str]:
        strengths: list[str] = []
        located_count = sum(1 for item in section_index if item.located)
        if located_count >= 4:
            strengths.append("关键章节已有一定覆盖，便于后续复核。")
        if not any(item.finding_type == FindingType.confirmed_issue for item in findings):
            strengths.append("当前文本未命中明确的实质性不合规强信号。")
        if not strengths:
            strengths.append("已形成结构化问题清单，便于采购人定向修改。")
        return strengths

    @staticmethod
    def _build_recommendations(findings: list[Finding]) -> list[Recommendation]:
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
                recommendations.append(
                    Recommendation(related_issue=finding.title, suggestion=suggestion)
                )
                seen.add(finding.title)
        return recommendations

    @staticmethod
    def _derive_conclusion(findings: list[Finding]) -> ConclusionLevel:
        high_count = sum(1 for item in findings if item.severity in {Severity.high, Severity.critical})
        confirmed_count = sum(1 for item in findings if item.finding_type == FindingType.confirmed_issue)
        if confirmed_count >= 3 or any(item.severity == Severity.critical for item in findings):
            return ConclusionLevel.reject
        if high_count >= 2:
            return ConclusionLevel.revise
        if any(item.finding_type in {FindingType.warning, FindingType.manual_review_required, FindingType.missing_evidence} for item in findings):
            return ConclusionLevel.optimize
        return ConclusionLevel.ready

    @staticmethod
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

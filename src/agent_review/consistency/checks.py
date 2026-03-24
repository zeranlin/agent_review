from __future__ import annotations

from typing import Iterable

from ..models import ConclusionLevel, ConsistencyCheck, Finding, FindingType, SectionIndex, Severity


def check_consistency(text: str) -> list[ConsistencyCheck]:
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


def convert_consistency_checks_to_findings(
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


def collect_relative_strengths(
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


def derive_conclusion(findings: list[Finding]) -> ConclusionLevel:
    high_count = sum(1 for item in findings if item.severity in {Severity.high, Severity.critical})
    confirmed_count = sum(1 for item in findings if item.finding_type == FindingType.confirmed_issue)
    if confirmed_count >= 3 or any(item.severity == Severity.critical for item in findings):
        return ConclusionLevel.reject
    if high_count >= 2:
        return ConclusionLevel.revise
    if any(
        item.finding_type in {FindingType.warning, FindingType.manual_review_required, FindingType.missing_evidence}
        for item in findings
    ):
        return ConclusionLevel.optimize
    return ConclusionLevel.ready

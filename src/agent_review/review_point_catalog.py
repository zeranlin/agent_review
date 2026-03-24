from __future__ import annotations

import re

from .models import ReviewPointCondition, ReviewPointDefinition, ReviewPoint, Severity


CATALOG: list[ReviewPointDefinition] = [
    ReviewPointDefinition(
        catalog_id="RP-SME-001",
        title="专门面向中小企业却仍保留价格扣除",
        dimension="中小企业政策风险",
        default_severity=Severity.high,
        scenario_tags=["policy"],
        required_conditions=[
            ReviewPointCondition("项目专门面向中小企业", [["专门面向中小企业"], ["中小企业采购"]]),
            ReviewPointCondition("文件仍保留价格扣除", [["价格扣除"]]),
        ],
        exclusion_conditions=[
            ReviewPointCondition("仅一般性政策说明无具体执行条款", [["政策说明"], ["不适用本项目"]]),
        ],
        basis_hint="专门面向中小企业采购项目不再适用价格评审优惠条款。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-REST-001",
        title="指定品牌/原厂限制",
        dimension="A.限制竞争风险",
        default_severity=Severity.high,
        scenario_tags=["goods"],
        required_conditions=[
            ReviewPointCondition("存在品牌或原厂指向", [["指定品牌", "品牌"], ["原厂"]]),
        ],
        exclusion_conditions=[
            ReviewPointCondition("仅供应商模板或声明文本", [["声明函"], ["证明书"]]),
        ],
        basis_hint="采购需求不得指向特定供应商或者产品来源。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONS-001",
        title="技术要求 vs 评分标准",
        dimension="跨条款一致性检查",
        default_severity=Severity.high,
        scenario_tags=["consistency"],
        required_conditions=[
            ReviewPointCondition("存在评分依据", [["评分", "综合评分"]]),
            ReviewPointCondition("技术要求支撑不足", [["技术要求"], ["未发现", "不足"]]),
        ],
        basis_hint="评分标准应与采购需求直接对应并量化。",
    ),
    ReviewPointDefinition(
        catalog_id="RP-CONTRACT-001",
        title="采购人单方解释或决定条款",
        dimension="合同与履约风险",
        default_severity=Severity.high,
        scenario_tags=["contract"],
        required_conditions=[
            ReviewPointCondition("存在单方决定表述", [["采购人意见为准", "采购人解释", "解释权", "采购人说了算"]]),
        ],
        exclusion_conditions=[
            ReviewPointCondition("仅程序性定义说明", [["采购代理机构"], ["名词解释"]]),
        ],
        basis_hint="不宜设置明显破坏合同公平的单方解释或决定条款。",
    ),
]


def resolve_review_point_definition(title: str, dimension: str, severity: Severity) -> ReviewPointDefinition:
    for item in CATALOG:
        if item.title == title and item.dimension == dimension:
            return item
    slug = _slugify(f"{dimension}-{title}")
    return ReviewPointDefinition(
        catalog_id=f"RP-GEN-{slug[:24].upper()}",
        title=title,
        dimension=dimension,
        default_severity=severity,
        scenario_tags=[],
        required_conditions=[],
        exclusion_conditions=[],
        basis_hint="当前审查点尚未在标准目录中沉淀完整适用要件。",
    )


def snapshot_catalog_for_points(review_points: list[ReviewPoint]) -> list[ReviewPointDefinition]:
    seen: set[str] = set()
    snapshot: list[ReviewPointDefinition] = []
    for point in review_points:
        definition = resolve_review_point_definition(point.title, point.dimension, point.severity)
        if definition.catalog_id in seen:
            continue
        seen.add(definition.catalog_id)
        snapshot.append(definition)
    return snapshot


def _slugify(text: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", text)
    return normalized.strip("-") or "GENERIC"

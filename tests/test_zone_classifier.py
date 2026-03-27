from agent_review.models import DocumentNode, SourceAnchor
from agent_review.ontology import NodeType, SemanticZoneType
from agent_review.structure.zone_classifier import classify_semantic_zones


def _node(
    node_id: str,
    *,
    node_type: NodeType,
    title: str,
    text: str,
    path: str,
    table_kind: str = "",
) -> DocumentNode:
    return DocumentNode(
        node_id=node_id,
        node_type=node_type,
        title=title,
        text=text,
        path=path,
        anchor=SourceAnchor(line_hint=f"line:{node_id}"),
        metadata={"table_kind": table_kind} if table_kind else {},
    )


def _zone_map(nodes: list[DocumentNode]):
    return {item.node_id: item for item in classify_semantic_zones(nodes)}


def test_zone_classifier_identifies_qualification_and_technical() -> None:
    qualification_node = _node(
        "q-1",
        node_type=NodeType.paragraph,
        title="投标人资格要求",
        text="投标人须具备相关资质。",
        path="ROOT > 第一章 招标公告 > 投标人资格要求",
    )
    technical_node = _node(
        "t-1",
        node_type=NodeType.paragraph,
        title="四、具体技术要求",
        text="家具甲醛释放量应符合国家标准。",
        path="ROOT > 第二章 招标项目需求 > 四、具体技术要求",
    )

    zones = _zone_map([qualification_node, technical_node])

    assert zones[qualification_node.node_id].zone_type == SemanticZoneType.qualification
    assert zones[technical_node.node_id].zone_type == SemanticZoneType.technical


def test_zone_classifier_uses_path_for_business_and_contract_boundaries() -> None:
    business_node = _node(
        "b-1",
        node_type=NodeType.paragraph,
        title="商务部分",
        text="交货和售后服务要求。",
        path="ROOT > 第二章 商务要求 > 商务部分",
    )
    contract_node = _node(
        "c-1",
        node_type=NodeType.paragraph,
        title="专用条款",
        text="付款方式为验收合格后支付。",
        path="ROOT > 第四章 合同条款 > 专用条款",
    )
    payment_node = _node(
        "c-2",
        node_type=NodeType.paragraph,
        title="付款方式为验收合格后支付。",
        text="付款方式为验收合格后支付。",
        path="ROOT > 第四章 合同条款 > 付款方式",
    )

    zones = _zone_map([business_node, contract_node, payment_node])

    assert zones[business_node.node_id].zone_type == SemanticZoneType.business
    assert zones[contract_node.node_id].zone_type == SemanticZoneType.contract
    assert zones[payment_node.node_id].zone_type == SemanticZoneType.contract


def test_zone_classifier_prefers_scoring_for_table_headers_and_rows() -> None:
    scoring_table = _node(
        "s-table",
        node_type=NodeType.table,
        title="第三章 评标办法",
        text="评审项 | 分值 | 评分标准\n检测报告 | 5 | 材料要求",
        path="ROOT > 第三章 评标办法 > 综合评分法评标信息",
        table_kind="scoring",
    )
    scoring_row = _node(
        "s-row",
        node_type=NodeType.table_row,
        title="检测报告 | 5 | 材料要求",
        text="检测报告 | 5 | 材料要求",
        path="ROOT > 第三章 评标办法 > 综合评分法评标信息 > row:2",
    )

    zones = _zone_map([scoring_table, scoring_row])

    assert zones[scoring_table.node_id].zone_type == SemanticZoneType.scoring
    assert zones[scoring_row.node_id].zone_type == SemanticZoneType.scoring


def test_zone_classifier_distinguishes_template_from_short_attachment_reference() -> None:
    template_node = _node(
        "a-1",
        node_type=NodeType.appendix,
        title="中小企业声明函（格式）详见附件1。",
        text="中小企业声明函（格式）详见附件1。",
        path="ROOT > 第四章 投标文件格式、附件 > 中小企业声明函（格式）详见附件1。",
    )
    appendix_node = _node(
        "a-2",
        node_type=NodeType.paragraph,
        title="详见附件2评审资料清单。",
        text="详见附件2评审资料清单。",
        path="ROOT > 第四章 附件 > 详见附件2评审资料清单。",
    )

    zones = _zone_map([template_node, appendix_node])

    assert zones[template_node.node_id].zone_type == SemanticZoneType.mixed_or_uncertain
    assert zones[appendix_node.node_id].zone_type == SemanticZoneType.appendix_reference


def test_zone_classifier_marks_policy_explanation_and_catalog_nodes() -> None:
    catalog_node = _node(
        "cat-1",
        node_type=NodeType.catalog_entry,
        title="第一章 招标公告",
        text="第一章 招标公告",
        path="ROOT > 目录 > 第一章 招标公告",
    )
    policy_node = _node(
        "p-1",
        node_type=NodeType.paragraph,
        title="依据《政府采购促进中小企业发展管理办法》执行。",
        text="依据《政府采购促进中小企业发展管理办法》执行。",
        path="ROOT > 政策说明 > 依据《政府采购促进中小企业发展管理办法》执行。",
    )

    zones = _zone_map([catalog_node, policy_node])

    assert zones[catalog_node.node_id].zone_type == SemanticZoneType.catalog_or_navigation
    assert zones[policy_node.node_id].zone_type == SemanticZoneType.policy_explanation


def test_zone_classifier_inherits_qualification_context_from_parent_heading() -> None:
    heading_node = _node(
        "q-head",
        node_type=NodeType.section,
        title="申请人的资格要求",
        text="申请人的资格要求",
        path="ROOT > 第一章 招标公告 > 申请人的资格要求",
    )
    detail_node = DocumentNode(
        node_id="q-detail",
        node_type=NodeType.list_item,
        title="12.投标人须提供纳税信用A级证明（提供税务部门出具的证明扫描件）；",
        text="12.投标人须提供纳税信用A级证明（提供税务部门出具的证明扫描件）；",
        path="ROOT > 第一章 招标公告 > 12.投标人须提供纳税信用A级证明（提供税务部门出具的证明扫描件）；",
        parent_id="q-head",
        anchor=SourceAnchor(line_hint="line:q-detail"),
    )

    zones = _zone_map([heading_node, detail_node])

    assert zones[detail_node.node_id].zone_type == SemanticZoneType.qualification


def test_zone_classifier_recognizes_qualification_review_table_heading() -> None:
    qualification_table_heading = _node(
        "q-table",
        node_type=NodeType.paragraph,
        title="资格性审查表",
        text="资格性审查表",
        path="ROOT > 招标文件信息 > 资格性审查表",
    )

    zones = _zone_map([qualification_table_heading])

    assert zones[qualification_table_heading.node_id].zone_type == SemanticZoneType.qualification


def test_zone_classifier_keeps_warning_heading_out_of_scoring_zone() -> None:
    warning_node = _node(
        "warn-1",
        node_type=NodeType.paragraph,
        title="警示条款",
        text="警示条款",
        path="ROOT > 评标信息 > （2021） > 警示条款",
    )

    zones = _zone_map([warning_node])

    assert zones[warning_node.node_id].zone_type == SemanticZoneType.policy_explanation


def test_zone_classifier_uses_child_context_for_scoring_subsection_inside_template_branch() -> None:
    subsection = _node(
        "score-sub",
        node_type=NodeType.subsection,
        title="（二）技术保障措施（可选）",
        text="（二）技术保障措施（可选）",
        path="ROOT > 第一册 专用条款 > 三、投标人情况及资格证明文件 > （二）技术保障措施（可选）",
    )
    subsection.children_ids = ["score-child"]
    score_child = _node(
        "score-child",
        node_type=NodeType.paragraph,
        title="特别提示",
        text="投标人须按本招标文件评标信息中“技术保障措施”这一评审因素要求，提供证明资料。",
        path="ROOT > 第一册 专用条款 > 三、投标人情况及资格证明文件 > （二）技术保障措施（可选） > 特别提示",
    )
    score_child.parent_id = subsection.node_id

    zones = _zone_map([subsection, score_child])

    assert zones[subsection.node_id].zone_type == SemanticZoneType.scoring


def test_zone_classifier_recognizes_generic_performance_scoring_subsection() -> None:
    subsection = _node(
        "perf-sub",
        node_type=NodeType.subsection,
        title="（五）近三年同类业绩（可选）",
        text="（五）近三年同类业绩（可选）",
        path="ROOT > 第一册 专用条款 > 三、投标人情况及资格证明文件 > （五）近三年同类业绩（可选）",
    )
    subsection.children_ids = ["perf-child"]
    score_child = _node(
        "perf-child",
        node_type=NodeType.paragraph,
        title="特别提示",
        text="投标人须按本招标文件评标信息中“近三年同类业绩”这一评审因素要求，提供证明资料。",
        path="ROOT > 第一册 专用条款 > 三、投标人情况及资格证明文件 > （五）近三年同类业绩（可选） > 特别提示",
    )
    score_child.parent_id = subsection.node_id

    zones = _zone_map([subsection, score_child])

    assert zones[subsection.node_id].zone_type == SemanticZoneType.scoring


def test_zone_classifier_recognizes_scoring_subsection_by_title_alone() -> None:
    subsection = _node(
        "perf-title",
        node_type=NodeType.subsection,
        title="（五）近三年同类业绩（可选）",
        text="（五）近三年同类业绩（可选）",
        path="ROOT > 第一册 专用条款 > 三、投标人情况及资格证明文件 > （五）近三年同类业绩（可选）",
    )

    zones = _zone_map([subsection])

    assert zones[subsection.node_id].zone_type == SemanticZoneType.scoring


def test_zone_classifier_marks_structural_chapters_as_catalog_navigation() -> None:
    chapter_node = _node(
        "chap-1",
        node_type=NodeType.chapter,
        title="第一章 招标公告",
        text="第一章 招标公告",
        path="ROOT > 第一章 招标公告",
    )
    info_node = _node(
        "info-1",
        node_type=NodeType.paragraph,
        title="招标文件信息",
        text="招标文件信息",
        path="ROOT > 招标文件信息",
    )

    zones = _zone_map([chapter_node, info_node])

    assert zones[chapter_node.node_id].zone_type == SemanticZoneType.catalog_or_navigation
    assert zones[info_node.node_id].zone_type == SemanticZoneType.administrative_info

from __future__ import annotations

import re

from ...models import DocumentNode, ParseResult, RawBlock, RawTable
from ...ontology import NodeType


STRUCTURAL_HEADING_TOKENS = [
    "项目概况",
    "投标人资格要求",
    "资格要求",
    "采购需求",
    "技术要求",
    "商务要求",
    "评分标准",
    "评标办法",
    "综合评分法评标信息",
    "评标信息",
    "合同条款",
    "付款方式",
    "验收",
    "违约责任",
    "投标文件格式",
    "联合体",
    "样品",
    "保证金",
]


def build_document_tree(parse_result: ParseResult) -> list[DocumentNode]:
    nodes: list[DocumentNode] = []
    root = DocumentNode(
        node_id="root",
        node_type=NodeType.volume,
        title="ROOT",
        text="",
        path="ROOT",
        metadata={"synthetic": True},
    )
    nodes.append(root)

    heading_stack: list[tuple[int, str]] = [(0, root.node_id)]
    in_catalog = False
    seen_catalog_entries = False

    events: list[tuple[int, int, str, RawBlock | RawTable]] = []
    for index, block in enumerate(parse_result.raw_blocks):
        order = int(block.metadata.get("document_order", index))
        events.append((order, 0, "block", block))
    for index, raw_table in enumerate(parse_result.raw_tables):
        order = int(raw_table.metadata.get("document_order", index))
        events.append((order, 1, "table", raw_table))
    events.sort(key=lambda item: (item[0], item[1]))

    for _, _, kind, item in events:
        if kind == "block":
            block = item
            text = _normalize_title(block.text)
            if not text:
                continue

            if text == "目录":
                node = _make_block_node(block, NodeType.catalog_entry, "目录", "ROOT > 目录", root.node_id)
                nodes.append(node)
                _append_child(nodes, root.node_id, node.node_id)
                in_catalog = True
                continue

            if in_catalog and block.metadata.get("catalog_candidate"):
                node = _make_block_node(
                    block,
                    NodeType.catalog_entry,
                    text,
                    f"ROOT > 目录 > {text}",
                    root.node_id,
                )
                nodes.append(node)
                _append_child(nodes, root.node_id, node.node_id)
                seen_catalog_entries = True
                continue

            if in_catalog and seen_catalog_entries:
                in_catalog = False

            inline_table_cells = _split_inline_table_row(text)
            if _should_promote_inline_table(text, inline_table_cells):
                table_kind = _infer_inline_table_kind(text, inline_table_cells)
                table_title = _inline_table_title(table_kind, heading_stack, inline_table_cells)
                parent_id = _inline_table_parent_id(nodes, heading_stack, table_kind)
                table_path = _path_for(nodes, parent_id, table_title)
                table_node = DocumentNode(
                    node_id=f"{block.block_id}-table",
                    node_type=NodeType.table,
                    title=table_title,
                    text=text,
                    path=table_path,
                    parent_id=parent_id,
                    anchor=block.anchor,
                    metadata={**block.metadata, "synthetic_inline_table": True, "table_kind": table_kind},
                )
                nodes.append(table_node)
                _append_child(nodes, parent_id, table_node.node_id)
                row_node = DocumentNode(
                    node_id=f"{block.block_id}-table-r-1",
                    node_type=NodeType.table_row,
                    title=_normalize_title(inline_table_cells[0] if inline_table_cells else text[:60]),
                    text=text,
                    path=f"{table_path} > row:1",
                    parent_id=table_node.node_id,
                    anchor=block.anchor,
                    metadata={
                        **block.metadata,
                        "row_index": 1,
                        "is_header": _looks_like_inline_table_header(inline_table_cells),
                        "table_kind": table_kind,
                        "synthetic_inline_table": True,
                    },
                )
                nodes.append(row_node)
                _append_child(nodes, table_node.node_id, row_node.node_id)
                continue

            appendix_reference_title = _extract_appendix_reference_title(text)
            if appendix_reference_title and (
                block.metadata.get("heading_candidate")
                or block.metadata.get("catalog_candidate")
                or _looks_like_appendix_reference(text)
            ):
                parent_id = _appendix_reference_parent_id(nodes, heading_stack)
                path = _path_for(nodes, parent_id, appendix_reference_title)
                node = _make_block_node(
                    block,
                    NodeType.appendix,
                    appendix_reference_title,
                    path,
                    parent_id,
                )
                nodes.append(node)
                _append_child(nodes, parent_id, node.node_id)
                continue

            if _should_promote_to_heading(block, text):
                level = _infer_heading_level(block, text, heading_stack)
                if level > 0:
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()
                    parent_id = heading_stack[-1][1] if heading_stack else root.node_id
                    path = _path_for(nodes, parent_id, text)
                    node = _make_heading_node(block, level, text, path, parent_id)
                    nodes.append(node)
                    _append_child(nodes, parent_id, node.node_id)
                    heading_stack.append((level, node.node_id))
                    continue

            parent_id = _table_parent_id(nodes, heading_stack)
            node_title = _paragraph_title(text)
            path = _path_for(nodes, parent_id, node_title[:48])
            node = _make_block_node(block, NodeType.paragraph, node_title, path, parent_id)
            nodes.append(node)
            _append_child(nodes, parent_id, node.node_id)
            continue

        raw_table = item
        parent_id = _table_parent_id(nodes, heading_stack)
        table_kind = _infer_table_kind_for_tree(raw_table)
        if table_kind == "scoring":
            table_title = "评分标准"
        elif table_kind == "template":
            table_title = "投标文件格式"
        elif table_kind == "contract":
            table_title = "合同条款"
        elif table_kind == "appendix_reference":
            table_title = "附件说明"
        else:
            table_title = _normalize_title(
                str(raw_table.title_hint or raw_table.metadata.get("preceding_heading") or raw_table.table_id)
            )
        table_path = _path_for(nodes, parent_id, table_title)
        table_node = DocumentNode(
            node_id=raw_table.table_id,
            node_type=NodeType.table,
            title=table_title,
            text="\n".join(" | ".join(cell.text for cell in row) for row in raw_table.rows),
            path=table_path,
            parent_id=parent_id,
            anchor=raw_table.anchor,
            metadata=raw_table.metadata,
        )
        nodes.append(table_node)
        _append_child(nodes, parent_id, table_node.node_id)
        for row_index, row in enumerate(raw_table.rows, start=1):
            row_text = " | ".join(cell.text for cell in row)
            row_node = DocumentNode(
                node_id=f"{raw_table.table_id}-r-{row_index}",
                node_type=NodeType.table_row,
                title=_normalize_title(row_text[:60]),
                text=row_text,
                path=f"{table_path} > row:{row_index}",
                parent_id=table_node.node_id,
                anchor=row[0].anchor if row else raw_table.anchor,
                metadata={"row_index": row_index, "is_header": all(cell.is_header for cell in row)},
            )
            nodes.append(row_node)
            _append_child(nodes, table_node.node_id, row_node.node_id)

    return nodes


def _should_promote_to_heading(block: RawBlock, title: str) -> bool:
    if block.metadata.get("heading_candidate"):
        return True
    if block.metadata.get("catalog_candidate") and _looks_like_catalog_heading(title):
        return True
    if not title or len(title) > 80:
        return False
    if _looks_like_clause_with_structural_prefix(title):
        return False
    if _looks_like_appendix_heading(title):
        return True
    return _looks_like_structural_heading(title)


def _infer_heading_level(
    block: RawBlock,
    title: str,
    heading_stack: list[tuple[int, str]],
) -> int:
    explicit_level = int(block.metadata.get("numbering_level_guess", 0) or 0)
    if explicit_level > 0:
        return explicit_level

    if _looks_like_appendix_reference(title):
        return 1

    kind = _classify_heading_kind(title)
    current_level = heading_stack[-1][0] if heading_stack else 0

    if kind == "chapter":
        return 1
    if kind == "appendix":
        if current_level <= 0:
            return 1
        if current_level == 1:
            return 2
        return min(current_level, 3)
    if kind == "section":
        if current_level <= 0:
            return 1
        if current_level == 1:
            return 2
        return min(current_level, 3)
    if kind == "subsection":
        if current_level <= 0:
            return 2
        return min(current_level + 1, 3)
    if kind == "list":
        if current_level <= 0:
            return 2
        return min(current_level + 1, 4)
    return 0


def _classify_heading_kind(title: str) -> str:
    normalized = title.strip()
    if not normalized:
        return ""
    if re.match(r"^第[一二三四五六七八九十百千0-9]+[章节册部分篇]", normalized):
        return "chapter"
    if _looks_like_appendix_heading(normalized):
        return "appendix"
    if _looks_like_structural_heading(normalized):
        return "section"
    if re.match(r"^[一二三四五六七八九十]+、", normalized) or re.match(r"^（[一二三四五六七八九十0-9]+）", normalized):
        return "subsection"
    if re.match(r"^\d+[\.、]", normalized):
        return "list"
    return ""


def _looks_like_structural_heading(title: str) -> bool:
    normalized = title.strip()
    if not normalized:
        return False
    return any(_matches_heading_token(normalized, token) for token in STRUCTURAL_HEADING_TOKENS)


def _looks_like_clause_with_structural_prefix(title: str) -> bool:
    normalized = title.strip()
    if not normalized:
        return False
    for prefix in ["技术要求", "商务要求", "资格要求", "投标人资格要求", "一般资格要求", "特定资格要求"]:
        if normalized.startswith((f"{prefix}：", f"{prefix}:")):
            body = normalized[len(prefix) + 1 :].strip()
            if not body:
                return False
            if len(body) > 12 or any(token in body for token in ["证书", "检测报告", "业绩", "参数", "指标", "评分", "分值"]):
                return True
    return False


def _looks_like_appendix_heading(title: str) -> bool:
    normalized = title.strip()
    if not normalized or len(normalized) > 60:
        return False
    if normalized.startswith(("附件", "附表", "承诺函", "投标文件格式", "详见附件", "另册提供")):
        return True
    return "声明函" in normalized


def _looks_like_appendix_reference(title: str) -> bool:
    normalized = title.strip()
    return normalized.startswith(("详见附件", "另册提供"))


def _looks_like_catalog_heading(title: str) -> bool:
    normalized = title.strip()
    return bool(
        re.match(
            r"^(第[一二三四五六七八九十百千0-9]+[章节册部分篇]|[一二三四五六七八九十]+、|（[一二三四五六七八九十0-9]+）)",
            normalized,
        )
    )


def _matches_heading_token(text: str, token: str) -> bool:
    return bool(re.match(rf"^{re.escape(token)}(?:[：:、，,（( ]|$)", text))


def _split_inline_table_row(text: str) -> list[str]:
    if "|" in text:
        cells = [part.strip() for part in text.split("|") if part.strip()]
        if len(cells) >= 2:
            return cells
    if "\t" in text:
        cells = [part.strip() for part in text.split("\t") if part.strip()]
        if len(cells) >= 2:
            return cells
    cells = [part.strip() for part in re.split(r"\s{2,}", text) if part.strip()]
    if len(cells) >= 3:
        return cells
    return []


def _should_promote_inline_table(text: str, cells: list[str]) -> bool:
    if len(cells) < 3:
        return False
    if any(token in text for token in ["评分项", "分值", "评分标准", "得分", "评标", "合同", "验收", "付款", "质保", "保修"]):
        return True
    if any(re.search(r"\d", cell) for cell in cells):
        return True
    return len(cells) >= 4 and all(len(cell) <= 32 for cell in cells)


def _infer_inline_table_kind(text: str, cells: list[str]) -> str:
    haystack = " ".join(cells) + " " + text
    if any(token in haystack for token in ["评分项", "分值", "评分标准", "得分", "评标", "综合评分", "13.0分", "5.0分"]):
        return "scoring"
    if any(token in haystack for token in ["中小企业声明函", "投标文件格式", "声明函", "承诺函"]):
        return "template"
    if any(token in haystack for token in ["付款", "验收", "违约", "解除合同", "质保", "保修"]):
        return "contract"
    if any(token in haystack for token in ["详见附件", "另册提供"]):
        return "appendix_reference"
    return "general"


def _inline_table_title(table_kind: str, heading_stack: list[tuple[int, str]], cells: list[str]) -> str:
    if table_kind == "scoring":
        return "评分标准"
    if table_kind == "template":
        return "投标文件格式"
    if table_kind == "contract":
        return "合同条款"
    if table_kind == "appendix_reference":
        return "附件说明"
    return _normalize_title(cells[0] if cells else "表格")


def _looks_like_inline_table_header(cells: list[str]) -> bool:
    if len(cells) < 2:
        return False
    header_keywords = {
        "评分项",
        "分值",
        "评分标准",
        "序号",
        "内容",
        "说明",
        "备注",
        "项目",
        "标准",
        "要求",
        "报价",
        "金额",
        "名称",
        "参数",
    }
    if any(cell in header_keywords for cell in cells):
        return True
    if len(cells) <= 4 and all(len(cell) <= 16 for cell in cells):
        label_like = sum(1 for cell in cells if _is_label_like(cell))
        return label_like >= 2 and not any(any(ch.isdigit() for ch in cell) for cell in cells)
    return False


def _is_label_like(text: str) -> bool:
    normalized = _normalize_title(text)
    if not normalized:
        return False
    if normalized in {
        "评分项",
        "分值",
        "评分标准",
        "序号",
        "内容",
        "说明",
        "备注",
        "项目",
        "标准",
        "要求",
        "报价",
        "金额",
        "名称",
        "参数",
    }:
        return True
    return bool(re.match(r"^[\u4e00-\u9fffA-Za-z]{1,12}$", normalized))


def _infer_table_kind_for_tree(raw_table: RawTable) -> str:
    table_kind = str(raw_table.metadata.get("table_kind", "")).strip()
    row_text = " ".join(" ".join(cell.text for cell in row) for row in raw_table.rows)
    title_hint = _normalize_title(str(raw_table.title_hint or raw_table.metadata.get("preceding_heading") or ""))
    haystack = f"{table_kind} {title_hint} {row_text}"
    if any(token in haystack for token in ["评分项", "评分标准", "分值", "得分", "评分办法", "13.0分", "5.0分", "最高得", "本项最高得"]):
        return "scoring"
    if any(token in haystack for token in ["中小企业声明函", "投标文件格式", "声明函", "承诺函", "格式"]):
        return "template"
    if any(token in haystack for token in ["付款", "验收", "违约", "解除合同", "质保", "保修"]):
        return "contract"
    if any(token in haystack for token in ["详见附件", "另册提供"]):
        return "appendix_reference"
    return table_kind or "general"


def _normalize_title(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _paragraph_title(text: str) -> str:
    normalized = _normalize_title(text)
    if not normalized:
        return ""
    for prefix in ["技术要求", "商务要求", "资格要求", "投标人资格要求", "一般资格要求", "特定资格要求"]:
        if normalized.startswith((f"{prefix}：", f"{prefix}:")):
            body = normalized[len(prefix) + 1 :].strip()
            if body:
                return body
    return normalized


def _make_heading_node(block: RawBlock, level: int, title: str, path: str, parent_id: str) -> DocumentNode:
    if _is_appendix_title(title):
        node_type = NodeType.appendix
    else:
        node_type = {
            1: NodeType.chapter,
            2: NodeType.section,
            3: NodeType.subsection,
        }.get(level, NodeType.list_item)
    return DocumentNode(
        node_id=block.block_id,
        node_type=node_type,
        title=title,
        text=block.text,
        path=path,
        parent_id=parent_id,
        anchor=block.anchor,
        metadata=block.metadata,
    )


def _make_block_node(block: RawBlock, node_type: NodeType, title: str, path: str, parent_id: str) -> DocumentNode:
    return DocumentNode(
        node_id=block.block_id,
        node_type=node_type,
        title=title,
        text=block.text,
        path=path,
        parent_id=parent_id,
        anchor=block.anchor,
        metadata=block.metadata,
    )


def _append_child(nodes: list[DocumentNode], parent_id: str, child_id: str) -> None:
    for node in nodes:
        if node.node_id == parent_id:
            node.children_ids.append(child_id)
            return


def _table_parent_id(nodes: list[DocumentNode], heading_stack: list[tuple[int, str]]) -> str:
    for _, node_id in reversed(heading_stack):
        node = _find_node(nodes, node_id)
        if node is None:
            continue
        if node.node_type not in {NodeType.paragraph, NodeType.list_item, NodeType.table_row, NodeType.table_cell, NodeType.note}:
            return node_id
    return heading_stack[-1][1] if heading_stack else "root"


def _inline_table_parent_id(
    nodes: list[DocumentNode],
    heading_stack: list[tuple[int, str]],
    table_kind: str,
) -> str:
    if table_kind == "scoring":
        parent_id = _nearest_heading_with_keywords(nodes, heading_stack, ["评分", "评标", "综合评分"])
        if parent_id:
            return parent_id
        return "root"
    if table_kind == "template":
        parent_id = _nearest_heading_with_keywords(nodes, heading_stack, ["投标文件格式", "格式", "声明函", "承诺函"])
        if parent_id:
            return parent_id
        return "root"
    if table_kind == "contract":
        parent_id = _nearest_heading_with_keywords(nodes, heading_stack, ["合同", "付款", "验收", "违约", "质保", "保修"])
        if parent_id:
            return parent_id
        return "root"
    if table_kind == "appendix_reference":
        parent_id = _nearest_heading_with_keywords(nodes, heading_stack, ["附件", "附表", "另册", "详见附件", "见附件"])
        if parent_id:
            return parent_id
        return "root"
    return _table_parent_id(nodes, heading_stack)


def _appendix_reference_parent_id(nodes: list[DocumentNode], heading_stack: list[tuple[int, str]]) -> str:
    fallback_parent_id = ""
    for _, node_id in reversed(heading_stack):
        node = _find_node(nodes, node_id)
        if node is None:
            continue
        if node.node_type in {NodeType.paragraph, NodeType.list_item, NodeType.table_row, NodeType.table_cell, NodeType.note}:
            continue
        if _is_template_like_title(node.title):
            continue
        if any(keyword in node.title or keyword in node.path for keyword in ["附件", "附表", "另册"]):
            return node_id
        if not fallback_parent_id:
            fallback_parent_id = node_id
    if fallback_parent_id:
        return fallback_parent_id
    return "root"


def _nearest_heading_with_keywords(
    nodes: list[DocumentNode],
    heading_stack: list[tuple[int, str]],
    keywords: list[str],
) -> str:
    for _, node_id in reversed(heading_stack):
        node = _find_node(nodes, node_id)
        if node is None:
            continue
        if any(keyword in node.title or keyword in node.path for keyword in keywords):
            return node_id
    return ""


def _find_node(nodes: list[DocumentNode], node_id: str) -> DocumentNode | None:
    for node in nodes:
        if node.node_id == node_id:
            return node
    return None


def _path_for(nodes: list[DocumentNode], parent_id: str, title: str) -> str:
    for node in nodes:
        if node.node_id == parent_id:
            if not node.path or node.path == "ROOT":
                return f"ROOT > {title}"
            return f"{node.path} > {title}"
    return f"ROOT > {title}"


def _is_free_heading_candidate(text: str) -> bool:
    normalized = text.strip()
    if not normalized or len(normalized) > 40:
        return False
    return any(
        token in normalized
        for token in [
            "评标信息",
            "评分标准",
            "投标文件格式",
            "声明函",
            "附件",
            "附表",
            "采购需求",
            "技术要求",
            "商务要求",
            "合同条款",
            "投标人资格要求",
        ]
    )


def _is_appendix_title(text: str) -> bool:
    normalized = text.strip()
    return bool(
        normalized.startswith(("附件", "附表", "声明函", "承诺函", "详见附件", "另册提供"))
        or "投标文件格式" in normalized
        or ("声明函" in normalized and len(normalized) <= 60)
    )


def _is_template_like_title(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return any(token in normalized for token in ["投标文件格式", "声明函", "承诺函", "格式", "范本", "模板"])


def _extract_appendix_reference_title(text: str) -> str:
    normalized = _normalize_title(text)
    if not normalized:
        return ""
    patterns = [
        r"(详见附件\s*[一二三四五六七八九十0-9]+(?:[。．.]|$))",
        r"(见附件\s*[一二三四五六七八九十0-9]+(?:[。．.]|$))",
        r"(参见附件\s*[一二三四五六七八九十0-9]+(?:[。．.]|$))",
        r"(附件\s*[一二三四五六七八九十0-9]+(?:[。．.]|$))",
        r"(另册提供(?:[。．.]|$))",
        r"(另附(?:[。．.]|$))",
        r"(附表\s*[一二三四五六七八九十0-9]+(?:[。．.]|$))",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return _normalize_title(match.group(1).rstrip("。．."))
    return ""

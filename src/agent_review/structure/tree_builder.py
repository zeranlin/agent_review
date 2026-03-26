from __future__ import annotations

from ..models import DocumentNode, ParseResult, RawBlock, RawTable
from ..ontology import NodeType


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

    stack: list[tuple[int, str]] = [(0, root.node_id)]
    in_catalog = False
    seen_catalog_entries = False

    for block in parse_result.raw_blocks:
        text = block.text.strip()
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

        level = int(block.metadata.get("numbering_level_guess", 0) or 0)
        title = text
        if block.metadata.get("heading_candidate") and level > 0:
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent_id = stack[-1][1] if stack else root.node_id
            path = _path_for(nodes, parent_id, title)
            node = _make_heading_node(block, level, title, path, parent_id)
            nodes.append(node)
            _append_child(nodes, parent_id, node.node_id)
            stack.append((level, node.node_id))
        else:
            parent_id = stack[-1][1] if stack else root.node_id
            path = _path_for(nodes, parent_id, title[:48])
            node = _make_block_node(block, NodeType.paragraph, title, path, parent_id)
            nodes.append(node)
            _append_child(nodes, parent_id, node.node_id)

    for raw_table in parse_result.raw_tables:
        parent_id = stack[-1][1] if stack else root.node_id
        table_title = raw_table.title_hint or raw_table.table_id
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
                title=row_text[:60],
                text=row_text,
                path=f"{table_path} > row:{row_index}",
                parent_id=table_node.node_id,
                anchor=row[0].anchor if row else raw_table.anchor,
                metadata={"row_index": row_index, "is_header": all(cell.is_header for cell in row)},
            )
            nodes.append(row_node)
            _append_child(nodes, table_node.node_id, row_node.node_id)

    return nodes


def _make_heading_node(block: RawBlock, level: int, title: str, path: str, parent_id: str) -> DocumentNode:
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


def _path_for(nodes: list[DocumentNode], parent_id: str, title: str) -> str:
    for node in nodes:
        if node.node_id == parent_id:
            if not node.path or node.path == "ROOT":
                return f"ROOT > {title}"
            return f"{node.path} > {title}"
    return f"ROOT > {title}"

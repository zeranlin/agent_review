from __future__ import annotations

from pathlib import Path

from ..models import FileInfo, FileType, ParseResult, SectionIndex
from ..extractors.clause_units import build_clause_units
from .effect_tagger import tag_effects
from .tree_builder import build_document_tree
from .zone_classifier import classify_semantic_zones


def detect_file_type(text: str) -> FileType:
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


def build_file_info(document_name: str, text: str, file_type: FileType) -> FileInfo:
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


def build_scope_statement(file_info: FileInfo) -> str:
    return (
        f"本次审查材料为《{file_info.document_name}》，识别类型为“{file_info.file_type.value}”。"
        f"审查范围：{file_info.review_scope} 审查边界：{file_info.review_boundary}"
    )


def locate_sections(text: str) -> list[SectionIndex]:
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
        "投标文件格式/附件/附表",
        "声明函/承诺函",
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


def enrich_parse_result_structure(parse_result: ParseResult) -> ParseResult:
    if not parse_result.raw_blocks and not parse_result.raw_tables:
        return parse_result
    parse_result.document_nodes = build_document_tree(parse_result)
    parse_result.semantic_zones = classify_semantic_zones(parse_result.document_nodes)
    parse_result.effect_tag_results = tag_effects(parse_result.document_nodes, parse_result.semantic_zones)
    parse_result.clause_units = build_clause_units(
        parse_result.document_nodes,
        parse_result.semantic_zones,
        parse_result.effect_tag_results,
    )
    return parse_result

"""文档结构层。"""

from .document_structure import build_file_info, build_scope_statement, detect_file_type, locate_sections

__all__ = [
    "build_file_info",
    "build_scope_statement",
    "detect_file_type",
    "locate_sections",
]

"""条款抽取层。"""

from .clauses import classify_clause_role, classify_extracted_clauses, extract_clauses

__all__ = ["classify_clause_role", "classify_extracted_clauses", "extract_clauses"]

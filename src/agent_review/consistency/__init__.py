"""一致性与裁决层。"""

from .checks import (
    check_consistency,
    collect_relative_strengths,
    convert_consistency_checks_to_findings,
    derive_conclusion,
)

__all__ = [
    "check_consistency",
    "collect_relative_strengths",
    "convert_consistency_checks_to_findings",
    "derive_conclusion",
]

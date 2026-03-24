from __future__ import annotations

import json
import re
from dataclasses import replace

from ..models import Recommendation, ReviewReport
from .client import OpenAICompatibleClient, QwenLocalConfig
from .prompts import REVIEW_ENHANCER_SYSTEM_PROMPT, build_review_enhancer_prompt


class NullReviewEnhancer:
    def enhance(self, report: ReviewReport) -> ReviewReport:
        return report


class QwenReviewEnhancer:
    def __init__(self, client: OpenAICompatibleClient | None = None) -> None:
        self.client = client or OpenAICompatibleClient(QwenLocalConfig.from_env_or_default())

    def enhance(self, report: ReviewReport) -> ReviewReport:
        try:
            raw = self.client.generate_text(
                system_prompt=REVIEW_ENHANCER_SYSTEM_PROMPT,
                user_prompt=build_review_enhancer_prompt(report),
            )
            parsed = _parse_json_response(raw)
            summary = str(parsed.get("summary", "")).strip() or report.summary
            recommendations = _merge_recommendations(report, parsed.get("recommendations"))
            return replace(
                report,
                summary=summary,
                recommendations=recommendations,
                llm_enhanced=True,
                llm_warnings=[],
            )
        except Exception as exc:
            return replace(
                report,
                llm_enhanced=False,
                llm_warnings=[f"LLM 增强未生效：{exc}"],
            )


def _merge_recommendations(report: ReviewReport, raw_recommendations: object) -> list[Recommendation]:
    if not isinstance(raw_recommendations, list):
        return report.recommendations

    updated: list[Recommendation] = []
    seen: set[str] = set()
    for item in raw_recommendations:
        if not isinstance(item, dict):
            continue
        related_issue = str(item.get("related_issue", "")).strip()
        suggestion = str(item.get("suggestion", "")).strip()
        if not related_issue or not suggestion:
            continue
        updated.append(Recommendation(related_issue=related_issue, suggestion=suggestion))
        seen.add(related_issue)

    for item in report.recommendations:
        if item.related_issue not in seen:
            updated.append(item)
    return updated or report.recommendations


def _parse_json_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise

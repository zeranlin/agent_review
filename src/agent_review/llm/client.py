from __future__ import annotations

import mimetypes
import json
import os
from base64 import b64encode
from pathlib import Path
import urllib.request
from dataclasses import dataclass


@dataclass(slots=True)
class QwenLocalConfig:
    base_url: str
    model: str
    api_key: str
    timeout: float = 1800.0

    @classmethod
    def from_env_or_default(cls) -> "QwenLocalConfig":
        return cls(
            base_url=os.getenv("AGENT_REVIEW_LLM_BASE_URL", "http://112.111.54.86:10011/v1"),
            model=os.getenv("AGENT_REVIEW_LLM_MODEL", "qwen3.5-27b"),
            api_key=os.getenv("AGENT_REVIEW_LLM_API_KEY", "123"),
            timeout=float(os.getenv("AGENT_REVIEW_LLM_TIMEOUT", "1800")),
        )


class OpenAICompatibleClient:
    def __init__(self, config: QwenLocalConfig) -> None:
        self.config = config

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        endpoint = self.config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 1200,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        message = body.get("choices", [{}])[0].get("message", {}) or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            if text_parts:
                return "\n".join(part.strip() for part in text_parts if part.strip())
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str):
            return reasoning.strip()
        return ""

    def generate_vision_text(self, system_prompt: str, user_prompt: str, image_path: str | Path) -> str:
        endpoint = self.config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": self._image_data_url(image_path)},
                        },
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": 1200,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        message = body.get("choices", [{}])[0].get("message", {}) or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            if text_parts:
                return "\n".join(part.strip() for part in text_parts if part.strip())
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str):
            return reasoning.strip()
        return ""

    @staticmethod
    def _image_data_url(image_path: str | Path) -> str:
        target = Path(image_path).expanduser().resolve()
        mime_type, _ = mimetypes.guess_type(target.name)
        mime_type = mime_type or "image/png"
        encoded = b64encode(target.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

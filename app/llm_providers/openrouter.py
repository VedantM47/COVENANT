"""OpenRouter provider (OpenAI-compatible)."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Type

from pydantic import BaseModel

from app.llm_providers.base import LLMProvider, LLMResponse


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(self, model: str = "anthropic/claude-sonnet-4", api_key: str = ""):
        self.model = model
        self._api_key = api_key

    async def extract_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Type[BaseModel],
        temperature: float = 0.0,
        max_output_tokens: int = 4096,
        timeout_s: float = 60.0,
        seed: int | None = None,
    ) -> LLMResponse:
        from openai import OpenAI
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=self._api_key)
        schema = response_schema.model_json_schema()

        t0 = time.monotonic()
        now = datetime.now(timezone.utc).isoformat()
        response = client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=max_output_tokens,
            response_format={"type": "json_schema", "json_schema": {"name": "extract", "schema": schema}},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw = response.choices[0].message.content
        data = json.loads(raw)
        parsed = response_schema.model_validate(data)

        return LLMResponse(
            provider="openrouter",
            model=self.model,
            request_id=response.id,
            started_at=now,
            completed_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=latency_ms,
            tokens={"input": response.usage.prompt_tokens, "output": response.usage.completion_tokens, "cached": 0},
            cost_usd_estimate=0.0,
            structured_output=parsed,
            raw_response=raw,
        )

"""Anthropic direct provider."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Type

from pydantic import BaseModel

from app.llm_providers.base import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: str = ""):
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
        import anthropic
        client = anthropic.Anthropic(api_key=self._api_key)
        schema = response_schema.model_json_schema()

        t0 = time.monotonic()
        now = datetime.now(timezone.utc).isoformat()
        response = client.messages.create(
            model=self.model,
            max_tokens=max_output_tokens,
            temperature=temperature,
            system=system_prompt,
            tools=[{"name": "extract", "description": "Extract structured data", "input_schema": schema}],
            tool_choice={"type": "tool", "name": "extract"},
            messages=[{"role": "user", "content": user_prompt}],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        tool_use = next(b for b in response.content if b.type == "tool_use")
        data = tool_use.input
        parsed = response_schema.model_validate(data)

        return LLMResponse(
            provider="anthropic",
            model=self.model,
            request_id=response.id,
            started_at=now,
            completed_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=latency_ms,
            tokens={"input": response.usage.input_tokens, "output": response.usage.output_tokens, "cached": 0},
            cost_usd_estimate=0.0,
            structured_output=parsed,
            raw_response=json.dumps(data),
        )

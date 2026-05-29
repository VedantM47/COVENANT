"""Gemini provider."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Type
import uuid

from pydantic import BaseModel

from app.llm_providers.base import LLMProvider, LLMResponse


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, model: str = "gemini-2.5-flash", api_key: str = ""):
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
        import google.generativeai as genai
        genai.configure(api_key=self._api_key)

        schema_dict = response_schema.model_json_schema()
        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "response_mime_type": "application/json",
        }
        if seed is not None:
            generation_config["seed"] = seed

        model = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system_prompt,
            generation_config=generation_config,
        )

        t0 = time.monotonic()
        now = datetime.now(timezone.utc).isoformat()
        response = model.generate_content(user_prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)

        import json
        raw = response.text
        data = json.loads(raw)
        parsed = response_schema.model_validate(data)

        return LLMResponse(
            provider="gemini",
            model=self.model,
            request_id=str(uuid.uuid4()),
            started_at=now,
            completed_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=latency_ms,
            tokens={"input": 0, "output": 0, "cached": 0},
            cost_usd_estimate=0.0,
            structured_output=parsed,
            raw_response=raw,
        )

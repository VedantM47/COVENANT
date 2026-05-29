"""AWS Bedrock provider."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Type

from pydantic import BaseModel

from app.llm_providers.base import LLMProvider, LLMResponse


class BedrockProvider(LLMProvider):
    name = "bedrock"

    def __init__(
        self,
        model: str = "anthropic.claude-sonnet-4-20250514-v1:0",
        region: str = "us-east-1",
        access_key: str = "",
        secret_key: str = "",
    ):
        self.model = model
        self._region = region
        self._access_key = access_key
        self._secret_key = secret_key

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
        import boto3
        client = boto3.client(
            "bedrock-runtime",
            region_name=self._region,
            aws_access_key_id=self._access_key or None,
            aws_secret_access_key=self._secret_key or None,
        )
        schema = response_schema.model_json_schema()
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_output_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "tools": [{"name": "extract", "description": "Extract structured data", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": "extract"},
            "messages": [{"role": "user", "content": user_prompt}],
        }

        t0 = time.monotonic()
        now = datetime.now(timezone.utc).isoformat()
        response = client.invoke_model(
            modelId=self.model,
            body=json.dumps(body),
            contentType="application/json",
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        result = json.loads(response["body"].read())
        tool_use = next(b for b in result["content"] if b["type"] == "tool_use")
        data = tool_use["input"]
        parsed = response_schema.model_validate(data)

        return LLMResponse(
            provider="bedrock",
            model=self.model,
            request_id=str(uuid.uuid4()),
            started_at=now,
            completed_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=latency_ms,
            tokens={"input": result.get("usage", {}).get("input_tokens", 0), "output": result.get("usage", {}).get("output_tokens", 0), "cached": 0},
            cost_usd_estimate=0.0,
            structured_output=parsed,
            raw_response=json.dumps(data),
        )

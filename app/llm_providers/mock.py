"""Mock LLM provider — reads canned responses from fixtures for deterministic tests."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from app.llm_providers.base import LLMProvider, LLMResponse

FIXTURES_DIR = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "llm_responses"


class MockLLMProvider(LLMProvider):
    name = "mock"
    model = "mock-v1"

    def __init__(self, fixture_subdir: str = ""):
        self._fixture_subdir = fixture_subdir

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
        prompt_hash = hashlib.sha256((system_prompt + user_prompt).encode()).hexdigest()[:16]
        fixture_path = FIXTURES_DIR / self._fixture_subdir / f"{prompt_hash}.json"

        if fixture_path.exists():
            data = json.loads(fixture_path.read_text())
        else:
            # Return empty valid instance
            data = {}

        try:
            parsed = response_schema.model_validate(data)
        except Exception:
            parsed = response_schema.model_construct()

        now = datetime.now(timezone.utc).isoformat()
        return LLMResponse(
            provider="mock",
            model="mock-v1",
            request_id=f"mock_{prompt_hash}",
            started_at=now,
            completed_at=now,
            latency_ms=0,
            tokens={"input": 0, "output": 0, "cached": 0},
            cost_usd_estimate=0.0,
            structured_output=parsed,
            raw_response=json.dumps(data),
            self_consistency={"n_runs": 1, "disagreements_flagged": []},
        )

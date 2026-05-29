"""Abstract LLM provider base."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Type

from pydantic import BaseModel


@dataclass
class LLMResponse:
    provider: str
    model: str
    request_id: str
    started_at: str
    completed_at: str
    latency_ms: int
    tokens: dict
    cost_usd_estimate: float
    structured_output: Any  # validated Pydantic instance
    raw_response: str
    self_consistency: dict = field(default_factory=dict)


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def extract_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Type[BaseModel],
        temperature: float = 0.0,
        max_output_tokens: int = 4096,
        timeout_s: float = 60.0,
        seed: int | None = None,
    ) -> LLMResponse: ...

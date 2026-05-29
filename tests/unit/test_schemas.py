"""Schema round-trip tests."""
from __future__ import annotations

import json
import pytest

from app.schemas.common import ChunkRef, ConfidenceField, BBox
from app.schemas.stage3 import CovenantRatioResult, Stage3Output
from app.schemas.stage4 import Exception_, Stage4Output
from app.schemas.api import CreateEngagementRequest, EngagementResponse


def test_chunk_ref_roundtrip():
    data = {
        "chunk_id": "ENG-001:DOC-001:chunk_00001",
        "document_id": "DOC-001",
        "document_type": "credit_agreement",
        "page_number": 87,
        "section_path": ["ARTICLE VII", "Section 7.01"],
        "text_excerpt": "The Borrower shall not permit...",
    }
    obj = ChunkRef.model_validate(data)
    assert obj.chunk_id == data["chunk_id"]
    assert json.loads(obj.model_dump_json())["chunk_id"] == data["chunk_id"]


def test_confidence_field_roundtrip():
    data = {
        "value": 5.00,
        "value_display": "5.00x",
        "source_chunk_id": "ENG-001:DOC-001:chunk_00342",
        "source_text_match": "5.00:1.00",
        "confidence": 0.96,
        "confidence_band": "high",
    }
    obj = ConfidenceField.model_validate(data)
    assert obj.value == 5.00
    assert obj.confidence_band == "high"


def test_covenant_ratio_result_roundtrip():
    data = {
        "covenant_id": "COV-NET-LEVERAGE",
        "covenant_name": "Net Leverage Ratio",
        "ratio_exact_rational": "1815000000/1361111111",
        "ratio_float": 1.334,
        "ratio_display": "1.334x",
        "threshold_value": 5.0,
        "threshold_operator": "<=",
        "is_compliant": True,
    }
    obj = CovenantRatioResult.model_validate(data)
    assert obj.is_compliant is True
    assert obj.ratio_display == "1.334x"


def test_exception_roundtrip():
    data = {
        "exception_id": "EXC-001-001",
        "covenant_id": "COV-NET-LEVERAGE",
        "type": "HARD_BREACH",
        "severity": "HIGH",
        "kind": "circular_cap_misapplication",
        "description": "Test exception",
    }
    obj = Exception_.model_validate(data)
    assert obj.type == "HARD_BREACH"
    assert obj.severity == "HIGH"


def test_create_engagement_request():
    data = {
        "engagement_code": "ENG-2025-EY-001",
        "borrower": {"name": "FirstBank Corp"},
        "lender": {"name": "LendCo"},
        "test_date": "2024-12-31",
    }
    obj = CreateEngagementRequest.model_validate(data)
    assert obj.engagement_code == "ENG-2025-EY-001"

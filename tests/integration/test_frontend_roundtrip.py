"""A3 — Frontend round-trip test.

Tests the full HTTP round-trip that the frontend performs:
1. POST /api/v1/engagements — create engagement
2. POST /api/v1/engagements/{id}/documents — upload FirstBank fixture files
3. POST /api/v1/engagements/{id}/pipeline/start — start pipeline (background)
4. POST /api/v1/engagements/{id}/gates/gate_1_rule_review/approve — gate 1 approval
5. GET  /api/v1/engagements/{id}/audit/events — verify RULE_APPROVED event present

This is the same sequence the React frontend performs via axios.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app

FIRSTBANK_DIR = Path("D:/covenant/test_inputs/firstbank")


@pytest.mark.asyncio
async def test_frontend_round_trip_engagement_creation_upload_gate1():
    """Full HTTP round-trip: create → upload → pipeline → gate 1 approve."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

        # ── Step 1: Create engagement ─────────────────────────────────────────
        create_payload = {
            "engagement_code": "ENG-A3-ROUNDTRIP-001",
            "borrower": {"name": "FirstBank Corp", "rssd_id": "1234567"},
            "lender": {"name": "LendCo Private Credit Fund II LP"},
            "loan_id": "FB-TL-2023-001",
            "test_date": "2024-12-31",
            "audit_team": [
                {"role": "associate", "email": "j.sharma@ey.com", "name": "J. Sharma"},
                {"role": "senior", "email": "r.patel@ey.com", "name": "R. Patel"},
            ],
            "external_egress_enabled": True,
        }
        create_resp = await client.post("/api/v1/engagements", json=create_payload)
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        eng = create_resp.json()
        eng_id = eng["engagement_id"]

        # Record request/response for audit report
        _A3_EVIDENCE["create_request"] = create_payload
        _A3_EVIDENCE["create_response"] = eng

        # ── Step 2: Upload documents ──────────────────────────────────────────
        files_to_upload = list(FIRSTBANK_DIR.glob("*.pdf")) + list(FIRSTBANK_DIR.glob("*.xlsx"))
        assert len(files_to_upload) > 0, "No fixture files found"

        upload_files = []
        file_handles = []
        for f in files_to_upload:
            fh = open(f, "rb")
            file_handles.append(fh)
            upload_files.append(("files", (f.name, fh, "application/octet-stream")))

        try:
            upload_resp = await client.post(
                f"/api/v1/engagements/{eng_id}/documents",
                files=upload_files,
            )
        finally:
            for fh in file_handles:
                fh.close()

        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        upload_result = upload_resp.json()
        _A3_EVIDENCE["upload_response"] = upload_result
        assert len(upload_result) > 0, "No documents uploaded"

        # ── Step 3: Start pipeline (background task) ──────────────────────────
        start_resp = await client.post(f"/api/v1/engagements/{eng_id}/pipeline/start")
        assert start_resp.status_code == 200, f"Pipeline start failed: {start_resp.text}"
        _A3_EVIDENCE["pipeline_start_response"] = start_resp.json()

        # Wait briefly for pipeline to register (it runs in background)
        await asyncio.sleep(0.5)

        # ── Step 4: Approve gate 1 ────────────────────────────────────────────
        approve_payload = {
            "item_ids": [],
            "approver_email": "j.sharma@ey.com",
            "notes": "Reviewed all covenant rules. COV-NET-LEVERAGE threshold 5.00x confirmed per Amendment No.3.",
        }
        approve_resp = await client.post(
            f"/api/v1/engagements/{eng_id}/gates/gate_1_rule_review/approve",
            json=approve_payload,
        )
        assert approve_resp.status_code == 200, f"Gate 1 approve failed: {approve_resp.text}"
        approve_result = approve_resp.json()
        _A3_EVIDENCE["gate1_approve_request"] = approve_payload
        _A3_EVIDENCE["gate1_approve_response"] = approve_result
        assert approve_result["status"] == "approved"

        # ── Step 5: Verify RULE_APPROVED event in audit trail ─────────────────
        events_resp = await client.get(f"/api/v1/engagements/{eng_id}/audit/events")
        assert events_resp.status_code == 200
        events = events_resp.json()
        _A3_EVIDENCE["audit_events_count"] = len(events)

        rule_approved_events = [
            e for e in events
            if e.get("event_type") == "RULE_APPROVED"
        ]
        assert len(rule_approved_events) > 0, (
            f"No RULE_APPROVED event found in audit trail. "
            f"Events present: {[e['event_type'] for e in events]}"
        )

        # Find the HTTP-triggered approval (actor.id = approver email, not "auto_approve")
        http_approvals = [
            e for e in rule_approved_events
            if e.get("actor", {}).get("id") == "j.sharma@ey.com"
        ]
        assert len(http_approvals) > 0, (
            f"No RULE_APPROVED event with actor j.sharma@ey.com found. "
            f"RULE_APPROVED events: {[e.get('actor') for e in rule_approved_events]}"
        )
        ra = http_approvals[0]

        _A3_EVIDENCE["rule_approved_event"] = ra

        # ── Step 6: Verify chain integrity ────────────────────────────────────
        verify_resp = await client.post(f"/api/v1/engagements/{eng_id}/audit/verify")
        assert verify_resp.status_code == 200
        verify_result = verify_resp.json()
        _A3_EVIDENCE["chain_verify_result"] = verify_result
        assert verify_result["is_intact"] is True, f"Chain broken: {verify_result['violations']}"
        assert verify_result["total_events"] >= 2  # ENGAGEMENT_CREATED + RULE_APPROVED


# Storage for evidence to be printed at end of test
_A3_EVIDENCE: dict = {}


@pytest.fixture(autouse=True)
def print_a3_evidence():
    yield
    if _A3_EVIDENCE:
        print("\n\n=== A3 ROUND-TRIP EVIDENCE ===")
        print(f"Engagement ID: {_A3_EVIDENCE.get('create_response', {}).get('engagement_id')}")
        print(f"\nPOST /api/v1/engagements request:")
        print(json.dumps(_A3_EVIDENCE.get("create_request", {}), indent=2))
        print(f"\nPOST /api/v1/engagements response:")
        print(json.dumps(_A3_EVIDENCE.get("create_response", {}), indent=2))
        print(f"\nDocument upload response ({len(_A3_EVIDENCE.get('upload_response', []))} files):")
        print(json.dumps(_A3_EVIDENCE.get("upload_response", []), indent=2))
        print(f"\nGate 1 approve request:")
        print(json.dumps(_A3_EVIDENCE.get("gate1_approve_request", {}), indent=2))
        print(f"\nGate 1 approve response:")
        print(json.dumps(_A3_EVIDENCE.get("gate1_approve_response", {}), indent=2))
        print(f"\nRULE_APPROVED audit event:")
        print(json.dumps(_A3_EVIDENCE.get("rule_approved_event", {}), indent=2))
        print(f"\nChain verify result:")
        print(json.dumps(_A3_EVIDENCE.get("chain_verify_result", {}), indent=2))
        print(f"\nTotal audit events: {_A3_EVIDENCE.get('audit_events_count')}")
        print("=== END A3 EVIDENCE ===\n")

"""FastAPI health check and basic API tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_create_and_get_engagement():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "engagement_code": "ENG-TEST-API-001",
            "borrower": {"name": "TestBank Corp"},
            "lender": {"name": "TestLender LP"},
            "test_date": "2024-12-31",
            "audit_team": [{"role": "associate", "email": "test@test.com", "name": "Test User"}],
        }
        create_resp = await client.post("/api/v1/engagements", json=payload)
        assert create_resp.status_code == 200
        data = create_resp.json()
        assert data["engagement_code"] == "ENG-TEST-API-001"
        eng_id = data["engagement_id"]

        get_resp = await client.get(f"/api/v1/engagements/{eng_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["engagement_id"] == eng_id


@pytest.mark.asyncio
async def test_list_engagements():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/engagements")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_nonexistent_engagement():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/engagements/ENG-DOES-NOT-EXIST")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_audit_verify_empty():
    """Verify chain on engagement with no events returns intact."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create engagement first
        payload = {
            "engagement_code": "ENG-AUDIT-TEST",
            "borrower": {"name": "AuditBank"},
            "lender": {"name": "Lender"},
            "test_date": "2024-12-31",
        }
        create_resp = await client.post("/api/v1/engagements", json=payload)
        eng_id = create_resp.json()["engagement_id"]

        verify_resp = await client.post(f"/api/v1/engagements/{eng_id}/audit/verify")
        assert verify_resp.status_code == 200
        result = verify_resp.json()
        assert result["is_intact"] is True
        assert result["total_events"] >= 1  # ENGAGEMENT_CREATED event

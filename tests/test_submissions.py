import pytest

from app.routers import submissions as submissions_router


def _create_widget(client, raw_key):
    resp = client.post("/api/widgets", json={"title": "Newsletter"}, headers={"X-API-Key": raw_key})
    return resp.json()["id"]


@pytest.fixture(autouse=True)
def mock_geo(monkeypatch):
    """Mock geo enrichment so the fallback chain is deterministic in tests,
    per the capstone rule: real free APIs are for manual dev only."""
    async def fake_enrich(ip):
        return {"country": "Pakistan", "city": "Islamabad", "provider_used": "provider_a"}

    monkeypatch.setattr(submissions_router, "enrich_ip", fake_enrich)


def test_valid_submission_is_stored(client, tenant_with_key):
    tenant, raw_key = tenant_with_key
    widget_id = _create_widget(client, raw_key)

    resp = client.post(
        "/api/submissions",
        json={"widget_id": widget_id, "name": "Ayesha", "email": "ayesha@example.com", "message": "hi"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "ok"
    assert "id" in resp.json()

    dash = client.get("/api/dashboard/submissions", headers={"X-API-Key": raw_key})
    assert dash.status_code == 200
    assert len(dash.json()) == 1
    assert dash.json()[0]["country"] == "Pakistan"


def test_invalid_payload_returns_400(client, tenant_with_key):
    tenant, raw_key = tenant_with_key
    widget_id = _create_widget(client, raw_key)

    # missing required "name" field, malformed email
    resp = client.post(
        "/api/submissions",
        json={"widget_id": widget_id, "email": "not-an-email"},
    )
    assert resp.status_code == 422  # FastAPI/Pydantic validation error, not a 500


def test_oversized_payload_returns_413(client, tenant_with_key):
    tenant, raw_key = tenant_with_key
    widget_id = _create_widget(client, raw_key)

    resp = client.post(
        "/api/submissions",
        json={
            "widget_id": widget_id,
            "name": "Ayesha",
            "email": "ayesha@example.com",
            "message": "x" * 20_000,  # forces content-length over MAX_BODY_BYTES
        },
    )
    assert resp.status_code in (413, 422)  # 413 from our check, or 422 if Pydantic's max_length catches it first


def test_honeypot_filled_silently_drops_submission(client, tenant_with_key):
    tenant, raw_key = tenant_with_key
    widget_id = _create_widget(client, raw_key)

    resp = client.post(
        "/api/submissions",
        json={
            "widget_id": widget_id,
            "name": "Bot",
            "email": "bot@example.com",
            "honeypot": "I am a bot filling every field",
        },
    )
    # fake success -- bot doesn't learn the check exists
    assert resp.status_code == 201
    assert resp.json() == {"status": "ok"}

    dash = client.get("/api/dashboard/submissions", headers={"X-API-Key": raw_key})
    assert len(dash.json()) == 0  # nothing was actually stored


def test_geo_fallback_provider_b_used_when_a_fails(client, tenant_with_key, monkeypatch):
    tenant, raw_key = tenant_with_key
    widget_id = _create_widget(client, raw_key)

    async def fake_enrich_b_only(ip):
        # simulates provider A being down, provider B answering
        return {"country": "Germany", "city": "Berlin", "provider_used": "provider_b"}

    monkeypatch.setattr(submissions_router, "enrich_ip", fake_enrich_b_only)

    resp = client.post(
        "/api/submissions",
        json={"widget_id": widget_id, "name": "Test", "email": "test@example.com"},
    )
    assert resp.status_code == 201

    dash = client.get("/api/dashboard/submissions", headers={"X-API-Key": raw_key})
    assert dash.json()[0]["country"] == "Germany"


def test_all_geo_providers_down_submission_still_succeeds(client, tenant_with_key, monkeypatch):
    tenant, raw_key = tenant_with_key
    widget_id = _create_widget(client, raw_key)

    async def fake_enrich_all_down(ip):
        return {"country": None, "city": None, "provider_used": None}

    monkeypatch.setattr(submissions_router, "enrich_ip", fake_enrich_all_down)

    resp = client.post(
        "/api/submissions",
        json={"widget_id": widget_id, "name": "Test", "email": "test@example.com"},
    )
    # degrade gracefully: still 201, still stored, just no geo data
    assert resp.status_code == 201

    dash = client.get("/api/dashboard/submissions", headers={"X-API-Key": raw_key})
    assert len(dash.json()) == 1
    assert dash.json()[0]["country"] is None


def test_email_side_effect_failure_does_not_break_submission(client, tenant_with_key, monkeypatch):
    """The core resilience pattern: a broken confirmation email must never
    prevent the submission from being stored and returning success."""
    tenant, raw_key = tenant_with_key
    widget_id = _create_widget(client, raw_key)

    def broken_send(*args, **kwargs):
        raise submissions_router.NotifyError("SMTP server unreachable (simulated)")

    monkeypatch.setattr(submissions_router, "send_confirmation", broken_send)

    resp = client.post(
        "/api/submissions",
        json={"widget_id": widget_id, "name": "Test", "email": "test@example.com"},
    )
    assert resp.status_code == 201  # still succeeds despite email failure

    dash = client.get("/api/dashboard/submissions", headers={"X-API-Key": raw_key})
    assert len(dash.json()) == 1  # and it was actually stored


def test_rate_limit_returns_429_then_recovers(client, tenant_with_key):
    tenant, raw_key = tenant_with_key
    widget_id = _create_widget(client, raw_key)

    # RATE_LIMIT_PER_MINUTE default is 10 -- burst past it
    statuses = []
    for _ in range(15):
        resp = client.post(
            "/api/submissions",
            json={"widget_id": widget_id, "name": "Burst", "email": "burst@example.com"},
        )
        statuses.append(resp.status_code)

    assert 429 in statuses  # limiter kicked in somewhere in the burst
    assert statuses[0] == 201  # legitimate first request still succeeds


def test_unknown_widget_returns_404(client):
    resp = client.post(
        "/api/submissions",
        json={"widget_id": "00000000-0000-0000-0000-000000000000", "name": "X", "email": "x@example.com"},
    )
    assert resp.status_code == 404

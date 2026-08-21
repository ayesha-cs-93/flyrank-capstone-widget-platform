from app.models import Tenant
from app.auth import hash_key


def test_create_widget_requires_auth(client):
    resp = client.post("/api/widgets", json={"title": "My Widget"})
    assert resp.status_code == 401


def test_create_and_get_widget(client, tenant_with_key):
    tenant, raw_key = tenant_with_key
    resp = client.post(
        "/api/widgets",
        json={"title": "Signup Form", "description": "Get updates"},
        headers={"X-API-Key": raw_key},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Signup Form"
    assert "widget.js?id=" in body["embed_snippet"]


def test_tenant_isolation(client, db_session, tenant_with_key):
    tenant_a, key_a = tenant_with_key
    tenant_b = Tenant(email="other@example.com", api_key_hash=hash_key("other-key"))
    db_session.add(tenant_b)
    db_session.commit()

    # tenant A creates a widget
    resp = client.post("/api/widgets", json={"title": "A's widget"}, headers={"X-API-Key": key_a})
    widget_id = resp.json()["id"]

    # tenant B tries to read it -> must be invisible (404, not the data)
    resp = client.get(f"/api/widgets/{widget_id}", headers={"X-API-Key": "other-key"})
    assert resp.status_code == 404

    # tenant B tries to delete it -> also invisible
    resp = client.delete(f"/api/widgets/{widget_id}", headers={"X-API-Key": "other-key"})
    assert resp.status_code == 404

    # tenant A can still see it fine
    resp = client.get(f"/api/widgets/{widget_id}", headers={"X-API-Key": key_a})
    assert resp.status_code == 200

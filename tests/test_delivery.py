def _create_widget(client, raw_key):
    resp = client.post("/api/widgets", json={"title": "Newsletter"}, headers={"X-API-Key": raw_key})
    return resp.json()["id"]


def test_widget_js_has_long_cache_header(client):
    resp = client.get("/widget.js")
    assert resp.status_code == 200
    assert "immutable" in resp.headers["cache-control"]
    assert "max-age=31536000" in resp.headers["cache-control"]


def test_config_endpoint_has_short_cache_and_cors(client, tenant_with_key):
    tenant, raw_key = tenant_with_key
    widget_id = _create_widget(client, raw_key)

    resp = client.get(f"/api/widgets/{widget_id}/config")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=60"
    assert resp.headers["access-control-allow-origin"] == "*"
    assert resp.json()["title"] == "Newsletter"


def test_config_endpoint_404_for_unknown_widget(client):
    resp = client.get("/api/widgets/does-not-exist/config")
    assert resp.status_code == 404


def test_cors_preflight_on_submissions(client):
    resp = client.options(
        "/api/submissions",
        headers={
            "Origin": "https://customer-site.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"

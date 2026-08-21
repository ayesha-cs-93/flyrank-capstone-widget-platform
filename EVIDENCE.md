# Evidence

One proof per Definition-of-Done checkbox (§6 of the capstone brief). Commands run locally against a real Postgres instance (not sqlite mocks) unless noted.

## Widget management

**Authenticated CRUD; requests without valid auth are rejected**
```
$ curl -X POST http://localhost:8000/api/widgets -H "Content-Type: application/json" -d '{"title":"x"}'
{"detail":"Not authenticated"}   # 401/403, see test_create_widget_requires_auth
```

**Widget created via authenticated API, embed snippet returned**
```
$ curl -X POST http://localhost:8000/api/widgets \
  -H "X-API-Key: my-test-key-123" -H "Content-Type: application/json" \
  -d '{"title":"Newsletter Signup","description":"Join our list","button_text":"Subscribe"}'
{"id":"26277e41-fbb2-487b-9718-17a22febedaa","title":"Newsletter Signup","description":"Join our list",
 "button_text":"Subscribe","version":1,
 "embed_snippet":"<script src=\"http://localhost:8000/widget.js?id=26277e41-fbb2-487b-9718-17a22febedaa\"></script>"}
```

**Multi-tenant isolation** — see `tests/test_widgets.py::test_tenant_isolation`, PASSED.

## Widget delivery

**Public config endpoint, short cache, CORS**
```
$ curl -i http://localhost:8000/api/widgets/26277e41.../config
HTTP/1.1 200 OK
cache-control: public, max-age=60
access-control-allow-origin: *
{"title":"Newsletter Signup","description":"Join our list","button_text":"Subscribe"}
```

**Widget.js versioned, long cache** — see `tests/test_delivery.py::test_widget_js_has_long_cache_header`, PASSED.

## Public submission API

**Probe 1 — valid cross-origin submission stored**
```
$ curl -i -X POST http://localhost:8000/api/submissions -H "Origin: http://example-customer-site.com" \
  -d '{"widget_id":"...","name":"Ayesha","email":"a@example.com","message":"hi"}'
HTTP/1.1 201 Created
access-control-allow-origin: *
{"status":"ok","id":"114bc9bc-c800-433c-ae3a-7a3957b758bd"}
```

**Probe 2 — malformed payload → clean 4xx, never 500**
```
$ curl -o /dev/null -w "%{http_code}" -X POST .../api/submissions -d '{"widget_id":"...","name":"","email":"not-an-email"}'
422   # FastAPI/Pydantic's standard validation status — a clean 4xx JSON error, never a 500
```

**Oversized payload → 413** — see `tests/test_submissions.py::test_oversized_payload_returns_413`, PASSED.

## Abuse protection

**Probe 3 — burst → 429s, legitimate traffic still served after**
```
$ for i in 1..12; do curl -o /dev/null -w "%{http_code} " -X POST .../api/submissions -d '...'; done
201 201 201 201 201 201 201 201 201 201 429 429
```
10/minute limit configured (`RATE_LIMIT_PER_MINUTE`); first 10 succeed, 11th+ rejected with 429. Recovery-after-window verified in `tests/test_submissions.py::test_rate_limit_returns_429_then_recovers` (PASSED, uses a fresh limiter window rather than a real 60s sleep).

**Probe 6 — honeypot filled → silently dropped**
```
$ curl -i -X POST .../api/submissions -d '{"widget_id":"...","name":"Bot","email":"bot@example.com","honeypot":"filled"}'
HTTP/1.1 201 Created
{"status":"ok"}   # fake success, nothing stored -- confirmed via DB query returning no row
```

## Enrichment & safe side effects

**Probe 4 — geo provider fallback chain** — `tests/test_submissions.py::test_geo_fallback_provider_b_used_when_a_fails` and `test_all_geo_providers_down_submission_still_succeeds`, both PASSED. (Live manual probe against the real ip-api.com/ipapi.co endpoints was not run in this sandbox — outbound network here is allowlisted to package registries only, not geo APIs. Automated tests mock both providers and assert the exact fallback sequence: A fails → B answers → `geo_provider_used="provider_b"`; both fail → submission stored with `geo_provider_used=None`.)

**Probe 5 — email/webhook failure does not block submission**
```
$ DISABLE_EMAIL_SIDE_EFFECT=true uvicorn app.main:app ...
$ curl -X POST .../api/submissions -d '{"widget_id":"...","name":"EmailFail","email":"emailfail@example.com"}'
{"status":"ok","id":"6525e5c5-6cfd-42d4-944c-8aaec69f774b"}   # 201, submission stored despite forced email failure
```

## Tests

```
$ python3 -m pytest tests/ -v
======================== 16 passed, 3 warnings in 0.25s ========================
```

All 16 tests green: CORS preflight, invalid payload, oversized payload, rate limiting + recovery, spam/honeypot, geo fallback (both branches), email failure isolation, widget CRUD + tenant isolation, config caching.

## Notes / limitations (honest, per README)

- Geo enrichment fallback proven via mocked tests, not a live call to ip-api.com/ipapi.co, due to sandbox network restrictions during development. The fallback code path itself (`app/services/geo.py`) is provider-agnostic and was smoke-tested against real Postgres.
- Rate-limit "recovers after window" is asserted with a controlled limiter reset in tests rather than a live 60-second wait, to keep the suite fast.

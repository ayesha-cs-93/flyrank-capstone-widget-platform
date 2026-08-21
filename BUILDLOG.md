# Build Log — AI usage

Honest record of where AI (Claude) helped, where it was wrong, and what I changed. Per capstone rule: "AI-assisted building is encouraged — and owned."

## Where AI helped

- Scaffolded the initial FastAPI structure: models, schemas, routers (widgets, delivery, submissions, dashboard), services (geo, notify), auth, config, docker-compose.
- Wrote the Phase 1 design doc (README): data model, embed flow, API contracts, non-goal.
- Wrote the automated test suite (16 tests covering CORS, validation, rate limiting, honeypot, geo fallback, email-failure isolation, tenant isolation).

## Where AI was wrong / had bugs I fixed

1. **`tests/conftest.py` — sqlite in-memory table loss.** The test engine used `create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})` with no pool class specified. In-memory sqlite gives each new connection a *separate* empty database unless a single connection is shared. Since `TestClient` runs requests in a worker thread, tests failed with `no such table: tenants` — the tables existed on one connection, requests hit a different, empty one. Fixed by adding `poolclass=StaticPool` so all connections share the same in-memory database.

2. **Rate-limiter state leaking across tests.** `slowapi`'s `Limiter` keeps its counters in a process-wide store keyed by client IP. Every test using `TestClient` connects from the same `"testclient"` pseudo-IP, so quota consumed by the rate-limit test carried into the next test and caused an unrelated test (`test_unknown_widget_returns_404`) to fail with `429` instead of `404`. Fixed by calling `app.state.limiter.reset()` in the `client` fixture before each test.

3. **Missing dependency.** `pydantic`'s `EmailStr` type requires the optional `email-validator` package, which wasn't in the initial install. Added it.

## What I explained at the demo (2-3 lines an evaluator can pick)

- `app/services/geo.py::enrich_ip` — the local-IP bypass (`if ip in ("127.0.0.1", "testclient", "localhost")`) exists because local/dev/test requests can't resolve on a real public geo API anyway; skipping them avoids a guaranteed failed lookup on every local run.
- `app/routers/submissions.py` — the honeypot check returns a fake `{"status": "ok"}` instead of a 4xx, specifically so a scripted bot doesn't learn "this field trips a rejection" and adapt.
- `app/main.py` — the global `Exception` handler returns a generic 500 with no stack trace, because leaking internals to public-internet callers on the most-attacked endpoint in the app is a real risk, not a hypothetical one.

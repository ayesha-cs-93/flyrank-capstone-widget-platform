# Embeddable Widget & Lead-Capture Platform

FlyRank Backend AI Engineering Capstone — a platform that lets a customer create an embeddable signup-form widget, hand out one `<script>` tag, and safely accept submissions from any website on the public internet: validated, rate-limited, spam-filtered, geo-enriched, and shown on a dashboard.

## Problem

Customers need a way to collect leads from their own websites without building backend infrastructure. This system provides:
- An authenticated API to create/manage widgets
- A public, cached endpoint that serves widget config + a versioned JS bundle
- A public, CORS-enabled submission endpoint that survives abuse from the open internet
- A dashboard API showing submissions and stats, isolated per tenant

## Non-goal

**Multiple widget types.** This capstone ships exactly one widget type — a signup form (email + name + optional message). No CTA popovers, no form-builder UI, no drag-and-drop field editor. The goal is to prove the hard backend patterns (CORS, rate limiting, fallback enrichment, safe side effects) once, correctly — not to build a form-builder product.

## Data model

**tenants**
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| email | text unique | |
| api_key_hash | text | for widget management auth |
| created_at | timestamptz | |

**widgets**
| column | type | notes |
|---|---|---|
| id | uuid PK | used in embed snippet `?id=` |
| tenant_id | uuid FK → tenants | indexed, every query scoped to this |
| title | text | |
| description | text | |
| button_text | text | default "Submit" |
| version | int | bumped on config change → busts cache |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**submissions**
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| widget_id | uuid FK → widgets | indexed |
| tenant_id | uuid FK → tenants | denormalized, indexed — avoids join on every dashboard query |
| name | text | |
| email | text | |
| message | text nullable | |
| ip_address | text | raw submitter IP, stored for enrichment + rate limit key |
| country | text nullable | from geo enrichment, null if all providers failed |
| city | text nullable | |
| geo_provider_used | text nullable | "provider_a" / "provider_b" / null — for debugging/evidence |
| spam_flagged | bool default false | honeypot hit |
| created_at | timestamptz | indexed, used for time-series stats |

Indexes: `widgets(tenant_id)`, `submissions(widget_id)`, `submissions(tenant_id, created_at)`.

## Embed flow

```
1. Owner creates widget         → POST /api/widgets            (authenticated)
2. API returns embed snippet    → <script src=".../widget.js?id={widget_id}"></script>
3. Customer pastes snippet on their site (any origin)
4. Browser loads widget.js      → GET /widget.js                (public, cached long, versioned)
5. Script fetches config        → GET /api/widgets/{id}/config  (public, cached short, CORS)
6. Script renders a form in the page
7. Visitor submits               → POST /api/submissions         (public, CORS, protected)
8. Server: validate → rate-limit/spam-check → geo-enrich (fallback chain) → store → fire-and-forget email
9. Owner views results           → GET /api/dashboard/*          (authenticated, tenant-scoped)
```

## API contracts

### Path 1 — Widget owner (authenticated, header `X-API-Key`)
- `POST /api/widgets` — create widget → `201 {id, embed_snippet}`
- `GET /api/widgets` — list own widgets → `200 [...]`
- `GET /api/widgets/{id}` — get one (403 if not owner)
- `PATCH /api/widgets/{id}` — update, bumps `version`
- `DELETE /api/widgets/{id}`

### Path 2 — Customer site (public, cached, CORS: `*` for config/script)
- `GET /widget.js` — versioned static bundle, `Cache-Control: public, max-age=31536000, immutable`
- `GET /api/widgets/{id}/config` — `{title, description, button_text}`, `Cache-Control: public, max-age=60`

### Path 3 — Visitor (public, CORS, protected)
- `POST /api/submissions` — body `{widget_id, name, email, message?, honeypot}`
  - `201` on success (even if geo/email failed)
  - `400` malformed payload (Pydantic validation)
  - `413` oversized payload
  - `429` rate limit exceeded
  - honeypot filled → `200` fake-success, silently dropped, never stored

### Path 4 — Dashboard (authenticated, tenant-scoped)
- `GET /api/dashboard/submissions?widget_id=` — paginated list
- `GET /api/dashboard/stats?widget_id=` — counts over time, geo breakdown

## Architecture

```
                              ┌─────────────────────────┐
                              │   Widget Owner (you)     │
                              │  authenticated, X-API-Key│
                              └────────────┬─────────────┘
                                           │
                          POST/GET/PATCH/DELETE /api/widgets
                                           │
                                           ▼
                              ┌─────────────────────────┐
                              │   Widget Management API  │
                              │   (tenant-isolated CRUD) │
                              └────────────┬─────────────┘
                                           │
                                           ▼
                                    ┌─────────────┐
                                    │  Postgres   │
                                    │  tenants    │
                                    │  widgets    │
                                    │ submissions │
                                    └──────┬──────┘
                                           ▲
                                           │
        ┌──────────────────────────────────┼──────────────────────────────────┐
        │                                   │                                  │
        │                          Path 2: delivery                  Path 3: submission
        │                        (public · cached · CORS)          (public · CORS · protected)
        │                                   │                                  │
┌───────┴────────┐              ┌──────────▼──────────┐          ┌───────────▼────────────┐
│ Customer Website │  <script>  │  GET /widget.js       │         │  POST /api/submissions   │
│ (any origin —    │───loads───▶│  GET /widgets/:id/     │         │                          │
│ different port    │            │       config          │         │  validate (Pydantic)     │
│ than the API)     │            │  cache: long / short   │         │       │                  │
└───────┬────────┘              └──────────┬──────────┘          │       ▼                  │
        │                                   │                     │  rate-limit + honeypot   │
   renders widget                    returns config                │  spam check ── flood?    │
   in the page                       (title, button)                │       │ → 429            │
        │                                                          │       ▼                  │
        ▼                                                          │  geo enrich: Provider A  │
┌────────────────┐                                                 │   ↓ fails                 │
│ Website Visitor  │──── submits form ─────────────────────────────▶│  Provider B               │
│ (the whole        │                                                │   ↓ fails                 │
│  public internet) │                                                │  store anyway (no geo)    │
└────────────────┘                                                 │       │                  │
                                                                    │       ▼                  │
                                                                    │  store submission         │
                                                                    │       │                  │
                                                                    │       ▼                  │
                                                                    │  email/webhook side       │
                                                                    │  effect (fire-and-forget, │
                                                                    │  failure never blocks     │
                                                                    │  the 201 response)        │
                                                                    └───────────────────────────┘
                                           ▲
                                           │
                              Path 4: dashboard (authenticated)
                              GET /api/dashboard/submissions
                              GET /api/dashboard/stats
                              (always scoped to tenant_id)
                                           │
                              ┌────────────┴─────────────┐
                              │   Widget Owner (you)      │
                              └────────────────────────────┘
```

Four request paths, kept deliberately separate in the code (different routers, different auth model):
1. **Owner → Widget Management** — authenticated, tenant-isolated CRUD.
2. **Customer site → Delivery** — public, cached, no auth (anyone can load a script tag).
3. **Visitor → Submission** — public, CORS, but hardened: validation → rate-limit/spam → geo-enrich with fallback → store → safe side effect.
4. **Owner → Dashboard** — authenticated, every query filtered by `tenant_id`.



Python + FastAPI, PostgreSQL (Docker), Pydantic for validation, slowapi for rate limiting, ip-api.com + ipapi.co for geo fallback, console-log for email side effect.

## Status

Phase 1 (design) — done.
Phase 2 (hardened submission path) — done. 16/16 automated tests pass. All Definition-of-Done probes (§12 of brief) manually verified against a real Postgres instance — see EVIDENCE.md.
Phase 3 (delivery, customer test page, dashboard) — widget.js + public config delivery done, dashboard API done (tenant-scoped stats + submission list), customer test page (`customer-site/index.html`) served from a separate origin/port and verified end-to-end.
Remaining: README architecture diagram polish, final EVIDENCE.md pass, push to public GitHub repo.

## Running it

```
docker compose up -d          # postgres
pip install -r requirements.txt
uvicorn app.main:app --reload # api on :8000

# in a second terminal, serve the customer test page on a different origin:
cd customer-site && python3 -m http.server 5500
```

Then open `http://localhost:5500` — the widget renders on a page served from a different origin than the API, exactly as the capstone requires.

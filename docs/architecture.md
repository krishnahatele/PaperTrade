# MarketOS architecture

> Status: **Phase 0–2 implemented** (foundation, encrypted credentials and auth, Telegram ingestion).
> Signal parsing, market data, paper execution and live Kite routing are designed but not yet built.

## 1. What MarketOS is

MarketOS is a signal-driven trading workstation for Indian markets. Trade ideas
arrive from sources such as Telegram channels. They are turned into structured
signals, checked against risk rules, and executed. Execution is **paper by
default** and live only when explicitly enabled. Zerodha Kite is the target broker.

```
Telegram ─► RawMessage ─► (parser: rules / LLM) ─► Signal ─► (risk) ─► Order ─► Broker (paper | Kite)
                                                                         │
                         Market data (Kite ticker) ─► quotes ────────────┘──► Trades ─► Positions
                                     every step emits Events ─► EventBus ─► events table (audit)
```

## 2. Repository layout

```
.
├── apps/
│   ├── api/                 FastAPI backend (Python 3.11+, uv)
│   │   ├── app/
│   │   │   ├── core/        config, logging, middleware, errors
│   │   │   ├── db/          declarative base, naming conventions, engine/session
│   │   │   ├── models/      SQLAlchemy ORM models (one file per aggregate)
│   │   │   ├── schemas/     Pydantic request/response models
│   │   │   ├── api/         health router + versioned routers (api/v1/routes/*)
│   │   │   ├── services/    application services, repository, adapter registry
│   │   │   ├── adapters/    external-system ports: broker, market_data, telegram, llm
│   │   │   ├── events/      Event model, EventBus, EventStore
│   │   │   ├── container.py composition root
│   │   │   └── main.py      app factory
│   │   ├── alembic/         migrations
│   │   └── tests/
│   └── web/                 Next.js 16 App Router frontend (TypeScript, Tailwind v4)
│       └── src/{app,components,lib}
├── infra/postgres/init/     first-boot SQL (creates the test database)
├── docs/                    architecture, database, API
├── docker-compose.yml       db + api + web
└── Makefile                 common dev commands
```

## 3. Backend layering

| Layer | Responsibility | Depends on |
|---|---|---|
| `api/` (routes) | HTTP concerns only: parsing, status codes, pagination | services, schemas |
| `services/` | Business rules, transactions, emitting events | models, repository, adapters, events |
| `adapters/` | Talking to the outside world behind abstract interfaces | schemas (own DTOs) |
| `models/` | Persistence shape | db |
| `events/` | Domain event envelope and dispatch | models (EventRecord) |
| `core/` | Cross-cutting: config, logging, errors | – |

Rules:

* Routes never touch adapters directly. They go through services.
* Nothing reads `os.environ`. Everything goes through `core.config.Settings`.
* Money and prices are `Decimal` (`NUMERIC(18,4)`), never floats.
* Every timestamp is timezone-aware UTC (`TIMESTAMPTZ`).

### Composition root

`app/container.py` builds long-lived objects once per process (`Settings`, `Database`,
`InMemoryEventBus` with the `EventStore` subscribed to `*`, and `AdapterRegistry`).
It stores them on `app.state.container` during the FastAPI lifespan.
Dependencies in `api/deps.py` read from it, so tests can build an app with any
`Settings` via `create_app(settings)`.

### Adapters (ports)

Each adapter is an abstract base class with a `health()` probe plus capability
methods, and ships with a `Disabled*` implementation used in Phase 0:

| Interface | Methods | Planned implementation |
|---|---|---|
| `BrokerAdapter` | `place_order`, `cancel_order`, `get_order`, `get_positions` | `PaperBrokerAdapter`, `KiteBrokerAdapter` |
| `MarketDataAdapter` | `get_quotes`, `subscribe(on_tick)`, `unsubscribe` | Kite Ticker WebSocket |
| `TelegramAdapter` | `start(channels, on_message)`, `stop`, `fetch_history` | Telethon (MTProto user client) |
| `LLMAdapter` | `complete(LLMRequest) -> LLMResponse` with optional JSON schema | Anthropic Claude |

`AdapterRegistry.from_settings()` is the single place that selects implementations.

### Event bus

* `Event` is an immutable Pydantic model: `id`, `type`, `occurred_at`, `aggregate_type`,
  `aggregate_id`, `correlation_id`, `causation_id`, `payload`.
  `event.caused(...)` creates follow-ups that keep the correlation chain.
* `EventBus` is a protocol, and `InMemoryEventBus` dispatches to type-specific and
  wildcard handlers concurrently. A failing handler is logged and isolated.
* `EventStore` persists every event to the append-only `events` table, which is the audit log.

### Configuration

`pydantic-settings` with prefix `MARKETOS_`, see `.env.example`. Secrets are `SecretStr`
and never appear in `repr`/logs. A model validator **refuses to start** when live trading
is requested in this build.

### Logging

`structlog` renders JSON in containers (`MARKETOS_LOG_JSON=false` gives a console renderer).
Uvicorn/SQLAlchemy/Alembic logs go through the same pipeline. `RequestContextMiddleware`
binds a `request_id` (from `X-Request-ID` or generated), echoes it in the response,
and logs `request.completed` with method, path, status and duration.

### Errors

Domain errors subclass `MarketOSError` and are rendered as
`{"error": {"code", "message"}}` with their status code (`NotFoundError` 404,
`ConflictError` 409, `FeatureDisabledError` 403). Validation errors use FastAPI's
standard 422 body.

### Security (Phase 1)

* **Credentials at rest**: `SecretStore` encrypts every credential with Fernet before it reaches
  the `secrets` table. The master key comes from `MARKETOS_SECRET_KEY` or is generated once into
  `MARKETOS_SECRET_KEY_FILE` (mode 0600, the `apisecrets` Docker volume). The API never returns a
  stored value, only "set" plus a masked hint.
* **Auth**: one admin password (scrypt hash in `secrets`). Tokens are HMAC-SHA256 signed with a
  key derived from the master key and carry an expiry and a *generation*. Changing the password
  bumps the generation, which revokes every outstanding token. Failed logins are rate limited.
* **Runtime settings** (`app_settings`): kill switch, auto-execute, live-armed, confidence threshold,
  signal TTL, parser mode and model.

### Telegram ingestion (Phase 2)

`TelegramService` owns a `TelethonTelegramAdapter` built from the encrypted API ID and hash and
the (encrypted) session string. Login is: send code to the saved phone, submit the code, then
optionally the 2FA password, after which the session string is stored. On startup (when
`MARKETOS_BACKGROUND_SERVICES=true`) it reconnects and listens to every **enabled** `telegram`
source. Each new post becomes a `RawMessage` (deduplicated by `(source_id, external_message_id)`)
and a `raw_message.received` event. Edits and deletions are not processed yet. Health is served
from cached state so status endpoints never block on Telegram's network.

## 4. Frontend

* Next.js App Router, client components fetching the API directly (`NEXT_PUBLIC_API_URL`, CORS-enabled).
* Shell = `Sidebar` (sectioned nav from `lib/nav.ts`, collapsible on mobile) + `Topbar`
  (page title, trading-mode badge, live API readiness).
* `DataTable` handles paginated `Page<T>` endpoints. `useApi` is a tiny fetch hook with optional polling.
* Output is `standalone` for a small Docker image.

## 5. Runtime topology (Docker Compose)

| Service | Image | Port | Health |
|---|---|---|---|
| `db` | postgres:16-alpine | 5432 | `pg_isready` |
| `api` | `apps/api/Dockerfile` | 8000 | `GET /health`. Runs `alembic upgrade head` on start |
| `web` | `apps/web/Dockerfile` | 3000 | `GET /` |

## 6. Safety model

1. `Settings` rejects `trading_mode=live` / `live_trading_enabled=true` in this build. The runtime
   `live_armed` switch cannot be turned on unless that server-level flag is set.
2. `AdapterRegistry` only wires `DisabledBrokerAdapter`, which raises on every order call.
3. The API exposes **no** order-mutation endpoints (asserted by a test on the OpenAPI spec).
4. Creating a `live` broker account is rejected with 403.

## 7. Known limitations / next steps

* `EventStore` writes in its own transaction after the publisher commits. A
  transactional outbox should replace it before execution flows land.
* The in-memory bus is single-process. Run one API replica until a durable bus exists.
* No authentication yet. The API must not be exposed beyond localhost.

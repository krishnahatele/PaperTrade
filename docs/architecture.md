# MarketOS architecture

> Status: **Phase 0–4 implemented**: foundation, encrypted credentials and auth, Telegram ingestion,
> signal parsing (any AI provider), Kite prices and **paper trading**. Live (real-money) order routing
> is not built; live accounts are refused everywhere.

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

### Signal parsing (Phase 3)

`SignalPipeline` subscribes to `raw_message.received` and runs in the background (inline in tests):

1. **Rules parser** (`app/parsing/rules.py`): normalises text (case, emojis, ₹, `24,500`, index
   aliases such as BANK NIFTY → BANKNIFTY, CALL/PUT → CE/PE) and extracts side, instrument
   (equity, `NIFTY 24500 CE`, `TATAMOTORS FUT`, optional expiry month), entry or range, SL and
   targets (`TGT 140/160`, `T1 … T2 …`). Follow-ups such as "target hit" or "book profit" are
   ignored. Verb-less option calls are assumed BUY with a warning. Confidence comes from
   completeness, and is cut when levels are inconsistent (e.g. BUY with SL above entry).
2. **AI fallback** (`app/parsing/llm.py`): only when rules confidence is below 0.8, the message
   looks trade-like, and the message is not stale. The provider is selectable in Settings:
   `AnthropicLLMAdapter` (Claude; default `claude-haiku-4-5` for low cost; `effort` and
   server-side refusal fallback are sent only to models that accept them) or
   `OpenAICompatibleAdapter` for Gemini, Groq, DeepSeek, OpenAI, OpenRouter, Ollama or any custom
   `/chat/completions` server (JSON-schema output, falling back to JSON mode then plain text if
   the provider doesn't support it). API keys are encrypted per provider; the model dropdown is
   filled from the provider's live `/models` list. Output is treated as untrusted and
   re-validated. At most 2 concurrent calls. Modes: rules only, rules then AI (default), AI only.
3. **Instrument resolution** (`InstrumentService.resolve`): equities by NSE then BSE symbol; F&O
   by underlying + type (+ strike) at the nearest unexpired expiry (respecting a stated month).
   The instrument master comes from Kite's public dump (`POST /instruments/sync`).
4. **Status**: `validated` when the instrument resolved, the entry and SL are present, levels are
   consistent and confidence ≥ the `min_confidence` setting. `expired` when the message is older
   than the signal TTL (catch-up after downtime never creates live signals). Otherwise `new`
   (needs review in the UI).

On startup `TelegramService.boot` also **catches up** on the last 50 messages of every enabled
channel (deduplicated), so messages posted while the app was off are not lost.

### Paper trading (Phase 4)

* **Kite login** (`KiteService`): API key/secret saved encrypted, then a daily login. Open the Kite
  login URL, sign in, and paste the redirect URL back. The `request_token` is exchanged for an
  access token (encrypted). `MarketDataService` polls Kite LTP (REST, 1.5 s cache). Without Kite,
  prices can be set by hand for practice.
* **Trade plans** (`trade_plans`): `TradingEngine.execute_signal` runs risk checks (kill switch,
  account active and paper, signal validated and fresh, no duplicate, max open trades, daily
  loss limit, shorting allowed) and sizes the position from the account's `AccountRiskSettings`:
  risk % of capital / |entry − SL|, rounded down to lots, capped by max position %, with an
  optional 1-lot minimum. The entry type depends on where the price is: inside the call's range
  → MARKET; not yet reached ("BUY ABOVE") → SL-M stop-entry; already beyond → LIMIT for a
  pullback. Unfilled entries expire after the signal TTL.
* **Bracket**: when the entry fills, an SL-M stop and a LIMIT target (target # from settings) are
  placed. When one fills the other is cancelled (OCO), and the plan closes with realized P&L net
  of per-order charges.
* **Matching** (`tick`, every 2 s): MARKET fills at LTP ± slippage rounded to tick; LIMIT when
  marketable; SL-M when triggered. Fills create `trades`, net into `positions` (average price,
  realized P&L, flips) and emit `order.*`, `trade.executed` and `trade_plan.*` events.
* **Auto-execution**: on `signal.created` / `signal.status_changed` to `validated`, when the global
  *auto-execute* setting is on, every active paper account with `auto_execute` gets the trade.
  Skips are recorded as `signal.execution_skipped` with the reason.
* A **"Paper"** account (₹1,00,000) is created on startup.

### Phase 5: trade management, brokers, bot, news, replay

* **Target ladders & trailing** (`services/risk.py`, `services/trading.py`): a trade's quantity is
  split lot-wise over TP1, TP2, … (`exit_mode=split`, front-loaded) or put on one target
  (`single`). After entry: one SL-M stop for `open_quantity` and one LIMIT per open leg. A target
  fill reduces `open_quantity`, shrinks the stop and trims later legs. Trailing: `step` (SL → cost
  after TP1, → TP1 after TP2), or `points`/`percent` from the best price, checked every tick; the
  stop only ever tightens. `update_plan` edits SL/targets/trailing live, `exit_plan` exits whole
  lots, `enter_now` replaces a waiting entry with a market order, `exit_all` is the panic button.
* **Brokers** (`adapters/broker/{providers,dhan,kite}.py`, `services/brokers.py`): a registry
  drives the Settings form. Dhan (DhanHQ v2, fields from the official SDK) and Kite adapters
  implement profile/funds/positions and the order calls (Dhan Super Orders with trailing, exit-all,
  kill switch). Only the read-only calls are used; nothing routes orders to them. Dhan tokens are
  renewed every ~20 h by a housekeeping task. `instruments.broker_refs.dhan` comes from Dhan's
  scrip master. `MarketDataService` picks Kite or Dhan per `BrokerRuntime.market_data`.
* **Telegram bot** (`adapters/telegram/bot_api.py`, `services/bot.py`): Bot API long-polling, a
  per-trade card edited in place with inline buttons, a persistent keyboard, a pinned status
  message, alerts for fills/targets/stops/news/moves. Linked to one owner chat by a one-time code;
  can be created through the user's own Telegram login (@BotFather conversation).
* **News** (`services/news.py`): RSS feeds every few minutes → `news_items`; keyword matches within
  6 h → `alerts` + `news.alert`. Watched instruments are checked every minute; a move ≥ threshold
  within the window → `market.alert` (with cooldown).
* **Replay** (`replay/simulator.py`, `replay/report.py`, `services/replay.py`,
  `adapters/history/*`): messages from Telegram history (or stored ones) for chosen IST days →
  rules (or AI) parse → contract resolved *as of that day* → 1-minute candles from Kite or Dhan
  (Dhan's rolling-option data for expired index options) → candle-by-candle simulation with the
  same entry/exit rules, intraday square-off, conservative same-candle ordering → report. Writes
  only `replay_*` tables.
* **Segments**: instruments sync NSE, NFO, BSE, BFO and MCX; commodity aliases (crude, natural gas,
  gold mini…) and plain commodity calls resolve to the nearest MCX future.

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
2. The trading engine refuses any account whose mode is not `paper`. Broker adapters (Kite,
   Dhan) exist for read-only use (connection test, positions, prices, candles); the engine never
   calls their order methods. Live execution would also need a static IP registered at the broker.
3. Creating a `live` broker account is rejected with 403.
4. The kill switch blocks every new order (signal-driven and manual). EXIT ALL (portal top bar or
   Telegram bot, with confirmation) turns it on and exits everything.
5. The Telegram bot obeys only the linked owner chat; button presses from anyone else are refused.

## 7. Known limitations / next steps

* `EventStore` writes in its own transaction after the publisher commits. A
  transactional outbox should replace it before execution flows land.
* The in-memory bus is single-process. Run one API replica until a durable bus exists.
* Single admin password; keep the API behind it and don't share the URL.

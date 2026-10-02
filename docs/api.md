# API reference

Base URL (local): `http://localhost:8000`. Interactive docs: `/docs` (Swagger UI), `/redoc`.
Machine-readable spec: `/openapi.json`.

## Conventions

* Versioned routes live under `/api/v1`. Health routes are unversioned.
* JSON everywhere. Decimals are serialised as **strings** (`"1500.0000"`) to preserve precision.
  Timestamps are ISO-8601 UTC.
* **Pagination**: list endpoints accept `limit` (1–500, default 50) and `offset` (default 0) and return
  `{"items": [...], "total": n, "limit": l, "offset": o}`.
* **Errors**: domain errors return `{"error": {"code": "...", "message": "..."}}`:

  | Status | code | When |
  |---|---|---|
  | 404 | `not_found` | Unknown id, or a referenced id does not exist |
  | 409 | `conflict` | Uniqueness violation |
  | 403 | `feature_disabled` | Capability not available yet (e.g. live accounts) |
  | 422 | (FastAPI) | Request validation failed, `{"detail": [...]}` |

* Every response carries `X-Request-ID` (echoed if you send one) for log correlation.
* No authentication in Phase 0. Bind to localhost only.

## Health

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness. Always `{"status":"ok"}` while the process runs |
| GET | `/health/ready` | Readiness. Checks the database. `200 {"status":"ok"}` or `503 {"status":"degraded"}` with per-check details |

## System

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/system/info` | Version, environment, trading mode, live flag, phase, health of each adapter |

## Instruments

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/instruments` | Filters: `exchange`, `q` (symbol prefix, case-insensitive) |
| POST | `/api/v1/instruments` | Body: `exchange`, `tradingsymbol`, `instrument_type`, optional `name`, `instrument_token`, `segment`, `expiry`, `strike`, `lot_size`, `tick_size` |
| GET | `/api/v1/instruments/{id}` | |

## Broker accounts

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/broker-accounts` | |
| POST | `/api/v1/broker-accounts` | `broker` (`paper`/`kite`), `label`, `mode` (`paper` only, `live` gives 403), `credentials_ref` (a pointer, never a secret) |
| GET | `/api/v1/broker-accounts/{id}` | |

## Signal sources & raw messages

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/signal-sources` | |
| POST | `/api/v1/signal-sources` | `kind` (`telegram`/`manual`/`webhook`), `name`, `external_id`, `is_enabled`, `config` |
| GET | `/api/v1/signal-sources/{id}` | |
| GET | `/api/v1/signal-sources/{id}/messages` | Raw inbound messages for the source, newest first |

## Signals

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/signals` | Filters: `status`, `source_id`. Newest first |
| POST | `/api/v1/signals` | Manual entry. `source_id`, `symbol_text`, `side`, optional `instrument_id`, `entry_low`, `entry_high` (low ≤ high), `stop_loss`, `targets[]`, `notes`. Does **not** trigger execution |
| GET | `/api/v1/signals/{id}` | |

Example:

```bash
curl -s -X POST localhost:8000/api/v1/signals -H 'content-type: application/json' -d '{
  "source_id": "<uuid>", "symbol_text": "INFY", "side": "BUY",
  "entry_low": "1500", "entry_high": "1510", "stop_loss": "1480", "targets": ["1550", "1600"]
}'
```

## Orders, trades, positions (read-only)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/orders` | Filters: `status`, `broker_account_id` |
| GET | `/api/v1/orders/{id}` | |
| GET | `/api/v1/orders/{id}/trades` | Fills for an order (array, not paginated) |
| GET | `/api/v1/positions` | Filter: `broker_account_id` |

There are intentionally no endpoints that create, modify or cancel orders in this build.

## Events

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/events` | Audit log, newest first. Filters: `event_type`, `aggregate_id`, `correlation_id` |

Event types emitted today: `system.started`, `system.stopping`, `instrument.created`,
`signal_source.created`, `broker_account.created`, `signal.created`.

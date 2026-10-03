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
* **Authentication**: every `/api/v1/*` route except `/api/v1/auth/*` requires
  `Authorization: Bearer <token>` (401 otherwise). Health routes are public.
  Disable only for local experiments with `MARKETOS_AUTH_ENABLED=false`.

## Auth

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/auth/status` | `{auth_enabled, configured, authenticated}` |
| POST | `/api/v1/auth/setup` | First run only: `{password}` (≥ 10 chars), returns `{token, expires_at}`. 409 once set |
| POST | `/api/v1/auth/login` | `{password}` gives a token. 401 on a wrong password, 429 after 5 failures per minute |
| POST | `/api/v1/auth/change-password` | `{current_password, new_password}`. Revokes all previous tokens |

## Integrations (write-only credentials)

Responses only say whether each credential is set, plus a masked hint (`••••3210`). Values are never returned.

| Method | Path | Body |
|---|---|---|
| GET | `/api/v1/integrations` | Status of telegram / kite / llm |
| PUT | `/api/v1/integrations/telegram` | any of `api_id` (digits), `api_hash` (32 hex), `phone` (`+<country><number>`). Resets the Telegram session |
| DELETE | `/api/v1/integrations/telegram` | Logs out and removes all Telegram credentials |
| PUT / DELETE | `/api/v1/integrations/kite` | `api_key`, `api_secret` |
| PUT | `/api/v1/integrations/llm` | `{provider?, api_key}`. Keys are stored per provider (defaults to the active one) |
| DELETE | `/api/v1/integrations/llm?provider=` | Removes that provider's key |

## Runtime settings

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/settings` | `{trading, parsing}` |
| PATCH | `/api/v1/settings/trading` | `kill_switch`, `auto_execute`, `live_armed` (403 unless `MARKETOS_LIVE_TRADING_ENABLED=true`), `min_confidence` (0–1), `signal_ttl_minutes` |
| PATCH | `/api/v1/settings/parsing` | `mode` (`rules_only` / `rules_then_llm` / `llm_only`), `llm_provider` (`anthropic`, `gemini`, `groq`, `deepseek`, `openai`, `openrouter`, `nvidia`, `ollama`, `custom`), `llm_model`, `llm_base_url` (custom/ollama only) |

## AI providers

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/llm/providers` | Presets with label, base URL, note, suggested models, `key_set`, `active` |
| GET | `/api/v1/llm/models?provider=` | Live chat-model list from the provider (needs its key). Embedding/audio/image models are filtered out |
| POST | `/api/v1/llm/test` | `{text?}`. Parses a sample with the active model (one paid call) |

## Telegram

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/telegram/status` | configured, authorized, listening, channel count, login step, counters, last error |
| POST | `/api/v1/telegram/login/start` | Sends a login code to the saved phone number, returns `{step: "code"}` |
| POST | `/api/v1/telegram/login/code` | `{code}` returns `{step: "done"}` or `{step: "password"}` (2FA) |
| POST | `/api/v1/telegram/login/password` | `{password}` returns `{step: "done"}` |
| POST | `/api/v1/telegram/logout` | Ends the session and deletes it |
| GET | `/api/v1/telegram/channels` | Your channels/groups, with `source_id` if already added |
| POST | `/api/v1/telegram/channels` | `{channel_id, name, enabled}` creates a `telegram` signal source and starts listening |
| POST | `/api/v1/telegram/sources/{id}/backfill?limit=50` | Fetches recent history and stores new messages, returning `{stored}` |

Telegram errors: 403 `feature_disabled` (credentials missing), 400 `telegram_login_failed`,
429 `telegram_rate_limited` (Telegram flood wait), 503 `telegram_unavailable` (cannot reach Telegram).

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
| POST | `/api/v1/instruments/sync` | `{exchanges: ["NSE","NFO"]}`. Downloads Kite's public instrument list (no login) and upserts it. Expired contracts are marked inactive. Returns counts per exchange |

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
| PATCH | `/api/v1/signal-sources/{id}` | `name`, `is_enabled`, `config`. Refreshes the Telegram listener |
| DELETE | `/api/v1/signal-sources/{id}` | 409 if signals reference it (disable instead) |
| GET | `/api/v1/signal-sources/{id}/messages` | Raw inbound messages for the source, newest first |

## Signals

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/signals` | Filters: `status`, `source_id`. Newest first |
| POST | `/api/v1/signals` | Manual entry. `source_id`, `symbol_text`, `side`, optional `instrument_id`, `entry_low`, `entry_high` (low ≤ high), `stop_loss`, `targets[]`, `notes`. Does **not** trigger execution |
| GET | `/api/v1/signals/{id}` | Includes `details` (underlying, type, strike, expiry text, warnings, AI error) |
| PATCH | `/api/v1/signals/{id}` | Review: `status` (new → validated/rejected, validated → new/rejected/cancelled, rejected/expired → new), `instrument_id`, `entry_low`, `entry_high`, `stop_loss`, `targets`, `notes`. Validating requires an instrument and a stop loss |
| POST | `/api/v1/signals/parse-preview` | `{text, use_llm, force_llm}`. Runs the parser and returns what it read, without storing anything |
| POST | `/api/v1/messages/{id}/parse` | Re-runs the parser on a stored raw message and returns the new signal (or `null` if it isn't a signal) |

Example:

```bash
curl -s -X POST localhost:8000/api/v1/signals -H 'content-type: application/json' -d '{
  "source_id": "<uuid>", "symbol_text": "INFY", "side": "BUY",
  "entry_low": "1500", "entry_high": "1510", "stop_loss": "1480", "targets": ["1550", "1600"]
}'
```

## Orders, trades, positions (paper trading)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/orders` | Filters: `status`, `broker_account_id`, `trade_plan_id`. Includes `role` (entry/stop/target/exit/manual) |
| POST | `/api/v1/orders` | Manual paper order: `instrument_id`, `side`, `quantity` (lot multiple), `order_type`, `price`, `trigger_price`, optional `broker_account_id` (default Paper) |
| GET | `/api/v1/orders/{id}` | |
| POST | `/api/v1/orders/{id}/cancel` | Manual or entry orders only (bracket legs are managed by their trade) |
| GET | `/api/v1/orders/{id}/trades` | Fills for an order (array, not paginated) |
| GET | `/api/v1/trades` | Managed trades (`trade_plans`) with symbol, exchange, segment, lot size, LTP and unrealized P&L (on `open_quantity`). Each has `targets` (TP ladder `[{price, quantity, status: open\|hit\|cancelled}]`), `trailing` (`{mode: none\|step\|points\|percent, value}`), `initial_stop_loss`, `best_price`, `gross_pnl`. Filters: `status`, `broker_account_id` |
| GET | `/api/v1/trades/{id}` | |
| PATCH | `/api/v1/trades/{id}` | Any of `stop_loss`, `targets: [{price, quantity}]` (replaces the open legs; whole lots; total ≤ open quantity), `trail_mode`, `trail_value`. Moves the working stop / target orders. 422 if the stop is past the live price |
| POST | `/api/v1/trades/{id}/exit` | `{quantity?}` exit some whole lots at market (stop and targets shrink); omit for everything |
| POST | `/api/v1/trades/{id}/enter-now` | Waiting trade: cancel the entry order and buy/sell at market now (same SL/targets). 422 if already past the stop |
| POST | `/api/v1/trades/{id}/stop-to-cost` | Move the stop-loss to the entry price |
| POST | `/api/v1/trades/{id}/close` | Open: exit everything at market. Pending: cancel the entry |
| POST | `/api/v1/trading/exit-all` | Panic button: kill switch on, cancel waiting trades, exit every open trade, flatten other paper positions. Returns `{cancelled, exited, flattened}` |
| POST | `/api/v1/trading/kill-switch` | `{on: bool}` |
| POST | `/api/v1/signals/{id}/execute` | Execute a validated signal now on `{broker_account_id?}` (default Paper). 422 with the reason when a risk rule blocks it |
| GET | `/api/v1/positions` | Raw positions. Filter: `broker_account_id` |
| GET | `/api/v1/portfolio/positions` | Open positions with LTP and unrealized P&L (`include_closed=true` for all) |
| GET | `/api/v1/portfolio/summary` | Per account: capital, realized today/total, unrealized, open/pending/closed counts, win rate |
| PATCH | `/api/v1/broker-accounts/{id}` | `label`, `is_active`, `settings` (merged and validated: `capital`, `risk_per_trade_pct`, `max_position_pct`, `max_open_trades`, `daily_loss_limit_pct`, `auto_execute`, `allow_short`, `allow_min_lot`, `exit_mode` (`split` lot-wise across TP1/TP2… or `single`), `target_index` (single mode), `max_split_targets`, `trail_mode` (`step`/`points`/`percent`/`none`), `trail_value`, `entry_tolerance_pct`, `slippage_bps`, `charges_per_order`) |

## Kite & market data

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/kite/status` | `{configured, session_active, user_id}` |
| GET | `/api/v1/kite/login-url` | Zerodha login URL for your API key |
| POST | `/api/v1/kite/session` | `{request_token}`: the token or the full redirect URL. Stores today's access token encrypted |
| POST | `/api/v1/kite/logout` | Forgets the access token |
| GET | `/api/v1/market/ltp?instrument_id=…` | Last traded prices (source per Broker settings: Kite, Dhan, else manual) |
| POST | `/api/v1/market/manual-price` | `{instrument_id, price}`: practice price used when Kite has none; triggers order matching |

## Brokers (read-only towards the broker; orders stay paper)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/brokers/providers` | Registry: id, label, available, credential `fields`, `capabilities`, `static_ip_required`, costs |
| GET | `/api/v1/brokers` | Each broker with `configured`, `session_active`, masked field status, `selected` |
| GET / PATCH | `/api/v1/brokers/settings` | `primary` broker, `market_data` and `history` source (`auto`/`kite`/`dhan`/`manual`), `dhan_token_saved_at` |
| PUT | `/api/v1/brokers/{provider}/credentials` | `{values: {field: value}}` (blank ignored); stored encrypted. 403 for "coming soon" brokers |
| DELETE | `/api/v1/brokers/{provider}/credentials` | |
| POST | `/api/v1/brokers/{provider}/test` | Read-only check: profile, funds, positions, notes (static-IP rule). Never places orders |
| GET | `/api/v1/brokers/{provider}/positions` | Positions held at the broker |
| POST | `/api/v1/brokers/dhan/renew-token` | Extend the Dhan token 24 h now (also automatic every ~20 h) |
| POST | `/api/v1/brokers/dhan/sync-instruments` | Download Dhan's scrip master and attach Dhan security ids (`instruments.broker_refs.dhan`) |

## Telegram bot

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/bot` | `{configured, running, username, linked, owner_name, last_error, notify}` |
| PUT | `/api/v1/bot/token` | `{token}` from @BotFather (validated with getMe, stored encrypted) |
| DELETE | `/api/v1/bot/token` | |
| POST | `/api/v1/bot/create` | Create the bot through your Telegram login (talks to @BotFather) and link it automatically |
| POST | `/api/v1/bot/link` | `{code, url}`: open `url` (t.me/<bot>?start=<code>) and press Start; valid 30 min |
| POST | `/api/v1/bot/unlink` · `/api/v1/bot/test` | |
| PATCH | `/api/v1/bot/notify` | `{signals, trades, skipped, news, market_moves}` |

Bot buttons (callback data): `buy:<trade>` enter now, `cx:<trade>` cancel, `ex1:<trade>` exit one lot,
`exa:<trade>` exit all of it, `be:<trade>` SL → cost, `trade|approve|reject:<signal>`, `xall!` EXIT ALL
(after a confirmation message), `ksoff`. Keyboard: 📊 Status · 🛑 EXIT ALL · ⏸ Pause auto · ▶️ Resume auto;
commands `/status /exitall /pause /resume /killoff /help`. Only the linked chat is obeyed.

## News & alerts

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/news` | Headlines, newest first. Filters: `q`, `matched_only`, `source` |
| POST | `/api/v1/news/refresh` | Fetch all feeds now: `{fetched, new, alerts}` |
| GET | `/api/v1/news/status` | `{last_poll, feed_errors}` |
| GET / PUT | `/api/v1/news/settings` | `enabled`, `poll_minutes`, `feeds [{name,url,enabled}]`, `keywords`, `watches [{symbol,label,threshold_pct,window_minutes,enabled}]`, `market_alerts`, `alert_cooldown_minutes` |
| GET | `/api/v1/market/watch` | Watched instruments now: LTP and % change over each window |
| GET | `/api/v1/alerts` | Keyword-headline and market-move alerts. Filters: `kind`, `unread_only` |
| GET | `/api/v1/alerts/unread-count` · POST `/api/v1/alerts/read-all` | |

## Replay (backtest)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/replays` | Start: `date_from`, `date_to` (≤ 31 days), `source_ids` (empty = all), `messages` (`auto`/`telegram`/`stored`), `use_ai`, `settings` (risk overrides), `entry_window_minutes`, `square_off`, `same_candle` (`stop_first`/`target_first`). Runs in the background |
| GET | `/api/v1/replays` | Runs with status, progress and overall stats |
| GET | `/api/v1/replays/{id}` | Run with `report`: overall stats, capital/return/drawdown, targets hit, breakdowns `by_source`, `by_segment`, `by_side`, `by_exit_reason`, `by_day`, `by_hour`, `by_underlying`, `equity_curve`, best/worst trades |
| GET | `/api/v1/replays/{id}/trades` | Every replayed signal and its outcome (`win`, `loss`, `breakeven`, `entry_not_hit`, `no_data`, `unresolved`, `incomplete`). Filters: `outcome`, `source`, `segment` |
| GET | `/api/v1/replays/{id}/trades.csv` | Same as CSV |
| POST | `/api/v1/replays/{id}/cancel` · DELETE `/api/v1/replays/{id}` | |

## Events

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/events` | Audit log, newest first. Filters: `event_type`, `aggregate_id`, `correlation_id` |

Event types emitted today: `system.started`, `system.stopping`, `instrument.created`,
`signal_source.created|updated|deleted`, `broker_account.created`, `signal.created`,
`raw_message.received`, `raw_message.processed`, `signal.status_changed`, `instruments.synced`,
`order.created`, `order.status_changed`, `trade.executed`, `trade_plan.created|opened|closed`,
`signal.execution_skipped`, `market.manual_price_set`, `broker_account.updated`,
`integration.updated`, `settings.updated`, `trade_plan.updated|reduced`, `order.modified`,
`trading.exit_all`, `trading.kill_switch_changed`, `news.received`, `news.alert`, `market.alert`,
`replay.finished`, `bot.linked`. Events caused by one Telegram message share its
`correlation_id`.

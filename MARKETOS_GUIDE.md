# MarketOS: complete project guide

This file is the single place to understand **what MarketOS is, what has been built, how to run
and use it, what to watch out for, what to build next, and how to continue in a new chat**.
Technical detail lives in `docs/` (architecture, database, API) and `CLAUDE.md` (rules for AI
assistants working on the code).

- Repository: <https://github.com/krishnahatele/PaperTrade>
- Working branch: `claude/marketos-phase-0-setup-04ty8h`
- Pull request: <https://github.com/krishnahatele/PaperTrade/pull/1> (not merged yet)

---

## 1. What MarketOS is

A personal trading workstation for Indian markets (NSE equities, NFO index/stock options and futures):

```
Telegram channels ──► messages ──► signal parser (rules, then AI if unclear)
                                      │
                                      ▼
                        signals (validated / needs review / expired)
                                      │  auto-execute (if on) or "Execute (paper)"
                                      ▼
                   trade plan: risk checks → position size → entry order
                                      │  fills at live Kite prices
                                      ▼
                    stop-loss + target placed (one cancels the other)
                                      │
                                      ▼
                     positions, P&L, win rate, full audit log of events
```

Everything is **paper trading** (simulated money) today. Real-money trading is deliberately
**not built and is blocked everywhere** (see §7).

---

## 2. What has been built

| Commit | Phase | What it added |
|---|---|---|
| `11e2bbc` | 0. Foundation | Monorepo; FastAPI backend; PostgreSQL + Alembic migrations; core tables; event bus + audit log; structured logging; health checks; adapter interfaces (broker, market data, Telegram, LLM); Next.js frontend shell; Docker Compose; CI; docs |
| `e21fa9a` | 1. Security | Encrypted credential store (Fernet, master key outside the DB); admin password login with expiring tokens; runtime settings (kill switch, auto-execute…); Settings page |
| `76f1864` | 2. Telegram | Log in with your own Telegram account (phone code + 2FA); pick channels; every new post is saved automatically; "Fetch recent" backfill |
| `ee0fefe` | 3. Signal parsing | Rules parser for common Indian signal formats; AI fallback for unclear messages; instrument matching (nearest expiry); signal review page; parser playground; Kite instrument sync; catch-up of missed messages on startup |
| `ae4b922` | 4a. Any AI | Choose AI provider (Anthropic, Gemini, Groq, DeepSeek, OpenAI, OpenRouter, Ollama, custom); model dropdown from the provider's live list; per-provider encrypted keys |
| `de95e8a` | 4b. Paper trading | Kite daily login + live prices; trade engine with risk checks, position sizing, smart entry, stop-loss/target brackets; positions and P&L; Trades page; risk settings |
| (this commit) | 4c | NVIDIA provider preset; clear "model not found / retired" errors; reusable start script; this guide |

Quality bar on every commit: backend tests (97), ruff lint, mypy strict, migration check;
frontend lint, typecheck, unit tests and production build.

### Tech stack

| Part | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic, structlog, uv |
| Database | PostgreSQL 16 |
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS v4, TypeScript |
| Integrations | Telethon (Telegram), kiteconnect (Zerodha), Anthropic SDK, any OpenAI-compatible API via httpx |
| Tooling | Docker Compose, GitHub Actions CI, pytest, Vitest, ruff, mypy, ESLint |

### Where things are

```
apps/api/                  backend
  app/adapters/            Telegram (Telethon), Kite, LLM (Anthropic + OpenAI-compatible), broker interfaces
  app/parsing/             rules parser + AI parser
  app/services/            telegram, signal_pipeline, instruments, llm, kite, market_data, trading, risk, secrets, auth
  app/api/v1/routes/       HTTP endpoints
  app/models/              database tables
  alembic/versions/        migrations 0001–0004
  tests/                   97 tests (fakes for Telegram, AI, Kite)
apps/web/                  frontend (src/app = pages, src/components, src/lib)
docs/                      architecture.md, database.md, api.md
scripts/codespace-start.sh one-command start inside GitHub Codespaces
CLAUDE.md                  rules for AI coding assistants on this repo
```

---

## 3. Running MarketOS

### Option A: GitHub Codespaces (what you use now; nothing installed on your Mac)

1. github.com/krishnahatele/PaperTrade → branch `claude/marketos-phase-0-setup-04ty8h` →
   **Code → Codespaces** → open your existing codespace (or create one on this branch).
2. In the codespace terminal:
   ```bash
   git pull
   bash scripts/codespace-start.sh
   ```
3. When it prints **Open: https://…-3000.app.github.dev**, open that link.
   If the page says "Can't reach the MarketOS API": **Ports** tab → right-click **8000** →
   **Port Visibility → Public**, then reload.

Notes:
- The codespace **sleeps after ~30 minutes idle**. While asleep nothing listens to Telegram and no
  trades are managed. On restart, MarketOS catches up on the last 50 messages per channel, but
  stale messages become "expired", not trades.
- Free Codespaces hours are limited per month. Stop it from GitHub → Code → Codespaces → ⋯ → Stop.
- Your data (database, encrypted credentials) stays in the codespace until you **delete** it.

### Option B: any computer with Docker (needs admin rights to install Docker)

```bash
git clone -b claude/marketos-phase-0-setup-04ty8h https://github.com/krishnahatele/PaperTrade.git
cd PaperTrade
cp .env.example .env
docker compose up -d --build
```
Open http://localhost:3000 (API docs: http://localhost:8000/docs).

### Option C: always-on cloud server (recommended for real use, not yet set up)

A small Linux VM (2 vCPU / 4 GB) running Option B. Access it through an SSH tunnel so nothing is
public: `ssh -L 3000:localhost:3000 -L 8000:localhost:8000 user@server`, then open
http://localhost:3000 on your Mac. See §9 (next step A).

### Your Mac
Everything we installed while trying to run locally (uv, micromamba, Node download) was removed.
Your Mac only needs a browser.

---

## 4. First-time setup inside the app

Do these once, in this order:

1. **Create admin password** (first screen). At least 10 characters. It protects everything.
2. **Settings → Telegram**
   - API ID + API hash from <https://my.telegram.org> → API development tools.
   - Phone number in international format, e.g. `+919876543210`.
   - Save, then **Log in to Telegram**, enter the code Telegram sends (and your 2FA password if set).
3. **Sources → Add Telegram channel**: add each signal channel. **Fetch recent** pulls old posts.
4. **Settings → Zerodha Kite** (live prices)
   - Create an app at <https://developers.kite.trade> (paid Zerodha subscription).
     Set its **Redirect URL** to `https://127.0.0.1/`.
   - Save API key + secret in Settings.
   - **Open Kite login** → sign in → you land on a page that doesn't load (expected) → copy the
     whole address from the browser bar → paste → **Connect**.
5. **Instruments → Sync from Kite** (downloads NSE + F&O contracts, about a minute). Repeat every
   few days so new weekly option expiries are known.
6. **Settings → AI signal parsing**
   - "When to use AI": **Rules first, AI only for unclear messages** (cheapest useful setting),
     or **Rules only** (free).
   - Provider: e.g. **NVIDIA (build.nvidia.com)**. Paste your `nvapi-…` key, **Save**, reload,
     then pick a working **…-instruct** model from the Model dropdown, **Save**, **Test active model**.
     A "retired" or "not found" error means pick a different model.
7. **Settings → Paper account & risk**: capital, risk per trade %, max open trades, daily loss
   limit, slippage, charges. Defaults: ₹1,00,000, 1%, 5 trades, 3%.
8. When you're happy with what the Signals page shows: **Settings → Trading controls →
   Auto-execute** on.

### Daily routine
1. Start the codespace (§3A) if it was stopped.
2. **Kite login** again (Kite sessions end every morning around 6 AM).
3. Check **Dashboard** (all four integrations "ready").
4. During the day: **Signals** (needs review?), **Trades** (open/closed, P&L), **Positions**.

---

## 5. How it works (what you'll see)

### Signal statuses
| Status | Meaning |
|---|---|
| **validated** | Complete (side, instrument found, entry, stop loss), sane levels, confidence ≥ minimum. Ready to trade |
| **needs review** (`new`) | Something missing or doubtful (no SL, instrument not found, levels inconsistent). Fix it or Approve/Reject on the signal page |
| **executed** | A trade was created from it |
| **expired** | Older than the expiry window (default 30 min), e.g. caught up after downtime. Never traded automatically |
| **rejected / cancelled** | Set by you |

Messages that aren't signals (greetings, "target hit", ads) are marked **ignored** on the
source's message page and cost nothing.

### How a trade runs
1. **Risk checks**: kill switch off · account active · signal validated and fresh · not already
   traded · below max open trades · daily loss limit not hit · shorting allowed (off by default).
2. **Size**: `capital × risk% ÷ |entry − stop|`, rounded down to whole lots, capped at max
   position %. If that's under one lot, one lot is used only if its risk is ≤ 2× the budget.
3. **Entry**, depending on the live price:
   - inside the signal's range → buy at market
   - below a "BUY ABOVE" level → wait for the breakout (stop-entry)
   - already past the range → limit order at the signal price (wait for pullback)
   - not filled within the expiry window → cancelled
4. **After entry**: a stop-loss order and a target order (target #1 by default) are placed. When
   one fills, the other is cancelled. P&L = price move × quantity − charges.
5. **Exit / Cancel** buttons on the Trades page close a trade at market or cancel a waiting entry.

Paper fills use the live Kite price plus simulated slippage (default 0.05%), rounded to the tick
size. Without Kite you can practise with **Instruments → set price**.

### AI costs
AI is only called for messages the rules can't read confidently, that look like trade calls, and
that aren't stale. Clear signals and chatter never reach the AI. Rough guide (estimates): Claude
Haiku is around a fraction of a rupee per AI-parsed message; NVIDIA, Gemini and Groq have free
tiers or credits; "Rules only" is free.

---

## 6. Troubleshooting (things we already ran into)

| Symptom | Fix |
|---|---|
| App says "Can't reach the MarketOS API" (Codespaces) | Ports tab → 8000 → Port Visibility → **Public**; or re-run `bash scripts/codespace-start.sh` |
| `10.0.0.x:3000` link doesn't open | Ignore it; use the `…-3000.app.github.dev` link |
| AI test: `404` / "not found" | Wrong model name (e.g. the *key's* name was typed as the model). Pick from the dropdown |
| AI test: `410` / "retired" | Provider retired that model. Pick another |
| AI test: `401` / `403` | Wrong or missing key. Re-save the key (it starts with `nvapi-` for NVIDIA) |
| Signals stay "needs review: instrument not found" | Run **Instruments → Sync from Kite**, or set the instrument on the signal page |
| Market data "error / session expired" | Do the daily **Kite login** again |
| Telegram "cannot reach Telegram servers" | Network issue on the host; Codespaces normally works |
| No trades happen | Auto-execute off (global or account), kill switch on, signal not validated, or a risk limit. **Event log** → `signal.execution_skipped` shows the reason |
| Lost the master key | Credentials can't be decrypted; re-enter Telegram/Kite/AI keys. Back up `apps/api/.secrets/master.key` (Codespaces/local) or the `apisecrets` Docker volume |

Logs: backend `~/api.log` in Codespaces (`tail -f ~/api.log`), or `docker compose logs -f api`.

---

## 7. Safety model (do not weaken)

- Paper trading is the only execution mode. The trade engine refuses any non-paper account; no
  live broker is wired; creating a live account returns 403; the "live armed" switch can't be
  turned on unless the server flag `MARKETOS_LIVE_TRADING_ENABLED` is set, and the server refuses
  to start with that flag in this build.
- Kill switch blocks every new order immediately.
- All credentials are encrypted at rest; the API never returns them (only "set" + last 4 chars).
- Every action is recorded in the **Event log** (audit trail).
- The app has a single admin password; don't expose it on the public internet without HTTPS (§9).

---

## 8. Known limitations

- Codespaces sleeps → no monitoring while asleep (needs Option C).
- Telegram **edited/deleted** messages and follow-ups ("SL hit", "book profit", "trail SL to …")
  are not acted on; only new calls are.
- One target per trade (choose which); no partial exits or trailing stop yet.
- No automatic intraday square-off at 3:20 PM; no margin modelling; charges are a flat per-order estimate.
- Prices are polled every ~2 s (not tick-by-tick); paper fills can differ from real fills.
- Rules parser was tuned on common formats, not on your channels yet. Send misread messages to improve it.
- The in-process event bus means run **one** API instance.

---

## 9. Suggested next steps (in order)

**A. Always-on server.** Small cloud VM + Docker Compose + SSH tunnel (or HTTPS with a domain).
Add a daily database backup and auto-restart. *Without this, nothing runs while you sleep.*

**B. Tune on your real channels.** Collect misread messages from Sources → message pages; add
rules per channel format; per-channel trust settings (min confidence, auto-execute on/off per source).

**C. Telegram follow-ups.** Understand replies/edits like "SL hit", "exit now", "trail SL to 130",
"book 50%" and apply them to the linked trade.

**D. Better trade management.** Multiple targets with partial exits, trailing stop, breakeven
after T1, auto square-off for intraday, time-based exits.

**E. Analytics.** Per-channel performance (win rate, average R, max drawdown), equity curve,
CSV export: decide which channels deserve real money.

**F. Alerts.** Telegram bot / push notification on new signal, entry, exit, errors, Kite expiry.

**G. Phase 5: live trading through Kite** (only after weeks of good paper results). Layered
opt-in: server flag + live account + "live armed" switch + per-order value cap + daily loss cap +
kill switch + order confirmation mode first; Kite order placement with idempotent `client_order_id`,
order-status reconciliation, and a dry-run period.

**H. Hardening.** HTTPS, rate limits, 2FA for the admin login, transactional outbox for events,
Redis-backed event bus if more than one API instance is needed.

---

## 10. Continuing in a new chat

### Starting a new Claude Code session on this repo
1. Go to <https://claude.ai/code> and start a new session.
2. Select the repository **krishnahatele/PaperTrade**.
3. Tell it which branch to work on. Either:
   - continue on `claude/marketos-phase-0-setup-04ty8h` (PR #1 stays open and grows), or
   - **merge PR #1 into `main` first** (recommended once you're happy), then start new work from `main`.
4. Paste a starter prompt like this:

```
You are continuing development of MarketOS in this repo (krishnahatele/PaperTrade).
First read MARKETOS_GUIDE.md, CLAUDE.md, docs/architecture.md, docs/database.md and docs/api.md.
Work on branch <branch-name>. Phases 0–4 are done (paper trading only).
Next task: <e.g. "Next step C: Telegram follow-up messages (SL hit / exit / trail SL)">.
Keep the safety model in MARKETOS_GUIDE.md §7 and CLAUDE.md. Do not enable live trading.
Run backend + frontend tests, lint and type checks; update docs; commit and push.
```

The new session reads `CLAUDE.md` automatically. The guide + docs give it everything else.

### Things a new session can't see
- Your **credentials** (Telegram, Kite, AI keys) and **database** live only in your codespace/server.
  They are never in GitHub. A new chat works on the code; you keep running the app where it is.
- After a new session pushes changes: in your codespace run `git pull` then
  `bash scripts/codespace-start.sh` (migrations run automatically).

### Working on the code yourself
```bash
cd apps/api && uv run pytest && uv run ruff check . && uv run mypy app tests   # backend checks
cd apps/web && npm run lint && npm run typecheck && npm test && npm run build    # frontend checks
cd apps/api && uv run alembic revision --autogenerate -m "describe change"      # new migration (then review it; see docs/database.md)
```

---

## 11. Reference

| Thing | Where |
|---|---|
| All API endpoints | `docs/api.md` or `<api-url>/docs` (interactive) |
| Database tables & ERD | `docs/database.md` |
| Architecture, parsing, trading engine, safety | `docs/architecture.md` |
| Environment variables | `.env.example` |
| Rules for AI assistants | `CLAUDE.md` |
| Event types (audit log) | `docs/api.md` → Events |

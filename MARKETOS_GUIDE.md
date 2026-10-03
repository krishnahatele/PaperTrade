# MarketOS: complete project guide

This file is the single place to understand **what MarketOS is, what has been built, how to run
and use it, what to watch out for, what to build next, and how to continue in a new chat**.
Technical detail lives in `docs/` (architecture, database, API) and `CLAUDE.md` (rules for AI
assistants working on the code).

- Repository: <https://github.com/krishnahatele/PaperTrade>
- Phases 0–4: merged into `main` (<https://github.com/krishnahatele/PaperTrade/pull/1>)
- Phase 5: branch `claude/marketos-phase-0-setup-04ty8h` (open a PR to merge it into `main`)

---

## 1. What MarketOS is

A personal trading workstation for Indian markets: NSE/BSE equities, NFO/BFO index & stock
futures and options, and MCX commodities (crude oil, natural gas, gold, silver…):

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
          stop-loss + TP1/TP2… exits (lot-wise), trailing stop, edit any time
                                      │
                                      ▼
                     positions, P&L, win rate, full audit log of events

 Telegram bot ◄── trade cards with ⚡Buy now / Exit / SL→cost, 🛑 EXIT ALL, alerts
 News & moves ──► keyword headlines + sharp moves (crude, NIFTY, VIX…) → app + bot
 Replay       ──► past days of a group's messages on historical prices → accuracy report
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
| `29c8821` | 4c | NVIDIA provider preset; clear "model not found / retired" errors; reusable start script; this guide |
| Phase 5 | 5a. Trade management | TP1/TP2 lot-wise exits, step / points / % trailing stop, edit SL & targets of a running trade, exit some lots, Buy now for waiting trades, EXIT ALL + kill switch |
| Phase 5 | 5b. Commodities | BSE/BFO/MCX sync; "crude", "natural gas", "gold mini"… understood; plain commodity calls use the nearest MCX future |
| Phase 5 | 5c. Brokers | Broker dropdown (Paper, Zerodha Kite, Dhan; Upstox/Angel/Fyers listed as coming soon); Dhan connection test, positions, funds, live prices, candles, token auto-renew |
| Phase 5 | 5d. Telegram bot | Your own private bot: trade cards with buttons, EXIT ALL (asks twice), pinned status, pause/resume auto, alerts; can be created automatically |
| Phase 5 | 5e. News | RSS news with keyword alerts; market-move alerts on crude/NIFTY/BANKNIFTY/VIX/gold |
| Phase 5 | 5f. Replay | Backtest past Telegram signals day-wise on 1-minute prices; report per group, per segment, exit reasons, equity curve, CSV |

Quality bar on every commit: backend tests (127), ruff lint, mypy strict, migration check;
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

1. github.com/krishnahatele/PaperTrade → **Code → Codespaces** → open your existing codespace
   (use **one** codespace; each has its own database and keys). To get Phase 5 before it is
   merged: in the codespace terminal `git fetch && git checkout claude/marketos-phase-0-setup-04ty8h`.
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
git clone https://github.com/krishnahatele/PaperTrade.git   # add -b <branch> for unmerged work
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
5. **Instruments → Sync from Kite** (downloads NSE, BSE, F&O and MCX contracts, a minute or two;
   no Kite login needed). Repeat every few days so new weekly option expiries are known.
6. **Settings → AI signal parsing**
   - "When to use AI": **Rules first, AI only for unclear messages** (cheapest useful setting),
     or **Rules only** (free).
   - Provider: e.g. **NVIDIA (build.nvidia.com)**. Paste your `nvapi-…` key, **Save**, reload,
     then pick a working **…-instruct** model from the Model dropdown, **Save**, **Test active model**.
     A "retired" or "not found" error means pick a different model.
7. **Settings → Paper account & risk**: capital, risk per trade %, max open trades, daily loss
   limit, slippage, charges. Defaults: ₹1,00,000, 1%, 5 trades, 3%. **How to exit**: split lots
   across targets (default) or all at one target. **Trailing**: step (default), points, % or none.
8. **Settings → Broker** (optional): pick **Dhan** and paste Client ID + access token
   (web.dhan.co → My Profile → DhanHQ Trading APIs), **Test connection** (read-only), then
   **Sync Dhan instrument IDs**. Choose where live prices and replay candles come from.
9. **Settings → Telegram bot**: **Create my bot automatically** (uses your Telegram login), or
   make one with @BotFather and paste its token, then **Link my Telegram** and press Start.
   Choose which notifications you want.
10. **Settings → News & market alerts**: keywords (crude, RBI, Fed…), feeds, and watched
    instruments with their % thresholds.
11. When you're happy with what the Signals page shows: **Settings → Trading controls →
    Auto-execute** on.

### Daily routine
1. Start the codespace (§3A) if it was stopped.
2. **Kite login** again (Kite sessions end every morning around 6 AM). Dhan's token renews itself
   while MarketOS is running; if the app was off for more than a day, paste a fresh Dhan token.
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
4. **After entry**: one stop-loss for the quantity you hold, and one exit per target. Example:
   2 lots of 20 with TGT 610/640 → 20 exit at T1 (610), 20 at T2 (640). 3 lots over 2 targets →
   2 lots at T1, 1 at T2. With **step trailing**, when T1 fills the stop moves to your entry
   price (the rest can't lose); when T2 fills it moves to T1. **Points/% trailing** follows the
   best price by that distance and only ever tightens.
5. **Change it while it runs** (Trades → click the symbol): new stop-loss, new targets (price +
   lots), trailing on/off, **Exit lots**, **Exit all**, **SL → cost**. Waiting trades have
   **⚡ Buy now @ market** (enter now instead of waiting for the breakout; same stop) and Cancel.
6. **🛑 EXIT ALL** (top bar, or the bot): cancels waiting trades, exits everything at market and
   turns the **kill switch** on, so nothing new starts until you turn it off (click the red pill).

Paper fills use the live Kite price plus simulated slippage (default 0.05%), rounded to the tick
size. Without Kite you can practise with **Instruments → set price**.

### Telegram bot
- Each trade gets one message that updates itself: waiting (⚡ Buy now / ✖ Cancel), open (Exit 1
  lot / Exit all / SL → cost), closed (result).
- A keyboard stays at the bottom: 📊 Status · 🛑 EXIT ALL · ⏸ Pause auto · ▶️ Resume auto. A status
  message is pinned at the top and refreshed every minute.
- With auto-execute paused, new signals arrive with **▶ Trade it / ✖ Ignore**; signals that need
  review come with **✅ Approve & trade**.
- Only your linked chat is obeyed. Anyone else who finds the bot gets "This is a private bot".

### News & market alerts
- Headlines from ET, Moneycontrol, Mint, Business Standard and Google News searches every 5 min.
  Headlines with your keywords become alerts (🔔 in the top bar, News page, and the bot).
- Watched instruments are checked every minute: e.g. crude oil future ±1.5% within 30 min, NIFTY
  ±0.8% within 15 min, India VIX ±8% → alert with the move and prices. 30 min cooldown each.

### Replay (backtest a group)
- **Replay → choose days** (yesterday, last 7 days, any range up to 31 days) and groups.
- MarketOS reads that period's messages (from Telegram, or the ones it stored), reads each call,
  finds the exact contract *as it was that day*, gets 1-minute prices from Kite or Dhan, and
  trades it on paper with your rules from the minute the message arrived: entry rules, SL, TP1/TP2,
  trailing, square-off at 15:20 (23:25 for MCX). If one candle touches both SL and target it
  assumes the SL (safer).
- Report: trades taken vs signals, wins/losses, win rate, **accuracy** (TP1 reached before SL), net
  P&L, return %, max drawdown, profit factor, average R, losing streak, targets hit (T1/T2/T3 %),
  equity curve, and tables by group, by segment (Equity / F&O / Commodity), by exit reason, side,
  day, hour and underlying, plus every trade with its message. CSV download.
- Separate from live paper trading: it never creates signals, orders or positions.
- Price data: Kite needs its historical-data plan and has **no data for expired contracts** (last
  week's weekly options). Dhan's Data API (₹499/month) also serves expired index options. Those
  messages show as "no data" otherwise.

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
| Broker test: "Dhan rejected the access token" | Token expired (24 h) or mistyped. Generate a new one on web.dhan.co and save it |
| Dhan prices missing | Data API plan needed; and run **Settings → Broker → Sync Dhan instrument IDs** after an instrument sync |
| Replay: many "no data" | Contract expired (Kite has no data for expired options) or no history source. Use Dhan as replay source, or replay recent days |
| Replay: "unresolved" | Contract not in the instrument list for that day: sync instruments; for old weeks the contract may never have been synced |
| Bot doesn't answer | Settings → Telegram bot: is it linked? "Send test message". Only the linked chat is obeyed |
| News: feed errors | Some sites block automated reading from some networks; disable that feed or add another RSS link |
| Lost the master key | Credentials can't be decrypted; re-enter Telegram/Kite/AI keys. Back up `apps/api/.secrets/master.key` (Codespaces/local) or the `apisecrets` Docker volume |

Logs: backend `~/api.log` in Codespaces (`tail -f ~/api.log`), or `docker compose logs -f api`.

---

## 7. Safety model (do not weaken)

- Paper trading is the only execution mode. The trade engine refuses any non-paper account; the
  Dhan and Kite adapters are used **read-only** (test connection, positions, funds, prices,
  candles); creating a live account returns 403; the "live armed" switch can't be turned on
  unless the server flag `MARKETOS_LIVE_TRADING_ENABLED` is set, and the server refuses to start
  with that flag in this build.
- Real orders through any broker API also need a **static IP registered with the broker** (SEBI
  rule from April 2026). Codespaces has no fixed IP.
- Kill switch blocks every new order immediately; EXIT ALL also exits everything.
- The Telegram bot obeys only your linked chat.
- All credentials are encrypted at rest; the API never returns them (only "set" + last 4 chars).
- Every action is recorded in the **Event log** (audit trail).
- The app has a single admin password; don't expose it on the public internet without HTTPS (§9).

---

## 8. Known limitations

- Codespaces sleeps → no monitoring while asleep (needs Option C).
- Telegram **edited/deleted** messages and follow-ups ("SL hit", "book profit", "trail SL to …")
  are not acted on; only new calls are.
- Live (paper) trades are not auto-squared-off at 3:20 PM (replay does square off); no margin
  modelling; charges are a flat per-order estimate.
- Changing SL/targets in the portal changes the paper trade only. Mirroring to Kite/Dhan orders is
  the live-trading phase (needs a static-IP server).
- Bot trade cards are remembered in memory: after a restart, updates arrive as new messages.
- Replay ignores max-open-trades/daily-loss limits and uses prices, not the order book.
- Dhan's API fields follow its official SDK but were not tried against a live Dhan account here;
  run **Test connection** first.
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

**D. Done in Phase 5:** TP1/TP2 partial exits, trailing stop, SL to cost, EXIT ALL, Telegram bot,
news & market alerts, replay with per-group accuracy, Dhan/Kite connections, MCX commodities.
Next small items: intraday auto square-off for live paper trades, per-group auto-execute/trust
based on replay accuracy, follow-up messages (step C).

**E. Use Replay to pick groups.** Replay each group for 1–4 weeks; keep only groups with good
accuracy and profit factor; set per-group trust (planned).

**F. More brokers.** Upstox / Angel One / Fyers: one adapter file each (see `app/adapters/broker/`).

**G. Phase 6: live trading through Dhan or Kite** (only after weeks of good paper + replay
results). Needs a small always-on server with a **static IP** registered at the broker. Layered
opt-in: server flag + live account + "live armed" switch + per-order quantity cap + daily loss cap
+ kill switch (also Dhan's own) + a confirmation mode first; Dhan Super Orders keep SL/target/
trailing at the broker even if MarketOS goes down; order-status reconciliation; 1 lot to start.

**H. Hardening.** HTTPS, rate limits, 2FA for the admin login, transactional outbox for events,
Redis-backed event bus if more than one API instance is needed.

---

## 10. Continuing in a new chat

### Starting a new Claude Code session on this repo
1. Go to <https://claude.ai/code> and start a new session.
2. Select the repository **krishnahatele/PaperTrade**.
3. Tell it which branch to work on: merge the Phase 5 PR into `main` first (recommended), then
   start new work from `main` on a new branch.
4. Paste a starter prompt like this:

```
You are continuing development of MarketOS in this repo (krishnahatele/PaperTrade).
First read MARKETOS_GUIDE.md, CLAUDE.md, docs/architecture.md, docs/database.md and docs/api.md.
Work on branch <branch-name>. Phases 0–5 are done (paper trading only; brokers read-only).
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

# CLAUDE.md: working on MarketOS

MarketOS is a signal-driven trading workstation (Telegram, then signals, then paper or Kite execution).
Monorepo: `apps/api` (FastAPI + SQLAlchemy 2 async + Alembic, managed with `uv`) and
`apps/web` (Next.js 16 App Router + Tailwind v4). Read `MARKETOS_GUIDE.md` (status, how it is used,
roadmap) and `docs/architecture.md` first. Phases 0–4 are done; execution is paper-only.

## Non-negotiables

* **Safety first.** Paper trading is the default. Never make live order placement reachable
  without the explicit, layered opt-in described in `docs/architecture.md` (safety model).
  Never weaken those guards to make a test pass.
* Never commit secrets. Credentials enter via env/`SecretStr` or the encrypted secret store,
  never plain DB columns or logs.
* Prices and money are `Decimal`, never `float`. Timestamps are timezone-aware UTC.
* All external systems sit behind an adapter interface in `app/adapters/*`.
  Routes call services, services call adapters.
* Every state change publishes an `Event` on the bus.

## Commands

```bash
make up                 # docker compose: db + api + web
make check              # lint + typecheck + tests (api and web)
cd apps/api && uv run pytest          # needs Postgres (marketos_test DB), else DB tests skip
cd apps/api && uv run alembic revision --autogenerate -m "..."  # then clean up (docs/database.md)
cd apps/api && uv run alembic check   # models and migrations must agree
cd apps/web && npm run lint && npm run typecheck && npm test && npm run build
```

## Conventions

* Backend: ruff (`select` in pyproject) + mypy `--strict`. New models: one file in
  `app/models/`, export in `app/models/__init__.py`, StrEnums in `models/enums.py`, stored via
  `str_enum()`. Schemas in `app/schemas/`. Routes in `app/api/v1/routes/` and registered in `router.py`.
* Tests: `tests/`. Mark DB tests with `pytest.mark.db`. Use the `db_client` fixture (it truncates after each test).
* Frontend: Next.js 16 differs from older versions. Check `apps/web/node_modules/next/dist/docs/`
  before using unfamiliar APIs. Nav lives in `src/lib/nav.ts`, API types in `src/lib/types.ts`.
* Docs: update `docs/api.md` and `docs/database.md` with any API or schema change.

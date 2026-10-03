# MarketOS

Signal-driven trading workstation for Indian markets. Telegram signals are parsed into
structured trade ideas and executed in paper mode (and, once explicitly enabled, through Zerodha Kite).

| | |
|---|---|
| Backend | FastAPI · SQLAlchemy 2 (async) · Alembic · PostgreSQL 16 · structlog |
| Frontend | Next.js 16 (App Router) · React 19 · Tailwind CSS v4 |
| Tooling | uv · ruff · mypy (strict) · pytest · ESLint · tsc · Vitest · Docker Compose |

## Quick start (GitHub Codespaces)

```bash
bash scripts/codespace-start.sh
```

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up -d --build
```

* Web: http://localhost:3000
* API: http://localhost:8000 (docs at `/docs`)
* Postgres: `localhost:5432` (marketos / marketos)

The API container applies migrations on start.

## Local development (without Docker for the apps)

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20.9+, PostgreSQL 16 (or just `docker compose up -d db`).

```bash
cp .env.example .env
docker compose up -d db          # or use your own Postgres
make install                     # uv sync + npm ci
make migrate                     # alembic upgrade head
make api                         # http://localhost:8000
make web                         # http://localhost:3000 (second terminal)
make check                       # lint + typecheck + tests
```

## Documentation

* **[Complete guide: what's built, how to run & use it, next steps](MARKETOS_GUIDE.md)**

* [Architecture](docs/architecture.md)
* [Database & ERD](docs/database.md)
* [API reference](docs/api.md)
* [Contributor / agent guide](CLAUDE.md)

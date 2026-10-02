# MarketOS API

FastAPI backend. See the repository root `README.md` and `docs/` for details.

```bash
uv sync                      # install
uv run alembic upgrade head  # migrate
uv run uvicorn app.main:app --reload
uv run pytest                # tests
uv run ruff check . && uv run ruff format --check . && uv run mypy app tests
```

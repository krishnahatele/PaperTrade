"""Replay report: numbers *and* breakdowns (per group, segment, exit, day, hour),
an equity curve and the best / worst trades. Built from ``ReplayTrade`` rows."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from app.models import ReplayTrade
from app.models.enums import ReplayOutcome

IST = ZoneInfo("Asia/Kolkata")
ZERO = Decimal("0")
TRADED = (ReplayOutcome.WIN, ReplayOutcome.LOSS, ReplayOutcome.BREAKEVEN)


def _q(v: Decimal, places: str = "0.01") -> str:
    return str(v.quantize(Decimal(places)))


def _pct(n: int, d: int) -> str | None:
    return _q(Decimal(n) / Decimal(d) * 100, "0.1") if d else None


def stats(rows: list[ReplayTrade]) -> dict[str, Any]:
    """Core stats for a group of replayed messages."""
    traded = [r for r in rows if r.outcome in TRADED]
    wins = [r for r in traded if r.outcome is ReplayOutcome.WIN]
    losses = [r for r in traded if r.outcome is ReplayOutcome.LOSS]
    net = sum((r.net_pnl or ZERO for r in traded), ZERO)
    gross_win = sum((r.net_pnl or ZERO for r in wins), ZERO)
    gross_loss = -sum((r.net_pnl or ZERO for r in losses), ZERO)
    t1 = sum(1 for r in traded if r.targets_hit >= 1)
    rs = [r.r_multiple for r in traded if r.r_multiple is not None]
    return {
        "signals": len(rows),
        "traded": len(traded),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(traded) - len(wins) - len(losses),
        "entry_not_hit": sum(1 for r in rows if r.outcome is ReplayOutcome.ENTRY_NOT_HIT),
        "no_data": sum(1 for r in rows if r.outcome is ReplayOutcome.NO_DATA),
        "unresolved": sum(1 for r in rows if r.outcome is ReplayOutcome.UNRESOLVED),
        "incomplete": sum(1 for r in rows if r.outcome is ReplayOutcome.INCOMPLETE),
        "win_rate": _pct(len(wins), len(traded)),
        # "accuracy" of the call itself: TP1 reached before the stop
        "accuracy_t1": _pct(t1, len(traded)),
        "net_pnl": _q(net),
        "avg_win": _q(gross_win / len(wins)) if wins else None,
        "avg_loss": _q(-gross_loss / len(losses)) if losses else None,
        "profit_factor": _q(gross_win / gross_loss) if gross_loss > 0 else None,
        "expectancy": _q(net / len(traded)) if traded else None,
        "avg_r": _q(sum(rs, ZERO) / len(rs)) if rs else None,
    }


def _group(rows: Iterable[ReplayTrade], key: Any) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[ReplayTrade]] = defaultdict(list)
    for r in rows:
        groups[str(key(r) or "unknown")].append(r)
    return {k: stats(v) for k, v in sorted(groups.items())}


def build_report(
    rows: list[ReplayTrade],
    *,
    messages_scanned: int,
    capital: Decimal,
    sources_used: dict[str, int],
) -> dict[str, Any]:
    traded = sorted(
        (r for r in rows if r.outcome in TRADED),
        key=lambda r: r.exit_at or r.message_at,
    )
    # Equity curve and drawdown, in exit order
    equity = capital
    peak = capital
    max_dd = ZERO
    curve = [{"t": None, "equity": _q(capital)}]
    streak = worst_streak = 0
    for r in traded:
        equity += r.net_pnl or ZERO
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        curve.append(
            {
                "t": (r.exit_at or r.message_at).isoformat(),
                "equity": _q(equity),
                "symbol": r.tradingsymbol,
            }
        )
        streak = streak + 1 if r.outcome is ReplayOutcome.LOSS else 0
        worst_streak = max(worst_streak, streak)

    targets_hit: dict[str, int] = defaultdict(int)
    holding: list[float] = []
    for r in traded:
        for i in range(1, r.targets_hit + 1):
            targets_hit[f"T{i}"] += 1
        if r.entry_at and r.exit_at:
            holding.append((r.exit_at - r.entry_at).total_seconds() / 60)

    def hour(r: ReplayTrade) -> str:
        return r.message_at.astimezone(IST).strftime("%H:00")

    def day(r: ReplayTrade) -> str:
        return r.message_at.astimezone(IST).date().isoformat()

    def brief(r: ReplayTrade) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "symbol": r.tradingsymbol,
            "source": r.source_name,
            "net_pnl": _q(r.net_pnl or ZERO),
            "exit_reason": r.exit_reason.value if r.exit_reason else None,
            "message_at": r.message_at.isoformat(),
        }

    best = sorted(traded, key=lambda r: r.net_pnl or ZERO, reverse=True)
    overall = stats(rows)
    return {
        "generated_at": datetime.now(IST).isoformat(),
        "messages_scanned": messages_scanned,
        "overall": overall,
        "capital_start": _q(capital),
        "capital_end": _q(equity),
        "return_pct": _q((equity - capital) / capital * 100) if capital else None,
        "max_drawdown": _q(max_dd),
        "max_drawdown_pct": _q(max_dd / peak * 100) if peak else None,
        "max_consecutive_losses": worst_streak,
        "avg_holding_minutes": round(sum(holding) / len(holding), 1) if holding else None,
        "targets_hit": {
            k: {"count": v, "pct": _pct(v, len(traded))} for k, v in sorted(targets_hit.items())
        },
        "by_source": _group(rows, lambda r: r.source_name),
        "by_segment": _group(rows, lambda r: r.segment),
        "by_side": _group(rows, lambda r: r.side.value if r.side else None),
        "by_exit_reason": {
            k: v
            for k, v in _group(
                traded, lambda r: r.exit_reason.value if r.exit_reason else None
            ).items()
        },
        "by_day": _group(rows, day),
        "by_hour": _group(traded, hour),
        "by_underlying": _group(
            rows, lambda r: (r.signal or {}).get("underlying") or r.tradingsymbol
        ),
        "equity_curve": curve,
        "best_trades": [brief(r) for r in best[:5]],
        "worst_trades": [brief(r) for r in reversed(best[-5:])] if best else [],
        "data_sources": sources_used,
    }

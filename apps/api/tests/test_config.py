import pytest
from pydantic import ValidationError

from app.core.config import Settings, TradingMode


def test_defaults_are_safe() -> None:
    s = Settings()
    assert s.trading_mode is TradingMode.PAPER
    assert s.live_trading_enabled is False


@pytest.mark.parametrize(
    "kwargs",
    [{"trading_mode": "live"}, {"live_trading_enabled": True}],
)
def test_live_trading_rejected_in_phase_0(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="Live trading is not available"):
        Settings(**kwargs)  # type: ignore[arg-type]


def test_secrets_are_masked() -> None:
    s = Settings(kite_api_secret="super-secret")
    assert "super-secret" not in repr(s)

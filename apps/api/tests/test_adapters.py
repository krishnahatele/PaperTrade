import pytest

from app.adapters.base import AdapterState
from app.adapters.broker import BrokerOrderRequest
from app.adapters.llm import LLMMessage, LLMRequest
from app.adapters.market_data import InstrumentKey
from app.core.config import Settings
from app.core.errors import FeatureDisabledError
from app.models.enums import Exchange, OrderType, ProductType, Side
from app.services.adapters import AdapterRegistry


@pytest.fixture
def registry() -> AdapterRegistry:
    return AdapterRegistry.from_settings(Settings())


async def test_all_adapters_report_disabled(registry: AdapterRegistry) -> None:
    health = await registry.health()
    assert set(health) == {"broker", "market_data", "telegram", "llm"}
    assert all(h.state is AdapterState.DISABLED for h in health.values())


async def test_broker_refuses_orders(registry: AdapterRegistry) -> None:
    req = BrokerOrderRequest(
        client_order_id="c1",
        exchange=Exchange.NSE,
        tradingsymbol="INFY",
        side=Side.BUY,
        quantity=1,
        order_type=OrderType.MARKET,
        product=ProductType.CNC,
    )
    with pytest.raises(FeatureDisabledError):
        await registry.broker.place_order(req)
    with pytest.raises(FeatureDisabledError):
        await registry.broker.cancel_order("x")
    assert await registry.broker.get_positions() == []


async def test_other_adapters_refuse(registry: AdapterRegistry) -> None:
    key = InstrumentKey(exchange=Exchange.NSE, tradingsymbol="INFY")

    async def on_tick(_: object) -> None: ...

    with pytest.raises(FeatureDisabledError):
        await registry.market_data.get_quotes([key])
    with pytest.raises(FeatureDisabledError):
        await registry.market_data.subscribe([key], on_tick)
    with pytest.raises(FeatureDisabledError):
        await registry.telegram.fetch_history("chan")
    with pytest.raises(FeatureDisabledError):
        await registry.llm.complete(LLMRequest(messages=[LLMMessage(role="user", content="hi")]))

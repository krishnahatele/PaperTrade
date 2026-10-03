from __future__ import annotations

from app.adapters.base import AdapterHealth, AdapterState
from app.adapters.broker.base import (
    BrokerAdapter,
    BrokerOrderAck,
    BrokerOrderRequest,
    BrokerOrderUpdate,
    BrokerPosition,
)
from app.core.errors import FeatureDisabledError
from app.models.enums import ExecutionMode

_MSG = "Order execution is not available in Phase 0."


class DisabledBrokerAdapter(BrokerAdapter):
    """Refuses every order operation. The only broker wired up in Phase 0."""

    name = "disabled"
    mode = ExecutionMode.PAPER

    async def health(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, state=AdapterState.DISABLED, detail=_MSG)

    async def place_order(self, request: BrokerOrderRequest) -> BrokerOrderAck:
        raise FeatureDisabledError(_MSG)

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderUpdate:
        raise FeatureDisabledError(_MSG)

    async def get_order(self, broker_order_id: str) -> BrokerOrderUpdate:
        raise FeatureDisabledError(_MSG)

    async def get_positions(self) -> list[BrokerPosition]:
        return []

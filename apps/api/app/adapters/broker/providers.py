"""Broker registry: which brokers MarketOS knows, what each needs and can do.

Adding a broker = one adapter in ``app/adapters/broker/<name>.py`` + one entry
here. The Settings page renders the credential form from ``fields``, so no
frontend change is needed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class BrokerProvider(StrEnum):
    PAPER = "paper"
    KITE = "kite"
    DHAN = "dhan"
    # Planned (shown as "coming soon"): same adapter pattern.
    UPSTOX = "upstox"
    ANGEL = "angel"
    FYERS = "fyers"


class CredentialField(BaseModel):
    name: str
    label: str
    secret_name: str  # key in the encrypted secret store
    secret: bool = True  # never shown back (only "set" + masked hint)
    placeholder: str = ""
    help: str = ""


class Capabilities(BaseModel):
    place_orders: bool = False  # live order placement (gated off in this build)
    modify_orders: bool = False
    broker_bracket: bool = False  # entry + target + SL held at the broker
    broker_trailing: bool = False  # trailing SL held at the broker
    positions: bool = False
    funds: bool = False
    exit_all: bool = False  # one call closes everything
    kill_switch: bool = False  # broker-side kill switch
    market_data: bool = False
    historical: bool = False
    expired_options: bool = False  # minute data for expired option contracts


class BrokerInfo(BaseModel):
    id: BrokerProvider
    label: str
    available: bool
    description: str
    fields: list[CredentialField]
    login_note: str = ""
    capabilities: Capabilities
    static_ip_required: bool = False
    costs: str = ""
    docs_url: str | None = None


def broker_secret(provider: BrokerProvider, field: str) -> str:
    return f"broker.{provider.value}.{field}"


BROKERS: dict[BrokerProvider, BrokerInfo] = {
    b.id: b
    for b in [
        BrokerInfo(
            id=BrokerProvider.PAPER,
            label="Paper (simulated)",
            available=True,
            description="Practice with fake money. Fills are simulated at live or manual prices.",
            fields=[],
            capabilities=Capabilities(
                place_orders=True,
                modify_orders=True,
                broker_bracket=True,
                broker_trailing=True,
                positions=True,
                exit_all=True,
                kill_switch=True,
            ),
        ),
        BrokerInfo(
            id=BrokerProvider.KITE,
            label="Zerodha Kite",
            available=True,
            description=(
                "Live prices and historical candles (for replay). Kite has no trailing "
                "stop-loss or bracket orders, so MarketOS manages SL/targets itself."
            ),
            fields=[
                CredentialField(
                    name="api_key",
                    label="API key",
                    secret_name="kite.api_key",  # noqa: S106 - a key name
                    placeholder="from developers.kite.trade",
                ),
                CredentialField(
                    name="api_secret",
                    label="API secret",
                    secret_name="kite.api_secret",  # noqa: S106 - a key name
                ),
            ],
            login_note="Daily: Open Kite login, sign in, paste the redirect URL back.",
            capabilities=Capabilities(
                place_orders=True,
                modify_orders=True,
                positions=True,
                funds=True,
                market_data=True,
                historical=True,
            ),
            static_ip_required=True,
            costs="Kite Connect plan for live data and historical candles.",
            docs_url="https://kite.trade/docs/connect/v3/",
        ),
        BrokerInfo(
            id=BrokerProvider.DHAN,
            label="Dhan",
            available=True,
            description=(
                "Super Orders hold entry + target + stop-loss + trailing at Dhan; "
                "one-call Exit All and a broker-side kill switch."
            ),
            fields=[
                CredentialField(
                    name="client_id",
                    label="Client ID",
                    secret_name=broker_secret(BrokerProvider.DHAN, "client_id"),
                    secret=False,
                    placeholder="e.g. 1000000001",
                    help="Your Dhan client ID (top-right of web.dhan.co).",
                ),
                CredentialField(
                    name="access_token",
                    label="Access token",
                    secret_name=broker_secret(BrokerProvider.DHAN, "access_token"),
                    placeholder="eyJ0eXAiOiJKV1Qi…",
                    help="web.dhan.co → My Profile → DhanHQ Trading APIs → Generate token "
                    "(valid 24 h; MarketOS renews it automatically while it stays valid).",
                ),
            ],
            login_note="Token lasts 24 hours; MarketOS renews it before it expires.",
            capabilities=Capabilities(
                place_orders=True,
                modify_orders=True,
                broker_bracket=True,
                broker_trailing=True,
                positions=True,
                funds=True,
                exit_all=True,
                kill_switch=True,
                market_data=True,
                historical=True,
                expired_options=True,
            ),
            static_ip_required=True,
            costs="Trading APIs free; Data APIs (live prices, candles) ₹499/month.",
            docs_url="https://dhanhq.co/docs/v2/",
        ),
        BrokerInfo(
            id=BrokerProvider.UPSTOX,
            label="Upstox (coming soon)",
            available=False,
            description="Planned. Ask to add it: one adapter file.",
            fields=[],
            capabilities=Capabilities(),
        ),
        BrokerInfo(
            id=BrokerProvider.ANGEL,
            label="Angel One (coming soon)",
            available=False,
            description="Planned. Ask to add it: one adapter file.",
            fields=[],
            capabilities=Capabilities(),
        ),
        BrokerInfo(
            id=BrokerProvider.FYERS,
            label="Fyers (coming soon)",
            available=False,
            description="Planned. Ask to add it: one adapter file.",
            fields=[],
            capabilities=Capabilities(),
        ),
    ]
}

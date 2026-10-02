"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-02 19:45:45.831488+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broker_accounts",
        sa.Column(
            "broker",
            sa.Enum(
                "paper",
                "kite",
                name="broker_name",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column(
            "mode",
            sa.Enum(
                "paper",
                "live",
                name="execution_mode",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("external_account_id", sa.String(length=64), nullable=True),
        sa.Column("credentials_ref", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "broker IN ('paper', 'kite')", name=op.f("ck_broker_accounts_broker_name")
        ),
        sa.CheckConstraint(
            "mode IN ('paper', 'live')", name=op.f("ck_broker_accounts_execution_mode")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broker_accounts")),
        sa.UniqueConstraint("label", name=op.f("uq_broker_accounts_label")),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=True),
        sa.Column("aggregate_id", sa.UUID(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correlation_id", sa.UUID(), nullable=True),
        sa.Column("causation_id", sa.UUID(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(
        "ix_events_aggregate", "events", ["aggregate_type", "aggregate_id"], unique=False
    )
    op.create_index(op.f("ix_events_correlation_id"), "events", ["correlation_id"], unique=False)
    op.create_index(op.f("ix_events_event_type"), "events", ["event_type"], unique=False)
    op.create_index("ix_events_occurred_at", "events", ["occurred_at"], unique=False)
    op.create_table(
        "instruments",
        sa.Column(
            "exchange",
            sa.Enum(
                "NSE",
                "BSE",
                "NFO",
                "BFO",
                "MCX",
                "CDS",
                name="exchange",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("tradingsymbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column(
            "instrument_type",
            sa.Enum(
                "EQ",
                "FUT",
                "CE",
                "PE",
                "INDEX",
                name="instrument_type",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("instrument_token", sa.BigInteger(), nullable=True),
        sa.Column("segment", sa.String(length=32), nullable=True),
        sa.Column("expiry", sa.Date(), nullable=True),
        sa.Column("strike", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("tick_size", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "exchange IN ('NSE', 'BSE', 'NFO', 'BFO', 'MCX', 'CDS')",
            name=op.f("ck_instruments_exchange"),
        ),
        sa.CheckConstraint(
            "instrument_type IN ('EQ', 'FUT', 'CE', 'PE', 'INDEX')",
            name=op.f("ck_instruments_instrument_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instruments")),
        sa.UniqueConstraint(
            "exchange", "tradingsymbol", name=op.f("uq_instruments_exchange_tradingsymbol")
        ),
        sa.UniqueConstraint("instrument_token", name=op.f("uq_instruments_instrument_token")),
    )
    op.create_table(
        "signal_sources",
        sa.Column(
            "kind",
            sa.Enum(
                "telegram",
                "manual",
                "webhook",
                name="signal_source_kind",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('telegram', 'manual', 'webhook')",
            name=op.f("ck_signal_sources_signal_source_kind"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_sources")),
        sa.UniqueConstraint("kind", "external_id", name=op.f("uq_signal_sources_kind_external_id")),
    )
    op.create_table(
        "positions",
        sa.Column("broker_account_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column(
            "product",
            sa.Enum(
                "CNC",
                "MIS",
                "NRML",
                name="product_type",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("average_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "product IN ('CNC', 'MIS', 'NRML')", name=op.f("ck_positions_product_type")
        ),
        sa.ForeignKeyConstraint(
            ["broker_account_id"],
            ["broker_accounts.id"],
            name=op.f("fk_positions_broker_account_id_broker_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_positions_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_positions")),
        sa.UniqueConstraint(
            "broker_account_id",
            "instrument_id",
            "product",
            name=op.f("uq_positions_broker_account_id_instrument_id_product"),
        ),
    )
    op.create_index(
        op.f("ix_positions_broker_account_id"), "positions", ["broker_account_id"], unique=False
    )
    op.create_index(
        op.f("ix_positions_instrument_id"), "positions", ["instrument_id"], unique=False
    )
    op.create_table(
        "raw_messages",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("external_message_id", sa.String(length=128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "parsed",
                "ignored",
                "failed",
                name="raw_message_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'parsed', 'ignored', 'failed')",
            name=op.f("ck_raw_messages_raw_message_status"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["signal_sources.id"],
            name=op.f("fk_raw_messages_source_id_signal_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_messages")),
        sa.UniqueConstraint(
            "source_id",
            "external_message_id",
            name=op.f("uq_raw_messages_source_id_external_message_id"),
        ),
    )
    op.create_index(op.f("ix_raw_messages_source_id"), "raw_messages", ["source_id"], unique=False)
    op.create_index(op.f("ix_raw_messages_status"), "raw_messages", ["status"], unique=False)
    op.create_table(
        "signals",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("raw_message_id", sa.UUID(), nullable=True),
        sa.Column("instrument_id", sa.UUID(), nullable=True),
        sa.Column("symbol_text", sa.String(length=128), nullable=False),
        sa.Column(
            "side",
            sa.Enum(
                "BUY", "SELL", name="side", native_enum=False, create_constraint=False, length=32
            ),
            nullable=False,
        ),
        sa.Column("entry_low", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("entry_high", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("stop_loss", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("targets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "validated",
                "rejected",
                "executed",
                "expired",
                "cancelled",
                name="signal_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "parser",
            sa.Enum(
                "manual",
                "rule",
                "llm",
                name="signal_parser",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "parser IN ('manual', 'rule', 'llm')", name=op.f("ck_signals_signal_parser")
        ),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name=op.f("ck_signals_side")),
        sa.CheckConstraint(
            "status IN ('new', 'validated', 'rejected', 'executed', 'expired', 'cancelled')",
            name=op.f("ck_signals_signal_status"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_signals_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_signals_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_message_id"],
            ["raw_messages.id"],
            name=op.f("fk_signals_raw_message_id_raw_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["signal_sources.id"],
            name=op.f("fk_signals_source_id_signal_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signals")),
    )
    op.create_index(op.f("ix_signals_instrument_id"), "signals", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_signals_raw_message_id"), "signals", ["raw_message_id"], unique=False)
    op.create_index(op.f("ix_signals_source_id"), "signals", ["source_id"], unique=False)
    op.create_index(op.f("ix_signals_status"), "signals", ["status"], unique=False)
    op.create_table(
        "orders",
        sa.Column("broker_account_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("signal_id", sa.UUID(), nullable=True),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
        sa.Column(
            "mode",
            sa.Enum(
                "paper",
                "live",
                name="execution_mode",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "side",
            sa.Enum(
                "BUY", "SELL", name="side", native_enum=False, create_constraint=False, length=32
            ),
            nullable=False,
        ),
        sa.Column(
            "order_type",
            sa.Enum(
                "MARKET",
                "LIMIT",
                "SL",
                "SL-M",
                name="order_type",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "product",
            sa.Enum(
                "CNC",
                "MIS",
                "NRML",
                name="product_type",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "validity",
            sa.Enum(
                "DAY",
                "IOC",
                name="order_validity",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("trigger_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "created",
                "submitted",
                "open",
                "partially_filled",
                "filled",
                "cancelled",
                "rejected",
                name="order_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("filled_quantity", sa.Integer(), nullable=False),
        sa.Column("average_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("mode IN ('paper', 'live')", name=op.f("ck_orders_execution_mode")),
        sa.CheckConstraint(
            "order_type IN ('MARKET', 'LIMIT', 'SL', 'SL-M')", name=op.f("ck_orders_order_type")
        ),
        sa.CheckConstraint(
            "product IN ('CNC', 'MIS', 'NRML')", name=op.f("ck_orders_product_type")
        ),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name=op.f("ck_orders_side")),
        sa.CheckConstraint(
            "status IN ('created', 'submitted', 'open', 'partially_filled', 'filled', 'cancelled', 'rejected')",
            name=op.f("ck_orders_order_status"),
        ),
        sa.CheckConstraint("validity IN ('DAY', 'IOC')", name=op.f("ck_orders_order_validity")),
        sa.CheckConstraint(
            "filled_quantity >= 0 AND filled_quantity <= quantity",
            name=op.f("ck_orders_filled_quantity_range"),
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_orders_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["broker_account_id"],
            ["broker_accounts.id"],
            name=op.f("fk_orders_broker_account_id_broker_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_orders_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.id"],
            name=op.f("fk_orders_signal_id_signals"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("client_order_id", name=op.f("uq_orders_client_order_id")),
    )
    op.create_index(
        op.f("ix_orders_broker_account_id"), "orders", ["broker_account_id"], unique=False
    )
    op.create_index(op.f("ix_orders_broker_order_id"), "orders", ["broker_order_id"], unique=False)
    op.create_index(op.f("ix_orders_instrument_id"), "orders", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_orders_signal_id"), "orders", ["signal_id"], unique=False)
    op.create_index(op.f("ix_orders_status"), "orders", ["status"], unique=False)
    op.create_table(
        "trades",
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("broker_trade_id", sa.String(length=64), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_trades_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name=op.f("fk_trades_order_id_orders"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trades")),
    )
    op.create_index(op.f("ix_trades_order_id"), "trades", ["order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_trades_order_id"), table_name="trades")
    op.drop_table("trades")
    op.drop_index(op.f("ix_orders_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_signal_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_instrument_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_broker_order_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_broker_account_id"), table_name="orders")
    op.drop_table("orders")
    op.drop_index(op.f("ix_signals_status"), table_name="signals")
    op.drop_index(op.f("ix_signals_source_id"), table_name="signals")
    op.drop_index(op.f("ix_signals_raw_message_id"), table_name="signals")
    op.drop_index(op.f("ix_signals_instrument_id"), table_name="signals")
    op.drop_table("signals")
    op.drop_index(op.f("ix_raw_messages_status"), table_name="raw_messages")
    op.drop_index(op.f("ix_raw_messages_source_id"), table_name="raw_messages")
    op.drop_table("raw_messages")
    op.drop_index(op.f("ix_positions_instrument_id"), table_name="positions")
    op.drop_index(op.f("ix_positions_broker_account_id"), table_name="positions")
    op.drop_table("positions")
    op.drop_table("signal_sources")
    op.drop_table("instruments")
    op.drop_index("ix_events_occurred_at", table_name="events")
    op.drop_index(op.f("ix_events_event_type"), table_name="events")
    op.drop_index(op.f("ix_events_correlation_id"), table_name="events")
    op.drop_index("ix_events_aggregate", table_name="events")
    op.drop_table("events")
    op.drop_table("broker_accounts")

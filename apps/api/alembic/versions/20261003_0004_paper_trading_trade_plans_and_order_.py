"""paper trading: trade plans and order roles

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-03 02:54:02.219518+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trade_plans",
        sa.Column("signal_id", sa.UUID(), nullable=True),
        sa.Column("broker_account_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column(
            "side",
            sa.Enum(
                "BUY", "SELL", name="side", native_enum=False, create_constraint=False, length=32
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
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "open",
                "closed",
                "cancelled",
                name="trade_plan_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("planned_entry", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("stop_loss", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("target", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("entry_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("exit_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("charges", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "exit_reason",
            sa.Enum(
                "target",
                "stop",
                "manual",
                "expired",
                "cancelled",
                name="exit_reason",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
            "exit_reason IN ('target', 'stop', 'manual', 'expired', 'cancelled')",
            name=op.f("ck_trade_plans_exit_reason"),
        ),
        sa.CheckConstraint(
            "product IN ('CNC', 'MIS', 'NRML')", name=op.f("ck_trade_plans_product_type")
        ),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name=op.f("ck_trade_plans_side")),
        sa.CheckConstraint(
            "status IN ('pending', 'open', 'closed', 'cancelled')",
            name=op.f("ck_trade_plans_trade_plan_status"),
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_trade_plans_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["broker_account_id"],
            ["broker_accounts.id"],
            name=op.f("fk_trade_plans_broker_account_id_broker_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_trade_plans_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.id"],
            name=op.f("fk_trade_plans_signal_id_signals"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trade_plans")),
    )
    op.create_index(
        op.f("ix_trade_plans_broker_account_id"), "trade_plans", ["broker_account_id"], unique=False
    )
    op.create_index(
        op.f("ix_trade_plans_instrument_id"), "trade_plans", ["instrument_id"], unique=False
    )
    op.create_index(op.f("ix_trade_plans_signal_id"), "trade_plans", ["signal_id"], unique=False)
    op.create_index(op.f("ix_trade_plans_status"), "trade_plans", ["status"], unique=False)
    op.add_column("orders", sa.Column("trade_plan_id", sa.UUID(), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "role",
            sa.Enum(
                "entry",
                "stop",
                "target",
                "exit",
                "manual",
                name="order_role",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="manual",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_orders_order_role"),
        "orders",
        "role IN ('entry', 'stop', 'target', 'exit', 'manual')",
    )
    op.add_column("orders", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_orders_trade_plan_id"), "orders", ["trade_plan_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_orders_trade_plan_id_trade_plans"),
        "orders",
        "trade_plans",
        ["trade_plan_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_orders_trade_plan_id_trade_plans"), "orders", type_="foreignkey")
    op.drop_index(op.f("ix_orders_trade_plan_id"), table_name="orders")
    op.drop_column("orders", "expires_at")
    op.drop_constraint(op.f("ck_orders_order_role"), "orders", type_="check")
    op.drop_column("orders", "role")
    op.drop_column("orders", "trade_plan_id")
    op.drop_index(op.f("ix_trade_plans_status"), table_name="trade_plans")
    op.drop_index(op.f("ix_trade_plans_signal_id"), table_name="trade_plans")
    op.drop_index(op.f("ix_trade_plans_instrument_id"), table_name="trade_plans")
    op.drop_index(op.f("ix_trade_plans_broker_account_id"), table_name="trade_plans")
    op.drop_table("trade_plans")

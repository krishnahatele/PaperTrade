"""Domain enumerations shared by models, schemas and adapters."""

from __future__ import annotations

from enum import StrEnum


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"
    MCX = "MCX"
    CDS = "CDS"


class Segment(StrEnum):
    """Market segment, used for reporting and trading hours."""

    EQUITY = "equity"
    FNO = "fno"
    COMMODITY = "commodity"
    CURRENCY = "currency"
    INDEX = "index"


class InstrumentType(StrEnum):
    EQ = "EQ"
    FUT = "FUT"
    CE = "CE"
    PE = "PE"
    INDEX = "INDEX"


class BrokerName(StrEnum):
    PAPER = "paper"
    KITE = "kite"


class ExecutionMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class SignalSourceKind(StrEnum):
    TELEGRAM = "telegram"
    MANUAL = "manual"
    WEBHOOK = "webhook"


class RawMessageStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    IGNORED = "ignored"
    FAILED = "failed"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class SignalStatus(StrEnum):
    NEW = "new"
    VALIDATED = "validated"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class SignalParser(StrEnum):
    MANUAL = "manual"
    RULE = "rule"
    LLM = "llm"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class ProductType(StrEnum):
    CNC = "CNC"
    MIS = "MIS"
    NRML = "NRML"


class OrderValidity(StrEnum):
    DAY = "DAY"
    IOC = "IOC"


class OrderStatus(StrEnum):
    CREATED = "created"
    SUBMITTED = "submitted"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderRole(StrEnum):
    ENTRY = "entry"
    STOP = "stop"
    TARGET = "target"
    EXIT = "exit"
    MANUAL = "manual"


class TradePlanStatus(StrEnum):
    PENDING = "pending"  # entry order working
    OPEN = "open"  # entry filled, stop + target working
    CLOSED = "closed"
    CANCELLED = "cancelled"  # entry never filled


class ExitReason(StrEnum):
    TARGET = "target"
    STOP = "stop"
    TRAILING_STOP = "trailing_stop"  # stop that had been moved up (cost / TP1 / trail)
    MANUAL = "manual"
    EXIT_ALL = "exit_all"  # panic button / kill switch
    END_OF_DAY = "end_of_day"  # replay square-off
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ExitMode(StrEnum):
    SINGLE = "single"  # all quantity at one target
    SPLIT = "split"  # lot-wise across TP1, TP2, ...


class TrailMode(StrEnum):
    NONE = "none"
    STEP = "step"  # SL to cost after TP1, to TP1 after TP2 ...
    POINTS = "points"
    PERCENT = "percent"


class AlertKind(StrEnum):
    NEWS = "news"
    MARKET = "market"
    SYSTEM = "system"


class ReplayStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReplayOutcome(StrEnum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    ENTRY_NOT_HIT = "entry_not_hit"  # price never reached the entry in time
    NO_DATA = "no_data"  # no historical candles for the contract
    UNRESOLVED = "unresolved"  # symbol could not be matched to a contract
    INCOMPLETE = "incomplete"  # missing entry / stop-loss
    NOT_SIGNAL = "not_signal"

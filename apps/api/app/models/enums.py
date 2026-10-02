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

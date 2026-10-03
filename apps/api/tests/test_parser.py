from decimal import Decimal

import pytest

from app.models.enums import InstrumentType, Side
from app.parsing.llm import to_parsed
from app.parsing.rules import parse_rules

CASES = [
    # text, side, symbol, type, strike, entry_low, entry_high, sl, targets
    (
        "BUY NIFTY 24500 CE ABOVE 120 SL 100 TGT 140/160/180",
        "BUY",
        "NIFTY 24500 CE",
        "CE",
        "24500",
        "120",
        "120",
        "100",
        ["140", "160", "180"],
    ),
    (
        "RELIANCE BUY 2450-2460 SL 2420 TARGET 2500, 2550",
        "BUY",
        "RELIANCE",
        "EQ",
        None,
        "2450",
        "2460",
        "2420",
        ["2500", "2550"],
    ),
    (
        "Sell INFY cmp 1500 stoploss 1530 T1 1450 T2 1400",
        "SELL",
        "INFY",
        "EQ",
        None,
        "1500",
        "1500",
        "1530",
        ["1450", "1400"],
    ),
    (
        "BUY TATAMOTORS FUT 950 SL 940 TGT 965",
        "BUY",
        "TATAMOTORS FUT",
        "FUT",
        None,
        "950",
        "950",
        "940",
        ["965"],
    ),
    (
        "Buy HDFCBANK 1650 stop loss 1620 targets 1700/1750",
        "BUY",
        "HDFCBANK",
        "EQ",
        None,
        "1650",
        "1650",
        "1620",
        ["1700", "1750"],
    ),
    (
        "🚀 bank nifty 52,000 put buy @ 300 sl 250 tgt 350 🎯",
        "BUY",
        "BANKNIFTY 52000 PE",
        "PE",
        "52000",
        "300",
        "300",
        "250",
        ["350"],
    ),
    (
        "NIFTY24500CE BUY ABOVE 85 SL 70 TARGET 100",
        "BUY",
        "NIFTY 24500 CE",
        "CE",
        "24500",
        "85",
        "85",
        "70",
        ["100"],
    ),
]


@pytest.mark.parametrize(
    ("text", "side", "symbol", "typ", "strike", "lo", "hi", "sl", "tgts"), CASES
)
def test_rule_parser_formats(
    text: str,
    side: str,
    symbol: str,
    typ: str,
    strike: str | None,
    lo: str,
    hi: str,
    sl: str,
    tgts: list[str],
) -> None:
    p = parse_rules(text)
    assert p.is_signal, p.reason
    assert p.side is Side(side)
    assert p.symbol_text == symbol
    assert p.instrument_type is InstrumentType(typ)
    assert p.strike == (Decimal(strike) if strike else None)
    assert (p.entry_low, p.entry_high, p.stop_loss) == (Decimal(lo), Decimal(hi), Decimal(sl))
    assert p.targets == [Decimal(t) for t in tgts]
    assert p.confidence >= Decimal("0.75")
    assert p.warnings == []


def test_option_without_verb_assumes_buy() -> None:
    p = parse_rules("BANKNIFTY 52000 PE @ 300 SL 250 TARGET 350")
    assert p.side is Side.BUY
    assert any("assumed BUY" in w for w in p.warnings)
    assert p.confidence < Decimal("0.95")


def test_expiry_month_is_captured() -> None:
    p = parse_rules("NIFTY 24 OCT 24,500 CALL buy above 120 sl 100")
    assert p.symbol_text == "NIFTY 24500 CE"
    assert p.expiry_text == "24 OCT"


@pytest.mark.parametrize(
    "text",
    [
        "Target 1 achieved 🎯 book profit",
        "Good morning traders!",
        "SL hit, exit now",
        "NIFTY 24500 CE looks strong today",
    ],
)
def test_non_signals(text: str) -> None:
    assert parse_rules(text).is_signal is False


def test_inconsistent_levels_lower_confidence() -> None:
    p = parse_rules("BUY SBIN 800 SL 820 TGT 790")
    assert p.is_signal
    assert p.confidence <= Decimal("0.5")
    assert any("wrong side" in w for w in p.warnings)


def test_missing_stop_loss_warns() -> None:
    p = parse_rules("BUY ITC 450 TGT 470")
    assert "no stop loss given" in p.warnings
    assert p.confidence < Decimal("0.8")  # below RULES_ACCEPT: LLM gets a look


def test_llm_output_is_validated() -> None:
    p = to_parsed(
        {
            "is_signal": True,
            "reason": None,
            "side": "BUY",
            "symbol_text": "nifty 24500 ce",
            "underlying": "nifty",
            "instrument_type": "CE",
            "strike": "24500",
            "expiry_text": None,
            "entry_low": "120",
            "entry_high": "1,25",
            "stop_loss": "100",
            "targets": ["140", "abc", "-5"],
            "confidence": 1.7,
        }
    )
    assert p.symbol_text == "NIFTY 24500 CE"
    assert p.underlying == "NIFTY"
    assert p.targets == [Decimal("140")]  # junk dropped
    assert p.confidence == Decimal("1.000")  # clamped
    assert p.entry_high == Decimal("125")


def test_llm_output_missing_side_is_not_signal() -> None:
    p = to_parsed({"is_signal": True, "side": None, "symbol_text": "X", "confidence": 0.9})
    assert p.is_signal is False

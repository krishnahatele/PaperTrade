"""Deterministic parser for common Indian-market Telegram signal formats.

Handles messages such as::

    BUY NIFTY 24500 CE ABOVE 120 SL 100 TGT 140/160/180
    BANKNIFTY 52000 PE @ 300 SL 250 TARGET 350
    RELIANCE BUY 2450-2460 SL 2420 TARGET 2500, 2550
    SELL INFY CMP 1500 STOPLOSS 1530 T1 1450 T2 1400
    BUY TATAMOTORS FUT 950 SL 940 TGT 965

Anything it cannot read confidently gets a low confidence (or is_signal=False)
so the LLM fallback can take over.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.models.enums import InstrumentType, Side
from app.parsing.models import ParsedSignal, sanity_check

NUM = r"(\d+(?:\.\d+)?)"
MONTHS = "JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC"

STOPWORDS = {
    "BUY",
    "SELL",
    "LONG",
    "SHORT",
    "SL",
    "STOP",
    "LOSS",
    "STOPLOSS",
    "TGT",
    "TARGET",
    "TARGETS",
    "TP",
    "ABOVE",
    "BELOW",
    "AT",
    "CMP",
    "NEAR",
    "AROUND",
    "ENTRY",
    "RANGE",
    "ZONE",
    "CE",
    "PE",
    "CALL",
    "PUT",
    "FUT",
    "FUTURE",
    "FUTURES",
    "AND",
    "OR",
    "TO",
    "ONLY",
    "INTRADAY",
    "POSITIONAL",
    "BTST",
    "STBT",
    "OPTION",
    "OPTIONS",
    "EXPIRY",
    "WEEKLY",
    "MONTHLY",
    "LOT",
    "LOTS",
    "QTY",
    "HERO",
    "ZERO",
    "JACKPOT",
    "TRADE",
    "NEW",
    "CALLS",
    "FOR",
    "THE",
    "IN",
    "ON",
    "OF",
    "RS",
    "INR",
    "NSE",
    "BSE",
    "NFO",
    "MCX",
    "SAFE",
    "RISKY",
    "HIGH",
    "RISK",
    "BOOK",
    "PROFIT",
    "HOLD",
    "EXIT",
    "HIT",
    "ACHIEVED",
    "DONE",
    "UPDATE",
    "ALERT",
    "SIGNAL",
    "TODAY",
    "TOMORROW",
    "NOW",
    "STRICT",
    "TRAIL",
    "TRAILING",
    "ADD",
    "MORE",
    "AVG",
    "AVERAGE",
    "PRICE",
    "LTP",
    # chatter that sits next to calls in channel posts
    "PLEASE",
    "PLZ",
    "JOIN",
    "FREE",
    "PAID",
    "CHANNEL",
    "GROUP",
    "MEMBERS",
    "CLICK",
    "LINK",
    "CONTACT",
    "WHATSAPP",
    "VIP",
    "PREMIUM",
    "GOOD",
    "MORNING",
    "GM",
    "LEVEL",
    "LEVELS",
    "SETUP",
    "VIEW",
    "WATCH",
    "STOCK",
    "SHARE",
    "SHARES",
    "CASH",
    "EQUITY",
    "SWING",
    "SCALP",
    "SCALPING",
    "AGAIN",
    "IF",
    "SUSTAINS",
    "CLOSING",
    "BASIS",
    "WITH",
    "LTD",
    "LIMITED",
    "OUR",
    "YOUR",
    "WE",
    "US",
    "ME",
    "IT",
    "THIS",
    "IS",
} | set(MONTHS.split("|"))
NAME_JOINERS = {"OF", "AND", "&"}  # "BANK OF BARODA", "LARSEN & TOUBRO"

INDEX_ALIASES = {
    "NIFTY50": "NIFTY",
    "NIFTY 50": "NIFTY",
    "BANK NIFTY": "BANKNIFTY",
    "BNF": "BANKNIFTY",
    "FIN NIFTY": "FINNIFTY",
    "MIDCAP NIFTY": "MIDCPNIFTY",
    "MIDCPNIFTY": "MIDCPNIFTY",
    # MCX commodities as they are usually written
    "CRUDE OIL MINI": "CRUDEOILM",
    "CRUDE MINI": "CRUDEOILM",
    "CRUDEOIL MINI": "CRUDEOILM",
    "CRUDE OIL": "CRUDEOIL",
    "CRUDE": "CRUDEOIL",
    "NATURAL GAS MINI": "NATGASMINI",
    "NATURAL GAS": "NATURALGAS",
    "NAT GAS": "NATURALGAS",
    "NG": "NATURALGAS",
    "GOLD MINI": "GOLDM",
    "SILVER MINI": "SILVERM",
    "SILVER MIC": "SILVERMIC",
}

_FOLLOW_UP = re.compile(
    r"\b(TARGET|TGT|T\d|SL)\s*(\d\s*)?(HIT|ACHIEVED|DONE|TRIGGERED)\b|\bBOOK(ED)?\s+PROFIT|\bEXIT\b"
)


def _d(s: str) -> Decimal | None:
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def normalise(text: str) -> str:
    t = text.upper()
    t = t.replace("₹", " ").replace("RS.", " ").replace("\u2013", "-").replace("\u2014", "-")
    t = re.sub(r"[^\w\s./@&,:-]", " ", t)  # drop emojis and decoration
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)  # 24,500 -> 24500
    for alias, canonical in INDEX_ALIASES.items():
        t = re.sub(rf"\b{alias}\b", canonical, t)
    t = re.sub(r"\bSTOP\s*-?\s*LOSS\b|\bS/L\b|\bSTOPLOSS\b", " SL ", t)
    t = re.sub(r"\bTARGETS?\b|\bTGTS?\b|\bTP\b", " TGT ", t)
    t = re.sub(r"\bCALL\b", "CE", t)
    t = re.sub(r"\bPUT\b", "PE", t)
    return re.sub(r"\s+", " ", t).strip()


def _side(t: str) -> Side | None:
    m = re.search(r"\b(BUY|SELL|LONG|SHORT)\b", t)
    if not m:
        return None
    return Side.BUY if m.group(1) in ("BUY", "LONG") else Side.SELL


def _stop_loss(t: str) -> Decimal | None:
    m = re.search(rf"\bSL\b\s*[:@=-]?\s*{NUM}", t)
    return _d(m.group(1)) if m else None


def _targets(t: str) -> list[Decimal]:
    out: list[Decimal] = []
    m = re.search(rf"\bTGT\b\s*[:@=-]?\s*({NUM}(?:\s*(?:/|,|-|&|\s)\s*{NUM})*)", t)
    if m:
        out = [d for x in re.findall(NUM, m.group(1)) if (d := _d(x)) is not None]
    for x in re.findall(rf"\bT\d\b\s*[:@=-]?\s*{NUM}", t):  # T1 120 T2 140
        d = _d(x)
        if d is not None and d not in out:
            out.append(d)
    return out


def _instrument(
    t: str,
) -> tuple[str | None, str | None, InstrumentType | None, Decimal | None, str | None]:
    """Return (symbol_text, underlying, type, strike, expiry_text)."""
    # Options: NIFTY 24500 CE | NIFTY 24 OCT 24500 CE | NIFTY24500CE
    m = re.search(
        rf"\b([A-Z][A-Z&-]{{1,19}})\s*((?:\d{{1,2}}\s*(?:{MONTHS})|(?:{MONTHS}))\s+)?(\d{{2,6}}(?:\.\d+)?)\s*(CE|PE)\b",
        t,
    )
    if m and m.group(1) not in STOPWORDS:
        und, exp, strike, kind = (
            m.group(1),
            (m.group(2) or "").strip() or None,
            m.group(3),
            m.group(4),
        )
        typ = InstrumentType.CE if kind == "CE" else InstrumentType.PE
        return f"{und} {strike} {kind}", und, typ, _d(strike), exp
    # Futures: TATAMOTORS FUT | NIFTY OCT FUT
    m = re.search(rf"\b([A-Z][A-Z&-]{{1,19}})\s+(?:({MONTHS})\s+)?FUT(?:URES?)?\b", t)
    if m and m.group(1) not in STOPWORDS:
        return f"{m.group(1)} FUT", m.group(1), InstrumentType.FUT, None, m.group(2)
    # Equity: the name right after the verb ("BUY Belrise Industries @ 242"), which may
    # be a company name rather than the NSE symbol; resolution matches both.
    m = re.search(r"\b(?:BUY|SELL|LONG|SHORT)\b\s+((?:(?:[A-Z][A-Z&.-]*|&)\s*){1,5})", t)
    if m:
        words: list[str] = []
        for tok in m.group(1).split():
            if tok in NAME_JOINERS and words:
                words.append(tok)
                continue
            if tok in STOPWORDS or re.fullmatch(r"T\d+", tok):
                break
            words.append(tok)
        while words and words[-1] in NAME_JOINERS:
            words.pop()
        if words:
            name = " ".join(words)
            return name, name, InstrumentType.EQ, None, None
    # Otherwise the first plausible ticker token ("RELIANCE BUY 2450")
    for tok in re.findall(r"\b[A-Z][A-Z&-]{1,19}\b", t):
        if tok not in STOPWORDS and not re.fullmatch(r"T\d+", tok):
            return tok, tok, InstrumentType.EQ, None, None
    return None, None, None, None, None


def _entry(t: str, strike: Decimal | None) -> tuple[Decimal | None, Decimal | None]:
    # Cut away SL / target clauses so their numbers aren't mistaken for entry.
    head = re.split(r"\bSL\b|\bTGT\b|\bT\d\b", t, maxsplit=1)[0]
    m = re.search(
        rf"(?:\b(?:ABOVE|BELOW|AT|CMP|NEAR|AROUND|ENTRY|RANGE|ZONE)\b|@)\s*[:=-]?\s*{NUM}"
        rf"(?:\s*(?:-|TO)\s*{NUM})?",
        head,
    )
    if m:
        lo = _d(m.group(1))
        hi = _d(m.group(2)) if m.group(2) else lo
        return lo, hi
    candidates: list[tuple[Decimal, Decimal]] = []
    for lo_s, hi_s in re.findall(rf"(?<![A-Z\d.]){NUM}(?:\s*-\s*{NUM})?", head):
        lo = _d(lo_s)
        if lo is None or (strike is not None and lo == strike):
            continue
        hi = (_d(hi_s) if hi_s else None) or lo
        candidates.append((lo, hi))
    if candidates:
        return candidates[-1]
    return None, None


def _call_part(text: str) -> str:
    """Drop header lines above the first line that holds a BUY/SELL and a price, so a
    banner like "SAHI Trade Alert : 1 Oct" isn't read as the stock."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.search(r"\b(buy|sell|long|short)\b", line, re.IGNORECASE) and re.search(r"\d", line):
            return "\n".join(lines[i:])
    return text


def parse_rules(text: str) -> ParsedSignal:
    t = normalise(_call_part(text))
    if _FOLLOW_UP.search(t) and not re.search(r"\b(BUY|SELL)\b", t):
        return ParsedSignal(is_signal=False, reason="follow-up / status update, not a new signal")
    side = _side(t)
    symbol, und, typ, strike, expiry = _instrument(t)
    assumed_side = False
    if side is None:
        # Option calls are often posted without a verb ("BANKNIFTY 52000 PE @ 300 SL 250");
        # these channels almost always mean buying the option.
        if typ in (InstrumentType.CE, InstrumentType.PE) and re.search(r"\bSL\b|\bTGT\b", t):
            side, assumed_side = Side.BUY, True
        else:
            return ParsedSignal(is_signal=False, reason="no BUY/SELL instruction found")
    if symbol is None:
        return ParsedSignal(is_signal=False, side=side, reason="no instrument found")

    lo, hi = _entry(t, strike)
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    sl = _stop_loss(t)
    targets = _targets(t)

    p = ParsedSignal(
        is_signal=True,
        side=side,
        symbol_text=symbol,
        underlying=und,
        instrument_type=typ,
        strike=strike,
        expiry_text=expiry,
        entry_low=lo,
        entry_high=hi,
        stop_loss=sl,
        targets=targets,
    )
    conf = Decimal("0.45")
    conf += Decimal("0.15") if lo is not None else 0
    conf += Decimal("0.2") if sl is not None else 0
    conf += Decimal("0.15") if targets else 0
    issues = sanity_check(p)
    if issues:
        conf -= Decimal("0.45")
        p.warnings.extend(issues)
    if assumed_side:
        conf -= Decimal("0.1")
        p.warnings.append("no BUY/SELL word; assumed BUY for an option call")
    if sl is None:
        p.warnings.append("no stop loss given")
    p.confidence = max(Decimal("0"), min(conf, Decimal("0.95")))
    return p

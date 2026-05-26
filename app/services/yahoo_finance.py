"""
Yahoo Finance API service via yfinance.

yfinance handles cookie/crumb authentication automatically,
avoiding 401 Unauthorized errors from direct API calls.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf


YAHOO_RANGE_MAP = {
    "5d":  ("5d",   "5m"),
    "1mo": ("1mo",  "30m"),
    "3mo": ("3mo",  "daily"),
    "6mo": ("6mo",  "daily"),
    "1y":  ("1y",   "daily"),
}


def board_from_ticker(ticker: str) -> str:
    """Return TWSE or TPEx based on suffix."""
    if ticker.endswith(".TWO"):
        return "TPEx"
    return "TWSE"


def _resolve_yf(symbol: str) -> str:
    """Resolve a 4-digit Taiwan code to full Yahoo ticker."""
    s = symbol.strip().upper()
    if s.endswith(".TW") or s.endswith(".TWO"):
        return s
    if s.isdigit() and len(s) == 4:
        t = yf.Ticker(f"{s}.TW")
        try:
            if t.info and t.info.get("regularMarketPrice") is not None:
                return f"{s}.TW"
        except Exception:
            pass
        return f"{s}.TWO"
    return s


@dataclass
class Quote:
    symbol:       str
    board:        str
    name:         str
    price:        float
    change:       float
    change_pct:   float
    open:         Optional[float]
    high:         Optional[float]
    low:          Optional[float]
    prev_close:   Optional[float]
    volume:       Optional[int]
    pe_ratio:     Optional[float]
    pb_ratio:     Optional[float]


@dataclass
class ChartData:
    symbol:    str
    board:     str
    timestamps: list[int]       # Unix seconds
    opens:     list[float]
    highs:     list[float]
    lows:      list[float]
    closes:    list[float]
    volumes:   list[int]
    ma5:       list[Optional[float]]
    ma20:      list[Optional[float]]
    ma60:      list[Optional[float]]
    kd_k:      list[Optional[float]]
    kd_d:      list[Optional[float]]
    rsi_6:     list[Optional[float]]
    rsi_12:    list[Optional[float]]


# ── KD calculation ───────────────────────────────────────────────────────

def _calc_kd(closes: list[float], period: int = 9) -> tuple[list[Optional[float]], list[Optional[float]]]:
    k_list, d_list = [], []
    k_val, d_val = 50.0, 50.0
    for i in range(len(closes)):
        if i < period - 1:
            k_list.append(None)
            d_list.append(None)
            continue
        lowest_low  = min(closes[i - period + 1 : i + 1])
        highest_high = max(closes[i - period + 1 : i + 1])
        rsv = (closes[i] - lowest_low) / (highest_high - lowest_low) * 100 if highest_high != lowest_low else 50
        k_val = k_val * 2/3 + rsv * 1/3
        d_val = d_val * 2/3 + k_val * 1/3
        k_list.append(round(k_val, 2))
        d_list.append(round(d_val, 2))
    return k_list, d_list


def _calc_rsi(closes: list[float], period: int) -> list[Optional[float]]:
    if len(closes) < period + 1:
        return [None] * len(closes)
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    if not gains:
        return [None] * len(closes)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi = [None] * (period + 1)
    for i in range(period, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsi.append(round(100 - 100 / (1 + rs), 2))
    return rsi


def _calc_ma(values: list[float], period: int) -> list[Optional[float]]:
    result = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(round(sum(values[i - period + 1 : i + 1]) / period, 2))
    return result


# ── Public API ────────────────────────────────────────────────────────────

async def get_quote(symbol: str) -> Optional[Quote]:
    """Fetch a single quote. Returns None if not found."""
    resolved = _resolve_yf(symbol)
    ticker = yf.Ticker(resolved)

    try:
        info = ticker.info
        if not info or info.get("regularMarketPrice") is None:
            return None
    except Exception:
        return None

    price      = info.get("regularMarketPrice") or 0
    prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose") or price
    change     = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0

    return Quote(
        symbol     = resolved,
        board      = board_from_ticker(resolved),
        name       = info.get("shortName") or info.get("longName") or resolved,
        price      = float(price),
        change     = round(float(change), 2),
        change_pct = round(float(change_pct), 2),
        open       = _to_float(info.get("regularMarketOpen")),
        high       = _to_float(info.get("regularMarketDayHigh")),
        low        = _to_float(info.get("regularMarketDayLow")),
        prev_close = _to_float(prev_close),
        volume     = _to_int(info.get("regularMarketVolume")),
        pe_ratio   = _to_float(info.get("trailingPE")),
        pb_ratio   = _to_float(info.get("priceToBook")),
    )


async def get_chart(symbol: str, range_key: str = "3mo") -> Optional[ChartData]:
    """
    Fetch OHLCV + indicators (MA5/20/60, KD, RSI6/12) for a symbol.
    Uses yfinance history() which handles crumb auth automatically.
    """
    resolved = _resolve_yf(symbol)
    yf_range, yf_interval = YAHOO_RANGE_MAP.get(range_key, ("3mo", "daily"))

    ticker = yf.Ticker(resolved)
    try:
        hist = ticker.history(range=yf_range, interval=yf_interval)
        if hist is None or hist.empty:
            return None
    except Exception:
        return None

    closes   = [float(c) for c in hist["Close"]]
    opens    = [float(o) for o in hist["Open"]]
    highs    = [float(h) for h in hist["High"]]
    lows     = [float(l) for l in hist["Low"]]
    volumes  = [int(v)   for v in hist["Volume"]]
    # Convert timestamps to Unix seconds (UTC)
    timestamps = [int(ts.timestamp()) for ts in hist.index]

    return ChartData(
        symbol    = resolved,
        board     = board_from_ticker(resolved),
        timestamps = timestamps,
        opens     = opens,
        highs     = highs,
        lows      = lows,
        closes    = closes,
        volumes   = volumes,
        ma5       = _calc_ma(closes, 5),
        ma20      = _calc_ma(closes, 20),
        ma60      = _calc_ma(closes, 60) if len(closes) >= 60 else [None] * len(closes),
        kd_k      = _calc_kd(closes)[0],
        kd_d      = _calc_kd(closes)[1],
        rsi_6     = _calc_rsi(closes, 6),
        rsi_12    = _calc_rsi(closes, 12),
    )


def search_stocks(q: str) -> list[dict]:
    """
    Basic prefix search against a known stock list.
    For production: query Yahoo Finance /api/v1/finance/search
    """
    KNOWN_STOCKS = {
        "2330": "台積電 (2330)",
        "2317": "鴻海 (2317)",
        "2454": "聯發科 (2454)",
        "3008": "大立光 (3008)",
        "2412": "中華電 (2412)",
        "2881": "富邦金 (2881)",
        "2882": "國泰金 (2882)",
        "2891": "中信金 (2891)",
        "2892": "第一金 (2892)",
        "2002": "中鋼 (2002)",
        "1215": "卜蜂 (1215)",
        "1303": "南亞 (1303)",
        "1326": "台化 (1326)",
        "1718": "中纖 (1718)",
        "2618": "長榮航 (2618)",
        "2610": "華航 (2610)",
        "3034": "聯詠 (3034)",
        "3035": "智原 (3035)",
        "3443": "創意 (3443)",
        "6515": "慧穎 (6515)",
        "6552": "展達 (6552)",
        "8107": "大富 (8107)",
        "8131": "上銀 (8131)",
        "3081": "聯亞 (3081)",
    }

    q = q.strip().upper()
    results = []
    for code, name in KNOWN_STOCKS.items():
        if code.startswith(q):
            results.append({"code": code, "name": name})
        if len(results) >= 10:
            break

    return results


# ── Helpers ────────────────────────────────────────────────────────────────

def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
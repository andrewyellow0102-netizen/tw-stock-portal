"""
Yahoo Finance API service.

Symbol resolution:
- 4-digit numeric → try .TW (TWSE/上市), then .TWO (TPEx/上櫃)
- Already-suffixed → use as-is
- US symbols → use as-is
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import httpx


YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 10.0  # seconds


def to_yahoo_ticker(symbol: str) -> list[str]:
    """Return list of Yahoo ticker suffixes to try for a given symbol."""
    s = symbol.strip().upper()
    # Already has suffix
    if s.endswith(".TW") or s.endswith(".TWO"):
        return [s]
    # 4-digit Taiwan stock code
    if s.isdigit() and len(s) == 4:
        return [f"{s}.TW", f"{s}.TWO"]
    # US / other — as-is
    return [s]


def board_from_ticker(ticker: str) -> str:
    """Return TWSE or TPEx based on suffix."""
    if ticker.endswith(".TWO"):
        return "TPEx"
    return "TWSE"


@dataclass
class Quote:
    symbol: str          # e.g. "2330.TW"
    board: str           # "TWSE" or "TPEx"
    name: str
    price: float
    change: float
    change_pct: float
    open: float
    high: float
    low: float
    prev_close: float
    volume: int
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]


async def get_quote(symbol: str) -> Quote | None:
    """
    Fetch a real-time quote for the given symbol.
    Tries .TW first, falls back to .TWO if 404.
    Returns None if the symbol cannot be resolved.
    """
    tickers = to_yahoo_ticker(symbol)
    last_error = None

    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT) as client:
        for ticker in tickers:
            try:
                url = f"{YAHOO_BASE}/{ticker}?interval=1d&range=1d"
                resp = await client.get(url)
                if resp.status_code == 404:
                    last_error = f"{ticker} not found"
                    continue
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as e:
                last_error = str(e)
                continue

            result = data["chart"]["result"]
            if not result:
                last_error = "empty result"
                continue

            meta = result[0]["meta"]
            price = meta.get("regularMarketPrice")
            if price is None:
                last_error = "no price data"
                continue

            prev = meta.get("chartPreviousClose", price)
            change = round(price - prev, 2)
            change_pct = round(change / prev * 100, 2) if prev else 0.0

            # Extract shortName or derive from symbol
            name = meta.get("shortName") or meta.get("symbol", symbol)

            # Financial ratios (may be null)
            # Yahoo doesn't expose PE/PB in chart meta — leave None for now
            # We'll populate from the quote endpoint if available
            pe_ratio = None
            pb_ratio = None

            # Try to get PE from the quote endpoint
            quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
            try:
                r2 = await client.get(quote_url)
                if r2.status_code == 200:
                    qdata = r2.json()
                    qt = qdata.get("quoteResponse", {}).get("result", [{}])
                    if qt:
                        pe_ratio = qt[0].get("trailingPE")
                        pb_ratio = qt[0].get("priceToBook")
            except Exception:
                pass  # PE/PB are best-effort

            return Quote(
                symbol=ticker,
                board=board_from_ticker(ticker),
                name=name,
                price=price,
                change=change,
                change_pct=change_pct,
                open=meta.get("regularMarketOpen", price),
                high=meta.get("regularMarketDayHigh", price),
                low=meta.get("regularMarketDayLow", price),
                prev_close=prev,
                volume=meta.get("regularMarketVolume", 0),
                pe_ratio=pe_ratio,
                pb_ratio=pb_ratio,
            )

    # All tickers failed
    return None


async def get_ohlc(
    symbol: str,
    interval: str = "1d",
    range_: str = "3mo",
) -> Optional[dict]:
    """
    Fetch OHLC candle data with technical indicators.
    Returns dict with candles, ma5, ma20, ma60, kd_k, kd_d, rsi_6, rsi_12.
    """
    tickers = to_yahoo_ticker(symbol)

    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT) as client:
        for ticker in tickers:
            try:
                url = f"{YAHOO_BASE}/{ticker}?interval={interval}&range={range_}"
                resp = await client.get(url)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError:
                continue

            result = data.get("chart", {}).get("result")
            if not result:
                continue

            r = result[0]
            timestamps = r.get("timestamp", [])
            quote = r.get("indicators", {}).get("quote", [{}])[0]

            opens  = quote.get("open", [])
            highs  = quote.get("high", [])
            lows   = quote.get("low", [])
            closes = quote.get("close", [])
            vols   = quote.get("volume", [])

            if not closes:
                continue

            candles = []
            for i, ts in enumerate(timestamps):
                candles.append({
                    "date":  ts,
                    "open":   opens[i]  if i < len(opens)  and opens[i]  is not None else None,
                    "high":   highs[i]  if i < len(highs)  and highs[i]  is not None else None,
                    "low":    lows[i]   if i < len(lows)   and lows[i]   is not None else None,
                    "close":  closes[i] if i < len(closes) and closes[i] is not None else None,
                    "volume": vols[i]   if i < len(vols)   and vols[i]   is not None else 0,
                })

            # Compute technical indicators
            closes_clean = [c for c in closes if c is not None]
            ma5   = _ma(closes, 5)
            ma20  = _ma(closes, 20)
            ma60  = _ma(closes, 60)
            kd_k, kd_d = _kd(closes)
            rsi6  = _rsi(closes, 6)
            rsi12 = _rsi(closes, 12)

            return {
                "symbol":  ticker,
                "board":   board_from_ticker(ticker),
                "candles": candles,
                "ma5":     ma5,
                "ma20":    ma20,
                "ma60":    ma60,
                "kd_k":    kd_k,
                "kd_d":    kd_d,
                "rsi_6":   rsi6,
                "rsi_12":  rsi12,
            }

    return None


# ── Technical indicator helpers ────────────────────────────────────────────

def _ma(closes: list, n: int) -> list:
    """Simple moving average, same length as closes, padding front with null."""
    result = [None] * len(closes)
    if len(closes) < n:
        return result
    for i in range(n - 1, len(closes)):
        vals = closes[i - n + 1 : i + 1]
        if None not in vals:
            result[i] = round(sum(vals) / n, 2)
    return result


def _kd(closes: list, n: int = 9) -> tuple[list, list]:
    """K and D values. Returns two same-length lists, front padded with null."""
    k = [None] * len(closes)
    d = [None] * len(closes)
    if len(closes) < n:
        return k, d

    # RSV for each day
    rsv = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        window = closes[i - n + 1 : i + 1]
        if None in window:
            continue
        low_min  = min(window)
        high_max = max(window)
        if high_max == low_min:
            rsv[i] = 50.0
        else:
            rsv[i] = (closes[i] - low_min) / (high_max - low_min) * 100

    # K = 2/3 prev K + 1/3 RSV, D = 2/3 prev D + 1/3 K
    k_val, d_val = 50.0, 50.0
    for i in range(n - 1, len(closes)):
        if rsv[i] is None:
            continue
        k_val = 2 / 3 * k_val + 1 / 3 * rsv[i]
        d_val = 2 / 3 * d_val + 1 / 3 * k_val
        k[i] = round(k_val, 2)
        d[i] = round(d_val, 2)

    return k, d


def _rsi(closes: list, n: int = 14) -> list:
    """RSI with period n. Returns same-length list, front padded with null."""
    result = [None] * len(closes)
    if len(closes) < n + 1:
        return result

    gains, losses = [], []
    for i in range(1, len(closes)):
        c = closes[i]
        p = closes[i - 1]
        if c is None or p is None:
            gains.append(None)
            losses.append(None)
            continue
        diff = c - p
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    for i in range(n, len(closes)):
        window_g = gains[i - n : i]
        window_l = losses[i - n : i]
        if None in window_g or None in window_l:
            continue
        avg_g = sum(window_g) / n
        avg_l = sum(window_l) / n
        if avg_l == 0:
            result[i] = 100.0
        else:
            rs = avg_g / avg_l
            result[i] = round(100 - 100 / (1 + rs), 2)

    return result
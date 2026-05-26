"""
Fundamentals service — key financial ratios via yfinance.

yfinance handles Yahoo Finance cookie/crumb authentication automatically.
"""

from __future__ import annotations

from typing import Optional

import yfinance as yf


def _resolve_symbol(symbol: str) -> str:
    """Normalize symbol for Yahoo Finance."""
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


def _py(val):
    """Convert numpy types to native Python, skip NaN."""
    if val is None:
        return None
    try:
        import numpy as np
        if isinstance(val, (np.integer, np.floating)):
            val = float(val)
            if np.isnan(val) or np.isinf(val):
                return None
    except Exception:
        pass
    try:
        f = float(val)
        import math
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


async def get_fundamentals(symbol: str) -> Optional[dict]:
    """
    Fetch key fundamental data for a Taiwan stock using yfinance.
    Returns EPS (trailing), book value, PE, ROE, debt ratio.
    """
    resolved = _resolve_symbol(symbol)
    ticker = yf.Ticker(resolved)

    try:
        info = ticker.info
        if not info or info.get("regularMarketPrice") is None:
            return None
    except Exception:
        return None

    # Board
    board = "TWSE" if resolved.endswith(".TW") else "TPEx" if resolved.endswith(".TWO") else "US"

    # Use trailing EPS from Yahoo (already calculated)
    trailing_eps = _py(info.get("trailingEps"))

    # Get quarterly EPS from financials
    eps_history = []
    try:
        financials = ticker.quarterly_financials
        if financials is not None and not financials.empty:
            for date_col in financials.columns[:8]:
                row = financials[date_col]
                ni = row.get("Net Income") or row.get("Net Income From Continuing Operation")
                if ni is None:
                    continue
                ni_val = _py(ni)
                if ni_val is None:
                    continue
                # shares outstanding (in millions) from info
                shares = _py(info.get("sharesOutstanding")) or 1
                if shares <= 0:
                    shares = 1
                # EPS = Net Income (TWD) / Shares Outstanding
                eps = ni_val / shares
                quarter = date_col.strftime("%Y") + "Q" + str(date_col.quarter) if hasattr(date_col, "quarter") else str(date_col)[:4]
                eps_rounded = round(eps, 2)
                # skip implausibly small values (likely bad data)
                if abs(eps_rounded) > 0.001 or eps_rounded == 0:
                    eps_history.append({"quarter": quarter, "eps": eps_rounded})
    except Exception:
        pass

    # Key ratios
    book_value    = _py(info.get("bookValue"))
    roe           = _py(info.get("returnOnEquity"))
    debt_ratio    = None

    try:
        balance = ticker.quarterly_balance_sheet
        if balance is not None and not balance.empty:
            for col in balance.columns[:2]:
                try:
                    ta = _py(balance.loc["Total Assets"].iloc[0]) if "Total Assets" in balance.index else None
                    tl = _py(balance.loc["Total Liabilities"].iloc[0]) if "Total Liabilities" in balance.index else None
                    if ta and ta > 0 and tl is not None:
                        debt_ratio = round((tl / ta) * 100, 2)
                        break
                except Exception:
                    continue
    except Exception:
        pass

    return {
        "symbol":               resolved,
        "board":                board,
        "trailing_eps":         trailing_eps,
        "eps_history":          eps_history,
        "book_value_per_share": book_value,
        "roe":                  round(roe * 100, 2) if roe else None,
        "debt_ratio":           debt_ratio,
    }
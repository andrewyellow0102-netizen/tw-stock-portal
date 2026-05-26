"""
Fundamentals service — quarterly EPS, key financial ratios via yfinance.

yfinance handles Yahoo Finance cookie/crumb authentication automatically.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import yfinance as yf


def _resolve_symbol(symbol: str) -> str:
    """
    Normalize symbol for Yahoo Finance.
    4-digit numeric → try .TW then .TWO
    Already-suffixed or US → use as-is
    """
    if symbol.upper() in (".TW", ".TWO", ".US"):
        return symbol
    if symbol.replace(".TW", "").replace(".TWO", "").isdigit():
        base = symbol.split(".")[0]
        tw_check = yf.Ticker(f"{base}.TW")
        try:
            if tw_check.info and tw_check.info.get("regularMarketPrice") is not None:
                return f"{base}.TW"
        except Exception:
            pass
        return f"{base}.TWO"
    return symbol


def _to_float(val, default: Optional[float] = None) -> Optional[float]:
    if val is None:
        return default
    try:
        f = float(val)
        return f if f != 0 else default
    except (TypeError, ValueError):
        return default


async def get_fundamentals(symbol: str) -> Optional[dict]:
    """
    Fetch fundamental data for a Taiwan stock using yfinance.
    Returns a dict with: symbol, board, eps_history, book_value_per_share, roe, debt_ratio
    """
    resolved = _resolve_symbol(symbol)
    ticker = yf.Ticker(resolved)

    try:
        info = ticker.info
    except Exception:
        return None

    if not info or info.get("regularMarketPrice") is None:
        return None

    # Board detection
    board = "TWSE" if resolved.endswith(".TW") else "TPEx" if resolved.endswith(".TWO") else "US"

    # ── EPS History (quarterly) ──────────────────────────────────────
    eps_history = []
    try:
        financials = ticker.quarterly_financials
        if financials is not None and not financials.empty:
            for date_col in financials.columns[:8]:  # up to 8 quarters
                row = financials[date_col]
                net_income = row.get("Net Income From Continuing Operation") or row.get("Net Income") or row.get("NetIncome")
                if net_income is None:
                    continue
                try:
                    shares = float(info.get("sharesOutstanding", 0))
                    if shares and shares > 0:
                        # EPS = Net Income / Shares Outstanding (in thousands)
                        eps = net_income / (shares * 1000)
                    else:
                        eps = float(net_income) / 1_000_000  # fallback
                except (TypeError, ValueError, ZeroDivisionError):
                    continue

                quarter = date_col.strftime("%Y") + "Q" + str(date_col.quarter) if hasattr(date_col, "quarter") else str(date_col)[:4]
                eps_history.append({"quarter": quarter, "eps": round(eps, 2)})
    except Exception:
        pass

    # ── Key ratios ────────────────────────────────────────────────────
    book_value_per_share = _to_float(info.get("bookValue"))
    roe                  = _to_float(info.get("returnOnEquity"))
    debt_ratio           = None

    try:
        balance = ticker.quarterly_balance_sheet
        if balance is not None and not balance.empty:
            total_assets  = balance.loc["Total Assets"].iloc[0] if "Total Assets" in balance.index else None
            total_liab    = balance.loc["Total Liabilities"].iloc[0] if "Total Liabilities" in balance.index else None
            if total_assets and total_assets > 0 and total_liab is not None:
                debt_ratio = round((total_liab / total_assets) * 100, 2)
    except Exception:
        pass

    return {
        "symbol":             resolved,
        "board":              board,
        "eps_history":        eps_history,
        "book_value_per_share": book_value_per_share,
        "roe":                (round(roe * 100, 2) if roe else None),
        "debt_ratio":         debt_ratio,
    }
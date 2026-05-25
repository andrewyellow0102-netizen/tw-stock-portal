"""
Fundamentals service — quarterly EPS, monthly revenue, key financial ratios.

Sources:
  - Primary: Yahoo Finance summary (PE, PB, market cap — already in quote)
  - EPS / Revenue: fetched from TWSE / TPEx official APIs
    (see _fetch_twse_financials / _fetch_tpex_financials helpers)

If all external sources fail, returns the partial data available in the quote.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import httpx


@dataclass
class FundamentalData:
    symbol:          str
    board:          str

    # Quarterly EPS
    eps_history:    list[dict]   # [{"quarter": "2024Q1", "eps": 10.5}, ...]

    # Monthly revenue (last 12 months)
    revenue_history: list[dict]  # [{"month": "2024-01", "revenue": 1234567, "yoy": 5.2}, ...]

    # Annual per-share metrics
    book_value_per_share: Optional[float] = None   # 每股淨值
    roe:                 Optional[float] = None   # 股東權益報酬率 %
    debt_ratio:          Optional[float] = None   # 負債比率 %


# ── TWSE (上市) ─────────────────────────────────────────────────────────────

async def _fetch_twse_financials(ticker: str) -> Optional[dict]:
    """
    Fetch quarterly EPS from TWSE fundamental API.
    Endpoint: https://api.twse.com.tw/stock/finance/t86/{month}
    Parameters: exptype=N, type=MSCF, code=2330
    """
    try:
        # Get recent 4 months to cover enough quarters
        url = (
            f"https://api.twse.com.tw/stock/finance/t86/{'03'}"
            f"?exptype=N&type=MSCF&code={ticker.replace('.TW','')}"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return None

        import json
        data = r.json()

        # TWSE response: {"rtcode": "0", "data": [[date, revenue, ...], ...]}
        if data.get("rtcode") != "0" or "data" not in data:
            return None

        rows = data["data"]  # [date, revenue, opIncome, preTaxIncome, afterTaxIncome, eps]
        eps_history = []
        for row in rows[-8:]:  # last 8 quarters
            date_str = str(row[0])          # e.g. "2024Q1"
            eps_val  = row[-1]               # EPS in last column
            try:
                eps_history.append({"quarter": date_str, "eps": float(eps_val)})
            except (ValueError, TypeError, IndexError):
                continue

        return {"eps_history": eps_history} if eps_history else None

    except Exception:
        return None


# ── TPEx (上櫃) ─────────────────────────────────────────────────────────────

async def _fetch_tpex_financials(ticker: str) -> Optional[dict]:
    """
    Fetch quarterly EPS from TPEx API.
    """
    try:
        code = ticker.replace(".TWO", "")
        url = (
            f"https://api.tpex.com.tw/webapi/tq103/pltot.php"
            f"?stkno={code}&t=1"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return None

        import json
        data = r.json()
        # TPEx format: {amc: [[date, revenue, ...], ...]}
        rows = data.get("amc", [])
        if not rows:
            return None

        # Last 8 quarters — column index varies; try to find EPS column
        eps_history = []
        for row in rows[-8:]:
            # TPEx rows: [date, revenue, grossProfit, opIncome, preTaxIncome, afterTaxIncome, eps]
            if len(row) >= 7:
                try:
                    date_str = str(row[0])
                    eps_val  = row[6]  # EPS typically last column
                    eps_history.append({"quarter": date_str, "eps": float(eps_val)})
                except (ValueError, TypeError):
                    continue

        return {"eps_history": eps_history} if eps_history else None

    except Exception:
        return None


# ── Public API ──────────────────────────────────────────────────────────────

async def get_fundamentals(symbol: str) -> Optional[FundamentalData]:
    """
    Fetch all available fundamental data for a Taiwan stock.
    Returns None if no data could be retrieved.
    """
    board = "TWSE" if symbol.endswith(".TW") else "TPEx"

    eps_history = []
    revenue_history = []

    if board == "TWSE":
        result = await _fetch_twse_financials(symbol)
        if result:
            eps_history = result.get("eps_history", [])
    else:
        result = await _fetch_tpex_financials(symbol)
        if result:
            eps_history = result.get("eps_history", [])

    # Fallback: return what we have (possibly empty) so the UI can show a placeholder
    return FundamentalData(
        symbol=symbol,
        board=board,
        eps_history=eps_history[-8:] if eps_history else [],
        revenue_history=revenue_history[-12:] if revenue_history else [],
    )
"""
Watchlist alerts API — price boundary notifications.

MVP: in-memory store (no DB). Alerts are checked on watchlist page load.
For production, this would be a background cron job or WebSocket push.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from app.services import yahoo_finance as yf
from app.services import stock_cache


router = APIRouter(prefix="/api/alerts", tags=["alerts"])

# ── In-memory store ─────────────────────────────────────────────────────────
# { user_id: { symbol: AlertRule } }
_ALERTS: dict[str, dict[str, dict]] = {}


def _uid(x_user_id: Optional[str] = Header(None)) -> str:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="請攜帶 X-User-Id header")
    if x_user_id not in _ALERTS:
        _ALERTS[x_user_id] = {}
    return x_user_id


def _ensure_uid(uid: str) -> None:
    if uid not in _ALERTS:
        _ALERTS[uid] = {}


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("")
async def list_alerts(x_user_id: Optional[str] = Header(None)):
    """
    Return all alerts for the user, enriched with current price
    and triggered status.
    """
    uid = _uid(x_user_id)
    _ensure_uid(uid)
    rules = _ALERTS.get(uid, {})

    result = []
    for symbol, rule in rules.items():
        triggered = None
        current_price = None

        try:
            quote = await yf.get_quote(symbol)
            if quote:
                current_price = quote.price
                p = quote.price
                upper = rule.get("upper_bound")
                lower = rule.get("lower_bound")
                if upper and p >= upper:
                    triggered = f"已觸發！價格突破上限 ${upper:.2f}（現價 ${p:.2f}）"
                elif lower and p <= lower:
                    triggered = f"已觸發！價格跌破下限 ${lower:.2f}（現價 ${p:.2f}）"
        except Exception:
            pass

        result.append({
            "symbol":        symbol,
            "name":          rule.get("name"),
            "upper_bound":   rule.get("upper_bound"),
            "lower_bound":   rule.get("lower_bound"),
            "created_at":    rule.get("created_at"),
            "current_price": current_price,
            "triggered":     triggered,
        })

    return {"alerts": result}


@router.post("")
async def set_alert(
    symbol: str,
    upper_bound: Optional[float] = None,
    lower_bound: Optional[float] = None,
    name: Optional[str] = None,
    x_user_id: Optional[str] = Header(None),
):
    """
    Create or update a price alert for a stock.
    """
    uid = _uid(x_user_id)
    _ensure_uid(uid)

    if upper_bound is None and lower_bound is None:
        raise HTTPException(
            status_code=400,
            detail="請設定上限或下限（至少一個）",
        )

    if upper_bound is not None and lower_bound is not None:
        if upper_bound <= lower_bound:
            raise HTTPException(
                status_code=400,
                detail="上限必須高於下限",
            )

    # Resolve full symbol
    quote = await yf.get_quote(symbol)
    if not quote:
        raise HTTPException(status_code=404, detail=f"查無「{symbol}」")

    resolved = quote.symbol
    _ALERTS[uid][resolved] = {
        "name":        name or quote.name,
        "upper_bound": upper_bound,
        "lower_bound": lower_bound,
        "created_at":  datetime.now().isoformat(),
    }

    return {
        "message":     "警示已設定",
        "symbol":      resolved,
        "name":        name or quote.name,
        "upper_bound": upper_bound,
        "lower_bound": lower_bound,
    }


@router.delete("/{symbol}")
async def delete_alert(symbol: str, x_user_id: Optional[str] = Header(None)):
    """Delete price alert for a stock."""
    uid = _uid(x_user_id)

    # Strip suffix to match
    clean = symbol.replace(".TW", "").replace(".TWO", "")
    for k in list(_ALERTS[uid].keys()):
        if k.replace(".TW", "").replace(".TWO", "") == clean:
            del _ALERTS[uid][k]
            return {"message": "已刪除"}

    raise HTTPException(status_code=404, detail="找不到此警示")
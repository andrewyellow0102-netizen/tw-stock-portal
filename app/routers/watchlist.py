"""
Watchlist API endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from app.services import yahoo_finance as yf
from app.services import stock_cache


router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

# ── In-memory store (MVP — no DB setup required) ──────────────────────────
# Structure: {user_id: list[WatchlistEntry]}
_WATCHLIST: dict[str, list[dict]] = {}


def _get_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    """MVP: user identified by X-User-Id header. No real auth."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="請攜帶 X-User-Id header（見登入功能施工中提示）")
    return x_user_id


def _ensure_user(uid: str) -> None:
    if uid not in _WATCHLIST:
        _WATCHLIST[uid] = []


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("")
async def get_watchlist(x_user_id: Optional[str] = Header(None)):
    """
    Return the user's watchlist, enriched with live quotes.
    """
    uid = _get_user_id(x_user_id)
    _ensure_user(uid)

    items = _WATCHLIST.get(uid, [])
    result = []
    for item in items:
        # Fetch live quote
        cache_key = f"quote:{item['symbol']}"
        cached = stock_cache.get_quote_cached(cache_key)
        if cached:
            q = cached
        else:
            quote = await yf.get_quote(item["symbol"])
            if quote:
                q = {
                    "symbol":     quote.symbol,
                    "board":      quote.board,
                    "name":       quote.name,
                    "price":      quote.price,
                    "change":     quote.change,
                    "change_pct": quote.change_pct,
                }
                stock_cache.set_quote_cached(cache_key, q)
            else:
                q = {"symbol": item["symbol"], "name": item.get("nickname") or item["symbol"],
                     "price": None, "change": None, "change_pct": None, "board": None}

        result.append({
            "symbol":   item["symbol"],
            "nickname": item.get("nickname"),
            "added_at": item.get("added_at"),
            **q,
        })

    return {"items": result}


@router.post("")
async def add_to_watchlist(
    symbol: str,
    nickname: Optional[str] = None,
    x_user_id: Optional[str] = Header(None),
):
    """
    Add a stock to the watchlist.
    """
    uid = _get_user_id(x_user_id)
    _ensure_user(uid)

    # Resolve full symbol first
    quote = await yf.get_quote(symbol)
    if not quote:
        raise HTTPException(status_code=404, detail=f"查無此股票「{symbol}」，請確認代碼是否正確")

    resolved = quote.symbol
    items = _WATCHLIST[uid]

    # Duplicate check
    if any(i["symbol"] == resolved for i in items):
        return {"message": "已存在", "symbol": resolved}

    items.append({
        "symbol":    resolved,
        "nickname":  nickname,
        "added_at":  datetime.now().isoformat(),
    })

    return {"message": "已加入", "symbol": resolved, "nickname": nickname}


@router.delete("/{symbol}")
async def remove_from_watchlist(
    symbol: str,
    x_user_id: Optional[str] = Header(None),
):
    """
    Remove a stock from the watchlist.
    """
    uid = _get_user_id(x_user_id)
    if uid not in _WATCHLIST:
        raise HTTPException(status_code=404, detail="自選股清單為空")

    items = _WATCHLIST[uid]
    original_len = len(items)

    # Try exact symbol first, then strip suffix
    items[:] = [i for i in items if i["symbol"] != symbol and i["symbol"].replace(".TW","").replace(".TWO","") != symbol.replace(".TW","").replace(".TWO","")]

    if len(items) == original_len:
        raise HTTPException(status_code=404, detail="找不到此股票")

    return {"message": "已移除"}
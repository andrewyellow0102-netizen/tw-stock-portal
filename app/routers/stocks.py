"""
Stock API endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.services import yahoo_finance as yf
from app.services import stock_cache


router = APIRouter(prefix="/api", tags=["stocks"])


@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    """
    Get a real-time quote for a Taiwan stock symbol.
    Automatically resolves .TW / .TWO based on availability.
    """
    cache_key = f"quote:{symbol}"
    cached = stock_cache.get_quote_cached(cache_key)
    if cached is not None:
        return cached

    quote = await yf.get_quote(symbol)
    if quote is None:
        raise HTTPException(
            status_code=404,
            detail=f"查無此股票「{symbol}」，請確認代碼是否正確。",
        )

    result = {
        "symbol":     quote.symbol,
        "board":      quote.board,
        "name":       quote.name,
        "price":      quote.price,
        "change":     quote.change,
        "change_pct": quote.change_pct,
        "open":       quote.open,
        "high":       quote.high,
        "low":        quote.low,
        "prev_close": quote.prev_close,
        "volume":     quote.volume,
        "pe_ratio":   quote.pe_ratio,
        "pb_ratio":   quote.pb_ratio,
    }

    stock_cache.set_quote_cached(cache_key, result)
    return result


@router.get("/chart/{symbol}")
async def get_chart(
    symbol: str,
    interval: str = Query("1d", description="Chart interval: 1d, 1wk, 1mo"),
    range_: str = Query("3mo", description="Data range: 5d, 1mo, 3mo, 6mo, 1y"),
):
    """
    Get OHLC candle data with pre-computed technical indicators.
    """
    cache_key = f"chart:{symbol}:{interval}:{range_}"
    cached = stock_cache.get_ohlc_cached(cache_key)
    if cached is not None:
        return cached

    data = await yf.get_ohlc(symbol, interval=interval, range_=range_)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"查無此股票「{symbol}」的圖表資料，請確認代碼是否正確。",
        )

    stock_cache.set_ohlc_cached(cache_key, data)
    return data


@router.get("/search")
async def search(q: str = Query(..., min_length=1, description="Stock code or name")):
    """
    Simple stock search. Returns matching Taiwan stocks by code prefix.
    For MVP this is a local list; production would call a search API.
    """
    # Common Taiwan stocks for MVP search
    KNOWN_STOCKS = {
        "2330": "台積電 (2330)",
        "2317": "鴻海 (2317)",
        "2454": "聯發科 (2454)",
        "2603": "長榮 (2603)",
        "2615": "萬海 (2615)",
        "2609": "陽明 (2609)",
        "2002": "中鋼 (2002)",
        "1215": "卜蜂 (1215)",
        "1216": "統一 (1216)",
        "2881": "富邦金 (2881)",
        "2882": "國泰金 (2882)",
        "2891": "中信金 (2891)",
        "5871": "中租-KY (5871)",
        "6505": "聯淳 (6505)",
        "6415": "矽力-KY (6415)",
        "3034": "聯詠 (3034)",
        "2379": "瑞昱 (2379)",
        "2458": "義隆 (2458)",
        "4958": "臻鼎-KY (4958)",
        "3481": "群創 (3481)",
        "2408": "友達 (2408)",
        "2474": "可成 (2474)",
        "3661": "世芯-KY (3661)",
        "3131": "弘塑 (3131)",
        "3081": "聯亞 (3081)",
        "6274": "台虹 (6274)",
        "6443": "元晶 (6443)",
        "6515": "慧穎 (6515)",
        "6552": "展達 (6552)",
        "8107": "大富 (8107)",
        "8131": "上銀 (8131)",
    }

    q = q.strip().upper()
    results = []
    for code, name in KNOWN_STOCKS.items():
        if code.startswith(q):
            results.append({"code": code, "name": name})
        if len(results) >= 10:
            break

    return {"query": q, "results": results}
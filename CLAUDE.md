# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

台股分析站台（TW Stock Portal）— 提供台股（上市/櫃買）的技術分析、報價查詢、圖表視覺化功能。

**Repo:** https://github.com/andrewyellow0102-netizen/tw-stock-portal

## Tech Stack

- **Backend**: Python 3 + FastAPI
- **Frontend**: 純 HTML + CSS + JavaScript（無框架）
- **Charts**: Chart.js 4.x
- **Data source**: Yahoo Finance Chart API（免費，無需 API Key）
- **部署**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# 開啟 http://localhost:8000
```

## Project Structure

```
app/
├── main.py              # FastAPI 應用程式
├── routers/
│   └── stocks.py        # API routes：/api/quote, /api/chart, /api/search
└── services/
    ├── yahoo_finance.py # Yahoo Finance API 包裝（含 TW→TWO fallback）
    └── stock_cache.py   # TTL 快取（60s 報價、30min K線）

frontend/
├── index.html           # 首頁/搜尋
├── stock.html          # 個股頁面（報價 + 圖表）
└── watchlist.html       # 自選股頁面（施工中）
```

## Domain Rules

### Symbol 解析
- 4碼數字 → 先查 `.TW`（上市），404後查 `.TWO`（上櫃）
- 上櫃股票（如 3081）只存在 `.TWO`，沒有 fallback 會 404
- Yahoo Finance URL: `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`

### API 回應格式

```
GET /api/quote/{symbol}
→ {symbol, board, name, price, change, change_pct, open, high, low, prev_close, volume, pe_ratio, pb_ratio}

GET /api/chart/{symbol}?range_=3mo
→ {symbol, board, candles[], ma5[], ma20[], ma60[], kd_k[], kd_d[], rsi_6[], rsi_12[]}
```

### 技術指標（後端計算）
- MA(n)：N日簡單移動平均
- KD：參數 9 日，K=RSV的3日均線，D=K的3日均線
- RSI：RSI(n)，n 可為 6 或 12

### 快取策略
- 報價快取：60 秒 TTL
- K線快取：30 分鐘 TTL

## Agent Skills

### Issue tracker

GitHub Issues in andrewyellow0102-netizen/tw-stock-portal. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary — `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — one `CONTEXT.md` at the repo root. See `docs/agents/domain.md`.
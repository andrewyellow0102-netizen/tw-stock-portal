"""
TW Stock Portal — FastAPI application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.routers import stocks, watchlist


app = FastAPI(
    title="TW Stock Portal API",
    description="台股分析站台 API — 報價、圖表、技術指標",
    version="0.1.0",
)

# Allow CORS for local dev and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router)
app.include_router(watchlist.router)

# Serve static frontend files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")


@app.get("/")
async def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/stock/{symbol}")
async def stock_page(symbol: str):
    return FileResponse(os.path.join(FRONTEND_DIR, "stock.html"))


@app.get("/watchlist")
async def watchlist_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "watchlist.html"))


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
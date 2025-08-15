from __future__ import annotations
import asyncio
import logging
import io
from typing import Optional
import requests
import numpy as np
import pandas as pd
from pycoingecko import CoinGeckoAPI

log = logging.getLogger("market")
_cg = CoinGeckoAPI()

# ---- OKX ----
def _okx_klines_sync(symbol: str, bar: str, limit: int) -> Optional[pd.DataFrame]:
    try:
        url = "https://www.okx.com/api/v5/market/candles"
        r = requests.get(url, params={"instId": symbol, "bar": bar, "limit": min(limit, 300)}, timeout=10)
        if r.status_code != 200:
            log.warning("OKX HTTP %s: %s", r.status_code, r.text[:200])
            return None
        js = r.json()
        data = js.get("data", [])
        if not data:
            return None
        rows = list(reversed(data))
        df = pd.DataFrame(rows, columns=["ts","open","high","low","close","vol","volCcy","volCcyQuote","confirm"])
        for c in ("open","high","low","close"):
            df[c] = df[c].astype(float)
        df["time"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms")
        return df[["time","open","high","low","close"]]
    except Exception as e:
        log.exception("okx_klines error: %s", e)
        return None

async def okx_klines(symbol: str, bar: str = "15m", limit: int = 200) -> Optional[pd.DataFrame]:
    return await asyncio.to_thread(_okx_klines_sync, symbol, bar, limit)

async def okx_15m_with_retry(symbol_okx: str, limit: int = 400, tries: int = 2) -> Optional[pd.DataFrame]:
    last_err = None
    for _ in range(max(1, tries)):
        try:
            df = await okx_klines(symbol_okx, "15m", limit)
            if df is not None and len(df) > 0:
                return df
        except Exception as e:
            last_err = e
        await asyncio.sleep(0.5)
    if last_err:
        log.warning("OKX 15m fallo tras reintentos: %s", last_err)
    return None

def ohlc_daily_from_15m(df_15m: pd.DataFrame) -> Optional[pd.DataFrame]:
    if df_15m is None or len(df_15m) < 4:
        return None
    df = df_15m.copy().set_index("time")
    if not {"open","high","low","close"}.issubset(df.columns):
        c = df["close"]
        df["open"] = c; df["high"] = c; df["low"] = c
    daily = df.resample("1D").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna().reset_index()
    return daily if len(daily) >= 1 else None

# ---- CoinGecko ----
def _cg_price_sync(coin_id: str) -> Optional[float]:
    try:
        d = _cg.get_price(ids=coin_id, vs_currencies="usd")
        return float(d.get(coin_id, {}).get("usd")) if d else None
    except Exception as e:
        log.warning("cg_price error: %s", e)
        return None

async def cg_price(coin_id: str) -> Optional[float]:
    return await asyncio.to_thread(_cg_price_sync, coin_id)

def _cg_prices_df_sync(coin_id: str, days: int) -> Optional[pd.DataFrame]:
    try:
        d = _cg.get_coin_market_chart_by_id(id=coin_id, vs_currency='usd', days=days)
        prices = d.get("prices", [])
        if not prices:
            return None
        df = pd.DataFrame(prices, columns=["ts", "close"])
        df["time"] = pd.to_datetime(df["ts"], unit="ms")
        df["close"] = df["close"].astype(float)
        return df[["time","close"]]
    except Exception as e:
        log.warning("cg_prices_df error: %s", e)
        return None

async def cg_prices_df(coin_id: str, days: int) -> Optional[pd.DataFrame]:
    return await asyncio.to_thread(_cg_prices_df_sync, coin_id, days)

def _cg_ohlc_daily_sync(coin_id: str, days: int) -> Optional[pd.DataFrame]:
    try:
        days_allowed = {1,7,14,30,90,180,365}
        if days not in days_allowed:
            days = 14
        arr = _cg.get_coin_ohlc_by_id(id=coin_id, vs_currency='usd', days=days)
        if not arr:
            return None
        df = pd.DataFrame(arr, columns=["time","open","high","low","close"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        for c in ("open","high","low","close"):
            df[c] = df[c].astype(float)
        df = (
            df.set_index("time")
              .resample("1D")
              .agg({"open":"first","high":"max","low":"min","close":"last"})
              .dropna()
              .reset_index()
        )
        return df
    except Exception as e:
        log.warning("cg_ohlc_daily error: %s", e)
        return None

async def cg_ohlc_daily(coin_id: str, days: int = 14) -> Optional[pd.DataFrame]:
    return await asyncio.to_thread(_cg_ohlc_daily_sync, coin_id, days)

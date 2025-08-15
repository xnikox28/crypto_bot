# bot/services/levels.py
from __future__ import annotations
import asyncio
import logging
from typing import Dict, Optional

import pandas as pd
from pycoingecko import CoinGeckoAPI

logger = logging.getLogger("crypto-bot")
_cg = CoinGeckoAPI()

# ------------------------- helpers sync ------------------------- #
def _cg_ohlc_daily_sync(coin_id: str, days: int = 14) -> Optional[pd.DataFrame]:
    """
    OHLC diarios desde CoinGecko (permitidos: 1,7,14,30,90,180,365,max).
    Se re-muestrea a 1D (UTC) para asegurar UNA vela diaria válida.
    """
    try:
        arr = _cg.get_coin_ohlc_by_id(id=coin_id, vs_currency="usd", days=days)
        if not arr:
            return None
        df = pd.DataFrame(arr, columns=["time", "open", "high", "low", "close"])
        # timestamps a UTC (tz-aware)
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        # una fila por día UTC
        df = (
            df.set_index("time")
              .resample("1D")
              .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
              .dropna()
              .reset_index()
        )
        return df
    except Exception as e:
        logger.warning("levels.cg_ohlc_daily error: %s", e)
        return None

def _pivots_from_row(row) -> Dict[str, float]:
    P  = (row.high + row.low + row.close) / 3.0
    R1 = 2 * P - row.low
    S1 = 2 * P - row.high
    R2 = P + (row.high - row.low)
    S2 = P - (row.high - row.low)
    R3 = row.high + 2 * (P - row.low)
    S3 = row.low  - 2 * (row.high - P)
    return {"P": P, "R1": R1, "R2": R2, "R3": R3, "S1": S1, "S2": S2, "S3": S3}

# --------------------------- API async -------------------------- #
async def get_levels(coin_id: str, symbol_okx: Optional[str] = None) -> Optional[Dict[str, float]]:
    """
    Devuelve Pivotes clásicos + Fibonacci tomando SIEMPRE el último DÍA COMPLETO (UTC).
    Si no hubiera día cerrado disponible, usa el último registro.

    return: dict con keys:
      P, S1, S2, S3, R1, R2, R3, F236, F382, F500, F618, F786
    """
    df = await asyncio.to_thread(_cg_ohlc_daily_sync, coin_id, 14)
    if df is None or df.empty:
        return None

    # elegir la vela del ÚLTIMO día CERRADO (UTC)
    today_utc = pd.Timestamp.now(tz="UTC").normalize()  # <- FIX
    df["date"] = df["time"].dt.normalize()              # ya tz-aware (UTC)
    closed = df[df["date"] < today_utc]
    row = closed.iloc[-1] if not closed.empty else df.iloc[-1]

    lv = _pivots_from_row(row)

    hi, lo, close = float(row.high), float(row.low), float(row.close)
    diff = max(hi - lo, 1e-12)
    fib = {
        "F236": hi - 0.236 * diff,
        "F382": hi - 0.382 * diff,
        "F500": hi - 0.500 * diff,
        "F618": hi - 0.618 * diff,
        "F786": hi - 0.786 * diff,
    }
    lv.update(fib)

    # Sanidad: garantizar orden S3<S2<S1<P<R1<R2<R3 (por si la fuente da datos raros)
    if not (lv["S3"] < lv["S2"] < lv["S1"] < lv["P"] < lv["R1"] < lv["R2"] < lv["R3"]):
        P = (hi + lo + close) / 3.0
        lv.update({
            "P": P,
            "S3": lo - 2 * (hi - P),
            "S2": P - (hi - lo),
            "S1": 2 * P - hi,
            "R1": 2 * P - lo,
            "R2": P + (hi - lo),
            "R3": hi + 2 * (P - lo),
        })
        lv.update(fib)

    return lv

__all__ = ["get_levels"]

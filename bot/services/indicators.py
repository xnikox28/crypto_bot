from __future__ import annotations
import pandas as pd
from typing import Dict, Tuple

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    rs = up.ewm(alpha=1/period, adjust=False).mean() / (down.ewm(alpha=1/period, adjust=False).mean() + 1e-9)
    return 100 - (100 / (1 + rs))

def macd(series: pd.Series, fast=12, slow=26, signal=9):
    mf = ema(series, fast)
    ms = ema(series, slow)
    m = mf - ms
    s = m.ewm(span=signal, adjust=False).mean()
    h = m - s
    return m, s, h

def modo_params(modo: str) -> Dict[str, float]:
    if modo == "agresivo":
        return {"pre_break_buffer": 0.006, "rsi_buy": 35, "rsi_sell": 65}
    if modo == "conservador":
        return {"pre_break_buffer": 0.003, "rsi_buy": 30, "rsi_sell": 70}
    return {"pre_break_buffer": 0.004, "rsi_buy": 33, "rsi_sell": 67}

from __future__ import annotations
from functools import lru_cache
from typing import Optional
import requests

OKX_BASE = "https://www.okx.com"

def _decimals_from_ticksz(tick: str) -> int:
    # tickSz es string tipo "0.0001" o "0.01"
    if not tick or "." not in tick:
        return 0
    frac = tick.rstrip("0").split(".")[1]
    return max(0, len(frac))

@lru_cache(maxsize=256)
def _okx_tick_decimals(inst_id: str) -> Optional[int]:
    """Devuelve cantidad de decimales según tickSz real de OKX para el símbolo."""
    try:
        r = requests.get(
            f"{OKX_BASE}/api/v5/public/instruments",
            params={"instType": "SPOT", "instId": inst_id},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json().get("data", [])
        if not data:
            return None
        tick = data[0].get("tickSz")
        return _decimals_from_ticksz(str(tick)) if tick is not None else None
    except Exception:
        return None

def _fallback_decimals(price: float) -> int:
    """Si no podemos consultar OKX, usa decimales sensatos por magnitud."""
    if price is None:
        return 4
    p = float(price)
    if p >= 100:   return 2
    if p >= 1:     return 3
    if p >= 0.1:   return 4
    if p >= 0.01:  return 5
    if p >= 0.001: return 6
    if p >= 0.0001:return 7
    return 8

def get_symbol_decimals(inst_id: str, sample_price: Optional[float] = None) -> int:
    """Decimales a usar para un símbolo. Intenta tickSz OKX; si no, fallback por precio."""
    d = _okx_tick_decimals(inst_id) if inst_id else None
    if d is None:
        d = _fallback_decimals(sample_price if sample_price is not None else 1.0)
    return int(max(0, min(10, d)))  # clamp

def fmt_price(inst_id: str, value: Optional[float]) -> str:
    """Formatea un precio acorde al símbolo (decimales OKX/fallback)."""
    if value is None:
        return "—"
    dp = get_symbol_decimals(inst_id, value)
    return f"{float(value):.{dp}f}"

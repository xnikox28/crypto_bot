from __future__ import annotations
from typing import Optional, Iterable, Dict
import requests

try:
    from pycoingecko import CoinGeckoAPI
except Exception:
    CoinGeckoAPI = None  # por si acaso

_CG = CoinGeckoAPI() if CoinGeckoAPI else None
_CACHE: Dict[str, str] = {}  # cg_id -> instId OKX resuelto

OKX_BASE = "https://www.okx.com"


def _cg_get_symbol(cg_id: str) -> Optional[str]:
    """Obtiene el símbolo base (ej. 'BTC', 'WIF') desde CoinGecko."""
    if not _CG:
        return None
    try:
        # usamos el endpoint ligero (sin tickers/market_data)
        d = _CG.get_coin_by_id(
            id=cg_id,
            localization=False,
            tickers=False,
            market_data=False,
            community_data=False,
            developer_data=False,
            sparkline=False,
        )
        sym = d.get("symbol") or d.get("symbol", "")
        return sym.upper() if sym else None
    except Exception:
        return None


def _okx_validate_inst(inst_id: str) -> bool:
    """Valida que un instId exista en OKX a través del catálogo de instrumentos."""
    try:
        r = requests.get(
            f"{OKX_BASE}/api/v5/public/instruments",
            params={"instType": "SPOT", "instId": inst_id},
            timeout=10,
        )
        if r.status_code != 200:
            return False
        data = r.json().get("data", [])
        return len(data) > 0 and (data[0].get("state") in {"live", "suspend"})  # 'live' preferido
    except Exception:
        return False


def _okx_search_by_base(base: str, quotes: Iterable[str] = ("USDT", "USDC", "USD")) -> Optional[str]:
    """Busca en todo el listado de SPOT un par base-quote por preferencia."""
    try:
        r = requests.get(
            f"{OKX_BASE}/api/v5/public/instruments",
            params={"instType": "SPOT"},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        items = r.json().get("data", [])
        base = base.upper()
        # Primero preferencia por quotes (orden)
        for q in quotes:
            for it in items:
                if it.get("baseCcy", "").upper() == base and it.get("quoteCcy", "").upper() == q:
                    if it.get("state") in {"live", "suspend"}:
                        return it.get("instId")
        # Si no se halló por preferencia, devolver cualquier match por base
        for it in items:
            if it.get("baseCcy", "").upper() == base:
                return it.get("instId")
        return None
    except Exception:
        return None


def _cg_tickers_try_okx(cg_id: str) -> Optional[str]:
    """Último recurso: consulta tickers de CG y busca mercado OKX/USDT."""
    if not _CG:
        return None
    try:
        d = _CG.get_coin_by_id(id=cg_id)  # completo; puede ser pesado
        tickers = d.get("tickers", []) or []
        # buscar OKX + target preferente
        for prefer in ("USDT", "USDC", "USD"):
            for t in tickers:
                mkt = (t.get("market") or {}).get("identifier", "") or (t.get("market") or {}).get("name", "")
                tgt = (t.get("target") or "").upper()
                base = (t.get("base") or "").upper()
                if "OKX" in str(mkt).upper() and tgt == prefer and base:
                    inst = f"{base}-{tgt}"
                    if _okx_validate_inst(inst):
                        return inst
        return None
    except Exception:
        return None


def resolve_okx_symbol_from_cg_id(cg_id: str) -> Optional[str]:
    """
    Dado un CoinGecko ID (ej. 'bitcoin', 'dogwifcoin'), intenta devolver un instId de OKX (ej. 'BTC-USDT').
    Estrategia:
      1) CG symbol -> probar "<SYMBOL>-USDT" (validar)
      2) Buscar en catálogo SPOT de OKX por base (preferencia USDT/USDC/USD)
      3) Consultar tickers de CG y localizar un par en OKX
    """
    if not cg_id:
        return None
    key = cg_id.strip().lower()
    if key in _CACHE:
        return _CACHE[key]

    base = _cg_get_symbol(key)
    if not base:
        return None

    guess = f"{base}-USDT"
    if _okx_validate_inst(guess):
        _CACHE[key] = guess
        return guess

    found = _okx_search_by_base(base)
    if found:
        _CACHE[key] = found
        return found

    found2 = _cg_tickers_try_okx(key)
    if found2:
        _CACHE[key] = found2
        return found2

    return None

# bot/db/models.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class ChatState:
    chat_id: int
    coin_id: str = "dogwifcoin"
    symbol_okx: str = "WIF-USDT"
    tp_pct: float = 2.0
    sl_pct: float = 1.5
    modo: str = "agresivo"
    precision_on: int = 0
    alerts_on: int = 1
    # 👇 nuevo: preferencia global por chat
    dark_mode: int = 0  # 0=claro, 1=oscuro

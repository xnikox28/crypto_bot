# bot/db/repo.py
from __future__ import annotations
import asyncio
import sqlite3
from typing import Optional
from .models import ChatState

# ---------------- base ----------------
def _connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con

def setup(db_path: str) -> None:
    con = _connect(db_path)
    cur = con.cursor()
    # tabla base
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chats (
            chat_id      INTEGER PRIMARY KEY,
            coin_id      TEXT    NOT NULL DEFAULT 'dogwifcoin',
            symbol_okx   TEXT    NOT NULL DEFAULT 'WIF-USDT',
            tp_pct       REAL    NOT NULL DEFAULT 2.0,
            sl_pct       REAL    NOT NULL DEFAULT 1.5,
            modo         TEXT    NOT NULL DEFAULT 'agresivo',
            precision_on INTEGER NOT NULL DEFAULT 0,
            alerts_on    INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    # migración suave: asegurar dark_mode
    try:
        cur.execute("ALTER TABLE chats ADD COLUMN dark_mode INTEGER NOT NULL DEFAULT 0;")
    except sqlite3.OperationalError:
        pass
    con.commit()
    con.close()

# ---------------- sync internals ----------------
def _get_chat_sync(db_path: str, chat_id: int) -> Optional[ChatState]:
    con = _connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT * FROM chats WHERE chat_id=?", (chat_id,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    keys = row.keys()
    return ChatState(
        chat_id=row["chat_id"],
        coin_id=row["coin_id"],
        symbol_okx=row["symbol_okx"],
        tp_pct=row["tp_pct"],
        sl_pct=row["sl_pct"],
        modo=row["modo"],
        precision_on=row["precision_on"],
        alerts_on=row["alerts_on"],
        dark_mode=(row["dark_mode"] if "dark_mode" in keys else 0),
    )

def _upsert_chat_sync(db_path: str, st: ChatState) -> None:
    con = _connect(db_path)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO chats (chat_id, coin_id, symbol_okx, tp_pct, sl_pct, modo, precision_on, alerts_on, dark_mode)
        VALUES (:chat_id, :coin_id, :symbol_okx, :tp_pct, :sl_pct, :modo, :precision_on, :alerts_on, :dark_mode)
        ON CONFLICT(chat_id) DO UPDATE SET
            coin_id=excluded.coin_id,
            symbol_okx=excluded.symbol_okx,
            tp_pct=excluded.tp_pct,
            sl_pct=excluded.sl_pct,
            modo=excluded.modo,
            precision_on=excluded.precision_on,
            alerts_on=excluded.alerts_on,
            dark_mode=excluded.dark_mode;
        """,
        {
            "chat_id": st.chat_id,
            "coin_id": st.coin_id,
            "symbol_okx": st.symbol_okx,
            "tp_pct": st.tp_pct,
            "sl_pct": st.sl_pct,
            "modo": st.modo,
            "precision_on": st.precision_on,
            "alerts_on": st.alerts_on,
            "dark_mode": st.dark_mode,
        },
    )
    con.commit()
    con.close()

def _update_fields_sync(db_path: str, chat_id: int, **fields) -> None:
    allowed = {"coin_id", "symbol_okx", "tp_pct", "sl_pct", "modo", "precision_on", "alerts_on", "dark_mode"}
    payload = {k: v for k, v in fields.items() if k in allowed}
    if not payload:
        return

    # asegurar existencia
    st = _get_chat_sync(db_path, chat_id)
    if not st:
        st = ChatState(chat_id=chat_id)
        for k, v in payload.items():
            setattr(st, k, v)
        _upsert_chat_sync(db_path, st)
        return

    sets = ", ".join([f"{k}=:{k}" for k in payload.keys()])
    payload["chat_id"] = chat_id

    con = _connect(db_path)
    cur = con.cursor()
    cur.execute(f"UPDATE chats SET {sets} WHERE chat_id=:chat_id;", payload)
    con.commit()
    con.close()

# ---------------- async wrappers (compat) ----------------
async def ensure_schema(db_path: str) -> None:
    """Wrapper async para main.py."""
    # Es rápido; no hace falta to_thread, pero si quieres:
    # await asyncio.to_thread(setup, db_path)
    setup(db_path)

async def get_chat(db_path: str, chat_id: int) -> Optional[ChatState]:
    """Compat: tus handlers usan `await repo.get_chat(...)`."""
    return await asyncio.to_thread(_get_chat_sync, db_path, chat_id)

async def upsert_chat(db_path: str, st: ChatState) -> None:
    """Compat: tus handlers usan `await repo.upsert_chat(...)`."""
    await asyncio.to_thread(_upsert_chat_sync, db_path, st)

async def update_fields(db_path: str, chat_id: int, **fields) -> None:
    """Compat: p.ej. /modo llama a repo.update_fields con await."""
    await asyncio.to_thread(_update_fields_sync, db_path, chat_id, **fields)

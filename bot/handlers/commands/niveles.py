from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ...config import Config
from ...db import repo
from ...db.models import ChatState
from ...services.levels import get_levels
from ...services.indicators import ema
from ...services.formatting import fmt_price
from ..jobs import get_15m_oper

async def niveles_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = update.effective_chat.id

    st = await repo.get_chat(cfg.db_path, chat_id) or ChatState(chat_id=chat_id)

    levels = await get_levels(st.coin_id, st.symbol_okx)
    if not levels:
        await update.message.reply_text("No pude calcular niveles ahora.")
        return

    op15 = await get_15m_oper(st.coin_id, st.symbol_okx)
    if not op15:
        await update.message.reply_text("No pude calcular EMAs ahora.")
        return

    # Orden nuevo: Resistencias (R3 -> R1) arriba, luego Punto Pivote, luego Soportes (S1 -> S3)
    R3 = fmt_price(st.symbol_okx, levels.get("R3"))
    R2 = fmt_price(st.symbol_okx, levels.get("R2"))
    R1 = fmt_price(st.symbol_okx, levels.get("R1"))
    P  = fmt_price(st.symbol_okx, levels.get("P"))
    S1 = fmt_price(st.symbol_okx, levels.get("S1"))
    S2 = fmt_price(st.symbol_okx, levels.get("S2"))
    S3 = fmt_price(st.symbol_okx, levels.get("S3"))

    F236 = fmt_price(st.symbol_okx, levels.get("F236"))
    F382 = fmt_price(st.symbol_okx, levels.get("F382"))
    F500 = fmt_price(st.symbol_okx, levels.get("F500"))
    F618 = fmt_price(st.symbol_okx, levels.get("F618"))
    F786 = fmt_price(st.symbol_okx, levels.get("F786"))

    em20 = fmt_price(st.symbol_okx, op15["ema20"])
    em50 = fmt_price(st.symbol_okx, op15["ema50"])
    em200= fmt_price(st.symbol_okx, op15["ema200"])

    msg = (
        f"📏 <b>Niveles — {st.coin_id.upper()}</b>\n"
        f"<b>Resistencias</b>\n"
        f"R3 {R3}  |  R2 {R2}  |  R1 {R1}\n"
        f"<b>Punto Pivote</b>\n"
        f"P  {P}\n"
        f"<b>Soportes</b>\n"
        f"S1 {S1}  |  S2 {S2}  |  S3 {S3}\n\n"
        f"<b>Fibonacci</b>\n"
        f"23.6% {F236}  |  38.2% {F382}  |  50% {F500}  |  61.8% {F618}  |  78.6% {F786}\n\n"
        f"<b>EMAs (15m)</b>\n"
        f"20 {em20}  |  50 {em50}  |  200 {em200}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)



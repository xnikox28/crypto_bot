# bot/handlers/commands/start.py
from __future__ import annotations
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ...config import Config
from ...db import repo
from ...db.models import ChatState

def _start_keyboard() -> ReplyKeyboardMarkup:
    # Botonera persistente (funciona en privados y grupos; aparece al usuario que usa /start)
    kb = [
        [KeyboardButton("/estado"), KeyboardButton("/grafica"), KeyboardButton("/niveles")],
        [KeyboardButton("/precision on"), KeyboardButton("/precision off")],
        [KeyboardButton("/header"), KeyboardButton("/header status")],
        [KeyboardButton("/header on"), KeyboardButton("/header off")],
        [KeyboardButton("/config"), KeyboardButton("/alerts")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=False, selective=False)

async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = update.effective_chat.id

    # Estado inicial del chat
    st = await repo.get_chat(cfg.db_path, chat_id)
    if not st:
        st = ChatState(chat_id=chat_id)
        await repo.upsert_chat(cfg.db_path, st)

    # 👇 texto del tema actual (lee de DB; fallback a claro)
    theme_txt = "🌙 Oscuro" if getattr(st, "dark_mode", 0) else "☀️ Claro"

    # Mensaje claro y sin activar header
    msg = (
        "🤖 <b>Bot PRO cripto</b>\n"
        "Análisis multi-TF (4H/15M/5M), alertas y niveles.\n\n"

        "📌 <b>Estado actual</b>\n"
        f"• Moneda: <b>{st.coin_id}</b>\n"
        f"• Símbolo: <b>{st.symbol_okx}</b>\n"
        f"• TP/SL: <b>{st.tp_pct:.2f}%</b> / <b>{st.sl_pct:.2f}%</b>\n"
        f"• Modo: <b>{st.modo}</b>\n"
        f"• Precisión (vela cerrada): <b>{'ON' if getattr(st, 'precision_on', 0) else 'OFF'}</b>\n"
        f"• Tema actual: <b>{theme_txt}</b>  → cambia con <code>/darkmode</code>\n\n"

        "🧭 <b>Comandos rápidos</b>\n"
        "• <code>/estado</code> — panel técnico (imagen)\n"
        "• <code>/grafica</code> — 15m con Pivotes + F618\n"
        "• <code>/niveles</code> — Pivotes + Fibonacci\n\n"

        "⚙️ <b>Config</b>\n"
        "• <code>/setcoin &lt;coingecko_id&gt;</code>\n"
        "• <code>/setsymbol &lt;SYMBOL_OKX&gt;</code>\n"
        "• <code>/tp &lt;pct&gt;</code> · <code>/sl &lt;pct&gt;</code> · "
        "<code>/modo &lt;agresivo|balanceado|conservador&gt;</code>\n"
        "• <code>/precision on</code> | <code>/precision off</code>\n"
        "• <code>/darkmode</code> (on/off) — tema por chat\n\n"

        "🖼️ <b>Header tendencia (opcional)</b>\n"
        "• <code>/header</code> — publicar una vez (silencioso)\n"
        "• <code>/header on</code> — activar auto-sync\n"
        "• <code>/header off</code> — desactivar auto-sync\n"
        "• <code>/header status</code> — estado del header\n"
    )

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=_start_keyboard(),  # 👈 tus botones intactos
    )








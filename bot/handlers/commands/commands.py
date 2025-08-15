# bot/handlers/commands/commands.py
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes

from .start import _start_keyboard  # reutiliza tu misma botonera
from ...config import Config
from ...db import repo
from ...db.models import ChatState

async def commands_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Vuelve a mostrar la botonera persistente sin reimprimir todo el /start.
    Útil para invocarlo desde captions: '🔘 /commands'.
    """
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = update.effective_chat.id

    # (nos aseguramos de tener un registro para este chat)
    st = await repo.get_chat(cfg.db_path, chat_id) or ChatState(chat_id=chat_id)
    if st.chat_id != chat_id:
        st.chat_id = chat_id
    await repo.upsert_chat(cfg.db_path, st)

    # mismo teclado que /start
    kb = _start_keyboard()

    await update.message.reply_text(
        "🔘 Atajos arriba. ¿Qué necesitas?",
        reply_markup=kb,
        disable_web_page_preview=True,
        disable_notification=True,  # no molestar en grupos
    )

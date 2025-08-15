# bot/handlers/commands/darkmode.py
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from ...config import Config
from ...db import repo
from ...db.models import ChatState

HELP = (
    "<b>Modo oscuro</b>\n"
    "• /darkmode           → alterna claro/oscuro\n"
    "• /darkmode on        → fuerza oscuro\n"
    "• /darkmode off       → fuerza claro\n\n"
    "Afecta a /estado, /grafica y demás salidas visuales de este chat."
)

async def darkmode_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    app = ctx.application
    cfg: Config = app.bot_data["config"]
    chat_id = update.effective_chat.id

    st = await repo.get_chat(cfg.db_path, chat_id) or ChatState(chat_id=chat_id)
    args = [a.lower() for a in (ctx.args or [])]

    if not args:
        st.dark_mode = 0 if st.dark_mode else 1
    else:
        if args[0] in ("on", "1", "true", "sí", "si"):
            st.dark_mode = 1
        elif args[0] in ("off", "0", "false", "no"):
            st.dark_mode = 0
        else:
            await update.message.reply_text(HELP, parse_mode=ParseMode.HTML)
            return

    await repo.upsert_chat(cfg.db_path, st)
    mode_txt = "🌙 Oscuro" if st.dark_mode else "☀️ Claro"
    await update.message.reply_text(
        f"✅ Modo visual guardado para este chat: <b>{mode_txt}</b>\n\n{HELP}",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

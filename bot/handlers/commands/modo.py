from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from ...config import Config
from ...db import repo

async def modo_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = update.effective_chat.id
    if not ctx.args:
        st = await repo.get_chat(cfg.db_path, chat_id)
        await update.message.reply_text(f"Modo actual: {st.modo}")
        return
    m = ctx.args[0].strip().lower()
    if m not in {"agresivo","balanceado","conservador"}:
        await update.message.reply_text("Usa: /modo agresivo|balanceado|conservador")
        return
    await repo.update_fields(cfg.db_path, chat_id, modo=m)
    await update.message.reply_text(f"✅ Modo cambiado a: {m}")

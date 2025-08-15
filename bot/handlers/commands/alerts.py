from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from ...config import Config
from ...db import repo

async def alerts_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = update.effective_chat.id
    if not ctx.args:
        st = await repo.get_chat(cfg.db_path, chat_id)
        await update.message.reply_text(f"Alerts: {'on' if st.alerts_on else 'off'}")
        return
    v = ctx.args[0].strip().lower()
    if v not in {"on","off"}:
        await update.message.reply_text("Uso: /alerts on|off"); return
    await repo.update_fields(cfg.db_path, chat_id, alerts_on=1 if v=="on" else 0)
    await update.message.reply_text(f"✅ Alerts {v}")

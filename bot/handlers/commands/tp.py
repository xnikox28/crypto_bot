from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from ...config import Config
from ...db import repo

async def tp_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = update.effective_chat.id
    if not ctx.args:
        st = await repo.get_chat(cfg.db_path, chat_id)
        await update.message.reply_text(f"TP actual: {st.tp_pct:.2f}%"); return
    try:
        v = max(0.2, min(50.0, float(ctx.args[0])))
        await repo.update_fields(cfg.db_path, chat_id, tp_pct=v)
        await update.message.reply_text(f"✅ TP actualizado a {v:.2f}%")
    except Exception:
        await update.message.reply_text("Uso: /tp 2  (por ejemplo)")

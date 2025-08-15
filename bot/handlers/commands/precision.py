from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from ...config import Config
from ...db import repo

async def precision_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = update.effective_chat.id

    await repo.ensure_schema(cfg.db_path)

    if not ctx.args:
        st = await repo.get_chat(cfg.db_path, chat_id)
        status = "ON" if (st and int(st.precision_on) == 1) else "OFF"
        await update.message.reply_text(
            f"Precision mode: {status}\nUsa: /precision on | /precision off | /precision status"
        )
        return

    arg = ctx.args[0].strip().lower()
    if arg == "status":
        st = await repo.get_chat(cfg.db_path, chat_id)
        status = "ON" if (st and int(st.precision_on) == 1) else "OFF"
        await update.message.reply_text(f"Precision mode: {status}")
        return

    if arg not in {"on", "off"}:
        await update.message.reply_text("Uso: /precision on | /precision off | /precision status")
        return

    val = 1 if arg == "on" else 0
    await repo.update_fields(cfg.db_path, chat_id, precision_on=val)
    await update.message.reply_text(f"✅ Precision mode {arg.upper()}")

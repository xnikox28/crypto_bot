from __future__ import annotations
import asyncio
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

async def clearchat_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.message

    if chat.type != "private":
        await msg.reply_text("En grupos/supergrupos usa /purge respondiendo al primer mensaje del bloque que quieras borrar.")
        return

    arg = ctx.args[0].strip().lower() if ctx.args else ""
    if arg == "all":
        limit = 5000
    else:
        try:
            limit = max(1, min(5000, int(arg))) if arg else 1000
        except Exception:
            limit = 1000

    last_id = msg.message_id
    deleted = tried = 0

    for mid in range(last_id, max(last_id - limit, 1), -1):
        tried += 1
        try:
            await ctx.bot.delete_message(chat.id, mid)
            deleted += 1
        except Exception:
            pass
        if tried % 25 == 0:
            await asyncio.sleep(0.08)

    note = (
        "🧹 <b>ClearChat (privado)</b>\n"
        f"Intentados: <code>{tried}</code> · Eliminados: <code>{deleted}</code>\n"
        "<i>Nota:</i> Telegram no permite a los bots borrar <b>tus</b> mensajes en chats privados.\n"
        "Para limpiar <b>todo</b>, usa “Vaciar chat / Clear history”."
    )
    m = await ctx.bot.send_message(chat.id, note, parse_mode=ParseMode.HTML)
    try:
        await asyncio.sleep(3)
        await ctx.bot.delete_message(chat.id, m.message_id)
    except Exception:
        pass

from __future__ import annotations
import asyncio
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

async def clearbot_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.message
    if chat.type in ("group", "supergroup"):
        await msg.reply_text(
            "Por seguridad, /clearbot solo funciona en <b>chats privados</b>.\n"
            "En grupos usa <code>/purge</code> respondiendo al primer mensaje del bloque.",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        n = max(1, min(500, int(ctx.args[0]))) if ctx.args else 50
    except Exception:
        n = 50

    last_id = msg.message_id
    deleted, tried = 0, 0
    for mid in range(last_id - 1, max(last_id - n - 1, 1), -1):
        tried += 1
        try:
            await ctx.bot.delete_message(chat.id, mid)
            deleted += 1
        except Exception:
            pass
        if tried % 25 == 0:
            await asyncio.sleep(0.08)

    await msg.reply_text(f"🧽 ClearBot: eliminados {deleted} mensajes del bot (intentados {tried}).")

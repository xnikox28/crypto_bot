from __future__ import annotations
import asyncio
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

async def purge_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.message
    if not msg or not msg.reply_to_message:
        await update.effective_message.reply_text(
            "Responde al <b>primer</b> mensaje que quieres borrar y envía /purge.",
            parse_mode=ParseMode.HTML,
        )
        return

    if chat.type in ("group", "supergroup"):
        me = await ctx.bot.get_me()
        me_member = await ctx.bot.get_chat_member(chat.id, me.id)
        can_delete = getattr(me_member, "can_delete_messages", False) or me_member.status in ("creator",)
        if not can_delete:
            await msg.reply_text("Necesito permiso de <b>borrar mensajes</b> para usar /purge.", parse_mode=ParseMode.HTML)
            return

    start_id = msg.reply_to_message.message_id
    end_id = msg.message_id

    deleted = 0
    for mid in range(start_id, end_id + 1):
        try:
            await ctx.bot.delete_message(chat.id, mid)
            deleted += 1
        except Exception:
            pass
        if (mid - start_id) % 25 == 0:
            await asyncio.sleep(0.08)

    try:
        await ctx.bot.delete_message(chat.id, msg.message_id)
    except Exception:
        pass

    await ctx.bot.send_message(chat.id, f"🧹 Purge: eliminados {deleted} mensajes.")

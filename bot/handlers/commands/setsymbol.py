from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from ...config import Config
from ...db import repo
from ...db.models import ChatState
from ...services.symbols import resolve_okx_symbol_from_cg_id

async def setsymbol_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = update.effective_chat.id

    if not ctx.args:
        await update.message.reply_text("Uso: /setsymbol <SYMBOL_OKX>|auto  (ej: WIF-USDT)")
        return

    arg = ctx.args[0].strip()

    if arg.lower() == "auto":
        # reintenta resolver usando el coin_id actual del chat
        st = await repo.get_chat(cfg.db_path, chat_id) or ChatState(chat_id=chat_id)
        sym = resolve_okx_symbol_from_cg_id(st.coin_id)
        if sym:
            await repo.update_fields(cfg.db_path, chat_id, symbol_okx=sym, position_entry=None)
            await update.message.reply_text(
                f"🔎 Símbolo OKX detectado: <b>{sym}</b> (posición virtual reiniciada)",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                "⚠️ No pude detectar símbolo OKX automáticamente. Indícalo manualmente: "
                "<code>/setsymbol &lt;PAR&gt;</code> (ej: <code>BTC-USDT</code>)",
                parse_mode="HTML",
            )
        return

    # set manual
    sym = arg.upper()
    await repo.update_fields(cfg.db_path, chat_id, symbol_okx=sym, position_entry=None)
    await update.message.reply_text(f"✅ Símbolo OKX cambiado a: {sym} (posición virtual reiniciada)")

from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from ...config import Config
from ...db import repo
from ...services.symbols import resolve_okx_symbol_from_cg_id

async def setcoin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = update.effective_chat.id

    if not ctx.args:
        await update.message.reply_text("Uso: /setcoin <coingecko_id>")
        return

    cid = ctx.args[0].strip().lower()
    # 1) guardamos el coin_id y reseteamos entrada virtual
    await repo.update_fields(cfg.db_path, chat_id, coin_id=cid, position_entry=None)

    # 2) intentar resolver símbolo OKX automáticamente
    sym = resolve_okx_symbol_from_cg_id(cid)

    if sym:
        await repo.update_fields(cfg.db_path, chat_id, symbol_okx=sym)
        await update.message.reply_text(
            f"✅ CoinGecko ID cambiado a: {cid}\n"
            f"🔎 Símbolo OKX detectado automáticamente: <b>{sym}</b>\n"
            f"(posición virtual reiniciada)",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"✅ CoinGecko ID cambiado a: {cid}\n"
            f"⚠️ No pude detectar el símbolo en OKX automáticamente.\n"
            f"Por favor indica uno con <code>/setsymbol &lt;PAR&gt;</code> (ej: <code>BTC-USDT</code>), "
            f"o prueba <code>/setsymbol auto</code>.",
            parse_mode="HTML",
        )

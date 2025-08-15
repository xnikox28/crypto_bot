# bot/handlers/commands/config.py
from __future__ import annotations
from typing import Optional
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

from ...config import Config
from ...db import repo
from ...db.models import ChatState

# ---------- helpers ----------
def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def _onoff(flag: int) -> str:
    return "ON ✅" if flag else "OFF ⛔"

def _theme(flag: int) -> str:
    return "🌙 Oscuro" if flag else "☀️ Claro"

def _render_text(st: ChatState) -> str:
    return (
        "<b>⚙️ Configuración del chat</b>\n\n"
        f"• Activo: <code>{st.coin_id}</code>\n"
        f"• Símbolo OKX: <code>{st.symbol_okx}</code>\n"
        f"• TP: <b>{st.tp_pct:.2f}%</b>   |   SL: <b>{st.sl_pct:.2f}%</b>\n"
        f"• Modo: <b>{st.modo}</b>\n"
        f"• Precisión (vela cerrada): <b>{_onoff(st.precision_on)}</b>\n"
        f"• Alertas: <b>{_onoff(st.alerts_on)}</b>\n"
        f"• Tema: <b>{_theme(st.dark_mode)}</b>\n\n"
        "💡 <i>Consejo:</i> Usa <code>/setcoin &lt;id_coingecko&gt;</code> y "
        "<code>/setsymbol &lt;SYMBOL_OKX&gt;</code> para cambiar activo/símbolo.\n"
        "🔘 Atajos: /commands"
    )

def _kb(st: ChatState) -> InlineKeyboardMarkup:
    # Fila TP/SL
    row_tp = [
        InlineKeyboardButton("TP -1%", callback_data="cfg:tp:-1"),
        InlineKeyboardButton("TP -0.25%", callback_data="cfg:tp:-0.25"),
        InlineKeyboardButton("TP +0.25%", callback_data="cfg:tp:+0.25"),
        InlineKeyboardButton("TP +1%", callback_data="cfg:tp:+1"),
    ]
    row_sl = [
        InlineKeyboardButton("SL -1%", callback_data="cfg:sl:-1"),
        InlineKeyboardButton("SL -0.25%", callback_data="cfg:sl:-0.25"),
        InlineKeyboardButton("SL +0.25%", callback_data="cfg:sl:+0.25"),
        InlineKeyboardButton("SL +1%", callback_data="cfg:sl:+1"),
    ]

    # Fila Modo (resalta actual con ●)
    def mode_btn(mode: str) -> InlineKeyboardButton:
        label = f"● {mode}" if st.modo == mode else mode
        return InlineKeyboardButton(label.capitalize(), callback_data=f"cfg:mode:{mode}")

    row_mode = [
        mode_btn("agresivo"),
        mode_btn("balanceado"),
        mode_btn("conservador"),
    ]

    # Toggles
    row_toggles1 = [
        InlineKeyboardButton(f"Precisión: {_onoff(st.precision_on)}", callback_data="cfg:toggle:precision"),
        InlineKeyboardButton(f"Alertas: {_onoff(st.alerts_on)}", callback_data="cfg:toggle:alerts"),
    ]
    row_toggles2 = [
        InlineKeyboardButton(f"Tema: {_theme(st.dark_mode)}", callback_data="cfg:toggle:darkmode"),
    ]

    # Acciones
    row_actions = [
        InlineKeyboardButton("🔄 Refrescar", callback_data="cfg:refresh"),
        InlineKeyboardButton("❌ Cerrar", callback_data="cfg:close"),
    ]

    return InlineKeyboardMarkup([row_tp, row_sl, row_mode, row_toggles1, row_toggles2, row_actions])

async def _safe_edit(query, text: str, markup: Optional[InlineKeyboardMarkup]) -> None:
    """Edita el mensaje, ignorando 'Message is not modified' si aplica."""
    try:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            # Nada que cambiar
            return
        # Intento solo actualizar markup
        try:
            await query.edit_message_reply_markup(reply_markup=markup)
        except BadRequest as e2:
            if "message is not modified" in str(e2).lower():
                return
            raise
    except Exception:
        # último intento solo markup
        try:
            await query.edit_message_reply_markup(reply_markup=markup)
        except Exception:
            pass

# ---------- command ----------
async def config_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = update.effective_chat.id

    st = await repo.get_chat(cfg.db_path, chat_id) or ChatState(chat_id=chat_id)
    if st.chat_id != chat_id:
        st.chat_id = chat_id
    await repo.upsert_chat(cfg.db_path, st)

    await update.message.reply_text(
        _render_text(st),
        parse_mode=ParseMode.HTML,
        reply_markup=_kb(st),
        disable_web_page_preview=True,
    )

# ---------- callbacks ----------
async def config_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones inline de /config, evitando 'Message is not modified'."""
    query = update.callback_query
    await query.answer()
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = query.message.chat_id

    st = await repo.get_chat(cfg.db_path, chat_id) or ChatState(chat_id=chat_id)

    data = (query.data or "").strip()
    parts = data.split(":")
    group = parts[1].lower() if len(parts) >= 2 else ""
    value = parts[2] if len(parts) >= 3 else ""

    changed = False
    toast: Optional[str] = None

    if group == "tp":
        try:
            delta = float(value)
            new_tp = _clamp(st.tp_pct + delta, 0.2, 50.0)
            if new_tp != st.tp_pct:
                st.tp_pct = new_tp
                changed = True
            else:
                toast = "Límite alcanzado"
        except Exception:
            toast = "Entrada inválida"

    elif group == "sl":
        try:
            delta = float(value)
            new_sl = _clamp(st.sl_pct + delta, 0.2, 50.0)
            if new_sl != st.sl_pct:
                st.sl_pct = new_sl
                changed = True
            else:
                toast = "Límite alcanzado"
        except Exception:
            toast = "Entrada inválida"

    elif group == "mode":
        val = value.lower()
        if val in ("agresivo", "balanceado", "conservador"):
            if val != st.modo:
                st.modo = val
                changed = True
            else:
                toast = f"Ya estás en '{val}'"
        else:
            toast = "Modo inválido"

    elif group == "toggle":
        if value == "precision":
            st.precision_on = 0 if st.precision_on else 1
            changed = True
        elif value == "alerts":
            st.alerts_on = 0 if st.alerts_on else 1
            changed = True
        elif value == "darkmode":
            st.dark_mode = 0 if st.dark_mode else 1
            changed = True

    elif group == "refresh":
        toast = "Refrescado ✅"

    elif group == "close":
        # Intenta borrar; si no, edita a 'cerrado' sin teclado
        try:
            await query.message.delete()
            await query.answer("Cerrado ✅", show_alert=False)
        except Exception:
            try:
                await query.edit_message_text(
                    "Configuración cerrada.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=None,
                    disable_web_page_preview=True,
                )
            except BadRequest as e:
                if "message is not modified" not in str(e).lower():
                    raise
            finally:
                await query.answer("Cerrado ✅", show_alert=False)
        return

    # persistir si cambió algo
    if changed:
        await repo.update_fields(
            cfg.db_path, chat_id,
            tp_pct=st.tp_pct,
            sl_pct=st.sl_pct,
            modo=st.modo,
            precision_on=st.precision_on,
            alerts_on=st.alerts_on,
            dark_mode=st.dark_mode,
        )

    # feedback breve
    if toast:
        await query.answer(toast, show_alert=False)

    # solo re-render si hubo cambios (evita 400 de 'not modified')
    if changed:
        await _safe_edit(query, _render_text(st), _kb(st))

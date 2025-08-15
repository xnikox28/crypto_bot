# bot/handlers/commands/header.py
from __future__ import annotations
import io
from typing import Tuple, Optional

import pandas as pd
from telegram import Update, InputFile
from telegram.ext import ContextTypes, Application
from telegram.constants import ChatMemberStatus

from ...db import repo
from ...db.models import ChatState
from ...config import Config
from ..jobs import get_4h_context, get_15m_oper  # funciones ya existentes

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None

# Colores por tendencia
COLOR_UP   = "#1b5e20"  # verde oscuro
COLOR_DOWN = "#b71c1c"  # rojo oscuro
COLOR_SIDE = "#b45309"  # ámbar oscuro


# ---------- utilidades ----------
def _trend_color_and_label(trend_up: bool, trend_down: bool) -> Tuple[str, str]:
    if trend_up:
        return (COLOR_UP, "Tendencia 4H: ALCISTA")
    if trend_down:
        return (COLOR_DOWN, "Tendencia 4H: BAJISTA")
    return (COLOR_SIDE, "Tendencia 4H: LATERAL")

def _day_change_from_15m(df15: pd.DataFrame, latest_price: float, tz_str: str = "America/New_York") -> Optional[float]:
    if df15 is None or len(df15) == 0:
        return None
    t = df15["time"]
    t_utc = t.dt.tz_localize("UTC") if (t.dt.tz is None) else t.dt.tz_convert("UTC")
    now_local = pd.Timestamp.now(tz=tz_str)
    day_start_local = now_local.normalize()
    day_start_utc = day_start_local.tz_convert("UTC")
    today = df15.loc[t_utc >= day_start_utc]
    if len(today) == 0:
        return None
    row0 = today.iloc[0]
    open_val = float(row0.get("open", row0["close"]))
    if open_val <= 0:
        return None
    last = float(latest_price)
    return (last - open_val) / open_val * 100.0

def _render_header(label: str, bg: str, badge_text: Optional[str] = None) -> io.BytesIO:
    """1200x220, color sólido, texto centrado y badge en esquina sup. derecha."""
    buf = io.BytesIO()
    if Image is None:
        from matplotlib import pyplot as plt
        import matplotlib
        matplotlib.use("Agg")
        fig = plt.figure(figsize=(12, 2.2), dpi=100)
        plt.axis("off"); plt.text(0.5, 0.5, label, ha="center", va="center")
        plt.savefig(buf, format="png"); plt.close(fig); buf.seek(0)
        return buf

    W, H = 1200, 220
    img = Image.new("RGB", (W, H), color=bg)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 46)
        badge_font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
        badge_font = ImageFont.load_default()

    # Texto centrado
    tw, th = draw.textbbox((0, 0), label, font=font)[2:]
    draw.text(((W - tw)//2, (H - th)//2), label, fill="#ffffff", font=font)

    # Badge (% diario)
    if badge_text:
        pad_x, pad_y = 18, 10
        bx, by = draw.textbbox((0, 0), badge_text, font=badge_font)[2:]
        bw = bx + pad_x * 2; bh = by + pad_y * 2
        x0 = W - bw - 20; y0 = 18
        x1 = x0 + bw; y1 = y0 + bh
        draw.rounded_rectangle([x0, y0, x1, y1], radius=14, fill="#111111")
        draw.text((x0 + pad_x, y0 + pad_y), badge_text, fill="#ffffff", font=badge_font)

    img.save(buf, format="PNG"); buf.seek(0)
    return buf


# ---------- job automático ----------
async def header_sync_job(ctx: ContextTypes.DEFAULT_TYPE):
    """
    Se ejecuta periódicamente por chat.
    Si la tendencia 4H cambió (o el % diario varió ≥ 0.3 pp), publica y fija un header silencioso.
    """
    app = ctx.application
    chat_id = ctx.job.chat_id if getattr(ctx, "job", None) else None
    if chat_id is None and getattr(ctx, "job", None) and ctx.job.data:
        chat_id = ctx.job.data.get("chat_id")
    if chat_id is None:
        return

    cfg = app.bot_data["config"]
    st = await repo.get_chat(cfg.db_path, chat_id) or ChatState(chat_id=chat_id)

    # Tendencia
    ctx4 = await get_4h_context(st.coin_id, st.symbol_okx)
    if not ctx4:
        return
    trend_up, trend_down = bool(ctx4["trend_up"]), bool(ctx4["trend_down"])
    state = "up" if trend_up else ("down" if trend_down else "side")

    # % diario (badge)
    badge_text = None
    op15 = await get_15m_oper(st.coin_id, st.symbol_okx)
    if op15 and "df" in op15:
        try:
            day_chg = _day_change_from_15m(op15["df"], latest_price=op15["price"], tz_str="America/New_York")
            if day_chg is not None:
                badge_text = f"{day_chg:+.2f}% hoy"
        except Exception:
            pass

    # Evitar publicar si no cambió (tendencia) o badge similar
    rt = app.bot_data.setdefault("runtime", {})
    key = ("header_state", chat_id)
    last = rt.get(key, {"state": None, "badge": None})
    need_update = (last["state"] != state)
    if (not need_update) and (badge_text is not None) and (last["badge"] is not None):
        try:
            last_val = float(str(last["badge"]).replace("% hoy", "").replace("+", "").strip())
            now_val = float(str(badge_text).replace("% hoy", "").replace("+", "").strip())
            if abs(now_val - last_val) >= 0.3:
                need_update = True
        except Exception:
            pass

    if not need_update:
        return

    color, label = _trend_color_and_label(trend_up, trend_down)
    buf = _render_header(label, color, badge_text=badge_text)
    msg = await ctx.bot.send_document(chat_id=chat_id, document=InputFile(buf, filename="header.png"), disable_notification=True)

    # Fijar si hay permisos
    try:
        me = await ctx.bot.get_chat_member(chat_id, ctx.bot.id)
        if me.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await ctx.bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id, disable_notification=True)
    except Exception:
        pass

    rt[key] = {"state": state, "badge": badge_text}

def _job_name(chat_id: int) -> str:
    return f"header:{chat_id}"

def ensure_header_job(app: Application, chat_id: int, interval_sec: int = 300):
    """Registra el job por chat si aún no existe (por defecto cada 5 min)."""
    name = _job_name(chat_id)
    try:
        jobs = app.job_queue.get_jobs_by_name(name)  # PTB ≥20
    except Exception:
        jobs = [j for j in app.job_queue.jobs() if j.name == name]
    if jobs:
        return
    app.job_queue.run_repeating(
        header_sync_job,
        interval=interval_sec,
        first=5,
        name=name,
        chat_id=chat_id,
        data={"chat_id": chat_id},
    )

def cancel_header_job(app: Application, chat_id: int):
    """Detiene el job automático para este chat."""
    name = _job_name(chat_id)
    try:
        jobs = app.job_queue.get_jobs_by_name(name)
    except Exception:
        jobs = [j for j in app.job_queue.jobs() if j.name == name]
    for j in jobs:
        j.schedule_removal()
    # limpiar estado runtime
    rt = app.bot_data.setdefault("runtime", {})
    rt.pop(("header_state", chat_id), None)


# ---------- comando /header ----------
async def header_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /header           → publica una vez y (si puede) fija silencioso.
    /header on        → activa auto-sync (y publica ahora).
    /header off       → desactiva auto-sync.
    /header status    → muestra el estado.
    """
    app = ctx.application
    cfg = app.bot_data["config"]
    chat_id = update.effective_chat.id

    # Estado actual del chat
    st = await repo.get_chat(cfg.db_path, chat_id) or ChatState(chat_id=chat_id)

    arg = (ctx.args[0].lower() if ctx.args else "").strip()

    if arg in ("on", "start", "auto"):
        ensure_header_job(app, chat_id, interval_sec=300)
        # Publicación inmediata
        ctx4 = await get_4h_context(st.coin_id, st.symbol_okx)
        if not ctx4:
            await update.message.reply_text("No pude calcular tendencia ahora.")
            return
        trend_up, trend_down = bool(ctx4["trend_up"]), bool(ctx4["trend_down"])
        color, label = _trend_color_and_label(trend_up, trend_down)
        # badge
        badge_text = None
        op15 = await get_15m_oper(st.coin_id, st.symbol_okx)
        if op15 and "df" in op15:
            dc = _day_change_from_15m(op15["df"], latest_price=op15["price"])
            if dc is not None:
                badge_text = f"{dc:+.2f}% hoy"
        buf = _render_header(label, color, badge_text=badge_text)
        msg = await update.message.reply_document(document=InputFile(buf, filename="header.png"), disable_notification=True)
        try:
            await ctx.bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id, disable_notification=True)
        except Exception:
            pass
        await update.message.reply_text("✅ Header auto-sync: <b>ACTIVADO</b>.", parse_mode="HTML")
        return

    if arg in ("off", "stop"):
        cancel_header_job(app, chat_id)
        await update.message.reply_text("🛑 Header auto-sync: <b>DESACTIVADO</b>.", parse_mode="HTML")
        return

    if arg in ("status", "estado"):
        name = _job_name(chat_id)
        try:
            jobs = app.job_queue.get_jobs_by_name(name)
        except Exception:
            jobs = [j for j in app.job_queue.jobs() if j.name == name]
        status = "ACTIVO" if jobs else "INACTIVO"
        await update.message.reply_text(f"ℹ️ Header auto-sync: <b>{status}</b>.", parse_mode="HTML")
        return

    # Sin argumentos: publicar una sola vez (no programa auto-sync)
    ctx4 = await get_4h_context(st.coin_id, st.symbol_okx)
    if not ctx4:
        await update.message.reply_text("No pude calcular tendencia ahora.")
        return
    trend_up, trend_down = bool(ctx4["trend_up"]), bool(ctx4["trend_down"])
    color, label = _trend_color_and_label(trend_up, trend_down)
    badge_text = None
    op15 = await get_15m_oper(st.coin_id, st.symbol_okx)
    if op15 and "df" in op15:
        dc = _day_change_from_15m(op15["df"], latest_price=op15["price"])
        if dc is not None:
            badge_text = f"{dc:+.2f}% hoy"
    buf = _render_header(label, color, badge_text=badge_text)
    msg = await update.message.reply_document(document=InputFile(buf, filename="header.png"), disable_notification=True)
    try:
        await ctx.bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id, disable_notification=True)
    except Exception:
        pass
    await update.message.reply_text("✅ Header actualizado (una vez).", parse_mode="HTML")



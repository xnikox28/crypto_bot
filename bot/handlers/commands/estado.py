# bot/handlers/commands/estado.py
from __future__ import annotations
import os
import io
import asyncio
from typing import Optional, Tuple, List

import pandas as pd
import pytz
from tzlocal import get_localzone
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from telegram import (
    Update, InputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, InputMediaDocument,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

from ...config import Config
from ...db import repo
from ...db.models import ChatState
from ..jobs import get_4h_context, get_15m_oper, get_5m_execution
from ...services.formatting import fmt_price
from ...services.levels import get_levels
from ...services.indicators import rsi as rsi_func, macd as macd_func


# ============== helpers numéricos/texto ==============
def _perc(a: float, b: float) -> float:
    return 0.0 if b == 0 else (a - b) / b * 100.0

def _near_pct(a: float, b: float, thr=0.3) -> bool:
    return abs(_perc(a, b)) <= thr

def _rsi_tag(x: float) -> str:
    return "🔥" if x >= 70 else ("❄️" if x <= 30 else "⚖️")

def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        wpx = draw.textlength(test, font=font)
        if wpx <= max_width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ============== helpers de dibujo/IO ==============
def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    preferred = [
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in preferred:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy, radius, fill=None, outline=None, width=1):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    except Exception:
        draw.rectangle(xy, fill=fill, outline=outline, width=width)

def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])
    except Exception:
        try:
            bbox = font.getbbox(text)
            return (bbox[2] - bbox[0], bbox[3] - bbox[1])
        except Exception:
            return (int(len(text) * font.size * 0.6), font.size)

def _drop_shadow(base_img: Image.Image, rect: Tuple[int,int,int,int], radius: int = 24, offset=(8, 10), alpha=90):
    x0, y0, x1, y1 = rect
    w, h = base_img.size
    shadow = Image.new("RGBA", (w, h), (0,0,0,0))
    sd = ImageDraw.Draw(shadow)
    _draw_rounded_rect(sd, (x0, y0, x1, y1), radius=radius, fill=(0,0,0,alpha), outline=None, width=0)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
    base_img.alpha_composite(shadow, dest=(offset[0], offset[1]))

def _draw_sparkline(draw: ImageDraw.ImageDraw, rect: Tuple[int,int,int,int], closes, color=(34,197,94,255), thickness=3):
    x0, y0, x1, y1 = rect
    w = max(1, x1 - x0); h = max(1, y1 - y0)
    if closes is None:
        return
    try:
        data = [float(v) for v in closes][-180:]  # ~45h en 15m
    except Exception:
        return
    if len(data) < 3:
        return
    vmin, vmax = min(data), max(data)
    if vmin == vmax:
        y = y0 + h // 2
        draw.line([(x0, y), (x1, y)], fill=color, width=thickness)
        return
    xs = [x0 + int(i * (w - 1) / (len(data) - 1)) for i in range(len(data))]
    ys = [y1 - int((v - vmin) * (h - 1) / (vmax - vmin)) for v in data]
    draw.line(list(zip(xs, ys)), fill=color, width=thickness, joint="curve")

def _badge(draw: ImageDraw.ImageDraw, xy: Tuple[int,int,int,int], text: str, bg: Tuple[int,int,int,int], font, fg=(255,255,255,255)):
    _draw_rounded_rect(draw, xy, radius=16, fill=bg, outline=None, width=0)
    tw, th = _text_size(draw, text, font)
    x0, y0, x1, y1 = xy
    draw.text((x0 + (x1-x0 - tw)//2, y0 + (y1-y0 - th)//2), text, font=font, fill=fg)

def _fresh_inputfile(buf: io.BytesIO, filename: str) -> InputFile:
    """Crea un InputFile con buffer nuevo desde el contenido actual (evita 'File must be non-empty')."""
    data = buf.getvalue()
    return InputFile(io.BytesIO(data), filename=filename)


# ============== lógica de señal ==============
def _strong_signal(
    trend_up: bool, trend_down: bool,
    rsi15: float, rsi5: float,
    macd15u: bool, macd5u: bool, macd_hist_up: bool,
    price: float, ema20: float, ema50: float, ema200: float,
    f618: Optional[float],
) -> Optional[str]:
    """Detección estricta de STRONG BUY / STRONG SELL."""
    if (trend_up and macd15u and macd5u and macd_hist_up and price > ema20 > ema50 > ema200
        and rsi15 >= 55 and rsi5 >= 50 and (f618 is None or price >= f618 * 1.0005)):
        return "STRONG BUY"
    if (trend_down and (not macd15u) and (not macd5u) and (not macd_hist_up) and price < ema20 < ema50 < ema200
        and rsi15 <= 45 and rsi5 <= 50 and (f618 is None or price <= f618 * 0.9995)):
        return "STRONG SELL"
    return None

def _moderate_signal(
    trend_up: bool, trend_down: bool,
    rsi15: float, rsi5: float,
    macd15u: bool, macd5u: bool,
    price: float, ema20: float, ema50: float, ema200: float,
) -> str:
    score = 0
    if trend_up: score += 2
    if trend_down: score -= 2
    score += 1 if macd15u else -1
    score += 1 if macd5u else -1
    score += 1 if price > ema20 else -1
    score += 1 if price > ema50 else -1
    score += 1 if price > ema200 else -1
    if rsi15 >= 60: score += 1
    if rsi15 < 45: score -= 1
    if rsi5 >= 55: score += 1
    if rsi5 < 45: score -= 1
    if score >= 2: return "BUY"
    if score <= -2: return "SELL"
    return "NEUTRAL"

def _reasons_text(
    decision: str,
    trend_up: bool, trend_down: bool,
    price: float, ema20: float, ema50: float,
    rsi15: float, rsi5: float,
    macd15u: bool, macd5u: bool,
    rsi15_series_ok_cross: bool,
    macd_hist_up: bool,
    f618_confirmed: bool,
) -> str:
    reasons = []
    if decision == "ESPERAR":
        if not trend_up: reasons.append("4H no alineado")
        if not (price > ema20 and price > ema50): reasons.append("precio/EMA20/50 no OK")
        if not macd15u: reasons.append("MACD 15m ↓")
        if not macd_hist_up: reasons.append("hist 15m no ↑")
        if rsi15 < 45: reasons.append("RSI 15m bajo")
        if not rsi15_series_ok_cross: reasons.append("RSI 15m no cruzó umbral")
        if not macd5u: reasons.append("MACD 5m ↓")
        if rsi5 < 45: reasons.append("RSI 5m bajo")
        if not f618_confirmed: reasons.append("F618 sin confirmación")
        prefix = "⏳ ESPERAR — "
    else:
        if trend_up: reasons.append("4H alineado")
        if price > ema20 and price > ema50: reasons.append("precio > EMA20/50")
        if macd15u: reasons.append("MACD 15m ↑")
        if macd_hist_up: reasons.append("hist 15m ↑")
        if rsi15 >= 50: reasons.append("RSI 15m OK")
        if rsi15_series_ok_cross: reasons.append("RSI 15m cruzó umbral")
        if macd5u: reasons.append("MACD 5m ↑")
        if rsi5 >= 50: reasons.append("RSI 5m OK")
        if f618_confirmed: reasons.append("F618 confirmado")
        prefix = "✅ ENTRAR YA — "
    return prefix + " · ".join(reasons[:9])


# ============== teclado & render wrappers ==============
def _kb_estado() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🔄 Refrescar", callback_data="state:refresh"),
            InlineKeyboardButton("❌ Cerrar",    callback_data="state:close"),
        ]]
    )


def _render_estado_image(
    coin: str,
    price_fmt: str,
    price_val: float,
    rsi4: float, rsi15: float, rsi5: float,
    macd15u: bool, macd5u: bool,
    ema20: float, ema50: float, ema200: float,
    last_ts_local_str: str,
    trend_up: bool, trend_down: bool,
    day_change_pct: Optional[float],
    reasons_line: str,
    closes_for_spark,
    theme: str = "light",
    decision_main: str = "ESPERAR",
    sec_signal: str = "NEUTRAL",
) -> Image.Image:
    W, H = 1280, 800
    M = 32
    R = 24

    # Paleta
    if theme == "dark":
        BG = (15, 23, 42)
        PANEL = (30, 41, 59, 255)
        COL_TEXT = (248, 250, 252, 255)
        COL_MUTED = (148, 163, 184, 255)
        SP_BG = (17, 24, 39, 255)
        SP_BORDER = (51, 65, 85, 255)
        SUBPANEL_BG = (31, 41, 55, 255)
        PANEL_FILL = (0, 0, 0, 60)
    else:
        BG = (248, 250, 252)
        PANEL = (255, 255, 255, 255)
        COL_TEXT = (17, 24, 39, 255)
        COL_MUTED = (75, 85, 99, 255)
        SP_BG = (245, 247, 250, 255)
        SP_BORDER = (203, 213, 225, 255)
        SUBPANEL_BG = (226, 232, 240, 255)
        PANEL_FILL = (255, 255, 255, 235)

    COL_GOOD = (27, 94, 32, 255)
    COL_BAD  = (183, 28, 28, 255)
    COL_WARN = (180, 83, 9, 255)
    COL_POS  = (34, 197, 94, 255)
    COL_NEG  = (239, 68, 68, 255)
    COL_NEU  = (107, 114, 128, 255)

    # Tendencia
    if trend_up:
        trend_badge_bg = COL_GOOD; trend_text = "ALCISTA"; spark_color = COL_POS
    elif trend_down:
        trend_badge_bg = COL_BAD; trend_text = "BAJISTA"; spark_color = COL_NEG
    else:
        trend_badge_bg = COL_WARN; trend_text = "LATERAL"; spark_color = COL_WARN

    # Lienzo
    img = Image.new("RGBA", (W, H), (*BG, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    # Marco + sombra (exterior depende de tendencia)
    outer = (M, M, W - M, H - M)
    _drop_shadow(img, outer, radius=R, offset=(8, 10), alpha=100)
    _draw_rounded_rect(draw, outer, radius=R, fill=None, outline=trend_badge_bg, width=12)

    inner = (M + 14, M + 14, W - M - 14, H - M - 14)
    _draw_rounded_rect(draw, inner, radius=R - 8, fill=PANEL, outline=None, width=0)

    # Fuentes
    f_h1 = _load_font(52)
    f_h2 = _load_font(38)
    f_h3 = _load_font(32)
    f_txt = _load_font(28)
    f_small = _load_font(24)
    f_badge = _load_font(28)
    f_decision = _load_font(42)
    f_badge2 = _load_font(30)

    # Layout base
    pad = 28
    left_x = inner[0] + pad
    right_x = inner[2] - pad
    top_y = inner[1] + pad

    # Header
    draw.text((left_x, top_y), f"{coin.upper()} — {price_fmt}", font=f_h1, fill=COL_TEXT)

    # Línea: Tendencia 4H + cápsula
    y = top_y + 66
    label = "Tendencia 4H:"
    draw.text((left_x, y), label, font=f_h2, fill=COL_TEXT)
    lbl_w = draw.textlength(label, font=f_h2)
    badge_h = 56
    badge_w = int(draw.textlength(trend_text, font=f_badge) + 40)
    bx = left_x + int(lbl_w) + 12
    by = y - 6
    _badge(draw, (bx, by, bx + badge_w, by + badge_h), trend_text, trend_badge_bg, f_badge)

    y = by + badge_h + 20

    # RSI
    rsi_line = f"RSI  4H {rsi4:4.1f} {_rsi_tag(rsi4)}   |   15M {rsi15:4.1f} {_rsi_tag(rsi15)}   |   5M {rsi5:4.1f} {_rsi_tag(rsi5)}"
    draw.text((left_x, y), rsi_line, font=f_h3, fill=COL_TEXT)
    y += 46

    # MACD (coloreado)
    macd_line = f"MACD  15M {'↑ Bullish' if macd15u else '↓ Bearish'}   |   5M {'↑ Bullish' if macd5u else '↓ Bearish'}"
    draw.text((left_x, y), macd_line, font=f_h3, fill=COL_TEXT)
    prefix = f"MACD  15M {'↑ ' if macd15u else '↓ '}"
    px, _ = _text_size(draw, prefix, f_h3)
    draw.text((left_x + px, y), "Bullish" if macd15u else "Bearish", font=f_h3, fill=COL_POS if macd15u else COL_NEG)
    prefix2 = prefix + ("Bullish" if macd15u else "Bearish") + f"   |   5M {'↑ ' if macd5u else '↓ '}"
    px2, _ = _text_size(draw, prefix2, f_h3)
    draw.text((left_x + px2, y), "Bullish" if macd5u else "Bearish", font=f_h3, fill=COL_POS if macd5u else COL_NEG)
    y += 54

    # EMAs (ΔP coloreado)
    draw.text((left_x, y), "Precio vs EMAs (15m)", font=f_h2, fill=COL_TEXT)
    y += 42

    def draw_ema_row(name: str, val: float):
        d = _perc(price_val, val)
        arrow = "≈" if _near_pct(price_val, val) else ("↑" if d > 0 else "↓")
        col = COL_NEU if arrow == "≈" else (COL_POS if d > 0 else COL_NEG)
        base = f"{name:<6} {val:,.6f}   ΔP "
        draw.text((left_x, y), base, font=f_txt, fill=COL_TEXT)
        base_w = draw.textlength(base, font=f_txt)
        draw.text((left_x + base_w, y), f"{arrow} {d:+5.2f}%", font=f_txt, fill=col)

    draw_ema_row("EMA20", ema20); y += 36
    draw_ema_row("EMA50", ema50); y += 36
    draw_ema_row("EMA200", ema200); y += 36

    # Última vela
    y += 8
    draw.text((left_x, y), f"Última vela 15m: {last_ts_local_str}", font=f_small, fill=COL_MUTED)

    # Var. diaria (arriba derecha)
    if day_change_pct is not None:
        vbadge_w, vbadge_h = 300, 64
        vbx = right_x - vbadge_w; vby = top_y
        vcol = COL_POS if day_change_pct >= 0 else COL_BAD
        _badge(draw, (vbx, vby, vbx + vbadge_w, vby + vbadge_h), f"Var. diaria: {day_change_pct:+.2f}%", vcol, _load_font(28))

    # ----------- Alturas reservadas para panel & razones -----------
    panel_h = 130
    reasons_h = 120
    bottom_padding = 28

    # Sparkline — más compacta y sin encimar
    spark_left = int(inner[0] + (inner[2] - inner[0]) * 0.60)
    spark_top  = top_y + 115
    spark_bottom_limit = inner[3] - (panel_h + reasons_h + bottom_padding + 18)
    spark_rect = (spark_left, spark_top, right_x, max(spark_top + 120, spark_bottom_limit))
    _draw_rounded_rect(draw, spark_rect, radius=14, fill=SP_BG, outline=SP_BORDER, width=2)
    _draw_sparkline(draw, spark_rect, closes_for_spark, color=spark_color, thickness=3)

    # Razones (abajo izquierda)
    reasons_x = left_x
    reasons_y = inner[3] - (panel_h + reasons_h)
    max_text_w = spark_left - left_x - 16
    for i, ln in enumerate(_wrap_text(draw, reasons_line, _load_font(28), max_text_w)[:3]):
        draw.text((reasons_x, reasons_y + i*34), ln, font=_load_font(28), fill=COL_TEXT)

    # Panel apilado de decisión
    def __draw_decision_panel():
        panel_w = 480
        bx2 = inner[2] - 28
        bx1 = bx2 - panel_w
        by2 = inner[3] - 28
        by1 = by2 - panel_h

        sig_upper = (sec_signal or "NEUTRAL").upper()
        if "SELL" in sig_upper:
            outline_col = COL_BAD
        elif "BUY" in sig_upper:
            outline_col = COL_GOOD
        else:
            outline_col = COL_NEU

        _draw_rounded_rect(draw, (bx1, by1, bx2, by2), radius=18, fill=PANEL_FILL, outline=outline_col, width=4)

        # Línea 1
        main_lbl = "ENTRAR YA" if decision_main.upper() == "ENTRAR YA" else "ESPERAR"
        tw, th = _text_size(draw, main_lbl, f_decision)
        draw.text((bx1 + (panel_w - tw)//2, by1 + 14), main_lbl, font=f_decision, fill=COL_TEXT)

        # Línea 2 (badge)
        kw = "NEUTRAL"; kw_col = COL_NEU; prefix = ""
        if "SELL" in sig_upper:
            kw = "SELL"; kw_col = COL_BAD
            if "STRONG" in sig_upper: prefix = "STRONG "
        elif "BUY" in sig_upper:
            kw = "BUY"; kw_col = COL_GOOD
            if "STRONG" in sig_upper: prefix = "STRONG "

        badge_text = f"{prefix}{kw}"
        badge_w = int(draw.textlength(badge_text, font=f_badge2) + 40)
        badge_h = 46
        bxx1 = bx1 + (panel_w - badge_w)//2
        bxy1 = by1 + th + 26
        bxx2 = bxx1 + badge_w
        bxy2 = bxy1 + badge_h
        _draw_rounded_rect(draw, (bxx1, bxy1, bxx2, bxy2), radius=12, fill=SUBPANEL_BG, outline=None, width=0)
        tx = bxx1 + 20
        ty = bxy1 + (badge_h - f_badge2.size)//2 - 2
        draw.text((tx, ty), badge_text, font=f_badge2, fill=kw_col)

    __draw_decision_panel()

    return img


async def _build_estado_payload(
    st: ChatState,
    ctx4: dict, op15: dict, ex5: dict,
    tz_local,
    last_ts_local_str: str,
    day_change_pct: Optional[float],
    reasons_line: str,
    theme: str,
    as_document: bool,
    decision_main: str,
    sec_signal: str,
) -> tuple[io.BytesIO, str, str]:
    """Devuelve (buffer, filename, caption). No envía nada."""
    price_now = float(op15["price"])
    rsi4 = float(ctx4["rsi"]); rsi15 = float(op15["rsi"]); rsi5 = float(ex5["rsi"])
    macd15u = bool(op15["macd_up"]); macd5u = bool(ex5["macd_up"])
    ema20 = float(op15["ema20"]); ema50 = float(op15["ema50"]); ema200 = float(op15["ema200"])
    trend_up, trend_down = bool(ctx4["trend_up"]), bool(ctx4["trend_down"])
    closes15 = op15["df"]["close"]

    img = _render_estado_image(
        coin=st.coin_id,
        price_fmt=fmt_price(st.symbol_okx, price_now),
        price_val=price_now,
        rsi4=rsi4, rsi15=rsi15, rsi5=rsi5,
        macd15u=macd15u, macd5u=macd5u,
        ema20=ema20, ema50=ema50, ema200=ema200,
        last_ts_local_str=last_ts_local_str,
        trend_up=trend_up, trend_down=trend_down,
        day_change_pct=day_change_pct,
        reasons_line=reasons_line,
        closes_for_spark=closes15.tolist(),
        theme=theme,
        decision_main=decision_main,
        sec_signal=sec_signal,
    )

    buf = io.BytesIO()
    if as_document:
        filename = f"estado_{st.coin_id.lower()}.png"
        img.save(buf, format="PNG")
    else:
        filename = f"estado_{st.coin_id.lower()}.jpg"
        img.convert("RGB").save(buf, format="JPEG", quality=95, optimize=True)
    buf.seek(0)

    caption = ("💡 Usa /grafica\npara velas 15m con Pivotes/Fibo.\n\n"
               "📏 Usa /niveles\npara Pivotes y Fibonacci.\n\n"
               "🔘 Atajos: /commands"
               )
    return buf, filename, caption


# ============== /estado ==============
async def estado_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /estado        -> usa el tema guardado (claro/oscuro) para este chat
    /estado doc    -> igual, pero como documento PNG (se puede refrescar también)
    """
    app = ctx.application
    cfg: Config = app.bot_data["config"]
    chat_id = update.effective_chat.id

    st = await repo.get_chat(cfg.db_path, chat_id) or ChatState(chat_id=chat_id)

    args = [a.lower() for a in (ctx.args or ())]
    as_document = any(a in ("doc", "documento", "file", "archivo") for a in args)
    theme = "dark" if bool(st.dark_mode) else "light"

    # Datasets
    ctx4, op15, ex5 = await asyncio.gather(
        get_4h_context(st.coin_id, st.symbol_okx),
        get_15m_oper(st.coin_id, st.symbol_okx),
        get_5m_execution(st.coin_id, st.symbol_okx),
    )
    if None in (ctx4, op15, ex5):
        await update.message.reply_text("❌ No pude obtener datos ahora. Intenta otra vez en 1–2 minutos.")
        return

    # Hora local
    try:
        ts = op15["df"]["time"].iloc[-1]
        ts_utc = pytz.UTC.localize(ts.to_pydatetime()) if getattr(ts, "tzinfo", None) is None else ts.astimezone(pytz.UTC)
        tz_env = os.getenv("BOT_TZ", None)
        tz_local = pytz.timezone(tz_env) if tz_env else get_localzone()
        ts_local = ts_utc.astimezone(tz_local)
        last_ts_local_str = f"{ts_local.strftime('%Y-%m-%d %H:%M %Z')}"
    except Exception:
        last_ts_local_str = "—"
        tz_local = get_localzone()

    # Var. diaria
    day_change_pct = None
    try:
        midnight_local = ts_local.replace(hour=0, minute=0, second=0, microsecond=0)  # type: ignore[name-defined]
        df = op15["df"].copy()
        df["time"] = pd.to_datetime(df["time"])
        if df["time"].dt.tz is None:
            df["time"] = df["time"].dt.tz_localize("UTC")
        df["time_local"] = df["time"].dt.tz_convert(str(tz_local))
        ref = df.iloc[(df["time_local"] - midnight_local).abs().argsort()[:1]]
        if not ref.empty:
            p0 = float(ref["close"].iloc[0])
            day_change_pct = _perc(float(op15["price"]), p0)
    except Exception:
        pass

    # Señales auxiliares
    closes15 = op15["df"]["close"]
    try:
        rsi_series = rsi_func(closes15.astype(float), 14).dropna()
        rsi15 = float(op15["rsi"])
        rsi5 = float(ex5["rsi"])
        rsi15_prev = float(rsi_series.iloc[-2]) if len(rsi_series) >= 2 else rsi15
        rsi15_cross_up = (rsi15_prev < 50 <= rsi15)
    except Exception:
        rsi15_cross_up = False
        rsi15 = float(op15["rsi"])
        rsi5 = float(ex5["rsi"])

    try:
        m, s, h = macd_func(closes15.astype(float))
        macd_hist_up = len(h.dropna()) >= 2 and (float(h.iloc[-1]) > float(h.iloc[-2]))
    except Exception:
        macd_hist_up = False

    # Niveles (para F618)
    try:
        levels = await get_levels(st.coin_id, st.symbol_okx)
        f618 = levels.get("F618") if levels else None
        f618_confirmed = (f618 is not None) and (float(op15["price"]) >= f618 * 1.001)
    except Exception:
        f618 = None
        f618_confirmed = False

    # Señal secundaria y decisión
    trend_up, trend_down = bool(ctx4["trend_up"]), bool(ctx4["trend_down"])
    macd15u, macd5u = bool(op15["macd_up"]), bool(ex5["macd_up"])
    sec_signal = _strong_signal(
        trend_up, trend_down, rsi15, rsi5, macd15u, macd5u, macd_hist_up,
        float(op15["price"]), float(op15["ema20"]), float(op15["ema50"]), float(op15["ema200"]), f618
    )
    if sec_signal is None:
        sec_signal = _moderate_signal(
            trend_up, trend_down, rsi15, rsi5, macd15u, macd5u,
            float(op15["price"]), float(op15["ema20"]), float(op15["ema50"]), float(op15["ema200"])
        )

    decision_main = "ENTRAR YA" if sec_signal in ("STRONG BUY", "BUY") else "ESPERAR"
    reasons_line = _reasons_text(
        decision=decision_main,
        trend_up=trend_up, trend_down=trend_down,
        price=float(op15["price"]), ema20=float(op15["ema20"]), ema50=float(op15["ema50"]),
        rsi15=rsi15, rsi5=rsi5,
        macd15u=macd15u, macd5u=macd5u,
        rsi15_series_ok_cross=rsi15_cross_up,
        macd_hist_up=macd_hist_up,
        f618_confirmed=f618_confirmed,
    )

    # Render a buffer (no enviar aún)
    buf, filename, caption = await _build_estado_payload(
        st, ctx4, op15, ex5, tz_local, last_ts_local_str, day_change_pct,
        reasons_line, theme, as_document,
        decision_main, sec_signal
    )

    # Envío con botones
    if as_document:
        await ctx.bot.send_document(
            chat_id=chat_id,
            document=_fresh_inputfile(buf, filename),
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=_kb_estado(),
            disable_content_type_detection=True,
        )
    else:
        await ctx.bot.send_photo(
            chat_id=chat_id,
            photo=_fresh_inputfile(buf, filename),
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=_kb_estado(),
        )


# ============== callbacks (refresh / close) ==============
async def estado_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Edita la MISMA imagen/documento de /estado (o borra y reenvía si falla)."""
    query = update.callback_query
    await query.answer()
    cfg: Config = ctx.application.bot_data["config"]
    chat_id = query.message.chat_id

    data = (query.data or "").strip()
    action = data.split(":")[1].lower() if ":" in data else ""

    st = await repo.get_chat(cfg.db_path, chat_id) or ChatState(chat_id=chat_id)

    if action == "close":
        try:
            await query.message.delete()
            await query.answer("Cerrado ✅", show_alert=False)
        except Exception:
            try:
                await query.edit_message_caption(caption="Estado cerrado.", parse_mode=ParseMode.HTML)
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
        return

    if action != "refresh":
        return

    # Recalcular datasets
    ctx4, op15, ex5 = await asyncio.gather(
        get_4h_context(st.coin_id, st.symbol_okx),
        get_15m_oper(st.coin_id, st.symbol_okx),
        get_5m_execution(st.coin_id, st.symbol_okx),
    )
    if None in (ctx4, op15, ex5):
        await query.answer("Sin datos. Intenta en un minuto.", show_alert=False)
        return

    # Hora local (como en /estado)
    try:
        ts = op15["df"]["time"].iloc[-1]
        ts_utc = pytz.UTC.localize(ts.to_pydatetime()) if getattr(ts, "tzinfo", None) is None else ts.astimezone(pytz.UTC)
        tz_env = os.getenv("BOT_TZ", None)
        tz_local = pytz.timezone(tz_env) if tz_env else get_localzone()
        ts_local = ts_utc.astimezone(tz_local)
        last_ts_local_str = f"{ts_local.strftime('%Y-%m-%d %H:%M %Z')}"
    except Exception:
        last_ts_local_str = "—"
        tz_local = get_localzone()

    # Var. diaria
    day_change_pct = None
    try:
        midnight_local = ts_local.replace(hour=0, minute=0, second=0, microsecond=0)  # type: ignore[name-defined]
        df = op15["df"].copy()
        df["time"] = pd.to_datetime(df["time"])
        if df["time"].dt.tz is None:
            df["time"] = df["time"].dt.tz_localize("UTC")
        df["time_local"] = df["time"].dt.tz_convert(str(tz_local))
        ref = df.iloc[(df["time_local"] - midnight_local).abs().argsort()[:1]]
        if not ref.empty:
            p0 = float(ref["close"].iloc[0])
            day_change_pct = _perc(float(op15["price"]), p0)
    except Exception:
        pass

    # Señales auxiliares (como en /estado)
    closes15 = op15["df"]["close"]
    try:
        rsi_series = rsi_func(closes15.astype(float), 14).dropna()
        rsi15 = float(op15["rsi"])
        rsi5 = float(ex5["rsi"])
        rsi15_prev = float(rsi_series.iloc[-2]) if len(rsi_series) >= 2 else rsi15
        rsi15_cross_up = (rsi15_prev < 50 <= rsi15)
    except Exception:
        rsi15_cross_up = False
        rsi15 = float(op15["rsi"])
        rsi5 = float(ex5["rsi"])

    try:
        m, s, h = macd_func(closes15.astype(float))
        macd_hist_up = len(h.dropna()) >= 2 and (float(h.iloc[-1]) > float(h.iloc[-2]))
    except Exception:
        macd_hist_up = False

    # Niveles (para F618)
    try:
        levels = await get_levels(st.coin_id, st.symbol_okx)
        f618 = levels.get("F618") if levels else None
        f618_confirmed = (f618 is not None) and (float(op15["price"]) >= f618 * 1.001)
    except Exception:
        f618 = None
        f618_confirmed = False

    # Señal y razones (igual que /estado)
    theme = "dark" if bool(st.dark_mode) else "light"
    trend_up, trend_down = bool(ctx4["trend_up"]), bool(ctx4["trend_down"])
    macd15u, macd5u = bool(op15["macd_up"]), bool(ex5["macd_up"])
    sec_signal = _strong_signal(
        trend_up, trend_down, rsi15, rsi5, macd15u, macd5u, macd_hist_up,
        float(op15["price"]), float(op15["ema20"]), float(op15["ema50"]), float(op15["ema200"]), f618
    )
    if sec_signal is None:
        sec_signal = _moderate_signal(
            trend_up, trend_down, rsi15, rsi5, macd15u, macd5u,
            float(op15["price"]), float(op15["ema20"]), float(op15["ema50"]), float(op15["ema200"])
        )
    decision_main = "ENTRAR YA" if sec_signal in ("STRONG BUY", "BUY") else "ESPERAR"
    reasons_line = _reasons_text(
        decision=decision_main,
        trend_up=trend_up, trend_down=trend_down,
        price=float(op15["price"]), ema20=float(op15["ema20"]), ema50=float(op15["ema50"]),
        rsi15=rsi15, rsi5=rsi5,
        macd15u=macd15u, macd5u=macd5u,
        rsi15_series_ok_cross=rsi15_cross_up,
        macd_hist_up=macd_hist_up,
        f618_confirmed=f618_confirmed,
    )

    as_document = bool(query.message.document) and not query.message.photo
    buf, filename, caption = await _build_estado_payload(
        st, ctx4, op15, ex5, tz_local, last_ts_local_str, day_change_pct,
        reasons_line, theme, as_document,
        decision_main, sec_signal
    )

    try:
        if as_document:
            media = InputMediaDocument(
                media=_fresh_inputfile(buf, filename),
                caption=caption,
                parse_mode=ParseMode.HTML
            )
        else:
            media = InputMediaPhoto(
                media=_fresh_inputfile(buf, filename),
                caption=caption,
                parse_mode=ParseMode.HTML
            )

        await query.edit_message_media(media=media, reply_markup=_kb_estado())

    except BadRequest as e:
        # Fallback/ignorables: variantes comunes + buffers agotados
        msg = str(e).lower()
        harmless = any(s in msg for s in [
            "message is not modified",
            "message content is not modified",
            "message to edit not found",
            "message can't be edited",
            "can't parse inputmedia",
            "media not found",
            "file must be non-empty",
        ])
        if harmless:
            try:
                await query.message.delete()
            except Exception:
                pass
            if as_document:
                await ctx.bot.send_document(
                    chat_id=chat_id,
                    document=_fresh_inputfile(buf, filename),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=_kb_estado(),
                    disable_content_type_detection=True,
                )
            else:
                await ctx.bot.send_photo(
                    chat_id=chat_id,
                    photo=_fresh_inputfile(buf, filename),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=_kb_estado(),
                )
        else:
            raise

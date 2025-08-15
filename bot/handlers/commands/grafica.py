# bot/handlers/commands/grafica.py
from __future__ import annotations
import asyncio
import io
from typing import Dict, Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter

from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ...config import Config
from ...db import repo
from ...db.models import ChatState
from ...services.indicators import ema
from ...services.levels import get_levels
from ...services.formatting import fmt_price, get_symbol_decimals
from ..jobs import get_4h_context, get_15m_oper, get_5m_execution


# ---------- colores ----------
C_EMA20 = "#6366f1"   # indigo
C_EMA50 = "#8b5cf6"   # violeta
C_EMA200= "#a855f7"   # violeta claro
C_PRICE = "#111827"   # gris muy oscuro

C_P     = "#9ca3af"   # pivote gris
C_S3    = "#ef4444"   # rojo
C_S2    = "#f97316"   # naranja
C_S1    = "#b45309"   # ámbar oscuro
C_R1R2  = "#06b6d4"   # cian
C_R3    = "#22c55e"   # verde

# Fibonacci
C_F236  = "#0ea5e9"   # celeste
C_F382  = "#22d3ee"   # cian claro
C_F500  = "#6b7280"   # gris medio
C_F618  = "#166534"   # verde oscuro (destacado)
C_F786  = "#14b8a6"   # teal


# ---------- helpers de pintado ----------
def _plot_candles(ax, df, color_up="#16a34a", color_down="#dc2626") -> None:
    """
    Dibuja velas OHLC sobre ax.
    df: DataFrame con columnas ['time','open','high','low','close'].
    """
    ts = pd.to_datetime(df["time"], errors="coerce")
    # Si trae tz, quitar tz para mdates
    try:
        if getattr(ts.dt, "tz", None) is not None:
            ts = ts.dt.tz_localize(None)
    except Exception:
        pass

    # Evitar FutureWarning: usar lista de Timestamps
    t = mdates.date2num(ts.tolist())

    o = df["open"].astype(float).to_numpy()
    h = df["high"].astype(float).to_numpy()
    l = df["low"].astype(float).to_numpy()
    c = df["close"].astype(float).to_numpy()

    # ancho de vela ~ 70% de 15 minutos (en días)
    width = (15.0 / 1440.0) * 0.7
    for x, open_, high_, low_, close_ in zip(t, o, h, l, c):
        up = close_ >= open_
        col = color_up if up else color_down
        # mecha
        ax.vlines(x, low_, high_, color=col, linewidth=1.0, alpha=0.9)
        # cuerpo
        y = min(open_, close_)
        height = abs(close_ - open_)
        if height == 0:
            # doji
            ax.hlines(y, x - width/2, x + width/2, color=col, linewidth=1.2)
        else:
            rect = Rectangle((x - width/2, y), width, height, facecolor=col, edgecolor=col, alpha=0.9)
            ax.add_patch(rect)

    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))


def _hline_labeled(ax, y: Optional[float], text: str, color: str, lw=0.95, ls="--",
                   box_fc="#ffffff", box_alpha=0.92, text_color="#111111") -> None:
    """
    Dibuja una línea horizontal y coloca una etiqueta con el texto (p.ej. 'R1 1.2345')
    pegada al borde derecho del gráfico (x en coords de ejes, y en coords de datos).
    """
    if y is None or not np.isfinite(y):
        return
    ax.axhline(y, color=color, linewidth=lw, linestyle=ls)
    trans = ax.get_yaxis_transform()  # x:[0..1], y:datos
    ax.text(
        0.99, y, text,
        transform=trans,
        ha="right", va="center",
        color=text_color,
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.25", fc=box_fc, ec=color, lw=0.8, alpha=box_alpha),
        clip_on=False,
    )


# ---------- plot principal ----------
def plot_chart(
    df_price, levels: Dict[str, float],
    ema20, ema50, ema200,
    title: str = "",
    inst_id: Optional[str] = None,
    show_full_fibo: bool = False,
    mark_idx: Optional[int] = None,   # (reservado; no dibujamos punto)
    dark: bool = False,
) -> io.BytesIO:
    """
    Dibuja 15m con:
      - Velas OHLC + EMA20/50/200
      - Pivotes P/S1/S2/S3/R1/R2/R3 con etiquetas de precio
      - F618 (y opcionalmente F236/F382/F500/F786) etiquetados
    """
    # recorta a últimas ~320 velas (≈ 3.3 días en 15m)
    df = df_price.tail(320).copy()

    fig = plt.figure(figsize=(10.6, 6.2), dpi=140)
    ax = plt.gca()

    # tema
    if dark:
        fig.patch.set_facecolor("#0f172a")  # slate-900
        ax.set_facecolor("#0b1220")         # casi negro
        grid_c = (1, 1, 1, 0.08)
        tick_c = "#e5e7eb"
        text_c = "#e5e7eb"
        label_box_fc = "#111827"
        label_text_c = "#ffffff"
        box_alpha = 0.9
    else:
        grid_c = (0, 0, 0, 0.1)
        tick_c = "#111827"
        text_c = "#111827"
        label_box_fc = "#ffffff"
        label_text_c = "#111111"
        box_alpha = 0.92

    for spine in ax.spines.values():
        spine.set_color(tick_c)
    ax.tick_params(colors=tick_c)
    ax.yaxis.label.set_color(tick_c)
    ax.xaxis.label.set_color(tick_c)

    # Candles o fallback
    if {"open","high","low","close"}.issubset(df.columns):
        _plot_candles(ax, df)
    else:
        ax.plot(pd.to_datetime(df["time"]), df["close"], label="Precio", linewidth=1.4, color=C_PRICE)

    # EMAs
    t = pd.to_datetime(df["time"])
    ax.plot(t, ema20.tail(len(df)), label="EMA20", linewidth=1.2, color=C_EMA20)
    ax.plot(t, ema50.tail(len(df)), label="EMA50", linewidth=1.1, color=C_EMA50)
    ax.plot(t, ema200.tail(len(df)), label="EMA200", linewidth=1.0, color=C_EMA200)

    # Formato de decimales según símbolo
    c_last = float(df["close"].iloc[-1])
    dp = 4
    if inst_id:
        try:
            dp = get_symbol_decimals(inst_id, c_last)
        except Exception:
            dp = 4
    fmtv = lambda v: fmt_price(inst_id or "", v)

    # Pivotes + etiquetas
    if levels:
        # Soportes (abajo)
        _hline_labeled(ax, levels.get("S3"), f"S3 {fmtv(levels.get('S3'))}", C_S3,
                       box_fc=label_box_fc, text_color=label_text_c, box_alpha=box_alpha)
        _hline_labeled(ax, levels.get("S2"), f"S2 {fmtv(levels.get('S2'))}", C_S2,
                       box_fc=label_box_fc, text_color=label_text_c, box_alpha=box_alpha)
        _hline_labeled(ax, levels.get("S1"), f"S1 {fmtv(levels.get('S1'))}", C_S1,
                       box_fc=label_box_fc, text_color=label_text_c, box_alpha=box_alpha)

        # Punto pivote (gris)
        _hline_labeled(ax, levels.get("P"), f"P {fmtv(levels.get('P'))}", C_P,
                       lw=0.8, ls=":", box_fc=label_box_fc, text_color=label_text_c, box_alpha=box_alpha)

        # Resistencias (arriba)
        _hline_labeled(ax, levels.get("R1"), f"R1 {fmtv(levels.get('R1'))}", C_R1R2,
                       box_fc=label_box_fc, text_color=label_text_c, box_alpha=box_alpha)
        _hline_labeled(ax, levels.get("R2"), f"R2 {fmtv(levels.get('R2'))}", C_R1R2,
                       box_fc=label_box_fc, text_color=label_text_c, box_alpha=box_alpha)
        _hline_labeled(ax, levels.get("R3"), f"R3 {fmtv(levels.get('R3'))}", C_R3,
                       box_fc=label_box_fc, text_color=label_text_c, box_alpha=box_alpha)

        # Fibonacci
        if "F618" in levels and levels["F618"] is not None:
            _hline_labeled(ax, levels["F618"], f"F618 {fmtv(levels['F618'])}", C_F618,
                           lw=1.8, ls="-.", box_fc=label_box_fc, text_color=label_text_c, box_alpha=box_alpha)

        if show_full_fibo:
            for key, color in (
                ("F236", C_F236),
                ("F382", C_F382),
                ("F500", C_F500),
                ("F786", C_F786),
            ):
                if key in levels and levels[key] is not None:
                    _hline_labeled(ax, levels[key], f"{key} {fmtv(levels[key])}", color,
                                   lw=1.2, ls="-.", box_fc=label_box_fc, text_color=label_text_c, box_alpha=box_alpha)

    ax.set_title(title, color=text_c)
    ax.set_xlabel("Tiempo"); ax.set_ylabel("USD")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: f"{v:.{dp}f}"))
    ax.grid(True, alpha=0.25, color=grid_c)

    fig.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


# ---------- /grafica ----------
async def grafica_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Gráfico 15m con velas, EMAs, Pivotes y Fibo etiquetados.
    - /grafica → sólo F618
    - /grafica full  (o 'fibo full') → F236/F382/F500/F618/F786
    Tema: se usa el guardado por chat con /darkmode.
    """
    app = ctx.application
    cfg: Config = app.bot_data["config"]
    chat_id = update.effective_chat.id

    st = await repo.get_chat(cfg.db_path, chat_id) or ChatState(chat_id=chat_id)

    # flags de argumentos (solo para Fibo)
    args = [a.lower() for a in (ctx.args or ())]
    show_full_fibo = any(a in ("fibo", "full", "todo", "all") for a in args)

    # datasets en paralelo
    ctx4_task = asyncio.create_task(get_4h_context(st.coin_id, st.symbol_okx))
    op15_task = asyncio.create_task(get_15m_oper(st.coin_id, st.symbol_okx))
    ex5_task  = asyncio.create_task(get_5m_execution(st.coin_id, st.symbol_okx))
    lev_task  = asyncio.create_task(get_levels(st.coin_id, st.symbol_okx))

    ctx4, op15, ex5, levels = await asyncio.gather(ctx4_task, op15_task, ex5_task, lev_task)
    if None in (ctx4, op15, ex5):
        await update.message.reply_text("No pude generar la gráfica ahora.")
        return

    # Series y EMAs (y recorte si precisión ON)
    df_all = op15["df"]
    precision_on: bool = bool(getattr(st, "precision_on", 0))
    # Si precisión ON, no dibujamos la vela en curso (última) para que el plot coincida
    df = df_all.iloc[:-1].copy() if (precision_on and len(df_all) >= 2) else df_all.copy()

    ema20s = ema(df["close"], 20); ema50s = ema(df["close"], 50); ema200s = ema(df["close"], 200)

    # Render en hilo (no bloquea loop)
    buf = await asyncio.to_thread(
        plot_chart,
        df,                      # <- usar df ya recortado si precisión ON
        (levels or {}),
        ema20s, ema50s, ema200s,
        title=f"{st.coin_id.upper()} — 15m · Velas, Pivotes & Fibo",
        inst_id=st.symbol_okx,
        show_full_fibo=show_full_fibo,
        mark_idx=None,                 # no dibujamos punto
        dark=bool(st.dark_mode),       # tema global
    )

    # Caption: coherente con precisión
    price_for_caption = float(df["close"].iloc[-1]) if precision_on else float(op15["price"])

    rsi4 = float(ctx4["rsi"])
    rsi15 = float(op15["rsi"])
    rsi5 = float(ex5["rsi"])
    macd15u = bool(op15["macd_up"])
    macd5u = bool(ex5["macd_up"])

    trend = "📈 Alcista" if ctx4["trend_up"] else ("📉 Bajista" if ctx4["trend_down"] else "➖ Lateral")
    macd_txt = f"MACD 15m {'↑' if macd15u else '↓'} · 5m {'↑' if macd5u else '↓'}"
    rsi_txt = f"RSI 4H/15M/5M: {rsi4:.1f}/{rsi15:.1f}/{rsi5:.1f}"
    fibo_hint = "Fibo: F618" if not show_full_fibo else "Fibo: F236 · F382 · F500 · F618 · F786"

    caption = (
        f"💹 {st.coin_id.upper()} 15m — Precio {fmt_price(st.symbol_okx, price_for_caption)}"
        f"{' (vela cerrada)' if precision_on else ''}\n"
        f"{trend} | {rsi_txt}\n"
        f"{macd_txt} | {fibo_hint}\n"
        f"📌 Tip: usa <code>/grafica full</code> para ver todos los niveles\n"
        f"🎨 Tema: {'🌙 Oscuro' if st.dark_mode else '☀️ Claro'} → /darkmode\n"
        f"🧭 Precisión: {'ON' if precision_on else 'OFF'} → /precision on|off\n"
        f"ℹ️ Usa /niveles para ver Pivotes y Fibonacci con valores"
    )

    await ctx.bot.send_photo(
        chat_id=chat_id,
        photo=InputFile(buf, filename=f"grafica_{st.coin_id.lower()}_15m.png"),
        caption=caption,
        parse_mode=ParseMode.HTML,
    )

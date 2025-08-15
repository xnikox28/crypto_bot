from __future__ import annotations
import io
from typing import Dict, Optional

import matplotlib
matplotlib.use("Agg")  # backend sin GUI
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, AutoMinorLocator

import pandas as pd

from .formatting import fmt_price, get_symbol_decimals

# Paleta solicitada
LEVEL_COLORS = {
    "S3":  "#d32f2f",  # rojo
    "S2":  "#fb8c00",  # naranja
    "S1":  "#f57c00",  # naranja oscuro
    "P":   "#9e9e9e",  # gris
    "R1":  "#00bcd4",  # cian
    "R2":  "#26c6da",  # cian claro
    "R3":  "#2e7d32",  # verde
    "F618":"#1b5e20",  # verde oscuro
}

def _fmt(inst_id: Optional[str], v: float) -> str:
    return fmt_price(inst_id or "", float(v))

def plot_chart(
    df_price: pd.DataFrame,
    levels: Dict[str, float],
    ema20: pd.Series,
    ema50: pd.Series,
    ema200: pd.Series,
    title: str = "",
    inst_id: Optional[str] = None,
    max_bars: int = 220,
    draw_labels: bool = True,
) -> io.BytesIO:
    """
    Renderiza la gráfica 15m con EMAs y niveles.
    - inst_id: si se provee (ej. 'BONK-USDT'), el eje Y y labels usan tickSz real de OKX.
               si es None, se usa un fallback por magnitud del precio.
    - max_bars: últimos N puntos a mostrar.
    - draw_labels: dibuja pequeñas etiquetas de texto sobre cada nivel.
    """
    if df_price is None or len(df_price) == 0:
        raise ValueError("df_price vacío")

    # Ventana
    df = df_price.tail(max_bars).copy()
    t = df["time"]
    close = df["close"]

    # Decimales recomendados (para ejes y textos)
    try:
        sample_price = float(close.iloc[-1])
    except Exception:
        sample_price = None
    dp = get_symbol_decimals(inst_id or "", sample_price)

    # --- Figura
    fig = plt.figure(figsize=(9.2, 5.2), dpi=150)
    ax = plt.gca()

    # Serie principal + EMAs
    ax.plot(t, close, label="Precio", linewidth=1.4)
    ax.plot(t, ema20.tail(len(df)), label="EMA20", linewidth=1.0, alpha=0.95)
    ax.plot(t, ema50.tail(len(df)), label="EMA50", linewidth=1.0, alpha=0.95)
    ax.plot(t, ema200.tail(len(df)), label="EMA200", linewidth=1.0, alpha=0.95)

    # Niveles horizontales
    def hline(key: str, lw=1.0, ls="--"):
        if key in levels and pd.notna(levels[key]):
            ax.axhline(levels[key], color=LEVEL_COLORS.get(key, "#9e9e9e"), linewidth=lw, linestyle=ls, label=key)
            if draw_labels:
                # etiqueta pequeña al borde derecho
                ax.text(
                    1.002, levels[key],
                    f" {key} {_fmt(inst_id, levels[key])}",
                    transform=ax.get_yaxis_transform(),
                    va="center", ha="left",
                    fontsize=8, color=LEVEL_COLORS.get(key, "#9e9e9e"),
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7)
                )

    # Pivotes
    for k in ("S3", "S2", "S1", "P", "R1", "R2", "R3"):
        hline(k, lw=1.0, ls="--")

    # Fibo 0.618, si existe, más notorio
    if "F618" in levels and pd.notna(levels["F618"]):
        ax.axhline(levels["F618"], color=LEVEL_COLORS["F618"], linewidth=1.3, linestyle="-.", label="F618")
        if draw_labels:
            ax.text(
                1.002, levels["F618"],
                f" F618 {_fmt(inst_id, levels['F618'])}",
                transform=ax.get_yaxis_transform(),
                va="center", ha="left",
                fontsize=8, color=LEVEL_COLORS["F618"],
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.75)
            )

    # Estética
    ax.set_title(title, fontsize=12, pad=10)
    ax.set_xlabel("Tiempo", fontsize=10)
    ax.set_ylabel("Precio", fontsize=10)

    # Eje Y con formateador por símbolo/decimales
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.{dp}f}"))
    ax.yaxis.set_minor_locator(AutoMinorLocator(2))

    # Grid
    ax.grid(True, which="major", alpha=0.28)
    ax.grid(True, which="minor", alpha=0.12)

    # Leyenda compacta
    ax.legend(fontsize=8, loc="upper left", ncol=4, frameon=False)

    # Márgenes
    plt.tight_layout()

    # Guardar a buffer
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf

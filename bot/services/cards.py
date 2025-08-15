from __future__ import annotations
import io
import matplotlib
matplotlib.use("Agg")  # backend sin GUI
import matplotlib.pyplot as plt

def status_card(text: str, bg: str = "#1b5e20", fg: str = "#ffffff") -> io.BytesIO:
    """
    Genera un banner pequeño con fondo 'bg' y texto 'text'.
    Sugerencias:
      - Alcista: #1b5e20 (dark green)
      - Bajista: #b71c1c (dark red)
      - Lateral: #b45309 (amber/dark)
    """
    # Figura con facecolor ya en el color deseado
    fig = plt.figure(figsize=(4.6, 1.0), dpi=220)
    fig.patch.set_facecolor(bg)
    fig.patch.set_alpha(1.0)

    # Eje a pantalla completa
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()

    # “Pinta” el fondo explícitamente dentro del eje
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, color=bg))

    # Texto centrado
    ax.text(
        0.5, 0.5, text,
        ha="center", va="center",
        color=fg, fontsize=16, fontweight="bold"
    )

    # Guardar preservando facecolor y sin márgenes
    buf = io.BytesIO()
    plt.savefig(
        buf, format="png",
        facecolor=fig.get_facecolor(),
        edgecolor="none",
        bbox_inches="tight", pad_inches=0
    )
    plt.close(fig)
    buf.seek(0)
    return buf



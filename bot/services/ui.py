from __future__ import annotations
import io
from typing import Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None  # si no está pillow, devolvemos None en status_card

# Colores por defecto
DEFAULT_BG = "#1b5e20"  # verde oscuro
DEFAULT_FG = "#ffffff"  # texto blanco

def _parse_color(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))

def status_card(
    text: str,
    bg: str = DEFAULT_BG,
    fg: str = DEFAULT_FG,
    badge_text: Optional[str] = None,
    badge_bg: Optional[str] = None,
    size: Tuple[int, int] = (980, 180),
) -> io.BytesIO:
    """
    Renderiza una tarjetita simple con:
      - banda superior de color `bg`
      - texto centrado `text`
      - opcional: badge en esquina superior derecha con `badge_text` y fondo `badge_bg`
    Devuelve BytesIO PNG. Si Pillow no está, devuelve una imagen en blanco.
    """
    W, H = size
    buf = io.BytesIO()

    if Image is None:
        # Fallback: PNG en blanco para no romper envío
        from matplotlib import pyplot as plt
        import matplotlib
        matplotlib.use("Agg")
        fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
        plt.axis("off")
        plt.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf

    img = Image.new("RGB", (W, H), color=_parse_color(bg))
    draw = ImageDraw.Draw(img)

    # Tipografías
    try:
        # Si tienes ttf en el entorno, puedes poner su ruta aquí
        title_font = ImageFont.truetype("arial.ttf", 40)
        badge_font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        title_font = ImageFont.load_default()
        badge_font = ImageFont.load_default()

    # Texto principal centrado
    tw, th = draw.textbbox((0, 0), text, font=title_font)[2:]
    cx = (W - tw) // 2
    cy = (H - th) // 2
    draw.text((cx, cy), text, fill=_parse_color(fg), font=title_font)

    # Badge (si aplica)
    if badge_text:
        pad_x, pad_y = 18, 10
        bx, by = draw.textbbox((0, 0), badge_text, font=badge_font)[2:]
        bw = bx + pad_x * 2
        bh = by + pad_y * 2
        # esquina superior derecha con pequeño margen
        x0 = W - bw - 20
        y0 = 18
        x1 = x0 + bw
        y1 = y0 + bh
        # rect redondeado
        draw.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=_parse_color(badge_bg or "#333333"))
        # texto centrado en el badge
        tx = x0 + pad_x
        ty = y0 + pad_y
        draw.text((tx, ty), badge_text, fill=_parse_color("#ffffff"), font=badge_font)

    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

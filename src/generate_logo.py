"""
Platform Bigdata — Corporate Logo / Badge Generator
Generates a professional dark-slate badge used in:
  - PDF report headers
  - Telegram header images
  - Documentation covers
"""

import os
import math
from PIL import Image, ImageDraw, ImageFont

OUTPUT_PATH = "output/platform_bigdata_logo.png"


def _try_font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def generate_logo(output_path: str = OUTPUT_PATH) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Canvas — HD output: 1920×480, draw at 4x scale for crisp anti-aliasing
    W, H = 1920, 480
    scale = 4  # internal drawing scale for pixel-perfect sharpness
    W2, H2 = W * scale, H * scale

    img = Image.new("RGB", (W2, H2), color="#0B0F1A")
    draw = ImageDraw.Draw(img)

    # ── Color palette (SOTERRA-style: dark navy + orange) ──────────
    C_BG        = "#0B0F1A"   # Very dark navy — background
    C_PANEL     = "#080C14"   # Even darker — left icon panel
    C_ACCENT    = "#E85D04"   # Burnt orange — brand accent
    C_ACCENT_DIM= "#7C2D12"   # Dark orange — subtle accent
    C_WHITE     = "#F8FAFC"   # Near white — main text
    C_MUTED     = "#94A3B8"   # Slate 400 — muted text
    C_BORDER    = "#1E2A3A"   # Very dark border
    C_DIVIDER   = "#1A2030"   # subtle divider

    s = scale

    # ── Left accent stripe ─────────────────────────────────────────
    draw.rectangle([(0, 0), (6 * s, H2)], fill=C_ACCENT)

    # ── Left icon panel ────────────────────────────────────────────
    PANEL_W = 220 * s
    draw.rectangle([(6 * s, 0), (PANEL_W, H2)], fill=C_PANEL)

    # Icon: stylized data-node hexagon cluster
    cx, cy = 113 * s, 140 * s
    r_outer = 52 * s
    r_inner = 28 * s
    r_dot   = 7 * s
    r_ring  = 38 * s

    # Outer hex ring (muted)
    for i in range(6):
        angle = math.radians(60 * i - 30)
        x = cx + r_outer * math.cos(angle)
        y = cy + r_outer * math.sin(angle)
        draw.ellipse([(x - r_dot, y - r_dot), (x + r_dot, y + r_dot)], fill=C_ACCENT_DIM)

    # Connecting lines between hex nodes
    for i in range(6):
        a1 = math.radians(60 * i - 30)
        a2 = math.radians(60 * ((i + 1) % 6) - 30)
        x1 = cx + r_outer * math.cos(a1)
        y1 = cy + r_outer * math.sin(a1)
        x2 = cx + r_outer * math.cos(a2)
        y2 = cy + r_outer * math.sin(a2)
        draw.line([(x1, y1), (x2, y2)], fill=C_BORDER, width=s)

    # Spokes from center to hex nodes (alternating)
    for i in [0, 2, 4]:
        angle = math.radians(60 * i - 30)
        x2 = cx + r_ring * math.cos(angle)
        y2 = cy + r_ring * math.sin(angle)
        draw.line([(cx, cy), (x2, y2)], fill=C_ACCENT_DIM, width=s)

    # Inner hex nodes (accent)
    for i in range(6):
        angle = math.radians(60 * i - 30)
        x = cx + r_outer * math.cos(angle)
        y = cy + r_outer * math.sin(angle)
        r = r_dot - s
        draw.ellipse([(x - r, y - r), (x + r, y + r)], fill=C_ACCENT if i % 2 == 0 else C_MUTED)

    # Center dot
    draw.ellipse(
        [(cx - r_inner, cy - r_inner), (cx + r_inner, cy + r_inner)],
        fill=C_ACCENT_DIM, outline=C_ACCENT, width=2 * s
    )
    draw.ellipse(
        [(cx - 10 * s, cy - 10 * s), (cx + 10 * s, cy + 10 * s)],
        fill=C_ACCENT
    )

    # ── Vertical divider ───────────────────────────────────────────
    div_x = PANEL_W + 1
    draw.rectangle([(div_x, 30 * s), (div_x + s, (H - 30) * s)], fill=C_BORDER)

    # ── Typography ─────────────────────────────────────────────────
    FONT_PATHS = {
        "bold": "C:/Windows/Fonts/segoeuib.ttf",
        "regular": "C:/Windows/Fonts/segoeui.ttf",
        "light": "C:/Windows/Fonts/segoeuil.ttf",
    }

    f_company  = _try_font(FONT_PATHS["bold"],    30 * s)
    f_tagline  = _try_font(FONT_PATHS["regular"], 11 * s)
    f_badge    = _try_font(FONT_PATHS["bold"],    8 * s)
    f_ver      = _try_font(FONT_PATHS["light"],   9 * s)

    text_x = (PANEL_W + 28 * s)
    name_y  = 68 * s

    # Company name — "Platform Bigdata"
    draw.text((text_x, name_y), "Platform Bigdata", font=f_company, fill=C_WHITE)

    # Tagline
    draw.text(
        (text_x, name_y + 46 * s),
        "Enterprise Infrastructure & AIOps Monitoring Platform",
        font=f_tagline, fill=C_MUTED
    )

    # Small horizontal rule under tagline
    rule_y = name_y + 68 * s
    draw.rectangle([(text_x, rule_y), (text_x + 420 * s, rule_y + s)], fill=C_BORDER)

    # Badges row
    badges = [
        ("Kubernetes", "#2A1200", "#F97316"),
        ("Longhorn",   "#1A0F00", "#FB923C"),
        ("Prometheus", "#1A1200", "#FBBF24"),
        ("AIOps",      "#2A0E00", "#EA580C"),
    ]
    bx = text_x
    by = rule_y + 12 * s
    for label, bg, fg in badges:
        bw_bb = draw.textbbox((0, 0), label, font=f_badge)
        bw = bw_bb[2] - bw_bb[0] + 14 * s
        bh = 18 * s
        draw.rounded_rectangle([(bx, by), (bx + bw, by + bh)], radius=4 * s, fill=bg)
        draw.text((bx + 7 * s, by + 3 * s), label, font=f_badge, fill=fg)
        bx += bw + 8 * s

    # Version / status
    draw.text(
        (text_x, by + 30 * s),
        "v2.5  ·  Production Ready  ·  Confidential",
        font=f_ver, fill=C_MUTED
    )

    # ── Top-right: accent mark ─────────────────────────────────────
    tr_x = W2 - 36 * s
    draw.rectangle([(tr_x, 0), (W2, 4 * s)], fill=C_ACCENT)

    # ── Bottom border line ─────────────────────────────────────────
    draw.rectangle([(0, H2 - 2 * s), (W2, H2)], fill=C_BORDER)

    # ── Save ───────────────────────────────────────────────────────
    final = img.resize((W, H), Image.LANCZOS)
    final.save(output_path, "PNG", quality=95)
    print(f"Logo saved: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_logo()


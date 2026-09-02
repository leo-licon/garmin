"""
Genera los íconos PNG para la PWA.
Corre una sola vez: python3 generate_icons.py
Requiere: pip install Pillow
"""
from PIL import Image, ImageDraw, ImageFont
import os

SIZES = [192, 512, 180]  # 180 = apple-touch-icon
OUT = "app/static/icons"
os.makedirs(OUT, exist_ok=True)

def make_icon(size):
    img = Image.new("RGB", (size, size), "#0a0e17")
    draw = ImageDraw.Draw(img)

    # Fondo círculo accent
    margin = size * 0.12
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill="#00d4ff"
    )

    # Letra G centrada
    font_size = int(size * 0.45)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except:
        font = ImageFont.load_default()

    text = "G"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1]
    draw.text((x, y), text, fill="#0a0e17", font=font)

    return img

for size in SIZES:
    name = "apple-touch-icon.png" if size == 180 else f"icon-{size}.png"
    make_icon(size).save(f"{OUT}/{name}")
    print(f"✓ {name}")

print("Íconos generados en app/static/icons/")

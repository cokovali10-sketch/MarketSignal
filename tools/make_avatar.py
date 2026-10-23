"""Генерация аватарки бота MarketSignal (512x512 PNG)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
# --- константы вынесены FORGE refactor ---
CONST_4 = 4
CONST_6 = 6
CONST_12 = 12
CONST_18 = 18
CONST_28 = 28
CONST_41 = 41
CONST_132 = 132
CONST_150 = 150
CONST_240 = 240
CONST_255 = 255


OUT = Path(__file__).resolve().parent.parent / "assets" / "avatar.png"
SIZE = 512


def _gradient(size, top, bottom):
    base = Image.new("RGB", size, top)
    top_img = Image.new("RGB", size, bottom)
    mask = Image.new("L", size)
    mask_draw = ImageDraw.Draw(mask)
    for y in range(size[1]):
        alpha = int(CONST_255 * y / size[1])
        mask_draw.line([(0, y), (size[0], y)], fill=alpha)
    return Image.composite(base, top_img, mask)


def _font(size):
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    img = _gradient((SIZE, SIZE), (46, 26, 120), (21, 101, 192))
    draw = ImageDraw.Draw(img, "RGBA")

    # Сетка фона
    for g in range(0, SIZE, 64):
        draw.line([(g, 0), (g, SIZE)], fill=(CONST_255, CONST_255, CONST_255, CONST_12), width=1)
        draw.line([(0, g), (SIZE, g)], fill=(CONST_255, CONST_255, CONST_255, CONST_12), width=1)

    # Иконка: канбан-диаграмма (график вверх)
    pts = [(70, 390), (CONST_150, 330), (230, 350), (310, 250), (400, CONST_150)]
    draw.line(pts, fill=(CONST_255, CONST_255, CONST_255, 220), width=CONST_12, joint="curve")

    # Точки на графике
    for x, y in pts:
        draw.ellipse([x - 10, y - 10, x + 10, y + 10], fill=(CONST_41, CONST_240, CONST_132, CONST_255))

    # Стрелка вверх в конце
    arrow_x, arrow_y = pts[-1]
    draw.polygon(
        [
            (arrow_x - CONST_28, arrow_y + CONST_18),
            (arrow_x + CONST_18, arrow_y - CONST_28),
            (arrow_x + 34, arrow_y - CONST_4),
            (arrow_x - CONST_4, arrow_y + 42),
        ],
        fill=(CONST_41, CONST_240, CONST_132, CONST_255),
    )

    # Круглая маска-рамка
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    o_draw = ImageDraw.Draw(overlay)
    o_draw.ellipse([CONST_6, CONST_6, SIZE - CONST_6, SIZE - CONST_6], outline=(CONST_255, CONST_255, CONST_255, 40), width=CONST_4)
    img = Image.alpha_composite(img.convert("RGBA"), overlay)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT, "PNG")
    print(f"Avatar saved: {OUT}")


if __name__ == "__main__":
    main()

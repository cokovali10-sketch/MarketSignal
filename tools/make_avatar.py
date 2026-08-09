"""Генерация аватарки бота MarketSignal (512x512 PNG)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "assets" / "avatar.png"
SIZE = 512


def _gradient(size, top, bottom):
    base = Image.new("RGB", size, top)
    top_img = Image.new("RGB", size, bottom)
    mask = Image.new("L", size)
    mask_draw = ImageDraw.Draw(mask)
    for y in range(size[1]):
        alpha = int(255 * y / size[1])
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
        draw.line([(g, 0), (g, SIZE)], fill=(255, 255, 255, 12), width=1)
        draw.line([(0, g), (SIZE, g)], fill=(255, 255, 255, 12), width=1)

    # Иконка: канбан-диаграмма (график вверх)
    pts = [(70, 390), (150, 330), (230, 350), (310, 250), (400, 150)]
    draw.line(pts, fill=(255, 255, 255, 220), width=12, joint="curve")

    # Точки на графике
    for x, y in pts:
        draw.ellipse([x - 10, y - 10, x + 10, y + 10], fill=(41, 240, 132, 255))

    # Стрелка вверх в конце
    arrow_x, arrow_y = pts[-1]
    draw.polygon(
        [
            (arrow_x - 28, arrow_y + 18),
            (arrow_x + 18, arrow_y - 28),
            (arrow_x + 34, arrow_y - 4),
            (arrow_x - 4, arrow_y + 42),
        ],
        fill=(41, 240, 132, 255),
    )

    # Круглая маска-рамка
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    o_draw = ImageDraw.Draw(overlay)
    o_draw.ellipse([6, 6, SIZE - 6, SIZE - 6], outline=(255, 255, 255, 40), width=4)
    img = Image.alpha_composite(img.convert("RGBA"), overlay)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT, "PNG")
    print(f"Avatar saved: {OUT}")


if __name__ == "__main__":
    main()

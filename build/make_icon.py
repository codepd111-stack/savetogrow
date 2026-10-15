"""Draws the app icon (a green LCD-style 'S' on a dark bevelled tile) and writes build/icon.ico."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent


def tile(size: int) -> Image.Image:
    s = 256
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=28, fill=(42, 42, 53, 255))
    d.rounded_rectangle([6, 6, s - 7, s - 7], radius=24, outline=(90, 90, 112, 255), width=4)
    d.rounded_rectangle([34, 34, s - 35, s - 35], radius=14, fill=(7, 20, 12, 255), outline=(11, 11, 16, 255), width=4)
    try:
        font = ImageFont.truetype("consolab.ttf", 150)
    except OSError:
        font = ImageFont.load_default()
    d.text((s / 2, s / 2 + 4), "S", font=font, fill=(53, 255, 128, 255), anchor="mm")
    for y in range(40, s - 40, 6):  # faint scanlines for the LCD feel
        d.line([(40, y), (s - 41, y)], fill=(0, 0, 0, 40))
    return im.resize((size, size), Image.LANCZOS)


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [tile(z) for z in sizes]
    out = HERE / "icon.ico"
    images[-1].save(out, format="ICO", sizes=[(z, z) for z in sizes], append_images=images[:-1])
    tile(256).save(HERE / "icon.png")
    print("wrote", out)


if __name__ == "__main__":
    main()

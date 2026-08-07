"""Generate the eight numbered buzzer images from the photo of the real button.

The vendor's product photo carries a printed "1". Every other number has to be
synthesized, so the digit is lifted out and redrawn: the label it sits on is
reconstructed by interpolating the surrounding white, then the new digit is
rendered in SF Rounded, sheared to match the angle the button is photographed
at, and composited in the same place and colour as the original.

Run with:  uv run --with pillow python scripts/make_buttons.py
Outputs:   assets/button-N.webp (600px) and button-N-sm.webp (160px) for every
           button in the table, copied
           into the web dir. WebP because eight PNGs of a photo ran to ~1.8 MB,
           which is a slow first paint on a phone.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from astabuzz.buttons import MAX_COUNT

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "button.png"
OUT = ROOT / "assets"
WEB = ROOT / "src" / "astabuzz" / "web"

SCALE = 2  # final assets are 600x600 so they stay sharp on a phone

# Measured off the photo, in its native 300px coordinates.
DIGIT_BOX = (145, 128, 158, 145)  # the printed "1"
PATCH = (139, 121, 165, 152)  # generous area to rebuild as clean label white
DIGIT_RGB = (71, 158, 220)
# The vendor's circular badge on the dome. Removed so the artwork carries no
# mark that isn't ours: this is a fan project and should not look otherwise.
MARK_CENTRE = (140, 93)
MARK_RADII = (25, 22)
# The stem drifts ~5px right over 14 rows: the button is shot at an angle, so a
# glyph drawn flat would sit visibly straighter than the printed one.
SHEAR = 0.36
FONT = Path("/System/Library/Fonts/SFNSRounded.ttf")


def rebuild_label(img: Image.Image) -> None:
    """Erase the printed digit by interpolating the label white around it.

    The label is near-uniform but not flat, so a solid fill would show as a
    patch. Blending the four borders follows its shading instead.
    """
    x0, y0, x1, y1 = (v * SCALE for v in PATCH)
    px = img.load()
    left = [px[x0 - 1, y][:3] for y in range(y0, y1)]
    right = [px[x1, y][:3] for y in range(y0, y1)]
    top = [px[x, y0 - 1][:3] for x in range(x0, x1)]
    bottom = [px[x, y1][:3] for x in range(x0, x1)]
    w, h = x1 - x0, y1 - y0
    for j, y in enumerate(range(y0, y1)):
        for i, x in enumerate(range(x0, x1)):
            u, v = i / (w - 1), j / (h - 1)
            horiz = [left[j][c] * (1 - u) + right[j][c] * u for c in range(3)]
            vert = [top[i][c] * (1 - v) + bottom[i][c] * v for c in range(3)]
            px[x, y] = (*(round((horiz[c] + vert[c]) / 2) for c in range(3)), 255)


def remove_vendor_mark(img: Image.Image) -> None:
    """Erase the badge and let the dome close over it.

    Filled by interpolating across the hole, row by row and column by column,
    between the real pixels just outside it. That reproduces the dome's
    gradient and its gloss; averaging neighbours iteratively (a Laplace fill)
    needs thousands of passes to converge over a hole this size and leaves a
    flat, visibly darker disc well before then.
    """
    cx, cy = (v * SCALE for v in MARK_CENTRE)
    rx, ry = (v * SCALE for v in MARK_RADII)
    px = img.load()

    def blend(a, b, t):
        return [a[i] + (b[i] - a[i]) * t for i in range(3)]

    patch = {}
    for y in range(cy - ry, cy + ry + 1):
        dy = (y - cy) / ry
        if abs(dy) >= 1:
            continue
        half_x = int(rx * (1 - dy * dy) ** 0.5)
        x0, x1 = cx - half_x, cx + half_x
        left, right = px[x0 - 1, y][:3], px[x1 + 1, y][:3]
        for x in range(x0, x1 + 1):
            dx = (x - cx) / rx
            half_y = int(ry * (1 - dx * dx) ** 0.5)
            y0, y1 = cy - half_y, cy + half_y
            top, bottom = px[x, y0 - 1][:3], px[x, y1 + 1][:3]
            horiz = blend(left, right, (x - x0) / max(1, x1 - x0))
            vert = blend(top, bottom, (y - y0) / max(1, y1 - y0))
            patch[x, y] = tuple(round((horiz[i] + vert[i]) / 2) for i in range(3))

    for (x, y), colour in patch.items():
        px[x, y] = (*colour, 255)

    # The interpolated patch meets the photo's grain along a hard edge. A soft
    # blur confined to the hole, feathered at its rim, hides the join.
    box = (cx - rx - 2, cy - ry - 2, cx + rx + 3, cy + ry + 3)
    region = img.crop(box)
    mask = Image.new("L", region.size, 0)
    ImageDraw.Draw(mask).ellipse((2, 2, region.width - 3, region.height - 3), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(6))
    img.paste(Image.composite(region.filter(ImageFilter.GaussianBlur(3)), region, mask), box)


def render_digit(text: str, height: int) -> Image.Image:
    """A single sheared digit, tight-cropped, ready to composite."""
    font = ImageFont.truetype(str(FONT), 240)
    canvas = Image.new("L", (400, 400), 0)
    ImageDraw.Draw(canvas).text((200, 200), text, font=font, fill=255, anchor="mm")
    canvas = canvas.crop(canvas.getbbox())

    # Widen first so the shear does not clip the glyph.
    pad = round(canvas.height * SHEAR) + 4
    wide = Image.new("L", (canvas.width + pad * 2, canvas.height), 0)
    wide.paste(canvas, (pad, 0))
    # PIL maps output->input, so a positive coefficient leans the bottom right.
    sheared = wide.transform(
        wide.size,
        Image.AFFINE,
        (1, -SHEAR, SHEAR * wide.height / 2, 0, 1, 0),
        resample=Image.BICUBIC,
    )
    sheared = sheared.crop(sheared.getbbox())
    scale = height / sheared.height
    return sheared.resize(
        (max(1, round(sheared.width * scale)), height), Image.LANCZOS
    )


def build(number: int) -> Image.Image:
    img = Image.open(SRC).convert("RGBA")
    img = img.resize((img.width * SCALE, img.height * SCALE), Image.LANCZOS)
    remove_vendor_mark(img)
    rebuild_label(img)

    dx0, dy0, dx1, dy1 = DIGIT_BOX
    height = round((dy1 - dy0 + 1) * SCALE)
    centre = (round((dx0 + dx1 + 1) / 2 * SCALE), round((dy0 + dy1 + 1) / 2 * SCALE))

    mask = render_digit(str(number), height)
    ink = Image.new("RGBA", mask.size, (*DIGIT_RGB, 255))
    img.paste(ink, (centre[0] - mask.width // 2, centre[1] - mask.height // 2), mask)
    return img


def main() -> None:
    total = 0
    row = Image.new("RGBA", (MAX_COUNT * 150, 150), (0, 0, 0, 0))
    for n in range(1, MAX_COUNT + 1):
        img = build(n)
        thumb = img.resize((160, 160), Image.LANCZOS)
        for folder in (OUT, WEB):
            img.save(folder / f"button-{n}.webp", "WEBP", quality=82, method=6)
            thumb.save(folder / f"button-{n}-sm.webp", "WEBP", quality=82, method=6)
        total += (WEB / f"button-{n}.webp").stat().st_size
        total += (WEB / f"button-{n}-sm.webp").stat().st_size
        row.alpha_composite(img.resize((150, 150), Image.LANCZOS), ((n - 1) * 150, 0))

    row.save(OUT / "buttons-row.webp", "WEBP", quality=85, method=6)
    # apple-touch-icon has to stay PNG: iOS will not take a WebP here.
    build(1).resize((180, 180), Image.LANCZOS).save(
        WEB / "icon.png", "PNG", optimize=True
    )
    print(f"wrote {MAX_COUNT} buttons + thumbs, {total / 1024:.0f} KB served in total")


if __name__ == "__main__":
    main()

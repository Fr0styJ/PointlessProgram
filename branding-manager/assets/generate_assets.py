"""
One-off generator for branding-manager's bundled placeholder asset library.
Not part of the runtime service — run manually (`python generate_assets.py`)
if the asset set ever needs to be regenerated. Requires Pillow.

Produces:
  branding-manager/assets/avatars/avatar-{01..10}.png  (256x256, solid-color
      square background + a bold initial letter, distinct colors)
  branding-manager/assets/emoji/{name}.png              (64x64, simple
      geometric shapes forming a small themed "FakeCo" emoji pack)
"""
from PIL import Image, ImageDraw, ImageFont
import os

HERE = os.path.dirname(os.path.abspath(__file__))
AVATAR_DIR = os.path.join(HERE, "avatars")
EMOJI_DIR = os.path.join(HERE, "emoji")

AVATAR_COLORS = [
    ("avatar-01", "#E63946", "A"),
    ("avatar-02", "#F1A208", "B"),
    ("avatar-03", "#2A9D8F", "C"),
    ("avatar-04", "#264653", "D"),
    ("avatar-05", "#8E44AD", "E"),
    ("avatar-06", "#3D5A80", "F"),
    ("avatar-07", "#EE6C4D", "G"),
    ("avatar-08", "#606C38", "H"),
    ("avatar-09", "#118AB2", "I"),
    ("avatar-10", "#7B2D26", "J"),
]


def _font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def make_avatar(name: str, hex_color: str, letter: str, size: int = 256):
    img = Image.new("RGB", (size, size), hex_color)
    draw = ImageDraw.Draw(img)
    font = _font(int(size * 0.5))
    bbox = draw.textbbox((0, 0), letter, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]),
        letter, fill="white", font=font,
    )
    path = os.path.join(AVATAR_DIR, f"{name}.png")
    img.save(path, "PNG")
    print("wrote", path)


def make_emoji_circle(name: str, hex_color: str, size: int = 64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = 4
    draw.ellipse([pad, pad, size - pad, size - pad], fill=hex_color)
    path = os.path.join(EMOJI_DIR, f"{name}.png")
    img.save(path, "PNG")
    print("wrote", path)


def make_emoji_square(name: str, hex_color: str, size: int = 64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = 6
    draw.rectangle([pad, pad, size - pad, size - pad], fill=hex_color)
    path = os.path.join(EMOJI_DIR, f"{name}.png")
    img.save(path, "PNG")
    print("wrote", path)


def make_emoji_star(name: str, hex_color: str, size: int = 64):
    import math
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size / 2, size / 2
    outer, inner = size / 2 - 4, (size / 2 - 4) * 0.42
    points = []
    for i in range(10):
        r = outer if i % 2 == 0 else inner
        angle = math.pi / 2 + i * math.pi / 5
        points.append((cx + r * math.cos(angle), cy - r * math.sin(angle)))
    draw.polygon(points, fill=hex_color)
    path = os.path.join(EMOJI_DIR, f"{name}.png")
    img.save(path, "PNG")
    print("wrote", path)


def make_emoji_triangle(name: str, hex_color: str, size: int = 64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = 4
    draw.polygon(
        [(size / 2, pad), (size - pad, size - pad), (pad, size - pad)],
        fill=hex_color,
    )
    path = os.path.join(EMOJI_DIR, f"{name}.png")
    img.save(path, "PNG")
    print("wrote", path)


if __name__ == "__main__":
    os.makedirs(AVATAR_DIR, exist_ok=True)
    os.makedirs(EMOJI_DIR, exist_ok=True)

    for name, color, letter in AVATAR_COLORS:
        make_avatar(name, color, letter)

    # Small "FakeCo" themed emoji pack — simple geometric shapes, distinct
    # colors/forms, real distinct PNG files Mattermost's emoji upload API can
    # actually accept.
    make_emoji_circle("fakeco-thumbsup", "#2A9D8F")
    make_emoji_square("fakeco-shipit", "#E63946")
    make_emoji_star("fakeco-star", "#F1A208")
    make_emoji_triangle("fakeco-alert", "#EE6C4D")
    make_emoji_circle("fakeco-money", "#118AB2")

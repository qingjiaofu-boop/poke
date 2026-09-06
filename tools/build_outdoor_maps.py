"""Build small three-layer outdoor maps from the Essentials Outside tileset."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"E:\123pan\Downloads\Pokemon Essentials v20.1\Graphics\Tilesets\Outside.png")
OUT = ROOT / "assets" / "maps"
W, H, TILE = 24, 18, 32


def tile(sheet: Image.Image, index: int) -> Image.Image:
    x = (index % 8) * TILE
    y = (index // 8) * TILE
    return sheet.crop((x, y, x + TILE, y + TILE))


def put(surface: Image.Image, sheet: Image.Image, index: int, x: int, y: int):
    surface.alpha_composite(tile(sheet, index), (x * TILE, y * TILE))


def fill(surface: Image.Image, sheet: Image.Image, index: int):
    stamp = tile(sheet, index)
    for y in range(H):
        for x in range(W):
            surface.alpha_composite(stamp, (x * TILE, y * TILE))


def path(surface: Image.Image, sheet: Image.Image, cells, index=100):
    for x, y in cells:
        put(surface, sheet, index, x, y)


def tree(upper: Image.Image, sheet: Image.Image, x: int, y: int):
    # Four valid tree tiles form a canopy that can occlude the actor.
    for dx, dy, idx in ((0, 0, 448), (1, 0, 449), (0, 1, 456), (1, 1, 457)):
        put(upper, sheet, idx, x + dx, y + dy)


def make_map(name: str, start, paths, decorations, trees, blocked):
    sheet = Image.open(SOURCE).convert("RGBA")
    lower = Image.new("RGBA", (W * TILE, H * TILE), (0, 0, 0, 0))
    current = Image.new("RGBA", lower.size, (0, 0, 0, 0))
    upper = Image.new("RGBA", lower.size, (0, 0, 0, 0))
    fill(lower, sheet, 1)
    for cells, idx in paths:
        path(lower, sheet, cells, idx)
    for x, y, idx in decorations:
        put(current, sheet, idx, x, y)
    for x, y in trees:
        tree(upper, sheet, x, y)
    OUT.mkdir(parents=True, exist_ok=True)
    for layer, image in (("lower", lower), ("current", current), ("upper", upper)):
        image.save(OUT / f"{name}_{layer}.png")
    return {
        "size": [W, H],
        "start": list(start),
        "blocked": [list(cell) for cell in blocked],
        "layers": {layer: f"maps/{name}_{layer}.png" for layer in ("lower", "current", "upper")},
    }


def main():
    # Keep the layouts open and readable: a central route, a side clearing,
    # and a small house garden. The upper tree rows are deliberately separate.
    home_path = {(x, 9) for x in range(2, 22)} | {(x, y) for x in range(10, 22) for y in range(9, 16)}
    friend_path = {(x, 10) for x in range(2, 22)} | {(12, y) for y in range(3, 11)}
    route_path = {(x, 8) for x in range(1, 23)} | {(11, y) for y in range(0, 18)}
    specs = {
        "home": make_map(
            "home", (6, 13), [(home_path, 100)],
            [(4, 5, 31), (5, 5, 31), (18, 4, 31), (19, 4, 31), (2, 13, 16), (3, 13, 17)],
            [(0, 0), (2, 0), (4, 0), (6, 0), (8, 0), (16, 0), (18, 0), (20, 0), (22, 0),
             (0, 2), (22, 2), (0, 14), (22, 14), (0, 16), (2, 16), (20, 16), (22, 16)],
            {(4, 5), (5, 5), (18, 4), (19, 4), (2, 13), (3, 13)}),
        "friend": make_map(
            "friend", (4, 10), [(friend_path, 100)],
            [(6, 6, 31), (7, 6, 31), (17, 7, 31), (18, 7, 31), (14, 3, 16), (15, 3, 17)],
            [(0, 0), (2, 0), (4, 0), (18, 0), (20, 0), (22, 0), (0, 2), (22, 2),
             (0, 15), (2, 15), (4, 15), (18, 15), (20, 15), (22, 15)],
            {(6, 6), (7, 6), (17, 7), (18, 7), (14, 3), (15, 3)}),
        "route": make_map(
            "route", (11, 15), [(route_path, 100)],
            [(3, 5, 31), (4, 5, 31), (17, 11, 31), (18, 11, 31), (3, 12, 16), (4, 12, 17)],
            [(0, 0), (2, 0), (4, 0), (6, 0), (16, 0), (18, 0), (20, 0), (22, 0),
             (0, 3), (22, 3), (0, 14), (22, 14), (0, 16), (2, 16), (20, 16), (22, 16)],
            {(3, 5), (4, 5), (17, 11), (18, 11), (3, 12), (4, 12)}),
    }
    (OUT / "outdoor_maps.json").write_text(json.dumps(specs, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

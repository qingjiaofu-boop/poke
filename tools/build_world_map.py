"""Bake connected outdoor maps into the three 120x120 world layer images."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
MAPS = ASSETS / "maps"
TILE_SIZE = 32
LAYERS = ("lower", "current", "upper")


def main():
    specs = json.loads((MAPS / "outdoor_maps.json").read_text(encoding="utf-8"))
    manifest = json.loads((MAPS / "world_connections.json").read_text(encoding="utf-8"))
    world_width, world_height = (int(value) for value in manifest["world_size"])

    for layer_name in LAYERS:
        world = Image.new(
            "RGBA",
            (world_width * TILE_SIZE, world_height * TILE_SIZE),
            (0, 0, 0, 0),
        )
        for placement in manifest["maps"]:
            if int(placement.get("rotation", 0)) != 0:
                raise ValueError(f"Unsupported map rotation: {placement['id']}")
            spec = specs[placement["map"]]
            source_path = ASSETS / spec["layers"][layer_name]
            with Image.open(source_path) as source:
                source = source.convert("RGBA")
                expected = tuple(int(value) * TILE_SIZE for value in spec["size"])
                if source.size != expected:
                    raise ValueError(
                        f"{source_path.name} is {source.size}, expected {expected}"
                    )
                position = placement["position"]
                world.alpha_composite(
                    source,
                    (int(position["x"]) * TILE_SIZE, int(position["y"]) * TILE_SIZE),
                )
        world.save(MAPS / f"world_{layer_name}.png")


if __name__ == "__main__":
    main()

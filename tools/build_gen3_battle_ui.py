"""Build a reusable 2x Gen III-style battle UI kit from the reference sheet."""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
RESOURCE = ASSETS / "resource"
BATTLE = RESOURCE / "battle"
SOURCE = RESOURCE / "Game Boy Advance - Pokemon FireRed _ LeafGreen - Battle Effects - HP Bars & In-battle Menu.png"
OUTPUT = BATTLE / "ui_gen3_2x"
SCALE = 2
SCREEN_SIZE = (480, 320)
ATLAS_SIZE = (1024, 512)

# Source rectangles are native 1x GBA pixels. Every exported pixel is doubled
# with nearest-neighbour sampling; atlas and screen coordinates remain even.
SOURCE_RECTS = {
    "databox_foe": (2, 2, 98, 36),
    "databox_player_classic": (8, 42, 108, 84),
    "panel_command_classic": (146, 3, 267, 53),
    "panel_move_list": (297, 3, 456, 53),
    "panel_move_info_classic": (459, 3, 537, 53),
    "panel_message": (297, 57, 537, 103),
    "cursor_command": (268, 3, 278, 14),
    "cursor_continue": (541, 55, 551, 66),
}

ATLAS_POSITIONS = {
    "databox_foe": (0, 0),
    "databox_player_classic": (208, 0),
    "databox_player": (424, 0),
    "cursor_command": (640, 0),
    "cursor_continue": (676, 0),
    "hp_fill_green": (704, 0),
    "hp_fill_yellow": (704, 16),
    "hp_fill_red": (704, 32),
    "hp_fill_empty": (704, 48),
    "panel_command_classic": (0, 112),
    "panel_command": (258, 112),
    "panel_move_info_classic": (524, 112),
    "panel_move_info": (696, 112),
    "panel_move_list": (0, 232),
    "panel_message": (334, 232),
    "panel_message_left": (0, 352),
}

SCREEN_LAYOUTS = {
    "databox_foe": [6, 8, 192, 68],
    "databox_player": [280, 146, 200, 68],
    "message_full": [0, 228, 480, 92],
    "message_left": [0, 228, 240, 92],
    "command_panel": [238, 220, 242, 100],
    "move_list": [0, 220, 318, 100],
    "move_info": [324, 220, 156, 100],
}


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        RESOURCE / "fonts" / "zpix.ttf",
        Path("C:/Windows/Fonts/msyh.ttf"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    )
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def transparent_exterior(image: Image.Image) -> Image.Image:
    """Remove only white pixels connected to the crop edge, preserving panels."""
    result = image.convert("RGBA")
    pixels = result.load()
    width, height = result.size
    queue = deque()
    seen = set()
    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))
    while queue:
        x, y = queue.popleft()
        if (x, y) in seen:
            continue
        seen.add((x, y))
        red, green, blue, _alpha = pixels[x, y]
        if min(red, green, blue) < 252:
            continue
        pixels[x, y] = (red, green, blue, 0)
        if x:
            queue.append((x - 1, y))
        if x + 1 < width:
            queue.append((x + 1, y))
        if y:
            queue.append((x, y - 1))
        if y + 1 < height:
            queue.append((x, y + 1))
    return result


def upscale(image: Image.Image) -> Image.Image:
    return image.resize((image.width * SCALE, image.height * SCALE), Image.Resampling.NEAREST)


def source_component(source: Image.Image, name: str) -> Image.Image:
    return transparent_exterior(source.crop(SOURCE_RECTS[name]))


def build_components() -> dict[str, Image.Image]:
    source = Image.open(SOURCE).convert("RGB")
    native = {name: source_component(source, name) for name in SOURCE_RECTS}

    foe = native["databox_foe"].copy()
    foe_draw = ImageDraw.Draw(foe)
    foe_draw.rectangle((72, 4, 91, 15), fill=(248, 248, 216, 255))
    foe_draw.rectangle((40, 18, 87, 20), fill=(64, 64, 64, 255))

    player_classic = native["databox_player_classic"].copy()
    player_draw = ImageDraw.Draw(player_classic)
    player_draw.rectangle((72, 4, 93, 15), fill=(248, 248, 216, 255))
    player_draw.rectangle((43, 19, 90, 21), fill=(64, 64, 64, 255))
    # This compact project variant omits the EXP strip and level label.
    player = player_classic.crop((0, 0, player_classic.width, 34))

    command = native["panel_command_classic"].copy()
    ImageDraw.Draw(command).rectangle((7, 8, 115, 43), fill=(248, 248, 248, 255))

    move_info = native["panel_move_info_classic"].copy()
    ImageDraw.Draw(move_info).rectangle((4, 7, 73, 44), fill=(248, 248, 248, 255))

    message_left = native["panel_message"].crop((0, 0, 120, 46))
    fills = {
        "hp_fill_green": ((112, 248, 168, 255), (88, 208, 128, 255)),
        "hp_fill_yellow": ((248, 232, 96, 255), (224, 184, 56, 255)),
        "hp_fill_red": ((248, 112, 88, 255), (208, 72, 64, 255)),
        "hp_fill_empty": ((104, 104, 104, 255), (64, 64, 64, 255)),
    }

    components = {
        "databox_foe": upscale(foe),
        "databox_player_classic": upscale(player_classic),
        "databox_player": upscale(player),
        "panel_command_classic": upscale(native["panel_command_classic"]),
        "panel_command": upscale(command),
        "panel_move_list": upscale(native["panel_move_list"]),
        "panel_move_info_classic": upscale(native["panel_move_info_classic"]),
        "panel_move_info": upscale(move_info),
        "panel_message": upscale(native["panel_message"]),
        "panel_message_left": upscale(message_left),
        "cursor_command": upscale(native["cursor_command"]),
        "cursor_continue": upscale(native["cursor_continue"]),
    }
    for name, (light, dark) in fills.items():
        bar = Image.new("RGBA", (96, 6), dark)
        ImageDraw.Draw(bar).rectangle((0, 0, 95, 1), fill=light)
        components[name] = bar
    return components


def save_components(components: dict[str, Image.Image]) -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    atlas = Image.new("RGBA", ATLAS_SIZE, (0, 0, 0, 0))
    sprites = {}
    for name, image in components.items():
        path = OUTPUT / f"{name}_2x.png"
        image.save(path, optimize=True)
        x, y = ATLAS_POSITIONS[name]
        atlas.alpha_composite(image, (x, y))
        sprites[name] = {
            "atlas_rect_2x": [x, y, image.width, image.height],
            "file": path.name,
        }
        if name in SOURCE_RECTS:
            sprites[name]["source_rect_1x"] = list(SOURCE_RECTS[name])
    atlas.save(OUTPUT / "gen3_battle_ui_atlas_2x.png", optimize=True)
    manifest = {
        "version": 1,
        "scale": 2,
        "logical_resolution_2x": list(SCREEN_SIZE),
        "native_gba_resolution_1x": [240, 160],
        "atlas": "gen3_battle_ui_atlas_2x.png",
        "atlas_size_2x": list(ATLAS_SIZE),
        "source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "sprites": sprites,
        "recommended_screen_layouts_2x": SCREEN_LAYOUTS,
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def paste_fitted(target: Image.Image, path: Path, center_x: int, bottom_y: int, max_size: tuple[int, int]):
    source = Image.open(path).convert("RGBA")
    bounds = source.getbbox()
    if not bounds:
        return
    source = source.crop(bounds)
    scale = min(max_size[0] / source.width, max_size[1] / source.height)
    source = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.NEAREST,
    )
    target.alpha_composite(source, (center_x - source.width // 2, bottom_y - source.height))


def base_preview() -> Image.Image:
    background = Image.open(BATTLE / "backgrounds" / "field_eve_bg.png").convert("RGBA")
    background = ImageOps.fit(background, (480, 228), method=Image.Resampling.NEAREST)
    result = Image.new("RGBA", SCREEN_SIZE, (232, 240, 232, 255))
    result.alpha_composite(background, (0, 0))
    player_base = Image.open(BATTLE / "backgrounds" / "field_eve_base0.png").convert("RGBA")
    foe_base = Image.open(BATTLE / "backgrounds" / "field_eve_base1.png").convert("RGBA")
    result.alpha_composite(player_base.resize((260, 34), Image.Resampling.NEAREST), (-4, 184))
    result.alpha_composite(foe_base.resize((154, 76), Image.Resampling.NEAREST), (304, 82))
    paste_fitted(result, BATTLE / "pokemon" / "back" / "ferrothorn.png", 116, 212, (136, 142))
    paste_fitted(result, RESOURCE / "dialogue" / "pokemons" / "GROTLE.png", 382, 136, (124, 112))
    return result


def add_databoxes(image: Image.Image, components: dict[str, Image.Image]):
    foe_x, foe_y = 6, 8
    player_x, player_y = 280, 146
    image.alpha_composite(components["databox_foe"], (foe_x, foe_y))
    image.alpha_composite(components["databox_player"], (player_x, player_y))
    image.alpha_composite(components["hp_fill_green"], (foe_x + 80, foe_y + 36))
    image.alpha_composite(components["hp_fill_green"], (player_x + 86, player_y + 38))
    draw = ImageDraw.Draw(image)
    label_font = font(18)
    number_font = font(14)
    ink = (48, 48, 40, 255)
    draw.text((foe_x + 12, foe_y + 10), "树林龟", font=label_font, fill=ink)
    draw.text((player_x + 12, player_y + 10), "坚果哑铃", font=label_font, fill=ink)
    draw.text((player_x + 130, player_y + 48), "100/100", font=number_font, fill=ink)


def build_previews(components: dict[str, Image.Image]):
    command = base_preview()
    add_databoxes(command, components)
    command.alpha_composite(components["panel_message"], (0, 228))
    command.alpha_composite(components["panel_command"], (238, 220))
    draw = ImageDraw.Draw(command)
    text_font = font(18)
    small_font = font(16)
    draw.multiline_text((18, 244), "树林龟正在等待\n坚果哑铃的行动。", font=text_font, fill=(248, 248, 248, 255), spacing=7)
    for label, position in (
        ("战斗", (270, 240)), ("背包", (386, 240)),
        ("宝可梦", (270, 278)), ("逃跑", (386, 278)),
    ):
        draw.text(position, label, font=small_font, fill=(48, 48, 48, 255))
    draw.polygon(((252, 246), (264, 240), (264, 252)), fill=(40, 48, 48, 255))
    command.convert("RGB").save(OUTPUT / "preview_command_480x320.png", optimize=True)

    fight = base_preview()
    add_databoxes(fight, components)
    fight.alpha_composite(components["panel_move_list"], (0, 220))
    fight.alpha_composite(components["panel_move_info"], (324, 220))
    draw = ImageDraw.Draw(fight)
    for label, position in (
        ("日光束", (28, 234)), ("光合作用", (174, 234)),
        ("重磅冲撞", (28, 274)), ("气象球", (174, 274)),
    ):
        draw.text(position, label, font=small_font, fill=(48, 48, 48, 255))
    draw.polygon(((10, 240), (22, 234), (22, 246)), fill=(40, 48, 48, 255))
    draw.text((338, 236), "属性/草", font=small_font, fill=(48, 48, 48, 255))
    draw.text((338, 274), "光照联动", font=font(14), fill=(72, 72, 72, 255))
    fight.convert("RGB").save(OUTPUT / "preview_fight_480x320.png", optimize=True)


def main():
    components = build_components()
    save_components(components)
    build_previews(components)
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()

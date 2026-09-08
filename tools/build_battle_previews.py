"""Build reusable 480x320 GBA-style battle interface reference images."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
BATTLE = ASSETS / "resource" / "battle"
OUTPUT = BATTLE / "previews"
SIZE = (480, 320)
ARENA_HEIGHT = 230
MENU_HEIGHT = SIZE[1] - ARENA_HEIGHT


ENCOUNTERS = {
    "grotle": {
        "name": "树林龟",
        "background": "field",
        "sprite": ASSETS / "resource" / "dialogue" / "pokemons" / "GROTLE.png",
        "moves": ("日光束", "光合作用"),
        "show_hp_number": False,
    },
    "zubat": {
        "name": "超音蝠",
        "background": "rocky",
        "sprite": BATTLE / "pokemon" / "front" / "zubat.png",
        "moves": ("日光束", "光合作用"),
        "show_hp_number": True,
    },
    "aron": {
        "name": "可可多拉",
        "background": "rocky",
        "sprite": BATTLE / "pokemon" / "front" / "aron.png",
        "moves": ("日光束", "光合作用"),
        "show_hp_number": True,
    },
    "sableye": {
        "name": "勾魂眼",
        "background": "rocky",
        "sprite": BATTLE / "pokemon" / "front" / "sableye.png",
        "moves": ("日光束", "光合作用", "重磅冲撞"),
        "show_hp_number": True,
    },
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    )
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def open_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return image.resize(size, Image.Resampling.NEAREST)


def paste_fitted(
    target: Image.Image,
    source_path: Path,
    center_x: int,
    bottom_y: int,
    max_size: tuple[int, int],
) -> None:
    source = open_rgba(source_path)
    bounds = source.getbbox()
    if not bounds:
        return
    source = source.crop(bounds)
    scale = min(max_size[0] / source.width, max_size[1] / source.height)
    fitted = resize(
        source,
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
    )
    target.alpha_composite(fitted, (center_x - fitted.width // 2, bottom_y - fitted.height))


def draw_hp_fill(image: Image.Image, box: tuple[int, int, int, int], side: str) -> None:
    draw = ImageDraw.Draw(image)
    x, y, width, height = box
    if side == "player":
        bar = (x + round(width * 0.43), y + round(height * 0.49), round(width * 0.47), 6)
    else:
        bar = (x + round(width * 0.43), y + round(height * 0.49), round(width * 0.47), 6)
    bx, by, bw, bh = bar
    draw.rectangle((bx + 1, by + 1, bx + bw - 2, by + bh - 2), fill=(72, 173, 73, 255))


def draw_databoxes(image: Image.Image, foe_name: str, show_hp_number: bool) -> None:
    player_box = (250, 151, 220, 71)
    foe_box = (8, 7, 210, 50)
    image.alpha_composite(
        resize(open_rgba(BATTLE / "ui" / "databox_normal.png"), player_box[2:]),
        player_box[:2],
    )
    image.alpha_composite(
        resize(open_rgba(BATTLE / "ui" / "databox_normal_foe.png"), foe_box[2:]),
        foe_box[:2],
    )
    draw_hp_fill(image, player_box, "player")
    draw_hp_fill(image, foe_box, "foe")

    draw = ImageDraw.Draw(image)
    name_font = font(13, True)
    small_font = font(11, True)
    ink = (31, 39, 38, 255)
    draw.text((foe_box[0] + 15, foe_box[1] + 7), foe_name, font=name_font, fill=ink)
    draw.text((player_box[0] + 15, player_box[1] + 8), "坚果哑铃", font=name_font, fill=ink)
    draw.text((player_box[0] + 163, player_box[1] + 9), "Lv.50", font=small_font, fill=ink)
    if show_hp_number:
        hp_text = "134/134"
        text_box = draw.textbbox((0, 0), hp_text, font=small_font)
        text_width = text_box[2] - text_box[0]
        draw.text(
            (player_box[0] + player_box[2] - text_width - 13, player_box[1] + 52),
            hp_text,
            font=small_font,
            fill=ink,
        )


def draw_move_menu(image: Image.Image, moves: tuple[str, ...]) -> None:
    overlay = resize(open_rgba(BATTLE / "ui" / "overlay_fight.png"), (SIZE[0], MENU_HEIGHT))
    image.alpha_composite(overlay, (0, ARENA_HEIGHT))
    draw = ImageDraw.Draw(image)
    move_font = font(14, True)
    help_font = font(11, True)
    active = (250, 244, 202, 255)
    inactive = (42, 45, 55, 255)
    disabled = (121, 119, 130, 255)
    slots = ((22, 240), (202, 240), (22, 277), (202, 277))

    for index, (x, y) in enumerate(slots):
        label = moves[index] if index < len(moves) else "—"
        color = active if index == 0 else (inactive if index < len(moves) else disabled)
        draw.text((x, y), label, font=move_font, fill=color)
    draw.polygon(((8, 248), (16, 243), (16, 253)), fill=(246, 190, 52, 255))

    help_x = 397
    draw.text((help_x, 239), "选择技能", font=help_font, fill=(45, 49, 54, 255))
    draw.text((help_x, 260), "方向键移动", font=help_font, fill=(70, 70, 76, 255))
    draw.text((help_x, 281), "回车确认", font=help_font, fill=(70, 70, 76, 255))


def build_preview(slug: str, spec: dict) -> Path:
    background_name = spec["background"]
    arena_source = open_rgba(BATTLE / "backgrounds" / f"{background_name}_bg.png")
    arena = ImageOps.fit(
        arena_source,
        (SIZE[0], ARENA_HEIGHT),
        method=Image.Resampling.NEAREST,
        centering=(0.5, 0.5),
    )
    image = Image.new("RGBA", SIZE, (255, 255, 255, 255))
    image.alpha_composite(arena, (0, 0))

    player_base = resize(
        open_rgba(BATTLE / "backgrounds" / f"{background_name}_base0.png"),
        (260, 33),
    )
    foe_base = resize(
        open_rgba(BATTLE / "backgrounds" / f"{background_name}_base1.png"),
        (154, 77),
    )
    image.alpha_composite(player_base, (-5, 177))
    image.alpha_composite(foe_base, (303, 79))

    paste_fitted(
        image,
        BATTLE / "pokemon" / "back" / "ferrothorn.png",
        center_x=120,
        bottom_y=204,
        max_size=(132, 139),
    )
    paste_fitted(
        image,
        spec["sprite"],
        center_x=378,
        bottom_y=132,
        max_size=(124, 108),
    )
    draw_databoxes(image, spec["name"], spec["show_hp_number"])
    draw_move_menu(image, spec["moves"])

    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / f"battle_{slug}.png"
    image.convert("RGB").save(path, optimize=True)
    return path


def main() -> None:
    for slug, spec in ENCOUNTERS.items():
        print(build_preview(slug, spec).relative_to(ROOT))


if __name__ == "__main__":
    main()

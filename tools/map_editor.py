"""Tiny tile map editor for the STC-B Pokémon prototype.

Run from the project root, for example::

    python tools/map_editor.py home

The editor paints three transparent 32px layers and writes the files consumed
by ``essentials_adventure.py``.  It intentionally has no external dependencies
besides pygame (which the game already uses).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pygame


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
# Prefer the copy committed with the project so teammates can edit maps after
# cloning. The original local path remains a fallback for older workspaces.
TILESET_CANDIDATES = (
    ASSETS / "Outside.png",
    Path(r"E:\123pan\Downloads\Pokemon Essentials v20.1\Graphics\Tilesets\Outside.png"),
)

# 图块集列表。kind="sheet" 表示一整张 32×32 网格图（按宽高切列）；
# kind="dir" 表示一个目录里若干张独立的 32×32 PNG（按文件名自然排序加载）。
# 想再增加自己的图块集，只需往这里加一项。
TILE_SOURCES = (
    {"name": "Outside", "kind": "sheet", "paths": TILESET_CANDIDATES},
    {"name": "Cave", "kind": "dir", "path": ASSETS / "cave"},
)

OUT = ASSETS / "maps"
MAP_W, MAP_H, TILE = 24, 18, 32
# 地图宽高上限（格）。超出视口(768×576) 的地图会启用相机滚动编辑。
MAX_MAP_W, MAX_MAP_H = 40, 40
SCREEN = (1200, 720)
# RPG Maker-like layout: resource palette on the left, map canvas on the right.
MAP_FRAME = pygame.Rect(400, 78, 768, 576)
SOURCE_BUTTON = pygame.Rect(8, 28, 384, 40)
PAGE_BUTTON = pygame.Rect(24, 306, 320, 30)
SAVE_BUTTON = pygame.Rect(24, 502, 320, 31)
SELECT_BUTTON = pygame.Rect(24, 535, 320, 38)
PASTE_BUTTON = pygame.Rect(24, 580, 320, 38)
NEW_BUTTON = pygame.Rect(24, 625, 152, 38)
RESIZE_BUTTON = pygame.Rect(192, 625, 152, 38)
OPEN_BUTTON = pygame.Rect(24, 666, 320, 28)
OPEN_DIALOG = pygame.Rect(430, 150, 700, 420)
OPEN_VISIBLE = 8


def _natural_key(name):
    """文件名自然排序：Caves_2 排在 Caves_10 之前。"""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", name)]


def _load_dir(directory):
    """读取目录里所有 PNG，每个当做一个 32×32 图块。"""
    tiles = []
    for path in sorted(directory.glob("*.png"), key=lambda p: _natural_key(p.name)):
        image = pygame.image.load(str(path)).convert_alpha()
        if image.get_size() != (TILE, TILE):
            image = pygame.transform.smoothscale(image, (TILE, TILE))
        tiles.append(image.copy())
    return tiles


def _load_sheet(paths):
    """从一整张 32×32 网格图切出所有图块，按实际宽高算列数。"""
    source = next((path for path in paths if path.exists()), None)
    if source is None:
        return []
    image = pygame.image.load(str(source)).convert_alpha()
    cols = image.get_width() // TILE
    rows = image.get_height() // TILE
    return [image.subsurface((x * TILE, y * TILE, TILE, TILE)).copy()
            for y in range(rows) for x in range(cols)]


def load_tiles(source):
    """按图块集定义加载 tile：目录 -> 逐张 PNG；否则 -> 整张图切列。"""
    if source["kind"] == "dir":
        return _load_dir(source["path"])
    return _load_sheet(source["paths"])


def resolve_size(name, old_meta):
    """确定地图尺寸(格)。

    优先用 json 里的 size；缺失或非法时按实际 PNG 尺寸探测（并钳制到上限）。
    这样即使 json 与 PNG 不同步，也不会用默认尺寸去加载一张更大/更小的图。
    """
    size = old_meta.get("size")
    if isinstance(size, (list, tuple)) and len(size) == 2:
        try:
            w, h = int(size[0]), int(size[1])
            if 1 <= w <= MAX_MAP_W and 1 <= h <= MAX_MAP_H:
                return w, h
        except (TypeError, ValueError):
            pass
    for suffix in ("lower", "current", "upper"):
        p = OUT / f"{name}_{suffix}.png"
        if p.exists():
            try:
                image = pygame.image.load(str(p))
                w = max(1, min(MAX_MAP_W, image.get_width() // TILE))
                h = max(1, min(MAX_MAP_H, image.get_height() // TILE))
                return w, h
            except pygame.error:
                continue
    return 24, 18


def load_layer(path, tile_w, tile_h):
    """加载一层 PNG 并归一化到 tile_w×tile_h。

    缺文件或偏小时用透明补齐，偏大时裁剪，保证返回的 Surface 一定是目标尺寸，
    后续绘制/碰撞高亮的 subsurface 就不会越界崩溃。
    """
    surface = pygame.Surface((tile_w * TILE, tile_h * TILE), pygame.SRCALPHA)
    if path.exists():
        try:
            image = pygame.image.load(str(path)).convert_alpha()
            surface.blit(image, (0, 0))
        except pygame.error:
            pass
    return surface


def make_font(size: int):
    """Load a Windows CJK font directly instead of using SysFont registry scan.

    Some Pygame builds encounter malformed font registry entries and raise
    ``TypeError: expected str ... not int`` inside ``pygame.font.SysFont``.
    """
    candidates = (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    )
    for path in candidates:
        if path.exists():
            try:
                return pygame.font.Font(str(path), size)
            except pygame.error:
                continue
    return pygame.font.Font(None, size)


def _event_char(event):
    """返回按键对应的可打印字符。

    对话框输入原来只依赖 ``event.unicode``，在部分系统/输入法下该字段为空，
    导致无法打字。这里在 unicode 缺失时退化为按 ``event.key`` 映射常用 ASCII
    字符（字母/数字/空格/减号/下划线/点）。
    """
    ch = getattr(event, "unicode", "")
    if ch and ch.isprintable():
        return ch
    key = event.key
    shift = bool(event.mod & pygame.KMOD_SHIFT)
    if pygame.K_a <= key <= pygame.K_z:
        base = ord("a") + (key - pygame.K_a)
        return chr(base - 32) if shift else chr(base)
    if pygame.K_0 <= key <= pygame.K_9:
        return chr(ord("0") + (key - pygame.K_0))
    if key == pygame.K_SPACE:
        return " "
    if key == pygame.K_MINUS:
        return "_" if shift else "-"
    if key == pygame.K_PERIOD:
        return "."
    return ""


def main(name: str):
    global MAP_W, MAP_H
    pygame.init()
    screen = pygame.display.set_mode(SCREEN)
    pygame.display.set_caption(f"三层地图编辑器 - {name}")
    font = make_font(18)
    small = make_font(15)
    meta_path = OUT / "outdoor_maps.json"
    all_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    old = all_meta.get(name, {})
    MAP_W, MAP_H = resolve_size(name, old)
    tiles = load_tiles(TILE_SOURCES[0])
    if not tiles:
        raise FileNotFoundError("找不到图块：请确认 assets/Outside.png 或 assets/cave 内存在 32×32 PNG")
    source_index = 0
    layers = [load_layer(OUT / f"{name}_{s}.png", MAP_W, MAP_H) for s in ("lower", "current", "upper")]
    blocked = {(x, y) for x, y in ({tuple(c) for c in old.get("blocked", [])}) if x < MAP_W and y < MAP_H}
    start = tuple(old.get("start", [0, 0]))
    if not (0 <= start[0] < MAP_W and 0 <= start[1] < MAP_H):
        start = (0, 0)
    layer = 0
    tile_index = 1
    palette_page = 0
    mode = "paint"
    preview_mode = False
    running = True
    dirty = False
    selection_start = None
    selection_cells = None
    clipboard_layers = None
    clipboard_blocked = set()
    paste_origin = None
    notice_lines = []
    notice_color = (142, 230, 151)
    notice_until = 0
    dialog_mode = None
    new_map_input = ""
    page_input = ""
    resize_input = ""
    open_list = []
    open_cursor = 0
    open_scroll = 0
    # 相机（视口）状态：cam 为地图像素偏移，origin/view 为屏上显示位置与可见尺寸。
    cam_x, cam_y = 0, 0
    origin_x, origin_y = MAP_FRAME.x, MAP_FRAME.y
    view_w, view_h = MAP_W * TILE, MAP_H * TILE
    SCROLL = 64

    def update_camera():
        """按地图大小重算视口：太小则居中(不滚动)，太大则从左上角滚动。"""
        nonlocal cam_x, cam_y, origin_x, origin_y, view_w, view_h
        px_w = MAP_W * TILE
        px_h = MAP_H * TILE
        view_w = min(px_w, MAP_FRAME.width)
        view_h = min(px_h, MAP_FRAME.height)
        if px_w <= MAP_FRAME.width:
            origin_x = MAP_FRAME.x + (MAP_FRAME.width - px_w) // 2
            cam_x = 0
        else:
            origin_x = MAP_FRAME.x
            cam_x = max(0, min(cam_x, px_w - view_w))
        if px_h <= MAP_FRAME.height:
            origin_y = MAP_FRAME.y + (MAP_FRAME.height - px_h) // 2
            cam_y = 0
        else:
            origin_y = MAP_FRAME.y
            cam_y = max(0, min(cam_y, px_h - view_h))

    def pan(dx, dy):
        nonlocal cam_x, cam_y
        cam_x += dx
        cam_y += dy
        update_camera()

    def blit_layer_view(image):
        """把整张地图图层的可见区域画到视口，并裁剪在 MAP_FRAME 内。"""
        screen.set_clip(MAP_FRAME)
        screen.blit(image, (origin_x, origin_y), area=pygame.Rect(cam_x, cam_y, view_w, view_h))
        screen.set_clip(None)

    def map_rect(mx, my, mw, mh):
        """把地图像素矩形换算成屏幕坐标矩形。"""
        return pygame.Rect(origin_x + mx - cam_x, origin_y + my - cam_y, mw, mh)

    def cell_at(pos):
        # 只允许在视口(MAP_FRAME)内取格，避免地图滚动后，点左侧资源区
        # 被误判为地图坐标（cam 偏移会让资源区坐标也算出合法的地图格）。
        if not MAP_FRAME.collidepoint(pos):
            return None
        mx = pos[0] - origin_x + cam_x
        my = pos[1] - origin_y + cam_y
        if not (0 <= mx < MAP_W * TILE and 0 <= my < MAP_H * TILE):
            return None
        return (mx // TILE, my // TILE)

    def paint(cell, erase=False):
        nonlocal dirty
        if cell is None:
            return
        x, y = cell
        rect = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
        if erase:
            layers[layer].fill((0, 0, 0, 0), rect)
        else:
            layers[layer].blit(tiles[tile_index], rect)
        dirty = True

    def normalized_selection(a, b):
        if a is None or b is None:
            return None
        left, right = sorted((a[0], b[0]))
        top, bottom = sorted((a[1], b[1]))
        return pygame.Rect(left, top, right - left + 1, bottom - top + 1)

    def enter_select():
        """Enter visible range-selection mode from a hotkey or toolbar."""
        nonlocal mode, preview_mode, selection_start, selection_cells
        preview_mode = False
        mode = "select"
        selection_start = None
        selection_cells = None

    def show_notice(lines, color=(142, 230, 151), seconds=4):
        """Display a clear, temporary editor confirmation on the map canvas."""
        nonlocal notice_lines, notice_color, notice_until
        notice_lines = list(lines)
        notice_color = color
        notice_until = pygame.time.get_ticks() + seconds * 1000

    def switch_source():
        """按 T / 点击按钮在 TILE_SOURCES 之间切换图块集。"""
        nonlocal source_index, tiles, tile_index, palette_page
        nonlocal mode, preview_mode, selection_start, selection_cells
        nxt = (source_index + 1) % len(TILE_SOURCES)
        new_tiles = load_tiles(TILE_SOURCES[nxt])
        if not new_tiles:
            show_notice([f"图块集 {TILE_SOURCES[nxt]['name']} 为空或找不到，未切换。"], (255, 158, 120), 5)
            return
        source_index = nxt
        tiles = new_tiles
        tile_index = 1
        palette_page = 0
        preview_mode = False
        mode = "paint"
        selection_start = None
        selection_cells = None
        show_notice(
            [f"已切换到图块集：{TILE_SOURCES[source_index]['name']}",
             f"共 {len(tiles)} 个 32×32 图块。按 1/2/3 切层后绘制。"],
            (142, 230, 151),
            5,
        )

    def enter_new_map():
        nonlocal dialog_mode, new_map_input
        dialog_mode = "new"
        new_map_input = ""

    def enter_page_jump():
        nonlocal dialog_mode, page_input
        dialog_mode = "page"
        page_input = ""

    def list_maps():
        """列出所有可打开的地图名（json 配置 + 目录里的 *_lower.png 都算）。"""
        names = set(all_meta.keys())
        for p in OUT.glob("*_lower.png"):
            if p.stem.endswith("_lower"):
                names.add(p.stem[:-len("_lower")])
        return sorted(names)

    def enter_open():
        nonlocal dialog_mode, open_list, open_cursor, open_scroll
        open_list = list_maps()
        if not open_list:
            show_notice(["没有可打开的地图。"], (255, 158, 120), 4)
            return
        open_cursor = open_list.index(name) if name in open_list else 0
        open_scroll = 0
        dialog_mode = "open"

    def open_map(target):
        """切换到已有地图（先自动保存当前未保存的修改）。"""
        nonlocal name, layers, blocked, start, dialog_mode, dirty
        nonlocal cam_x, cam_y, mode, preview_mode
        nonlocal selection_start, selection_cells, clipboard_layers, clipboard_blocked, paste_origin
        global MAP_W, MAP_H
        if target not in list_maps():
            show_notice([f"地图 {target} 不存在。"], (255, 158, 120), 4)
            return
        if dirty:
            save(silent=True)
        name = target
        old = all_meta.get(target, {})
        MAP_W, MAP_H = resolve_size(target, old)
        layers = [load_layer(OUT / f"{target}_{s}.png", MAP_W, MAP_H) for s in ("lower", "current", "upper")]
        blocked = {(x, y) for x, y in ({tuple(c) for c in old.get("blocked", [])}) if x < MAP_W and y < MAP_H}
        start = tuple(old.get("start", [0, 0]))
        if not (0 <= start[0] < MAP_W and 0 <= start[1] < MAP_H):
            start = (0, 0)
        cam_x, cam_y = 0, 0
        update_camera()
        mode, preview_mode = "paint", False
        selection_start = None
        selection_cells = None
        clipboard_layers = None
        clipboard_blocked = set()
        paste_origin = None
        dirty = False
        dialog_mode = None
        pygame.display.set_caption(f"三层地图编辑器 - {name}")
        show_notice([f"已打开地图：{name}（{MAP_W}×{MAP_H} 格）"], (142, 230, 151), 4)

    def open_row_rect(i):
        """打开对话框里第 i 个地图项的屏幕矩形（按滚动偏移换算）。"""
        rel = i - open_scroll
        return pygame.Rect(OPEN_DIALOG.x + 24, OPEN_DIALOG.y + 74 + rel * 34, OPEN_DIALOG.width - 48, 30)

    def enter_resize():
        nonlocal dialog_mode, resize_input
        dialog_mode = "resize"
        resize_input = f"{MAP_W} {MAP_H}"

    def resize_map():
        """调整当前地图尺寸：内容保留在左上角，新区域留空，越界内容丢弃。"""
        nonlocal layers, blocked, start, dialog_mode, resize_input, dirty
        nonlocal cam_x, cam_y
        global MAP_W, MAP_H
        parts = resize_input.strip().split()
        if len(parts) != 2:
            show_notice(["格式应为：新宽 新高，例如 40 30。"], (255, 158, 120), 5)
            return
        try:
            new_w, new_h = int(parts[0]), int(parts[1])
        except ValueError:
            show_notice(["宽和高必须是数字，例如 40 30。"], (255, 158, 120), 5)
            return
        if not (1 <= new_w <= MAX_MAP_W and 1 <= new_h <= MAX_MAP_H):
            show_notice([f"尺寸范围：宽 1-{MAX_MAP_W}，高 1-{MAX_MAP_H}。"], (255, 158, 120), 5)
            return
        if (new_w, new_h) == (MAP_W, MAP_H):
            dialog_mode = None
            show_notice(["尺寸没有变化。"], (255, 158, 120), 3)
            return
        old_w, old_h = MAP_W, MAP_H
        new_layers = []
        for surface in layers:
            ns = pygame.Surface((new_w * TILE, new_h * TILE), pygame.SRCALPHA)
            ns.blit(surface, (0, 0))
            new_layers.append(ns)
        layers = new_layers
        blocked = {(x, y) for x, y in blocked if x < new_w and y < new_h}
        if start[0] >= new_w or start[1] >= new_h:
            start = (0, 0)
        MAP_W, MAP_H = new_w, new_h
        cam_x, cam_y = 0, 0
        update_camera()
        dirty = True
        dialog_mode = None
        resize_input = ""
        show_notice(
            [f"地图已调整为 {new_w}×{new_h} 格（原 {old_w}×{old_h}）",
             "内容保留在左上角，新区域为空；Ctrl+S 保存。"],
            (142, 230, 151),
            5,
        )

    def change_palette_page():
        nonlocal dialog_mode, page_input, palette_page
        page_count = max(1, (len(tiles) + 31) // 32)
        try:
            requested = int(page_input)
        except ValueError:
            show_notice([f"请输入 1 到 {page_count} 之间的页码。"], (255, 158, 120), 5)
            return
        if not 1 <= requested <= page_count:
            show_notice([f"页码超出范围：当前有 {page_count} 页图块。"], (255, 158, 120), 5)
            return
        palette_page = requested - 1
        page_input = ""
        dialog_mode = None
        show_notice([f"已跳转到图块第 {requested} 页（共 {page_count} 页）。"], (142, 230, 151), 4)

    def create_new_map():
        nonlocal name, layers, blocked, start, dialog_mode, new_map_input
        nonlocal cam_x, cam_y
        global MAP_W, MAP_H
        parts = new_map_input.strip().split()
        if len(parts) != 3:
            show_notice(["格式应为：地图名 宽 高，例如 forest2 20 14。"], (255, 158, 120), 5)
            return
        new_name = parts[0]
        if not new_name.replace("_", "").isalnum():
            show_notice(["地图名只能使用字母、数字和下划线。"], (255, 158, 120), 5)
            return
        try:
            new_w, new_h = int(parts[1]), int(parts[2])
        except ValueError:
            show_notice(["宽和高必须是数字，例如 20 14。"], (255, 158, 120), 5)
            return
        if not (1 <= new_w <= MAX_MAP_W and 1 <= new_h <= MAX_MAP_H):
            show_notice([f"当前编辑器支持：宽 1-{MAX_MAP_W} 格，高 1-{MAX_MAP_H} 格。"], (255, 158, 120), 5)
            return
        exists = new_name in all_meta or any((OUT / f"{new_name}_{suffix}.png").exists()
                                               for suffix in ("lower", "current", "upper"))
        if exists:
            show_notice([f"地图 {new_name} 已存在，请换一个名称。"], (255, 158, 120), 5)
            return
        name = new_name
        MAP_W, MAP_H = new_w, new_h
        cam_x, cam_y = 0, 0
        update_camera()
        layers = [pygame.Surface((MAP_W * TILE, MAP_H * TILE), pygame.SRCALPHA) for _ in range(3)]
        blocked = set()
        start = (0, 0)
        dialog_mode = None
        new_map_input = ""
        pygame.display.set_caption(f"三层地图编辑器 - {name}")
        save()
        show_notice([f"已新建 {name}：{MAP_W} × {MAP_H} 格", "已创建三层 PNG 和 outdoor_maps.json 配置。"], (142, 230, 151), 6)

    def copy_selection():
        """Copy the same rectangular area from all three map layers."""
        nonlocal clipboard_layers, clipboard_blocked, mode
        if selection_cells is None:
            return
        rect = selection_cells
        clipboard_layers = [surface.subsurface((rect.x * TILE, rect.y * TILE,
                                                rect.w * TILE, rect.h * TILE)).copy()
                            for surface in layers]
        clipboard_blocked = {(x - rect.x, y - rect.y)
                             for x, y in blocked if rect.collidepoint(x, y)}
        mode = "copied"
        show_notice(
            [f"已复制 {rect.w} × {rect.h} 格：地面层、当前层、上层", f"包含 {len(clipboard_blocked)} 个碰撞格。点击左侧“开始粘贴”或按 Ctrl+V。"],
            (255, 228, 92),
            5,
        )

    def enter_paste():
        nonlocal mode, preview_mode, paste_origin
        if clipboard_layers is None:
            show_notice(["尚未复制内容。先用框选工具拖出范围，再按 Ctrl+C。"], (255, 158, 120))
            return
        preview_mode = False
        mode = "paste"
        paste_origin = None
        show_notice(["粘贴模式：移动鼠标查看黄色目标框，左键放置。", "可连续点击重复粘贴；按 1/2/3 返回绘制。"], (255, 228, 92))

    def paste_at(origin):
        """Replace a destination rectangle with the copied three-layer area."""
        nonlocal dirty, mode, paste_origin
        if clipboard_layers is None:
            return
        width = clipboard_layers[0].get_width() // TILE
        height = clipboard_layers[0].get_height() // TILE
        x = max(0, min(MAP_W - width, origin[0]))
        y = max(0, min(MAP_H - height, origin[1]))
        destination = pygame.Rect(x * TILE, y * TILE, width * TILE, height * TILE)
        for index, image in enumerate(clipboard_layers):
            # Pygame blit does not overwrite transparent source pixels. Clear
            # first so a copied transparent gap correctly removes any old
            # flowers, trunks, or canopy tiles at the destination.
            layers[index].fill((0, 0, 0, 0), destination)
            layers[index].blit(image, (x * TILE, y * TILE))
        # Remove collision cells in the destination rectangle before applying
        # copied cells, matching the way a pasted current-layer tree replaces
        # the previous tree footprint.
        blocked.difference_update({(bx, by) for bx, by in blocked
                                   if x <= bx < x + width and y <= by < y + height})
        blocked.update((x + bx, y + by) for bx, by in clipboard_blocked)
        paste_origin = (x, y)
        # Keep paste mode active so one copied tree/building can be stamped
        # repeatedly with successive clicks.
        mode = "paste"
        dirty = True
        show_notice([f"已粘贴 {width} × {height} 格，三层与碰撞已同步。", "仍处于连续粘贴模式，可继续点击放置。"], (142, 230, 151))

    def save(silent=False):
        nonlocal dirty
        OUT.mkdir(parents=True, exist_ok=True)
        for i, suffix in enumerate(("lower", "current", "upper")):
            pygame.image.save(layers[i], str(OUT / f"{name}_{suffix}.png"))
        all_meta[name] = {
            "size": [MAP_W, MAP_H],
            "start": list(start),
            "blocked": [list(x) for x in sorted(blocked)],
            "layers": {s: f"maps/{name}_{s}.png" for s in ("lower", "current", "upper")},
        }
        meta_path.write_text(json.dumps(all_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        dirty = False
        if not silent:
            show_notice(
                ["地图已保存", f"assets/maps/{name}_lower.png  |  {name}_current.png  |  {name}_upper.png", "配置文件：assets/maps/outdoor_maps.json"],
                (142, 230, 151),
                5,
            )

    def draw_layer_preview():
        """Show the active layer clearly and fade the other two layers."""
        if preview_mode:
            # This is the same three-layer composition used by the game:
            # lower -> current -> upper, without editor overlays.
            for image in layers:
                blit_layer_view(image)
            return
        for i, image in enumerate(layers):
            if i == layer:
                blit_layer_view(image)
            else:
                faded = image.copy()
                faded.set_alpha(72)
                blit_layer_view(faded)

        # Highlight every occupied tile in the active layer.  This is an
        # editor-only overlay; exported PNGs remain unchanged.
        colors = ((92, 210, 255), (255, 190, 75), (205, 145, 255))
        overlay = pygame.Surface((MAP_W * TILE, MAP_H * TILE), pygame.SRCALPHA)
        highlight = colors[layer]
        for y in range(MAP_H):
            for x in range(MAP_W):
                rect = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                if layers[layer].subsurface(rect).get_bounding_rect().width:
                    pygame.draw.rect(overlay, (*highlight, 26), rect)
                    pygame.draw.rect(overlay, (*highlight, 165), rect, 1)
        blit_layer_view(overlay)

    clock = pygame.time.Clock()
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if dialog_mode == "open":
                    if event.key == pygame.K_ESCAPE:
                        dialog_mode = None
                    elif event.key == pygame.K_UP:
                        open_cursor = (open_cursor - 1) % len(open_list)
                    elif event.key == pygame.K_DOWN:
                        open_cursor = (open_cursor + 1) % len(open_list)
                    elif event.key == pygame.K_PAGEUP:
                        open_cursor = max(0, open_cursor - OPEN_VISIBLE)
                    elif event.key == pygame.K_PAGEDOWN:
                        open_cursor = min(len(open_list) - 1, open_cursor + OPEN_VISIBLE)
                    elif event.key == pygame.K_RETURN:
                        if open_list:
                            open_map(open_list[open_cursor])
                    continue
                if dialog_mode:
                    if event.key == pygame.K_ESCAPE:
                        dialog_mode = None
                        new_map_input = ""
                        page_input = ""
                        resize_input = ""
                    elif event.key == pygame.K_RETURN:
                        if dialog_mode == "new":
                            create_new_map()
                        elif dialog_mode == "page":
                            change_palette_page()
                        else:
                            resize_map()
                    elif event.key == pygame.K_BACKSPACE:
                        if dialog_mode == "new":
                            new_map_input = new_map_input[:-1]
                        elif dialog_mode == "page":
                            page_input = page_input[:-1]
                        else:
                            resize_input = resize_input[:-1]
                    else:
                        ch = _event_char(event)
                        if ch:
                            if dialog_mode == "new":
                                new_map_input += ch
                            elif dialog_mode == "page":
                                page_input += ch
                            else:
                                resize_input += ch
                    continue
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_t:
                    switch_source()
                elif event.key == pygame.K_o:
                    enter_open()
                elif event.key == pygame.K_m or getattr(event, "unicode", "").lower() == "m":
                    enter_select()
                elif event.key == pygame.K_n:
                    enter_new_map()
                elif event.key == pygame.K_e:
                    enter_resize()
                elif event.key == pygame.K_g:
                    enter_page_jump()
                elif event.key == pygame.K_s and (event.mod & pygame.KMOD_CTRL):
                    save()
                elif event.key == pygame.K_c and (event.mod & pygame.KMOD_CTRL):
                    copy_selection()
                elif event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
                    enter_paste()
                elif event.key == pygame.K_4:
                    preview_mode = not preview_mode
                    mode = "preview" if preview_mode else "paint"
                    selection_start = None
                    selection_cells = None
                elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    layer = event.key - pygame.K_1
                    preview_mode = False
                    mode = "paint"
                elif event.key == pygame.K_c:
                    mode = "collision" if mode != "collision" else "paint"
                elif event.key == pygame.K_p:
                    mode = "start"
                elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    page_count = max(1, (len(tiles) + 31) // 32)
                    palette_page = max(0, min(page_count - 1, palette_page + (1 if event.key == pygame.K_RIGHT else -1)))
                elif event.key == pygame.K_PAGEUP:
                    palette_page = max(0, palette_page - 1)
                elif event.key == pygame.K_PAGEDOWN:
                    palette_page = min(max(0, (len(tiles) + 31) // 32 - 1), palette_page + 1)
                elif event.key == pygame.K_w:
                    pan(0, -SCROLL)
                elif event.key == pygame.K_s:
                    pan(0, SCROLL)
                elif event.key == pygame.K_a:
                    pan(-SCROLL, 0)
                elif event.key == pygame.K_d:
                    pan(SCROLL, 0)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                # 打开对话框：滚轮滚动列表、左键点选地图。
                if dialog_mode == "open":
                    if event.button == 4:
                        open_cursor = max(0, open_cursor - 1)
                    elif event.button == 5:
                        open_cursor = min(len(open_list) - 1, open_cursor + 1)
                    elif event.button == 1:
                        for i in range(len(open_list)):
                            if 0 <= i - open_scroll < OPEN_VISIBLE and open_row_rect(i).collidepoint(event.pos):
                                open_map(open_list[i])
                                break
                    continue
                # 滚轮：前进/后退=上下，按钮4/5；左右用按钮6/7（如支持）。
                if event.button in (4, 5, 6, 7):
                    if dialog_mode:
                        continue
                    dx = -SCROLL if event.button == 6 else (SCROLL if event.button == 7 else 0)
                    dy = -SCROLL if event.button == 4 else (SCROLL if event.button == 5 else 0)
                    pan(dx, dy)
                    continue
                if event.button in (1, 3):
                    if dialog_mode:
                        continue
                    if event.button == 1 and SAVE_BUTTON.collidepoint(event.pos):
                        save()
                        continue
                    if event.button == 1 and PAGE_BUTTON.collidepoint(event.pos):
                        enter_page_jump()
                        continue
                    if event.button == 1 and SELECT_BUTTON.collidepoint(event.pos):
                        enter_select()
                        continue
                    if event.button == 1 and PASTE_BUTTON.collidepoint(event.pos):
                        enter_paste()
                        continue
                    if event.button == 1 and NEW_BUTTON.collidepoint(event.pos):
                        enter_new_map()
                        continue
                    if event.button == 1 and RESIZE_BUTTON.collidepoint(event.pos):
                        enter_resize()
                        continue
                    if event.button == 1 and OPEN_BUTTON.collidepoint(event.pos):
                        enter_open()
                        continue
                    if event.button == 1 and SOURCE_BUTTON.collidepoint(event.pos):
                        switch_source()
                        continue
                    # 左侧资源区选图块：预览模式下也允许，避免"按了 4 后点不了图块"。
                    if event.button == 1:
                        palette = pygame.Rect(24, 110, 8 * 40, 4 * 40)
                        if palette.collidepoint(event.pos):
                            px, py = event.pos
                            col = (px - palette.x) // 40
                            row = (py - palette.y) // 40
                            candidate = palette_page * 32 + row * 8 + col
                            if candidate < len(tiles):
                                tile_index = candidate
                            continue
                    cell = cell_at(event.pos)
                    if preview_mode:
                        continue
                    if event.button == 1 and (mode == "select" or pygame.key.get_mods() & pygame.KMOD_SHIFT) and cell is not None:
                        if mode != "select":
                            enter_select()
                        selection_start = cell
                        selection_cells = pygame.Rect(cell[0], cell[1], 1, 1)
                    elif mode == "paste" and cell is not None and event.button == 1:
                        paste_at(cell)
                    elif mode == "collision" and cell is not None and layer == 1:
                        (blocked.remove(cell) if cell in blocked else blocked.add(cell))
                        dirty = True
                    elif mode == "start" and cell is not None:
                        start = cell
                        mode = "paint"
                        dirty = True
                    elif cell is not None:
                        paint(cell, erase=event.button == 3)
            elif event.type == pygame.MOUSEMOTION:
                cell = cell_at(event.pos)
                if mode == "select" and selection_start is not None and cell is not None and event.buttons[0]:
                    selection_cells = normalized_selection(selection_start, cell)
                elif mode == "paste" and cell is not None:
                    paste_origin = cell
                elif mode == "paint" and event.buttons[0]:
                    paint(cell_at(event.pos))
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1 and mode == "select" and selection_start is not None:
                    cell = cell_at(event.pos)
                    if cell is not None:
                        selection_cells = normalized_selection(selection_start, cell)
                    if selection_cells is not None:
                        mode = "selected"

        screen.fill((35, 48, 43))
        # Recompute the camera each frame (handles map resize and clamping).
        update_camera()
        # Map preview with active-layer focus.
        draw_layer_preview()
        if not preview_mode:
            screen.set_clip(MAP_FRAME)
            for x, y in blocked:
                r = map_rect(x * TILE, y * TILE, TILE, TILE)
                pygame.draw.rect(screen, (220, 80, 70), (r.x + 2, r.y + 2, TILE - 4, TILE - 4), 2)
            sx, sy = start
            r = map_rect(sx * TILE, sy * TILE, TILE, TILE)
            pygame.draw.rect(screen, (250, 220, 80), (r.x + 5, r.y + 5, TILE - 10, TILE - 10), 2)
            if selection_cells is not None:
                rr = map_rect(selection_cells.x * TILE, selection_cells.y * TILE,
                              selection_cells.w * TILE, selection_cells.h * TILE)
                pygame.draw.rect(screen, (255, 238, 94), rr, 3)
            screen.set_clip(None)
        # 视口边框（大图滚动时的窗口边界；小图即整张地图边界）。
        pygame.draw.rect(screen, (180, 210, 175), MAP_FRAME, 2)
        if mode == "select":
            banner = pygame.Rect(MAP_FRAME.x + 10, MAP_FRAME.y + 10, 410, 38)
            pygame.draw.rect(screen, (28, 68, 62), banner, border_radius=5)
            pygame.draw.rect(screen, (255, 228, 92), banner, 2, border_radius=5)
            screen.blit(font.render("框选模式：按住左键拖出复制范围", True, (255, 243, 180)), (banner.x + 12, banner.y + 8))
        elif mode == "selected" and selection_cells is not None:
            banner = pygame.Rect(MAP_FRAME.x + 10, MAP_FRAME.y + 10, 380, 38)
            pygame.draw.rect(screen, (28, 68, 62), banner, border_radius=5)
            pygame.draw.rect(screen, (255, 228, 92), banner, 2, border_radius=5)
            screen.blit(font.render("已框选：按 Ctrl+C 复制三层内容", True, (255, 243, 180)), (banner.x + 12, banner.y + 8))
        if pygame.time.get_ticks() < notice_until and notice_lines:
            notice_height = 16 + len(notice_lines) * 26
            notice = pygame.Rect(MAP_FRAME.x + 10, MAP_FRAME.bottom - notice_height - 12, MAP_FRAME.width - 20, notice_height)
            pygame.draw.rect(screen, (33, 93, 62), notice, border_radius=6)
            pygame.draw.rect(screen, notice_color, notice, 2, border_radius=6)
            for index, text in enumerate(notice_lines):
                text_font = font if index == 0 else small
                screen.blit(text_font.render(text, True, (232, 255, 218)), (notice.x + 14, notice.y + 5 + index * 26))
        if not preview_mode and mode == "paste" and paste_origin is not None and clipboard_layers is not None:
            pw = clipboard_layers[0].get_width()
            ph = clipboard_layers[0].get_height()
            preview = pygame.Surface((pw, ph), pygame.SRCALPHA)
            for image in clipboard_layers:
                preview.blit(image, (0, 0))
            preview.set_alpha(150)
            px = max(0, min(MAP_W - pw // TILE, paste_origin[0]))
            py = max(0, min(MAP_H - ph // TILE, paste_origin[1]))
            rr = map_rect(px * TILE, py * TILE, pw, ph)
            screen.set_clip(MAP_FRAME)
            screen.blit(preview, (rr.x, rr.y))
            pygame.draw.rect(screen, (255, 238, 94), rr, 3)
            screen.set_clip(None)

        # Palette and controls.
        layer_name = '游戏预览' if preview_mode else ('地面' if layer == 0 else '当前' if layer == 1 else '上层')
        layer_color = ((92, 210, 255), (255, 190, 75), (205, 145, 255))[layer]
        screen.blit(font.render(f"地图：{name}   当前层：{layer_name}", True, (242, 244, 218) if preview_mode else layer_color), (400, 28))
        screen.blit(small.render("1/2/3切层 4预览 M框选 Ctrl+C/V复制粘贴 T图块 O打开 E扩充 WASD平移 Ctrl+S保存 Esc", True, (190, 210, 190)), (400, 50))
        if MAP_W * TILE > MAP_FRAME.width or MAP_H * TILE > MAP_FRAME.height:
            screen.blit(small.render(f"视口可滚动：WASD/滚轮平移（{MAP_W}×{MAP_H} 格）", True, (150, 214, 168)), (400, 68))
        pygame.draw.rect(screen, (20, 30, 28), (8, 78, 368, 620), border_radius=8)
        # 图块集切换按钮（顶部，独立于左侧资源面板，不挤占原布局）。
        source = TILE_SOURCES[source_index]
        source_hot = source_index != 0
        pygame.draw.rect(screen, (61, 109, 87) if source_hot else (48, 74, 64), SOURCE_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (255, 228, 92) if source_hot else (137, 171, 139), SOURCE_BUTTON, 2, border_radius=5)
        screen.blit(font.render(f"图块集：{source['name']}（{len(tiles)} 格）", True, (245, 246, 219)), (SOURCE_BUTTON.x + 16, SOURCE_BUTTON.y + 7))
        screen.blit(small.render("T 切换", True, (205, 220, 198)), (SOURCE_BUTTON.right - 66, SOURCE_BUTTON.y + 12))
        screen.blit(font.render(f"{source['name']} 图块（资源区）", True, (242, 244, 218)), (24, 88))
        palette = pygame.Rect(24, 110, 8 * 40, 4 * 40)
        for i in range(32):
            idx = palette_page * 32 + i
            if idx >= len(tiles):
                break
            x, y = i % 8, i // 8
            tile_img = pygame.transform.scale(tiles[idx], (40, 40))
            screen.blit(tile_img, (palette.x + x * 40, palette.y + y * 40))
            if idx == tile_index:
                pygame.draw.rect(screen, (255, 224, 95), (palette.x + x * 40, palette.y + y * 40, 40, 40), 3)
        page_count = max(1, (len(tiles) + 31) // 32)
        screen.blit(small.render(f"图块编号：{tile_index}   页面：{palette_page + 1}/{page_count}", True, (205, 220, 198)), (24, 290))
        pygame.draw.rect(screen, (48, 74, 64), PAGE_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (137, 171, 139), PAGE_BUTTON, 2, border_radius=5)
        screen.blit(font.render("跳转图块页  [G]", True, (245, 246, 219)), (PAGE_BUTTON.x + 80, PAGE_BUTTON.y + 5))
        screen.blit(small.render("C：碰撞标记模式（仅当前层）", True, (205, 220, 198)), (24, 344))
        screen.blit(small.render("P：设置出生点（点击地图格）", True, (205, 220, 198)), (24, 367))
        screen.blit(small.render("M 或按钮：框选；Shift+左键拖动也可直接框选", True, (205, 220, 198)), (24, 390))
        screen.blit(small.render("4：查看游戏最终合成画面，再按 1/2/3 返回编辑", True, (205, 220, 198)), (24, 413))
        status = f"模式：{mode}" + (" *未保存" if dirty else "")
        screen.blit(font.render(status, True, (238, 194, 117)), (24, 435))
        if preview_mode:
            screen.blit(small.render("当前为游戏画面预览：三层已正常合成", True, (178, 222, 184)), (24, 460))
        else:
            screen.blit(small.render("彩色描边 = 当前编辑层（其他层已变暗）", True, layer_color), (24, 460))
            screen.blit(small.render("红框 = 当前层碰撞   黄框 = 出生点", True, (205, 220, 198)), (24, 485))
        pygame.draw.rect(screen, (61, 109, 87) if dirty else (48, 74, 64), SAVE_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (142, 230, 151) if dirty else (137, 171, 139), SAVE_BUTTON, 2, border_radius=5)
        screen.blit(font.render("保存地图  [Ctrl+S]", True, (245, 246, 219)), (SAVE_BUTTON.x + 66, SAVE_BUTTON.y + 5))
        pygame.draw.rect(screen, (61, 109, 87) if mode == "select" else (48, 74, 64), SELECT_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (255, 228, 92) if mode == "select" else (137, 171, 139), SELECT_BUTTON, 2, border_radius=5)
        screen.blit(font.render("框选工具  [M]", True, (245, 246, 219)), (SELECT_BUTTON.x + 84, SELECT_BUTTON.y + 8))
        paste_active = mode == "paste"
        paste_enabled = clipboard_layers is not None
        pygame.draw.rect(screen, (116, 88, 47) if paste_active else ((61, 109, 87) if paste_enabled else (48, 74, 64)), PASTE_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (255, 228, 92) if paste_active else ((142, 230, 151) if paste_enabled else (100, 125, 105)), PASTE_BUTTON, 2, border_radius=5)
        paste_text = "开始粘贴  [Ctrl+V]" if paste_enabled else "开始粘贴  [先 Ctrl+C]"
        screen.blit(font.render(paste_text, True, (245, 246, 219)), (PASTE_BUTTON.x + 65, PASTE_BUTTON.y + 8))
        new_active = dialog_mode == "new"
        pygame.draw.rect(screen, (61, 109, 87) if new_active else (48, 74, 64), NEW_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (255, 228, 92) if new_active else (137, 171, 139), NEW_BUTTON, 2, border_radius=5)
        screen.blit(font.render("新建地图 [N]", True, (245, 246, 219)), (NEW_BUTTON.x + 16, NEW_BUTTON.y + 8))
        resize_active = dialog_mode == "resize"
        pygame.draw.rect(screen, (61, 109, 87) if resize_active else (48, 74, 64), RESIZE_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (255, 228, 92) if resize_active else (137, 171, 139), RESIZE_BUTTON, 2, border_radius=5)
        screen.blit(font.render("扩充地图 [E]", True, (245, 246, 219)), (RESIZE_BUTTON.x + 16, RESIZE_BUTTON.y + 8))
        open_active = dialog_mode == "open"
        pygame.draw.rect(screen, (61, 109, 87) if open_active else (48, 74, 64), OPEN_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (255, 228, 92) if open_active else (137, 171, 139), OPEN_BUTTON, 2, border_radius=5)
        screen.blit(font.render("打开已有地图  [O]", True, (245, 246, 219)), (OPEN_BUTTON.x + 66, OPEN_BUTTON.y + 3))
        if dialog_mode == "open":
            overlay = pygame.Surface(SCREEN, pygame.SRCALPHA)
            overlay.fill((8, 15, 13, 185))
            screen.blit(overlay, (0, 0))
            dialog = OPEN_DIALOG
            pygame.draw.rect(screen, (28, 55, 45), dialog, border_radius=10)
            pygame.draw.rect(screen, (255, 228, 92), dialog, 3, border_radius=10)
            screen.blit(font.render("打开已有地图", True, (245, 246, 219)), (dialog.x + 24, dialog.y + 20))
            screen.blit(small.render(f"共 {len(open_list)} 张地图。↑/↓ 选择  Enter 打开  Esc 取消", True, (220, 235, 210)), (dialog.x + 24, dialog.y + 48))
            # 滚动窗口：让光标始终可见。
            if open_cursor < open_scroll:
                open_scroll = open_cursor
            if open_cursor >= open_scroll + OPEN_VISIBLE:
                open_scroll = open_cursor - OPEN_VISIBLE + 1
            for i in range(len(open_list)):
                rel = i - open_scroll
                if not (0 <= rel < OPEN_VISIBLE):
                    continue
                rr = open_row_rect(i)
                is_current = open_list[i] == name
                is_cursor = i == open_cursor
                bg = (61, 109, 87) if is_cursor else (40, 62, 54)
                pygame.draw.rect(screen, bg, rr, border_radius=5)
                pygame.draw.rect(screen, (255, 228, 92) if is_cursor else (90, 120, 105), rr, 2, border_radius=5)
                spec = all_meta.get(open_list[i], {})
                size = spec.get("size", [24, 18])
                label = f"{open_list[i]}  （{size[0]}×{size[1]} 格）"
                if is_current:
                    label += "  ·当前"
                screen.blit(small.render(label, True, (245, 246, 219)), (rr.x + 12, rr.y + 7))
            screen.blit(small.render("PgUp/PgDn 翻页   滚轮也可滚动", True, (220, 235, 210)), (dialog.x + 24, dialog.y + dialog.height - 26))
        elif dialog_mode:
            overlay = pygame.Surface(SCREEN, pygame.SRCALPHA)
            overlay.fill((8, 15, 13, 185))
            screen.blit(overlay, (0, 0))
            dialog = pygame.Rect(430, 250, 700, 190)
            pygame.draw.rect(screen, (28, 55, 45), dialog, border_radius=10)
            pygame.draw.rect(screen, (255, 228, 92), dialog, 3, border_radius=10)
            if dialog_mode == "new":
                dialog_title = "新建三层地图"
                dialog_hint = "输入：地图名 宽 高（例如 forest2 20 14）"
                dialog_value = new_map_input
                dialog_placeholder = "地图名 宽 高"
                dialog_footer = f"Enter 创建   Esc 取消   范围：宽 1-{MAX_MAP_W}，高 1-{MAX_MAP_H}"
            elif dialog_mode == "page":
                dialog_title = "跳转图块页"
                dialog_hint = f"输入页码：1 到 {page_count}"
                dialog_value = page_input
                dialog_placeholder = "页码"
                dialog_footer = "Enter 跳转   Esc 取消"
            else:
                dialog_title = "扩充 / 调整地图尺寸"
                dialog_hint = "输入：新宽 新高（例如 40 30），内容保留在左上角"
                dialog_value = resize_input
                dialog_placeholder = f"当前 {MAP_W} × {MAP_H}"
                dialog_footer = f"Enter 调整   Esc 取消   范围：宽 1-{MAX_MAP_W}，高 1-{MAX_MAP_H}"
            screen.blit(font.render(dialog_title, True, (245, 246, 219)), (dialog.x + 24, dialog.y + 20))
            screen.blit(small.render(dialog_hint, True, (220, 235, 210)), (dialog.x + 24, dialog.y + 62))
            pygame.draw.rect(screen, (12, 25, 22), (dialog.x + 24, dialog.y + 92, dialog.width - 48, 42), border_radius=5)
            screen.blit(font.render(dialog_value or dialog_placeholder, True, (245, 246, 219)), (dialog.x + 36, dialog.y + 102))
            screen.blit(small.render(dialog_footer, True, (220, 235, 210)), (dialog.x + 24, dialog.y + 150))
        pygame.display.flip()
        clock.tick(60)
    if dirty:
        save()
    pygame.quit()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "home")

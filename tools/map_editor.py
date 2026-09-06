"""Tiny tile map editor for the STC-B Pokémon prototype.

Run from the project root, for example::

    python tools/map_editor.py home

The editor paints three transparent 32px layers and writes the files consumed
by ``essentials_adventure.py``.  It intentionally has no external dependencies
besides pygame (which the game already uses).
"""
from __future__ import annotations

import json
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
OUT = ASSETS / "maps"
MAP_W, MAP_H, TILE = 24, 18, 32
SCREEN = (1200, 720)
# RPG Maker-like layout: resource palette on the left, map canvas on the right.
CANVAS = pygame.Rect(400, 78, MAP_W * TILE, MAP_H * TILE)
MAP_FRAME = pygame.Rect(400, 78, 768, 576)
SELECT_BUTTON = pygame.Rect(24, 535, 320, 38)
PASTE_BUTTON = pygame.Rect(24, 580, 320, 38)
NEW_BUTTON = pygame.Rect(24, 625, 320, 38)


def load_tiles():
    source = next((path for path in TILESET_CANDIDATES if path.exists()), None)
    if source is None:
        raise FileNotFoundError("找不到 Outside.png，请确认 assets/Outside.png 存在")
    image = pygame.image.load(str(source)).convert_alpha()
    count = image.get_height() // TILE
    return [image.subsurface((x * TILE, y * TILE, TILE, TILE)).copy()
            for y in range(count) for x in range(8)]


def load_or_blank(path: Path):
    if path.exists():
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            pass
    return pygame.Surface((MAP_W * TILE, MAP_H * TILE), pygame.SRCALPHA)


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


def main(name: str):
    global MAP_W, MAP_H, CANVAS
    pygame.init()
    screen = pygame.display.set_mode(SCREEN)
    pygame.display.set_caption(f"三层地图编辑器 - {name}")
    font = make_font(18)
    small = make_font(15)
    meta_path = OUT / "outdoor_maps.json"
    all_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    old = all_meta.get(name, {})
    stored_size = old.get("size", [24, 18])
    MAP_W = max(1, min(24, int(stored_size[0])))
    MAP_H = max(1, min(18, int(stored_size[1])))
    CANVAS = pygame.Rect(
        MAP_FRAME.x + (MAP_FRAME.width - MAP_W * TILE) // 2,
        MAP_FRAME.y + (MAP_FRAME.height - MAP_H * TILE) // 2,
        MAP_W * TILE,
        MAP_H * TILE,
    )
    tiles = load_tiles()
    layers = [load_or_blank(OUT / f"{name}_{layer}.png") for layer in ("lower", "current", "upper")]
    blocked = {tuple(x) for x in old.get("blocked", [])}
    start = tuple(old.get("start", [1, 1]))
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
    dialog_mode = False
    new_map_input = ""

    def cell_at(pos):
        if not CANVAS.collidepoint(pos):
            return None
        return ((pos[0] - CANVAS.x) // TILE, (pos[1] - CANVAS.y) // TILE)

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

    def enter_new_map():
        nonlocal dialog_mode, new_map_input
        dialog_mode = True
        new_map_input = ""

    def create_new_map():
        nonlocal name, layers, blocked, start, dialog_mode, new_map_input
        global MAP_W, MAP_H, CANVAS
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
        if not (1 <= new_w <= 24 and 1 <= new_h <= 18):
            show_notice(["当前编辑器支持：宽 1-24 格，高 1-18 格。"], (255, 158, 120), 5)
            return
        exists = new_name in all_meta or any((OUT / f"{new_name}_{suffix}.png").exists()
                                               for suffix in ("lower", "current", "upper"))
        if exists:
            show_notice([f"地图 {new_name} 已存在，请换一个名称。"], (255, 158, 120), 5)
            return
        name = new_name
        MAP_W, MAP_H = new_w, new_h
        CANVAS = pygame.Rect(
            MAP_FRAME.x + (MAP_FRAME.width - MAP_W * TILE) // 2,
            MAP_FRAME.y + (MAP_FRAME.height - MAP_H * TILE) // 2,
            MAP_W * TILE,
            MAP_H * TILE,
        )
        layers = [pygame.Surface((MAP_W * TILE, MAP_H * TILE), pygame.SRCALPHA) for _ in range(3)]
        blocked = set()
        start = (0, 0)
        dialog_mode = False
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

    def save():
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
                screen.blit(image, CANVAS)
            return
        for i, image in enumerate(layers):
            if i == layer:
                screen.blit(image, CANVAS)
            else:
                faded = image.copy()
                faded.set_alpha(72)
                screen.blit(faded, CANVAS)

        # Highlight every occupied tile in the active layer.  This is an
        # editor-only overlay; exported PNGs remain unchanged.
        colors = ((92, 210, 255), (255, 190, 75), (205, 145, 255))
        overlay = pygame.Surface(CANVAS.size, pygame.SRCALPHA)
        highlight = colors[layer]
        for y in range(MAP_H):
            for x in range(MAP_W):
                rect = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                if layers[layer].subsurface(rect).get_bounding_rect().width:
                    pygame.draw.rect(overlay, (*highlight, 26), rect)
                    pygame.draw.rect(overlay, (*highlight, 165), rect, 1)
        screen.blit(overlay, CANVAS)

    clock = pygame.time.Clock()
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if dialog_mode:
                    if event.key == pygame.K_ESCAPE:
                        dialog_mode = False
                        new_map_input = ""
                    elif event.key == pygame.K_RETURN:
                        create_new_map()
                    elif event.key == pygame.K_BACKSPACE:
                        new_map_input = new_map_input[:-1]
                    elif getattr(event, "unicode", "").isprintable():
                        new_map_input += event.unicode
                    continue
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_s:
                    save()
                elif event.key == pygame.K_m or getattr(event, "unicode", "").lower() == "m":
                    enter_select()
                elif event.key == pygame.K_n:
                    enter_new_map()
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
                    palette_page = max(0, palette_page + (1 if event.key == pygame.K_RIGHT else -1))
                elif event.key == pygame.K_PAGEUP:
                    palette_page = max(0, palette_page - 1)
                elif event.key == pygame.K_PAGEDOWN:
                    palette_page += 1
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button in (1, 3):
                    if dialog_mode:
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
                    else:
                        px, py = event.pos
                        palette = pygame.Rect(24, 110, 8 * 40, 4 * 40)
                        if palette.collidepoint(event.pos):
                            col = (px - palette.x) // 40
                            row = (py - palette.y) // 40
                            candidate = palette_page * 32 + row * 8 + col
                            if candidate < len(tiles):
                                tile_index = candidate
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
        # Map preview with active-layer focus.
        draw_layer_preview()
        if not preview_mode:
            for x, y in blocked:
                pygame.draw.rect(screen, (220, 80, 70), (CANVAS.x + x * TILE + 2, CANVAS.y + y * TILE + 2, TILE - 4, TILE - 4), 2)
            sx, sy = start
            pygame.draw.rect(screen, (250, 220, 80), (CANVAS.x + sx * TILE + 5, CANVAS.y + sy * TILE + 5, TILE - 10, TILE - 10), 2)
        pygame.draw.rect(screen, (180, 210, 175), CANVAS, 2)
        if not preview_mode and selection_cells is not None:
            selection_rect = pygame.Rect(CANVAS.x + selection_cells.x * TILE,
                                         CANVAS.y + selection_cells.y * TILE,
                                         selection_cells.w * TILE,
                                         selection_cells.h * TILE)
            pygame.draw.rect(screen, (255, 238, 94), selection_rect, 3)
        if mode == "select":
            banner = pygame.Rect(CANVAS.x + 10, CANVAS.y + 10, 410, 38)
            pygame.draw.rect(screen, (28, 68, 62), banner, border_radius=5)
            pygame.draw.rect(screen, (255, 228, 92), banner, 2, border_radius=5)
            screen.blit(font.render("框选模式：按住左键拖出复制范围", True, (255, 243, 180)), (banner.x + 12, banner.y + 8))
        elif mode == "selected" and selection_cells is not None:
            banner = pygame.Rect(CANVAS.x + 10, CANVAS.y + 10, 380, 38)
            pygame.draw.rect(screen, (28, 68, 62), banner, border_radius=5)
            pygame.draw.rect(screen, (255, 228, 92), banner, 2, border_radius=5)
            screen.blit(font.render("已框选：按 Ctrl+C 复制三层内容", True, (255, 243, 180)), (banner.x + 12, banner.y + 8))
        if pygame.time.get_ticks() < notice_until and notice_lines:
            notice_height = 16 + len(notice_lines) * 26
            notice = pygame.Rect(CANVAS.x + 10, CANVAS.bottom - notice_height - 12, CANVAS.width - 20, notice_height)
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
            screen.blit(preview, (CANVAS.x + px * TILE, CANVAS.y + py * TILE))
            pygame.draw.rect(screen, (255, 238, 94),
                             (CANVAS.x + px * TILE, CANVAS.y + py * TILE, pw, ph), 3)

        # Palette and controls.
        layer_name = '游戏预览' if preview_mode else ('地面' if layer == 0 else '当前' if layer == 1 else '上层')
        layer_color = ((92, 210, 255), (255, 190, 75), (205, 145, 255))[layer]
        screen.blit(font.render(f"地图：{name}   当前层：{layer_name}", True, (242, 244, 218) if preview_mode else layer_color), (400, 28))
        screen.blit(small.render("1/2/3 切层  4游戏预览  M框选  Ctrl+C复制  Ctrl+V粘贴  S保存  Esc退出", True, (190, 210, 190)), (400, 50))
        pygame.draw.rect(screen, (20, 30, 28), (8, 78, 368, 620), border_radius=8)
        screen.blit(font.render("Outside 图块（资源区）", True, (242, 244, 218)), (24, 88))
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
        screen.blit(small.render(f"图块编号：{tile_index}   页面：{palette_page}（←/→翻页）", True, (205, 220, 198)), (24, 290))
        screen.blit(small.render("C：碰撞标记模式（仅当前层）", True, (205, 220, 198)), (24, 326))
        screen.blit(small.render("P：设置出生点（点击地图格）", True, (205, 220, 198)), (24, 351))
        screen.blit(small.render("M 或按钮：框选；Shift+左键拖动也可直接框选", True, (205, 220, 198)), (24, 375))
        screen.blit(small.render("4：查看游戏最终合成画面，再按 1/2/3 返回编辑", True, (205, 220, 198)), (24, 398))
        status = f"模式：{mode}" + (" *未保存" if dirty else "")
        screen.blit(font.render(status, True, (238, 194, 117)), (24, 435))
        if preview_mode:
            screen.blit(small.render("当前为游戏画面预览：三层已正常合成", True, (178, 222, 184)), (24, 460))
        else:
            screen.blit(small.render("彩色描边 = 当前编辑层（其他层已变暗）", True, layer_color), (24, 460))
            screen.blit(small.render("红框 = 当前层碰撞   黄框 = 出生点", True, (205, 220, 198)), (24, 485))
        pygame.draw.rect(screen, (61, 109, 87) if mode == "select" else (48, 74, 64), SELECT_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (255, 228, 92) if mode == "select" else (137, 171, 139), SELECT_BUTTON, 2, border_radius=5)
        screen.blit(font.render("框选工具  [M]", True, (245, 246, 219)), (SELECT_BUTTON.x + 84, SELECT_BUTTON.y + 8))
        paste_active = mode == "paste"
        paste_enabled = clipboard_layers is not None
        pygame.draw.rect(screen, (116, 88, 47) if paste_active else ((61, 109, 87) if paste_enabled else (48, 74, 64)), PASTE_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (255, 228, 92) if paste_active else ((142, 230, 151) if paste_enabled else (100, 125, 105)), PASTE_BUTTON, 2, border_radius=5)
        paste_text = "开始粘贴  [Ctrl+V]" if paste_enabled else "开始粘贴  [先 Ctrl+C]"
        screen.blit(font.render(paste_text, True, (245, 246, 219)), (PASTE_BUTTON.x + 65, PASTE_BUTTON.y + 8))
        pygame.draw.rect(screen, (61, 109, 87) if dialog_mode else (48, 74, 64), NEW_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (255, 228, 92) if dialog_mode else (137, 171, 139), NEW_BUTTON, 2, border_radius=5)
        screen.blit(font.render("新建地图  [N]", True, (245, 246, 219)), (NEW_BUTTON.x + 80, NEW_BUTTON.y + 8))
        screen.blit(small.render("框选后：Ctrl+C 复制，再点击“开始粘贴”", True, (175, 196, 175)), (24, 672))
        if dialog_mode:
            overlay = pygame.Surface(SCREEN, pygame.SRCALPHA)
            overlay.fill((8, 15, 13, 185))
            screen.blit(overlay, (0, 0))
            dialog = pygame.Rect(430, 250, 700, 190)
            pygame.draw.rect(screen, (28, 55, 45), dialog, border_radius=10)
            pygame.draw.rect(screen, (255, 228, 92), dialog, 3, border_radius=10)
            screen.blit(font.render("新建三层地图", True, (245, 246, 219)), (dialog.x + 24, dialog.y + 20))
            screen.blit(small.render("输入：地图名 宽 高（例如 forest2 20 14）", True, (220, 235, 210)), (dialog.x + 24, dialog.y + 62))
            pygame.draw.rect(screen, (12, 25, 22), (dialog.x + 24, dialog.y + 92, dialog.width - 48, 42), border_radius=5)
            screen.blit(font.render(new_map_input or "地图名 宽 高", True, (245, 246, 219)), (dialog.x + 36, dialog.y + 102))
            screen.blit(small.render("Enter 创建   Esc 取消   范围：宽 1-24，高 1-18", True, (220, 235, 210)), (dialog.x + 24, dialog.y + 150))
        pygame.display.flip()
        clock.tick(60)
    if dirty:
        save()
    pygame.quit()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "home")

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
    pygame.init()
    screen = pygame.display.set_mode(SCREEN)
    pygame.display.set_caption(f"三层地图编辑器 - {name}")
    font = make_font(18)
    small = make_font(15)
    tiles = load_tiles()
    layers = [load_or_blank(OUT / f"{name}_{layer}.png") for layer in ("lower", "current", "upper")]
    meta_path = OUT / "outdoor_maps.json"
    all_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    old = all_meta.get(name, {})
    blocked = {tuple(x) for x in old.get("blocked", [])}
    start = tuple(old.get("start", [1, 1]))
    layer = 0
    tile_index = 1
    palette_page = 0
    mode = "paint"
    running = True
    dirty = False
    selection_start = None
    selection_cells = None
    clipboard_layers = None
    clipboard_blocked = set()
    paste_origin = None

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

    def copy_selection():
        """Copy all three layers and current-layer collision cells."""
        nonlocal clipboard_layers, clipboard_blocked, mode
        if selection_cells is None:
            return
        rect = selection_cells
        clipboard_layers = [surface.subsurface((rect.x * TILE, rect.y * TILE,
                                                rect.w * TILE, rect.h * TILE)).copy()
                            for surface in layers]
        clipboard_blocked = {(x - rect.x, y - rect.y)
                             for x, y in blocked if rect.collidepoint(x, y)}
        mode = "paste_ready"

    def paste_at(origin):
        """Paste the copied rectangle, keeping it inside the map."""
        nonlocal dirty, mode, paste_origin
        if clipboard_layers is None:
            return
        width = clipboard_layers[0].get_width() // TILE
        height = clipboard_layers[0].get_height() // TILE
        x = max(0, min(MAP_W - width, origin[0]))
        y = max(0, min(MAP_H - height, origin[1]))
        for index, image in enumerate(clipboard_layers):
            layers[index].blit(image, (x * TILE, y * TILE))
        # Remove collision cells in the destination rectangle before applying
        # copied cells, matching the way a pasted current-layer tree replaces
        # the previous tree footprint.
        blocked.difference_update({(bx, by) for bx, by in blocked
                                   if x <= bx < x + width and y <= by < y + height})
        blocked.update((x + bx, y + by) for bx, by in clipboard_blocked)
        paste_origin = (x, y)
        mode = "paint"
        dirty = True

    def save():
        nonlocal dirty
        OUT.mkdir(parents=True, exist_ok=True)
        for i, suffix in enumerate(("lower", "current", "upper")):
            layers[i].save(OUT / f"{name}_{suffix}.png")
        all_meta[name] = {
            "size": [MAP_W, MAP_H],
            "start": list(start),
            "blocked": [list(x) for x in sorted(blocked)],
            "layers": {s: f"maps/{name}_{s}.png" for s in ("lower", "current", "upper")},
        }
        meta_path.write_text(json.dumps(all_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        dirty = False

    def draw_layer_preview():
        """Show the active layer clearly and fade the other two layers."""
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
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_s:
                    save()
                elif event.key == pygame.K_m:
                    mode = "select"
                    selection_start = None
                    selection_cells = None
                elif event.key == pygame.K_c and (event.mod & pygame.KMOD_CTRL):
                    copy_selection()
                elif event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
                    if clipboard_layers is not None:
                        mode = "paste"
                elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    layer = event.key - pygame.K_1
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
                    cell = cell_at(event.pos)
                    if mode == "select" and cell is not None and event.button == 1:
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
        for x, y in blocked:
            pygame.draw.rect(screen, (220, 80, 70), (CANVAS.x + x * TILE + 2, CANVAS.y + y * TILE + 2, TILE - 4, TILE - 4), 2)
        sx, sy = start
        pygame.draw.rect(screen, (250, 220, 80), (CANVAS.x + sx * TILE + 5, CANVAS.y + sy * TILE + 5, TILE - 10, TILE - 10), 2)
        pygame.draw.rect(screen, (180, 210, 175), CANVAS, 2)
        if selection_cells is not None:
            selection_rect = pygame.Rect(CANVAS.x + selection_cells.x * TILE,
                                         CANVAS.y + selection_cells.y * TILE,
                                         selection_cells.w * TILE,
                                         selection_cells.h * TILE)
            pygame.draw.rect(screen, (255, 238, 94), selection_rect, 3)
        if mode == "paste" and paste_origin is not None and clipboard_layers is not None:
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
        layer_name = ('地面' if layer == 0 else '当前' if layer == 1 else '上层')
        layer_color = ((92, 210, 255), (255, 190, 75), (205, 145, 255))[layer]
        screen.blit(font.render(f"地图：{name}   当前层：{layer_name}", True, layer_color), (400, 28))
        screen.blit(small.render("1/2/3 切层  M框选  Ctrl+C复制  Ctrl+V粘贴  S保存  Esc退出", True, (190, 210, 190)), (400, 50))
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
        screen.blit(small.render("M：框选三层，Ctrl+C复制，Ctrl+V后点击地图粘贴", True, (205, 220, 198)), (24, 375))
        status = f"模式：{mode}" + (" *未保存" if dirty else "")
        screen.blit(font.render(status, True, (238, 194, 117)), (24, 410))
        screen.blit(small.render("彩色描边 = 当前编辑层（其他层已变暗）", True, layer_color), (24, 430))
        screen.blit(small.render("红框 = 当前层碰撞   黄框 = 出生点", True, (205, 220, 198)), (24, 455))
        screen.blit(small.render("建议：地面层铺草地/道路，当前层放花草水边，", True, (175, 196, 175)), (24, 490))
        screen.blit(small.render("上层放树冠；上层不会阻挡角色。", True, (175, 196, 175)), (24, 515))
        pygame.display.flip()
        clock.tick(60)
    if dirty:
        save()
    pygame.quit()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "home")

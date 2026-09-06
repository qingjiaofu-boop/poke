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
MAX_MAP_W, MAX_MAP_H = 40, 40
VIEW_TILE = TILE
SCREEN = (1600, 900)
# RPG Maker-like layout: resource palette on the left, map canvas on the right.
CANVAS = pygame.Rect(450, 78, MAP_W * TILE, MAP_H * TILE)
MAP_FRAME = pygame.Rect(450, 78, 1120, 760)
PAGE_BUTTON = pygame.Rect(24, 306, 320, 30)
SAVE_BUTTON = pygame.Rect(24, 502, 320, 31)
SELECT_BUTTON = pygame.Rect(24, 535, 320, 38)
PASTE_BUTTON = pygame.Rect(24, 580, 320, 38)
NEW_BUTTON = pygame.Rect(24, 625, 320, 38)
OPEN_BUTTON = pygame.Rect(24, 670, 320, 38)
WORLD_BUTTON = pygame.Rect(24, 715, 320, 38)
WORLD_LAYOUT = OUT / "world_layout.json"
WORLD_DEFAULT_SIZE = (120, 120)
WORLD_MAX_SIZE = (120, 120)


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


def load_map_surface_set(map_name: str, spec: dict):
    """Load the three exported layers for a map listed in outdoor_maps.json."""
    layers = spec.get("layers", {})
    result = []
    for suffix in ("lower", "current", "upper"):
        relative = layers.get(suffix, f"maps/{map_name}_{suffix}.png")
        path = ASSETS / relative
        if not path.exists():
            path = OUT / f"{map_name}_{suffix}.png"
        try:
            result.append(pygame.image.load(str(path)).convert_alpha())
        except (pygame.error, OSError):
            size = spec.get("size", [24, 18])
            result.append(pygame.Surface((int(size[0]) * TILE, int(size[1]) * TILE), pygame.SRCALPHA))
    return result


def run_world_editor(screen, font, small, all_meta):
    """Edit and preview a simple multi-map overworld layout.

    Placement coordinates are stored in map cells, so the layout remains
    independent of the editor's display zoom.  The generated PNGs are useful
    as a complete stitched background, while the JSON remains the editable
    source of truth.
    """
    world_meta = {}
    if WORLD_LAYOUT.exists():
        try:
            world_meta = json.loads(WORLD_LAYOUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            world_meta = {}
    stored_world_size = world_meta.get("size")
    # Migrate older implicit defaults while preserving all existing map
    # coordinates. The extra rows are available immediately on next save.
    if not stored_world_size or list(stored_world_size) in ([80, 60], [120, 80]):
        stored_world_size = WORLD_DEFAULT_SIZE
    world_w, world_h = stored_world_size
    world_w = max(1, min(WORLD_MAX_SIZE[0], int(world_w)))
    world_h = max(1, min(WORLD_MAX_SIZE[1], int(world_h)))
    placements = [dict(item) for item in world_meta.get("placements", [])
                  if item.get("map") in all_meta]
    used_ids = set()
    for index, item in enumerate(placements):
        base_id = str(item.get("id") or f"{item['map']}_{index + 1}")
        item_id = base_id
        suffix = 2
        while item_id in used_ids:
            item_id = f"{base_id}_{suffix}"
            suffix += 1
        item["id"] = item_id
        item["rotation"] = int(item.get("rotation", 0)) % 360
        used_ids.add(item_id)
    map_names = list(all_meta.keys())
    map_surfaces = {map_name: load_map_surface_set(map_name, all_meta[map_name])
                    for map_name in map_names}
    selected = map_names.index(placements[0]["map"]) if placements else 0
    selected = min(selected, max(0, len(map_names) - 1))
    selected_placement = len(placements) - 1 if placements else None
    notice = ""
    notice_until = 0
    dirty = False
    preview_only = False
    sidebar_visible = True
    zoom = 1.0
    pan_x = 0
    pan_y = 0
    dragging = False
    drag_pos = None
    clock = pygame.time.Clock()
    frame = pygame.Rect(390, 70, 1180, 780)
    list_rect = pygame.Rect(18, 110, 340, 690)
    view_tile = 8
    canvas = pygame.Rect(0, 0, 1, 1)

    def update_view():
        """Fit or zoom the world canvas into the available workspace."""
        nonlocal frame, list_rect, view_tile, canvas, pan_x, pan_y
        screen_w, screen_h = screen.get_size()
        if sidebar_visible:
            sidebar_width = 370
            frame = pygame.Rect(sidebar_width + 20, 70,
                                max(240, screen_w - sidebar_width - 40),
                                max(240, screen_h - 130))
        else:
            # Use nearly the entire window in large-canvas mode.
            frame = pygame.Rect(10, 55, max(240, screen_w - 20), max(240, screen_h - 80))
        list_rect = pygame.Rect(18, 110, 340, max(180, screen_h - 210))
        # Do not cap the fit scale at the old 16px value. In large-canvas mode
        # the wider frame should visibly provide more room when possible.
        fit_tile = min(frame.width // max(1, world_w), frame.height // max(1, world_h))
        view_tile = max(4, int(fit_tile * zoom))
        canvas_width = world_w * view_tile
        canvas_height = world_h * view_tile
        max_pan_x = max(0, canvas_width - frame.width)
        max_pan_y = max(0, canvas_height - frame.height)
        pan_x = min(max(0, pan_x), max_pan_x)
        pan_y = min(max(0, pan_y), max_pan_y)
        canvas_x = (frame.x + (frame.width - canvas_width) // 2
                    if canvas_width <= frame.width else frame.x - pan_x)
        canvas_y = (frame.y + (frame.height - canvas_height) // 2
                    if canvas_height <= frame.height else frame.y - pan_y)
        canvas = pygame.Rect(canvas_x, canvas_y, canvas_width, canvas_height)

    update_view()

    def show(text, seconds=4):
        nonlocal notice, notice_until
        notice = text
        notice_until = pygame.time.get_ticks() + seconds * 1000

    def save_world():
        nonlocal dirty
        WORLD_LAYOUT.parent.mkdir(parents=True, exist_ok=True)
        manifest = connection_manifest()
        text_lines = [f"箱庭尺寸：{world_w}×{world_h} 格", "", "地图位置："]
        for item in manifest["maps"]:
            text_lines.append(
                f"- {item['id']} = {item['map']}，位置 ({item['position']['x']},{item['position']['y']})，"
                f"尺寸 {item['size']['width']}×{item['size']['height']}，旋转 {item['rotation']}°"
            )
        text_lines.append("")
        text_lines.append("地图连接：")
        if manifest["connections"]:
            for link in manifest["connections"]:
                world_range = link["world_range"]
                text_lines.append(
                    f"- {link['from']}.{link['from_edge']} → {link['to']}.{link['to_edge']}，"
                    f"世界 {world_range['axis']}={world_range['start']}..{world_range['end']}，"
                    f"前者局部 {link['from_local_range']['start']}..{link['from_local_range']['end']}，"
                    f"后者局部 {link['to_local_range']['start']}..{link['to_local_range']['end']}"
                )
        else:
            text_lines.append("- 暂无边缘对齐的地图连接。")
        data = {"size": [world_w, world_h], "placements": placements,
                "connections": manifest["connections"],
                "connection_manifest": "maps/world_connections.json",
                "connection_text_manifest": "maps/world_connections.txt",
                "preview": {s: f"maps/world_{s}.png" for s in ("lower", "current", "upper")}}
        WORLD_LAYOUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "world_connections.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "world_connections.txt").write_text("\n".join(text_lines) + "\n", encoding="utf-8")
        composites = [pygame.Surface((world_w * TILE, world_h * TILE), pygame.SRCALPHA) for _ in range(3)]
        for item in placements:
            for index, image in enumerate(map_surfaces[item["map"]]):
                rotation = int(item.get("rotation", 0)) % 360
                if rotation:
                    image = pygame.transform.rotate(image, -rotation)
                composites[index].blit(image, (int(item.get("x", 0)) * TILE, int(item.get("y", 0)) * TILE))
        for index, suffix in enumerate(("lower", "current", "upper")):
            pygame.image.save(composites[index], str(OUT / f"world_{suffix}.png"))
        dirty = False
        show(f"箱庭已保存：{len(manifest['connections'])} 条连接，已导出 JSON 和 TXT 清单", 5)

    def map_card_at(pos):
        if not list_rect.collidepoint(pos):
            return None
        index = (pos[1] - list_rect.y) // 42
        return index if 0 <= index < len(map_names) else None

    def world_cell_at(pos):
        if not frame.collidepoint(pos) or not canvas.collidepoint(pos):
            return None
        return ((pos[0] - canvas.x) // view_tile, (pos[1] - canvas.y) // view_tile)

    def map_size(map_name):
        size = all_meta.get(map_name, {}).get("size", [24, 18])
        return int(size[0]), int(size[1])

    def placement_size(item):
        width, height = map_size(item["map"])
        if int(item.get("rotation", 0)) % 180:
            return height, width
        return width, height

    def rotated_surface(surface, item):
        rotation = int(item.get("rotation", 0)) % 360
        return pygame.transform.rotate(surface, -rotation) if rotation else surface

    def new_placement_id(map_name):
        """Return a stable readable id without colliding with old placements."""
        used = {str(item.get("id", "")) for item in placements}
        number = 1
        candidate = f"{map_name}_{number}"
        while candidate in used:
            number += 1
            candidate = f"{map_name}_{number}"
        return candidate

    def placement_at(cell):
        """Return the topmost placed map containing a world cell."""
        for index in range(len(placements) - 1, -1, -1):
            item = placements[index]
            width, height = placement_size(item)
            x, y = int(item.get("x", 0)), int(item.get("y", 0))
            if x <= cell[0] < x + width and y <= cell[1] < y + height:
                return index
        return None

    def connection_manifest():
        """Build explicit edge-to-edge connections for the current layout."""
        exported = []
        for item in placements:
            width, height = placement_size(item)
            x, y = int(item.get("x", 0)), int(item.get("y", 0))
            exported.append({
                "id": item["id"], "map": item["map"],
                "rotation": int(item.get("rotation", 0)) % 360,
                "position": {"x": x, "y": y},
                "size": {"width": width, "height": height},
                "bounds": {"left": x, "top": y, "right": x + width, "bottom": y + height},
                "edges": {
                    "left": {"x": x, "y": [y, y + height]},
                    "right": {"x": x + width, "y": [y, y + height]},
                    "top": {"y": y, "x": [x, x + width]},
                    "bottom": {"y": y + height, "x": [x, x + width]},
                },
            })
        connections = []
        for first in range(len(placements)):
            a = placements[first]
            aw, ah = placement_size(a)
            ax, ay = int(a.get("x", 0)), int(a.get("y", 0))
            for second in range(first + 1, len(placements)):
                b = placements[second]
                bw, bh = placement_size(b)
                bx, by = int(b.get("x", 0)), int(b.get("y", 0))
                if ax + aw == bx or bx + bw == ax:
                    start, end = max(ay, by), min(ay + ah, by + bh)
                    if start < end:
                        left, right = (a, b) if ax + aw == bx else (b, a)
                        left_y = int(left.get("y", 0))
                        right_y = int(right.get("y", 0))
                        connections.append({"type": "edge", "axis": "vertical",
                                            "from": left["id"], "to": right["id"],
                                            "from_edge": "right", "to_edge": "left",
                                            "world_range": {"axis": "y", "start": start, "end": end},
                                            "from_local_range": {"axis": "y", "start": start - left_y, "end": end - left_y},
                                            "to_local_range": {"axis": "y", "start": start - right_y, "end": end - right_y}})
                if ay + ah == by or by + bh == ay:
                    start, end = max(ax, bx), min(ax + aw, bx + bw)
                    if start < end:
                        top, bottom = (a, b) if ay + ah == by else (b, a)
                        top_x = int(top.get("x", 0))
                        bottom_x = int(bottom.get("x", 0))
                        connections.append({"type": "edge", "axis": "horizontal",
                                            "from": top["id"], "to": bottom["id"],
                                            "from_edge": "bottom", "to_edge": "top",
                                            "world_range": {"axis": "x", "start": start, "end": end},
                                            "from_local_range": {"axis": "x", "start": start - top_x, "end": end - top_x},
                                            "to_local_range": {"axis": "x", "start": start - bottom_x, "end": end - bottom_x}})
        return {"world_size": [world_w, world_h], "maps": exported, "connections": connections}

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_TAB:
                    sidebar_visible = not sidebar_visible
                    if not sidebar_visible and zoom <= 1.0:
                        zoom = 1.25
                    elif sidebar_visible and zoom == 1.25:
                        zoom = 1.0
                    update_view()
                    show("已切换大画布模式；Tab 可显示或隐藏左侧地图栏，0 可恢复适配。", 3)
                elif event.key == pygame.K_0:
                    zoom = 1.0
                    pan_x = pan_y = 0
                    update_view()
                    show("已恢复完整箱庭视图。", 2)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    zoom = max(0.35, zoom / 1.25)
                    update_view()
                    show(f"画布缩放：{int(zoom * 100)}%", 2)
                elif event.key in (pygame.K_EQUALS, pygame.K_KP_PLUS):
                    zoom = min(4.0, zoom * 1.25)
                    update_view()
                    show(f"画布缩放：{int(zoom * 100)}%", 2)
                elif event.key == pygame.K_s:
                    save_world()
                elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                    if selected_placement is not None and selected_placement < len(placements):
                        step = 5 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1
                        dx = (1 if event.key == pygame.K_RIGHT else -1 if event.key == pygame.K_LEFT else 0) * step
                        dy = (1 if event.key == pygame.K_DOWN else -1 if event.key == pygame.K_UP else 0) * step
                        item = placements[selected_placement]
                        width, height = placement_size(item)
                        item["x"] = min(max(0, int(item.get("x", 0)) + dx), max(0, world_w - width))
                        item["y"] = min(max(0, int(item.get("y", 0)) + dy), max(0, world_h - height))
                        dirty = True
                        show(f"已移动 {item['map']} 到 ({item['x']}, {item['y']})。Shift+方向键可快速移动。", 2)
                elif event.key == pygame.K_r:
                    if selected_placement is not None and selected_placement < len(placements):
                        item = placements[selected_placement]
                        old_width, old_height = placement_size(item)
                        item["rotation"] = (int(item.get("rotation", 0)) + 90) % 360
                        new_width, new_height = placement_size(item)
                        # Keep the block centered as its width and height swap.
                        center_x = int(item.get("x", 0)) * 2 + old_width
                        center_y = int(item.get("y", 0)) * 2 + old_height
                        item["x"] = min(max(0, (center_x - new_width + 1) // 2), max(0, world_w - new_width))
                        item["y"] = min(max(0, (center_y - new_height + 1) // 2), max(0, world_h - new_height))
                        dirty = True
                        show(f"已旋转 {item['map']}：{item['rotation']}°，位置 ({item['x']},{item['y']})。", 3)
                elif event.key == pygame.K_DELETE:
                    if selected_placement is not None and selected_placement < len(placements):
                        removed = placements.pop(selected_placement)
                        selected_placement = min(selected_placement, len(placements) - 1) if placements else None
                        dirty = True
                        show(f"已删除 {removed['map']}。", 3)
                elif event.key == pygame.K_4:
                    preview_only = not preview_only
                elif event.key == pygame.K_RETURN and dirty:
                    save_world()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 2:
                    dragging = True
                    drag_pos = event.pos
                    continue
                if event.button == 1:
                    card = map_card_at(event.pos)
                    if card is not None:
                        selected = card
                        selected_placement = None
                        continue
                    cell = world_cell_at(event.pos)
                    if cell is not None and map_names:
                        existing = placement_at(cell)
                        if existing is not None:
                            selected_placement = existing
                            selected = map_names.index(placements[existing]["map"])
                            show(f"已选中 {placements[existing]['map']}，使用方向键移动，Delete 删除。", 3)
                            continue
                        map_name = map_names[selected]
                        spec = all_meta[map_name]
                        size = spec.get("size", [24, 18])
                        map_width, map_height = int(size[0]), int(size[1])
                        x = min(max(0, cell[0]), max(0, world_w - map_width))
                        y = min(max(0, cell[1]), max(0, world_h - map_height))
                        placements.append({"id": new_placement_id(map_name), "map": map_name,
                                           "x": x, "y": y, "rotation": 0})
                        selected_placement = len(placements) - 1
                        dirty = True
                        show(f"已放置 {map_name}，左键可继续放置，右键删除地图块。")
                elif event.button == 3:
                    cell = world_cell_at(event.pos)
                    if cell is not None:
                        existing = placement_at(cell)
                        if existing is not None:
                            removed = placements.pop(existing)
                            selected_placement = min(existing, len(placements) - 1) if placements else None
                            dirty = True
                            show(f"已移除 {removed['map']}。")
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 2:
                    dragging = False
                    drag_pos = None
            elif event.type == pygame.MOUSEMOTION and dragging and drag_pos is not None:
                pan_x -= event.pos[0] - drag_pos[0]
                pan_y -= event.pos[1] - drag_pos[1]
                drag_pos = event.pos
                update_view()
            elif event.type == pygame.MOUSEWHEEL and frame.collidepoint(pygame.mouse.get_pos()):
                zoom = min(4.0, zoom * 1.25) if event.y > 0 else max(0.35, zoom / 1.25)
                update_view()
                show(f"画布缩放：{int(zoom * 100)}%", 2)

        screen.fill((35, 48, 43))
        screen.blit(font.render("箱庭地图拼接工作区", True, (242, 244, 218)), (18, 28))
        help_text = ("空白处左键放置，点击地图后方向键移动，R 旋转，Shift 加速，Delete 删除；"
                     "滚轮缩放，中键拖动，Tab 大画布，0 适配，S 保存；Esc 返回")
        screen.blit(small.render(help_text, True, (190, 210, 190)), (frame.x, 40))
        if sidebar_visible:
            pygame.draw.rect(screen, (20, 30, 28), list_rect, border_radius=8)
            screen.blit(font.render("可用地图", True, (242, 244, 218)), (32, 78))
            for index, map_name in enumerate(map_names):
                y = list_rect.y + index * 42
                if y + 38 > list_rect.bottom:
                    break
                active = index == selected
                rect = pygame.Rect(list_rect.x + 8, y, list_rect.width - 16, 36)
                pygame.draw.rect(screen, (61, 109, 87) if active else (42, 61, 52), rect, border_radius=5)
                pygame.draw.rect(screen, (255, 228, 92) if active else (100, 125, 105), rect, 2, border_radius=5)
                size = all_meta[map_name].get("size", [24, 18])
                screen.blit(small.render(f"{map_name}   {size[0]}×{size[1]}", True, (245, 246, 219)), (rect.x + 12, rect.y + 9))
            selected_name = map_names[selected] if map_names else "无地图"
            screen.blit(small.render(f"当前选择：{selected_name}", True, (220, 235, 210)), (32, list_rect.bottom + 20))
        screen.blit(font.render(f"箱庭尺寸：{world_w}×{world_h} 格    缩放：{int(zoom * 100)}%", True, (242, 244, 218)), (frame.x, screen.get_height() - 40))
        pygame.draw.rect(screen, (180, 210, 175), canvas, 2)
        old_clip = screen.get_clip()
        screen.set_clip(frame)
        # A light grid makes cell alignment visible even when a map has a
        # transparent layer or a large empty area.
        grid_step = 1 if view_tile >= 10 else 2
        for grid_x in range(0, world_w + 1, grid_step):
            x = canvas.x + grid_x * view_tile
            pygame.draw.line(screen, (55, 78, 68), (x, canvas.y), (x, canvas.bottom), 1)
        for grid_y in range(0, world_h + 1, grid_step):
            y = canvas.y + grid_y * view_tile
            pygame.draw.line(screen, (55, 78, 68), (canvas.x, y), (canvas.right, y), 1)
        connections = connection_manifest()["connections"]
        # Draw each placed map as a composited preview plus a colored boundary.
        for index, item in enumerate(placements):
            images = map_surfaces[item["map"]]
            composed = pygame.Surface(images[0].get_size(), pygame.SRCALPHA)
            for image in images:
                composed.blit(image, (0, 0))
            composed = rotated_surface(composed, item)
            width, height = composed.get_width() // TILE, composed.get_height() // TILE
            preview = pygame.transform.scale(composed, (width * view_tile, height * view_tile))
            x = canvas.x + int(item.get("x", 0)) * view_tile
            y = canvas.y + int(item.get("y", 0)) * view_tile
            screen.blit(preview, (x, y))
            pygame.draw.rect(screen, (255, 228, 92) if index == selected_placement else (112, 178, 150),
                             (x, y, width * view_tile, height * view_tile), 2)
            if not preview_only:
                label = small.render(f"{item['id']}  ({item.get('x', 0)},{item.get('y', 0)}) R{int(item.get('rotation', 0))}°", True, (255, 250, 190))
                screen.blit(label, (x + 4, y + 3))
        if not preview_only:
            # Draw after the map previews so exact joins remain visible.
            items_by_id = {item["id"]: item for item in placements}
            for connection in connections:
                left = items_by_id[connection["from"]]
                start = connection["world_range"]["start"] * view_tile
                end = connection["world_range"]["end"] * view_tile
                if connection["axis"] == "vertical":
                    edge_x = (int(left.get("x", 0)) + placement_size(left)[0]) * view_tile
                    pygame.draw.line(screen, (90, 235, 242),
                                     (canvas.x + edge_x, canvas.y + start),
                                     (canvas.x + edge_x, canvas.y + end), 4)
                else:
                    edge_y = (int(left.get("y", 0)) + placement_size(left)[1]) * view_tile
                    pygame.draw.line(screen, (90, 235, 242),
                                     (canvas.x + start, canvas.y + edge_y),
                                     (canvas.x + end, canvas.y + edge_y), 4)
        if selected_placement is not None and selected_placement < len(placements):
            selected_item = placements[selected_placement]
            selected_map = selected_item["map"]
            selected_connections = sum(
                selected_item["id"] in (link["from"], link["to"])
                for link in connections
            )
            info = (f"已选中：{selected_item['id']}    地图：{selected_map}    "
                    f"位置：({selected_item.get('x', 0)},{selected_item.get('y', 0)})    "
                    f"尺寸：{placement_size(selected_item)[0]}×{placement_size(selected_item)[1]}    "
                    f"旋转：{int(selected_item.get('rotation', 0))}°    "
                    f"连接：{selected_connections} 条")
            screen.blit(small.render(info, True, (255, 232, 130)), (frame.x, frame.bottom - 28))
        screen.set_clip(old_clip)
        if pygame.time.get_ticks() < notice_until:
            box = pygame.Rect(frame.x + 20, screen.get_height() - 105, min(900, frame.width - 40), 48)
            pygame.draw.rect(screen, (33, 93, 62), box, border_radius=6)
            pygame.draw.rect(screen, (142, 230, 151), box, 2, border_radius=6)
            screen.blit(small.render(notice, True, (232, 255, 218)), (box.x + 14, box.y + 14))
        pygame.display.flip()
        clock.tick(30)
    if dirty:
        save_world()


def main(name: str):
    global MAP_W, MAP_H, CANVAS, VIEW_TILE
    pygame.init()
    screen = pygame.display.set_mode(SCREEN)
    pygame.display.set_caption(f"三层地图编辑器 - {name}")
    font = make_font(18)
    small = make_font(15)
    meta_path = OUT / "outdoor_maps.json"
    all_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    old = all_meta.get(name, {})
    stored_size = old.get("size", [24, 18])
    MAP_W = max(1, min(MAX_MAP_W, int(stored_size[0])))
    MAP_H = max(1, min(MAX_MAP_H, int(stored_size[1])))

    def update_canvas():
        """Fit the editable map into the fixed preview area for large maps."""
        global CANVAS, VIEW_TILE
        VIEW_TILE = max(8, min(TILE, MAP_FRAME.width // MAP_W, MAP_FRAME.height // MAP_H))
        CANVAS = pygame.Rect(
            MAP_FRAME.x + (MAP_FRAME.width - MAP_W * VIEW_TILE) // 2,
            MAP_FRAME.y + (MAP_FRAME.height - MAP_H * VIEW_TILE) // 2,
            MAP_W * VIEW_TILE,
            MAP_H * VIEW_TILE,
        )

    update_canvas()
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
    dialog_mode = None
    new_map_input = ""
    page_input = ""
    open_map_input = ""

    def cell_at(pos):
        if not CANVAS.collidepoint(pos):
            return None
        return ((pos[0] - CANVAS.x) // VIEW_TILE, (pos[1] - CANVAS.y) // VIEW_TILE)

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
        dialog_mode = "new"
        new_map_input = ""

    def enter_open_map():
        nonlocal dialog_mode, open_map_input
        dialog_mode = "open"
        open_map_input = ""

    def open_existing_map():
        nonlocal name, layers, blocked, start, dialog_mode, open_map_input, dirty
        global MAP_W, MAP_H
        map_name = open_map_input.strip()
        if map_name not in all_meta:
            show_notice([f"找不到地图 {map_name}。可用地图：{', '.join(all_meta) or '无'}"], (255, 158, 120), 6)
            return
        if dirty:
            save()
        name = map_name
        spec = all_meta[name]
        size = spec.get("size", [24, 18])
        MAP_W = max(1, min(MAX_MAP_W, int(size[0])))
        MAP_H = max(1, min(MAX_MAP_H, int(size[1])))
        update_canvas()
        layers = [load_or_blank(OUT / f"{name}_{suffix}.png") for suffix in ("lower", "current", "upper")]
        blocked = {tuple(item) for item in spec.get("blocked", [])}
        start = tuple(spec.get("start", [0, 0]))
        dialog_mode = None
        open_map_input = ""
        pygame.display.set_caption(f"三层地图编辑器 - {name}")
        show_notice([f"已打开地图：{name}（{MAP_W}×{MAP_H}）", "可以继续编辑三层、碰撞和出生点。"], (142, 230, 151), 5)

    def enter_page_jump():
        nonlocal dialog_mode, page_input
        dialog_mode = "page"
        page_input = ""

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
        update_canvas()
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
                screen.blit(pygame.transform.scale(image, CANVAS.size), CANVAS)
            return
        for i, image in enumerate(layers):
            display_image = pygame.transform.scale(image, CANVAS.size)
            if i == layer:
                screen.blit(display_image, CANVAS)
            else:
                display_image.set_alpha(72)
                screen.blit(display_image, CANVAS)

        # Highlight every occupied tile in the active layer.  This is an
        # editor-only overlay; exported PNGs remain unchanged.
        colors = ((92, 210, 255), (255, 190, 75), (205, 145, 255))
        overlay = pygame.Surface(CANVAS.size, pygame.SRCALPHA)
        highlight = colors[layer]
        for y in range(MAP_H):
            for x in range(MAP_W):
                rect = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                if layers[layer].subsurface(rect).get_bounding_rect().width:
                    display_rect = pygame.Rect(x * VIEW_TILE, y * VIEW_TILE, VIEW_TILE, VIEW_TILE)
                    pygame.draw.rect(overlay, (*highlight, 26), display_rect)
                    pygame.draw.rect(overlay, (*highlight, 165), display_rect, 1)
        screen.blit(overlay, CANVAS)

    clock = pygame.time.Clock()
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if dialog_mode:
                    if event.key == pygame.K_ESCAPE:
                        dialog_mode = None
                        new_map_input = ""
                        page_input = ""
                        open_map_input = ""
                    elif event.key == pygame.K_RETURN:
                        if dialog_mode == "new":
                            create_new_map()
                        elif dialog_mode == "open":
                            open_existing_map()
                        else:
                            change_palette_page()
                    elif event.key == pygame.K_BACKSPACE:
                        if dialog_mode == "new":
                            new_map_input = new_map_input[:-1]
                        elif dialog_mode == "open":
                            open_map_input = open_map_input[:-1]
                        else:
                            page_input = page_input[:-1]
                    elif getattr(event, "unicode", "").isprintable():
                        if dialog_mode == "new":
                            new_map_input += event.unicode
                        elif dialog_mode == "open":
                            open_map_input += event.unicode
                        else:
                            page_input += event.unicode
                    continue
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_s:
                    save()
                elif event.key == pygame.K_m or getattr(event, "unicode", "").lower() == "m":
                    enter_select()
                elif event.key == pygame.K_n:
                    enter_new_map()
                elif event.key == pygame.K_o:
                    enter_open_map()
                elif event.key == pygame.K_g:
                    enter_page_jump()
                elif event.key == pygame.K_w:
                    if dirty:
                        save()
                    run_world_editor(screen, font, small, all_meta)
                    pygame.display.set_caption(f"三层地图编辑器 - {name}")
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
            elif event.type == pygame.MOUSEBUTTONDOWN:
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
                    if event.button == 1 and OPEN_BUTTON.collidepoint(event.pos):
                        enter_open_map()
                        continue
                    if event.button == 1 and WORLD_BUTTON.collidepoint(event.pos):
                        if dirty:
                            save()
                        run_world_editor(screen, font, small, all_meta)
                        pygame.display.set_caption(f"三层地图编辑器 - {name}")
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
                pygame.draw.rect(screen, (220, 80, 70),
                                 (CANVAS.x + x * VIEW_TILE + 2, CANVAS.y + y * VIEW_TILE + 2,
                                  max(2, VIEW_TILE - 4), max(2, VIEW_TILE - 4)), 2)
            sx, sy = start
            pygame.draw.rect(screen, (250, 220, 80),
                             (CANVAS.x + sx * VIEW_TILE + 5, CANVAS.y + sy * VIEW_TILE + 5,
                              max(2, VIEW_TILE - 10), max(2, VIEW_TILE - 10)), 2)
        pygame.draw.rect(screen, (180, 210, 175), CANVAS, 2)
        if not preview_mode and selection_cells is not None:
            selection_rect = pygame.Rect(CANVAS.x + selection_cells.x * VIEW_TILE,
                                         CANVAS.y + selection_cells.y * VIEW_TILE,
                                         selection_cells.w * VIEW_TILE,
                                         selection_cells.h * VIEW_TILE)
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
            cell_width = pw // TILE
            cell_height = ph // TILE
            px = max(0, min(MAP_W - cell_width, paste_origin[0]))
            py = max(0, min(MAP_H - cell_height, paste_origin[1]))
            preview = pygame.transform.scale(preview, (cell_width * VIEW_TILE, cell_height * VIEW_TILE))
            screen.blit(preview, (CANVAS.x + px * VIEW_TILE, CANVAS.y + py * VIEW_TILE))
            pygame.draw.rect(screen, (255, 238, 94),
                             (CANVAS.x + px * VIEW_TILE, CANVAS.y + py * VIEW_TILE,
                              cell_width * VIEW_TILE, cell_height * VIEW_TILE), 3)

        # Palette and controls.
        layer_name = '游戏预览' if preview_mode else ('地面' if layer == 0 else '当前' if layer == 1 else '上层')
        layer_color = ((92, 210, 255), (255, 190, 75), (205, 145, 255))[layer]
        screen.blit(font.render(f"地图：{name}   当前层：{layer_name}", True, (242, 244, 218) if preview_mode else layer_color), (400, 28))
        screen.blit(small.render("1/2/3 切层  4游戏预览  M框选  Ctrl+C复制  Ctrl+V粘贴  S保存  Esc退出", True, (190, 210, 190)), (400, 50))
        pygame.draw.rect(screen, (20, 30, 28), (8, 78, 368, 810), border_radius=8)
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
        screen.blit(font.render("保存地图  [S]", True, (245, 246, 219)), (SAVE_BUTTON.x + 88, SAVE_BUTTON.y + 5))
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
        pygame.draw.rect(screen, (48, 74, 64), OPEN_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (137, 171, 139), OPEN_BUTTON, 2, border_radius=5)
        screen.blit(font.render("打开地图  [O]", True, (245, 246, 219)), (OPEN_BUTTON.x + 88, OPEN_BUTTON.y + 8))
        pygame.draw.rect(screen, (48, 74, 64), WORLD_BUTTON, border_radius=5)
        pygame.draw.rect(screen, (137, 171, 139), WORLD_BUTTON, 2, border_radius=5)
        screen.blit(font.render("箱庭拼接  [W]", True, (245, 246, 219)), (WORLD_BUTTON.x + 80, WORLD_BUTTON.y + 8))
        screen.blit(small.render("框选后：Ctrl+C 复制，再点击“开始粘贴”", True, (175, 196, 175)), (24, 770))
        screen.blit(small.render("O 打开已有地图；W 编辑地图拼接布局", True, (175, 196, 175)), (24, 795))
        if dialog_mode:
            overlay = pygame.Surface(SCREEN, pygame.SRCALPHA)
            overlay.fill((8, 15, 13, 185))
            screen.blit(overlay, (0, 0))
            dialog = pygame.Rect(430, 250, 700, 190)
            pygame.draw.rect(screen, (28, 55, 45), dialog, border_radius=10)
            pygame.draw.rect(screen, (255, 228, 92), dialog, 3, border_radius=10)
            is_new_map = dialog_mode == "new"
            is_open_map = dialog_mode == "open"
            dialog_title = "新建三层地图" if is_new_map else ("打开已有地图" if is_open_map else "跳转图块页")
            dialog_hint = ("输入：地图名 宽 高（例如 forest2 20 14）" if is_new_map else
                           (f"输入地图名：{', '.join(all_meta) or '无可用地图'}" if is_open_map else f"输入页码：1 到 {page_count}"))
            dialog_value = new_map_input if is_new_map else (open_map_input if is_open_map else page_input)
            dialog_placeholder = "地图名 宽 高" if is_new_map else ("地图名" if is_open_map else "页码")
            dialog_footer = (f"Enter 创建   Esc 取消   范围：宽 1-{MAX_MAP_W}，高 1-{MAX_MAP_H}" if is_new_map else
                             ("Enter 打开   Esc 取消" if is_open_map else "Enter 跳转   Esc 取消"))
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

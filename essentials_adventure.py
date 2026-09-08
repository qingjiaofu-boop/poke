"""Essentials/Hoenn-style STC-B adventure prototype.

This is deliberately independent of RPG Maker's runtime.  Supplied map
artwork and extracted Essentials/GBA assets are used as scene backgrounds,
while game state, encounters and the STC-B input bridge are implemented here.
It is a small vertical slice intended for classroom demonstration and later
content expansion.
"""
from __future__ import annotations

import math
import json
import queue
import random
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pygame

from event_system import (
    ICON_DIR,
    PRELOAD_DIR,
    conditions_met,
    event_index,
    events_for_trigger,
    load_event_document,
)
from scripted_battle import GrotleTutorial

try:
    import serial
except ImportError:
    serial = None


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
WIDTH, HEIGHT = 480, 320
PLAY_W, PLAY_H = WIDTH, HEIGHT
WINDOW_SCALE = 2
WINDOW_SIZE = (WIDTH * WINDOW_SCALE, HEIGHT * WINDOW_SCALE)
FPS = 60
TILE_SIZE = 32
MOVE_FRAMES = 4
FIELD_ATTACK_WINDUP_FRAMES = 6
ROCK_FRAME_HOLD = 1
WARP_FADE_FRAMES = 12
DIALOGUE_CHAR_FRAMES = 2
LAYER_NAMES = ("lower", "current", "upper")

WARP_LINKS = (
    ("world", (41, 10), "grancave", (25, 10)),
    ("grancave", (25, 11), "world", (42, 10)),
    ("grancave", (13, 9), "caveB1F", (3, 12)),
    ("caveB1F", (3, 13), "grancave", (13, 8)),
    ("caveB1F", (27, 12), "caveB2f", (31, 15)),
    ("caveB2f", (32, 15), "caveB1F", (26, 12)),
    ("caveB2f", (34, 7), "caveB1F", (28, 7)),
    ("caveB1F", (29, 7), "caveB2f", (34, 6)),
    ("caveB1F", (25, 7), "grancave", (22, 2)),
    ("grancave", (23, 2), "caveB1F", (26, 7)),
    ("grancave", (4, 9), "finalcave", (7, 3)),
    ("finalcave", (7, 2), "grancave", (4, 8)),
)
WARP_BY_SOURCE = {
    (source_map, source): (target_map, target)
    for source_map, source, target_map, target in WARP_LINKS
}


@dataclass
class TileMap:
    """One map in local, top-left-origin tile coordinates."""

    name: str
    size: tuple[int, int]
    start: tuple[int, int]
    layers: dict[str, list[list[pygame.Surface]]]
    layer_surfaces: dict[str, pygame.Surface]
    blocked: set[tuple[int, int]]
    upper_tiles: set[tuple[int, int]]

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]


class SerialBridge:
    def __init__(self, port: str | None, events: queue.Queue):
        self.port = port
        self.events = events
        self.stop = threading.Event()
        self.status = "键盘演示模式"

    def start(self):
        if not self.port:
            return
        if serial is None:
            self.status = "未安装 pyserial，使用键盘演示"
            return
        try:
            link = serial.Serial(self.port, 9600, timeout=0.2)
        except Exception as exc:
            self.status = f"串口连接失败：{exc}"
            return
        self.status = f"串口已连接：{self.port}"

        def read_loop():
            sensor_kind = None
            high = None
            while not self.stop.is_set():
                raw = link.read(1)
                if not raw:
                    continue
                value = raw[0]
                if value in (0x40, 0x41):
                    sensor_kind = value - 0x40
                    high = None
                elif sensor_kind is not None:
                    if high is None:
                        high = value
                    else:
                        self.events.put(("sensor", sensor_kind, (high << 8) | value))
                        sensor_kind = None
                elif value == 0x09:
                    self.events.put(("vibration",))
                else:
                    self.events.put(("key", value))
            link.close()

        threading.Thread(target=read_loop, daemon=True).start()

    def close(self):
        self.stop.set()


class Game:
    MAP_VIEW_ORDER = ("world", "grancave", "caveB1F", "caveB2f", "finalcave")
    CAVE_MAP_NAMES = frozenset(MAP_VIEW_ORDER[1:])
    WARPS = WARP_LINKS
    MAP_VIEW_TITLES = {
        "world": "室外森林世界",
        "grancave": "矿洞入口",
        "caveB1F": "矿洞 B1F",
        "caveB2f": "矿洞 B2F",
        "finalcave": "矿洞最深处",
    }
    SCENES = {
        # Grid sizes and starts are fallbacks used only when map JSON is absent.
        "home": ("bg_map_home.png", (24, 18), (6, 13), "父亲的家"),
        "friend": ("bg_map_friend.png", (24, 18), (4, 10), "森林空地"),
        "route": ("bg_map_route1.png", (24, 18), (11, 15), "1号道路"),
        "cave1": ("resource/granite_cave/background/Pokemon_RS_Granite_Cave_1F.png", (12, 9), (6, 7), "月影山洞·入口"),
        "cave2": ("resource/granite_cave/background/Pokemon_RS_Granite_Cave_B1F.png", (12, 9), (8, 6), "月影山洞·回廊"),
        "cave3": ("resource/granite_cave/background/Pokemon_RS_Granite_Cave_B2F-1.png", (12, 9), (4, 7), "月影山洞·深处"),
    }
    # Kept near the upper-left/left clearing so the opening guidance remains
    # easy to discover (and compatible with the original classroom demo).
    NPC_POS = {"home": [1, 1], "friend": [2, 5]}
    ROCK_POS = [6, 4]

    def __init__(self, port: str | None):
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass
        self.display = pygame.display.set_mode(WINDOW_SIZE)
        self.screen = pygame.Surface((WIDTH, HEIGHT)).convert()
        pygame.display.set_caption("STC-B 坚果哑铃：流星与基拉祈")
        self.clock = pygame.time.Clock()
        self.font = self._font(13)
        self.small = self._font(10)
        self.title = self._font(16, True)
        self.battle_font = self._battle_font(18)
        self.battle_small = self._battle_font(14)
        self.events: queue.Queue = queue.Queue()
        self.serial = SerialBridge(port, self.events)
        self.serial.start()
        self.running = True
        self.scene = "home"
        self.pos = list(self.SCENES["home"][2])
        self.light: int | None = None
        self.temperature: float | None = None
        self.vibration_count = 0
        self.rock_broken = False
        self.friend_met = False
        self.father_done = False
        self.battle_won = False
        self.dialogue: list[str] = []
        self.dialogue_index = 0
        self.dialogue_source = None
        # Dialogue presentation state.  The text format stays
        # ``Speaker: message`` so existing events and tests remain compatible,
        # while the renderer can select a matching large portrait.
        self.dialogue_portraits = {}
        self.dialogue_reveal = 0
        self.dialogue_reveal_tick = 0
        self.dialogue_preload: str | None = None
        self.toast = ""
        self.toast_until = 0.0
        self.meteor_phase = 0
        self.player_hp, self.enemy_hp = 100, 100
        self.move_cursor = 0
        self.heavy_ready = False
        self.battle_lost = False
        self.battle_effect = None
        self.battle_started_at = time.monotonic()
        self.battle_message = ""
        self.battle_message_reveal = 0
        self.battle_message_tick = 0
        self.battle_notice = ""
        self.battle_notice_until = 0.0
        self.map_view: str | None = None
        self.map_view_pos = [0, 0]
        self.step = None
        self.field_attack = None
        self.warp_fade_frames = 0
        self.fade_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.facing = "down"
        self._load_assets()
        self.story_events = self._load_story_events()
        self.step_events = self._load_step_events()
        self.triggered_step_events: set[tuple[str, str]] = set()
        self.map_event_document = load_event_document()
        self.map_events = self.map_event_document["events"]
        self.map_event_index = event_index(self.map_events)
        self.completed_map_events: set[str] = set()
        self.story_flags: set[str] = set()
        self.active_map_event: dict | None = None
        self.active_map_event_step = 0
        self.map_event_origin: dict | None = None
        self.event_action: dict | None = None
        self.event_camera_focus: tuple[float, float] | None = None
        self.event_actor_positions: dict[str, tuple[float, float]] = {}
        self.hidden_event_actors: set[str] = set()
        self.event_animation_cache: dict[str, list[pygame.Surface]] = {}
        self.event_battle_active = False
        self.event_battle_return: dict | None = None
        self.scripted_battle: GrotleTutorial | None = None
        self.map_event_icon_cache: dict[str, pygame.Surface | None] = {}
        self.dialogue_preload_cache: dict[str, pygame.Surface | None] = {}
        self.pos[:] = self.scene_start("home")
        world = self.tile_maps.get("world")
        if world:
            self.map_view = "world"
            self.map_view_pos[:] = world.start
        self.trigger_game_start_event()

    @staticmethod
    def _font(size, bold=False):
        candidates = [
            Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/simhei.ttf"),
        ]
        for path in candidates:
            if path.exists():
                return pygame.font.Font(str(path), size)
        return pygame.font.Font(None, size)

    @staticmethod
    def _battle_font(size):
        candidates = [
            ASSETS / "resource" / "fonts" / "zpix.ttf",
            Path("C:/Windows/Fonts/msyh.ttf"),
            Path("C:/Windows/Fonts/simhei.ttf"),
        ]
        for path in candidates:
            if path.exists():
                return pygame.font.Font(str(path), size)
        return pygame.font.Font(None, size)

    def _load_assets(self):
        self.tile_maps: dict[str, TileMap] = {}
        self.outdoor_maps = {}
        map_index = ASSETS / "maps" / "outdoor_maps.json"
        if map_index.exists():
            try:
                raw_maps = json.loads(map_index.read_text(encoding="utf-8"))
                for map_name, spec in raw_maps.items():
                    if map_name != "world":
                        self.tile_maps[map_name] = self._load_tile_map(map_name, spec)
                self.tile_maps["world"] = self._load_world_map(raw_maps.get("world", {}))
                self.outdoor_maps = {
                    name: {
                        "layers": tile_map.layer_surfaces,
                        "tile_layers": tile_map.layers,
                        "size": tile_map.size,
                        "start": tile_map.start,
                        "blocked": tile_map.blocked,
                    }
                    for name, tile_map in self.tile_maps.items()
                }
            except (OSError, ValueError, TypeError):
                self.tile_maps = {}
                self.outdoor_maps = {}
        self.backgrounds = {}
        for scene, (name, _grid, _start, _title) in self.SCENES.items():
            path = ASSETS / name
            try:
                self.backgrounds[scene] = pygame.image.load(str(path)).convert()
            except (pygame.error, FileNotFoundError):
                self.backgrounds[scene] = None
        self.player_frames = self._load_movement_frames()
        self.attack_frames = self._load_attack_frames()
        self.rock_break_frames = self._load_rock_break_frames()
        down_frames = self.player_frames.get("down", [])
        self.player = down_frames[1] if len(down_frames) > 1 else None
        self.player = self.player or self._load("resource/map/characters/ferrothorn_user.png") or self._load("FERROTHORN_USER.png")
        self.friend = self._load("introMarill.png")
        # The father is a different Ferrothorn model from the player's
        # FERROTHORN_USER sprite.  STC.png is a four-direction, four-frame
        # character sheet; the battle front sprite is used for his portrait.
        self.father_frames = self._load_character_sheet("FERROTHORN_STC.png")
        self.father_portrait = (
            self._load("resource/battle/pokemon/front/ferrothorn.png")
            or self._load("FERROTHORN_STC.png")
        )
        self.player_portrait = self._load("FERROTHORN_USER.png")
        self.jirachi = self._load("JIRACHI.png")
        if self.player:
            if not self.player_frames and self.player.get_width() >= 32 and self.player.get_height() >= 32:
                self.player = self.player.subsurface((0, 0, 32, 32)).copy()
            self.player = pygame.transform.scale(self.player, (TILE_SIZE, TILE_SIZE))
        battle_player = self._load("resource/battle/pokemon/back/ferrothorn.png") or self.player
        self.ferro_battle = battle_player
        battle_enemy = self._load("resource/battle/pokemon/front/ferroseed.png") or self.friend
        self.enemy_battle = battle_enemy
        self.default_enemy_battle = self.enemy_battle
        grotle = self._load("resource/dialogue/pokemons/GROTLE.png")
        self.grotle_battle = grotle
        self.battle_background = self._load("resource/battle/backgrounds/field_eve_bg.png")
        self.battle_bases = {
            "player": self._load("resource/battle/backgrounds/field_eve_base0.png"),
            "foe": self._load("resource/battle/backgrounds/field_eve_base1.png"),
        }
        self.battle_ui = {
            "player_box": self._load("resource/battle/ui_gen3_2x/databox_player_2x.png"),
            "foe_box": self._load("resource/battle/ui_gen3_2x/databox_foe_2x.png"),
            "hp_green": self._load("resource/battle/ui_gen3_2x/hp_fill_green_2x.png"),
            "hp_yellow": self._load("resource/battle/ui_gen3_2x/hp_fill_yellow_2x.png"),
            "hp_red": self._load("resource/battle/ui_gen3_2x/hp_fill_red_2x.png"),
            "fight": self._load("resource/battle/ui_gen3_2x/panel_move_list_2x.png"),
            "move_info": self._load("resource/battle/ui_gen3_2x/panel_move_info_2x.png"),
            "message": self._load("resource/battle/ui_gen3_2x/panel_message_2x.png"),
            "cursor": self._load("resource/battle/ui_gen3_2x/cursor_command_2x.png"),
            "continue": self._load("resource/battle/ui_gen3_2x/cursor_continue_2x.png"),
        }
        self.battle_effect_frames = {
            "synthesis": self._load_battle_effect_frames("synthesis_heal.png"),
            "solar": self._load_battle_effect_frames("solar_beam_core.png"),
            "heavy": self._load_battle_effect_frames("heavy_slam.png"),
            "weather": self._load_battle_effect_frames("weather_ball.png"),
        }
        self.battle_sounds = {
            "synthesis": self._load_battle_sound("synthesis_heal.ogg"),
            "solar": self._load_battle_sound("impact.ogg"),
            "heavy": self._load_battle_sound("heavy_slam.ogg"),
            "weather": self._load_battle_sound("weather_ball.ogg"),
        }
        if self.jirachi:
            self.jirachi = pygame.transform.scale(self.jirachi, (72, 72))
        if self.friend:
            self.friend = pygame.transform.scale(self.friend, (32, 32))
        # Portraits use nearest-neighbour scaling to preserve the pixel-art
        # appearance.  They are intentionally cached once at startup.
        self.dialogue_portraits = {
            "父亲": self._portrait(self.father_portrait, (150, 190)),
            "大木博士": self._portrait(self.father_portrait, (150, 190)),
            "青梅": self._portrait(self.friend, (150, 150)),
            "坚果哑铃": self._portrait(self.player_portrait, (150, 150)),
            "基拉祈": self._portrait(self.jirachi, (150, 150)),
        }
        music = ASSETS / "Title.ogg"
        if music.exists():
            try:
                pygame.mixer.music.load(str(music))
                pygame.mixer.music.set_volume(0.24)
                pygame.mixer.music.play(-1)
            except pygame.error:
                pass

    def _load_tile_map(self, name, spec, size=None, start=None, blocked=None):
        width, height = size or spec.get("size", (24, 18))
        width, height = max(1, int(width)), max(1, int(height))
        raw_start = start or spec.get("start", (0, 0))
        local_start = (
            max(0, min(width - 1, int(raw_start[0]))),
            max(0, min(height - 1, int(raw_start[1]))),
        )
        local_blocked = {
            (int(cell[0]), int(cell[1]))
            for cell in (blocked if blocked is not None else spec.get("blocked", []))
            if len(cell) >= 2 and 0 <= int(cell[0]) < width and 0 <= int(cell[1]) < height
        }
        layer_surfaces = {}
        layers = {}
        for layer_name in LAYER_NAMES:
            surface = pygame.Surface((width * TILE_SIZE, height * TILE_SIZE), pygame.SRCALPHA)
            rel_path = spec.get("layers", {}).get(layer_name)
            if rel_path:
                try:
                    source = pygame.image.load(str(ASSETS / rel_path)).convert_alpha()
                    surface.blit(source, (0, 0))
                except (pygame.error, FileNotFoundError):
                    pass
            layer_surfaces[layer_name] = surface
            layers[layer_name] = [
                [
                    surface.subsurface((x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE))
                    for x in range(width)
                ]
                for y in range(height)
            ]
        upper_tiles = set()
        if name in self.CAVE_MAP_NAMES:
            upper_tiles = {
                (x, y)
                for y in range(height)
                for x in range(width)
                if layers["upper"][y][x].get_bounding_rect(min_alpha=1)
            }
        return TileMap(
            name, (width, height), local_start, layers,
            layer_surfaces, local_blocked, upper_tiles,
        )

    def _load_world_map(self, world_spec):
        connection_path = ASSETS / "maps" / "world_connections.json"
        connections = json.loads(connection_path.read_text(encoding="utf-8"))
        world_size = tuple(connections.get("world_size", (120, 120)))
        width, height = int(world_size[0]), int(world_size[1])
        covered = set()
        blocked = set()
        start = (0, 0)

        for placement in connections.get("maps", []):
            source = self.tile_maps.get(placement.get("map"))
            if source is None or int(placement.get("rotation", 0)) != 0:
                continue
            origin = placement.get("position", {})
            ox, oy = int(origin.get("x", 0)), int(origin.get("y", 0))
            for y in range(source.height):
                for x in range(source.width):
                    wx, wy = ox + x, oy + y
                    if 0 <= wx < width and 0 <= wy < height:
                        covered.add((wx, wy))
                        # Placements are painted in manifest order. A later map
                        # replaces both the visible tile and collision state.
                        blocked.discard((wx, wy))
            blocked.update(
                (ox + x, oy + y)
                for x, y in source.blocked
                if 0 <= ox + x < width and 0 <= oy + y < height
            )
            if source.name == "home":
                start = (ox + source.start[0], oy + source.start[1])

        blocked.update(
            (x, y)
            for y in range(height)
            for x in range(width)
            if (x, y) not in covered
        )
        if start in blocked:
            start = next(((x, y) for y in range(height) for x in range(width)
                          if (x, y) not in blocked), (0, 0))

        layers = world_spec.get("layers") or {
            layer_name: f"maps/world_{layer_name}.png" for layer_name in LAYER_NAMES
        }
        return self._load_tile_map(
            "world", {"layers": layers}, (width, height), start, blocked
        )

    def _load_movement_frames(self):
        path = ASSETS / "movements.png"
        if not path.exists():
            return {}
        try:
            sheet = pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            return {}

        columns = (177, 216, 255)
        rows = {"down": (31, 27), "left": (85, 27), "up": (141, 28)}

        frames = {
            direction: [self._character_frame(sheet, (x, y, 40, height)) for x in columns]
            for direction, (y, height) in rows.items()
        }
        frames["right"] = [pygame.transform.flip(frame, True, False)
                           for frame in frames["left"]]
        return frames

    def _load_character_sheet(self, name):
        """Load a 4-column, 4-row 32px character sheet.

        The sheet is intentionally separate from the player's animation so an
        NPC can have its own collision tile and facing direction.
        """
        sheet = self._load(name)
        if sheet is None or sheet.get_width() < TILE_SIZE * 4 or sheet.get_height() < TILE_SIZE * 3:
            return {}
        rows = {"down": 0, "left": 1, "up": 2}
        frames = {
            direction: [
                sheet.subsurface((column * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE)).copy()
                for column in range(4)
            ]
            for direction, row in rows.items()
        }
        frames["right"] = [pygame.transform.flip(frame, True, False) for frame in frames["left"]]
        return frames

    def _load_attack_frames(self):
        path = ASSETS / "movements.png"
        if not path.exists():
            return {}
        try:
            sheet = pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            return {}

        crops = {
            "down": ((355, 39, 29, 24), (315, 139, 33, 19), (317, 170, 31, 20)),
            "up": ((314, 80, 33, 20), (356, 75, 27, 25), (315, 108, 32, 21)),
            "right": ((359, 110, 36, 19), (356, 140, 35, 18), (356, 170, 36, 25)),
        }
        frames = {
            direction: [self._character_frame(sheet, rect) for rect in rects]
            for direction, rects in crops.items()
        }
        frames["left"] = [pygame.transform.flip(frame, True, False)
                          for frame in frames["right"]]
        return frames

    @staticmethod
    def _character_frame(sheet, rect):
        source = sheet.subsurface(rect).copy()
        for py in range(source.get_height()):
            for px in range(source.get_width()):
                color = source.get_at((px, py))
                if all(abs(int(color[channel]) - 239) <= 16 for channel in range(3)):
                    source.set_at((px, py), (0, 0, 0, 0))
        bounds = source.get_bounding_rect()
        frame = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        if bounds.width and bounds.height:
            sprite = source.subsurface(bounds).copy()
            scale = min(TILE_SIZE / bounds.width, TILE_SIZE / bounds.height)
            size = (max(1, round(bounds.width * scale)),
                    max(1, round(bounds.height * scale)))
            sprite = pygame.transform.scale(sprite, size)
            frame.blit(sprite, ((TILE_SIZE - size[0]) // 2, TILE_SIZE - size[1]))
        return frame

    @staticmethod
    def _load_rock_break_frames():
        path = ASSETS / "resource" / "map" / "objects" / "rock_break_sequence.png"
        try:
            sheet = pygame.image.load(str(path)).convert_alpha()
        except (pygame.error, FileNotFoundError):
            return []
        if sheet.get_width() < TILE_SIZE or sheet.get_height() < TILE_SIZE:
            return []
        return [
            sheet.subsurface((x, y, TILE_SIZE, TILE_SIZE)).copy()
            for y in range(0, sheet.get_height() - TILE_SIZE + 1, TILE_SIZE)
            for x in range(0, sheet.get_width() - TILE_SIZE + 1, TILE_SIZE)
        ]

    @staticmethod
    def _load(name):
        for path in (ASSETS / name, ASSETS / "resource" / name):
            try:
                return pygame.image.load(str(path)).convert_alpha()
            except (pygame.error, FileNotFoundError):
                continue
        return None

    @staticmethod
    def _portrait(image, size):
        """Scale a portrait to fit a dialogue card without stretching it."""
        if image is None:
            return None
        iw, ih = image.get_size()
        scale = min(size[0] / max(1, iw), size[1] / max(1, ih))
        scaled = pygame.transform.scale(
            image, (max(1, round(iw * scale)), max(1, round(ih * scale)))
        )
        card = pygame.Surface(size, pygame.SRCALPHA)
        card.blit(scaled, scaled.get_rect(midbottom=(size[0] // 2, size[1])))
        return card

    def _load_battle_effect_frames(self, name):
        """Load the first animation row from an Essentials effect sheet.

        The supplied effects use 192px cells.  The first row contains a
        compact, complete animation for each of the four classroom moves,
        which is enough for this small turn-based prototype without importing
        RPG Maker's animation runtime.
        """
        sheet = self._load(f"resource/battle/effects/{name}")
        if sheet is None:
            return []
        cell = 192
        count = sheet.get_width() // cell
        if count == 0 or sheet.get_height() < cell:
            return []
        frames = []
        for column in range(count):
            frame = sheet.subsurface((column * cell, 0, cell, cell)).copy()
            if frame.get_bounding_rect().width:
                frames.append(frame)
        return frames

    @staticmethod
    def _load_battle_sound(name):
        """Return an optional move sound; the game remains playable silently."""
        path = ASSETS / "resource" / "audio" / "se" / "moves" / name
        if not path.exists() or not pygame.mixer.get_init():
            return None
        try:
            return pygame.mixer.Sound(str(path))
        except pygame.error:
            return None

    @staticmethod
    def _load_story_events():
        """Load editable event dialogue, retaining a built-in fallback."""
        defaults = {
            "father": [
                "父亲：坚果哑铃，刚才的流星你也看见了吧？",
                "父亲：去左边的森林空地找你的青梅竹马。",
                "父亲：她也许知道流星落在哪里。",
            ],
            "friend": [
                "青梅：你也在追那颗流星？我们先练习一下招式吧。",
                "青梅：光照越强，日光束越强；光合作用也能恢复更多体力。",
                "青梅：温度还会改变气象球的属性。准备好就出发！",
            ],
        }
        path = ASSETS / "story_events.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for key in defaults:
                entries = raw.get(key)
                if isinstance(entries, list) and entries:
                    parsed = []
                    for item in entries:
                        if isinstance(item, str) and item.strip():
                            parsed.append(item.strip())
                        elif isinstance(item, dict) and item.get("text"):
                            speaker = str(item.get("speaker", "")).strip()
                            text = str(item["text"]).strip()
                            parsed.append(f"{speaker}：{text}" if speaker else text)
                    if parsed:
                        defaults[key] = parsed
        except (OSError, ValueError, TypeError):
            pass
        return defaults

    @staticmethod
    def _load_step_events():
        """Read optional tile-triggered events from assets/step_events.json."""
        path = ASSETS / "step_events.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        events = {}
        for scene, entries in raw.items() if isinstance(raw, dict) else ():
            if not isinstance(entries, dict):
                continue
            for coordinate, value in entries.items():
                try:
                    x, y = (int(part.strip()) for part in str(coordinate).split(",", 1))
                except (TypeError, ValueError):
                    continue
                lines = value if isinstance(value, list) else [value]
                parsed = []
                for item in lines:
                    if isinstance(item, str) and item.strip():
                        parsed.append(item.strip())
                    elif isinstance(item, dict) and item.get("text"):
                        speaker = str(item.get("speaker", "")).strip()
                        text = str(item["text"]).strip()
                        parsed.append(f"{speaker}：{text}" if speaker else text)
                if parsed:
                    events[(str(scene), (x, y))] = parsed
        return events

    def run(self):
        while self.running:
            self.clock.tick(FPS)
            self.handle_events()
            self.read_serial()
            self.update_movement()
            self.update_field_attack()
            self.update_warp_fade()
            self.update_event_action()
            self.update_battle_effect()
            self.update_battle_message_reveal()
            self.update_dialogue_reveal()
            self.draw()
        self.serial.close()
        pygame.quit()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif self.step or self.field_attack or self.warp_fade_frames or self.event_action:
                    continue
                elif event.key == pygame.K_r:
                    self.reset()
                elif self.dialogue:
                    if event.key == pygame.K_RETURN:
                        self.command(5)
                    continue
                elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5,
                                    pygame.K_KP1, pygame.K_KP2, pygame.K_KP3, pygame.K_KP4, pygame.K_KP5) \
                        and self.scene != "battle" and self.active_map_event is None:
                    number_keys = {
                        pygame.K_1: 0, pygame.K_KP1: 0,
                        pygame.K_2: 1, pygame.K_KP2: 1,
                        pygame.K_3: 2, pygame.K_KP3: 2,
                        pygame.K_4: 3, pygame.K_KP4: 3,
                        pygame.K_5: 4, pygame.K_KP5: 4,
                    }
                    self.switch_map_view(number_keys[event.key])
                elif event.key == pygame.K_v:
                    self.vibration_count += 1
                    self.vibration()
                elif event.key == pygame.K_z:
                    self.use_field_heavy_slam()
                elif event.key == pygame.K_F1:
                    if self.map_view:
                        self.map_view = None
                        self.show_toast("已返回剧情场景。", 1.5)
                    else:
                        self.cycle_scene()
                elif event.key == pygame.K_F2:
                    self.show_toast("F2：STC-B 传感器联动状态", 2)
                else:
                    keys = {pygame.K_UP: 1, pygame.K_DOWN: 2, pygame.K_LEFT: 3,
                            pygame.K_RIGHT: 4, pygame.K_RETURN: 5}
                    if event.key in keys:
                        self.command(keys[event.key])

    def read_serial(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            if event[0] == "sensor":
                if event[1] == 0:
                    self.light = event[2]
                else:
                    self.temperature = self.adc_temperature(event[2])
            elif event[0] == "vibration":
                if self.step or self.field_attack or self.warp_fade_frames or self.event_action:
                    continue
                self.vibration_count += 1
                self.vibration()
            else:
                self.command(event[1])

    @staticmethod
    def adc_temperature(adc):
        adc = max(1, min(1022, adc))
        resistance = 10000.0 * adc / (1023.0 - adc)
        return 1.0 / (1.0 / 298.15 + math.log(resistance / 10000.0) / 3950.0) - 273.15

    def command(self, command):
        if self.step or self.field_attack or self.warp_fade_frames or self.event_action:
            return
        if command == 6:
            self.reset()
            return
        if self.dialogue:
            if command == 5:
                text = self.dialogue[self.dialogue_index]
                _speaker, message = self._split_dialogue(text)
                if self.dialogue_reveal < len(message):
                    self.dialogue_reveal = len(message)
                else:
                    self.advance_dialogue()
            elif command == 7 and self.active_map_event is None:
                self.dialogue = []
                self.dialogue_source = None
                self.dialogue_preload = None
            return
        if command == 7:
            self.show_toast("K2：取消当前对白/操作", 1.5)
            return
        if command == 8:
            self.cycle_scene()
            return
        if command == 9:
            self.vibration_count += 1
            self.vibration()
            return
        if self.scene == "battle":
            self.battle_command(command)
            return
        if self.map_view:
            if command in (1, 2, 3, 4):
                self.move_map_view(command)
            return
        if command in (1, 2, 3, 4):
            self.move(command)
        elif command == 5:
            self.interact()

    def move(self, command):
        tile_map = self.tile_maps.get(self.scene)
        grid = tile_map.size if tile_map else self.SCENES[self.scene][1]
        self.facing = {1: "up", 2: "down", 3: "left", 4: "right"}[command]
        dxdy = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}[command]
        nx, ny = self.pos[0] + dxdy[0], self.pos[1] + dxdy[1]
        if not (0 <= nx < grid[0] and 0 <= ny < grid[1]):
            self.transition_from_edge(command)
            return
        if self.scene == "cave3" and not self.rock_broken and [nx, ny] == self.ROCK_POS:
            self.show_toast("岩石挡住了去路。请靠近后晃动 STC-B。", 2.5)
            return
        if self.is_npc_tile(self.scene, (nx, ny)):
            target = "父亲" if self.scene == "home" else "青梅"
            self.show_toast(f"{target}挡住了去路。贴近后面对他按 Enter。", 1.8)
            return
        if tile_map and (nx, ny) in tile_map.blocked:
            self.show_toast("这里有花丛或装饰物，换个方向试试。", 1.0)
            return
        self._begin_step(self.pos, (nx, ny), command)

    def scene_start(self, scene):
        tile_map = self.tile_maps.get(scene)
        return list(tile_map.start if tile_map else self.SCENES[scene][2])

    def switch_map_view(self, index):
        map_name = self.MAP_VIEW_ORDER[index]
        tile_map = self.tile_maps.get(map_name)
        if tile_map is None:
            self.show_toast(f"地图未加载：{map_name}", 2)
            return
        self.map_view = map_name
        self.map_view_pos[:] = tile_map.start
        self.step = None
        self.field_attack = None
        self.warp_fade_frames = 0
        self.facing = "down"
        self.dialogue = []
        self.show_toast(f"地图 {index + 1}：{self.MAP_VIEW_TITLES[map_name]}", 1.8)

    def move_map_view(self, command):
        tile_map = self.tile_maps[self.map_view]
        self.facing = {1: "up", 2: "down", 3: "left", 4: "right"}[command]
        dx, dy = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}[command]
        nx, ny = self.map_view_pos[0] + dx, self.map_view_pos[1] + dy
        if not (0 <= nx < tile_map.width and 0 <= ny < tile_map.height):
            self.show_toast("已到达地图边界。", 1)
            return
        if (nx, ny) in tile_map.blocked:
            self.show_toast("该格不可通行。", 1)
            return
        self._begin_step(self.map_view_pos, (nx, ny), command)

    @staticmethod
    def upper_tile_exists(tile_map, point):
        x, y = point
        if not (0 <= x < tile_map.width and 0 <= y < tile_map.height):
            return False
        return point in tile_map.upper_tiles

    def is_breakable_rock(self, tile_map, point):
        return (tile_map.name in self.CAVE_MAP_NAMES
                and point in tile_map.blocked
                and self.upper_tile_exists(tile_map, point))

    def use_field_heavy_slam(self):
        if self.step or self.field_attack or self.map_view not in self.CAVE_MAP_NAMES:
            return False
        tile_map = self.tile_maps[self.map_view]
        dx, dy = {
            "up": (0, -1), "down": (0, 1),
            "left": (-1, 0), "right": (1, 0),
        }[self.facing]
        target = (self.map_view_pos[0] + dx, self.map_view_pos[1] + dy)
        if not self.is_breakable_rock(tile_map, target):
            return False
        self.field_attack = {
            "context": self._movement_context(),
            "tile_map": tile_map,
            "target": target,
            "frame": 0,
            "broken": False,
        }
        return True

    def update_field_attack(self):
        attack = self.field_attack
        if not attack:
            return
        if attack["context"] != self._movement_context():
            self.field_attack = None
            return
        attack["frame"] += 1
        if not attack["broken"] and attack["frame"] >= FIELD_ATTACK_WINDUP_FRAMES:
            x, y = attack["target"]
            tile_map = attack["tile_map"]
            tile_map.layer_surfaces["upper"].fill(
                (0, 0, 0, 0),
                pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE),
            )
            tile_map.layers["upper"][y][x] = pygame.Surface(
                (TILE_SIZE, TILE_SIZE), pygame.SRCALPHA
            )
            tile_map.upper_tiles.discard((x, y))
            tile_map.blocked.discard((x, y))
            attack["broken"] = True
        effect_frames = max(1, len(self.rock_break_frames)) * ROCK_FRAME_HOLD
        if attack["frame"] >= FIELD_ATTACK_WINDUP_FRAMES + effect_frames:
            self.field_attack = None

    def trigger_warp(self):
        if not self.map_view:
            return False
        destination = WARP_BY_SOURCE.get((self.map_view, tuple(self.map_view_pos)))
        if destination is None:
            return False
        if self.trigger_event_at("warp_attempt"):
            return True
        target_map_name, target = destination
        target_map = self.tile_maps.get(target_map_name)
        if target_map is None or target in target_map.blocked:
            return False
        self.map_view = target_map_name
        self.map_view_pos[:] = target
        self.step = None
        self.field_attack = None
        self.warp_fade_frames = WARP_FADE_FRAMES
        if hasattr(self, "_map_camera"):
            del self._map_camera
        return True

    def update_warp_fade(self):
        if self.warp_fade_frames:
            self.warp_fade_frames -= 1

    def _movement_context(self):
        return ("view", self.map_view) if self.map_view else ("scene", self.scene)

    def _begin_step(self, position, target, command):
        self.facing = {1: "up", 2: "down", 3: "left", 4: "right"}[command]
        self.step = {
            "context": self._movement_context(),
            "position": position,
            "from": tuple(position),
            "to": tuple(target),
            "frame": 0,
        }

    def update_movement(self):
        if not self.step:
            return
        if self.step["context"] != self._movement_context():
            self.step = None
            return
        self.step["frame"] += 1
        if self.step["frame"] >= MOVE_FRAMES:
            self.step["position"][:] = self.step["to"]
            self.step = None
            warp_handled = self.trigger_warp()
            if not warp_handled and not self.trigger_map_event():
                self.trigger_step_event()

    def is_npc_tile(self, scene, point):
        """NPCs occupy a solid tile in normal scenes, like RPG Maker events."""
        return scene in self.NPC_POS and tuple(point) == tuple(self.NPC_POS[scene])

    def is_facing_point(self, point):
        dx = point[0] - self.pos[0]
        dy = point[1] - self.pos[1]
        return ((self.facing == "up" and (dx, dy) == (0, -1)) or
                (self.facing == "down" and (dx, dy) == (0, 1)) or
                (self.facing == "left" and (dx, dy) == (-1, 0)) or
                (self.facing == "right" and (dx, dy) == (1, 0)))

    def trigger_step_event(self):
        """Fire a one-shot event after the player finishes entering a tile."""
        key = (self.scene, tuple(self.pos))
        lines = self.step_events.get(key)
        if not lines or key in self.triggered_step_events or self.scene == "battle":
            return
        self.triggered_step_events.add(key)
        self.dialogue = list(lines)
        self.dialogue_index = 0
        self.dialogue_source = "step"
        self.dialogue_preload = None
        self.dialogue_reveal = 0
        self.dialogue_reveal_tick = 0

    def trigger_game_start_event(self):
        """Start the first eligible opening event after the initial map is ready."""
        map_name = self.map_view or self.scene
        candidates = events_for_trigger(
            self.map_events, "game_start", map_name=map_name, flags=self.story_flags
        )
        for event in candidates:
            if not (event.get("once", True) and event["id"] in self.completed_map_events):
                self.start_map_event(event)
                return True
        return False

    def trigger_event_at(self, trigger):
        """Start an eligible event for the player's current map coordinate."""
        map_name = self.map_view or self.scene
        position = tuple(self.map_view_pos if self.map_view else self.pos)
        if self.active_map_event is not None:
            return False
        candidates = events_for_trigger(
            self.map_events,
            trigger,
            map_name=map_name,
            position=position,
            flags=self.story_flags,
        )
        for event in candidates:
            if event.get("once", True) and event["id"] in self.completed_map_events:
                continue
            self.start_map_event(event)
            return True
        return False

    def trigger_map_event(self):
        """Start the ordered step event placed on the entered tile."""
        return self.trigger_event_at("step")

    def start_map_event(self, event):
        self.active_map_event = event
        self.active_map_event_step = 0
        self.map_event_origin = {
            "map_view": self.map_view,
            "scene": self.scene,
            "map_position": tuple(self.map_view_pos),
            "scene_position": tuple(self.pos),
            "facing": self.facing,
            "story_flags": set(self.story_flags),
            "actor_positions": dict(self.event_actor_positions),
            "hidden_actors": set(self.hidden_event_actors),
        }
        self.event_battle_active = False
        self.event_battle_return = None
        self.run_map_event_step()

    def run_map_event_step(self):
        """Execute steps until one needs player input, or finish the event."""
        while self.active_map_event is not None:
            event = self.active_map_event
            steps = event.get("steps", [])
            if self.active_map_event_step >= len(steps):
                self.finish_map_event()
                return

            step = steps[self.active_map_event_step]
            step_type = step.get("type", "dialogue")
            if step_type == "battle":
                self.start_event_battle(step.get("battle_id", "placeholder"))
                return
            if step_type == "dialogue":
                speaker = str(step.get("speaker", "")).strip()
                message = str(step.get("text", ""))
                self.dialogue = [f"{speaker}：{message}" if speaker else message]
                self.dialogue_index = 0
                self.dialogue_source = "map_event"
                self.dialogue_preload = str(step.get("preload", "no_portrait_bottom.png"))
                self.dialogue_reveal = 0
                self.dialogue_reveal_tick = 0
                return
            if step_type == "set_flag":
                flag = str(step.get("flag", "")).strip()
                if flag:
                    if step.get("value", True):
                        self.story_flags.add(flag)
                    else:
                        self.story_flags.discard(flag)
                self.active_map_event_step += 1
                continue
            if step_type == "actor_visibility":
                actor = self.resolve_event_actor(step.get("actor", "event"))
                if step.get("visible", True):
                    self.hidden_event_actors.discard(actor)
                else:
                    self.hidden_event_actors.add(actor)
                self.active_map_event_step += 1
                continue
            self.begin_event_action(step)
            return

    def finish_map_event(self):
        event = self.active_map_event
        if event and event.get("once", True):
            self.completed_map_events.add(event["id"])
        self.active_map_event = None
        self.active_map_event_step = 0
        self.map_event_origin = None
        self.event_battle_active = False
        self.event_battle_return = None
        self.event_action = None
        self.event_camera_focus = None
        self.dialogue = []
        self.dialogue_source = None
        self.dialogue_preload = None
        self.battle_won = False
        self.battle_lost = False
        self.battle_effect = None
        self.scripted_battle = None

    def resolve_event_actor(self, actor):
        actor = str(actor or "event")
        if actor == "event" and self.active_map_event:
            return self.active_map_event["id"]
        return actor

    def begin_event_action(self, step):
        """Start a non-blocking timeline step; update_event_action advances it."""
        kind = step.get("type")
        duration_ms = max(0, int(step.get("duration_ms", 0)))
        total = max(1, round(duration_ms * FPS / 1000))
        action = {"type": kind, "frame": 0, "total": total, "step": step}
        player = tuple(self.map_view_pos if self.map_view else self.pos)
        if kind == "toast":
            self.show_toast(str(step.get("text", "")), duration_ms / 1000)
        elif kind == "camera_pan":
            action["from"] = self.event_camera_focus or player
            action["to"] = player if step.get("target") == "player" else tuple(step.get("position", player))
        elif kind == "actor_move":
            actor = self.resolve_event_actor(step.get("actor", "event"))
            action["actor"] = actor
            if actor == "player":
                action["from"] = player
            else:
                action["from"] = self.event_actor_positions.get(
                    actor, tuple(self.active_map_event.get("position", player))
                )
            action["to"] = tuple(step.get("position", action["from"]))
        self.event_action = action

    def update_event_action(self):
        action = self.event_action
        if not action:
            return
        action["frame"] += 1
        progress = min(1.0, action["frame"] / action["total"])
        if action["type"] == "camera_pan":
            start, target = action["from"], action["to"]
            eased = progress * progress * (3 - 2 * progress)
            self.event_camera_focus = (
                start[0] + (target[0] - start[0]) * eased,
                start[1] + (target[1] - start[1]) * eased,
            )
        elif action["type"] == "actor_move":
            start, target = action["from"], action["to"]
            current = (
                start[0] + (target[0] - start[0]) * progress,
                start[1] + (target[1] - start[1]) * progress,
            )
            if action["actor"] != "player":
                self.event_actor_positions[action["actor"]] = current
        if progress < 1.0:
            return
        step = action["step"]
        if action["type"] == "camera_pan" and step.get("target") == "player":
            self.event_camera_focus = None
        elif action["type"] == "actor_move" and action["actor"] == "player":
            destination = [round(value) for value in action["to"]]
            if self.map_view:
                self.map_view_pos[:] = destination
            else:
                self.pos[:] = destination
        self.event_action = None
        if self.active_map_event is not None:
            self.active_map_event_step += 1
            self.run_map_event_step()

    def advance_dialogue(self):
        """Advance legacy dialogue or return control to the ordered event."""
        if self.dialogue_index + 1 < len(self.dialogue):
            self.dialogue_index += 1
            self.dialogue_reveal = 0
            self.dialogue_reveal_tick = 0
            return
        source = self.dialogue_source
        self.dialogue = []
        self.dialogue_index = 0
        self.dialogue_source = None
        self.dialogue_preload = None
        self.dialogue_reveal = 0
        self.dialogue_reveal_tick = 0
        if source == "map_event" and self.active_map_event is not None:
            self.active_map_event_step += 1
            self.run_map_event_step()
        else:
            self.after_dialogue()

    def update_dialogue_reveal(self):
        if not self.dialogue:
            return
        text = self.dialogue[self.dialogue_index]
        _speaker, message = self._split_dialogue(text)
        if self.dialogue_reveal >= len(message):
            return
        self.dialogue_reveal_tick += 1
        if self.dialogue_reveal_tick >= DIALOGUE_CHAR_FRAMES:
            self.dialogue_reveal += 1
            self.dialogue_reveal_tick = 0

    def actor_grid_position(self, position):
        action = self.event_action
        if action and action.get("type") == "actor_move" and action.get("actor") == "player":
            progress = min(1.0, action["frame"] / action["total"])
            start_x, start_y = action["from"]
            target_x, target_y = action["to"]
            return (start_x + (target_x - start_x) * progress,
                    start_y + (target_y - start_y) * progress)
        if not self.step or self.step["context"] != self._movement_context():
            return float(position[0]), float(position[1])
        progress = self.step["frame"] / MOVE_FRAMES
        start_x, start_y = self.step["from"]
        target_x, target_y = self.step["to"]
        return (start_x + (target_x - start_x) * progress,
                start_y + (target_y - start_y) * progress)

    def transition_from_edge(self, command):
        next_scene = None
        if self.scene == "home" and command == 3 and self.father_done:
            next_scene = "friend"
        elif self.scene == "friend" and command == 4 and self.friend_met:
            next_scene = "route"
        elif self.scene == "route" and command == 1:
            next_scene = "cave1"
        elif self.scene == "cave1" and command == 1:
            next_scene = "cave2"
        elif self.scene == "cave2" and command == 1:
            next_scene = "cave3"
        elif self.scene == "cave3" and command == 1 and self.rock_broken:
            next_scene = "ending"
        if next_scene:
            self.step = None
            self.scene = next_scene
            if next_scene in self.SCENES:
                self.pos[:] = self.scene_start(next_scene)
            if next_scene == "route":
                self.meteor_phase = 1
                self.show_toast("一道流星划过天空，坠向北方的山洞。", 3)
            elif next_scene == "cave1":
                self.show_toast("洞口没有任何落石痕迹……声音从深处传来。", 3)
            elif next_scene == "cave3":
                self.show_toast("矿洞最深处，岩石封住了最后的通道。", 3)

    def interact(self):
        if self.scene in self.NPC_POS and (
                not self.adjacent(self.pos, self.NPC_POS[self.scene]) or
                not self.is_facing_point(self.NPC_POS[self.scene])):
            target = "父亲" if self.scene == "home" else "青梅"
            self.show_toast(f"请贴着{target}并面对他，再按中心键。", 1.8)
            return
        if self.scene == "home" and not self.father_done:
            self.dialogue = list(self.story_events["father"])
            self.dialogue_index = 0
            self.dialogue_source = "father"
            self.dialogue_preload = None
            self.dialogue_reveal = 0
            self.dialogue_reveal_tick = 0
            self.father_done = True
        elif self.scene == "friend" and not self.friend_met:
            self.dialogue = list(self.story_events["friend"])
            self.dialogue_index = 0
            self.dialogue_source = "friend"
            self.dialogue_preload = None
            self.dialogue_reveal = 0
            self.dialogue_reveal_tick = 0
            self.friend_met = True
        elif self.scene == "friend" and self.friend_met and not self.battle_won:
            self.start_battle()
        elif self.scene == "route" and self.meteor_phase == 1:
            self.meteor_phase = 2
            self.show_toast("青梅：流星就在山洞方向，我们一起去看看！", 3)
        elif self.scene == "cave3" and self.rock_broken:
            self.scene = "ending"
        elif self.scene == "ending":
            self.reset()

    def after_dialogue(self):
        if self.scene == "friend" and self.friend_met and not self.battle_won:
            self.start_battle()

    def start_battle(self):
        self.step = None
        self.field_attack = None
        self.warp_fade_frames = 0
        self.scene = "battle"
        self.player_hp, self.enemy_hp = 100, 100
        self.move_cursor = 0
        self.heavy_ready = False
        self.battle_won = False
        self.battle_lost = False
        self.battle_effect = None
        self.battle_started_at = time.monotonic()
        self.battle_message = ""
        self.battle_message_reveal = 0
        self.battle_message_tick = 0
        self.scripted_battle = None
        self.enemy_battle = self.default_enemy_battle
        self.set_battle_notice("青梅派出了种子铁球！", 2.4)

    def start_event_battle(self, battle_id):
        """Start either a configured story battle or the legacy placeholder."""
        self.event_battle_return = {
            "map_view": self.map_view,
            "scene": self.scene,
            "map_position": tuple(self.map_view_pos),
            "scene_position": tuple(self.pos),
            "facing": self.facing,
        }
        self.event_battle_active = True
        self.dialogue = []
        self.dialogue_source = None
        self.dialogue_preload = None
        self.map_view = None
        self.start_battle()
        self.event_battle_active = True
        if battle_id == "grotle_tutorial":
            self.scripted_battle = GrotleTutorial()
            self.player_hp = self.scripted_battle.player_hp
            self.enemy_hp = self.scripted_battle.foe_hp
            self.enemy_battle = self.grotle_battle or self.default_enemy_battle
            self.battle_notice = ""
            self.battle_notice_until = 0.0
            self.sync_scripted_battle_message(force=True)
        else:
            self.set_battle_notice(f"事件战斗 [{battle_id}]：当前使用训练战占位。", 2.4)

    def restore_map_event_origin(self):
        origin = self.map_event_origin
        if origin is None:
            return
        self.scene = origin["scene"]
        self.map_view = origin["map_view"]
        self.map_view_pos[:] = origin["map_position"]
        self.pos[:] = origin["scene_position"]
        self.facing = origin["facing"]
        self.story_flags = set(origin.get("story_flags", self.story_flags))
        self.event_actor_positions = dict(origin.get("actor_positions", self.event_actor_positions))
        self.hidden_event_actors = set(origin.get("hidden_actors", self.hidden_event_actors))
        self.event_camera_focus = None
        self.event_action = None
        self.step = None
        self.field_attack = None
        self.warp_fade_frames = 0
        if hasattr(self, "_map_camera"):
            del self._map_camera

    def finish_event_battle(self):
        self.event_battle_active = False
        self.battle_lost = False
        self.battle_effect = None
        self.scripted_battle = None
        self.restore_event_battle_return()
        self.active_map_event_step += 1
        self.run_map_event_step()

    def restore_event_battle_return(self):
        state = self.event_battle_return or self.map_event_origin
        if state is None:
            return
        self.scene = state["scene"]
        self.map_view = state["map_view"]
        self.map_view_pos[:] = state["map_position"]
        self.pos[:] = state["scene_position"]
        self.facing = state["facing"]
        self.event_battle_return = None
        self.event_camera_focus = None

    def restart_map_event_after_defeat(self):
        self.restore_map_event_origin()
        self.event_battle_active = False
        self.battle_won = False
        self.battle_lost = False
        self.battle_effect = None
        self.scripted_battle = None
        self.event_battle_return = None
        self.active_map_event_step = 0
        self.run_map_event_step()

    def battle_command(self, command):
        if self.battle_effect:
            return
        if self.scripted_battle:
            self.scripted_battle_command(command)
            return
        if self.battle_won:
            if command == 5:
                if self.event_battle_active:
                    self.finish_event_battle()
                else:
                    self.step = None
                    self.scene = "route"
                    self.pos[:] = self.scene_start("route")
                    self.meteor_phase = 1
                    self.show_toast("训练结束。青梅：流星坠向北方的山洞！", 3)
            return
        if self.battle_lost:
            if command == 5:
                if self.event_battle_active:
                    self.restart_map_event_after_defeat()
                else:
                    self.start_battle()
            return
        if command in (3, 4):
            self.move_cursor = (self.move_cursor + (1 if command == 4 else -1)) % 4
        elif command in (1, 2):
            self.move_cursor = (self.move_cursor + (1 if command == 2 else -1)) % 4
        elif command == 5:
            self.use_move(self.move_cursor)

    def scripted_battle_command(self, command):
        battle = self.scripted_battle
        if battle is None:
            return
        if battle.outcome == "won":
            if command == 5:
                self.finish_event_battle()
            return
        if battle.outcome == "lost":
            if command == 5:
                self.restart_map_event_after_defeat()
            return
        action = None
        hp_before = (battle.player_hp, battle.foe_hp)
        if battle.mode == "message":
            if command == 5:
                self.sync_scripted_battle_message()
                _speaker, message = self._split_dialogue(self.battle_message)
                if self.battle_message_reveal < len(message):
                    self.battle_message_reveal = len(message)
                    return
                action = battle.confirm()
        elif battle.mode == "moves":
            moves = battle.available_moves
            if command in (1, 3):
                self.move_cursor = (self.move_cursor - 1) % len(moves)
            elif command in (2, 4):
                self.move_cursor = (self.move_cursor + 1) % len(moves)
            elif command == 5:
                action = battle.choose_move(moves[self.move_cursor % len(moves)], self.light)
        if action:
            if action.target == "player":
                transition = ("player", hp_before[0], battle.player_hp)
            else:
                transition = ("foe", hp_before[1], battle.foe_hp)
            self.begin_battle_effect(action.effect, action.message, action.target, transition)
        else:
            self.player_hp = battle.player_hp
            self.enemy_hp = battle.foe_hp
            self.sync_scripted_battle_message()

    def sync_scripted_battle_message(self, force=False):
        if not self.scripted_battle:
            return
        message = self.scripted_battle.message if self.scripted_battle.mode == "message" else ""
        if force or message != self.battle_message:
            self.battle_message = message
            self.battle_message_reveal = 0
            self.battle_message_tick = 0

    def update_battle_message_reveal(self):
        if self.scene != "battle" or not self.scripted_battle or self.battle_effect:
            return
        self.sync_scripted_battle_message()
        _speaker, message = self._split_dialogue(self.battle_message)
        if self.scripted_battle.mode != "message" or self.battle_message_reveal >= len(message):
            return
        self.battle_message_tick += 1
        if self.battle_message_tick >= DIALOGUE_CHAR_FRAMES:
            self.battle_message_reveal += 1
            self.battle_message_tick = 0

    def use_move(self, move):
        light_value = 512 if self.light is None else self.light
        light_power = 0.5 + light_value / 1023.0
        if move == 0:
            heal = round(18 * light_power)
            self.player_hp = min(100, self.player_hp + heal)
            self.begin_battle_effect("synthesis", f"坚果哑铃使用了光合作用！恢复 {heal} 点体力。")
        elif move == 1:
            damage = round(45 * light_power)
            self.enemy_hp = max(0, self.enemy_hp - damage)
            self.begin_battle_effect("solar", f"坚果哑铃使用了日光束！造成 {damage} 点伤害。")
        elif move == 2:
            if not self.heavy_ready:
                self.set_battle_notice("重磅冲撞需要先由震动传感器触发。", 2)
                return
            damage = 28 + min(35, self.vibration_count * 4)
            self.enemy_hp = max(0, self.enemy_hp - damage)
            self.heavy_ready = False
            self.begin_battle_effect("heavy", f"坚果哑铃使出重磅冲撞！造成 {damage} 点伤害！")
        else:
            temp = self.temperature if self.temperature is not None else 20
            kind = "火" if temp > 30 else ("冰" if temp < 10 else "一般")
            damage = 38 if temp > 30 or temp < 10 else 25
            self.enemy_hp = max(0, self.enemy_hp - damage)
            self.begin_battle_effect("weather", f"气象球变为{kind}属性！造成 {damage} 点伤害。")
        if self.enemy_hp <= 0:
            self.battle_won = True
            self.set_battle_notice("种子铁球倒下了！战斗胜利，按 Enter 前往 1 号道路。", 4)
            return
        self.player_hp = max(0, self.player_hp - 8)
        if self.player_hp <= 0:
            self.battle_lost = True
            self.set_battle_notice("坚果哑铃失去战斗能力。按 Enter 再次挑战。", 4)

    def set_battle_notice(self, text, seconds=2.0):
        self.battle_notice = text
        self.battle_notice_until = time.monotonic() + seconds

    def begin_battle_effect(self, effect, message, target=None, hp_transition=None):
        sound = self.battle_sounds.get(effect)
        if sound:
            sound.play()
        self.battle_effect = {
            "name": effect,
            "frame": 0,
            "message": message,
            "target": target or ("player" if effect == "synthesis" else "foe"),
            "hp_transition": hp_transition,
        }
        if self.scripted_battle:
            self.battle_message = message
            self.battle_message_reveal = len(message)
            self.battle_message_tick = 0
        self.set_battle_notice(message, 2.2)

    def update_battle_effect(self):
        if not self.battle_effect:
            return
        self.battle_effect["frame"] += 1
        frames = self.battle_effect_frames.get(self.battle_effect["name"], [])
        # The standalone battle UI holds each 192px effect frame for ~110ms.
        duration = max(48, len(frames) * 7)
        transition = self.battle_effect.get("hp_transition")
        if transition:
            side, start, target = transition
            value = round(start + (target - start) * min(1.0, self.battle_effect["frame"] / duration))
            if side == "player":
                self.player_hp = value
            else:
                self.enemy_hp = value
        if self.battle_effect["frame"] >= duration:
            self.battle_effect = None
            if self.scripted_battle and self.scripted_battle.mode == "action":
                self.scripted_battle.complete_action()
                self.player_hp = self.scripted_battle.player_hp
                self.enemy_hp = self.scripted_battle.foe_hp
                self.battle_won = self.scripted_battle.outcome == "won"
                self.battle_lost = self.scripted_battle.outcome == "lost"
                self.sync_scripted_battle_message(force=True)

    def vibration(self):
        if self.scene == "cave3" and self.adjacent(self.pos, self.ROCK_POS) and not self.rock_broken:
            self.rock_broken = True
            self.show_toast("重磅冲撞！岩石被击碎，通道打开了。", 3)
        elif self.scene == "battle":
            self.heavy_ready = True
            self.show_toast("震动已检测：重磅冲撞准备完成。", 2)
        elif self.scene in self.SCENES:
            self.show_toast("检测到震动，但附近没有可互动岩石。", 1.8)

    @staticmethod
    def adjacent(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) <= 1

    def cycle_scene(self):
        self.step = None
        self.field_attack = None
        self.warp_fade_frames = 0
        order = ["home", "friend", "battle", "route", "cave1", "cave2", "cave3", "ending"]
        self.scene = order[(order.index(self.scene) + 1) % len(order)]
        if self.scene in self.SCENES:
            self.pos[:] = self.scene_start(self.scene)

    def reset(self):
        self.map_view = None
        self.step = None
        self.field_attack = None
        self.warp_fade_frames = 0
        self.facing = "down"
        self.scene, self.pos = "home", self.scene_start("home")
        self.father_done = self.friend_met = self.battle_won = False
        self.battle_lost = False
        self.battle_effect = None
        self.rock_broken = False
        self.dialogue = []
        self.dialogue_index = 0
        self.dialogue_source = None
        self.dialogue_preload = None
        self.dialogue_reveal = 0
        self.dialogue_reveal_tick = 0
        self.triggered_step_events.clear()
        self.completed_map_events.clear()
        self.story_flags.clear()
        self.active_map_event = None
        self.active_map_event_step = 0
        self.map_event_origin = None
        self.event_action = None
        self.event_camera_focus = None
        self.event_actor_positions.clear()
        self.hidden_event_actors.clear()
        self.event_battle_active = False
        self.event_battle_return = None
        self.scripted_battle = None
        self.meteor_phase = 0
        self.player_hp, self.enemy_hp = 100, 100
        self.show_toast("回到父亲的家。靠近左上角父亲并按 Enter。", 3)

    def show_toast(self, text, seconds=2):
        self.toast, self.toast_until = text, time.monotonic() + seconds

    def draw(self):
        if self.map_view:
            self.draw_map_view()
        elif self.scene == "battle":
            self.draw_battle()
        elif self.scene == "ending":
            self.draw_ending()
        else:
            self.draw_map()
        if self.map_view or self.scene not in ("battle", "ending"):
            self.draw_status_badge()
        if self.dialogue:
            speaker, message = self._split_dialogue(self.dialogue[self.dialogue_index])
            visible_message = message[:self.dialogue_reveal]
            text = f"{speaker}：{visible_message}" if speaker else visible_message
            if self.dialogue_preload:
                self.draw_preloaded_dialogue(text, self.dialogue_preload)
            else:
                self.draw_dialogue(text)
        elif self.toast and time.monotonic() < self.toast_until:
            self.draw_toast(self.toast)
        self.draw_warp_fade()
        scaled = pygame.transform.scale(self.screen, WINDOW_SIZE)
        self.display.blit(scaled, (0, 0))
        pygame.display.flip()

    def draw_map_view(self):
        tile_map = self.tile_maps[self.map_view]
        actor_pos = self.actor_grid_position(self.map_view_pos)
        camera_x, camera_y, origin_x, origin_y = self.map_camera(tile_map, actor_pos)
        self.screen.fill((20, 24, 22), (0, 0, PLAY_W, PLAY_H))
        self.draw_tile_layer(tile_map, "lower", camera_x, camera_y, origin_x, origin_y)
        self.draw_tile_layer(tile_map, "current", camera_x, camera_y, origin_x, origin_y)
        self.draw_map_event_icons(tile_map, camera_x, camera_y, origin_x, origin_y)
        actor_x = origin_x + (actor_pos[0] + 0.5) * TILE_SIZE - camera_x
        actor_y = origin_y + (actor_pos[1] + 0.5) * TILE_SIZE - camera_y
        self.draw_actor(actor_x, actor_y)
        self.draw_tile_layer(tile_map, "upper", camera_x, camera_y, origin_x, origin_y)
        self.draw_rock_break(camera_x, camera_y, origin_x, origin_y)
        self.draw_event_animation(camera_x, camera_y, origin_x, origin_y)

        index = self.MAP_VIEW_ORDER.index(self.map_view) + 1
        label = f"{index}  {self.MAP_VIEW_TITLES[self.map_view]}  {tile_map.width}×{tile_map.height}"
        label_box = pygame.Rect(6, 6, self.title.size(label)[0] + 14, 25)
        pygame.draw.rect(self.screen, (16, 27, 26), label_box, border_radius=3)
        pygame.draw.rect(self.screen, (169, 190, 126), label_box, 1, border_radius=3)
        self.screen.blit(self.title.render(label, True, (252, 247, 210)), (13, 10))

    def map_camera(self, tile_map, actor_pos):
        map_width = tile_map.width * TILE_SIZE
        map_height = tile_map.height * TILE_SIZE
        focus = self.event_camera_focus or actor_pos
        focus_x = (focus[0] + 0.5) * TILE_SIZE
        focus_y = (focus[1] + 0.5) * TILE_SIZE
        camera_x = round(max(0, min(max(0, map_width - PLAY_W), focus_x - PLAY_W / 2)))
        camera_y = round(max(0, min(max(0, map_height - PLAY_H), focus_y - PLAY_H / 2)))
        action = self.event_action
        if action and action.get("type") == "camera_shake":
            strength = int(action["step"].get("intensity", 6))
            decay = 1.0 - min(1.0, action["frame"] / action["total"])
            camera_x += round(math.sin(action["frame"] * 2.7) * strength * decay)
            camera_y += round(math.cos(action["frame"] * 3.9) * strength * decay)
            camera_x = max(0, min(max(0, map_width - PLAY_W), camera_x))
            camera_y = max(0, min(max(0, map_height - PLAY_H), camera_y))
        origin_x = max(0, (PLAY_W - map_width) // 2)
        origin_y = max(0, (PLAY_H - map_height) // 2)
        return camera_x, camera_y, origin_x, origin_y

    def draw_tile_layer(self, tile_map, layer_name, camera_x, camera_y, origin_x=0, origin_y=0):
        grid = tile_map.layers[layer_name]
        first_x = max(0, camera_x // TILE_SIZE)
        first_y = max(0, camera_y // TILE_SIZE)
        last_x = min(tile_map.width, (camera_x + PLAY_W + TILE_SIZE - 1) // TILE_SIZE)
        last_y = min(tile_map.height, (camera_y + PLAY_H + TILE_SIZE - 1) // TILE_SIZE)
        for y in range(first_y, last_y):
            for x in range(first_x, last_x):
                self.screen.blit(
                    grid[y][x],
                    (origin_x + x * TILE_SIZE - camera_x,
                     origin_y + y * TILE_SIZE - camera_y),
                )

    def load_map_event_icon(self, name):
        name = Path(str(name)).name
        if not name:
            return None
        if name in self.map_event_icon_cache:
            return self.map_event_icon_cache[name]
        path = ICON_DIR / name
        try:
            source = pygame.image.load(str(path)).convert_alpha()
        except (pygame.error, FileNotFoundError):
            self.map_event_icon_cache[name] = None
            return None
        if source.get_width() >= source.get_height() * 2:
            source = source.subsurface((0, 0, source.get_height(), source.get_height())).copy()
        bounds = source.get_bounding_rect(min_alpha=1)
        if not bounds.width or not bounds.height:
            self.map_event_icon_cache[name] = None
            return None
        source = source.subsurface(bounds).copy()
        scale = min(28 / source.get_width(), 28 / source.get_height())
        source = pygame.transform.scale(
            source,
            (max(1, round(source.get_width() * scale)),
             max(1, round(source.get_height() * scale))),
        )
        icon = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        icon.blit(source, ((TILE_SIZE - source.get_width()) // 2,
                           TILE_SIZE - source.get_height() - 2))
        self.map_event_icon_cache[name] = icon
        return icon

    def draw_map_event_icons(self, tile_map, camera_x, camera_y, origin_x=0, origin_y=0):
        for event in self.map_events:
            if event.get("map") != tile_map.name:
                continue
            if event.get("trigger", "step") != "step":
                continue
            if not conditions_met(event, self.story_flags):
                continue
            if event.get("once", True) and event["id"] in self.completed_map_events:
                continue
            if event["id"] in self.hidden_event_actors:
                continue
            x, y = self.event_actor_positions.get(event["id"], event["position"])
            if not (0 <= x < tile_map.width and 0 <= y < tile_map.height):
                continue
            icon = self.load_map_event_icon(event.get("icon", ""))
            if icon:
                self.screen.blit(
                    icon,
                    (origin_x + x * TILE_SIZE - camera_x,
                     origin_y + y * TILE_SIZE - camera_y),
                )

    def draw_map(self):
        bg = self.backgrounds.get(self.scene)
        outdoor = self.outdoor_maps.get(self.scene)
        actor_pos = self.actor_grid_position(self.pos)
        if outdoor and self.scene in self.tile_maps:
            tile_map = self.tile_maps[self.scene]
            camera_x, camera_y, origin_x, origin_y = self.map_camera(tile_map, actor_pos)
            self._map_camera = (camera_x, camera_y, origin_x, origin_y)
            self.screen.fill((46, 91, 58))
            self.draw_tile_layer(tile_map, "lower", *self._map_camera)
            self.draw_tile_layer(tile_map, "current", *self._map_camera)
        elif bg:
            target = pygame.Rect(0, 0, PLAY_W, HEIGHT)
            if self.scene.startswith("cave"):
                self.map_rect = self.blit_fit(bg, target, (91, 67, 48))
            else:
                self.map_rect = target
                self.blit_cover(bg, target)
        else:
            self.map_rect = pygame.Rect(0, 0, PLAY_W, HEIGHT)
            self.screen.fill((46, 91, 58), (0, 0, PLAY_W, HEIGHT))
        if outdoor and self.scene in self.tile_maps:
            self.draw_map_event_icons(self.tile_maps[self.scene], *self._map_camera)
        if self.scene == "home":
            self.draw_npc_at("home", self.father_frames, "父亲")
        elif self.scene == "friend":
            self.draw_npc_at("friend", self.friend, "青梅")
        elif self.scene == "route":
            self.screen.blit(self.font.render("流星坠落方向 ↑", True, (255, 245, 180)), (12, 12))
            if self.meteor_phase:
                pygame.draw.line(self.screen, (255, 245, 160), (350, 8), (390, 80), 3)
                pygame.draw.circle(self.screen, (255, 239, 143), (350, 8), 7)
        elif self.scene == "cave3":
            self.draw_rock()
            if self.rock_broken and self.jirachi:
                self.screen.blit(self.jirachi, self.jirachi.get_rect(center=(390, 75)))
        x, y = self.tile_point(actor_pos)
        self.draw_actor(x, y)
        # Upper layer is intentionally rendered last: tree crowns and roof
        # edges can cover the actor's head while walking underneath them.
        if outdoor and self.scene in self.tile_maps:
            self.draw_tile_layer(self.tile_maps[self.scene], "upper", *self._map_camera)
            self.draw_event_animation(*self._map_camera)
        self.screen.blit(self.title.render(self.SCENES[self.scene][3], True, (252, 247, 210)), (10, 9))

    def load_event_animation(self, name):
        if name in self.event_animation_cache:
            return self.event_animation_cache[name]
        frames = []
        if name == "meteor":
            for index in range(1, 4):
                image = self._load(f"resource/Meteor/Meteor{index}.png")
                if image:
                    frames.append(image)
        elif name == "dust":
            sheet = self._load("resource/map/effects/dust_and_grass.png")
            if sheet:
                frame_size = 192
                for y in range(0, sheet.get_height(), frame_size):
                    for x in range(0, sheet.get_width(), frame_size):
                        if x + frame_size <= sheet.get_width() and y + frame_size <= sheet.get_height():
                            frames.append(sheet.subsurface((x, y, frame_size, frame_size)).copy())
        self.event_animation_cache[name] = frames
        return frames

    def draw_event_animation(self, camera_x, camera_y, origin_x=0, origin_y=0):
        action = self.event_action
        if not action or action.get("type") != "play_animation":
            return
        step = action["step"]
        name = step.get("animation", "")
        frames = self.load_event_animation(name)
        if not frames:
            return
        progress = min(1.0, action["frame"] / action["total"])
        frame = frames[min(len(frames) - 1, int(progress * len(frames)))]
        x, y = step.get("position", (0, 0))
        screen_x = origin_x + (x + 0.5) * TILE_SIZE - camera_x
        screen_y = origin_y + (y + 0.5) * TILE_SIZE - camera_y
        if name == "meteor":
            screen_y -= (1.0 - progress) * 180
            size = (64, 64)
        else:
            size = (80, 80)
        image = pygame.transform.scale(frame, size)
        self.screen.blit(image, image.get_rect(center=(round(screen_x), round(screen_y))))

    def tile_point(self, pos):
        outdoor = self.outdoor_maps.get(self.scene)
        if outdoor and hasattr(self, "_map_camera"):
            camera_x, camera_y, origin_x, origin_y = self._map_camera
            return (origin_x + (pos[0] + 0.5) * TILE_SIZE - camera_x,
                    origin_y + (pos[1] + 0.5) * TILE_SIZE - camera_y)
        grid = self.SCENES[self.scene][1]
        rect = getattr(self, "map_rect", pygame.Rect(0, 0, PLAY_W, HEIGHT))
        pad_x = min(58, rect.width * 0.08)
        pad_y = min(42, rect.height * 0.08)
        return (rect.left + pad_x + pos[0] * (rect.width - 2 * pad_x) / max(1, grid[0] - 1),
                rect.top + pad_y + pos[1] * (rect.height - 2 * pad_y) / max(1, grid[1] - 1))

    def draw_actor(self, x, y):
        shadow = pygame.Rect(int(x - 10), int(y + 11), 20, 5)
        pygame.draw.ellipse(self.screen, (30, 45, 30), shadow)
        frames = self.player_frames.get(self.facing, [])
        if self.field_attack:
            attack_frames = self.attack_frames.get(self.facing, [])
            sequence = (0, 1, 2, 1, 0)
            if attack_frames and self.field_attack["frame"] < len(sequence) * 2:
                sequence_index = min(len(sequence) - 1, self.field_attack["frame"] // 2)
                image = attack_frames[sequence[sequence_index]]
                self.screen.blit(image, image.get_rect(center=(round(x), round(y))))
                return
        if frames:
            frame_index = min(len(frames) - 1, self.step["frame"] - 1) if self.step else 1
            image = frames[max(0, frame_index)]
            self.screen.blit(image, image.get_rect(center=(round(x), round(y))))
        elif self.player:
            self.screen.blit(self.player, self.player.get_rect(center=(round(x), round(y))))
        else:
            pygame.draw.circle(self.screen, (180, 200, 180), (round(x), round(y)), 14)

    def draw_rock_break(self, camera_x, camera_y, origin_x=0, origin_y=0):
        attack = self.field_attack
        if not attack or not attack["broken"] or not self.rock_break_frames:
            return
        elapsed = attack["frame"] - FIELD_ATTACK_WINDUP_FRAMES
        frame_index = min(len(self.rock_break_frames) - 1, elapsed // ROCK_FRAME_HOLD)
        x, y = attack["target"]
        self.screen.blit(
            self.rock_break_frames[frame_index],
            (origin_x + x * TILE_SIZE - camera_x,
             origin_y + y * TILE_SIZE - camera_y),
        )

    def draw_warp_fade(self):
        if not self.warp_fade_frames:
            return
        fade_frames = WARP_FADE_FRAMES * 2 // 3
        alpha = 255 if self.warp_fade_frames > fade_frames else round(
            255 * self.warp_fade_frames / fade_frames
        )
        self.fade_overlay.fill((0, 0, 0, alpha))
        self.screen.blit(self.fade_overlay, (0, 0))

    def draw_npc(self, x, y, image, label):
        if isinstance(image, dict):
            frames = image.get("down", [])
            sprite = frames[1 if len(frames) > 1 else 0] if frames else None
            if sprite:
                self.screen.blit(sprite, sprite.get_rect(center=(x, y)))
        elif image:
            image = pygame.transform.scale(image, (32, 32))
            self.screen.blit(image, image.get_rect(center=(x, y)))
        else:
            pygame.draw.circle(self.screen, (222, 216, 174), (x, y), 14)
        self.screen.blit(self.small.render(label, True, (30, 45, 30)), (x - 12, y + 17))

    def draw_npc_at(self, scene, image, label):
        x, y = self.tile_point(self.NPC_POS[scene])
        self.draw_npc(int(x), int(y), image, label)

    def draw_rock(self):
        if self.rock_broken:
            return
        x, y = self.tile_point(self.ROCK_POS)
        pygame.draw.polygon(self.screen, (93, 92, 103), ((x - 14, y + 12), (x - 11, y - 11), (x + 10, y - 13), (x + 15, y + 9), (x + 4, y + 14)))
        pygame.draw.line(self.screen, (185, 181, 191), (x - 5, y - 7), (x + 7, y + 5), 2)

    def draw_battle(self):
        if self.battle_background:
            self.screen.blit(self.battle_background, (0, 0), (16, 0, WIDTH, 228))
        else:
            self.screen.fill((43, 72, 65), (0, 0, WIDTH, 228))

        player_base = self.battle_bases.get("player")
        foe_base = self.battle_bases.get("foe")
        if player_base:
            self.screen.blit(player_base, (-16, 166))
        if foe_base:
            self.screen.blit(foe_base, (240, 44))

        intro = min(1.0, (time.monotonic() - self.battle_started_at) / 0.56)
        player_x = round(-120 + 168 * intro)
        foe_x = round(440 - 148 * intro)
        player_y = 62
        foe_y = 8 + round(2 * math.sin(time.monotonic() / 0.21))
        if self.battle_effect:
            offset = 5 if (self.battle_effect["frame"] // 4) % 2 == 0 else -5
            if self.battle_effect.get("target") == "player":
                player_x += offset
            elif self.battle_effect.get("target") == "foe":
                foe_x += offset
        if self.ferro_battle and not self.battle_lost:
            self.screen.blit(self.ferro_battle, (player_x, player_y))
        if self.enemy_battle and not self.battle_won:
            self.screen.blit(self.enemy_battle, (foe_x, foe_y))
        self.draw_battle_effect()
        self.draw_gen3_databoxes()
        self.draw_battle_menu()

    def draw_gen3_databoxes(self):
        foe_box = self.battle_ui.get("foe_box")
        player_box = self.battle_ui.get("player_box")
        if foe_box:
            self.screen.blit(foe_box, (6, 8))
        if player_box:
            self.screen.blit(player_box, (280, 146))
        foe_name = (
            self.scripted_battle.config["opponent"]["name"]
            if self.scripted_battle else "青梅的种子铁球"
        )
        text_color = (48, 48, 40)
        self.screen.blit(self.battle_font.render(foe_name, False, text_color), (18, 18))
        self.screen.blit(self.battle_font.render("坚果哑铃", False, text_color), (292, 156))
        foe_max = self.scripted_battle.foe_max_hp if self.scripted_battle else 100
        player_max = self.scripted_battle.player_max_hp if self.scripted_battle else 100
        self.draw_gen3_hp_bar("foe", self.enemy_hp, foe_max)
        self.draw_gen3_hp_bar("player", self.player_hp, player_max)
        hp_text = f"{round(self.player_hp)}/{player_max}"
        rendered = self.battle_small.render(hp_text, False, text_color)
        self.screen.blit(rendered, (466 - rendered.get_width(), 194))

    def draw_gen3_hp_bar(self, side, hp, maximum):
        ratio = max(0.0, min(1.0, hp / max(1, maximum)))
        asset_name = "hp_green" if ratio > 0.5 else ("hp_yellow" if ratio > 0.2 else "hp_red")
        fill = self.battle_ui.get(asset_name)
        width = max(0, min(96, round(96 * ratio / 2) * 2))
        if fill and width:
            x, y = (86, 44) if side == "foe" else (366, 184)
            self.screen.blit(fill, (x, y), (0, 0, width, 6))

    def draw_battle_effect(self):
        effect = self.battle_effect
        if not effect:
            return
        frames = self.battle_effect_frames.get(effect["name"], [])
        if not frames:
            return
        frame = frames[min(len(frames) - 1, effect["frame"] // 7)]
        target = (126, 142) if effect.get("target") == "player" else (372, 100)
        self.screen.blit(frame, frame.get_rect(center=target))

    def draw_battle_menu(self):
        if self.scripted_battle:
            self.draw_scripted_battle_menu()
            return
        message_active = self.battle_effect or time.monotonic() < self.battle_notice_until
        if message_active:
            overlay = self.battle_ui.get("message")
            if overlay:
                self.screen.blit(overlay, (0, 228))
            else:
                pygame.draw.rect(self.screen, (40, 56, 64), (0, 228, WIDTH, 92))
            message = self.battle_effect["message"] if self.battle_effect else self.battle_notice
            self.draw_multiline(
                18, 244, message, self.battle_font, (248, 248, 248), 444,
                antialias=False,
            )
            return

        move_list = self.battle_ui.get("fight")
        move_info = self.battle_ui.get("move_info")
        if move_list:
            self.screen.blit(move_list, (0, 220))
        else:
            pygame.draw.rect(self.screen, (232, 232, 232), (0, 220, 318, 100))
        if move_info:
            self.screen.blit(move_info, (324, 220))
        labels = ["光合作用", "日光束", "重磅冲撞", "气象球"]
        positions = ((28, 234), (174, 234), (28, 274), (174, 274))
        for index, (label, position) in enumerate(zip(labels, positions)):
            suffix = " *" if index == 2 and self.heavy_ready else ""
            self.screen.blit(self.battle_font.render(label + suffix, False, (48, 48, 40)), position)
        cursor = self.battle_ui.get("cursor")
        if cursor:
            self.screen.blit(cursor, (8 + (self.move_cursor % 2) * 146,
                                      232 + (self.move_cursor // 2) * 40))
        info = (
            ("属性/变化", "光照决定回复") if self.move_cursor == 0 else
            ("属性/特殊", "光照决定威力") if self.move_cursor == 1 else
            ("属性/物理", "震动后可以使用") if self.move_cursor == 2 else
            ("属性/特殊", "温度决定属性")
        )
        for index, line in enumerate(info):
            self.screen.blit(self.battle_small.render(line, False, (56, 56, 56)),
                             (338, 236 + index * 36))

    def draw_scripted_battle_menu(self):
        battle = self.scripted_battle
        if battle is None:
            return
        if self.battle_effect or battle.mode == "message":
            overlay = self.battle_ui.get("message")
            if overlay:
                self.screen.blit(overlay, (0, 228))
            else:
                pygame.draw.rect(self.screen, (40, 56, 64), (0, 228, WIDTH, 92))
            if self.battle_effect:
                message = self.battle_effect["message"]
            else:
                speaker, body = self._split_dialogue(self.battle_message)
                visible_body = body[:self.battle_message_reveal]
                message = f"{speaker}：{visible_body}" if speaker else visible_body
            self.draw_multiline(
                18, 244, message, self.battle_font, (248, 248, 248), 444,
                antialias=False,
            )
            _speaker, full_body = self._split_dialogue(self.battle_message)
            if (not self.battle_effect and
                    self.battle_message_reveal >= len(full_body)):
                cursor = self.battle_ui.get("continue")
                if cursor:
                    bob = 2 if int(time.monotonic() * 4) % 2 else 0
                    self.screen.blit(cursor, (444, 288 + bob))
            return

        move_list = self.battle_ui.get("fight")
        move_info = self.battle_ui.get("move_info")
        if move_list:
            self.screen.blit(move_list, (0, 220))
        else:
            pygame.draw.rect(self.screen, (232, 232, 232), (0, 220, 318, 100))
        if move_info:
            self.screen.blit(move_info, (324, 220))
        else:
            pygame.draw.rect(self.screen, (232, 232, 232), (324, 220, 156, 100))
        moves = battle.available_moves
        self.move_cursor %= max(1, len(moves))
        positions = ((28, 234), (174, 234), (28, 274), (174, 274))
        for index, position in enumerate(positions):
            label = battle.move_spec(moves[index])["name"] if index < len(moves) else "—"
            font = self.battle_font if index < len(moves) else self.battle_small
            color = (48, 48, 40) if index < len(moves) else (128, 128, 128)
            self.screen.blit(font.render(label, False, color), position)
        cursor = self.battle_ui.get("cursor")
        if cursor:
            cursor_x = 8 + (self.move_cursor % 2) * 146
            cursor_y = 232 + (self.move_cursor // 2) * 40
            self.screen.blit(cursor, (cursor_x, cursor_y))
        selected = battle.move_spec(moves[self.move_cursor])
        if battle.hint:
            required = battle.move_spec(battle.required_move)["name"]
            info = ("当前教学目标", f"请使用{required}")
        else:
            info = selected.get("info", [])
        for index, line in enumerate(info[:2]):
            self.screen.blit(
                self.battle_small.render(str(line), False, (56, 56, 56)),
                (338, 236 + index * 36),
            )

    def blit_cover(self, image, target):
        """Scale a map or battle background without changing its aspect ratio."""
        iw, ih = image.get_size()
        scale = max(target.width / iw, target.height / ih)
        size = (max(1, round(iw * scale)), max(1, round(ih * scale)))
        scaled = pygame.transform.scale(image, size)
        crop = scaled.get_rect(center=target.center)
        self.screen.set_clip(target)
        self.screen.blit(scaled, crop)
        self.screen.set_clip(None)

    def blit_fit(self, image, target, fill):
        """Show a complete floor map, letterboxed instead of cropping it."""
        self.screen.fill(fill, target)
        iw, ih = image.get_size()
        scale = min(target.width / iw, target.height / ih)
        size = (max(1, round(iw * scale)), max(1, round(ih * scale)))
        scaled = pygame.transform.scale(image, size)
        rect = scaled.get_rect(center=target.center)
        self.screen.blit(scaled, rect)
        return rect

    def blit_layer(self, image, target):
        """Composite a transparent outdoor layer over the fitted map rect."""
        scaled = pygame.transform.scale(image, target.size)
        self.screen.blit(scaled, target)

    def draw_hp(self, xy, name, hp):
        x, y = xy
        self.screen.blit(self.font.render(name, True, (30, 50, 35)), (x, y))
        pygame.draw.rect(self.screen, (43, 51, 43), (x, y + 18, 155, 10), border_radius=4)
        pygame.draw.rect(self.screen, (218, 214, 112) if hp > 30 else (207, 92, 76),
                         (x + 2, y + 20, max(0, round(151 * hp / 100)), 6), border_radius=3)
        self.screen.blit(self.small.render(f"HP {hp}/100", True, (30, 50, 35)), (x + 98, y + 30))

    def draw_ending(self):
        self.screen.fill((42, 43, 77))
        pygame.draw.circle(self.screen, (245, 229, 158), (260, 110), 82)
        if self.jirachi:
            self.screen.blit(self.jirachi, self.jirachi.get_rect(center=(260, 105)))
        self.draw_actor(125, 185)
        self.screen.blit(self.title.render("流星的朋友", True, (255, 244, 186)), (14, 14))
        self.draw_dialogue("基拉祈：谢谢你把我唤醒。今后，我们一起寻找更多流星吧。")

    def draw_status_badge(self):
        position = self.map_view_pos if self.map_view else self.pos
        coordinate = self.small.render(
            f"X {position[0]}   Y {position[1]}", True, (252, 247, 210)
        )
        coordinate_box = pygame.Rect(
            WIDTH - coordinate.get_width() - 16, 6,
            coordinate.get_width() + 10, 20,
        )
        pygame.draw.rect(self.screen, (16, 27, 26), coordinate_box, border_radius=3)
        pygame.draw.rect(self.screen, (212, 185, 101), coordinate_box, 1, border_radius=3)
        self.screen.blit(coordinate, (coordinate_box.x + 5, coordinate_box.y + 5))

        light = "--" if self.light is None else str(self.light)
        temp = "--" if self.temperature is None else f"{self.temperature:.1f}C"
        text = f"L {light}   T {temp}   V {self.vibration_count}"
        rendered = self.small.render(text, True, (235, 242, 214))
        box = pygame.Rect(WIDTH - rendered.get_width() - 16, 29,
                          rendered.get_width() + 10, 20)
        pygame.draw.rect(self.screen, (16, 27, 26), box, border_radius=3)
        pygame.draw.rect(self.screen, (111, 151, 103), box, 1, border_radius=3)
        self.screen.blit(rendered, (box.x + 5, box.y + 5))

    def draw_dialogue(self, text):
        # Hades-inspired layout: a large speaker card occupies the left half
        # of the lower screen, with a readable text panel beside it.  It also
        # works for scenes without a portrait by simply omitting the card art.
        speaker, message = self._split_dialogue(text)
        portrait = self.dialogue_portraits.get(speaker)
        panel = pygame.Rect(156 if portrait else 10, 224, WIDTH - (166 if portrait else 20), 86)
        if portrait:
            card = pygame.Rect(8, 128, 142, 182)
            pygame.draw.rect(self.screen, (12, 22, 23), card, border_radius=5)
            pygame.draw.rect(self.screen, (169, 190, 126), card, 2, border_radius=5)
            self.screen.blit(portrait, portrait.get_rect(midbottom=(card.centerx, card.bottom - 7)))
            name_box = pygame.Rect(card.x + 8, card.y + 8, card.width - 16, 23)
            pygame.draw.rect(self.screen, (20, 37, 35), name_box, border_radius=3)
            self.screen.blit(self.font.render(speaker, True, (250, 239, 180)), (name_box.x + 7, name_box.y + 3))
        pygame.draw.rect(self.screen, (16, 27, 26), panel, border_radius=5)
        pygame.draw.rect(self.screen, (169, 190, 126), panel, 2, border_radius=5)
        self.draw_multiline(panel.x + 12, panel.y + 14, message, self.font,
                            (242, 245, 220), panel.width - 24)
        hint = self.small.render("Enter / 开发板中心键 继续", True, (180, 205, 177))
        self.screen.blit(hint, (panel.right - hint.get_width() - 10, panel.bottom - hint.get_height() - 7))

    def load_dialogue_preload(self, name):
        name = Path(str(name)).name
        if name in self.dialogue_preload_cache:
            return self.dialogue_preload_cache[name]
        path = PRELOAD_DIR / name
        try:
            image = pygame.image.load(str(path)).convert_alpha()
            if image.get_size() != (WIDTH, HEIGHT):
                image = pygame.transform.scale(image, (WIDTH, HEIGHT))
        except (pygame.error, FileNotFoundError):
            image = None
        self.dialogue_preload_cache[name] = image
        return image

    def draw_preloaded_dialogue(self, text, preload_name):
        """Composite a prepared portrait/dialogue overlay over the live scene."""
        overlay = self.load_dialogue_preload(preload_name)
        if overlay is None:
            self.draw_dialogue(text)
            return
        self.screen.blit(overlay, (0, 0))
        center_box = Path(preload_name).name == "no_portrait_center.png"
        if center_box:
            x, y, width, height = 82, 123, 316, 74
        else:
            x, y, width, height = 28, 241, 424, 53
        self.draw_multiline(x, y, text, self.font, (38, 48, 54), width, height)
        full = self.dialogue[self.dialogue_index] if self.dialogue else ""
        _speaker, full_message = self._split_dialogue(full)
        if self.dialogue_reveal >= len(full_message):
            tip_x = 386 if center_box else 440
            tip_y = 184 if center_box else 282
            pygame.draw.polygon(
                self.screen,
                (52, 66, 70),
                ((tip_x, tip_y), (tip_x + 7, tip_y), (tip_x + 3, tip_y + 5)),
            )

    @staticmethod
    def _split_dialogue(text):
        separator = "：" if "：" in text else (":" if ":" in text else None)
        if separator:
            speaker, message = text.split(separator, 1)
            return speaker.strip(), message.strip()
        return "", text

    def draw_toast(self, text):
        box = pygame.Rect(10, 284, min(WIDTH - 20, 22 + self.small.size(text)[0]), 26)
        pygame.draw.rect(self.screen, (17, 29, 25), box, border_radius=3)
        pygame.draw.rect(self.screen, (212, 185, 101), box, 1, border_radius=3)
        self.screen.blit(self.small.render(text, True, (249, 238, 181)), (box.x + 8, box.y + 7))

    def draw_multiline(self, x, y, text, font, color, max_width, max_height=None, antialias=True):
        line, lines = "", []
        for paragraph in text.split("\n"):
            for char in paragraph:
                if line and font.size(line + char)[0] > max_width:
                    lines.append(line)
                    line = ""
                line += char
            lines.append(line)
            line = ""
        line_height = font.get_height() + 3
        for i, value in enumerate(lines):
            if max_height is not None and (i + 1) * line_height > max_height:
                break
            self.screen.blit(font.render(value, antialias, color), (x, y + i * line_height))


if __name__ == "__main__":
    Game(sys.argv[1] if len(sys.argv) > 1 else None).run()

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
from pathlib import Path

import pygame

try:
    import serial
except ImportError:
    serial = None


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
WIDTH, HEIGHT = 1200, 720
PLAY_W, PLAY_H = 800, 720
FPS = 60


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
    SCENES = {
        # Outdoor scenes use a 24x18 hidden logic grid.  The visible map is
        # composed from the three generated Outside tileset layers.
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
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("STC-B 坚果哑铃：流星与基拉祈")
        self.clock = pygame.time.Clock()
        self.font = self._font(21)
        self.small = self._font(16)
        self.title = self._font(30, True)
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
        self.toast = ""
        self.toast_until = 0.0
        self.meteor_phase = 0
        self.player_hp, self.enemy_hp = 100, 100
        self.move_cursor = 0
        self.heavy_ready = False
        self._load_assets()

    @staticmethod
    def _font(size, bold=False):
        candidates = [Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf")]
        for path in candidates:
            if path.exists():
                return pygame.font.Font(str(path), size)
        return pygame.font.Font(None, size)

    def _load_assets(self):
        self.outdoor_maps = {}
        map_index = ASSETS / "maps" / "outdoor_maps.json"
        if map_index.exists():
            try:
                raw_maps = json.loads(map_index.read_text(encoding="utf-8"))
                for scene, spec in raw_maps.items():
                    layers = {}
                    for layer, rel_path in spec.get("layers", {}).items():
                        try:
                            layers[layer] = pygame.image.load(str(ASSETS / rel_path)).convert_alpha()
                        except (pygame.error, FileNotFoundError):
                            layers[layer] = None
                    self.outdoor_maps[scene] = {
                        "layers": layers,
                        "size": tuple(spec.get("size", (24, 18))),
                        "blocked": {tuple(cell) for cell in spec.get("blocked", [])},
                    }
            except (OSError, ValueError, TypeError):
                self.outdoor_maps = {}
        self.backgrounds = {}
        for scene, (name, _grid, _start, _title) in self.SCENES.items():
            path = ASSETS / name
            try:
                self.backgrounds[scene] = pygame.image.load(str(path)).convert()
            except (pygame.error, FileNotFoundError):
                self.backgrounds[scene] = None
        self.player = self._load("resource/map/characters/ferrothorn_user.png") or self._load("FERROTHORN_USER.png")
        self.friend = self._load("introMarill.png")
        self.jirachi = self._load("JIRACHI.png")
        if self.player:
            if self.player.get_width() >= 32 and self.player.get_height() >= 32:
                self.player = self.player.subsurface((0, 0, 32, 32)).copy()
            self.player = pygame.transform.scale(self.player, (48, 48))
        battle_player = self._load("resource/battle/pokemon/back/ferrothorn.png") or self.player
        self.ferro_battle = pygame.transform.smoothscale(battle_player, (210, 210)) if battle_player else None
        self.battle_background = self._load("resource/battle/backgrounds/cave1_bg.png")
        if self.jirachi:
            self.jirachi = pygame.transform.smoothscale(self.jirachi, (142, 142))
        if self.friend:
            self.friend = pygame.transform.smoothscale(self.friend, (48, 48))
        music = ASSETS / "Title.ogg"
        if music.exists():
            try:
                pygame.mixer.music.load(str(music))
                pygame.mixer.music.set_volume(0.24)
                pygame.mixer.music.play(-1)
            except pygame.error:
                pass

    @staticmethod
    def _load(name):
        for path in (ASSETS / name, ASSETS / "resource" / name):
            try:
                return pygame.image.load(str(path)).convert_alpha()
            except (pygame.error, FileNotFoundError):
                continue
        return None

    def run(self):
        while self.running:
            self.clock.tick(FPS)
            self.handle_events()
            self.read_serial()
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
                elif event.key == pygame.K_r:
                    self.reset()
                elif event.key == pygame.K_v:
                    self.vibration_count += 1
                    self.vibration()
                elif event.key == pygame.K_F1:
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
        if command == 6:
            self.reset()
            return
        if command == 7:
            self.show_toast("K2：取消当前对白/操作", 1.5)
            self.dialogue = []
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
        if self.dialogue:
            if command == 5:
                self.dialogue_index += 1
                if self.dialogue_index >= len(self.dialogue):
                    self.dialogue = []
                    self.after_dialogue()
            return
        if command in (1, 2, 3, 4):
            self.move(command)
        elif command == 5:
            self.interact()

    def move(self, command):
        grid = self.SCENES[self.scene][1]
        dxdy = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}[command]
        nx, ny = self.pos[0] + dxdy[0], self.pos[1] + dxdy[1]
        if not (0 <= nx < grid[0] and 0 <= ny < grid[1]):
            self.transition_from_edge(command)
            return
        if self.scene == "cave3" and not self.rock_broken and [nx, ny] == self.ROCK_POS:
            self.show_toast("岩石挡住了去路。请靠近后晃动 STC-B。", 2.5)
            return
        outdoor = self.outdoor_maps.get(self.scene)
        if outdoor and (nx, ny) in outdoor["blocked"]:
            self.show_toast("这里有花丛或装饰物，换个方向试试。", 1.0)
            return
        self.pos[:] = [nx, ny]

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
            self.scene = next_scene
            self.pos[:] = list(self.SCENES[next_scene][2])
            if next_scene == "route":
                self.meteor_phase = 1
                self.show_toast("一道流星划过天空，坠向北方的山洞。", 3)
            elif next_scene == "cave1":
                self.show_toast("洞口没有任何落石痕迹……声音从深处传来。", 3)
            elif next_scene == "cave3":
                self.show_toast("矿洞最深处，岩石封住了最后的通道。", 3)

    def interact(self):
        if self.scene in self.NPC_POS and not self.adjacent(self.pos, self.NPC_POS[self.scene]):
            target = "父亲" if self.scene == "home" else "青梅"
            self.show_toast(f"请靠近{target}后按中心键。", 1.8)
            return
        if self.scene == "home" and not self.father_done:
            self.dialogue = ["父亲：坚果哑铃，刚才的流星你也看见了吧？", "父亲：去左边的森林空地找你的青梅竹马。", "父亲：她也许知道流星落在哪里。"]
            self.dialogue_index = 0
            self.father_done = True
        elif self.scene == "friend" and not self.friend_met:
            self.dialogue = ["青梅：你也在追那颗流星？我们先练习一下招式吧。", "青梅：光照越强，日光束越强；光合作用也能恢复更多体力。", "青梅：温度还会改变气象球的属性。准备好就出发！"]
            self.dialogue_index = 0
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
        self.scene = "battle"
        self.player_hp, self.enemy_hp = 100, 100
        self.move_cursor = 0
        self.heavy_ready = False
        self.show_toast("训练战斗开始！", 2)

    def battle_command(self, command):
        if self.battle_won:
            if command == 5:
                self.scene = "route"
                self.pos[:] = list(self.SCENES["route"][2])
                self.meteor_phase = 1
                self.show_toast("训练结束。青梅：流星坠向北方的山洞！", 3)
            return
        if command in (3, 4):
            self.move_cursor = (self.move_cursor + (1 if command == 4 else -1)) % 4
        elif command in (1, 2):
            self.move_cursor = (self.move_cursor + (1 if command == 2 else -1)) % 4
        elif command == 5:
            self.use_move(self.move_cursor)

    def use_move(self, move):
        light_power = 0.5 + (self.light or 512) / 1023.0
        if move == 0:
            heal = round(18 * light_power)
            self.player_hp = min(100, self.player_hp + heal)
            self.show_toast(f"光合作用恢复了 {heal} 点体力。", 2)
        elif move == 1:
            damage = round(45 * light_power)
            self.enemy_hp = max(0, self.enemy_hp - damage)
            self.show_toast(f"日光束造成 {damage} 点伤害。", 2)
        elif move == 2:
            if not self.heavy_ready:
                self.show_toast("重磅冲撞需要先由震动传感器触发。", 2)
                return
            damage = 28 + min(35, self.vibration_count * 4)
            self.enemy_hp = max(0, self.enemy_hp - damage)
            self.heavy_ready = False
            self.show_toast(f"重磅冲撞造成 {damage} 点伤害！", 2)
        else:
            temp = self.temperature if self.temperature is not None else 20
            kind = "火" if temp > 30 else ("冰" if temp < 10 else "一般")
            damage = 38 if temp > 30 or temp < 10 else 25
            self.enemy_hp = max(0, self.enemy_hp - damage)
            self.show_toast(f"气象球（{kind}）造成 {damage} 点伤害。", 2)
        if self.enemy_hp <= 0:
            self.battle_won = True
            self.show_toast("战斗胜利！按 Enter 前往 1 号道路。", 3)
            return
        self.player_hp = max(0, self.player_hp - 8)
        if self.player_hp <= 0:
            self.show_toast("体力耗尽，按 R 重新开始。", 3)

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
        order = ["home", "friend", "battle", "route", "cave1", "cave2", "cave3", "ending"]
        self.scene = order[(order.index(self.scene) + 1) % len(order)]
        if self.scene in self.SCENES:
            self.pos[:] = list(self.SCENES[self.scene][2])

    def reset(self):
        self.scene, self.pos = "home", list(self.SCENES["home"][2])
        self.father_done = self.friend_met = self.battle_won = False
        self.rock_broken = False
        self.dialogue = []
        self.dialogue_index = 0
        self.meteor_phase = 0
        self.player_hp, self.enemy_hp = 100, 100
        self.show_toast("回到父亲的家。靠近左上角父亲并按 Enter。", 3)

    def show_toast(self, text, seconds=2):
        self.toast, self.toast_until = text, time.monotonic() + seconds

    def draw(self):
        if self.scene == "battle":
            self.draw_battle()
        elif self.scene == "ending":
            self.draw_ending()
        else:
            self.draw_map()
        self.draw_sidebar()
        if self.dialogue:
            self.draw_dialogue(self.dialogue[self.dialogue_index])
        elif self.toast and time.monotonic() < self.toast_until:
            self.draw_toast(self.toast)
        pygame.display.flip()

    def draw_map(self):
        bg = self.backgrounds.get(self.scene)
        outdoor = self.outdoor_maps.get(self.scene)
        if outdoor and outdoor["layers"].get("lower"):
            # Draw the map at native tile proportions.  Pixel-art layers use
            # nearest-neighbour scaling so the 32px tiles stay crisp.
            target = pygame.Rect(0, 0, PLAY_W, HEIGHT)
            self.map_rect = self.blit_fit(outdoor["layers"]["lower"], target, (91, 125, 75))
            for layer_name in ("current",):
                layer = outdoor["layers"].get(layer_name)
                if layer:
                    self.blit_layer(layer, self.map_rect)
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
        if self.scene == "home":
            self.draw_npc_at("home", self.player, "父亲")
        elif self.scene == "friend":
            self.draw_npc_at("friend", self.friend, "青梅")
        elif self.scene == "route":
            self.screen.blit(self.font.render("流星坠落方向 ↑", True, (255, 245, 180)), (30, 30))
            if self.meteor_phase:
                pygame.draw.line(self.screen, (255, 245, 160), (600, 25), (680, 190), 5)
                pygame.draw.circle(self.screen, (255, 239, 143), (600, 25), 13)
        elif self.scene == "cave3":
            self.draw_rock()
            if self.rock_broken and self.jirachi:
                self.screen.blit(self.jirachi, self.jirachi.get_rect(center=(650, 170)))
        x, y = self.tile_point(self.pos)
        self.draw_actor(x, y)
        # Upper layer is intentionally rendered last: tree crowns and roof
        # edges can cover the actor's head while walking underneath them.
        if outdoor:
            upper = outdoor["layers"].get("upper")
            if upper:
                self.blit_layer(upper, self.map_rect)
        self.screen.blit(self.title.render(self.SCENES[self.scene][3], True, (252, 247, 210)), (24, 22))

    def tile_point(self, pos):
        outdoor = self.outdoor_maps.get(self.scene)
        if outdoor and hasattr(self, "map_rect"):
            w, h = outdoor["size"]
            tile_w = self.map_rect.width / w
            tile_h = self.map_rect.height / h
            return (self.map_rect.left + (pos[0] + 0.5) * tile_w,
                    self.map_rect.top + (pos[1] + 0.5) * tile_h)
        grid = self.SCENES[self.scene][1]
        rect = getattr(self, "map_rect", pygame.Rect(0, 0, PLAY_W, HEIGHT))
        pad_x = min(58, rect.width * 0.08)
        pad_y = min(42, rect.height * 0.08)
        return (rect.left + pad_x + pos[0] * (rect.width - 2 * pad_x) / max(1, grid[0] - 1),
                rect.top + pad_y + pos[1] * (rect.height - 2 * pad_y) / max(1, grid[1] - 1))

    def draw_actor(self, x, y):
        if self.player:
            self.screen.blit(self.player, self.player.get_rect(center=(int(x), int(y))))
        else:
            pygame.draw.circle(self.screen, (180, 200, 180), (int(x), int(y)), 28)
        shadow = pygame.Rect(int(x - 25), int(y + 31), 50, 10)
        pygame.draw.ellipse(self.screen, (30, 45, 30), shadow)

    def draw_npc(self, x, y, image, label):
        if image:
            image = pygame.transform.smoothscale(image, (48, 48))
            self.screen.blit(image, image.get_rect(center=(x, y)))
        else:
            pygame.draw.circle(self.screen, (222, 216, 174), (x, y), 28)
        self.screen.blit(self.small.render(label, True, (30, 45, 30)), (x - 24, y + 42))

    def draw_npc_at(self, scene, image, label):
        x, y = self.tile_point(self.NPC_POS[scene])
        self.draw_npc(int(x), int(y), image, label)

    def draw_rock(self):
        if self.rock_broken:
            return
        x, y = self.tile_point(self.ROCK_POS)
        pygame.draw.polygon(self.screen, (93, 92, 103), ((x - 38, y + 34), (x - 29, y - 29), (x + 30, y - 37), (x + 48, y + 24), (x + 12, y + 42)))
        pygame.draw.line(self.screen, (185, 181, 191), (x - 12, y - 18), (x + 20, y + 15), 3)

    def draw_battle(self):
        if self.battle_background:
            self.blit_cover(self.battle_background, pygame.Rect(0, 0, PLAY_W, 460))
        else:
            self.screen.fill((43, 72, 65), (0, 0, PLAY_W, HEIGHT))
        pygame.draw.rect(self.screen, (121, 164, 112), (35, 70, 730, 390), border_radius=12)
        pygame.draw.ellipse(self.screen, (73, 112, 84), (55, 350, 370, 85))
        pygame.draw.ellipse(self.screen, (73, 112, 84), (430, 160, 730, 240))
        if self.ferro_battle:
            self.screen.blit(self.ferro_battle, self.ferro_battle.get_rect(center=(220, 315)))
        if self.jirachi:
            self.screen.blit(self.jirachi, self.jirachi.get_rect(center=(590, 190)))
        self.draw_hp((65, 85), "坚果哑铃", self.player_hp)
        self.draw_hp((470, 90), "训练对手", self.enemy_hp)
        self.screen.blit(self.title.render("训练战斗", True, (248, 243, 204)), (28, 24))
        labels = ["光合作用", "日光束", "重磅冲撞", "气象球"]
        pygame.draw.rect(self.screen, (22, 38, 36), (35, 490, 730, 185), border_radius=10)
        for i, label in enumerate(labels):
            col, row = i % 2, i // 2
            box = pygame.Rect(55 + col * 350, 510 + row * 65, 320, 52)
            color = (187, 153, 75) if i == self.move_cursor else (73, 105, 88)
            pygame.draw.rect(self.screen, color, box, border_radius=6)
            suffix = " *" if i == 2 and self.heavy_ready else ""
            self.screen.blit(self.font.render(label + suffix, True, (245, 244, 213)), (box.x + 18, box.y + 12))

    def blit_cover(self, image, target):
        """Scale a map or battle background without changing its aspect ratio."""
        iw, ih = image.get_size()
        scale = max(target.width / iw, target.height / ih)
        size = (max(1, round(iw * scale)), max(1, round(ih * scale)))
        scaled = pygame.transform.smoothscale(image, size)
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
        scaled = pygame.transform.smoothscale(image, size)
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
        pygame.draw.rect(self.screen, (43, 51, 43), (x, y + 31, 270, 18), border_radius=9)
        pygame.draw.rect(self.screen, (218, 214, 112) if hp > 30 else (207, 92, 76), (x + 3, y + 34, max(0, 264 * hp / 100), 12), border_radius=6)
        self.screen.blit(self.small.render(f"HP {hp}/100", True, (30, 50, 35)), (x + 180, y + 54))

    def draw_ending(self):
        self.screen.fill((42, 43, 77), (0, 0, PLAY_W, HEIGHT))
        pygame.draw.circle(self.screen, (245, 229, 158), (375, 235), 175)
        if self.jirachi:
            self.screen.blit(self.jirachi, self.jirachi.get_rect(center=(385, 235)))
        self.draw_actor(200, 420)
        self.screen.blit(self.title.render("流星的朋友", True, (255, 244, 186)), (30, 32))
        self.draw_dialogue("基拉祈：谢谢你把我唤醒。今后，我们一起寻找更多流星吧。")

    def draw_sidebar(self):
        pygame.draw.rect(self.screen, (21, 34, 30), (PLAY_W, 0, WIDTH - PLAY_W, HEIGHT))
        pygame.draw.line(self.screen, (111, 151, 103), (PLAY_W, 0), (PLAY_W, HEIGHT), 2)
        self.screen.blit(self.title.render("STC-B 状态", True, (235, 242, 214)), (830, 28))
        scene_name = "战斗" if self.scene == "battle" else (self.SCENES.get(self.scene, (None, None, None, "结局"))[3])
        light = "--" if self.light is None else str(self.light)
        temp = "--" if self.temperature is None else f"{self.temperature:.1f} °C"
        rows = [("主角", "坚果哑铃"), ("场景", scene_name), ("光照 ADC", light), ("温度", temp), ("震动次数", str(self.vibration_count)), ("岩石", "已击碎" if self.rock_broken else "未击碎")]
        y = 105
        for label, value in rows:
            self.screen.blit(self.small.render(label, True, (158, 185, 158)), (830, y))
            self.screen.blit(self.font.render(value, True, (236, 241, 214)), (950, y - 4))
            y += 42
        pygame.draw.line(self.screen, (62, 92, 69), (830, y + 8), (1170, y + 8), 1)
        self.screen.blit(self.font.render("传感器效果", True, (235, 242, 214)), (830, y + 34))
        power = 0.5 + (self.light or 512) / 1023.0
        effects = [f"光合作用  +{round(18 * power)} HP", f"日光束    {round(45 * power)} 威力", "重磅冲撞  震动触发", "气象球    温度决定属性"]
        for i, text in enumerate(effects):
            self.screen.blit(self.small.render(text, True, (201, 216, 191)), (842, y + 75 + i * 29))
        controls = "导航键：移动/选择\n中心键：互动/确认\nK1：重开\nK2：取消\n导航键3：切换场景\n震动：重磅冲撞\nV：键盘模拟震动"
        self.draw_multiline(830, 555, controls, self.small, (145, 172, 148), 340)
        self.screen.blit(self.small.render(self.serial.status, True, (120, 150, 126)), (830, 685))

    def draw_dialogue(self, text):
        box = pygame.Rect(28, 585, PLAY_W - 56, 105)
        pygame.draw.rect(self.screen, (16, 27, 26), box, border_radius=9)
        pygame.draw.rect(self.screen, (169, 190, 126), box, 2, border_radius=9)
        self.draw_multiline(48, 605, text, self.font, (242, 245, 220), box.width - 40)

    def draw_toast(self, text):
        box = pygame.Rect(28, 520, min(730, 50 + self.font.size(text)[0]), 50)
        pygame.draw.rect(self.screen, (17, 29, 25), box, border_radius=8)
        pygame.draw.rect(self.screen, (212, 185, 101), box, 2, border_radius=8)
        self.screen.blit(self.small.render(text, True, (249, 238, 181)), (box.x + 14, box.y + 15))

    def draw_multiline(self, x, y, text, font, color, max_width):
        line, lines = "", []
        for paragraph in text.split("\n"):
            for char in paragraph:
                if line and font.size(line + char)[0] > max_width:
                    lines.append(line)
                    line = ""
                line += char
            lines.append(line)
            line = ""
        for i, value in enumerate(lines):
            self.screen.blit(font.render(value, True, color), (x, y + i * (font.get_height() + 3)))


if __name__ == "__main__":
    Game(sys.argv[1] if len(sys.argv) > 1 else None).run()

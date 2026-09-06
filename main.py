"""STC-B Pokemon prototype.

Keyboard controls mirror the board protocol so the prototype remains usable
without additional hardware.  With pyserial installed, pass a COM port to
connect the STC-B board (for example: python main.py COM3).
"""
from __future__ import annotations

import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

try:
    from PIL import Image, ImageTk  # Optional, improves image scaling.
except ImportError:
    Image = ImageTk = None

try:
    import serial  # Optional hardware connection.
except ImportError:
    serial = None


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"


class SerialBridge:
    def __init__(self, port: str | None, on_command):
        self.port = port
        self.on_command = on_command
        self.thread = None
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
            self.status = f"串口已连接：{self.port}"
        except Exception as exc:
            self.status = f"串口连接失败：{exc}"
            return

        def read_loop():
            sensor_type = None
            high = None
            while not self.stop.is_set():
                data = link.read(1)
                if not data:
                    continue
                value = data[0]
                if value in (0x40, 0x41):
                    sensor_type = value - 0x40
                    high = None
                elif sensor_type is not None:
                    if high is None:
                        high = value
                    else:
                        self.on_command(("sensor", sensor_type, (high << 8) | value))
                        sensor_type = None
                elif value == 0x09:
                    self.on_command(("vibration",))
                else:
                    self.on_command(("key", value))
            link.close()

        self.thread = threading.Thread(target=read_loop, daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()


class PokemonGame(tk.Tk):
    def __init__(self, port: str | None):
        super().__init__()
        self.title("STC-B 坚果哑铃实验世界")
        self.geometry("1000x700")
        self.minsize(820, 560)
        self.configure(bg="#17231e")
        self.page = "序章"
        self.hp = 100
        self.light = None
        self.temperature = None
        self.vibration_count = 0
        self.dialogue = [
            "大木博士：欢迎来到这片森林，坚果哑铃。",
            "大木博士：你的力量会回应光照、温度与震动。",
            "大木博士：先去左边区域找你的青梅竹马吧。",
            "提示：方向键移动，Enter 互动；传感器数据会实时更新。",
        ]
        self.dialogue_index = 0
        self.cursor = [4, 4]
        self.board = [[0] * 9 for _ in range(9)]
        self.sensor = SerialBridge(port, self.receive)
        self.sensor.start()
        self._build_ui()
        self.bind("<Key>", self.key_event)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.redraw)

    def _build_ui(self):
        header = tk.Frame(self, bg="#21352d", height=64)
        header.pack(fill="x")
        tk.Label(header, text="STC-B 坚果哑铃实验世界", fg="#e8f3df", bg="#21352d",
                 font=("Microsoft YaHei", 21, "bold")).pack(side="left", padx=22, pady=14)
        self.status = tk.Label(header, text=self.sensor.status, fg="#c4d6c0", bg="#21352d",
                               font=("Microsoft YaHei", 10))
        self.status.pack(side="right", padx=20)

        nav = tk.Frame(self, bg="#17231e")
        nav.pack(fill="x", padx=18, pady=(12, 4))
        self.buttons = {}
        for name in ("序章", "传感器", "训练战斗"):
            button = tk.Button(nav, text=name, command=lambda n=name: self.switch_page(n),
                               relief="flat", bd=0, padx=18, pady=7,
                               bg="#395a47", fg="white", activebackground="#5d8a68",
                               font=("Microsoft YaHei", 11))
            button.pack(side="left", padx=(0, 8))
            self.buttons[name] = button

        self.content = tk.Frame(self, bg="#17231e")
        self.content.pack(fill="both", expand=True, padx=18, pady=10)
        self.canvas = tk.Canvas(self.content, bg="#264936", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        side = tk.Frame(self.content, width=270, bg="#203128")
        side.pack(side="right", fill="y", padx=(12, 0))
        side.pack_propagate(False)
        tk.Label(side, text="状态", bg="#203128", fg="#e8f3df", font=("Microsoft YaHei", 15, "bold")).pack(anchor="w", padx=18, pady=(18, 12))
        self.state_text = tk.Label(side, justify="left", anchor="nw", bg="#203128", fg="#cbd9c7",
                                   font=("Microsoft YaHei", 11), wraplength=230)
        self.state_text.pack(fill="x", padx=18)
        tk.Label(side, text="招式实验", bg="#203128", fg="#e8f3df", font=("Microsoft YaHei", 13, "bold")).pack(anchor="w", padx=18, pady=(24, 8))
        self.move_text = tk.Label(side, justify="left", anchor="nw", bg="#203128", fg="#cbd9c7",
                                  font=("Microsoft YaHei", 10), wraplength=230)
        self.move_text.pack(fill="x", padx=18)
        self.switch_page("序章")

    def switch_page(self, page):
        self.page = page
        self.dialogue_index = 0
        for name, button in self.buttons.items():
            button.configure(bg="#5d8a68" if name == page else "#395a47")
        self.redraw()

    def receive(self, message):
        self.after(0, lambda: self._receive_ui(message))

    def _receive_ui(self, message):
        kind = message[0]
        if kind == "sensor":
            if message[1] == 0:
                self.light = message[2]
            else:
                self.temperature = self.convert_temperature(message[2])
        elif kind == "vibration":
            self.vibration_count += 1
        elif kind == "key":
            self.board_command(message[1])
        self.redraw()

    @staticmethod
    def convert_temperature(adc):
        adc = max(1, min(1022, adc))
        resistance = 10000.0 * adc / (1023.0 - adc)
        return 1.0 / (1.0 / 298.15 + __import__("math").log(resistance / 10000.0) / 3950.0) - 273.15

    def key_event(self, event):
        mapping = {"Up": 1, "Down": 2, "Left": 3, "Right": 4, "Return": 5,
                   "r": 6, "R": 6, "F1": 9, "F2": 8}
        if event.keysym in mapping:
            self.board_command(mapping[event.keysym])

    def board_command(self, command):
        if command == 9:
            self.switch_page({"序章": "传感器", "传感器": "训练战斗", "训练战斗": "序章"}[self.page])
        elif self.page == "序章":
            if command == 1: self.cursor[1] = max(0, self.cursor[1] - 1)
            if command == 2: self.cursor[1] = min(8, self.cursor[1] + 1)
            if command == 3: self.cursor[0] = max(0, self.cursor[0] - 1)
            if command == 4: self.cursor[0] = min(8, self.cursor[0] + 1)
            if command == 5: self.dialogue_index = min(len(self.dialogue) - 1, self.dialogue_index + 1)
        elif self.page == "训练战斗" and command == 5:
            self.hp = max(0, self.hp - 5)
        self.redraw()

    def redraw(self):
        self.status.configure(text=self.sensor.status)
        self.canvas.delete("all")
        if self.page == "序章": self.draw_prologue()
        elif self.page == "传感器": self.draw_sensors()
        else: self.draw_battle()
        light = "--" if self.light is None else str(self.light)
        temp = "--" if self.temperature is None else f"{self.temperature:.1f} °C"
        self.state_text.configure(text=f"主角：坚果哑铃\n生命：{self.hp}/100\n\n光照 ADC：{light}\n温度：{temp}\n震动次数：{self.vibration_count}")
        light_power = 1.0 if self.light is None else 0.5 + self.light / 1023.0
        impact = 1 + min(4, self.vibration_count)
        self.move_text.configure(text=f"光合作用\n回血：{round(20 * light_power)}\n\n日光束\n威力：{round(60 * light_power)}\n\n重磅冲撞\n威力：{impact * 20}\n\n气象球\n温度决定天气形态")

    def draw_prologue(self):
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        for y in range(0, h, 36):
            self.canvas.create_rectangle(0, y, w, y + 36, fill="#315c3c" if (y // 36) % 2 else "#2a5036", outline="")
        for x, y in ((90, 80), (w - 110, 110), (w - 180, h - 130), (150, h - 150)):
            self.canvas.create_oval(x - 25, y - 25, x + 25, y + 25, fill="#1e3e2b", outline="")
            self.canvas.create_polygon(x, y - 60, x - 48, y + 12, x + 48, y + 12, fill="#44794d", outline="")
        px, py = 90 + self.cursor[0] * (w - 180) / 8, 90 + self.cursor[1] * (h - 180) / 8
        self.draw_ferrothorn(px, py)
        self.canvas.create_text(24, 24, anchor="nw", text="森林序章  |  方向键移动  Enter互动  F1切换页面",
                                fill="#f2f5dd", font=("Microsoft YaHei", 13, "bold"))
        self.canvas.create_rectangle(26, h - 115, w - 26, h - 25, fill="#17231e", outline="#91b78e", width=2)
        self.canvas.create_text(45, h - 98, anchor="nw", text=self.dialogue[self.dialogue_index],
                                fill="#f0f5e9", font=("Microsoft YaHei", 14), width=w - 90)

    def draw_ferrothorn(self, x, y):
        path = ASSETS / "FERROTHORN_STC.png"
        if path.exists() and ImageTk:
            try:
                image = Image.open(path).resize((72, 72))
                self._ferro_image = ImageTk.PhotoImage(image)
                self.canvas.create_image(x, y, image=self._ferro_image)
                return
            except Exception:
                pass
        self.canvas.create_oval(x - 28, y - 28, x + 28, y + 28, fill="#bcc9bd", outline="#152218", width=3)
        self.canvas.create_text(x, y, text="草钢", fill="#152218", font=("Microsoft YaHei", 10, "bold"))

    def draw_sensors(self):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.canvas.create_text(30, 28, anchor="nw", text="环境测量", fill="#edf6e8", font=("Microsoft YaHei", 22, "bold"))
        self.canvas.create_text(30, 75, anchor="nw", text="数据来自 STC-B 光敏/温度/震动传感器；没有连接时可用键盘 F2 模拟战斗页。",
                                fill="#c9dbc9", font=("Microsoft YaHei", 11))
        self.chart(45, 140, w - 90, 180, "光照 ADC", self.light or 0, 1023, "#e5b95c")
        temp = self.temperature if self.temperature is not None else 0
        self.chart(45, 370, w - 90, 180, "温度 °C", temp, 50, "#e88372")

    def chart(self, x, y, w, h, title, value, maximum, color):
        self.canvas.create_rectangle(x, y, x + w, y + h, fill="#203a2b", outline="#527458", width=2)
        self.canvas.create_text(x + 14, y + 12, anchor="nw", text=title, fill="#e5f1df", font=("Microsoft YaHei", 13, "bold"))
        ratio = max(0, min(1, float(value) / maximum))
        self.canvas.create_rectangle(x + 22, y + h - 38, x + 22 + (w - 44) * ratio, y + h - 18, fill=color, outline="")
        self.canvas.create_text(x + w - 16, y + 12, anchor="ne", text=f"{value:.1f}" if isinstance(value, float) else str(value), fill=color, font=("Microsoft YaHei", 14, "bold"))

    def draw_battle(self):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.canvas.create_text(30, 28, anchor="nw", text="训练战斗", fill="#edf6e8", font=("Microsoft YaHei", 22, "bold"))
        self.canvas.create_text(30, 72, anchor="nw", text="传感器联动招式演示：Enter 使用日光束，震动会增强重磅冲撞。R 重开。",
                                fill="#c9dbc9", font=("Microsoft YaHei", 11))
        cx, cy = w * .36, h * .50
        self.draw_ferrothorn(cx, cy)
        self.canvas.create_text(cx, cy + 60, text="坚果哑铃", fill="#f0f5e9", font=("Microsoft YaHei", 14, "bold"))
        self.canvas.create_rectangle(w * .62, h * .35, w * .9, h * .58, fill="#3a2930", outline="#a36b72", width=2)
        self.canvas.create_text(w * .76, h * .44, text="训练木桩", fill="#f0e7da", font=("Microsoft YaHei", 16, "bold"))
        self.canvas.create_text(w * .76, h * .52, text=f"目标 HP  {self.hp}", fill="#eaa4a4", font=("Microsoft YaHei", 12))

    def on_close(self):
        self.sensor.close()
        self.destroy()


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else None
    PokemonGame(port).mainloop()

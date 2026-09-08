"""Pygame-only STC-B serial acquisition monitor.

This program deliberately performs no game, temperature, damage, or sensor
calculation. It displays the raw two-byte ADC values and raw event bytes sent
by the firmware. Run it with ``python sensor_monitor.py COM3``.
"""

from __future__ import annotations

import collections
import queue
import sys
import threading
import time
from dataclasses import dataclass

import pygame

try:
    import serial
except ImportError:  # pragma: no cover - shown in the UI when unavailable
    serial = None


BAUDRATE = 9600
WIDTH, HEIGHT = 960, 640
BACKGROUND = (24, 31, 38)
PANEL = (36, 47, 57)
TEXT = (231, 238, 242)
MUTED = (161, 177, 187)
ACCENT = (95, 190, 220)
ORANGE = (239, 180, 91)
GREEN = (112, 205, 139)


@dataclass(frozen=True)
class RawEvent:
    kind: str
    value: int | None = None
    raw: bytes = b""
    timestamp: float = 0.0


class ProtocolParser:
    """Parse the fixed STC-B protocol without transforming sensor values."""

    def __init__(self):
        self.sensor_marker: int | None = None
        self.high: int | None = None

    def feed(self, data: bytes) -> list[RawEvent]:
        events: list[RawEvent] = []
        now = time.time()
        for value in data:
            if value in (0x40, 0x41):
                self.sensor_marker = value
                self.high = None
                continue
            if self.sensor_marker is not None:
                if self.high is None:
                    self.high = value
                    continue
                raw_value = (self.high << 8) | value
                kind = "light_raw_adc" if self.sensor_marker == 0x40 else "temperature_raw_adc"
                events.append(RawEvent(kind, raw_value, bytes((self.sensor_marker, self.high, value)), now))
                self.sensor_marker = None
                self.high = None
                continue
            if value == 0x09:
                events.append(RawEvent("vibration", None, bytes((value,)), now))
            else:
                events.append(RawEvent("key", value, bytes((value,)), now))
        return events


class SerialReader:
    def __init__(self, port: str | None, events: queue.Queue[RawEvent | tuple[str, str]]):
        self.port = port
        self.events = events
        self.stop = threading.Event()
        self.parser = ProtocolParser()
        self.status = "键盘演示模式（未打开串口）" if not port else "正在连接..."
        self._link = None

    def start(self) -> None:
        if not self.port:
            return
        if serial is None:
            self.status = "未安装 pyserial"
            return
        try:
            self._link = serial.Serial(self.port, BAUDRATE, timeout=0.2)
        except Exception as exc:  # pragma: no cover - depends on local COM state
            self.status = f"串口打开失败：{exc}"
            return
        self.status = f"已连接 {self.port} @ {BAUDRATE} baud"
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self) -> None:
        while not self.stop.is_set() and self._link is not None:
            data = self._link.read(64)
            if data:
                for event in self.parser.feed(data):
                    self.events.put(event)

    def close(self) -> None:
        self.stop.set()
        if self._link is not None:
            self._link.close()


class SensorMonitor:
    def __init__(self, port: str | None):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("STC-B 原始串口数据采集")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Microsoft YaHei", 22)
        self.small = pygame.font.SysFont("Microsoft YaHei", 16)
        self.title = pygame.font.SysFont("Microsoft YaHei", 30, bold=True)
        self.events: queue.Queue[RawEvent | tuple[str, str]] = queue.Queue()
        self.reader = SerialReader(port, self.events)
        self.reader.start()
        self.running = True
        self.light_raw: int | None = None
        self.temperature_raw: int | None = None
        self.vibration_count = 0
        self.last_key: int | None = None
        self.last_raw = ""
        self.log: collections.deque[str] = collections.deque(maxlen=12)

    def add_log(self, text: str) -> None:
        self.log.appendleft(time.strftime("%H:%M:%S ") + text)

    def inject_demo(self, event: RawEvent) -> None:
        """Keyboard-only raw packet demo; no values are converted."""
        self.events.put(event)

    def poll_events(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            if isinstance(event, tuple):
                self.add_log(event[1])
                continue
            self.last_raw = " ".join(f"{byte:02X}" for byte in event.raw)
            if event.kind == "light_raw_adc":
                self.light_raw = event.value
                self.add_log(f"光照原始 ADC = {event.value}   [{self.last_raw}]")
            elif event.kind == "temperature_raw_adc":
                self.temperature_raw = event.value
                self.add_log(f"温度原始 ADC = {event.value}   [{self.last_raw}]")
            elif event.kind == "vibration":
                self.vibration_count += 1
                self.add_log(f"震动事件 0x09   [{self.last_raw}]")
            else:
                self.last_key = event.value
                self.add_log(f"按键事件 0x{event.value:02X}   [{self.last_raw}]")

    def draw_value(self, rect: pygame.Rect, title: str, value: int | None, color: tuple[int, int, int], note: str) -> None:
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=8)
        pygame.draw.rect(self.screen, color, rect, width=2, border_radius=8)
        self.screen.blit(self.font.render(title, True, TEXT), (rect.x + 18, rect.y + 16))
        shown = "--" if value is None else str(value)
        self.screen.blit(self.title.render(shown, True, color), (rect.x + 18, rect.y + 57))
        self.screen.blit(self.small.render(note, True, MUTED), (rect.x + 18, rect.bottom - 32))

    def draw(self) -> None:
        self.screen.fill(BACKGROUND)
        self.screen.blit(self.title.render("STC-B 原始串口采集", True, TEXT), (28, 22))
        self.screen.blit(self.small.render(self.reader.status, True, GREEN if self.reader._link else ORANGE), (30, 66))
        self.screen.blit(self.small.render("不换算、不套公式：显示固件直接发送的原始数据", True, MUTED), (30, 92))
        self.draw_value(pygame.Rect(28, 130, 276, 145), "光照传感器", self.light_raw, ACCENT, "原始 ADC，范围由固件决定")
        self.draw_value(pygame.Rect(322, 130, 276, 145), "温度传感器", self.temperature_raw, ORANGE, "原始 ADC，不转换为 °C")
        self.draw_value(pygame.Rect(616, 130, 276, 145), "震动事件", self.vibration_count, GREEN, "收到 0x09 的累计次数")
        pygame.draw.rect(self.screen, PANEL, (28, 300, 864, 300), border_radius=8)
        self.screen.blit(self.font.render("原始事件记录", True, TEXT), (48, 318))
        y = 360
        for line in self.log:
            self.screen.blit(self.small.render(line, True, MUTED), (48, y))
            y += 19
        help_text = "COM3 启动示例：python sensor_monitor.py COM3    无串口时：L 光照 / T 温度 / V 震动 / Esc 退出"
        self.screen.blit(self.small.render(help_text, True, MUTED), (28, HEIGHT - 28))
        pygame.display.flip()

    def run(self) -> None:
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_l:
                        self.inject_demo(RawEvent("light_raw_adc", 512, bytes((0x40, 0x02, 0x00)), time.time()))
                    elif event.key == pygame.K_t:
                        self.inject_demo(RawEvent("temperature_raw_adc", 300, bytes((0x41, 0x01, 0x2C)), time.time()))
                    elif event.key == pygame.K_v:
                        self.inject_demo(RawEvent("vibration", raw=bytes((0x09,)), timestamp=time.time()))
            self.poll_events()
            self.draw()
            self.clock.tick(60)
        self.reader.close()
        pygame.quit()


if __name__ == "__main__":
    SensorMonitor(sys.argv[1] if len(sys.argv) > 1 else None).run()

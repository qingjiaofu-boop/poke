"""Visual editor for map-triggered dialogue and battle event sequences."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from event_system import (  # noqa: E402
    ASSETS,
    EVENTS_PATH,
    ICON_DIR,
    MAPS_PATH,
    PRELOAD_DIR,
    load_event_document,
    map_sizes,
    save_event_document,
    unique_event_id,
)


LOGICAL_SIZE = (480, 320)
TILE_SIZE = 32
PREVIEW_INTERVAL_MS = 38
ZOOMS = (0.25, 0.5, 1.0)

SPEAKER_NAMES = {
    "aron_right.png": "可可多拉",
    "ferrothorn_left.png": "坚果哑铃",
    "grotle_right.png": "树林龟",
    "sableye_right.png": "勾魂眼",
    "zubat_right.png": "超音蝠",
    "ferroseed_left.png": "种子铁球",
    "jirachi_right.png": "基拉祈",
}


def _font(size: int):
    for path in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _fit_event_icon(path: Path, size: int = TILE_SIZE) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if image.width >= image.height * 2:
        image = image.crop((0, 0, image.height, image.height))
    bounds = image.getbbox()
    if not bounds:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    image = image.crop(bounds)
    scale = min((size - 4) / image.width, (size - 4) / image.height)
    image = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.NEAREST,
    )
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.alpha_composite(image, ((size - image.width) // 2, size - image.height - 2))
    return result


class EventEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("STC-B 地图剧情事件编辑器")
        self.geometry("1460x900")
        self.minsize(1180, 760)

        self.document = load_event_document()
        self.events = self.document["events"]
        self.sizes = map_sizes()
        self.preloads = sorted(path.name for path in PRELOAD_DIR.glob("*.png"))
        self.icons = sorted(path.name for path in ICON_DIR.glob("*.png"))
        self.map_specs = self._load_map_specs()
        self.map_cache: dict[str, Image.Image] = {}
        self.icon_cache: dict[str, Image.Image] = {}
        self.selected_event: int | None = None
        self.selected_step: int | None = None
        self.map_photo = None
        self.preview_photo = None
        self.preview_job = None
        self.preview_chars = 0
        self.dirty = False

        self.event_name = tk.StringVar()
        self.event_map = tk.StringVar(value="world")
        self.event_x = tk.IntVar(value=0)
        self.event_y = tk.IntVar(value=0)
        self.event_icon = tk.StringVar(value=self.icons[0] if self.icons else "")
        self.event_once = tk.BooleanVar(value=True)
        self.zoom = tk.DoubleVar(value=0.5)
        self.step_type = tk.StringVar(value="dialogue")
        default_preload = "no_portrait_bottom.png"
        self.step_preload = tk.StringVar(
            value=default_preload if default_preload in self.preloads
            else (self.preloads[0] if self.preloads else "")
        )
        self.step_speaker = tk.StringVar()
        self.battle_id = tk.StringVar(value="placeholder")
        self.status = tk.StringVar(value=f"事件文件：{EVENTS_PATH}")

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_event_list()
        if self.events:
            self.event_list.selection_set(0)
            self._select_event()
        else:
            self._new_event()

    @staticmethod
    def _load_map_specs() -> dict:
        import json

        try:
            return json.loads(MAPS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}

    def _build(self):
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="新建事件", command=self._new_event).pack(side="left")
        ttk.Button(toolbar, text="删除事件", command=self._delete_event).pack(side="left", padx=5)
        ttk.Button(toolbar, text="应用当前修改", command=self._apply_event_form).pack(side="left", padx=5)
        ttk.Button(toolbar, text="保存全部 JSON", command=self._save).pack(side="left", padx=12)
        ttk.Label(toolbar, textvariable=self.status).pack(side="right")

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        sidebar = ttk.Frame(main, width=250)
        work = ttk.Frame(main)
        main.add(sidebar, weight=0)
        main.add(work, weight=1)

        ttk.Label(sidebar, text="地图事件").pack(anchor="w")
        event_wrap = ttk.Frame(sidebar)
        event_wrap.pack(fill="both", expand=True, pady=(4, 8))
        self.event_list = tk.Listbox(event_wrap, width=31, exportselection=False)
        event_scroll = ttk.Scrollbar(event_wrap, orient="vertical", command=self.event_list.yview)
        self.event_list.configure(yscrollcommand=event_scroll.set)
        self.event_list.pack(side="left", fill="both", expand=True)
        event_scroll.pack(side="right", fill="y")
        self.event_list.bind("<<ListboxSelect>>", lambda _event: self._select_event())

        help_text = (
            "使用方法\n"
            "1. 新建或选择事件\n"
            "2. 在地图上点击触发格\n"
            "3. 选择 32x32 地图图标\n"
            "4. 按顺序添加对白/战斗步骤\n"
            "5. 保存后重新启动游戏\n\n"
            "对白预览会自动逐字播放。战斗步骤目前调用现有训练战，作为后续战斗配置的占位入口。"
        )
        ttk.Label(sidebar, text=help_text, wraplength=225, justify="left").pack(fill="x")

        meta = ttk.LabelFrame(work, text="事件触发设置", padding=7)
        meta.pack(fill="x")
        ttk.Label(meta, text="名称").grid(row=0, column=0, sticky="w")
        ttk.Entry(meta, textvariable=self.event_name, width=24).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(meta, text="地图").grid(row=0, column=2, sticky="w", padx=(10, 0))
        map_box = ttk.Combobox(meta, textvariable=self.event_map, values=sorted(self.sizes), state="readonly", width=18)
        map_box.grid(row=0, column=3, sticky="ew", padx=4)
        map_box.bind("<<ComboboxSelected>>", lambda _event: self._map_changed())
        ttk.Label(meta, text="X").grid(row=0, column=4, sticky="e")
        ttk.Spinbox(meta, textvariable=self.event_x, from_=0, to=999, width=5, command=self._coordinates_changed).grid(row=0, column=5)
        ttk.Label(meta, text="Y").grid(row=0, column=6, sticky="e")
        ttk.Spinbox(meta, textvariable=self.event_y, from_=0, to=999, width=5, command=self._coordinates_changed).grid(row=0, column=7)
        ttk.Label(meta, text="图标").grid(row=1, column=0, sticky="w", pady=(7, 0))
        icon_box = ttk.Combobox(meta, textvariable=self.event_icon, values=self.icons, state="readonly", width=24)
        icon_box.grid(row=1, column=1, columnspan=2, sticky="ew", padx=4, pady=(7, 0))
        icon_box.bind("<<ComboboxSelected>>", lambda _event: self._draw_map())
        ttk.Checkbutton(meta, text="单次游玩只触发一次", variable=self.event_once).grid(row=1, column=3, columnspan=2, sticky="w", padx=4, pady=(7, 0))
        ttk.Label(meta, text="缩放").grid(row=1, column=5, sticky="e", pady=(7, 0))
        zoom_box = ttk.Combobox(meta, textvariable=self.zoom, values=ZOOMS, state="readonly", width=6)
        zoom_box.grid(row=1, column=6, sticky="w", pady=(7, 0))
        zoom_box.bind("<<ComboboxSelected>>", lambda _event: self._draw_map())
        ttk.Label(meta, text="点击地图可设置触发格").grid(row=1, column=7, sticky="e", pady=(7, 0))
        meta.columnconfigure(1, weight=1)
        meta.columnconfigure(3, weight=1)

        content = ttk.Panedwindow(work, orient="horizontal")
        content.pack(fill="both", expand=True, pady=(7, 0))
        map_panel = ttk.LabelFrame(content, text="地图与事件触发图标", padding=4)
        sequence_panel = ttk.Frame(content)
        content.add(map_panel, weight=3)
        content.add(sequence_panel, weight=2)

        canvas_wrap = ttk.Frame(map_panel)
        canvas_wrap.pack(fill="both", expand=True)
        self.map_canvas = tk.Canvas(canvas_wrap, bg="#202622", highlightthickness=0)
        sx = ttk.Scrollbar(canvas_wrap, orient="horizontal", command=self.map_canvas.xview)
        sy = ttk.Scrollbar(canvas_wrap, orient="vertical", command=self.map_canvas.yview)
        self.map_canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.map_canvas.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        canvas_wrap.rowconfigure(0, weight=1)
        canvas_wrap.columnconfigure(0, weight=1)
        self.map_canvas.bind("<Button-1>", self._place_on_map)

        steps_box = ttk.LabelFrame(sequence_panel, text="事件步骤序列", padding=5)
        steps_box.pack(fill="x")
        list_wrap = ttk.Frame(steps_box)
        list_wrap.pack(fill="x")
        self.step_list = tk.Listbox(list_wrap, height=7, exportselection=False)
        self.step_list.pack(side="left", fill="x", expand=True)
        self.step_list.bind("<<ListboxSelect>>", lambda _event: self._select_step())
        order = ttk.Frame(list_wrap)
        order.pack(side="left", padx=(5, 0))
        ttk.Button(order, text="上移", width=6, command=lambda: self._move_step(-1)).pack(pady=1)
        ttk.Button(order, text="下移", width=6, command=lambda: self._move_step(1)).pack(pady=1)
        ttk.Button(order, text="删除", width=6, command=self._delete_step).pack(pady=1)

        form = ttk.LabelFrame(sequence_panel, text="当前步骤", padding=6)
        form.pack(fill="x", pady=(7, 0))
        ttk.Label(form, text="类型").grid(row=0, column=0, sticky="w")
        type_box = ttk.Combobox(form, textvariable=self.step_type, values=("dialogue", "battle"), state="readonly", width=13)
        type_box.grid(row=0, column=1, sticky="w")
        type_box.bind("<<ComboboxSelected>>", lambda _event: self._step_type_changed())
        ttk.Label(form, text="预载图").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.preload_box = ttk.Combobox(form, textvariable=self.step_preload, values=self.preloads, state="readonly")
        self.preload_box.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(5, 0))
        self.preload_box.bind("<<ComboboxSelected>>", lambda _event: self._preload_changed())
        ttk.Label(form, text="说话者").grid(row=2, column=0, sticky="w", pady=(5, 0))
        self.speaker_entry = ttk.Entry(form, textvariable=self.step_speaker)
        self.speaker_entry.grid(row=2, column=1, columnspan=3, sticky="ew", pady=(5, 0))
        ttk.Label(form, text="对白内容").grid(row=3, column=0, sticky="nw", pady=(5, 0))
        self.text_editor = tk.Text(form, height=4, wrap="word", undo=True)
        self.text_editor.grid(row=3, column=1, columnspan=3, sticky="ew", pady=(5, 0))
        self.text_editor.bind("<KeyRelease>", lambda _event: self._restart_preview())
        ttk.Label(form, text="战斗 ID").grid(row=4, column=0, sticky="w", pady=(5, 0))
        self.battle_entry = ttk.Entry(form, textvariable=self.battle_id)
        self.battle_entry.grid(row=4, column=1, columnspan=3, sticky="ew", pady=(5, 0))
        buttons = ttk.Frame(form)
        buttons.grid(row=5, column=0, columnspan=4, sticky="e", pady=(7, 0))
        ttk.Button(buttons, text="新增步骤", command=self._add_step).pack(side="left", padx=3)
        ttk.Button(buttons, text="更新步骤", command=self._update_step).pack(side="left", padx=3)
        form.columnconfigure(1, weight=1)

        preview_frame = ttk.LabelFrame(sequence_panel, text="480x320 文字渐入预览", padding=4)
        preview_frame.pack(fill="both", expand=True, pady=(7, 0))
        self.preview_canvas = tk.Canvas(preview_frame, width=480, height=320, bg="black", highlightthickness=0)
        self.preview_canvas.pack(anchor="center", fill="none", expand=True)
        self.preview_canvas.bind("<Button-1>", lambda _event: self._restart_preview())
        ttk.Button(preview_frame, text="重新播放渐入", command=self._restart_preview).pack(pady=(3, 0))

        self._step_type_changed()

    def _current_event(self) -> dict | None:
        if self.selected_event is None or not (0 <= self.selected_event < len(self.events)):
            return None
        return self.events[self.selected_event]

    def _refresh_event_list(self):
        self.event_list.delete(0, "end")
        for event in self.events:
            x, y = event["position"]
            battle = " [战]" if any(step["type"] == "battle" for step in event["steps"]) else ""
            self.event_list.insert("end", f"{event['name']}  {event['map']} ({x},{y}){battle}")

    def _new_event(self):
        event_id = unique_event_id("new_event", (event["id"] for event in self.events))
        map_name = self.event_map.get() if self.event_map.get() in self.sizes else "world"
        self.events.append({
            "id": event_id,
            "name": "新事件",
            "map": map_name,
            "position": [0, 0],
            "icon": self.icons[0] if self.icons else "",
            "once": True,
            "steps": [],
        })
        self.dirty = True
        self._refresh_event_list()
        index = len(self.events) - 1
        self.event_list.selection_clear(0, "end")
        self.event_list.selection_set(index)
        self.event_list.see(index)
        self._select_event()

    def _delete_event(self):
        event = self._current_event()
        if event is None or not messagebox.askyesno("删除事件", f"确定删除“{event['name']}”吗？"):
            return
        del self.events[self.selected_event]
        self.selected_event = None
        self.selected_step = None
        self.dirty = True
        self._refresh_event_list()
        if self.events:
            self.event_list.selection_set(min(len(self.events) - 1, self.event_list.size() - 1))
            self._select_event()
        else:
            self._new_event()

    def _select_event(self):
        selection = self.event_list.curselection()
        if not selection:
            return
        next_index = selection[0]
        if self.selected_event is not None and self.selected_event != next_index:
            self._write_event_form(self.selected_event)
        self.selected_event = next_index
        event = self.events[self.selected_event]
        self.event_name.set(event["name"])
        self.event_map.set(event["map"])
        self.event_x.set(event["position"][0])
        self.event_y.set(event["position"][1])
        self.event_icon.set(event.get("icon", ""))
        self.event_once.set(event.get("once", True))
        self.selected_step = None
        self._refresh_steps()
        self._draw_map()
        self._restart_preview()

    def _write_event_form(self, index):
        if not (0 <= index < len(self.events)):
            return
        map_name = self.event_map.get()
        width, height = self.sizes.get(map_name, (1, 1))
        try:
            x = max(0, min(width - 1, self.event_x.get()))
            y = max(0, min(height - 1, self.event_y.get()))
        except tk.TclError:
            x, y = self.events[index]["position"]
        updated = {
            "name": self.event_name.get().strip() or "未命名事件",
            "map": map_name,
            "position": [x, y],
            "icon": self.event_icon.get(),
            "once": self.event_once.get(),
        }
        if any(self.events[index].get(key) != value for key, value in updated.items()):
            self.events[index].update(updated)
            self.dirty = True

    def _apply_event_form(self, notify=True):
        event = self._current_event()
        if event is None:
            return
        self._write_event_form(self.selected_event)
        x, y = event["position"]
        self.event_x.set(x)
        self.event_y.set(y)
        self._refresh_event_list()
        self.event_list.selection_set(self.selected_event)
        self._draw_map()
        if notify:
            self.status.set("已应用当前事件设置，尚未写入 JSON")

    def _map_changed(self):
        self.event_x.set(0)
        self.event_y.set(0)
        self._draw_map()
        self._restart_preview()

    def _coordinates_changed(self):
        self._draw_map()
        self._restart_preview()

    def _load_map_image(self, name: str) -> Image.Image:
        if name in self.map_cache:
            return self.map_cache[name]
        width, height = self.sizes.get(name, (15, 10))
        result = Image.new("RGBA", (width * TILE_SIZE, height * TILE_SIZE), (35, 45, 40, 255))
        spec = self.map_specs.get(name, {})
        layers = spec.get("layers", {})
        if name == "world":
            layers = {key: f"maps/world_{key}.png" for key in ("lower", "current", "upper")}
        for layer in ("lower", "current", "upper"):
            path = ASSETS / layers.get(layer, "")
            if path.is_file():
                with Image.open(path) as image:
                    image = image.convert("RGBA")
                    if image.size == result.size:
                        result.alpha_composite(image)
        self.map_cache[name] = result
        return result

    def _icon_image(self, name: str) -> Image.Image | None:
        if not name:
            return None
        if name not in self.icon_cache:
            path = ICON_DIR / Path(name).name
            if not path.is_file():
                return None
            self.icon_cache[name] = _fit_event_icon(path)
        return self.icon_cache[name]

    def _draw_map(self):
        name = self.event_map.get()
        if name not in self.sizes:
            return
        zoom = float(self.zoom.get())
        source = self._load_map_image(name)
        size = (max(1, round(source.width * zoom)), max(1, round(source.height * zoom)))
        image = source.resize(size, Image.Resampling.NEAREST)
        draw = ImageDraw.Draw(image, "RGBA")
        cell = TILE_SIZE * zoom
        for index, event in enumerate(self.events):
            if event["map"] != name:
                continue
            x, y = event["position"]
            icon = self._icon_image(event.get("icon", ""))
            if icon:
                icon_size = max(8, round(TILE_SIZE * zoom))
                image.alpha_composite(icon.resize((icon_size, icon_size), Image.Resampling.NEAREST), (round(x * cell), round(y * cell)))
            outline = (255, 231, 82, 255) if index == self.selected_event else (76, 224, 205, 220)
            draw.rectangle(
                (round(x * cell), round(y * cell), round((x + 1) * cell - 1), round((y + 1) * cell - 1)),
                outline=outline,
                width=max(1, round(2 * zoom)),
            )
            if any(step["type"] == "battle" for step in event["steps"]):
                badge = max(8, round(13 * zoom))
                draw.rectangle((round(x * cell), round(y * cell), round(x * cell) + badge, round(y * cell) + badge), fill=(185, 42, 42, 235))
                draw.text((round(x * cell) + 2, round(y * cell)), "B", fill="white", font=_font(max(7, round(10 * zoom))))
        self.map_photo = ImageTk.PhotoImage(image)
        self.map_canvas.delete("all")
        self.map_canvas.create_image(0, 0, anchor="nw", image=self.map_photo)
        self.map_canvas.configure(scrollregion=(0, 0, image.width, image.height))

    def _place_on_map(self, event):
        name = self.event_map.get()
        zoom = float(self.zoom.get())
        x = int(self.map_canvas.canvasx(event.x) // (TILE_SIZE * zoom))
        y = int(self.map_canvas.canvasy(event.y) // (TILE_SIZE * zoom))
        width, height = self.sizes.get(name, (0, 0))
        if 0 <= x < width and 0 <= y < height:
            self.event_x.set(x)
            self.event_y.set(y)
            self._apply_event_form(notify=False)
            self.status.set(f"触发格已设置为 {name} ({x}, {y})")
            self._restart_preview()

    def _refresh_steps(self):
        self.step_list.delete(0, "end")
        event = self._current_event()
        if event is None:
            return
        for index, step in enumerate(event["steps"], 1):
            if step["type"] == "battle":
                label = f"{index}. 下一步：进入战斗 [{step.get('battle_id', 'placeholder')}]"
            else:
                speaker = step.get("speaker") or "无署名"
                text = step.get("text", "").replace("\n", " ")
                label = f"{index}. 对话 {speaker}：{text[:22]}"
            self.step_list.insert("end", label)

    def _select_step(self):
        event = self._current_event()
        selection = self.step_list.curselection()
        if event is None or not selection:
            return
        self.selected_step = selection[0]
        step = event["steps"][self.selected_step]
        self.step_type.set(step["type"])
        if step["type"] == "dialogue":
            self.step_preload.set(step.get("preload", "no_portrait_bottom.png"))
            self.step_speaker.set(step.get("speaker", ""))
            self.text_editor.configure(state="normal")
            self.text_editor.delete("1.0", "end")
            self.text_editor.insert("1.0", step.get("text", ""))
        else:
            self.battle_id.set(step.get("battle_id", "placeholder"))
        self._step_type_changed()
        self._restart_preview()

    def _step_from_form(self) -> dict | None:
        if self.step_type.get() == "battle":
            return {"type": "battle", "battle_id": self.battle_id.get().strip() or "placeholder"}
        text = self.text_editor.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("缺少对白", "请先输入对白内容。")
            return None
        return {
            "type": "dialogue",
            "preload": self.step_preload.get(),
            "speaker": self.step_speaker.get().strip(),
            "text": text,
        }

    def _add_step(self):
        event = self._current_event()
        step = self._step_from_form()
        if event is None or step is None:
            return
        event["steps"].append(step)
        self.selected_step = len(event["steps"]) - 1
        self.dirty = True
        self._refresh_steps()
        self.step_list.selection_set(self.selected_step)
        self._refresh_event_list()
        self.event_list.selection_set(self.selected_event)
        self._draw_map()
        self._restart_preview()

    def _update_step(self):
        event = self._current_event()
        step = self._step_from_form()
        if event is None or step is None or self.selected_step is None:
            return
        event["steps"][self.selected_step] = step
        self.dirty = True
        self._refresh_steps()
        self.step_list.selection_set(self.selected_step)
        self._refresh_event_list()
        self.event_list.selection_set(self.selected_event)
        self._draw_map()
        self._restart_preview()

    def _delete_step(self):
        event = self._current_event()
        if event is None or self.selected_step is None:
            return
        del event["steps"][self.selected_step]
        self.selected_step = None
        self.dirty = True
        self._refresh_steps()
        self._refresh_event_list()
        self.event_list.selection_set(self.selected_event)
        self._draw_map()
        self._restart_preview()

    def _move_step(self, offset: int):
        event = self._current_event()
        if event is None or self.selected_step is None:
            return
        target = self.selected_step + offset
        if not 0 <= target < len(event["steps"]):
            return
        event["steps"][self.selected_step], event["steps"][target] = event["steps"][target], event["steps"][self.selected_step]
        self.selected_step = target
        self.dirty = True
        self._refresh_steps()
        self.step_list.selection_set(target)

    def _step_type_changed(self):
        dialogue = self.step_type.get() == "dialogue"
        self.preload_box.configure(state="readonly" if dialogue else "disabled")
        self.speaker_entry.configure(state="normal" if dialogue else "disabled")
        self.text_editor.configure(state="normal" if dialogue else "disabled")
        self.battle_entry.configure(state="disabled" if dialogue else "normal")
        self._restart_preview()

    def _preload_changed(self):
        suggested = SPEAKER_NAMES.get(self.step_preload.get())
        if suggested:
            self.step_speaker.set(suggested)
        self._restart_preview()

    def _preview_background(self) -> Image.Image:
        source = self._load_map_image(self.event_map.get())
        x, y = self.event_x.get(), self.event_y.get()
        center_x = (x + 0.5) * TILE_SIZE
        center_y = (y + 0.5) * TILE_SIZE
        left = max(0, min(max(0, source.width - 480), round(center_x - 240)))
        top = max(0, min(max(0, source.height - 320), round(center_y - 160)))
        crop = source.crop((left, top, min(source.width, left + 480), min(source.height, top + 320)))
        result = Image.new("RGBA", LOGICAL_SIZE, (30, 38, 34, 255))
        result.alpha_composite(crop, ((480 - crop.width) // 2, (320 - crop.height) // 2))
        return result

    def _restart_preview(self):
        if self.preview_job:
            self.after_cancel(self.preview_job)
            self.preview_job = None
        self.preview_chars = 0
        self._draw_preview()

    def _draw_preview(self):
        if self.step_type.get() == "battle":
            image = self._preview_background()
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((72, 118, 408, 202), 8, fill=(14, 22, 25, 235), outline=(220, 190, 92, 255), width=2)
            text = f"下一步：进入战斗\nBattle ID: {self.battle_id.get() or 'placeholder'}"
            draw.multiline_text((96, 139), text, font=_font(16), fill=(250, 245, 220, 255), spacing=8)
        else:
            image = self._preview_background()
            preload = PRELOAD_DIR / Path(self.step_preload.get()).name
            if preload.is_file():
                with Image.open(preload) as overlay:
                    image = Image.alpha_composite(image, overlay.convert("RGBA"))
            speaker = self.step_speaker.get().strip()
            body = self.text_editor.get("1.0", "end-1c") if self.text_editor.cget("state") == "normal" else ""
            full_text = f"{speaker}：{body}" if speaker else body
            visible = full_text[: self.preview_chars]
            center = self.step_preload.get() == "no_portrait_center.png"
            box = (82, 123, 398, 197) if center else (28, 241, 452, 294)
            self._draw_wrapped_text(image, visible, box, _font(14))
            if self.preview_chars < len(full_text):
                self.preview_chars += 1
                self.preview_job = self.after(PREVIEW_INTERVAL_MS, self._draw_preview)
        self.preview_photo = ImageTk.PhotoImage(image)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, anchor="nw", image=self.preview_photo)

    @staticmethod
    def _draw_wrapped_text(image: Image.Image, text: str, box: tuple[int, int, int, int], font):
        draw = ImageDraw.Draw(image)
        x0, y0, x1, y1 = box
        line = ""
        lines = []
        for char in text:
            if char == "\n":
                lines.append(line)
                line = ""
            elif draw.textlength(line + char, font=font) > x1 - x0:
                lines.append(line)
                line = char
            else:
                line += char
        lines.append(line)
        for index, value in enumerate(lines):
            y = y0 + index * 20
            if y + 20 > y1:
                break
            draw.text((x0, y), value, font=font, fill=(38, 48, 54, 255))

    def _save(self):
        self._apply_event_form(notify=False)
        try:
            self.document = save_event_document({"version": 1, "events": self.events})
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self.events = self.document["events"]
        self.dirty = False
        self._refresh_event_list()
        if self.selected_event is not None and self.selected_event < len(self.events):
            self.event_list.selection_set(self.selected_event)
        self.status.set(f"已保存：{EVENTS_PATH}")
        messagebox.showinfo("已保存", f"地图剧情事件已保存到：\n{EVENTS_PATH}")

    def _on_close(self):
        if self.dirty and not messagebox.askyesno("尚未保存", "当前事件有未保存修改，仍要退出吗？"):
            return
        if self.preview_job:
            self.after_cancel(self.preview_job)
        self.destroy()


if __name__ == "__main__":
    EventEditor().mainloop()

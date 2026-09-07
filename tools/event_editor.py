"""Small Tkinter event editor for the prototype's dialogue JSON.

Run from the project root: ``python tools/event_editor.py``.  It edits only
assets/story_events.json, so map data and game code are left untouched.
"""
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "assets" / "story_events.json"


class EventEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("STC-B 剧情事件编辑器")
        self.geometry("760x480")
        self.data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {"father": [], "friend": []}
        self.lines = []
        self.kind = tk.StringVar(value="father")
        self.speaker = tk.StringVar()
        self.text = tk.StringVar()
        self._build()
        self._load_kind()

    def _build(self):
        top = ttk.Frame(self); top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="事件：").pack(side="left")
        box = ttk.Combobox(top, textvariable=self.kind, values=("father", "friend"), state="readonly", width=14)
        box.pack(side="left"); box.bind("<<ComboboxSelected>>", lambda _e: self._load_kind())
        ttk.Button(top, text="保存 JSON", command=self._save).pack(side="right")
        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=10)
        self.listbox = tk.Listbox(body, width=34); self.listbox.pack(side="left", fill="y")
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._select())
        form = ttk.Frame(body); form.pack(side="left", fill="both", expand=True, padx=12)
        ttk.Label(form, text="说话者").pack(anchor="w"); ttk.Entry(form, textvariable=self.speaker).pack(fill="x", pady=(0, 12))
        ttk.Label(form, text="对白文本").pack(anchor="w"); ttk.Entry(form, textvariable=self.text).pack(fill="x")
        buttons = ttk.Frame(form); buttons.pack(anchor="e", pady=12)
        ttk.Button(buttons, text="新增", command=self._add).pack(side="left", padx=4)
        ttk.Button(buttons, text="更新", command=self._update).pack(side="left", padx=4)
        ttk.Button(buttons, text="删除", command=self._delete).pack(side="left", padx=4)
        ttk.Label(form, text="游戏会把每行显示成半屏立绘 + 下方对话框。", foreground="#666").pack(anchor="w", pady=16)

    def _load_kind(self):
        self.listbox.delete(0, "end"); self.lines = self.data.setdefault(self.kind.get(), [])
        for item in self.lines: self.listbox.insert("end", f"{item.get('speaker', '')}：{item.get('text', '')}")
        self.speaker.set(""); self.text.set("")

    def _select(self):
        sel = self.listbox.curselection()
        if sel:
            item = self.lines[sel[0]]; self.speaker.set(item.get("speaker", "")); self.text.set(item.get("text", ""))

    def _add(self):
        if self.text.get().strip(): self.lines.append({"speaker": self.speaker.get().strip(), "text": self.text.get().strip()}); self._load_kind(); self.listbox.selection_set("end")

    def _update(self):
        sel = self.listbox.curselection()
        if sel: self.lines[sel[0]] = {"speaker": self.speaker.get().strip(), "text": self.text.get().strip()}; self._load_kind(); self.listbox.selection_set(sel[0])

    def _delete(self):
        sel = self.listbox.curselection()
        if sel: del self.lines[sel[0]]; self._load_kind()

    def _save(self):
        PATH.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        messagebox.showinfo("已保存", f"对白事件已保存到：\n{PATH}")


if __name__ == "__main__":
    EventEditor().mainloop()

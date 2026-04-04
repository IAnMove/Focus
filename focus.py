from __future__ import annotations

import io
import calendar
import json
import math
import os
import platform
import re
import struct
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
import wave
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox


APP_NAME = "focus"

BG = "#ede8e0"
CARD = "#faf7f2"
CARD_HL = "#fff9f4"
SHADOW = "#cfc8be"
BORDER = "#ddd4c4"
TEXT = "#251b14"
MUTED = "#9a8a7e"
ACCENT = "#e85528"
SUCCESS = "#4e9145"
HIST_BG = "#e4d9cc"
PROG_BG = "#d8d0c5"
CURRENT_BG = "#efe2c0"
UNDO_BG = "#efe6d6"
BUTTON_FILL = "#3a2e26"
URL_RE = re.compile(r"(https?://[^\s]+)")

THEME_KEYS = [
    "BG",
    "CARD",
    "CARD_HL",
    "SHADOW",
    "BORDER",
    "TEXT",
    "MUTED",
    "ACCENT",
    "SUCCESS",
    "HIST_BG",
    "PROG_BG",
    "CURRENT_BG",
    "UNDO_BG",
    "BUTTON_FILL",
]

THEME_PRESETS = {
    "warm": {
        "BG": "#ede8e0",
        "CARD": "#faf7f2",
        "CARD_HL": "#fff9f4",
        "SHADOW": "#cfc8be",
        "BORDER": "#ddd4c4",
        "TEXT": "#251b14",
        "MUTED": "#9a8a7e",
        "ACCENT": "#e85528",
        "SUCCESS": "#4e9145",
        "HIST_BG": "#e4d9cc",
        "PROG_BG": "#d8d0c5",
        "CURRENT_BG": "#efe2c0",
        "UNDO_BG": "#efe6d6",
        "BUTTON_FILL": "#3a2e26",
    },
    "forest": {
        "BG": "#e8efe8",
        "CARD": "#f7fbf4",
        "CARD_HL": "#fcfffa",
        "SHADOW": "#c7d1c6",
        "BORDER": "#d4dfd0",
        "TEXT": "#1d2a20",
        "MUTED": "#728276",
        "ACCENT": "#557c57",
        "SUCCESS": "#3f8f61",
        "HIST_BG": "#dde7da",
        "PROG_BG": "#ced9ca",
        "CURRENT_BG": "#e5edd8",
        "UNDO_BG": "#e9efe1",
        "BUTTON_FILL": "#2f4332",
    },
    "ocean": {
        "BG": "#e8eef2",
        "CARD": "#f6fafc",
        "CARD_HL": "#ffffff",
        "SHADOW": "#c6d1d9",
        "BORDER": "#d6e0e7",
        "TEXT": "#1f2c36",
        "MUTED": "#6f7f8c",
        "ACCENT": "#3d7890",
        "SUCCESS": "#4b8f79",
        "HIST_BG": "#dde7ee",
        "PROG_BG": "#ccd8e0",
        "CURRENT_BG": "#dfeaf0",
        "UNDO_BG": "#e8eef4",
        "BUTTON_FILL": "#304957",
    },
    "rose": {
        "BG": "#f2e8e9",
        "CARD": "#fff8f8",
        "CARD_HL": "#fffdfd",
        "SHADOW": "#d9cacc",
        "BORDER": "#eadbdd",
        "TEXT": "#342125",
        "MUTED": "#8d7277",
        "ACCENT": "#b56474",
        "SUCCESS": "#75966f",
        "HIST_BG": "#ecdfe1",
        "PROG_BG": "#e1d3d6",
        "CURRENT_BG": "#f5dde1",
        "UNDO_BG": "#f2e7e9",
        "BUTTON_FILL": "#5b3942",
    },
}

TAB_PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}

DEFAULT_ITEMS = [
    {"text": "Define the next concrete task"},
    {"text": "Finish what is already in progress"},
    {"text": "Avoid switching context without reason"},
]


def now_stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def get_data_path() -> Path:
    system = platform.system().lower()
    base = Path.home() / "AppData" / "Roaming" / "focus" if system == "windows" else Path.home() / ".focus"
    base.mkdir(parents=True, exist_ok=True)
    return base / "checklist.json"


def make_item(
    item_id: int,
    text: str,
    *,
    created_at: str | None = None,
    current: bool = False,
    extra_info: str = "",
    due_date: str = "",
    tab: str = "General",
) -> dict:
    return {
        "id": item_id,
        "text": text,
        "done": False,
        "current": current,
        "created_at": created_at or now_stamp(),
        "completed_at": "",
        "extra_info": extra_info,
        "due_date": due_date,
        "tab": tab,
    }


def parse_time_prefix(value: str, pattern: str) -> bool:
    return bool(value) and value.startswith(pattern)


def is_valid_due_date(value: str) -> bool:
    if not value:
        return True
    for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            time.strptime(value, pattern)
            return True
        except ValueError:
            continue
    return False


def parse_created_at(value: str) -> float | None:
    if not value:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return time.mktime(time.strptime(value, pattern))
        except ValueError:
            continue
    return None


def parse_due_date(value: str) -> float | None:
    if not value:
        return None
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(value, pattern))
        except ValueError:
            continue
    return None


def format_remaining_time(due_date: str) -> str:
    due_ts = parse_due_date(due_date)
    if due_ts is None:
        return ""
    remaining = int(due_ts - time.time())
    if remaining <= 0:
        overdue = abs(remaining)
        days = overdue // 86400
        hours = (overdue % 86400) // 3600
        if days > 0:
            return f"overdue {days}d {hours}h"
        minutes = max(1, (overdue % 3600) // 60)
        return f"overdue {hours}h {minutes}m" if hours > 0 else f"overdue {minutes}m"
    days = remaining // 86400
    hours = (remaining % 86400) // 3600
    minutes = (remaining % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h left"
    if hours > 0:
        return f"{hours}h {minutes}m left"
    return f"{max(1, minutes)}m left"


def due_progress_ratio(created_at: str, due_date: str) -> float | None:
    due_ts = parse_due_date(due_date)
    created_ts = parse_created_at(created_at)
    if due_ts is None or created_ts is None or due_ts <= created_ts:
        return None
    ratio = (time.time() - created_ts) / (due_ts - created_ts)
    return max(0.0, min(1.0, ratio))


def normalize_hex(value: str) -> str | None:
    value = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.lower()
    return None


def apply_palette_values(palette: dict) -> None:
    global BG, CARD, CARD_HL, SHADOW, BORDER, TEXT, MUTED, ACCENT, SUCCESS, HIST_BG, PROG_BG, CURRENT_BG, UNDO_BG, BUTTON_FILL
    BG = palette["BG"]
    CARD = palette["CARD"]
    CARD_HL = palette["CARD_HL"]
    SHADOW = palette["SHADOW"]
    BORDER = palette["BORDER"]
    TEXT = palette["TEXT"]
    MUTED = palette["MUTED"]
    ACCENT = palette["ACCENT"]
    SUCCESS = palette["SUCCESS"]
    HIST_BG = palette["HIST_BG"]
    PROG_BG = palette["PROG_BG"]
    CURRENT_BG = palette["CURRENT_BG"]
    UNDO_BG = palette["UNDO_BG"]
    BUTTON_FILL = palette["BUTTON_FILL"]


def normalize_tab_name(value: str) -> str:
    return " ".join(value.strip().split())


def default_tabs() -> list[dict]:
    return [{"name": "General", "priority": "normal"}]


def parse_due_parts(value: str) -> tuple[int, int, int, int, int] | None:
    if not value:
        return None
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = time.strptime(value, pattern)
            return parsed.tm_year, parsed.tm_mon, parsed.tm_mday, parsed.tm_hour, parsed.tm_min
        except ValueError:
            continue
    return None


def _make_wav(tones: list[tuple[float, float]], volume: float = 0.32, sample_rate: int = 44100) -> bytes:
    samples: list[int] = []
    for freq, duration in tones:
        total = int(sample_rate * duration)
        for index in range(total):
            if freq == 0:
                samples.append(0)
                continue
            t = index / sample_rate
            envelope = min(t * 110, 1.0) * max(1.0 - (index / total) ** 0.55, 0.0)
            value = int(32767 * volume * envelope * math.sin(2 * math.pi * freq * t))
            samples.append(max(-32767, min(32767, value)))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buffer.getvalue()


IS_WINDOWS = platform.system() == "Windows"
CLICK_WAV = _make_wav([(1050, 0.035)], volume=0.16)
COMPLETE_WAV = _make_wav([(440, 0.08), (0, 0.02), (523, 0.09), (0, 0.02), (659, 0.14)], volume=0.34)
ADD_WAV = _make_wav([(620, 0.05)], volume=0.20)


def _play_wav(raw_wav: bytes) -> None:
    if not IS_WINDOWS:
        return
    try:
        import winsound

        winsound.PlaySound(raw_wav, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
    except Exception:
        pass


def play_click() -> None:
    threading.Thread(target=_play_wav, args=(CLICK_WAV,), daemon=True).start()


def play_complete() -> None:
    threading.Thread(target=_play_wav, args=(COMPLETE_WAV,), daemon=True).start()


def play_add() -> None:
    threading.Thread(target=_play_wav, args=(ADD_WAV,), daemon=True).start()


class PillButton(tk.Canvas):
    radius = 7

    def __init__(self, master: tk.Misc, text: str, command, *, padding_x: int = 30, font_size: int = 9) -> None:
        self._font_size = font_size
        self._font = tkfont.Font(family="Segoe UI", size=font_size, weight="bold")
        self._text = text
        self._command = command
        self._padding_x = padding_x
        self._color = BUTTON_FILL
        width = self._font.measure(text) + padding_x
        height = self._font.metrics("linespace") + 14
        try:
            bg = master.cget("bg")
        except tk.TclError:
            bg = BG
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0, borderwidth=0, cursor="hand2")
        self._draw()
        self.bind("<Enter>", lambda _event: self._recolor(ACCENT))
        self.bind("<Leave>", lambda _event: self._recolor(BUTTON_FILL))
        self.bind("<Button-1>", self._click)

    def _rounded(self, x1: int, y1: int, x2: int, y2: int, fill: str) -> None:
        r = self.radius
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        self.create_polygon(points, smooth=True, fill=fill, outline="")

    def _draw(self) -> None:
        self.delete("all")
        width = int(self.cget("width"))
        height = int(self.cget("height"))
        self._rounded(0, 0, width, height, self._color)
        self.create_text(width // 2, height // 2, text=self._text, fill=CARD, font=("Segoe UI", 9, "bold"))

    def _recolor(self, color: str) -> None:
        self._color = color
        self._draw()

    def set_text(self, text: str) -> None:
        self._text = text
        self.configure(width=self._font.measure(text) + self._padding_x)
        self._draw()

    def refresh_theme(self, font_size: int | None = None) -> None:
        if font_size is not None and font_size != self._font_size:
            self._font_size = font_size
            self._font = tkfont.Font(family="Segoe UI", size=font_size, weight="bold")
            self.configure(width=self._font.measure(self._text) + self._padding_x, height=self._font.metrics("linespace") + 14)
        try:
            self.configure(bg=self.master.cget("bg"))
        except tk.TclError:
            self.configure(bg=BG)
        self._color = BUTTON_FILL
        self._draw()

    def _click(self, _event: tk.Event) -> None:
        play_click()
        self._command()


class DueDatePicker(tk.Toplevel):
    def __init__(self, master: tk.Misc, initial_value: str, on_apply) -> None:
        super().__init__(master)
        self.on_apply = on_apply
        self.title("Due date")
        self.transient(master)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.configure(bg=BG)
        self.grab_set()

        parsed = parse_due_parts(initial_value)
        now = time.localtime()
        self.selected_year = parsed[0] if parsed else now.tm_year
        self.selected_month = parsed[1] if parsed else now.tm_mon
        self.selected_day = parsed[2] if parsed else now.tm_mday
        self.hour_var = tk.StringVar(value=f"{parsed[3]:02d}" if parsed else "00")
        self.minute_var = tk.StringVar(value=f"{parsed[4]:02d}" if parsed else "00")

        shell = tk.Frame(self, bg=BG, padx=14, pady=14)
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(0, weight=1)

        header = tk.Frame(shell, bg=BG)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        tk.Label(header, text="<", bg=BG, fg=ACCENT, font=("Segoe UI", 12, "bold"), cursor="hand2").grid(row=0, column=0, padx=(0, 10))
        tk.Label(header, text=">", bg=BG, fg=ACCENT, font=("Segoe UI", 12, "bold"), cursor="hand2").grid(row=0, column=2, padx=(10, 0))
        header.grid_slaves(row=0, column=0)[0].bind("<Button-1>", lambda _event: self.shift_month(-1))
        header.grid_slaves(row=0, column=2)[0].bind("<Button-1>", lambda _event: self.shift_month(1))

        self.month_label = tk.Label(header, text="", bg=BG, fg=TEXT, font=("Georgia", 13, "bold"))
        self.month_label.grid(row=0, column=1)

        self.calendar_frame = tk.Frame(shell, bg=BG)
        self.calendar_frame.grid(row=1, column=0, sticky="ew", pady=(10, 10))

        time_row = tk.Frame(shell, bg=BG)
        time_row.grid(row=2, column=0, sticky="w", pady=(0, 10))
        tk.Label(time_row, text="Time", bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        self.hour_spin = tk.Spinbox(time_row, from_=0, to=23, wrap=True, width=3, textvariable=self.hour_var, format="%02.0f", relief="flat")
        self.hour_spin.pack(side="left")
        tk.Label(time_row, text=":", bg=BG, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left", padx=4)
        self.minute_spin = tk.Spinbox(time_row, from_=0, to=59, wrap=True, width=3, textvariable=self.minute_var, format="%02.0f", relief="flat")
        self.minute_spin.pack(side="left")

        actions = tk.Frame(shell, bg=BG)
        actions.grid(row=3, column=0, sticky="e")
        PillButton(actions, "clear", self.clear_value, padding_x=24).pack(side="left", padx=(0, 8))
        PillButton(actions, "apply", self.apply_value, padding_x=24).pack(side="left")

        self.draw_calendar()
        self.bind("<Escape>", lambda _event: self.destroy())

    def shift_month(self, delta: int) -> None:
        month = self.selected_month + delta
        year = self.selected_year
        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1
        self.selected_year = year
        self.selected_month = month
        last_day = calendar.monthrange(year, month)[1]
        self.selected_day = min(self.selected_day, last_day)
        self.draw_calendar()

    def draw_calendar(self) -> None:
        for child in self.calendar_frame.winfo_children():
            child.destroy()
        self.month_label.configure(text=f"{calendar.month_name[self.selected_month]} {self.selected_year}")
        day_names = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        for column, name in enumerate(day_names):
            tk.Label(self.calendar_frame, text=name, bg=BG, fg=MUTED, font=("Segoe UI", 8, "bold"), width=3).grid(row=0, column=column, pady=(0, 6))
        for row, week in enumerate(calendar.monthcalendar(self.selected_year, self.selected_month), start=1):
            for column, day in enumerate(week):
                if day == 0:
                    tk.Label(self.calendar_frame, text="", bg=BG, width=3).grid(row=row, column=column, padx=2, pady=2)
                    continue
                is_selected = day == self.selected_day
                cell = tk.Label(
                    self.calendar_frame,
                    text=str(day),
                    bg="#f0ded4" if is_selected else CARD,
                    fg=ACCENT if is_selected else TEXT,
                    font=("Segoe UI", 9, "bold" if is_selected else "normal"),
                    width=3,
                    cursor="hand2",
                )
                cell.grid(row=row, column=column, padx=2, pady=2)
                cell.bind("<Button-1>", lambda _event, value=day: self.select_day(value))

    def select_day(self, day: int) -> None:
        self.selected_day = day
        self.draw_calendar()

    def clear_value(self) -> None:
        self.on_apply("")
        self.destroy()

    def apply_value(self) -> None:
        try:
            hour = max(0, min(23, int(self.hour_var.get() or "0")))
        except ValueError:
            hour = 0
        try:
            minute = max(0, min(59, int(self.minute_var.get() or "0")))
        except ValueError:
            minute = 0
        value = f"{self.selected_year:04d}-{self.selected_month:02d}-{self.selected_day:02d} {hour:02d}:{minute:02d}"
        self.on_apply(value)
        self.destroy()


class ChecklistItem(tk.Frame):
    anim_steps = [
        ("#f4a08a", "#fdf0ea", "checking...", "o"),
        ("#ec7055", "#fde8df", "checking...", "o"),
        ("#d4a060", "#fdeee0", "done", "v"),
        ("#9bc46a", "#f4f8e6", "done", "v"),
        ("#62ad55", "#eaf5e7", "saved!", "v"),
        (SUCCESS, "#e4f2e1", "completed", "v"),
    ]

    def __init__(self, master: tk.Misc, app: "FocusApp", item: dict) -> None:
        super().__init__(master, bg=SHADOW)
        self.app = app
        self.item = item
        self.hovered = False
        self.animating = False

        card_bg = CURRENT_BG if item.get("current") else CARD
        self.card = tk.Frame(self, bg=card_bg, highlightthickness=1, highlightbackground=BORDER)
        self.card.pack(fill="both", expand=True, padx=(0, 3), pady=(0, 3))
        self.card.grid_columnconfigure(1, weight=1)

        self.checkbox = tk.Label(self.card, text="o", fg=ACCENT, bg=card_bg, font=("Segoe UI", self.app.scaled(16), "bold"), cursor="hand2", width=2)
        self.checkbox.grid(row=0, column=0, padx=(10, 4), pady=14, sticky="n")
        self.checkbox.bind("<Button-1>", lambda _event: self.complete())

        center = tk.Frame(self.card, bg=card_bg)
        center.grid(row=0, column=1, sticky="ew", pady=12)
        center.grid_columnconfigure(0, weight=1)

        self.title_row = tk.Frame(center, bg=card_bg)
        self.title_row.grid(row=0, column=0, sticky="ew")
        self.title_row.grid_columnconfigure(0, weight=1)

        self.current_badge = tk.Label(self.title_row, text="◉", bg=card_bg, fg=ACCENT, font=("Segoe UI", self.app.scaled(9), "bold"))

        self.text = tk.Text(
            center,
            bg=card_bg,
            fg=TEXT,
            font=("Segoe UI", self.app.scaled(12)),
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            cursor="arrow",
            height=1,
            padx=0,
            pady=0,
        )
        self.text.grid(row=1, column=0, sticky="ew")
        self.text.bind("<Double-Button-1>", lambda _event: self.app.start_edit(self.item["id"]))
        self.text.bind("<Key>", lambda _event: "break")
        self.text.bind("<Button-1>", self._on_text_click, add="+")

        self.meta_label = tk.Label(center, text=self.meta_text(), bg=card_bg, fg=MUTED, font=("Segoe UI", self.app.scaled(8)))
        self.meta_label.grid(row=2, column=0, sticky="w", pady=(5, 0))

        self.progress = tk.Canvas(center, height=4, bg=card_bg, highlightthickness=0, borderwidth=0)
        self.progress.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        self.actions = tk.Frame(self.card, bg=card_bg)
        self.actions.grid(row=0, column=2, padx=(6, 10), pady=14, sticky="ne")

        self.current_btn = tk.Label(self.actions, text="◎", bg=card_bg, fg=MUTED, font=("Segoe UI", self.app.scaled(10), "bold"), cursor="hand2", width=2)
        self.current_btn.pack(side="left", padx=(0, 4))
        self.current_btn.bind("<Button-1>", lambda _event: self.app.toggle_current(self.item["id"]))

        self.edit_btn = tk.Label(self.actions, text="E", bg=card_bg, fg=MUTED, font=("Segoe UI", self.app.scaled(9), "bold"), cursor="hand2", width=2)
        self.edit_btn.pack(side="left", padx=(0, 4))
        self.edit_btn.bind("<Button-1>", lambda _event: self.app.start_edit(self.item["id"]))

        self.delete_btn = tk.Label(self.actions, text="x", bg=card_bg, fg=MUTED, font=("Segoe UI", self.app.scaled(11), "bold"), cursor="hand2", width=2)
        self.delete_btn.pack(side="left", padx=(0, 4))
        self.delete_btn.bind("<Button-1>", lambda _event: self.app.delete_item(self.item["id"]))

        self.drag_handle = tk.Label(self.actions, text="::", bg=card_bg, fg=MUTED, font=("Consolas", self.app.scaled(10), "bold"), cursor="fleur", width=2)
        self.drag_handle.pack(side="left")
        self.drag_handle.bind("<ButtonPress-1>", lambda event: self.app.start_drag(self.item["id"], event))
        self.drag_handle.bind("<B1-Motion>", self.app.drag_motion)
        self.drag_handle.bind("<ButtonRelease-1>", self.app.end_drag)

        for widget in (
            self,
            self.card,
            self.drag_handle,
            self.checkbox,
            center,
            self.title_row,
            self.text,
            self.meta_label,
            self.actions,
            self.current_btn,
            self.edit_btn,
            self.delete_btn,
        ):
            self._bind_hover(widget)
        self.refresh_content()

    def meta_text(self) -> str:
        created_at = self.item.get("created_at", "")
        due_date = self.item.get("due_date", "")
        tab_name = self.item.get("tab", "General")
        parts = []
        if tab_name:
            parts.append(tab_name.lower())
        if created_at:
            parts.append(f"added {created_at[:16]}")
        if due_date:
            remaining = format_remaining_time(due_date)
            parts.append(f"due {due_date}" + (f" ({remaining})" if remaining else ""))
        return "   ".join(parts)

    def _bind_hover(self, widget: tk.Misc) -> None:
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")

    def _base_bg(self) -> str:
        return CURRENT_BG if self.item.get("current") else CARD

    def refresh_content(self) -> None:
        base_bg = self._base_bg()
        self.card.configure(bg=base_bg)
        for widget in (self.drag_handle, self.checkbox, self.actions, self.current_btn, self.edit_btn, self.delete_btn, self.meta_label, self.title_row):
            widget.configure(bg=base_bg)
        self.text.configure(bg=base_bg)
        self.progress.configure(bg=base_bg)
        self.meta_label.configure(text=self.meta_text())
        self.current_btn.configure(text="◉" if self.item.get("current") else "◎", fg=ACCENT if self.item.get("current") else MUTED)
        if self.item.get("current"):
            self.current_badge.grid(row=0, column=1, sticky="e", padx=(8, 0))
        else:
            self.current_badge.grid_remove()
        self._render_text(self.item["text"])
        self._draw_progress()

    def _on_enter(self, _event: tk.Event) -> None:
        self.hovered = True
        if self.animating:
            return
        bg = CARD_HL if not self.item.get("current") else "#f4ead1"
        self.card.configure(highlightbackground=ACCENT, bg=bg)
        for widget in (self.drag_handle, self.checkbox, self.actions, self.current_btn, self.edit_btn, self.delete_btn, self.meta_label, self.title_row):
            widget.configure(bg=bg)
        self.text.configure(bg=bg)
        self.progress.configure(bg=bg)
        self.text.tag_configure("body", font=("Segoe UI", self.app.scaled(12), "bold"))
        self.checkbox.configure(text=".")

    def _on_leave(self, _event: tk.Event) -> None:
        self.after(8, self._sync_hover)

    def _sync_hover(self) -> None:
        pointer = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        inside = False
        widget = pointer
        while widget is not None:
            if widget == self:
                inside = True
                break
            widget = getattr(widget, "master", None)
        self.hovered = inside
        if inside or self.animating:
            return
        self.card.configure(highlightbackground=BORDER)
        self.refresh_content()
        self.text.tag_configure("body", font=("Segoe UI", self.app.scaled(12)))
        self.checkbox.configure(text="o")

    def set_dragging(self, enabled: bool) -> None:
        self.card.configure(highlightbackground=ACCENT if enabled else BORDER)
        self.drag_handle.configure(fg=ACCENT if enabled else MUTED)

    def update_wrap(self, width: int) -> None:
        self.text.configure(width=max(16, (max(140, width - 220) // 8)))
        self._render_text(self.item["text"])
        self._draw_progress()

    def complete(self) -> None:
        if self.animating:
            return
        self.animating = True
        play_complete()
        self._animate(0)

    def _animate(self, step: int) -> None:
        color, bg, text, tick = self.anim_steps[min(step, len(self.anim_steps) - 1)]
        self.card.configure(highlightbackground=color, bg=bg)
        for widget in (self.drag_handle, self.checkbox, self.actions, self.current_btn, self.edit_btn, self.delete_btn, self.meta_label, self.title_row):
            widget.configure(bg=bg)
        self.text.configure(bg=bg)
        self._render_text(text if step >= 2 else self.item["text"], color=color, clickable=step < 2, bold=True)
        self.checkbox.configure(text=tick, fg=color, bg=bg)
        if step < len(self.anim_steps) - 1:
            self.after(65, lambda: self._animate(step + 1))
        else:
            self.after(100, lambda: self.app.complete_item(self.item["id"]))

    def _render_text(self, text: str, *, color: str = TEXT, clickable: bool = True, bold: bool = False) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for tag in self.text.tag_names():
            self.text.tag_delete(tag)
        self.text.insert("1.0", text)
        self.text.tag_add("body", "1.0", "end")
        self.text.tag_configure("body", foreground=color, font=("Segoe UI", self.app.scaled(12), "bold" if bold else "normal"))
        if clickable:
            for index, match in enumerate(URL_RE.finditer(text)):
                tag = f"url_{index}"
                start = f"1.0+{match.start()}c"
                end = f"1.0+{match.end()}c"
                url = match.group(0)
                self.text.tag_add(tag, start, end)
                self.text.tag_configure(tag, foreground=ACCENT, underline=True)
                self.text.tag_bind(tag, "<Enter>", lambda _event: self.text.configure(cursor="hand2"))
                self.text.tag_bind(tag, "<Leave>", lambda _event: self.text.configure(cursor="arrow"))
                self.text.tag_bind(tag, "<Button-1>", lambda _event, value=url: self._open_url(value))
        lines = max(1, int(self.text.index("end-1c").split(".")[0]))
        self.text.configure(height=lines)
        self.text.edit_modified(False)

    def _draw_progress(self) -> None:
        self.progress.delete("all")
        due_date = self.item.get("due_date", "")
        created_at = self.item.get("created_at", "")
        ratio = due_progress_ratio(created_at, due_date)
        if ratio is None:
            self.progress.grid_remove()
            return
        self.progress.grid()
        self.progress.update_idletasks()
        width = max(20, self.progress.winfo_width())
        self.progress.create_rectangle(0, 0, width, 4, fill="#efe7d2", outline="")
        fill = max(3, int(width * ratio))
        self.progress.create_rectangle(0, 0, fill, 4, fill="#e9d48d", outline="")

    def _on_text_click(self, event: tk.Event) -> str | None:
        index = self.text.index(f"@{event.x},{event.y}")
        for tag in self.text.tag_names(index):
            if tag.startswith("url_"):
                return None
        return "break"

    def _open_url(self, value: str) -> str:
        webbrowser.open(value)
        return "break"


class HistoryItem(tk.Frame):
    def __init__(self, master: tk.Misc, app: "FocusApp", item: dict) -> None:
        super().__init__(master, bg=HIST_BG, padx=10, pady=8)
        self.app = app
        self.item = item
        self.grid_columnconfigure(0, weight=1)
        tk.Label(self, text=item.get("text", ""), bg=HIST_BG, fg=TEXT, anchor="w", justify="left", font=("Segoe UI", app.scaled(10)), wraplength=240).grid(row=0, column=0, sticky="ew")
        meta_parts = []
        if item.get("created_at", ""):
            meta_parts.append(f"added {item.get('created_at', '')[:16]}")
        if item.get("due_date", ""):
            meta_parts.append(f"due {item.get('due_date', '')}")
        if item.get("completed_at", ""):
            meta_parts.append(f"completed {item.get('completed_at', '')[:16]}")
        meta = "   ".join(meta_parts)
        tk.Label(self, text=meta, bg=HIST_BG, fg=MUTED, font=("Segoe UI", app.scaled(8))).grid(row=1, column=0, sticky="w", pady=(3, 0))
        restore = tk.Label(self, text="restore", bg=HIST_BG, fg=ACCENT, font=("Segoe UI", app.scaled(9), "bold"), cursor="hand2")
        restore.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        restore.bind("<Button-1>", lambda _event: self.app.restore_history_item(self.item["id"]))


class FocusApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("420x620")
        self.minsize(300, 260)
        self.attributes("-topmost", True)
        self.configure(bg=BG)

        self.data_path = get_data_path()
        self.items, self.history, self.settings = self.load_data()
        self.tabs = self.normalize_tabs(self.settings.get("tabs", default_tabs()))
        for item in self.items + self.history:
            self.ensure_tab_exists(item.get("tab", "General"))
        self.settings["tabs"] = self.tabs
        self.active_tab = "All"
        self.theme_name = self.settings.get("theme_name", "warm")
        self.custom_palette = self.settings.get("custom_palette", {}).copy() if isinstance(self.settings.get("custom_palette", {}), dict) else {}
        self.font_scale = float(self.settings.get("font_scale", 1.0))
        self.accessibility_mode = bool(self.settings.get("accessibility_mode", False))
        self.apply_theme(self.theme_name, persist=False)
        self.item_widgets: dict[int, ChecklistItem] = {}
        self.pending_completion: dict | None = None
        self.pending_timer: str | None = None
        self.drag_item_id: int | None = None
        self.drag_target_id: int | None = None
        self._next_id = max([item["id"] for item in self.items] + [item["id"] for item in self.history], default=0) + 1

        self.header_visible = False
        self.header_locked = False
        self.history_visible = False
        self.tools_visible = False
        self.view_mode = "main"
        self.pin_var = True
        self.color_entries: dict[str, tk.StringVar] = {}
        self.color_preview_boxes: dict[str, tk.Label] = {}
        self.tab_priority_vars: dict[str, tk.StringVar] = {}

        self._build_ui()
        self.render_tab_bar()
        self.render_tab_manager()
        self._update_header()
        self.render_items()
        self.bind("<Configure>", self._on_resize)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.root = tk.Frame(self, bg=BG)
        self.root.pack(fill="both", expand=True)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(5, weight=1)

        self.header = tk.Frame(self.root, bg=BG, height=52)
        self.header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        self.header.grid_columnconfigure(1, weight=1)
        self.header.grid_propagate(False)

        self.header_hint = tk.Label(self.header, text="focus", bg=BG, fg="#bfb0a4", font=("Georgia", 18, "italic"))
        self.header_hint.grid(row=0, column=0, sticky="w", padx=(0, 12))

        self.header_controls = tk.Frame(self.header, bg=BG)
        self.header_controls.grid(row=0, column=1, sticky="w")
        self.header_controls.grid_columnconfigure(0, weight=1)

        left = tk.Frame(self.header_controls, bg=BG)
        left.grid(row=0, column=0, sticky="w")
        PillButton(left, "+ add", self.toggle_add_panel).pack(side="left", padx=(0, 6))
        PillButton(left, "+ add tab", self.open_add_tab_dialog, padding_x=26).pack(side="left", padx=(0, 6))
        PillButton(left, "history", self.toggle_history).pack(side="left", padx=(0, 6))
        PillButton(left, "tools", self.toggle_tools).pack(side="left", padx=(0, 6))
        self.pin_button = PillButton(left, "on top", self.toggle_topmost)
        self.pin_button.pack(side="left")


        self.progress_bar = tk.Canvas(self.root, bg=BG, height=4, highlightthickness=0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))

        self.tab_bar = tk.Frame(self.root, bg=BG)
        self.tab_bar.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))

        self.tools_panel = tk.Frame(self.root, bg=BG)
        self.tools_panel.grid(row=5, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.tools_panel.grid_columnconfigure(0, weight=1)
        self.tools_canvas = tk.Canvas(self.tools_panel, bg=BG, height=280, highlightthickness=0, borderwidth=0)
        self.tools_canvas.grid(row=0, column=0, sticky="nsew")
        self.tools_scrollbar = tk.Scrollbar(self.tools_panel, orient="vertical", command=self.tools_canvas.yview, troughcolor=BG, bg=PROG_BG, activebackground=ACCENT, relief="flat")
        self.tools_scrollbar.grid(row=0, column=1, sticky="ns")
        self.tools_canvas.configure(yscrollcommand=self.tools_scrollbar.set)
        self.tools_panel.grid_rowconfigure(0, weight=1)
        self.tools_inner = tk.Frame(self.tools_canvas, bg=BG)
        self.tools_canvas_window = self.tools_canvas.create_window((0, 0), window=self.tools_inner, anchor="nw")
        self.tools_inner.bind("<Configure>", lambda _event: self.tools_canvas.configure(scrollregion=self.tools_canvas.bbox("all")))
        self.tools_canvas.bind("<Configure>", lambda event: self.tools_canvas.itemconfigure(self.tools_canvas_window, width=event.width))
        for widget in (self.tools_canvas, self.tools_inner):
            widget.bind("<MouseWheel>", self._on_tools_mousewheel, add="+")

        tools_row = tk.Frame(self.tools_inner, bg=BG)
        tools_row.pack(fill="x")
        PillButton(tools_row, "export", self.export_json).pack(side="left", padx=(0, 6))
        PillButton(tools_row, "import", self.import_json).pack(side="left", padx=(0, 6))
        self.startup_button = PillButton(tools_row, "startup off", self.toggle_startup, padding_x=26)
        self.startup_button.pack(side="left")

        self.colors_panel = tk.Frame(self.tools_inner, bg=BG)
        self.colors_panel.pack(fill="x", pady=(10, 0))
        tk.Label(self.colors_panel, text="colors", bg=BG, fg=TEXT, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))

        preset_row = tk.Frame(self.colors_panel, bg=BG)
        preset_row.grid(row=1, column=0, sticky="w", pady=(0, 8))
        for preset_name in ("warm", "forest", "ocean", "rose"):
            PillButton(preset_row, preset_name, lambda value=preset_name: self.apply_theme(value)).pack(side="left", padx=(0, 6))

        custom_grid = tk.Frame(self.colors_panel, bg=BG)
        custom_grid.grid(row=2, column=0, sticky="ew")
        custom_grid.grid_columnconfigure(1, weight=1)

        editable_keys = ["BG", "CARD", "TEXT", "MUTED", "ACCENT", "BORDER", "CURRENT_BG", "UNDO_BG", "BUTTON_FILL"]
        for row, key in enumerate(editable_keys):
            tk.Label(custom_grid, text=key.lower(), bg=BG, fg=MUTED, font=("Segoe UI", 8, "bold")).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            var = tk.StringVar(value=self.get_active_palette()[key])
            self.color_entries[key] = var
            entry = tk.Entry(custom_grid, textvariable=var, font=("Consolas", 9), relief="flat", bg=CARD, fg=TEXT, insertbackground=TEXT)
            entry.grid(row=row, column=1, sticky="ew", pady=2, ipady=4)
            preview = tk.Label(custom_grid, text="    ", bg=var.get(), relief="flat")
            preview.grid(row=row, column=2, sticky="w", padx=(8, 0))
            self.color_preview_boxes[key] = preview
            var.trace_add("write", lambda *_args, color_key=key: self.update_color_preview(color_key))

        custom_actions = tk.Frame(self.colors_panel, bg=BG)
        custom_actions.grid(row=3, column=0, sticky="w", pady=(8, 0))
        PillButton(custom_actions, "apply custom", self.apply_custom_theme, padding_x=30).pack(side="left", padx=(0, 6))
        PillButton(custom_actions, "load current", self.load_theme_entries, padding_x=28).pack(side="left")

        self.access_panel = tk.Frame(self.tools_inner, bg=BG)
        self.access_panel.pack(fill="x", pady=(12, 0))
        tk.Label(self.access_panel, text="accessibility", bg=BG, fg=TEXT, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))

        font_row = tk.Frame(self.access_panel, bg=BG)
        font_row.grid(row=1, column=0, sticky="w")
        tk.Label(font_row, text="font size", bg=BG, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))
        for label, scale in (("S", 0.9), ("M", 1.0), ("L", 1.15), ("XL", 1.3)):
            PillButton(font_row, label, lambda value=scale: self.set_font_scale(value), padding_x=18).pack(side="left", padx=(0, 6))

        access_row = tk.Frame(self.access_panel, bg=BG)
        access_row.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.access_button = PillButton(access_row, "accessibility off", self.toggle_accessibility, padding_x=30)
        self.access_button.pack(side="left")

        self.tabs_panel = tk.Frame(self.tools_inner, bg=BG)
        self.tabs_panel.pack(fill="x", pady=(12, 0))
        tk.Label(self.tabs_panel, text="tabs", bg=BG, fg=TEXT, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.tab_list = tk.Frame(self.tabs_panel, bg=BG)
        self.tab_list.grid(row=1, column=0, sticky="ew")

        add_tab_row = tk.Frame(self.tabs_panel, bg=BG)
        add_tab_row.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.new_tab_var = tk.StringVar()
        self.new_tab_entry = tk.Entry(add_tab_row, textvariable=self.new_tab_var, font=("Segoe UI", 9), relief="flat", bg=CARD, fg=TEXT, insertbackground=TEXT)
        self.new_tab_entry.pack(side="left", padx=(0, 8), ipady=4)
        PillButton(add_tab_row, "add tab", self.add_tab, padding_x=24).pack(side="left")
        self.tools_panel.grid_remove()

        self.content = tk.Frame(self.root, bg=BG)
        self.content.grid(row=5, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(2, weight=1)

        self.history_panel = tk.Frame(self.content, bg=HIST_BG, padx=12, pady=10)
        self.history_panel.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.history_panel.grid_columnconfigure(0, weight=1)
        tk.Label(self.history_panel, text="recent history", bg=HIST_BG, fg=TEXT, font=("Georgia", 13, "bold italic")).grid(row=0, column=0, sticky="w")
        self.history_list = tk.Frame(self.history_panel, bg=HIST_BG)
        self.history_list.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.history_list.grid_columnconfigure(0, weight=1)
        self.history_panel.grid_remove()

        self.undo_panel = tk.Frame(self.content, bg=UNDO_BG, padx=12, pady=8)
        self.undo_panel.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.undo_label = tk.Label(self.undo_panel, text="", bg=UNDO_BG, fg=TEXT, font=("Segoe UI", 9))
        self.undo_label.pack(side="left")
        self.undo_button = tk.Label(self.undo_panel, text="undo", bg=UNDO_BG, fg=ACCENT, font=("Segoe UI", 9, "bold"), cursor="hand2")
        self.undo_button.pack(side="right")
        self.undo_button.bind("<Button-1>", lambda _event: self.undo_complete())
        self.undo_panel.grid_remove()

        self.list_shell = tk.Frame(self.content, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        self.list_shell.grid(row=2, column=0, sticky="nsew")
        self.list_shell.grid_rowconfigure(0, weight=1)
        self.list_shell.grid_columnconfigure(0, weight=1)

        self.loading_panel = tk.Frame(self.content, bg=BG)
        self.loading_panel.grid(row=2, column=0, sticky="nsew")
        self.loading_panel.grid_columnconfigure(0, weight=1)
        self.loading_panel.grid_rowconfigure(0, weight=1)
        loading_inner = tk.Frame(self.loading_panel, bg=BG)
        loading_inner.grid(row=0, column=0)
        self.loading_label = tk.Label(loading_inner, text="Loading...", bg=BG, fg=MUTED, font=("Segoe UI", 10, "bold"))
        self.loading_label.pack(pady=(0, 8))
        self.loading_bar = ttk.Progressbar(loading_inner, orient="horizontal", mode="indeterminate", length=180)
        self.loading_bar.pack()
        self.loading_panel.grid_remove()

        self.canvas = tk.Canvas(self.list_shell, bg=CARD, highlightthickness=0, borderwidth=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = tk.Scrollbar(self.list_shell, orient="vertical", command=self.canvas.yview, troughcolor=CARD, bg="#c8bcae", activebackground=ACCENT, relief="flat")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.items_frame = tk.Frame(self.canvas, bg=CARD, padx=10, pady=10)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.items_frame, anchor="nw")
        self.items_frame.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._sync_canvas_width)
        for widget in (self.canvas, self.items_frame, self.list_shell):
            widget.bind("<MouseWheel>", self._on_mousewheel, add="+")

        self.footer = tk.Label(self.root, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.footer.grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 8))

        for widget in (self, self.root, self.header, self.header_hint, self.header_controls, self.content, self.list_shell, self.canvas):
            widget.bind("<Motion>", self._on_pointer_motion, add="+")
        self.update_startup_button()

    def load_data(self) -> tuple[list[dict], list[dict], dict]:
        defaults = [make_item(index + 1, item["text"], created_at=now_stamp()) for index, item in enumerate(DEFAULT_ITEMS)]
        if not self.data_path.exists():
            return defaults, [], {}
        try:
            raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return defaults, [], {}
        if isinstance(raw, list):
            active = [normalized for index, item in enumerate(raw) if (normalized := self._normalize_active(item, index))]
            return active or defaults, [], {}
        active = [normalized for index, item in enumerate(raw.get("active", [])) if (normalized := self._normalize_active(item, index))]
        history = [normalized for index, item in enumerate(raw.get("history", [])) if (normalized := self._normalize_history(item, index))]
        settings = raw.get("settings", {}) if isinstance(raw.get("settings", {}), dict) else {}
        return active or defaults, history, settings

    def normalize_tabs(self, raw_tabs) -> list[dict]:
        tabs: list[dict] = []
        seen: set[str] = set()
        if isinstance(raw_tabs, list):
            for tab in raw_tabs:
                if not isinstance(tab, dict):
                    continue
                name = normalize_tab_name(str(tab.get("name", "")))
                if not name or name in seen:
                    continue
                priority = str(tab.get("priority", "normal"))
                if priority not in TAB_PRIORITY_ORDER:
                    priority = "normal"
                tabs.append({"name": name, "priority": priority})
                seen.add(name)
        if not tabs:
            tabs = default_tabs()
        if "General" not in {tab["name"] for tab in tabs}:
            tabs.insert(0, {"name": "General", "priority": "normal"})
        return tabs

    def ensure_tab_exists(self, name: str) -> str:
        name = normalize_tab_name(name) or "General"
        if name not in {tab["name"] for tab in self.tabs}:
            self.tabs.append({"name": name, "priority": "normal"})
            self.settings["tabs"] = self.tabs
        return name

    def tab_priority(self, name: str) -> int:
        for tab in self.tabs:
            if tab["name"] == name:
                return TAB_PRIORITY_ORDER.get(tab["priority"], 1)
        return TAB_PRIORITY_ORDER["normal"]

    def _normalize_active(self, item: dict, index: int) -> dict | None:
        text = str(item.get("text", "")).strip()
        if not text:
            return None
        return {
            "id": int(item.get("id", index + 1)),
            "text": text,
            "done": False,
            "current": bool(item.get("current", False)),
            "created_at": str(item.get("created_at", now_stamp())),
            "completed_at": "",
            "extra_info": str(item.get("extra_info", "")),
            "due_date": str(item.get("due_date", "")),
            "tab": normalize_tab_name(str(item.get("tab", "General"))) or "General",
        }

    def _normalize_history(self, item: dict, index: int) -> dict | None:
        text = str(item.get("text", "")).strip()
        if not text:
            return None
        return {
            "id": int(item.get("id", index + 1000)),
            "text": text,
            "done": True,
            "current": False,
            "created_at": str(item.get("created_at", "")),
            "completed_at": str(item.get("completed_at", "")),
            "extra_info": str(item.get("extra_info", "")),
            "due_date": str(item.get("due_date", "")),
            "tab": normalize_tab_name(str(item.get("tab", "General"))) or "General",
        }

    def save_data(self) -> None:
        payload = {"active": self.items, "history": self.history[:250], "settings": self.settings}
        self.data_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def scaled(self, size: int) -> int:
        factor = self.font_scale * (1.08 if self.accessibility_mode else 1.0)
        return max(8, int(round(size * factor)))

    def get_active_palette(self) -> dict:
        if self.theme_name == "custom" and self.custom_palette:
            base = THEME_PRESETS["warm"].copy()
            for key in THEME_KEYS:
                if key in self.custom_palette:
                    base[key] = self.custom_palette[key]
            return base
        return THEME_PRESETS.get(self.theme_name, THEME_PRESETS["warm"]).copy()

    def apply_theme(self, theme_name: str, persist: bool = True) -> None:
        if theme_name == "custom":
            palette = self.get_active_palette()
        else:
            palette = THEME_PRESETS.get(theme_name, THEME_PRESETS["warm"]).copy()
        apply_palette_values(palette)
        self.theme_name = theme_name
        if persist:
            self.settings["theme_name"] = theme_name
            self.settings["custom_palette"] = self.custom_palette
            self.save_data()
        if hasattr(self, "root"):
            self.refresh_theme()

    def apply_custom_theme(self) -> None:
        palette = self.get_active_palette()
        for key, var in self.color_entries.items():
            normalized = normalize_hex(var.get())
            if normalized is None:
                messagebox.showwarning("Invalid color", f"{key} must be a hex color like #aabbcc.", parent=self)
                return
            palette[key] = normalized
        self.custom_palette = palette
        self.apply_theme("custom")

    def load_theme_entries(self) -> None:
        palette = self.get_active_palette()
        for key, var in self.color_entries.items():
            var.set(palette[key])

    def update_color_preview(self, key: str) -> None:
        if key not in self.color_preview_boxes or key not in self.color_entries:
            return
        normalized = normalize_hex(self.color_entries[key].get())
        preview = self.color_preview_boxes[key]
        preview.configure(bg=normalized if normalized else BORDER, text="    " if normalized else " ? ")

    def set_font_scale(self, value: float) -> None:
        self.font_scale = value
        self.settings["font_scale"] = value
        self.save_data()
        self.refresh_theme()

    def toggle_accessibility(self) -> None:
        self.accessibility_mode = not self.accessibility_mode
        self.settings["accessibility_mode"] = self.accessibility_mode
        self.save_data()
        self.refresh_theme()

    def refresh_theme(self) -> None:
        self.configure(bg=BG)
        self.root.configure(bg=BG)
        self.header.configure(bg=BG)
        self.header_hint.configure(bg=BG, fg=MUTED, font=("Georgia", self.scaled(18), "italic"))
        self.header_controls.configure(bg=BG)
        for child in self.header_controls.winfo_children():
            child.configure(bg=BG)
            for grandchild in child.winfo_children():
                if isinstance(grandchild, PillButton):
                    grandchild.refresh_theme(self.scaled(9))
                else:
                    grandchild.configure(bg=BG)
        self.progress_bar.configure(bg=BG)
        self.tab_bar.configure(bg=BG)
        self.tools_panel.configure(bg=BG)
        self.tools_canvas.configure(bg=BG)
        self.tools_inner.configure(bg=BG)
        self.tools_scrollbar.configure(troughcolor=BG, bg=PROG_BG, activebackground=ACCENT)
        for widget in self.tools_inner.winfo_children():
            self._refresh_widget_colors(widget)
        self.content.configure(bg=BG)
        self.history_panel.configure(bg=HIST_BG)
        self.history_list.configure(bg=HIST_BG)
        for child in self.history_panel.winfo_children():
            self._refresh_widget_colors(child)
        self.undo_panel.configure(bg=UNDO_BG)
        self.undo_label.configure(bg=UNDO_BG, fg=TEXT, font=("Segoe UI", self.scaled(9)))
        self.undo_button.configure(bg=UNDO_BG, fg=ACCENT, font=("Segoe UI", self.scaled(9), "bold"))
        self.list_shell.configure(bg=CARD, highlightbackground=BORDER)
        self.canvas.configure(bg=CARD)
        self.items_frame.configure(bg=CARD)
        self.loading_panel.configure(bg=BG)
        self.loading_label.configure(bg=BG, fg=MUTED, font=("Segoe UI", self.scaled(10), "bold"))
        self.scrollbar.configure(troughcolor=CARD, bg=PROG_BG, activebackground=ACCENT)
        self.footer.configure(bg=BG, fg=MUTED, font=("Segoe UI", self.scaled(8)))
        self.update_startup_button()
        self.access_button.set_text("accessibility on" if self.accessibility_mode else "accessibility off")
        self.load_theme_entries()
        self.render_tab_bar()
        self.render_tab_manager()
        self.render_items()
        if self.history_visible:
            self.render_history()

    def _refresh_widget_colors(self, widget: tk.Misc) -> None:
        if isinstance(widget, PillButton):
            widget.refresh_theme(self.scaled(9))
            return
        if isinstance(widget, tk.Frame):
            widget.configure(bg=BG if widget not in (self.history_panel, self.history_list) else HIST_BG)
        elif isinstance(widget, tk.Label):
            if widget in self.color_preview_boxes.values():
                return
            parent_bg = HIST_BG if widget.master in (self.history_panel, self.history_list) else BG
            fg = TEXT if "colors" in str(widget.cget("text")).lower() else MUTED
            if widget.master in (self.colors_panel, self.access_panel, self.tabs_panel) and widget.cget("text") in ("colors", "accessibility", "tabs"):
                fg = TEXT
            widget.configure(bg=parent_bg, fg=fg, font=("Segoe UI", self.scaled(8), "bold" if fg == TEXT or "?" in str(widget.cget("text")) else "normal"))
        elif isinstance(widget, tk.Entry):
            font_family = "Consolas" if widget in getattr(self, "color_preview_boxes", {}).values() else "Segoe UI"
            widget.configure(bg=CARD, fg=TEXT, insertbackground=TEXT, readonlybackground=CARD, font=(font_family, self.scaled(9)))
        for child in widget.winfo_children():
            self._refresh_widget_colors(child)

    def show_loading(self) -> None:
        self.loading_panel.configure(bg=BG)
        self.loading_label.configure(bg=BG, fg=MUTED, font=("Segoe UI", self.scaled(10), "bold"))
        self.list_shell.grid_remove()
        self.history_panel.grid_remove()
        self.loading_panel.grid()
        self.loading_bar.start(12)
        self.update_idletasks()

    def hide_loading(self) -> None:
        self.loading_bar.stop()
        self.loading_panel.grid_remove()

    def render_tab_bar(self) -> None:
        for child in self.tab_bar.winfo_children():
            child.destroy()
        labels = ["All"] + [tab["name"] for tab in self.tabs]
        for name in labels:
            active = name == self.active_tab
            chip = tk.Label(
                self.tab_bar,
                text=name,
                bg=ACCENT if active else CARD,
                fg=CARD if active else TEXT,
                font=("Segoe UI", self.scaled(9), "bold"),
                padx=10,
                pady=4,
                cursor="hand2",
            )
            chip.pack(side="left", padx=(0, 6))
            chip.bind("<Button-1>", lambda _event, value=name: self.set_active_tab(value))

    def render_tab_manager(self) -> None:
        for child in self.tab_list.winfo_children():
            child.destroy()
        self.tab_priority_vars.clear()
        for row, tab in enumerate(self.tabs):
            name = tab["name"]
            tk.Label(self.tab_list, text=name, bg=BG, fg=TEXT, font=("Segoe UI", self.scaled(8), "bold")).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            var = tk.StringVar(value=tab["priority"])
            self.tab_priority_vars[name] = var
            menu = tk.OptionMenu(self.tab_list, var, "high", "normal", "low", command=lambda _value, tab_name=name: self.update_tab_priority(tab_name))
            menu.configure(bg=CARD, fg=TEXT, activebackground=CARD_HL, highlightthickness=0, relief="flat")
            menu["menu"].configure(bg=CARD, fg=TEXT)
            menu.grid(row=row, column=1, sticky="w", pady=2)
            up = tk.Label(self.tab_list, text="↑", bg=BG, fg=MUTED, font=("Segoe UI", self.scaled(9), "bold"), cursor="hand2")
            up.grid(row=row, column=2, sticky="w", padx=(8, 4))
            up.bind("<Button-1>", lambda _event, tab_name=name: self.move_tab(tab_name, -1))
            down = tk.Label(self.tab_list, text="↓", bg=BG, fg=MUTED, font=("Segoe UI", self.scaled(9), "bold"), cursor="hand2")
            down.grid(row=row, column=3, sticky="w", padx=(0, 4))
            down.bind("<Button-1>", lambda _event, tab_name=name: self.move_tab(tab_name, 1))
            if name != "General":
                remove = tk.Label(self.tab_list, text="x", bg=BG, fg=MUTED, font=("Segoe UI", self.scaled(9), "bold"), cursor="hand2")
                remove.grid(row=row, column=4, sticky="w", padx=(8, 0))
                remove.bind("<Button-1>", lambda _event, tab_name=name: self.remove_tab(tab_name))

    def set_active_tab(self, name: str) -> None:
        self.active_tab = name
        self.render_tab_bar()
        self.render_items()

    def visible_items(self) -> list[dict]:
        if self.active_tab == "All":
            ordered = list(self.items)
        else:
            ordered = [item for item in self.items if item.get("tab", "General") == self.active_tab]
        return sorted(
            ordered,
            key=lambda item: (
                0 if item.get("current") else 1,
                self.tab_priority(item.get("tab", "General")),
                self.items.index(item),
            ),
        )

    def update_tab_priority(self, tab_name: str) -> None:
        for tab in self.tabs:
            if tab["name"] == tab_name:
                tab["priority"] = self.tab_priority_vars[tab_name].get()
                break
        self.settings["tabs"] = self.tabs
        self.save_data()
        self.render_tab_bar()
        self.render_items()

    def add_tab(self) -> None:
        name = normalize_tab_name(self.new_tab_var.get())
        if not name:
            return
        if name in {tab["name"] for tab in self.tabs}:
            self.new_tab_var.set("")
            return
        self.tabs.append({"name": name, "priority": "normal"})
        self.settings["tabs"] = self.tabs
        self.new_tab_var.set("")
        self.save_data()
        self.render_tab_bar()
        self.render_tab_manager()

    def open_add_tab_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Add tab")
        dialog.transient(self)
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.configure(bg=BG)
        dialog.geometry(f"+{self.winfo_rootx() + 36}+{self.winfo_rooty() + 56}")

        frame = tk.Frame(dialog, bg=BG, padx=16, pady=16)
        frame.pack(fill="both", expand=True)
        frame.grid_columnconfigure(0, weight=1)

        tk.Label(frame, text="Add tab", bg=BG, fg=TEXT, font=("Georgia", 13, "bold italic")).grid(row=0, column=0, sticky="w")

        value = tk.StringVar()
        entry = tk.Entry(frame, textvariable=value, font=("Segoe UI", 10), relief="flat", bg=CARD, fg=TEXT, insertbackground=TEXT)
        entry.grid(row=1, column=0, sticky="ew", pady=(10, 12), ipady=8)
        entry.focus_set()

        def submit() -> None:
            name = normalize_tab_name(value.get())
            if not name:
                return
            if name in {tab["name"] for tab in self.tabs}:
                messagebox.showwarning("Duplicate tab", "That tab already exists.", parent=dialog)
                return
            self.tabs.append({"name": name, "priority": "normal"})
            self.settings["tabs"] = self.tabs
            self.save_data()
            self.render_tab_bar()
            self.render_tab_manager()
            dialog.destroy()

        actions = tk.Frame(frame, bg=BG)
        actions.grid(row=2, column=0, sticky="e")
        PillButton(actions, "cancel", dialog.destroy).pack(side="left", padx=(0, 8))
        PillButton(actions, "create", submit).pack(side="left")
        dialog.bind("<Return>", lambda _event: submit())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def move_tab(self, tab_name: str, direction: int) -> None:
        index = next((i for i, tab in enumerate(self.tabs) if tab["name"] == tab_name), None)
        if index is None:
            return
        target = index + direction
        if target < 0 or target >= len(self.tabs):
            return
        self.tabs[index], self.tabs[target] = self.tabs[target], self.tabs[index]
        self.settings["tabs"] = self.tabs
        self.save_data()
        self.render_tab_bar()
        self.render_tab_manager()
        self.render_items()

    def remove_tab(self, tab_name: str) -> None:
        self.tabs = [tab for tab in self.tabs if tab["name"] != tab_name]
        for item in self.items:
            if item.get("tab") == tab_name:
                item["tab"] = "General"
        for item in self.history:
            if item.get("tab") == tab_name:
                item["tab"] = "General"
        if self.active_tab == tab_name:
            self.active_tab = "All"
        self.settings["tabs"] = self.tabs
        self.save_data()
        self.render_tab_bar()
        self.render_tab_manager()
        self.render_items()

    def toggle_topmost(self) -> None:
        self.pin_var = not self.pin_var
        self.attributes("-topmost", self.pin_var)
        self.pin_button.set_text("on top" if self.pin_var else "normal")

    def toggle_add_panel(self) -> None:
        self.set_view_mode("main")
        self.header_locked = True
        self.header_visible = True
        self._update_header()
        self.start_create()

    def toggle_history(self) -> None:
        should_open = self.view_mode != "history"
        self.history_visible = should_open
        if should_open:
            self.header_locked = True
            self.header_visible = True
            self._update_header()
            self.set_view_mode("history")
            self.render_history()
        else:
            self.set_view_mode("main")
            self.header_locked = False

    def toggle_tools(self) -> None:
        should_open = self.view_mode != "tools"
        self.tools_visible = should_open
        if should_open:
            self.header_locked = True
            self.header_visible = True
            self._update_header()
            self.set_view_mode("tools")
        else:
            self.set_view_mode("main")
            self.header_locked = False

    def set_view_mode(self, mode: str) -> None:
        self.view_mode = mode
        if mode == "tools":
            self.tools_visible = True
            self.history_visible = False
            self.content.grid_remove()
            self.tools_panel.grid()
            return
        self.tools_visible = False
        self.tools_panel.grid_remove()
        self.content.grid()
        if mode == "history":
            self.history_visible = True
            self.history_panel.grid()
            self.list_shell.grid_remove()
            self.undo_panel.grid_remove()
        else:
            self.history_visible = False
            self.history_panel.grid_remove()
            self.list_shell.grid()
            if self.pending_completion is not None:
                self.undo_panel.grid()

    def start_create(self) -> None:
        default_tab = self.active_tab if self.active_tab != "All" else "General"
        self.open_task_editor(
            {
                "id": self._next_id,
                "text": "",
                "done": False,
                "current": False,
                "created_at": now_stamp(),
                "completed_at": "",
                "extra_info": "",
                "due_date": "",
                "tab": self.ensure_tab_exists(default_tab),
            },
            is_new=True,
        )

    def delete_item(self, item_id: int) -> None:
        self.items = [item for item in self.items if item["id"] != item_id]
        self.save_data()
        self.render_items()

    def toggle_current(self, item_id: int) -> None:
        target = next((item for item in self.items if item["id"] == item_id), None)
        if target is None:
            return
        new_value = not target.get("current", False)
        for item in self.items:
            item["current"] = False
        target["current"] = new_value
        if new_value:
            self.items = [target] + [item for item in self.items if item["id"] != item_id]
        self.save_data()
        self.render_items()

    def complete_item(self, item_id: int) -> None:
        item = next((entry for entry in self.items if entry["id"] == item_id), None)
        if item is None:
            return
        self.finalize_pending_completion()
        self.items = [entry for entry in self.items if entry["id"] != item_id]
        item["done"] = True
        item["current"] = False
        item["completed_at"] = now_stamp()
        self.pending_completion = item
        self.undo_label.configure(text=f"Completed: {item['text']}")
        self.undo_panel.grid()
        self.pending_timer = self.after(3000, self.finalize_pending_completion)
        self.save_data()
        self.render_items()

    def undo_complete(self) -> None:
        if self.pending_completion is None:
            return
        if self.pending_timer is not None:
            self.after_cancel(self.pending_timer)
            self.pending_timer = None
        restored = dict(self.pending_completion)
        restored["done"] = False
        restored["completed_at"] = ""
        self.items.insert(0, restored)
        self.pending_completion = None
        self.undo_panel.grid_remove()
        self.save_data()
        self.render_items()

    def finalize_pending_completion(self) -> None:
        if self.pending_completion is None:
            return
        if self.pending_timer is not None:
            self.after_cancel(self.pending_timer)
            self.pending_timer = None
        self.history.insert(0, dict(self.pending_completion))
        self.pending_completion = None
        self.undo_panel.grid_remove()
        self.save_data()
        self.render_items()
        if self.history_visible:
            self.render_history()

    def restore_history_item(self, item_id: int) -> None:
        item = next((entry for entry in self.history if entry["id"] == item_id), None)
        if item is None:
            return
        self.history = [entry for entry in self.history if entry["id"] != item_id]
        restored = dict(item)
        restored["done"] = False
        restored["completed_at"] = ""
        self.items.append(restored)
        self.save_data()
        self.render_items()
        self.render_history()

    def start_edit(self, item_id: int) -> None:
        item = next((entry for entry in self.items if entry["id"] == item_id), None)
        if item is None:
            return
        self.open_task_editor(item, is_new=False)

    def open_task_editor(self, item: dict, *, is_new: bool) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Add task" if is_new else "Edit")
        dialog.transient(self)
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.configure(bg=BG)
        dialog.geometry(f"+{self.winfo_rootx() + 30}+{self.winfo_rooty() + 60}")

        frame = tk.Frame(dialog, bg=BG, padx=18, pady=18)
        frame.pack(fill="both", expand=True)
        frame.grid_columnconfigure(0, weight=1)

        tk.Label(frame, text="Add task" if is_new else "Edit task", bg=BG, fg=TEXT, font=("Georgia", 14, "bold italic")).grid(row=0, column=0, sticky="w")

        value = tk.StringVar(value=item["text"])
        entry = tk.Entry(frame, textvariable=value, font=("Segoe UI", 11), relief="flat", bg=CARD, fg=TEXT, insertbackground=TEXT)
        entry.grid(row=1, column=0, sticky="ew", pady=(10, 12), ipady=10)
        entry.focus_set()
        entry.select_range(0, "end")

        current_var = tk.BooleanVar(value=item.get("current", False))
        tk.Checkbutton(frame, text="mark as current focus", variable=current_var, bg=BG, fg=TEXT, selectcolor=BG, activebackground=BG).grid(row=2, column=0, sticky="w")

        tab_wrap = tk.Frame(frame, bg=BG)
        tab_wrap.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        tab_wrap.grid_columnconfigure(1, weight=1)
        tk.Label(tab_wrap, text="Tab", bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        tab_var = tk.StringVar(value=item.get("tab", "General"))
        tab_options = [tab["name"] for tab in self.tabs]
        tab_menu = tk.OptionMenu(tab_wrap, tab_var, *tab_options)
        tab_menu.configure(bg=CARD, fg=TEXT, activebackground=CARD_HL, highlightthickness=0, relief="flat")
        tab_menu["menu"].configure(bg=CARD, fg=TEXT)
        tab_menu.grid(row=0, column=1, sticky="w")

        due_var = tk.StringVar(value=item.get("due_date", ""))
        due_wrap = tk.Frame(frame, bg=BG)
        due_wrap.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        due_wrap.grid_columnconfigure(1, weight=1)
        tk.Label(due_wrap, text="Due date", bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        due_entry = tk.Entry(due_wrap, textvariable=due_var, font=("Segoe UI", 10), relief="flat", bg=CARD, fg=TEXT, insertbackground=TEXT, state="readonly", readonlybackground=CARD)
        due_entry.grid(row=0, column=1, sticky="ew", ipady=6)
        pick_due = tk.Label(due_wrap, text="pick", bg=BG, fg=ACCENT, font=("Segoe UI", 9, "bold"), cursor="hand2")
        pick_due.grid(row=0, column=2, sticky="e", padx=(8, 0))
        tk.Label(due_wrap, text="Date picker with optional time", bg=BG, fg=MUTED, font=("Segoe UI", 8)).grid(row=1, column=1, sticky="w", pady=(4, 0))

        def open_due_picker() -> None:
            DueDatePicker(dialog, due_var.get().strip(), lambda value: due_var.set(value))

        pick_due.bind("<Button-1>", lambda _event: open_due_picker())
        due_entry.bind("<Button-1>", lambda _event: open_due_picker())

        extra_wrap = tk.Frame(frame, bg=BG)
        extra_wrap.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        extra_wrap.grid_columnconfigure(0, weight=1)
        extra_open = tk.BooleanVar(value=bool(item.get("extra_info", "")))

        extra_header = tk.Frame(extra_wrap, bg=BG)
        extra_header.grid(row=0, column=0, sticky="ew")
        extra_header.grid_columnconfigure(0, weight=1)

        tk.Label(extra_header, text="Extra info", bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        toggle_extra = tk.Label(extra_header, text="hide" if extra_open.get() else "edit", bg=BG, fg=ACCENT, font=("Segoe UI", 9, "bold"), cursor="hand2")
        toggle_extra.grid(row=0, column=1, sticky="e")

        extra_text = tk.Text(extra_wrap, height=6, wrap="word", relief="flat", bg=CARD, fg=TEXT, insertbackground=TEXT, font=("Segoe UI", 10))
        extra_text.insert("1.0", item.get("extra_info", ""))
        extra_text.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        def sync_extra_visibility() -> None:
            if extra_open.get():
                extra_text.grid()
                toggle_extra.configure(text="hide")
            else:
                extra_text.grid_remove()
                toggle_extra.configure(text="edit")

        toggle_extra.bind("<Button-1>", lambda _event: (extra_open.set(not extra_open.get()), sync_extra_visibility()))
        sync_extra_visibility()

        tk.Label(frame, text=f"Added {item.get('created_at', '')[:19]}", bg=BG, fg=MUTED, font=("Segoe UI", 8)).grid(row=6, column=0, sticky="w", pady=(10, 0))

        buttons = tk.Frame(frame, bg=BG)
        buttons.grid(row=7, column=0, sticky="e", pady=(14, 0))

        def submit() -> None:
            new_text = value.get().strip()
            if not new_text:
                messagebox.showwarning("Empty text", "Type something before saving.", parent=dialog)
                return
            due_date = due_var.get().strip()
            if not is_valid_due_date(due_date):
                messagebox.showwarning("Invalid date", "Use YYYY-MM-DD or YYYY-MM-DD HH:MM for the due date.", parent=dialog)
                return
            item["text"] = new_text
            item["extra_info"] = extra_text.get("1.0", "end").strip()
            item["due_date"] = due_date
            item["tab"] = self.ensure_tab_exists(tab_var.get())
            if current_var.get():
                for entry_item in self.items:
                    entry_item["current"] = False
            item["current"] = current_var.get()
            if is_new:
                self.finalize_pending_completion()
                self.items.append(item)
                self._next_id += 1
                play_add()
            self.save_data()
            self.render_tab_bar()
            self.render_tab_manager()
            self.render_items()
            dialog.destroy()

        PillButton(buttons, "cancel", dialog.destroy).pack(side="left", padx=(0, 8))
        PillButton(buttons, "save", submit).pack(side="left")
        dialog.bind("<Return>", lambda _event: submit())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def start_drag(self, item_id: int, _event: tk.Event) -> None:
        self.drag_item_id = item_id
        self.drag_target_id = None
        widget = self.item_widgets.get(item_id)
        if widget is not None:
            widget.set_dragging(True)

    def drag_motion(self, event: tk.Event) -> None:
        if self.drag_item_id is None:
            return
        pointer = self.winfo_containing(event.x_root, event.y_root)
        item_widget = None
        while pointer is not None:
            if isinstance(pointer, ChecklistItem):
                item_widget = pointer
                break
            pointer = getattr(pointer, "master", None)
        if item_widget is None or item_widget.item["id"] == self.drag_item_id:
            return
        if self.drag_target_id == item_widget.item["id"]:
            return
        source_index = next((index for index, item in enumerate(self.items) if item["id"] == self.drag_item_id), None)
        target_index = next((index for index, item in enumerate(self.items) if item["id"] == item_widget.item["id"]), None)
        if source_index is None or target_index is None or source_index == target_index:
            return
        moving = self.items.pop(source_index)
        if source_index < target_index:
            target_index -= 1
        self.items.insert(target_index, moving)
        self.render_items()
        self.drag_item_id = moving["id"]
        self.drag_target_id = item_widget.item["id"]
        widget = self.item_widgets.get(self.drag_item_id)
        if widget is not None:
            widget.set_dragging(True)

    def end_drag(self, _event: tk.Event) -> None:
        if self.drag_item_id is None:
            return
        widget = self.item_widgets.get(self.drag_item_id)
        if widget is not None:
            widget.set_dragging(False)
        self.drag_item_id = None
        self.drag_target_id = None
        self.save_data()

    def export_json(self) -> None:
        self.finalize_pending_completion()
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export checklist",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="focus-export.json",
        )
        if not path:
            return
        payload = {
            "app": APP_NAME,
            "exported_at": now_stamp(),
            "active": self.items,
            "history": self.history,
            "settings": self.settings,
        }
        Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def import_json(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Import checklist",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            messagebox.showerror("Import failed", "That file is not a valid JSON export.", parent=self)
            return
        active = [normalized for index, item in enumerate(raw.get("active", [])) if (normalized := self._normalize_active(item, index))]
        history = [normalized for index, item in enumerate(raw.get("history", [])) if (normalized := self._normalize_history(item, index))]
        if not active and not history:
            messagebox.showerror("Import failed", "No valid tasks were found in that file.", parent=self)
            return
        if not messagebox.askyesno("Replace data", "Importing will replace your current checklist and history. Continue?", parent=self):
            return
        self.items = active
        self.history = history
        self.settings = raw.get("settings", {}) if isinstance(raw.get("settings", {}), dict) else {}
        self._next_id = max([item["id"] for item in self.items] + [item["id"] for item in self.history], default=0) + 1
        self.pending_completion = None
        if self.pending_timer is not None:
            self.after_cancel(self.pending_timer)
            self.pending_timer = None
        self.undo_panel.grid_remove()
        self.save_data()
        self.render_items()
        self.render_history()

    def get_startup_path(self) -> Path | None:
        if platform.system() == "Windows":
            appdata = os.environ.get("APPDATA")
            if not appdata:
                return None
            return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "focus.cmd"
        if platform.system() == "Linux":
            return Path.home() / ".config" / "autostart" / "focus.desktop"
        return None

    def startup_command(self) -> tuple[str, str]:
        if getattr(sys, "frozen", False):
            executable = Path(sys.executable).resolve()
            return str(executable), str(executable)
        python_exe = Path(sys.executable).resolve()
        script = Path(__file__).resolve()
        return str(python_exe), str(script)

    def is_startup_enabled(self) -> bool:
        path = self.get_startup_path()
        return bool(path and path.exists())

    def update_startup_button(self) -> None:
        self.startup_button.set_text("startup on" if self.is_startup_enabled() else "startup off")

    def toggle_startup(self) -> None:
        path = self.get_startup_path()
        if path is None:
            messagebox.showinfo("Not supported", "Startup integration is only implemented for Windows and Linux.", parent=self)
            return
        enabled = self.is_startup_enabled()
        try:
            if enabled:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                first, second = self.startup_command()
                if platform.system() == "Windows":
                    content = f'@echo off\r\nstart "" "{first}"\r\n' if getattr(sys, "frozen", False) else f'@echo off\r\nstart "" "{first}" "{second}"\r\n'
                else:
                    exec_value = f'"{first}"' if getattr(sys, "frozen", False) else f'"{first}" "{second}"'
                    content = "[Desktop Entry]\nType=Application\nName=focus\nExec=" + exec_value + "\nX-GNOME-Autostart-enabled=true\n"
                path.write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Startup failed", str(exc), parent=self)
            return
        self.update_startup_button()

    def render_items(self) -> None:
        self.show_loading()
        for child in self.items_frame.winfo_children():
            child.destroy()
        self.item_widgets.clear()
        visible_items = self.visible_items()

        if not visible_items:
            tk.Label(
                self.items_frame,
                text="All clear." if self.active_tab == "All" else f"No tasks in {self.active_tab}.",
                bg=CARD,
                fg=MUTED,
                justify="center",
                font=("Georgia", 12, "italic"),
                pady=52,
            ).grid(row=0, column=0, sticky="ew")
            self.items_frame.grid_columnconfigure(0, weight=1)
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.list_shell.grid()
            self.hide_loading()
            self._draw_progress()
            self._update_footer()
            return

        for row, item in enumerate(visible_items):
            widget = ChecklistItem(self.items_frame, self, item)
            widget.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            self.item_widgets[item["id"]] = widget

        self.items_frame.grid_columnconfigure(0, weight=1)
        self.after(10, self._refresh_wraps)
        self.list_shell.grid()
        self.hide_loading()
        self._draw_progress()
        self._update_footer()

    def render_history(self) -> None:
        self.show_loading()
        for child in self.history_list.winfo_children():
            child.destroy()
        if not self.history:
            tk.Label(self.history_list, text="No completed tasks yet.", bg=HIST_BG, fg=MUTED, font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")
            self.history_panel.grid()
            self.hide_loading()
            return
        for row, item in enumerate(self.history[:10]):
            HistoryItem(self.history_list, self, item).grid(row=row, column=0, sticky="ew", pady=4)
        self.history_list.grid_columnconfigure(0, weight=1)
        self.history_panel.grid()
        self.hide_loading()

    def _draw_progress(self) -> None:
        today = time.strftime("%Y-%m-%d")
        done_today = sum(1 for item in self.history if parse_time_prefix(item.get("completed_at", ""), today))
        total = len(self.items) + done_today
        self.progress_bar.delete("all")
        self.progress_bar.update_idletasks()
        width = self.progress_bar.winfo_width()
        height = self.progress_bar.winfo_height()
        if width < 2:
            return
        self.progress_bar.create_rectangle(0, 0, width, height, fill=PROG_BG, outline="")
        if total > 0 and done_today > 0:
            fill_width = max(4, int(width * done_today / total))
            self.progress_bar.create_rectangle(0, 0, fill_width, height, fill=SUCCESS, outline="")

    def _update_footer(self) -> None:
        today = time.strftime("%Y-%m-%d")
        month = time.strftime("%Y-%m")
        year = time.strftime("%Y")
        done_today = sum(1 for item in self.history if parse_time_prefix(item.get("completed_at", ""), today))
        done_month = sum(1 for item in self.history if parse_time_prefix(item.get("completed_at", ""), month))
        done_year = sum(1 for item in self.history if parse_time_prefix(item.get("completed_at", ""), year))
        self.footer.configure(text=f"{len(self.items)} pending   {done_today} today   {done_month} month   {done_year} year")

    def _refresh_wraps(self) -> None:
        width = self.canvas.winfo_width()
        for widget in self.item_widgets.values():
            widget.update_wrap(width)

    def _sync_canvas_width(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.canvas_window, width=event.width)
        self._refresh_wraps()
        self._draw_progress()

    def _on_resize(self, _event: tk.Event) -> None:
        self._refresh_wraps()
        self._draw_progress()

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self.view_mode != "main":
            return
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_tools_mousewheel(self, event: tk.Event) -> None:
        if self.view_mode != "tools":
            return
        if self.tools_canvas.winfo_exists():
            self.tools_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_pointer_motion(self, event: tk.Event) -> None:
        if self.header_locked:
            inside = (
                self.winfo_rootx() <= event.x_root <= self.winfo_rootx() + self.winfo_width()
                and self.winfo_rooty() <= event.y_root <= self.winfo_rooty() + self.winfo_height()
            )
            if not inside:
                self.header_locked = False
                self.header_visible = False
                self._update_header()
            elif not self.header_visible:
                self.header_visible = True
                self._update_header()
            return
        top_end = self.header.winfo_rooty() + self.header.winfo_height()
        should_show = event.y_root <= top_end
        if should_show != self.header_visible:
            self.header_visible = should_show
            self._update_header()

    def _update_header(self) -> None:
        if self.header_visible:
            self.header_controls.grid()
        else:
            self.header_controls.grid_remove()
            self.set_view_mode("main")
            self.header_locked = False

    def _on_close(self) -> None:
        self.finalize_pending_completion()
        self.destroy()


if __name__ == "__main__":
    app = FocusApp()
    app.mainloop()

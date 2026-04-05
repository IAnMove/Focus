from __future__ import annotations

import io
import json
import math
import platform
import re
import struct
import sys
import threading
import wave
import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDateTime, QEvent, QPointF, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "focus"
TAB_PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
THEME_KEYS = ["BG", "CARD", "CARD_ALT", "TEXT", "MUTED", "ACCENT", "BORDER", "PROGRESS_BG", "PROGRESS_FILL"]
THEME_PRESETS = {
    "warm": {
        "BG": "#e2d4c0",
        "CARD": "#f0e8d8",
        "CARD_ALT": "#e8dcc8",
        "TEXT": "#28180a",
        "MUTED": "#7a6448",
        "ACCENT": "#c07828",
        "BORDER": "#c8b898",
        "PROGRESS_BG": "#d4c4a8",
        "PROGRESS_FILL": "#c07828",
    },
    "forest": {
        "BG": "#bcd0bc",
        "CARD": "#d4e8d4",
        "CARD_ALT": "#c8e0c8",
        "TEXT": "#101e10",
        "MUTED": "#406040",
        "ACCENT": "#2e8830",
        "BORDER": "#98c098",
        "PROGRESS_BG": "#b0ccb0",
        "PROGRESS_FILL": "#389838",
    },
    "ocean": {
        "BG": "#b8cede",
        "CARD": "#cce0f0",
        "CARD_ALT": "#c0d8ec",
        "TEXT": "#080e18",
        "MUTED": "#305878",
        "ACCENT": "#1468a0",
        "BORDER": "#88b0cc",
        "PROGRESS_BG": "#a8c4d8",
        "PROGRESS_FILL": "#1878b8",
    },
    "rose": {
        "BG": "#e0c0c0",
        "CARD": "#f4d8d8",
        "CARD_ALT": "#eccece",
        "TEXT": "#200808",
        "MUTED": "#804040",
        "ACCENT": "#b83040",
        "BORDER": "#cc9898",
        "PROGRESS_BG": "#d4aaaa",
        "PROGRESS_FILL": "#c83848",
    },
    "dark": {
        "BG": "#141414",
        "CARD": "#202020",
        "CARD_ALT": "#282828",
        "TEXT": "#e4ddd4",
        "MUTED": "#888070",
        "ACCENT": "#d4904a",
        "BORDER": "#383028",
        "PROGRESS_BG": "#282420",
        "PROGRESS_FILL": "#c07830",
    },
}
DEFAULT_ITEMS = [
    {"text": "Define the next concrete task"},
    {"text": "Finish what is already in progress"},
    {"text": "Avoid switching context without reason"},
]
URL_RE = re.compile(r"(https?://[^\s]+)")

IS_WINDOWS = platform.system() == "Windows"


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


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def get_data_path() -> Path:
    system = platform.system().lower()
    base = Path.home() / "AppData" / "Roaming" / APP_NAME if system == "windows" else Path.home() / f".{APP_NAME}"
    base.mkdir(parents=True, exist_ok=True)
    return base / "checklist.json"


def normalize_tab_name(value: str) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    return cleaned[:40] if cleaned else ""


def default_tabs() -> list[dict]:
    return [{"name": "General", "priority": "normal"}]


def parse_created_at(value: str | None) -> datetime:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.now()


def parse_due_date(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def format_dt(value: str | None) -> str:
    dt = parse_due_date(value) if value else None
    if dt is None:
        return str(value or "")
    return dt.strftime("%Y-%m-%d %H:%M")


def format_remaining_time(value: str | None) -> str:
    due = parse_due_date(value)
    if due is None:
        return ""
    delta = due - datetime.now()
    total_minutes = int(delta.total_seconds() // 60)
    overdue = total_minutes < 0
    total_minutes = abs(total_minutes)
    days, rem = divmod(total_minutes, 1440)
    hours, minutes = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    label = " ".join(parts)
    return f"overdue {label}" if overdue else f"{label} left"


def due_progress_ratio(item: dict) -> float | None:
    due = parse_due_date(item.get("due_date"))
    if due is None:
        return None
    created = parse_created_at(item.get("created_at"))
    total = (due - created).total_seconds()
    elapsed = (datetime.now() - created).total_seconds()
    if total <= 0:
        return 1.0
    return max(0.0, min(1.0, elapsed / total))


def normalize_hex(value: str, fallback: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return text.lower()
    return fallback


def make_item(
    item_id: int,
    text: str,
    *,
    created_at: str | None = None,
    current: bool = False,
    extra_info: str = "",
    completed_at: str = "",
    due_date: str = "",
    tab: str = "General",
) -> dict:
    return {
        "id": int(item_id),
        "text": str(text).strip(),
        "done": False,
        "current": bool(current),
        "created_at": created_at or now_stamp(),
        "completed_at": str(completed_at or ""),
        "extra_info": str(extra_info or ""),
        "due_date": str(due_date or ""),
        "tab": normalize_tab_name(tab) or "General",
    }


def open_url(url: str) -> None:
    webbrowser.open(url)


class DataStore:
    def __init__(self) -> None:
        self.path = get_data_path()

    def load(self) -> tuple[list[dict], list[dict], dict]:
        defaults = [make_item(index + 1, item["text"], created_at=now_stamp()) for index, item in enumerate(DEFAULT_ITEMS)]
        if not self.path.exists():
            return defaults, [], {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return defaults, [], {}
        active_raw = raw.get("active", defaults)
        history_raw = raw.get("history", [])
        settings = raw.get("settings", {}) if isinstance(raw.get("settings", {}), dict) else {}
        active = [item for index, entry in enumerate(active_raw) if (item := self._normalize_active(entry, index))]
        history = [item for index, entry in enumerate(history_raw) if (item := self._normalize_history(entry, index))]
        return active or defaults, history, settings

    def save(self, active: list[dict], history: list[dict], settings: dict) -> None:
        payload = {"active": active, "history": history[:250], "settings": settings}
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def normalize_tabs(self, raw_tabs) -> list[dict]:
        tabs: list[dict] = []
        seen: set[str] = set()
        if isinstance(raw_tabs, list):
            for tab in raw_tabs:
                if not isinstance(tab, dict):
                    continue
                name = normalize_tab_name(tab.get("name", ""))
                if not name or name in seen:
                    continue
                priority = str(tab.get("priority", "normal")).lower()
                if priority not in TAB_PRIORITY_ORDER:
                    priority = "normal"
                tabs.append({"name": name, "priority": priority})
                seen.add(name)
        if not tabs:
            tabs = default_tabs()
        if "General" not in {tab["name"] for tab in tabs}:
            tabs.insert(0, {"name": "General", "priority": "normal"})
        return tabs

    def _normalize_active(self, item: dict, index: int) -> dict | None:
        if not isinstance(item, dict):
            return None
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
            "tab": normalize_tab_name(item.get("tab", "General")) or "General",
        }

    def _normalize_history(self, item: dict, index: int) -> dict | None:
        if not isinstance(item, dict):
            return None
        text = str(item.get("text", "")).strip()
        if not text:
            return None
        return {
            "id": int(item.get("id", index + 1000)),
            "text": text,
            "done": True,
            "current": False,
            "created_at": str(item.get("created_at", now_stamp())),
            "completed_at": str(item.get("completed_at", now_stamp())),
            "extra_info": str(item.get("extra_info", "")),
            "due_date": str(item.get("due_date", "")),
            "tab": normalize_tab_name(item.get("tab", "General")) or "General",
        }


class TaskDialog(QDialog):
    def __init__(self, parent: QWidget, tabs: list[dict], item: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add task" if item is None else "Edit task")
        self.setModal(True)
        self.resize(560, 420)
        data = item or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("What are you doing now?")
        self.text_edit.setPlainText(data.get("text", ""))
        self.text_edit.setTabChangesFocus(True)
        form.addRow("Task", self.text_edit)

        self.tab_combo = QComboBox()
        tab_names = [tab["name"] for tab in tabs]
        self.tab_combo.addItems(tab_names)
        current_tab = normalize_tab_name(data.get("tab", "General")) or "General"
        if current_tab not in tab_names:
            self.tab_combo.addItem(current_tab)
        self.tab_combo.setCurrentText(current_tab)
        form.addRow("Tab", self.tab_combo)

        self.current_check = QCheckBox("Current task")
        self.current_check.setChecked(bool(data.get("current", False)))
        form.addRow("", self.current_check)

        self.due_edit = QDateTimeEdit()
        self.due_edit.setCalendarPopup(True)
        self.due_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.has_due_check = QCheckBox("Enable due date")
        due = parse_due_date(data.get("due_date", ""))
        self.has_due_check.setChecked(due is not None)
        due_dt = QDateTime.currentDateTime() if due is None else QDateTime.fromString(due.strftime("%Y-%m-%d %H:%M"), "yyyy-MM-dd HH:mm")
        self.due_edit.setDateTime(due_dt)
        self.due_edit.setEnabled(self.has_due_check.isChecked())
        self.has_due_check.toggled.connect(self.due_edit.setEnabled)
        due_wrap = QWidget()
        due_layout = QHBoxLayout(due_wrap)
        due_layout.setContentsMargins(0, 0, 0, 0)
        due_layout.addWidget(self.has_due_check)
        due_layout.addWidget(self.due_edit, 1)
        form.addRow("Due", due_wrap)

        self.extra_edit = QPlainTextEdit()
        self.extra_edit.setPlaceholderText("Optional extra info")
        self.extra_edit.setPlainText(data.get("extra_info", ""))
        form.addRow("Extra info", self.extra_edit)
        layout.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        save = QPushButton("Create" if item is None else "Save")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

    def payload(self) -> dict | None:
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Missing task", "Task text cannot be empty.")
            return None
        due_text = ""
        if self.has_due_check.isChecked():
            due_text = self.due_edit.dateTime().toString("yyyy-MM-dd HH:mm")
        return {
            "text": text,
            "tab": self.tab_combo.currentText(),
            "current": self.current_check.isChecked(),
            "due_date": due_text,
            "extra_info": self.extra_edit.toPlainText().strip(),
        }

    def accept(self) -> None:
        if self.payload() is None:
            return
        super().accept()


class AddTabDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add tab")
        self.setModal(True)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["high", "normal", "low"])
        self.priority_combo.setCurrentText("normal")
        form.addRow("Name", self.name_edit)
        form.addRow("Priority", self.priority_combo)
        layout.addLayout(form)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        create = QPushButton("Create")
        cancel.clicked.connect(self.reject)
        create.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(create)
        layout.addLayout(actions)

    def values(self) -> tuple[str, str] | None:
        name = normalize_tab_name(self.name_edit.text())
        if not name:
            QMessageBox.warning(self, "Missing name", "Tab name cannot be empty.")
            return None
        return name, self.priority_combo.currentText()

    def accept(self) -> None:
        if self.values() is None:
            return
        super().accept()


class ColorPreview(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(20, 20)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"background:{color}; border:1px solid #999; border-radius:4px;")


class TaskRowWidget(QWidget):
    complete_requested = Signal(int)
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    current_toggled = Signal(int)

    def __init__(self, item: dict, accessibility: bool, alt: bool = False, palette: dict | None = None) -> None:
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.item = item
        self._palette = palette or {}
        self.setObjectName("taskCardAlt" if alt else "taskCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        done_btn = QPushButton("")
        done_btn.setObjectName("doneBtn")
        done_btn.setFixedSize(28, 28)
        done_btn.clicked.connect(lambda: self.complete_requested.emit(self.item["id"]))
        top.addWidget(done_btn, 0, Qt.AlignVCenter)

        text_wrap = QVBoxLayout()
        text_wrap.setSpacing(4)
        self.text_label = QLabel()
        self.text_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.text_label.setOpenExternalLinks(False)
        self.text_label.linkActivated.connect(open_url)
        self.text_label.setWordWrap(True)
        escaped = self.item.get("text", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.text_label.setText(URL_RE.sub(r'<a href="\1">\1</a>', escaped))
        text_wrap.addWidget(self.text_label)

        meta_parts = [f"tab {self.item.get('tab', 'General')}", f"added {self.item.get('created_at', '')}"]
        if self.item.get("due_date"):
            meta_parts.append(f"due {format_dt(self.item['due_date'])} ({format_remaining_time(self.item['due_date'])})")
        if self.item.get("extra_info"):
            meta_parts.append("extra info")
        meta = QLabel("  ·  ".join(meta_parts))
        meta.setObjectName("metaLabel")
        meta.setWordWrap(True)
        text_wrap.addWidget(meta)
        top.addLayout(text_wrap, 1)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        current_btn = QPushButton("◉" if self.item.get("current") else "◎")
        current_btn.setObjectName("iconBtn")
        current_btn.setFixedSize(34, 34)
        current_btn.clicked.connect(lambda: self.current_toggled.emit(self.item["id"]))
        edit_btn = QPushButton("✎")
        edit_btn.setObjectName("iconBtn")
        edit_btn.setFixedSize(34, 34)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.item["id"]))
        delete_btn = QPushButton("×")
        delete_btn.setObjectName("iconBtn")
        delete_btn.setFixedSize(34, 34)
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.item["id"]))
        self.drag_handle = DragHandle()
        actions.addWidget(current_btn)
        actions.addWidget(edit_btn)
        actions.addWidget(delete_btn)
        actions.addWidget(self.drag_handle)
        top.addLayout(actions, 0)
        outer.addLayout(top)

        ratio = due_progress_ratio(self.item)
        if ratio is not None:
            due_dt = parse_due_date(self.item.get("due_date"))
            is_overdue = due_dt is not None and due_dt < datetime.now()
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(int(ratio * 1000))
            bar.setTextVisible(False)
            bar.setFixedHeight(7 if accessibility else 5)
            if is_overdue:
                card = self._palette.get("CARD", "#ffffff")
                r, g, b = int(card[1:3], 16), int(card[3:5], 16), int(card[5:7], 16)
                is_dark_theme = (r * 299 + g * 587 + b * 114) / 1000 < 128
                if is_dark_theme:
                    bar.setStyleSheet(
                        "QProgressBar { background: #3a1010; border: none; border-radius: 3px; }"
                        "QProgressBar::chunk { background: #cc2828; border-radius: 3px; }"
                    )
                else:
                    bar.setStyleSheet(
                        "QProgressBar { background: #f5d5d5; border: none; border-radius: 3px; }"
                        "QProgressBar::chunk { background: #d94f4f; border-radius: 3px; }"
                    )
            outer.addWidget(bar)


class HistoryRowWidget(QWidget):
    restore_requested = Signal(int)

    def __init__(self, item: dict) -> None:
        super().__init__()
        self.item = item
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 8)
        layout.setSpacing(4)
        top = QHBoxLayout()
        text = QLabel(item.get("text", ""))
        text.setWordWrap(True)
        top.addWidget(text, 1)
        restore = QPushButton("Restore")
        restore.clicked.connect(lambda: self.restore_requested.emit(self.item["id"]))
        top.addWidget(restore)
        layout.addLayout(top)
        meta_parts = [f"tab {item.get('tab', 'General')}", f"added {item.get('created_at', '')}"]
        if item.get("completed_at"):
            meta_parts.append(f"done {item['completed_at']}")
        if item.get("due_date"):
            meta_parts.append(f"due {format_dt(item['due_date'])}")
        meta = QLabel("  ·  ".join(meta_parts))
        meta.setObjectName("metaLabel")
        layout.addWidget(meta)


class FocusListWidget(QListWidget):
    dropped = Signal()

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        self.dropped.emit()


class DragHandle(QLabel):
    """Drag handle that initiates a QListWidget drag when the user pulls it."""

    def __init__(self) -> None:
        super().__init__("⠿")
        self.setObjectName("dragHandle")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(24, 34)
        self.setCursor(Qt.SizeVerCursor)
        self._start: QPointF | None = None
        self._list_widget: FocusListWidget | None = None
        self._item_id: int = -1

    def bind(self, list_widget: FocusListWidget, item_id: int) -> None:
        self._list_widget = list_widget
        self._item_id = item_id

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._start = event.position()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.LeftButton) or self._start is None or self._list_widget is None:
            return
        pos = event.position()
        if abs(pos.x() - self._start.x()) + abs(pos.y() - self._start.y()) < QApplication.startDragDistance():
            return
        for i in range(self._list_widget.count()):
            li = self._list_widget.item(i)
            if li and li.data(Qt.UserRole) == self._item_id:
                self._list_widget.setCurrentItem(li)
                break
        self._list_widget.startDrag(Qt.MoveAction)
        self._start = None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(460, 740)
        self.store = DataStore()
        self.items, self.history, self.settings = self.store.load()
        self.tabs = self.store.normalize_tabs(self.settings.get("tabs", default_tabs()))
        for item in self.items + self.history:
            self.ensure_tab_exists(item.get("tab", "General"))
        self.settings["tabs"] = self.tabs

        self.theme_name = self.settings.get("theme_name", "warm")
        self.custom_palette = self.settings.get("custom_palette", {}) if isinstance(self.settings.get("custom_palette", {}), dict) else {}
        self.font_scale = float(self.settings.get("font_scale", 1.0) or 1.0)
        self.accessibility_mode = bool(self.settings.get("accessibility_mode", False))
        self.active_tab = "All"
        self.active_view = "main"
        self.undo_item: dict | None = None
        self.undo_timer = QTimer(self)
        self.undo_timer.setInterval(3000)
        self.undo_timer.setSingleShot(True)
        self.undo_timer.timeout.connect(self.finalize_pending_completion)

        self._build_ui()
        self.apply_theme(self.theme_name, persist=False)
        self.refresh_all()
        self.set_on_top(bool(self.settings.get("always_on_top", True)), persist=False)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setMouseTracking(True)
        central.installEventFilter(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        self.title_label = QLabel(APP_NAME)
        self.title_label.setObjectName("titleLabel")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.header_actions = QWidget()
        header_actions_layout = QHBoxLayout(self.header_actions)
        header_actions_layout.setContentsMargins(0, 0, 0, 0)
        header_actions_layout.setSpacing(6)
        self.add_btn = QPushButton("+ add")
        self.add_tab_btn = QPushButton("+ add tab")
        self.history_btn = QPushButton("history")
        self.tools_btn = QPushButton("tools")
        self.on_top_btn = QPushButton("on top")
        self.on_top_btn.setCheckable(True)
        for widget in (self.add_btn, self.add_tab_btn, self.history_btn, self.tools_btn, self.on_top_btn):
            header_actions_layout.addWidget(widget)
        self.header_actions.setVisible(False)
        header.addWidget(self.header_actions)
        root.addLayout(header)

        self.tab_bar = QHBoxLayout()
        self.tab_bar.setSpacing(6)
        root.addLayout(self.tab_bar)

        self.loading_label = QLabel("Loading...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setVisible(False)
        root.addWidget(self.loading_label)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        self.main_page = QWidget()
        main_layout = QVBoxLayout(self.main_page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.task_list = FocusListWidget()
        self.task_list.setDragDropMode(QListWidget.InternalMove)
        self.task_list.setSelectionMode(QListWidget.SingleSelection)
        self.task_list.setSpacing(8)
        self.task_list.dropped.connect(self.sync_order_from_list)
        main_layout.addWidget(self.task_list)
        self.pages.addWidget(self.main_page)

        self.history_page = QWidget()
        history_layout = QVBoxLayout(self.history_page)
        history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_list = QListWidget()
        self.history_list.setSelectionMode(QListWidget.NoSelection)
        self.history_list.setSpacing(8)
        history_layout.addWidget(self.history_list)
        self.pages.addWidget(self.history_page)

        self.tools_scroll = QScrollArea()
        self.tools_scroll.setWidgetResizable(True)
        self.tools_body = QWidget()
        self.tools_layout = QVBoxLayout(self.tools_body)
        self.tools_layout.setContentsMargins(4, 4, 4, 4)
        self.tools_layout.setSpacing(12)
        self.tools_scroll.setWidget(self.tools_body)
        self.pages.addWidget(self.tools_scroll)
        self._build_tools()

        footer = QHBoxLayout()
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setVisible(False)
        self.undo_btn.clicked.connect(self.undo_complete)
        self.footer_label = QLabel("")
        footer.addWidget(self.undo_btn)
        footer.addStretch(1)
        footer.addWidget(self.footer_label)
        root.addLayout(footer)

        self.add_btn.clicked.connect(self.open_add_task)
        self.add_tab_btn.clicked.connect(self.open_add_tab_dialog)
        self.history_btn.clicked.connect(lambda: self.switch_view("main" if self.active_view == "history" else "history"))
        self.tools_btn.clicked.connect(lambda: self.switch_view("main" if self.active_view == "tools" else "tools"))
        self.on_top_btn.clicked.connect(self.toggle_on_top)

    def _build_tools(self) -> None:
        title = QLabel("Tools")
        title.setObjectName("sectionTitle")
        self.tools_layout.addWidget(title)

        close_btn = QPushButton("Back to list")
        close_btn.clicked.connect(lambda: self.switch_view("main"))
        self.tools_layout.addWidget(close_btn)

        system_box = QFrame()
        system_layout = QVBoxLayout(system_box)
        system_layout.setContentsMargins(12, 12, 12, 12)
        system_title = QLabel("System")
        system_title.setObjectName("sectionTitle")
        system_layout.addWidget(system_title)
        self.startup_check = QCheckBox("Launch on login")
        self.startup_check.setChecked(self.startup_enabled())
        self.startup_check.toggled.connect(self.toggle_startup)
        system_layout.addWidget(self.startup_check)
        export_btn = QPushButton("Export JSON")
        import_btn = QPushButton("Import JSON")
        export_btn.clicked.connect(self.export_json)
        import_btn.clicked.connect(self.import_json)
        system_layout.addWidget(export_btn)
        system_layout.addWidget(import_btn)
        self.tools_layout.addWidget(system_box)

        appearance = QFrame()
        appearance_layout = QVBoxLayout(appearance)
        appearance_layout.setContentsMargins(12, 12, 12, 12)
        appearance_title = QLabel("Appearance")
        appearance_title.setObjectName("sectionTitle")
        appearance_layout.addWidget(appearance_title)
        presets_row = QHBoxLayout()
        presets_row.setSpacing(4)
        for name in THEME_PRESETS:
            preset = THEME_PRESETS[name]
            btn = QPushButton(name)
            btn.setStyleSheet(
                f"QPushButton {{ background: {preset['CARD']}; color: {preset['TEXT']};"
                f" border: 2px solid {preset['ACCENT']}; border-radius: 8px; padding: 4px 6px;"
                f" font-size: 9pt; }}"
                f"QPushButton:hover {{ background: {preset['ACCENT']}; color: {preset['CARD']}; }}"
            )
            btn.clicked.connect(lambda checked=False, theme=name: self.apply_theme(theme))
            presets_row.addWidget(btn)
        appearance_layout.addLayout(presets_row)

        self.custom_color_inputs: dict[str, QLineEdit] = {}
        self.custom_previews: dict[str, ColorPreview] = {}
        grid = QGridLayout()
        for row, key in enumerate(THEME_KEYS):
            preview = ColorPreview()
            edit = QLineEdit()
            edit.textChanged.connect(lambda value, color_key=key: self.update_color_preview(color_key, value))
            self.custom_previews[key] = preview
            self.custom_color_inputs[key] = edit
            grid.addWidget(QLabel(key.lower()), row, 0)
            grid.addWidget(preview, row, 1)
            grid.addWidget(edit, row, 2)
        appearance_layout.addLayout(grid)
        custom_btn = QPushButton("Apply custom")
        custom_btn.clicked.connect(self.apply_custom_theme)
        appearance_layout.addWidget(custom_btn)

        font_row = QHBoxLayout()
        font_row.setSpacing(8)
        font_row.addWidget(QLabel("Font scale"))
        font_row.addStretch(1)
        minus_btn = QPushButton("−")
        minus_btn.setObjectName("iconBtn")
        minus_btn.setFixedSize(34, 34)
        minus_btn.clicked.connect(lambda: self.set_font_scale(round(self.font_scale - 0.1, 1)))
        self.font_scale_label = QLabel(f"{int(round(self.font_scale * 100))}%")
        self.font_scale_label.setAlignment(Qt.AlignCenter)
        self.font_scale_label.setFixedWidth(52)
        plus_btn = QPushButton("+")
        plus_btn.setObjectName("iconBtn")
        plus_btn.setFixedSize(34, 34)
        plus_btn.clicked.connect(lambda: self.set_font_scale(round(self.font_scale + 0.1, 1)))
        font_row.addWidget(minus_btn)
        font_row.addWidget(self.font_scale_label)
        font_row.addWidget(plus_btn)
        appearance_layout.addLayout(font_row)
        self.accessibility_check = QCheckBox("Accessibility mode")
        self.accessibility_check.setChecked(self.accessibility_mode)
        self.accessibility_check.toggled.connect(self.toggle_accessibility)
        appearance_layout.addWidget(self.accessibility_check)
        self.tools_layout.addWidget(appearance)

        self.tab_manager_box = QFrame()
        self.tab_manager_layout = QVBoxLayout(self.tab_manager_box)
        self.tab_manager_layout.setContentsMargins(12, 12, 12, 12)
        tabs_title = QLabel("Tabs")
        tabs_title.setObjectName("sectionTitle")
        self.tab_manager_layout.addWidget(tabs_title)
        self.tab_manager_list = QVBoxLayout()
        self.tab_manager_layout.addLayout(self.tab_manager_list)
        self.tools_layout.addWidget(self.tab_manager_box)
        self.tools_layout.addStretch(1)

    def eventFilter(self, watched, event):
        if watched is self.centralWidget():
            if event.type() == QEvent.Enter:
                self.header_actions.setVisible(True)
            elif event.type() == QEvent.Leave:
                self.header_actions.setVisible(False)
        return super().eventFilter(watched, event)

    def palette_values(self) -> dict:
        if self.theme_name == "custom":
            palette = THEME_PRESETS["warm"].copy()
            for key in THEME_KEYS:
                palette[key] = normalize_hex(self.custom_palette.get(key, palette[key]), palette[key])
            return palette
        return THEME_PRESETS.get(self.theme_name, THEME_PRESETS["warm"]).copy()

    def apply_theme(self, theme_name: str, persist: bool = True) -> None:
        self.theme_name = theme_name
        if persist:
            self.settings["theme_name"] = theme_name
            self.settings["custom_palette"] = self.custom_palette
            self.save()
        self.refresh_styles()
        self.load_custom_theme_inputs()

    def load_custom_theme_inputs(self) -> None:
        palette_values = self.palette_values()
        for key in THEME_KEYS:
            value = self.custom_palette.get(key, palette_values[key]) if self.theme_name == "custom" else palette_values[key]
            self.custom_color_inputs[key].blockSignals(True)
            self.custom_color_inputs[key].setText(value)
            self.custom_color_inputs[key].blockSignals(False)
            self.update_color_preview(key, value)

    def update_color_preview(self, key: str, value: str) -> None:
        fallback = self.palette_values().get(key, "#ffffff")
        self.custom_previews[key].set_color(normalize_hex(value, fallback))

    def apply_custom_theme(self) -> None:
        base = THEME_PRESETS["warm"]
        self.custom_palette = {key: normalize_hex(self.custom_color_inputs[key].text(), base[key]) for key in THEME_KEYS}
        self.theme_name = "custom"
        self.settings["theme_name"] = "custom"
        self.settings["custom_palette"] = self.custom_palette
        self.save()
        self.refresh_styles()

    def scaled(self, size: int) -> int:
        factor = self.font_scale * (1.08 if self.accessibility_mode else 1.0)
        return max(8, int(round(size * factor)))

    def refresh_styles(self) -> None:
        p = self.palette_values()
        QApplication.instance().setStyleSheet(
            f"""
            /* ── Base ─────────────────────────────────────────── */
            QWidget {{
                background: {p['BG']};
                color: {p['TEXT']};
                font-size: {self.scaled(10)}pt;
                font-family: "Segoe UI", system-ui, sans-serif;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
            QCheckBox {{
                background: transparent;
                border: none;
                spacing: 8px;
            }}

            /* ── Cards / frames ───────────────────────────────── */
            QFrame {{
                background: {p['CARD']};
                border: 1px solid {p['BORDER']};
                border-radius: 14px;
            }}
            QWidget#taskCard {{
                background: {p['CARD']};
                border: 1px solid {p['BORDER']};
                border-radius: 14px;
            }}
            QWidget#taskCardAlt {{
                background: {p['CARD_ALT']};
                border: 1px solid {p['BORDER']};
                border-radius: 14px;
            }}

            /* ── List widgets ─────────────────────────────────── */
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                background: transparent;
                border: none;
                padding: 0px;
            }}
            QListWidget::item:selected,
            QListWidget::item:hover {{
                background: transparent;
            }}

            /* ── Buttons ──────────────────────────────────────── */
            QPushButton {{
                background: {p['CARD_ALT']};
                color: {p['TEXT']};
                border: 1px solid {p['BORDER']};
                border-radius: 8px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{
                background: {p['BORDER']};
                border-color: {p['ACCENT']};
            }}
            QPushButton:pressed {{
                background: {p['ACCENT']};
                border-color: {p['ACCENT']};
            }}
            QPushButton:checked {{
                background: {p['ACCENT']};
                border-color: {p['ACCENT']};
                font-weight: 600;
            }}
            QPushButton:disabled {{
                color: {p['MUTED']};
                border-color: {p['BORDER']};
            }}
            QPushButton#tabBtn {{
                border-radius: 12px;
                padding: 4px 14px;
                font-size: {self.scaled(9)}pt;
            }}
            QPushButton#iconBtn {{
                font-size: {self.scaled(14)}pt;
                padding: 2px;
                border-radius: 8px;
            }}
            QPushButton#doneBtn {{
                background: transparent;
                border: 2px solid {p['BORDER']};
                border-radius: 14px;
                padding: 0px;
            }}
            QPushButton#doneBtn:hover {{
                border-color: {p['ACCENT']};
                background: transparent;
            }}
            QPushButton#doneBtn:pressed {{
                background: {p['ACCENT']};
                border-color: {p['ACCENT']};
            }}

            /* ── Labels ───────────────────────────────────────── */
            QLabel#titleLabel {{
                font-family: "Georgia";
                font-size: {self.scaled(18)}pt;
                font-style: italic;
                font-weight: 400;
                color: {p['MUTED']};
                letter-spacing: 1px;
            }}
            QLabel#sectionTitle {{
                font-size: {self.scaled(9)}pt;
                font-weight: 700;
                color: {p['MUTED']};
                letter-spacing: 1px;
                padding-bottom: 6px;
            }}
            QLabel#metaLabel {{
                color: {p['MUTED']};
                font-size: {self.scaled(8)}pt;
            }}
            QLabel#dragHandle {{
                color: {p['MUTED']};
                font-size: {self.scaled(16)}pt;
            }}

            /* ── Inputs ───────────────────────────────────────── */
            QLineEdit, QPlainTextEdit, QDateTimeEdit {{
                background: {p['CARD']};
                color: {p['TEXT']};
                border: 1px solid {p['BORDER']};
                border-radius: 8px;
                padding: 6px 10px;
                selection-background-color: {p['ACCENT']};
            }}
            QLineEdit:focus, QPlainTextEdit:focus, QDateTimeEdit:focus {{
                border-color: {p['ACCENT']};
            }}

            /* ── ComboBox ─────────────────────────────────────── */
            QComboBox {{
                background: {p['CARD_ALT']};
                color: {p['TEXT']};
                border: 1px solid {p['BORDER']};
                border-radius: 8px;
                padding: 5px 10px;
            }}
            QComboBox:focus {{
                border-color: {p['ACCENT']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {p['CARD']};
                color: {p['TEXT']};
                border: 1px solid {p['BORDER']};
                border-radius: 8px;
                selection-background-color: {p['ACCENT']};
            }}

            /* ── SpinBox ──────────────────────────────────────── */
            QSpinBox {{
                background: {p['CARD_ALT']};
                color: {p['TEXT']};
                border: 1px solid {p['BORDER']};
                border-radius: 8px;
                padding: 5px 8px;
            }}
            QSpinBox:focus {{
                border-color: {p['ACCENT']};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                border: none;
                background: transparent;
                width: 16px;
            }}

            /* ── CheckBox ─────────────────────────────────────── */
            QCheckBox::indicator {{
                width: 15px;
                height: 15px;
                border: 1.5px solid {p['BORDER']};
                border-radius: 4px;
                background: {p['CARD']};
            }}
            QCheckBox::indicator:checked {{
                background: {p['ACCENT']};
                border-color: {p['ACCENT']};
            }}

            /* ── Progress bar ─────────────────────────────────── */
            QProgressBar {{
                background: {p['PROGRESS_BG']};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {p['PROGRESS_FILL']};
                border-radius: 3px;
            }}

            /* ── Scrollbars ───────────────────────────────────── */
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {p['BORDER']};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {p['MUTED']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {p['BORDER']};
                border-radius: 3px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {p['MUTED']};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}

            /* ── Scroll area ──────────────────────────────────── */
            QScrollArea {{
                background: {p['BG']};
                border: none;
            }}
            """
        )
        self.refresh_all()

    def set_font_scale(self, value: float) -> None:
        self.font_scale = max(0.8, min(1.8, value))
        self.settings["font_scale"] = self.font_scale
        self.save()
        if hasattr(self, "font_scale_label"):
            self.font_scale_label.setText(f"{int(round(self.font_scale * 100))}%")
        self.refresh_styles()

    def toggle_accessibility(self, checked: bool) -> None:
        self.accessibility_mode = bool(checked)
        self.settings["accessibility_mode"] = self.accessibility_mode
        self.save()
        self.refresh_styles()

    def switch_view(self, view: str) -> None:
        self.loading_label.setVisible(True)
        self.pages.setVisible(False)
        self.active_view = view
        QTimer.singleShot(1, self._finish_switch_view)

    def _finish_switch_view(self) -> None:
        if self.active_view == "main":
            self.pages.setCurrentWidget(self.main_page)
            self.render_tab_bar()
            self.render_main()
        elif self.active_view == "history":
            self.pages.setCurrentWidget(self.history_page)
            self.render_history()
        else:
            self.pages.setCurrentWidget(self.tools_scroll)
            self.render_tab_manager()
        self.pages.setVisible(True)
        self.loading_label.setVisible(False)
        self.update_footer()

    def refresh_all(self) -> None:
        self.render_tab_bar()
        if self.active_view == "history":
            self.pages.setCurrentWidget(self.history_page)
            self.render_history()
        elif self.active_view == "tools":
            self.pages.setCurrentWidget(self.tools_scroll)
            self.render_tab_manager()
        else:
            self.pages.setCurrentWidget(self.main_page)
            self.render_main()
        self.load_custom_theme_inputs()
        self.update_footer()

    def render_tab_bar(self) -> None:
        while self.tab_bar.count():
            item = self.tab_bar.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        all_btn = QPushButton("All")
        all_btn.setObjectName("tabBtn")
        all_btn.setCheckable(True)
        all_btn.setChecked(self.active_tab == "All")
        all_btn.clicked.connect(lambda: self.set_active_tab("All"))
        self.tab_bar.addWidget(all_btn)
        for tab in self.tabs:
            btn = QPushButton(tab["name"])
            btn.setObjectName("tabBtn")
            btn.setCheckable(True)
            btn.setChecked(self.active_tab == tab["name"])
            btn.clicked.connect(lambda checked=False, name=tab["name"]: self.set_active_tab(name))
            self.tab_bar.addWidget(btn)
        self.tab_bar.addStretch(1)

    def set_active_tab(self, name: str) -> None:
        play_click()
        self.active_tab = name
        if self.active_view == "main":
            self.render_tab_bar()
            self.render_main()
        else:
            self.switch_view("main")

    def visible_items(self) -> list[dict]:
        if self.active_tab != "All":
            return [item for item in self.items if item.get("tab", "General") == self.active_tab]
        current = [item for item in self.items if item.get("current")]
        rest = [item for item in self.items if not item.get("current")]
        return current + rest

    def render_main(self) -> None:
        self.task_list.clear()
        for index, item in enumerate(self.visible_items()):
            list_item = QListWidgetItem()
            list_item.setData(Qt.UserRole, item["id"])
            list_item.setFlags(list_item.flags() | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
            row = TaskRowWidget(item, self.accessibility_mode, alt=index % 2 == 1, palette=self.palette_values())
            row.drag_handle.bind(self.task_list, item["id"])
            row.complete_requested.connect(self.complete_item)
            row.edit_requested.connect(self.open_edit_task)
            row.delete_requested.connect(self.delete_item)
            row.current_toggled.connect(self.toggle_current)
            list_item.setSizeHint(row.sizeHint())
            self.task_list.addItem(list_item)
            self.task_list.setItemWidget(list_item, row)

    def render_history(self) -> None:
        self.history_list.clear()
        for item in reversed(self.history):
            list_item = QListWidgetItem()
            list_item.setData(Qt.UserRole, item["id"])
            row = HistoryRowWidget(item)
            row.restore_requested.connect(self.restore_history_item)
            list_item.setSizeHint(row.sizeHint())
            self.history_list.addItem(list_item)
            self.history_list.setItemWidget(list_item, row)

    def ensure_tab_exists(self, name: str) -> str:
        name = normalize_tab_name(name) or "General"
        for tab in self.tabs:
            if tab["name"] == name:
                return name
        self.tabs.append({"name": name, "priority": "normal"})
        return name

    def tab_priority(self, name: str) -> int:
        for tab in self.tabs:
            if tab["name"] == name:
                return TAB_PRIORITY_ORDER.get(tab["priority"], 1)
        return TAB_PRIORITY_ORDER["normal"]

    def render_tab_manager(self) -> None:
        while self.tab_manager_list.count():
            item = self.tab_manager_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, tab in enumerate(self.tabs):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(QLabel(tab["name"]), 1)
            priority = QComboBox()
            priority.addItems(["high", "normal", "low"])
            priority.setCurrentText(tab["priority"])
            priority.currentTextChanged.connect(lambda value, i=index: self.update_tab_priority(i, value))
            up = QPushButton("↑")
            down = QPushButton("↓")
            up.clicked.connect(lambda checked=False, i=index: self.move_tab(i, -1))
            down.clicked.connect(lambda checked=False, i=index: self.move_tab(i, 1))
            remove = QPushButton("×")
            remove.setEnabled(tab["name"] != "General")
            remove.clicked.connect(lambda checked=False, i=index: self.remove_tab(i))
            layout.addWidget(priority)
            layout.addWidget(up)
            layout.addWidget(down)
            layout.addWidget(remove)
            self.tab_manager_list.addWidget(row)

    def update_tab_priority(self, index: int, priority: str) -> None:
        if index < 0 or index >= len(self.tabs):
            return
        self.tabs[index]["priority"] = priority if priority in TAB_PRIORITY_ORDER else "normal"
        self.settings["tabs"] = self.tabs
        self.save()
        self.refresh_all()

    def move_tab(self, index: int, delta: int) -> None:
        target = index + delta
        if index < 0 or target < 0 or index >= len(self.tabs) or target >= len(self.tabs):
            return
        self.tabs[index], self.tabs[target] = self.tabs[target], self.tabs[index]
        self.settings["tabs"] = self.tabs
        self.save()
        self.refresh_all()

    def remove_tab(self, index: int) -> None:
        if index < 0 or index >= len(self.tabs):
            return
        name = self.tabs[index]["name"]
        if name == "General":
            return
        del self.tabs[index]
        for item in self.items + self.history:
            if item.get("tab") == name:
                item["tab"] = "General"
        if self.active_tab == name:
            self.active_tab = "All"
        self.settings["tabs"] = self.tabs
        self.save()
        self.refresh_all()

    def open_add_tab_dialog(self) -> None:
        dialog = AddTabDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if values is None:
            return
        name, priority = values
        if name in {tab["name"] for tab in self.tabs}:
            QMessageBox.information(self, "Existing tab", "That tab already exists.")
            return
        self.tabs.append({"name": name, "priority": priority})
        self.settings["tabs"] = self.tabs
        self.save()
        self.refresh_all()

    def next_id(self) -> int:
        values = [item["id"] for item in self.items + self.history]
        return (max(values) + 1) if values else 1

    def open_add_task(self) -> None:
        dialog = TaskDialog(self, self.tabs)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.payload()
        if payload is None:
            return
        item = make_item(
            self.next_id(),
            payload["text"],
            created_at=now_stamp(),
            current=payload["current"],
            extra_info=payload["extra_info"],
            due_date=payload["due_date"],
            tab=self.ensure_tab_exists(payload["tab"]),
        )
        if item["current"]:
            for entry in self.items:
                entry["current"] = False
            self.items.insert(0, item)
        else:
            self.items.append(item)
        play_add()
        self.save()
        self.refresh_all()

    def open_edit_task(self, item_id: int) -> None:
        item = self.find_active(item_id)
        if item is None:
            return
        dialog = TaskDialog(self, self.tabs, item)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.payload()
        if payload is None:
            return
        item["text"] = payload["text"]
        item["tab"] = self.ensure_tab_exists(payload["tab"])
        item["extra_info"] = payload["extra_info"]
        item["due_date"] = payload["due_date"]
        if payload["current"]:
            self.promote_current(item_id)
        else:
            item["current"] = False
        self.save()
        self.refresh_all()

    def find_active(self, item_id: int) -> dict | None:
        for item in self.items:
            if item["id"] == item_id:
                return item
        return None

    def promote_current(self, item_id: int) -> None:
        item = self.find_active(item_id)
        if item is None:
            return
        for entry in self.items:
            entry["current"] = False
        item["current"] = True
        self.items = [item] + [entry for entry in self.items if entry["id"] != item_id]

    def toggle_current(self, item_id: int) -> None:
        item = self.find_active(item_id)
        if item is None:
            return
        if item.get("current"):
            item["current"] = False
        else:
            self.promote_current(item_id)
        self.save()
        self.refresh_all()

    def delete_item(self, item_id: int) -> None:
        item = self.find_active(item_id)
        if item is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete task",
            f"Delete this task?\n\n{item['text']}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.items = [entry for entry in self.items if entry["id"] != item_id]
        self.save()
        self.refresh_all()

    def complete_item(self, item_id: int) -> None:
        item = self.find_active(item_id)
        if item is None:
            return
        play_complete()
        self.undo_item = {**item, "completed_at": now_stamp(), "done": True, "current": False}
        self.items = [entry for entry in self.items if entry["id"] != item_id]
        self.undo_btn.setVisible(True)
        self.undo_timer.start()
        self.save()
        self.refresh_all()

    def undo_complete(self) -> None:
        if self.undo_item is None:
            return
        restored = dict(self.undo_item)
        restored["done"] = False
        restored["completed_at"] = ""
        self.items.insert(0, restored)
        self.undo_item = None
        self.undo_timer.stop()
        self.undo_btn.setVisible(False)
        self.save()
        self.refresh_all()

    def finalize_pending_completion(self) -> None:
        if self.undo_item is None:
            return
        self.history.append(dict(self.undo_item))
        self.undo_item = None
        self.undo_btn.setVisible(False)
        self.save()
        self.refresh_all()

    def restore_history_item(self, item_id: int) -> None:
        for index, item in enumerate(self.history):
            if item["id"] != item_id:
                continue
            restored = dict(item)
            restored["done"] = False
            restored["completed_at"] = ""
            self.items.append(restored)
            del self.history[index]
            self.save()
            self.refresh_all()
            return

    def sync_order_from_list(self) -> None:
        ordered_ids = [self.task_list.item(index).data(Qt.UserRole) for index in range(self.task_list.count())]
        visible_map = {item["id"]: item for item in self.visible_items()}
        reordered = [visible_map[item_id] for item_id in ordered_ids if item_id in visible_map]
        hidden = [item for item in self.items if item["id"] not in ordered_ids]
        self.items = reordered + hidden
        self.save()
        self.refresh_all()

    def update_footer(self) -> None:
        now = datetime.now()
        pending = len(self.items)
        today = 0
        month = 0
        year = 0
        for item in self.history:
            completed = parse_due_date(item.get("completed_at"))
            if completed is None:
                continue
            if completed.date() == now.date():
                today += 1
            if completed.year == now.year and completed.month == now.month:
                month += 1
            if completed.year == now.year:
                year += 1
        self.footer_label.setText(f"pending {pending}  ·  today {today}  ·  month {month}  ·  year {year}")

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON", str(Path.home() / "focus-export.json"), "JSON Files (*.json)")
        if not path:
            return
        payload = {"active": self.items, "history": self.history, "settings": self.settings}
        Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import JSON", str(Path.home()), "JSON Files (*.json)")
        if not path:
            return
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            QMessageBox.warning(self, "Import failed", "Could not read that JSON file.")
            return
        self.items = [item for index, entry in enumerate(raw.get("active", [])) if (item := self.store._normalize_active(entry, index))]
        self.history = [item for index, entry in enumerate(raw.get("history", [])) if (item := self.store._normalize_history(entry, index))]
        settings = raw.get("settings", {}) if isinstance(raw.get("settings", {}), dict) else {}
        self.settings.update(settings)
        self.tabs = self.store.normalize_tabs(self.settings.get("tabs", default_tabs()))
        self.settings["tabs"] = self.tabs
        self.save()
        self.refresh_all()

    def startup_path(self) -> Path | None:
        system = platform.system().lower()
        if system == "windows":
            return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "focus.cmd"
        if system == "linux":
            return Path.home() / ".config" / "autostart" / "focus.desktop"
        return None

    def startup_enabled(self) -> bool:
        path = self.startup_path()
        return bool(path and path.exists())

    def toggle_startup(self, checked: bool) -> None:
        path = self.startup_path()
        if path is None:
            QMessageBox.information(self, "Not available", "Startup is currently implemented for Windows and Linux.")
            self.startup_check.blockSignals(True)
            self.startup_check.setChecked(False)
            self.startup_check.blockSignals(False)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if checked:
            script = Path(sys.argv[0]).resolve()
            if platform.system().lower() == "windows":
                path.write_text(f'@echo off\r\npython "{script}"\r\n', encoding="utf-8")
            else:
                path.write_text(
                    "[Desktop Entry]\nType=Application\nName=focus\nExec=python3 \"" + str(script) + "\"\nX-GNOME-Autostart-enabled=true\n",
                    encoding="utf-8",
                )
        else:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def set_on_top(self, checked: bool, persist: bool = True) -> None:
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.show()
        self.on_top_btn.setChecked(checked)
        if persist:
            self.settings["always_on_top"] = checked
            self.save()

    def toggle_on_top(self) -> None:
        self.set_on_top(not bool(self.windowFlags() & Qt.WindowStaysOnTopHint))

    def save(self) -> None:
        self.settings["tabs"] = self.tabs
        self.settings["theme_name"] = self.theme_name
        self.settings["custom_palette"] = self.custom_palette
        self.settings["font_scale"] = self.font_scale
        self.settings["accessibility_mode"] = self.accessibility_mode
        self.store.save(self.items, self.history, self.settings)

    def closeEvent(self, event) -> None:
        self.finalize_pending_completion()
        self.save()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

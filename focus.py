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

from PySide6.QtCore import QDateTime, QEvent, QPointF, QSize, QTimer, Qt, Signal
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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "focus"
APP_VERSION = "0.1.0"
BUILD_REPO_URL = "https://github.com/IAnMove/Focus"
BUILD_COMMIT = "98f1010"
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
HEADER_MIN_WIDTH = 360
HEADER_COMPACT_WIDTH = 500
TASK_POPUP_WIDTH = 360
TASK_COMPACT_WIDTH = 560
FOOTER_COMPACT_WIDTH = 520
RESIZE_SETTLE_MS = 140
ROW_DEBUG_LOGS = False


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


def debug_stamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def debug_log(event: str, **values) -> None:
    details = " ".join(f"{key}={value}" for key, value in values.items())
    message = f"[{debug_stamp()}] {event}"
    if details:
        message = f"{message} {details}"
    print(message, file=sys.stderr, flush=True)


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


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("About focus")
        self.setModal(True)
        self.resize(420, 220)

        layout = QVBoxLayout(self)
        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        subtitle = QLabel("Minimal desktop checklist")
        subtitle.setObjectName("sectionTitle")

        repo = QLabel(f'<a href="{BUILD_REPO_URL}">{BUILD_REPO_URL}</a>')
        repo.setOpenExternalLinks(True)
        repo.setTextInteractionFlags(Qt.TextBrowserInteraction)

        info = QLabel(
            f"Version: {APP_VERSION}<br>"
            f"Commit: {BUILD_COMMIT}<br>"
            f"Generated from: {BUILD_REPO_URL}"
        )
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(repo)
        layout.addWidget(info)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)


class ClickableWidget(QWidget):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class TaskActionsPopup(QDialog):
    def __init__(self, parent: QWidget, item: dict, is_current: bool) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setModal(False)
        self.setObjectName("taskActionsPopup")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel(item.get("text", ""))
        title.setWordWrap(True)
        layout.addWidget(title)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        self.current_btn = QPushButton("◉" if is_current else "◎")
        self.current_btn.setObjectName("iconBtn")
        self.current_btn.setFixedSize(34, 34)
        self.edit_btn = QPushButton("✎")
        self.edit_btn.setObjectName("iconBtn")
        self.edit_btn.setFixedSize(34, 34)
        self.delete_btn = QPushButton("×")
        self.delete_btn.setObjectName("iconBtn")
        self.delete_btn.setFixedSize(34, 34)
        for button in (self.current_btn, self.edit_btn, self.delete_btn):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)


class TaskRowWidget(QWidget):
    complete_requested = Signal(int)
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    current_toggled = Signal(int)

    def __init__(
        self,
        item: dict,
        accessibility: bool,
        alt: bool = False,
        palette: dict | None = None,
        show_meta: bool = True,
        layout_mode: str = "wide",
    ) -> None:
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.item = item
        self.accessibility = accessibility
        self.show_meta = show_meta
        self._palette = palette or {}
        self.layout_mode = "wide"
        self._popup_mode = False
        self._actions_popup: TaskActionsPopup | None = None
        self.setObjectName("taskCardAlt" if alt else "taskCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        self.top_row = QWidget()
        top_layout = QHBoxLayout(self.top_row)
        top_layout.setContentsMargins(3, 1, 3, 1)
        top_layout.setSpacing(10)
        outer.addWidget(self.top_row)

        self.bottom_row = QWidget()
        self.bottom_layout = QHBoxLayout(self.bottom_row)
        self.bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_layout.setSpacing(6)
        outer.addWidget(self.bottom_row)

        self.done_btn = QPushButton("")
        self.done_btn.setObjectName("doneBtn")
        self.done_btn.setFixedSize(28, 28)
        self.done_btn.setStyleSheet("margin: 1px 0px;")
        self.done_btn.clicked.connect(lambda: self.complete_requested.emit(self.item["id"]))

        self.content_widget = ClickableWidget()
        self.content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.content_widget.clicked.connect(self._handle_content_clicked)
        self.content_widget.setAttribute(Qt.WA_StyledBackground, True)
        self.content_widget.setObjectName("taskContent")
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(2, 2, 2, 2)
        content_layout.setSpacing(4)

        self.text_label = QLabel()
        self.text_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.text_label.setOpenExternalLinks(False)
        self.text_label.linkActivated.connect(open_url)
        self.text_label.setWordWrap(True)
        self.text_label.installEventFilter(self)
        escaped = self.item.get("text", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.text_label.setText(URL_RE.sub(r'<a href="\1">\1</a>', escaped))
        content_layout.addWidget(self.text_label)

        self.meta_label = QLabel(self._meta_text())
        self.meta_label.setObjectName("metaLabel")
        self.meta_label.setWordWrap(True)
        self.meta_label.setVisible(self.show_meta)
        self.meta_label.installEventFilter(self)
        content_layout.addWidget(self.meta_label)

        self.progress_bar: QProgressBar | None = None
        ratio = due_progress_ratio(self.item)
        if ratio is not None:
            due_dt = parse_due_date(self.item.get("due_date"))
            is_overdue = due_dt is not None and due_dt < datetime.now()
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(int(ratio * 1000))
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setFixedHeight(7 if accessibility else 5)
            if is_overdue:
                card = self._palette.get("CARD", "#ffffff")
                r, g, b = int(card[1:3], 16), int(card[3:5], 16), int(card[5:7], 16)
                is_dark_theme = (r * 299 + g * 587 + b * 114) / 1000 < 128
                if is_dark_theme:
                    self.progress_bar.setStyleSheet(
                        "QProgressBar { background: #3a1010; border: none; border-radius: 3px; }"
                        "QProgressBar::chunk { background: #cc2828; border-radius: 3px; }"
                    )
                else:
                    self.progress_bar.setStyleSheet(
                        "QProgressBar { background: #f5d5d5; border: none; border-radius: 3px; }"
                        "QProgressBar::chunk { background: #d94f4f; border-radius: 3px; }"
                    )
            self.progress_bar.installEventFilter(self)
            content_layout.addWidget(self.progress_bar)

        self.wide_actions_widget, self.wide_current_btn, self.wide_drag_handle = self._build_actions_widget()
        self.compact_actions_widget, self.compact_current_btn, self.compact_drag_handle = self._build_actions_widget()
        self.drag_handle = self.wide_drag_handle

        top_layout.addWidget(self.done_btn, 0, Qt.AlignVCenter)
        top_layout.addWidget(self.content_widget, 1)
        top_layout.addWidget(self.wide_actions_widget, 0, Qt.AlignVCenter)
        self.bottom_layout.addWidget(self.compact_actions_widget)

        self.bottom_row.setVisible(False)
        self.bottom_row.setMaximumHeight(0)
        self.set_layout_mode(layout_mode)

    def _meta_text(self) -> str:
        if not self.show_meta:
            return ""
        meta_parts = [f"tab {self.item.get('tab', 'General')}", f"added {self.item.get('created_at', '')}"]
        if self.item.get("due_date"):
            meta_parts.append(f"due {format_dt(self.item['due_date'])} ({format_remaining_time(self.item['due_date'])})")
        if self.item.get("extra_info"):
            meta_parts.append("extra info")
        return "  ·  ".join(meta_parts)

    def set_show_meta(self, enabled: bool) -> None:
        self.show_meta = bool(enabled)
        self.meta_label.setVisible(self.show_meta)
        self.meta_label.setText(self._meta_text())

    def _build_actions_widget(self) -> tuple[QWidget, QPushButton, DragHandle]:
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        widget.setMinimumHeight(34)
        widget.setAttribute(Qt.WA_StyledBackground, True)
        widget.setObjectName("taskActions")
        actions = QHBoxLayout(widget)
        actions.setContentsMargins(3, 1, 3, 1)
        actions.setSpacing(6)
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
        drag_handle = DragHandle()
        actions.addWidget(current_btn)
        actions.addWidget(edit_btn)
        actions.addWidget(delete_btn)
        actions.addWidget(drag_handle)
        return widget, current_btn, drag_handle

    def _handle_content_clicked(self) -> None:
        if not self._popup_mode:
            return
        self._open_actions_popup()

    def _update_content_interaction(self) -> None:
        self.content_widget.setCursor(Qt.PointingHandCursor if self._popup_mode else Qt.ArrowCursor)
        self.text_label.setCursor(Qt.PointingHandCursor if self._popup_mode else Qt.IBeamCursor)
        self.meta_label.setCursor(Qt.PointingHandCursor if self._popup_mode else Qt.ArrowCursor)

    def _open_actions_popup(self) -> None:
        if self._actions_popup is not None and self._actions_popup.isVisible():
            self._actions_popup.close()
        popup = TaskActionsPopup(self, self.item, bool(self.item.get("current")))
        popup.current_btn.clicked.connect(lambda: self._popup_action(self.current_toggled))
        popup.edit_btn.clicked.connect(lambda: self._popup_action(self.edit_requested))
        popup.delete_btn.clicked.connect(lambda: self._popup_action(self.delete_requested))
        anchor = self.content_widget.mapToGlobal(self.content_widget.rect().bottomLeft())
        popup.move(anchor)
        popup.show()
        self._actions_popup = popup

    def _popup_action(self, signal) -> None:
        if self._actions_popup is not None:
            self._actions_popup.close()
            self._actions_popup = None
        signal.emit(self.item["id"])

    def eventFilter(self, watched, event):
        if (
            self._popup_mode
            and watched in {self.text_label, self.meta_label, self.progress_bar}
            and event.type() == QEvent.MouseButtonPress
            and event.button() == Qt.LeftButton
        ):
            self._open_actions_popup()
            return True
        return super().eventFilter(watched, event)

    def set_layout_mode(self, layout_mode: str) -> None:
        mode = layout_mode if layout_mode in {"wide", "compact", "popup"} else "wide"
        if mode == self.layout_mode and self._popup_mode == (mode == "popup"):
            return
        if ROW_DEBUG_LOGS:
            debug_log("task_row.set_layout_mode", item_id=self.item["id"], mode=mode)
        self.layout_mode = mode
        self._popup_mode = mode == "popup"
        self.wide_actions_widget.setVisible(mode == "wide")
        self.compact_actions_widget.setVisible(mode == "compact")
        self.bottom_row.setVisible(mode == "compact")
        self.bottom_row.setMaximumHeight(16777215 if mode == "compact" else 0)
        self.bottom_layout.setAlignment(self.compact_actions_widget, Qt.AlignRight)
        self._update_content_interaction()

    def measure_for_width(self, width: int) -> None:
        if width <= 0:
            return
        if ROW_DEBUG_LOGS:
            debug_log("task_row.measure_for_width", item_id=self.item["id"], width=width, mode=self.layout_mode)
        self.resize(width, 1)
        self.adjustSize()

    def sizeHint(self):
        hint = super().sizeHint()
        layout = self.layout()
        if layout is None:
            return hint
        return layout.sizeHint().expandedTo(hint)


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
        self.show_item_meta = bool(self.settings.get("show_item_meta", True))
        self.tab_visible_count = max(1, min(12, int(self.settings.get("tab_visible_count", 5) or 5)))
        self.tab_window_start = 0
        self.active_tab = "All"
        self.active_view = "main"
        self.undo_item: dict | None = None
        self.undo_timer = QTimer(self)
        self.undo_timer.setInterval(3000)
        self.undo_timer.setSingleShot(True)
        self.undo_timer.timeout.connect(self.finalize_pending_completion)
        self.resize_settle_timer = QTimer(self)
        self.resize_settle_timer.setInterval(RESIZE_SETTLE_MS)
        self.resize_settle_timer.setSingleShot(True)
        self.resize_settle_timer.timeout.connect(self.handle_resize_settled)
        self._header_compact_level = -1
        self._main_render_signature: tuple[int, str] | None = None
        self._row_size_cache: dict[tuple, QSize] = {}
        self._ui_ready = False
        self._initial_render_done = False
        self._resize_pending = False
        self._header_init_scheduled = False

        self._build_ui()
        self.loading_label.setVisible(True)
        self.pages.setVisible(False)
        self.apply_theme(self.theme_name, persist=False)
        self.set_on_top(bool(self.settings.get("always_on_top", True)), persist=False)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        debug_log("main.show_event", width=self.width(), height=self.height(), initialized=self._header_init_scheduled)
        if self._header_init_scheduled:
            return
        self._header_init_scheduled = True

        def finish_init() -> None:
            self._ui_ready = True
            debug_log("main.finish_init", width=self.width(), height=self.height())
            self.update_header_compact()
            debug_log("main.schedule_initial_refresh", reason="finish_init")
            QTimer.singleShot(0, self.run_initial_refresh)

        QTimer.singleShot(0, finish_init)

    def run_initial_refresh(self) -> None:
        debug_log(
            "main.run_initial_refresh",
            pages_visible=self.pages.isVisible(),
            active_view=self.active_view,
            viewport_width=self.task_viewport_width(),
        )
        self.refresh_all()
        self.pages.setVisible(True)
        self.loading_label.setVisible(False)
        self._initial_render_done = True

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
            widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            header_actions_layout.addWidget(widget)
        self.header_actions.setVisible(False)
        header.addWidget(self.header_actions)
        root.addLayout(header)

        self.tab_bar_frame = QFrame()
        self.tab_bar_frame.setObjectName("tabBarFrame")
        self.tab_bar_layout = QHBoxLayout(self.tab_bar_frame)
        self.tab_bar_layout.setContentsMargins(8, 8, 8, 8)
        self.tab_bar_layout.setSpacing(6)
        self.tab_left_btn = QPushButton("←")
        self.tab_left_btn.setObjectName("iconBtn")
        self.tab_left_btn.setFixedSize(30, 30)
        self.tab_left_btn.clicked.connect(lambda: self.shift_tab_window(-1))
        self.tab_right_btn = QPushButton("→")
        self.tab_right_btn.setObjectName("iconBtn")
        self.tab_right_btn.setFixedSize(30, 30)
        self.tab_right_btn.clicked.connect(lambda: self.shift_tab_window(1))
        self.tab_tabs_host = QWidget()
        self.tab_tabs_layout = QHBoxLayout(self.tab_tabs_host)
        self.tab_tabs_layout.setContentsMargins(0, 0, 0, 0)
        self.tab_tabs_layout.setSpacing(6)
        self.tab_bar_layout.addWidget(self.tab_tabs_host, 1)
        self.tab_bar_layout.addWidget(self.tab_left_btn)
        self.tab_bar_layout.addWidget(self.tab_right_btn)
        root.addWidget(self.tab_bar_frame)

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
        self.item_meta_check = QCheckBox("Show item meta")
        self.item_meta_check.setChecked(self.show_item_meta)
        self.item_meta_check.toggled.connect(self.toggle_item_meta)
        appearance_layout.addWidget(self.item_meta_check)
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
        tabs_control = QFrame()
        tabs_control_layout = QVBoxLayout(tabs_control)
        tabs_control_layout.setContentsMargins(12, 12, 12, 12)
        tabs_title = QLabel("Tab strip")
        tabs_title.setObjectName("sectionTitle")
        tabs_control_layout.addWidget(tabs_title)
        tabs_row = QHBoxLayout()
        tabs_row.addWidget(QLabel("Visible tabs"))
        self.tab_visible_spin = QSpinBox()
        self.tab_visible_spin.setRange(2, 12)
        self.tab_visible_spin.setValue(self.tab_visible_count)
        self.tab_visible_spin.valueChanged.connect(self.set_tab_visible_count)
        tabs_row.addWidget(self.tab_visible_spin)
        tabs_row.addStretch(1)
        tabs_control_layout.addLayout(tabs_row)
        tabs_hint = QLabel("Use the arrows in the tab bar to scroll when there are more tabs than fit.")
        tabs_hint.setWordWrap(True)
        tabs_control_layout.addWidget(tabs_hint)
        self.tools_layout.addWidget(tabs_control)

        about_box = QFrame()
        about_layout = QVBoxLayout(about_box)
        about_layout.setContentsMargins(12, 12, 12, 12)
        about_title = QLabel("About")
        about_title.setObjectName("sectionTitle")
        about_layout.addWidget(about_title)
        about_subtitle = QLabel("Minimal desktop checklist")
        about_subtitle.setWordWrap(True)
        about_layout.addWidget(about_subtitle)
        about_repo = QLabel(f'<a href="{BUILD_REPO_URL}">{BUILD_REPO_URL}</a>')
        about_repo.setOpenExternalLinks(True)
        about_repo.setTextInteractionFlags(Qt.TextBrowserInteraction)
        about_layout.addWidget(about_repo)
        about_info = QLabel(f"{APP_NAME} {APP_VERSION}  ·  {BUILD_COMMIT}")
        about_info.setWordWrap(True)
        about_layout.addWidget(about_info)
        self.tools_layout.addWidget(about_box)
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
            QWidget#taskContent {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid {p['BORDER']};
                border-radius: 12px;
            }}
            QWidget#taskActions {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid {p['BORDER']};
                border-radius: 10px;
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
        if self._ui_ready:
            self.refresh_all()

    def set_font_scale(self, value: float) -> None:
        self.font_scale = max(0.8, min(1.8, value))
        self._row_size_cache.clear()
        self.settings["font_scale"] = self.font_scale
        self.save()
        if hasattr(self, "font_scale_label"):
            self.font_scale_label.setText(f"{int(round(self.font_scale * 100))}%")
        self.refresh_styles()

    def toggle_accessibility(self, checked: bool) -> None:
        self.accessibility_mode = bool(checked)
        self._row_size_cache.clear()
        self.settings["accessibility_mode"] = self.accessibility_mode
        self.save()
        self.refresh_styles()

    def toggle_item_meta(self, checked: bool) -> None:
        self.show_item_meta = bool(checked)
        self._row_size_cache.clear()
        self.settings["show_item_meta"] = self.show_item_meta
        self.save()
        self.refresh_all()

    def header_compact_level_for_width(self, width: int) -> int:
        debug_log("responsive.header_level_for_width", width=width)
        if width < HEADER_MIN_WIDTH:
            return 2
        if width < HEADER_COMPACT_WIDTH:
            return 1
        return 0

    def task_layout_mode_for_width(self, width: int) -> str:
        debug_log("responsive.task_mode_for_width", width=width)
        if width < TASK_POPUP_WIDTH:
            return "popup"
        if width < TASK_COMPACT_WIDTH:
            return "compact"
        return "wide"

    def task_viewport_width(self) -> int:
        if not hasattr(self, "task_list"):
            return 0
        width = max(0, self.task_list.viewport().width())
        debug_log("responsive.task_viewport_width", width=width)
        return width

    def current_main_render_signature(self) -> tuple[int, str]:
        use_viewport = self._initial_render_done and self.pages.isVisible() and not self._resize_pending
        viewport_width = self.task_viewport_width() if use_viewport else max(0, self.centralWidget().width() - 24)
        row_width = max(0, viewport_width - 8)
        mode = self.task_layout_mode_for_width(viewport_width)
        debug_log(
            "responsive.main_render_signature",
            viewport_width=viewport_width,
            row_width=row_width,
            mode=mode,
            source="viewport" if use_viewport else "window",
        )
        return row_width, mode

    def row_size_cache_key(self, item: dict, row_width: int, layout_mode: str) -> tuple:
        return (
            item.get("id"),
            item.get("text", ""),
            item.get("created_at", ""),
            item.get("due_date", ""),
            item.get("extra_info", ""),
            item.get("tab", ""),
            bool(item.get("current")),
            self.show_item_meta,
            self.accessibility_mode,
            round(self.font_scale, 2),
            row_width,
            layout_mode,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        debug_log("main.resize_event", width=self.width(), height=self.height(), ui_ready=self._ui_ready, active_view=self.active_view)
        if self._ui_ready and self._initial_render_done:
            if not self._resize_pending:
                self._resize_pending = True
                debug_log("main.begin_resize_cycle", width=self.width(), height=self.height())
                self.loading_label.setText("Resizing...")
                self.loading_label.setVisible(True)
                self.pages.setVisible(False)
            debug_log("main.schedule_resize_settle", delay_ms=RESIZE_SETTLE_MS, reason="resize_event")
            self.resize_settle_timer.start()

    def handle_resize_settled(self) -> None:
        debug_log(
            "main.handle_resize_settled.start",
            ui_ready=self._ui_ready,
            active_view=self.active_view,
            initial_render_done=self._initial_render_done,
        )
        if not self._ui_ready or not self._initial_render_done:
            return
        self.update_header_compact()
        self.refresh_all()
        self.loading_label.setText("Loading...")
        self.loading_label.setVisible(False)
        self.pages.setVisible(True)
        self._resize_pending = False

    def update_header_compact(self) -> None:
        if not self._ui_ready or not hasattr(self, "header_actions") or self.width() <= 0:
            return
        level = self.header_compact_level_for_width(self.width())
        if level == self._header_compact_level:
            debug_log("main.update_header_compact.skip", level=level)
            return
        debug_log("main.update_header_compact.apply", previous=self._header_compact_level, level=level, width=self.width())
        self._header_compact_level = level
        self.title_label.setVisible(level == 0)
        if level == 0:
            self.add_btn.setText("+ add")
            self.add_tab_btn.setText("+ add tab")
            self.history_btn.setText("history")
            self.tools_btn.setText("tools")
            self.on_top_btn.setText("on top" if not self.on_top_btn.isChecked() else "on top")
        elif level == 1:
            self.add_btn.setText("+")
            self.add_tab_btn.setText("+ T")
            self.history_btn.setText("H")
            self.tools_btn.setText("T")
            self.on_top_btn.setText("👁" if self.on_top_btn.isChecked() else "○")
        else:
            self.add_btn.setText("+")
            self.add_tab_btn.setText("+T")
            self.history_btn.setText("H")
            self.tools_btn.setText("T")
            self.on_top_btn.setText("👁" if self.on_top_btn.isChecked() else "○")
        self.header_actions.setMinimumWidth(0)

    def switch_view(self, view: str) -> None:
        debug_log("main.switch_view", from_view=self.active_view, to_view=view)
        self.loading_label.setVisible(True)
        self.pages.setVisible(False)
        self.active_view = view
        QTimer.singleShot(1, self._finish_switch_view)

    def _finish_switch_view(self) -> None:
        debug_log("main.finish_switch_view", active_view=self.active_view)
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
        while self.tab_tabs_layout.count():
            item = self.tab_tabs_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._clamp_tab_window()
        if self.active_tab != "All":
            self._ensure_active_tab_visible(self.active_tab)
        all_btn = QPushButton("All")
        all_btn.setObjectName("tabBtn")
        all_btn.setCheckable(True)
        all_btn.setChecked(self.active_tab == "All")
        all_btn.clicked.connect(lambda: self.set_active_tab("All"))
        self.tab_tabs_layout.addWidget(all_btn)

        tabs = self.tabs[self.tab_window_start : self.tab_window_start + self.tab_visible_count]
        for tab in tabs:
            btn = QPushButton(tab["name"])
            btn.setObjectName("tabBtn")
            btn.setCheckable(True)
            btn.setChecked(self.active_tab == tab["name"])
            btn.clicked.connect(lambda checked=False, name=tab["name"]: self.set_active_tab(name))
            self.tab_tabs_layout.addWidget(btn)
        self.tab_tabs_layout.addStretch(1)

        overflow = len(self.tabs) > self.tab_visible_count
        self.tab_left_btn.setVisible(overflow)
        self.tab_right_btn.setVisible(overflow)
        self.tab_left_btn.setEnabled(self.tab_window_start > 0)
        self.tab_right_btn.setEnabled(self.tab_window_start + self.tab_visible_count < len(self.tabs))

    def set_active_tab(self, name: str) -> None:
        debug_log("main.set_active_tab", current=self.active_tab, target=name, active_view=self.active_view)
        play_click()
        self.active_tab = name
        if name != "All":
            self._ensure_active_tab_visible(name)
        if self.active_view == "main":
            self.render_tab_bar()
            self.render_main()
        else:
            self.switch_view("main")

    def _clamp_tab_window(self) -> None:
        max_start = max(0, len(self.tabs) - self.tab_visible_count)
        self.tab_window_start = max(0, min(self.tab_window_start, max_start))

    def _ensure_active_tab_visible(self, name: str) -> None:
        names = [tab["name"] for tab in self.tabs]
        try:
            index = names.index(name)
        except ValueError:
            return
        if index < self.tab_window_start:
            self.tab_window_start = index
        elif index >= self.tab_window_start + self.tab_visible_count:
            self.tab_window_start = index - self.tab_visible_count + 1
        self._clamp_tab_window()

    def shift_tab_window(self, direction: int) -> None:
        if not self.tabs:
            return
        names = [tab["name"] for tab in self.tabs]
        if self.active_tab == "All":
            current_index = -1 if direction > 0 else 0
        else:
            try:
                current_index = names.index(self.active_tab)
            except ValueError:
                current_index = -1 if direction > 0 else 0
        target_index = max(0, min(len(names) - 1, current_index + direction))
        self.set_active_tab(names[target_index])

    def set_tab_visible_count(self, value: int) -> None:
        self.tab_visible_count = max(2, min(12, int(value)))
        self.settings["tab_visible_count"] = self.tab_visible_count
        self.save()
        self._clamp_tab_window()
        self.render_tab_bar()

    def visible_items(self) -> list[dict]:
        if self.active_tab != "All":
            return [item for item in self.items if item.get("tab", "General") == self.active_tab]
        current = [item for item in self.items if item.get("current")]
        rest = [item for item in self.items if not item.get("current")]
        return current + rest

    def render_main(self) -> None:
        row_width, layout_mode = self.current_main_render_signature()
        visible_items = self.visible_items()
        debug_log(
            "main.render_main.start",
            row_width=row_width,
            layout_mode=layout_mode,
            visible_items=len(visible_items),
            active_tab=self.active_tab,
        )
        self.task_list.setUpdatesEnabled(False)
        self.task_list.viewport().setUpdatesEnabled(False)
        try:
            self.task_list.clear()
            for index, item in enumerate(visible_items):
                list_item = QListWidgetItem()
                list_item.setData(Qt.UserRole, item["id"])
                list_item.setFlags(list_item.flags() | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
                row = TaskRowWidget(
                    item,
                    self.accessibility_mode,
                    alt=index % 2 == 1,
                    palette=self.palette_values(),
                    show_meta=self.show_item_meta,
                    layout_mode=layout_mode,
                )
                row.wide_drag_handle.bind(self.task_list, item["id"])
                row.compact_drag_handle.bind(self.task_list, item["id"])
                row.complete_requested.connect(self.complete_item)
                row.edit_requested.connect(self.open_edit_task)
                row.delete_requested.connect(self.delete_item)
                row.current_toggled.connect(self.toggle_current)
                cache_key = self.row_size_cache_key(item, row_width, layout_mode)
                cached_size = self._row_size_cache.get(cache_key)
                if row_width > 0:
                    row.setFixedWidth(row_width)
                    if cached_size is None:
                        row.measure_for_width(row_width)
                        cached_size = QSize(row.sizeHint())
                        self._row_size_cache[cache_key] = QSize(cached_size)
                list_item.setSizeHint(cached_size if cached_size is not None else row.sizeHint())
                self.task_list.addItem(list_item)
                self.task_list.setItemWidget(list_item, row)
        finally:
            self.task_list.viewport().setUpdatesEnabled(True)
            self.task_list.setUpdatesEnabled(True)
            self.task_list.viewport().update()
        self._main_render_signature = (row_width, layout_mode)
        debug_log("main.render_main.done", signature=self._main_render_signature, count=self.task_list.count())

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
        debug_log("main.update_footer", width=self.width(), pending=pending, today=today, month=month, year=year)
        if self.width() < FOOTER_COMPACT_WIDTH:
            self.footer_label.setText(f"P {pending}  ·  T {today}  ·  M {month}  ·  Y {year}")
        else:
            self.footer_label.setText(f"pending {pending}  ·  Tasks done: today {today}  ·  month {month}  ·  year {year}")

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
        self.show_item_meta = bool(self.settings.get("show_item_meta", True))
        self._row_size_cache.clear()
        if hasattr(self, "item_meta_check"):
            self.item_meta_check.blockSignals(True)
            self.item_meta_check.setChecked(self.show_item_meta)
            self.item_meta_check.blockSignals(False)
        self.tabs = self.store.normalize_tabs(self.settings.get("tabs", default_tabs()))
        self.settings["tabs"] = self.tabs
        self.save()
        self.refresh_all()

    def open_about_dialog(self) -> None:
        play_click()
        dialog = AboutDialog(self)
        dialog.exec()

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
        if self.isVisible():
            self.show()
        self.on_top_btn.setChecked(checked)
        self.update_header_compact()
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
        self.settings["show_item_meta"] = self.show_item_meta
        self.settings["tab_visible_count"] = self.tab_visible_count
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

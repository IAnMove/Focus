# focus

Minimal desktop checklist for Windows and Linux, built to stay visible and keep the current task in front of you.

## Features

- Normal desktop window with taskbar presence.
- Hover-first header controls.
- Always-on-top toggle.
- Add, edit, delete, reorder, and complete tasks.
- Single `current` task mode that moves the task to the top.
- One tab/label per task.
- Tab filtering with `All` view.
- Tab priority levels: `high`, `normal`, `low`.
- Tab management from `tools`.
- Tab reordering controls.
- Clickable `http://` and `https://` links inside tasks.
- Due date picker with optional time.
- Small remaining-time text next to due date.
- Minimal due-date progress bar based on creation time to deadline.
- Completion animation with 3-second undo.
- History with restore.
- Optional hidden `extra info` per task.
- Footer stats for pending, done today, this month, and this year.
- Export and import full JSON data.
- Saved metadata: `created_at`, `completed_at`, `due_date`, `extra_info`, `tab`.
- Startup toggle for Windows and Linux.
- Theme presets: `warm`, `forest`, `ocean`, `rose`.
- Custom color theme editor with live preview squares.
- Font size controls.
- Accessibility toggle.
- Scrollable `tools` panel.
- Settings persistence between sessions.

## Run

## Python Setup

### Windows

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install packages:

```powershell
python -m pip install --upgrade pip
python -m pip install PySide6
```

### Linux

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install packages:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install PySide6
```

### macOS

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install packages:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install PySide6
```

Deactivate the virtual environment when you are done:

```bash
deactivate
```

On Windows:

```powershell
python .\focus.py
```

PySide6 rewrite:

```powershell
python -m pip install PySide6
python .\focus.py
```

On Linux:

```bash
python3 ./focus.py
```

PySide6 rewrite:

```bash
python3 -m pip install PySide6
python3 ./focus.py
```

## Build

On Windows:

```powershell
.\build_windows.ps1
```

Expected output: `dist\focus.exe`

On Linux:

```bash
chmod +x ./build_linux.sh
./build_linux.sh
```

Expected output: `dist/focus`

## Data

Windows:

`%USERPROFILE%\AppData\Roaming\focus\checklist.json`

Linux:

`~/.focus/checklist.json`

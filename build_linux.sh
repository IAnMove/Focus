#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install pyinstaller
python3 -m PyInstaller --noconfirm --onefile --windowed --name focus focus.py

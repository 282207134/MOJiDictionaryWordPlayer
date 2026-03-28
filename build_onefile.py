# -*- coding: utf-8 -*-
"""将 logo.jpg / logo.png 转为 .ico 并执行 PyInstaller 单文件打包。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICO = ROOT / "logo.ico"

_LOGO_CANDIDATES = ("logo.jpg", "logo.jpeg", "logo.png")


def find_logo_path() -> Path:
    for name in _LOGO_CANDIDATES:
        p = ROOT / name
        if p.is_file():
            return p
    raise SystemExit(
        "未找到图标源文件，请在项目根目录放置以下之一："
        + ", ".join(_LOGO_CANDIDATES)
    )


def ensure_build_deps() -> None:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "pillow", "pyinstaller"],
        cwd=ROOT,
    )


def raster_to_ico() -> None:
    from PIL import Image

    src = find_logo_path()
    print(f"图标源: {src.name}")
    im = Image.open(src).convert("RGBA")
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    images = [im.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    images[0].save(ICO, format="ICO", append_images=images[1:])
    print(f"已生成 {ICO}")


def run_pyinstaller() -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        "--name",
        "MOJiDictionaryWordPlayer",
        "--icon",
        str(ICO),
        "--collect-all",
        "customtkinter",
        str(ROOT / "main.py"),
    ]
    subprocess.check_call(cmd, cwd=ROOT)
    print(f"输出: {ROOT / 'dist' / 'MOJiDictionaryWordPlayer.exe'}")


def main() -> None:
    ensure_build_deps()
    raster_to_ico()
    run_pyinstaller()


if __name__ == "__main__":
    main()

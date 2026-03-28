# -*- coding: utf-8 -*-
"""已记住词条与界面设置的本地持久化。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from parser_vocab import VocabEntry

DATA_DIR = Path(__file__).resolve().parent / "data"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def entry_id(e: VocabEntry) -> str:
    raw = f"{e.source}\0{e.headline}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def meta_for_entry(e: VocabEntry) -> dict[str, str]:
    return {
        "source": e.source,
        "headline": e.headline,
        "word": e.word,
    }


def load_remembered() -> dict[str, dict[str, str]]:
    ensure_data_dir()
    p = DATA_DIR / "remembered.json"
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items", {})
        return {str(k): dict(v) for k, v in items.items()}
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}


def save_remembered(items: dict[str, dict[str, str]]) -> None:
    ensure_data_dir()
    (DATA_DIR / "remembered.json").write_text(
        json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def favorite_meta_for_entry(e: VocabEntry) -> dict[str, str]:
    return {
        "source": e.source,
        "headline": e.headline,
        "word": e.word,
        "reading": e.reading,
        "definitions": e.definitions or "",
    }


def load_favorites() -> dict[str, dict[str, str]]:
    ensure_data_dir()
    p = DATA_DIR / "favorites.json"
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items", {})
        return {str(k): dict(v) for k, v in items.items()}
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}


def save_favorites(items: dict[str, dict[str, str]]) -> None:
    ensure_data_dir()
    (DATA_DIR / "favorites.json").write_text(
        json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_settings() -> dict[str, Any]:
    ensure_data_dir()
    p = DATA_DIR / "settings.json"
    defaults: dict[str, Any] = {
        "alpha": 1.0,
        "text_color_hex": "",
        "hide_remembered": True,
        "shuffle_mode": False,
        "bg_head_mode": "default",
        "bg_head_hex": "#FAFAFA",
        "bg_def_mode": "default",
        "bg_def_hex": "#FFFFFF",
        "font_head_pt": 20,
        "font_def_pt": 15,
        "tts_voice": "ja-JP-NanamiNeural",
        "auto_interval_sec": 2.0,
        "auto_advance": False,
        "last_source_kind": "",
        "last_folder_path": "",
        "last_file_path": "",
    }
    if not p.is_file():
        return defaults
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        merged = {**defaults, **data}
        merged["alpha"] = float(merged.get("alpha", 1.0))
        merged["alpha"] = max(0.25, min(1.0, merged["alpha"]))
        merged["font_head_pt"] = int(merged.get("font_head_pt", 20))
        merged["font_head_pt"] = max(10, min(48, merged["font_head_pt"]))
        merged["font_def_pt"] = int(merged.get("font_def_pt", 15))
        merged["font_def_pt"] = max(9, min(40, merged["font_def_pt"]))
        merged["tts_voice"] = str(merged.get("tts_voice", "ja-JP-NanamiNeural") or "ja-JP-NanamiNeural")
        try:
            merged["auto_interval_sec"] = float(merged.get("auto_interval_sec", 2.0))
        except (TypeError, ValueError):
            merged["auto_interval_sec"] = 2.0
        merged["auto_interval_sec"] = max(0.5, min(120.0, merged["auto_interval_sec"]))
        merged["auto_advance"] = bool(merged.get("auto_advance", False))
        merged["last_source_kind"] = str(merged.get("last_source_kind", "") or "")
        merged["last_folder_path"] = str(merged.get("last_folder_path", "") or "")
        merged["last_file_path"] = str(merged.get("last_file_path", "") or "")
        merged.pop("text_color_mode", None)
        # 旧版带 text_color_mode：仅 custom 保留 hex；否则清空。无该字段则保留文件中的 text_color_hex。
        mode = str(data.get("text_color_mode", "") or "")
        if "text_color_mode" in data:
            if mode == "custom":
                merged["text_color_hex"] = str(merged.get("text_color_hex", "") or "").strip()
            else:
                merged["text_color_hex"] = ""
        return merged
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return defaults


def save_settings(data: dict[str, Any]) -> None:
    ensure_data_dir()
    try:
        interval = float(data.get("auto_interval_sec", 2.0))
    except (TypeError, ValueError):
        interval = 2.0
    interval = max(0.5, min(120.0, interval))
    fh = int(data.get("font_head_pt", 20))
    fd = int(data.get("font_def_pt", 15))
    out = {
        "alpha": float(max(0.25, min(1.0, data.get("alpha", 1.0)))),
        "text_color_hex": str(data.get("text_color_hex", "") or ""),
        "hide_remembered": bool(data.get("hide_remembered", True)),
        "shuffle_mode": bool(data.get("shuffle_mode", False)),
        "bg_head_mode": str(data.get("bg_head_mode", "default")),
        "bg_head_hex": str(data.get("bg_head_hex", "#FAFAFA")),
        "bg_def_mode": str(data.get("bg_def_mode", "default")),
        "bg_def_hex": str(data.get("bg_def_hex", "#FFFFFF")),
        "font_head_pt": max(10, min(48, fh)),
        "font_def_pt": max(9, min(40, fd)),
        "tts_voice": str(data.get("tts_voice", "ja-JP-NanamiNeural") or "ja-JP-NanamiNeural"),
        "auto_interval_sec": interval,
        "auto_advance": bool(data.get("auto_advance", False)),
        "last_source_kind": str(data.get("last_source_kind", "") or ""),
        "last_folder_path": str(data.get("last_folder_path", "") or ""),
        "last_file_path": str(data.get("last_file_path", "") or ""),
    }
    (DATA_DIR / "settings.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# -*- coding: utf-8 -*-
"""紅宝書／MOJi 形式のテキスト・PDF から語彙エントリを抽出する。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class VocabEntry:
    headline: str  # 原文一行，如「呆気ない | あっけない ④」
    word: str
    reading: str
    definitions: str
    source: str


_NOISE_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r"www\.mojidict\.com", re.I),
    re.compile(r"^\d+\s*/\s*\d+"),
    re.compile(r"^--\s*\d+\s+of\s+\d+\s*--", re.I),
    re.compile(r"^第.+单元\s*$"),
    re.compile(r"^MOちゃん\s*$"),
]

# 见出し | 読み（右侧可含声调符号或数字）
_ENTRY_HEAD = re.compile(r"^(.+?)\s*\|\s*(.+)$")


def _is_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    for p in _NOISE_PATTERNS:
        if p.search(s):
            return True
    return False


def _looks_like_definition_start(s: str) -> bool:
    t = s.lstrip()
    return bool(t.startswith("["))


def parse_text(text: str, source_label: str) -> List[VocabEntry]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: List[VocabEntry] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        if _is_noise(line):
            i += 1
            continue

        m = _ENTRY_HEAD.match(line.strip())
        if not m:
            i += 1
            continue

        left, right = m.group(1).strip(), m.group(2).strip()
        if left.startswith("[") or not right:
            i += 1
            continue

        headline = f"{left} | {right}"
        word, reading = left, right
        def_parts: List[str] = []
        i += 1
        while i < n:
            raw = lines[i]
            if _is_noise(raw):
                i += 1
                continue
            stripped = raw.strip()
            if _ENTRY_HEAD.match(stripped) and not stripped.startswith("["):
                break
            if def_parts or _looks_like_definition_start(stripped):
                def_parts.append(stripped)
                i += 1
                continue
            if not def_parts:
                i += 1
                continue
            def_parts[-1] = def_parts[-1] + " " + stripped
            i += 1

        definitions = "\n".join(def_parts).strip()
        out.append(
            VocabEntry(
                headline=headline,
                word=word,
                reading=reading,
                definitions=definitions,
                source=source_label,
            )
        )

    return out


def load_file(path: Path) -> List[VocabEntry]:
    suffix = path.suffix.lower()
    label = str(path.name)
    if suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace")
        return parse_text(text, label)
    if suffix == ".pdf":
        import fitz  # pymupdf

        doc = fitz.open(path)
        parts: List[str] = []
        for page in doc:
            parts.append(page.get_text("text"))
        doc.close()
        return parse_text("\n".join(parts), label)
    return []


def load_folder(folder: Path) -> List[VocabEntry]:
    all_entries: List[VocabEntry] = []
    if not folder.is_dir():
        return all_entries
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in (".txt", ".pdf"):
            continue
        all_entries.extend(load_file(p))
    return all_entries

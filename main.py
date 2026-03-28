# -*- coding: utf-8 -*-
"""フォルダ内の PDF/TXT から語彙を読み取り、1 件ずつ表示し日本語 TTS で再生するデスクトップアプリ。"""

from __future__ import annotations

import asyncio
import os
import random
import re
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog
from typing import Any, List, Optional

import customtkinter as ctk
import edge_tts
import pygame

import storage
from parser_vocab import VocabEntry, load_file, load_folder

DEFAULT_VOICE = "ja-JP-NanamiNeural"
WINDOW_TITLE = "词条播放器 MOJi PDF文本"


def reading_for_tts(reading: str) -> str:
    """アクセント記号などを除き、読み上げ用の文字列にする。"""
    s = reading.strip()
    s = re.sub(r"\s*[⓪①②③④⑤⑥⑦⑧⑨]+\s*$", "", s)
    s = re.sub(r"\s+\d+\s*$", "", s)
    return s.strip() or reading.strip()


class VocabPlayerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("920x760")
        self.minsize(720, 620)

        self._settings: dict[str, Any] = storage.load_settings()
        self._remembered: dict[str, dict[str, str]] = storage.load_remembered()

        self._pool: List[VocabEntry] = []
        self._entries: List[VocabEntry] = []
        self._index = 0
        self._folder: Optional[Path] = None
        self._auto_thread: Optional[threading.Thread] = None
        self._auto_stop = threading.Event()
        self._tts_busy = threading.Lock()
        self._save_settings_after_id: Optional[str] = None

        pygame.mixer.init()

        self.var_hide_remembered = ctk.BooleanVar(
            value=bool(self._settings.get("hide_remembered", True))
        )
        self.var_shuffle = ctk.BooleanVar(
            value=bool(self._settings.get("shuffle_mode", False))
        )

        self._build_ui()
        self._apply_alpha(self._settings.get("alpha", 1.0))
        self._update_content_text_label()
        self._apply_text_color()
        self._apply_chrome_text_colors()
        self._update_bg_labels()
        self._apply_area_backgrounds()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=12, pady=(12, 4))

        ctk.CTkButton(top, text="选择文件夹", width=120, command=self._pick_folder).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(top, text="单个文件…", width=100, command=self._pick_file).pack(
            side="left", padx=(0, 8)
        )

        self.lbl_folder = ctk.CTkLabel(top, text="未选择目录", anchor="w")
        self.lbl_folder.pack(side="left", fill="x", expand=True)

        self.lbl_count = ctk.CTkLabel(top, text="0 条", width=200, anchor="e")
        self.lbl_count.pack(side="right")

        row_opts = ctk.CTkFrame(self)
        row_opts.pack(fill="x", padx=12, pady=(0, 4))

        ctk.CTkCheckBox(
            row_opts,
            text="隐藏已记住",
            variable=self.var_hide_remembered,
            command=self._on_hide_toggle,
        ).pack(side="left", padx=(0, 12))

        ctk.CTkCheckBox(
            row_opts,
            text="乱序模式",
            variable=self.var_shuffle,
            command=self._on_shuffle_toggle,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(row_opts, text="重新打乱", width=90, command=self._reshuffle_visible).pack(
            side="left", padx=(0, 12)
        )

        ctk.CTkButton(row_opts, text="管理已记住…", width=110, command=self._open_remembered_manager).pack(
            side="left", padx=(0, 0)
        )

        row_look = ctk.CTkFrame(self)
        row_look.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkLabel(row_look, text="文字颜色（词汇/释义）").pack(side="left", padx=(0, 6))
        ctk.CTkButton(row_look, text="选色…", width=70, command=self._pick_content_text_color).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkButton(row_look, text="恢复主题", width=72, command=self._reset_content_text_color).pack(
            side="left", padx=(0, 6)
        )
        self.lbl_content_text_val = ctk.CTkLabel(
            row_look, text="主题默认", width=100, anchor="w"
        )
        self.lbl_content_text_val.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(row_look, text="窗口透明度").pack(side="left", padx=(0, 6))
        self.slider_alpha = ctk.CTkSlider(
            row_look,
            from_=0.25,
            to=1.0,
            number_of_steps=75,
            width=180,
            command=self._on_alpha_slider,
        )
        self.slider_alpha.set(float(self._settings.get("alpha", 1.0)))
        self.slider_alpha.pack(side="left", padx=(0, 8))
        self.lbl_alpha = ctk.CTkLabel(row_look, text="100%", width=44)
        self.lbl_alpha.pack(side="left")

        row_bg = ctk.CTkFrame(self)
        row_bg.pack(fill="x", padx=12, pady=(0, 4))

        ctk.CTkLabel(row_bg, text="词汇区背景").pack(side="left", padx=(0, 4))
        ctk.CTkButton(row_bg, text="选色…", width=56, command=self._pick_bg_head).pack(
            side="left", padx=(0, 6)
        )
        self.lbl_bg_head_val = ctk.CTkLabel(row_bg, text="跟随主题", width=96, anchor="w")
        self.lbl_bg_head_val.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(row_bg, text="释义区背景").pack(side="left", padx=(0, 4))
        ctk.CTkButton(row_bg, text="选色…", width=56, command=self._pick_bg_def).pack(
            side="left", padx=(0, 6)
        )
        self.lbl_bg_def_val = ctk.CTkLabel(row_bg, text="跟随主题", width=96, anchor="w")
        self.lbl_bg_def_val.pack(side="left", padx=(0, 12))

        ctk.CTkButton(row_bg, text="背景恢复默认", width=100, command=self._reset_area_bgs).pack(
            side="left", padx=(0, 0)
        )

        mid = ctk.CTkFrame(self)
        mid.pack(fill="both", expand=True, padx=12, pady=6)

        self.frm_vocab = ctk.CTkFrame(mid, corner_radius=8)
        self.frm_vocab.pack(fill="x", pady=(0, 10))

        self.btn_remember = ctk.CTkButton(
            self.frm_vocab,
            text="已记住（隐藏）",
            width=118,
            command=self._mark_current_remembered,
        )
        self.btn_remember.pack(side="right", padx=(10, 12), pady=12, anchor="n")

        self.txt_head = ctk.CTkTextbox(self.frm_vocab, height=108, font=ctk.CTkFont(size=20))
        self.txt_head.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        self.txt_head.configure(state="disabled")

        self.frm_def = ctk.CTkFrame(mid, corner_radius=8)
        self.frm_def.pack(fill="both", expand=True)

        self.txt_def = ctk.CTkTextbox(self.frm_def, font=ctk.CTkFont(size=15))
        self.txt_def.pack(fill="both", expand=True, padx=10, pady=10)

        nav = ctk.CTkFrame(self)
        nav.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkButton(nav, text="上一条", width=100, command=self._prev).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkButton(nav, text="下一条", width=100, command=self._next).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkButton(nav, text="播放读音", width=110, command=self._play_tts).pack(
            side="left", padx=(0, 6)
        )

        self.var_auto = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            nav, text="自动下一条", variable=self.var_auto, command=self._toggle_auto
        ).pack(side="left", padx=(16, 6))

        ctk.CTkLabel(nav, text="间隔(秒)").pack(side="left", padx=(8, 4))
        self.spin_interval = ctk.CTkEntry(nav, width=50)
        self.spin_interval.insert(0, "2")
        self.spin_interval.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(nav, text="朗读语音").pack(side="left", padx=(8, 4))
        self.combo_voice = ctk.CTkComboBox(
            nav,
            values=[DEFAULT_VOICE, "ja-JP-KeitaNeural"],
            width=200,
        )
        self.combo_voice.set(DEFAULT_VOICE)
        self.combo_voice.pack(side="left")

        bottom = ctk.CTkFrame(self)
        bottom.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkLabel(bottom, text="跳转", width=50).pack(side="left", padx=(0, 6))
        self.entry_jump = ctk.CTkEntry(bottom, width=80, placeholder_text="序号")
        self.entry_jump.pack(side="left", padx=(0, 6))
        ctk.CTkButton(bottom, text="跳转", width=70, command=self._jump).pack(
            side="left", padx=(0, 12)
        )
        self.lbl_source = ctk.CTkLabel(bottom, text="", anchor="w")
        self.lbl_source.pack(side="left", fill="x", expand=True)

    # —— 显示与词库 —— #

    def _default_text_fg(self) -> str:
        m = ctk.get_appearance_mode()
        if m == "Light":
            return "gray10"
        return "#DCE4EE"

    def _resolved_content_text_color(self) -> str:
        """仅用于词汇区 / 释义区 Textbox；空字符串表示跟随主题。"""
        hx = str(self._settings.get("text_color_hex", "") or "").strip()
        if not hx:
            return self._default_text_fg()
        return hx

    def _update_content_text_label(self) -> None:
        hx = str(self._settings.get("text_color_hex", "") or "").strip()
        if hx:
            self.lbl_content_text_val.configure(text=hx)
        else:
            self.lbl_content_text_val.configure(text="主题默认")

    def _apply_chrome_text_colors(self) -> None:
        """路径、统计、透明度、背景说明、文字色说明等沿用主题文字色。"""
        c = self._default_text_fg()
        for w in (
            self.lbl_folder,
            self.lbl_count,
            self.lbl_source,
            self.lbl_alpha,
            self.lbl_bg_head_val,
            self.lbl_bg_def_val,
            self.lbl_content_text_val,
        ):
            try:
                w.configure(text_color=c)
            except Exception:
                pass

    def _theme_bg_tuples(self) -> tuple[tuple[str, str], tuple[str, str]]:
        """(词汇区, 释义区) 随深浅主题的默认背景色。"""
        return (("#F0F0F0", "#2B2B2B"), ("#FFFFFF", "#1A1A1A"))

    def _resolved_bg_head(self) -> str | tuple[str, str]:
        if str(self._settings.get("bg_head_mode", "default")) != "custom":
            return self._theme_bg_tuples()[0]
        return str(self._settings.get("bg_head_hex", "#F0F0F0"))

    def _resolved_bg_def(self) -> str | tuple[str, str]:
        if str(self._settings.get("bg_def_mode", "default")) != "custom":
            return self._theme_bg_tuples()[1]
        return str(self._settings.get("bg_def_hex", "#FFFFFF"))

    def _apply_area_backgrounds(self) -> None:
        h, d = self._resolved_bg_head(), self._resolved_bg_def()
        try:
            self.frm_vocab.configure(fg_color=h)
            self.txt_head.configure(fg_color=h)
        except Exception:
            pass
        try:
            self.frm_def.configure(fg_color=d)
            self.txt_def.configure(fg_color=d)
        except Exception:
            pass

    def _update_bg_labels(self) -> None:
        if str(self._settings.get("bg_head_mode", "default")) == "custom":
            self.lbl_bg_head_val.configure(text=str(self._settings.get("bg_head_hex", "")))
        else:
            self.lbl_bg_head_val.configure(text="跟随主题")
        if str(self._settings.get("bg_def_mode", "default")) == "custom":
            self.lbl_bg_def_val.configure(text=str(self._settings.get("bg_def_hex", "")))
        else:
            self.lbl_bg_def_val.configure(text="跟随主题")

    def _pick_bg_head(self) -> None:
        init = str(self._settings.get("bg_head_hex", "#F0F0F0"))
        if str(self._settings.get("bg_head_mode", "default")) != "custom":
            init = "#F0F0F0"
        tup = colorchooser.askcolor(color=init, title="词汇区背景")
        if not tup or tup[1] is None:
            return
        self._settings["bg_head_hex"] = tup[1]
        self._settings["bg_head_mode"] = "custom"
        self._apply_area_backgrounds()
        self._update_bg_labels()
        self._apply_text_color()
        self._schedule_save_settings()

    def _pick_bg_def(self) -> None:
        init = str(self._settings.get("bg_def_hex", "#FFFFFF"))
        if str(self._settings.get("bg_def_mode", "default")) != "custom":
            init = "#FFFFFF"
        tup = colorchooser.askcolor(color=init, title="释义区背景")
        if not tup or tup[1] is None:
            return
        self._settings["bg_def_hex"] = tup[1]
        self._settings["bg_def_mode"] = "custom"
        self._apply_area_backgrounds()
        self._update_bg_labels()
        self._apply_text_color()
        self._schedule_save_settings()

    def _reset_area_bgs(self) -> None:
        self._settings["bg_head_mode"] = "default"
        self._settings["bg_def_mode"] = "default"
        self._apply_area_backgrounds()
        self._update_bg_labels()
        self._apply_text_color()
        self._schedule_save_settings()

    def _apply_text_color(self) -> None:
        c = self._resolved_content_text_color()
        for w in (self.txt_head, self.txt_def):
            try:
                w.configure(text_color=c)
            except Exception:
                pass

    def _pick_content_text_color(self) -> None:
        init = self._resolved_content_text_color()
        tup = colorchooser.askcolor(color=init, title="词汇/释义文字颜色")
        if not tup or tup[1] is None:
            return
        self._settings["text_color_hex"] = tup[1]
        self._update_content_text_label()
        self._apply_text_color()
        self._apply_chrome_text_colors()
        self._schedule_save_settings()

    def _reset_content_text_color(self) -> None:
        self._settings["text_color_hex"] = ""
        self._update_content_text_label()
        self._apply_text_color()
        self._apply_chrome_text_colors()
        self._schedule_save_settings()

    def _on_alpha_slider(self, value: float | str) -> None:
        a = float(value)
        self._apply_alpha(a)
        pct = int(round(a * 100))
        self.lbl_alpha.configure(text=f"{pct}%")
        self._settings["alpha"] = a
        self._schedule_save_settings()

    def _apply_alpha(self, a: float) -> None:
        a = max(0.25, min(1.0, float(a)))
        try:
            self.attributes("-alpha", a)
        except Exception:
            pass

    def _schedule_save_settings(self) -> None:
        if self._save_settings_after_id is not None:
            try:
                self.after_cancel(self._save_settings_after_id)
            except Exception:
                pass

        def _do() -> None:
            self._save_settings_after_id = None
            self._flush_settings()

        self._save_settings_after_id = self.after(400, _do)

    def _flush_settings(self) -> None:
        self._settings["hide_remembered"] = self.var_hide_remembered.get()
        self._settings["shuffle_mode"] = self.var_shuffle.get()
        storage.save_settings(self._settings)

    def _set_text_widgets(self, head: str, body: str, source: str) -> None:
        content_c = self._resolved_content_text_color()
        chrome_c = self._default_text_fg()
        for w, content in ((self.txt_head, head), (self.txt_def, body)):
            w.configure(state="normal")
            w.delete("1.0", "end")
            w.insert("1.0", content)
            try:
                w.configure(text_color=content_c)
            except Exception:
                pass
            w.configure(state="disabled")
        self.lbl_source.configure(text=source, text_color=chrome_c)
        self._apply_area_backgrounds()

    def _show_current(self) -> None:
        chrome_c = self._default_text_fg()
        self.lbl_folder.configure(text_color=chrome_c)
        self.lbl_count.configure(text_color=chrome_c)

        total_pool = len(self._pool)
        rem = len(self._remembered)
        if not self._entries:
            msg = "当前没有可显示的词条。"
            if total_pool > 0:
                msg += "\n可关闭「隐藏已记住」或点击「管理已记住…」移除部分条目。"
            else:
                msg += "\n请选择包含 PDF 或 TXT 的文件夹。"
            self._set_text_widgets("", msg, "")
            self.lbl_count.configure(text=f"0 条（词库 {total_pool}，已记住 {rem}）")
            return

        e = self._entries[self._index]
        vis_n = len(self._entries)
        head = f"{e.word}  |  {e.reading}\n（{self._index + 1} / {vis_n}）"
        self._set_text_widgets(
            head,
            e.definitions or "（无释义行）",
            f"来源：{e.source}  ·  词库 {total_pool} 条  ·  已记住 {rem} 条",
        )
        self.lbl_count.configure(text=f"{vis_n} 条显示（词库 {total_pool}，已记住 {rem}）")

    def _rebuild_visible(self, reset_index: bool = False) -> None:
        hide = self.var_hide_remembered.get()
        vis: List[VocabEntry] = []
        for e in self._pool:
            eid = storage.entry_id(e)
            if hide and eid in self._remembered:
                continue
            vis.append(e)
        if self.var_shuffle.get():
            random.shuffle(vis)
        self._entries = vis
        if reset_index:
            self._index = 0
        else:
            self._index = min(self._index, max(0, len(self._entries) - 1))
        self._show_current()

    def _load_entries(self, entries: List[VocabEntry], folder_hint: Optional[Path]) -> None:
        self._stop_auto()
        self._pool = list(entries)
        self._folder = folder_hint
        if folder_hint:
            self.lbl_folder.configure(text=str(folder_hint))
        self._rebuild_visible(reset_index=True)

    def _mark_current_remembered(self) -> None:
        if not self._entries:
            return
        e = self._entries[self._index]
        eid = storage.entry_id(e)
        if eid in self._remembered:
            return
        self._remembered[eid] = storage.meta_for_entry(e)
        storage.save_remembered(self._remembered)
        if self.var_hide_remembered.get():
            self._entries.pop(self._index)
            if self._index >= len(self._entries):
                self._index = max(0, len(self._entries) - 1)
        self._show_current()

    def _on_hide_toggle(self) -> None:
        self._settings["hide_remembered"] = self.var_hide_remembered.get()
        self._rebuild_visible(reset_index=True)
        self._schedule_save_settings()

    def _on_shuffle_toggle(self) -> None:
        self._settings["shuffle_mode"] = self.var_shuffle.get()
        self._rebuild_visible(reset_index=True)
        self._schedule_save_settings()

    def _reshuffle_visible(self) -> None:
        if len(self._entries) < 2:
            return
        random.shuffle(self._entries)
        self._index = 0
        self._show_current()

    def _open_remembered_manager(self) -> None:
        top = ctk.CTkToplevel(self)
        top.title("已记住的词条")
        top.geometry("640x420")
        top.transient(self)

        ctk.CTkLabel(
            top,
            text="选中一行后点击「移除选中」，将从「已记住」中删除并重新参与显示（若开启隐藏则仍按规则过滤）。",
            wraplength=600,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(12, 6))

        frame = ctk.CTkFrame(top)
        frame.pack(fill="both", expand=True, padx=12, pady=6)

        lb = tk.Listbox(frame, font=("Microsoft YaHei UI", 11), selectmode=tk.SINGLE)
        scroll = tk.Scrollbar(frame, command=lb.yview)
        lb.configure(yscrollcommand=scroll.set)
        lb.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def refresh_list() -> None:
            lb.delete(0, tk.END)
            self._manager_ids = []
            for eid, meta in sorted(
                self._remembered.items(),
                key=lambda x: (x[1].get("source", ""), x[1].get("headline", "")),
            ):
                line = f"{meta.get('headline', '')}  ({meta.get('source', '')})"
                lb.insert(tk.END, line)
                self._manager_ids.append(eid)

        def remove_sel() -> None:
            sel = lb.curselection()
            if not sel:
                return
            i = int(sel[0])
            if i < 0 or i >= len(self._manager_ids):
                return
            eid = self._manager_ids[i]
            self._remembered.pop(eid, None)
            storage.save_remembered(self._remembered)
            refresh_list()
            self._rebuild_visible(reset_index=False)

        refresh_list()

        row = ctk.CTkFrame(top)
        row.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(row, text="移除选中", command=remove_sel).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="关闭", command=top.destroy).pack(side="left")

    def _pick_folder(self) -> None:
        d = filedialog.askdirectory(title="选择词条文件夹")
        if not d:
            return
        p = Path(d)
        entries = load_folder(p)
        self._load_entries(entries, p)
        if not entries:
            self._set_text_widgets(
                "",
                "该文件夹内未解析到词条。\n支持：.pdf / .txt\n格式示例：\n呆気ない | あっけない ④\n[形] 释义…",
                "",
            )

    def _pick_file(self) -> None:
        f = filedialog.askopenfilename(
            title="选择 PDF 或 TXT",
            filetypes=[("PDF / 文本", "*.pdf *.txt"), ("全部", "*.*")],
        )
        if not f:
            return
        p = Path(f)
        entries = load_file(p)
        self._load_entries(entries, p.parent)
        self.lbl_folder.configure(text=str(p))
        if not entries:
            self._set_text_widgets("", "未能从该文件解析到词条。", str(p.name))

    def _prev(self) -> None:
        if not self._entries:
            return
        self._index = (self._index - 1) % len(self._entries)
        self._show_current()

    def _next(self) -> None:
        if not self._entries:
            return
        self._index = (self._index + 1) % len(self._entries)
        self._show_current()

    def _jump(self) -> None:
        if not self._entries:
            return
        raw = self.entry_jump.get().strip()
        if not raw.isdigit():
            return
        n = int(raw)
        if 1 <= n <= len(self._entries):
            self._index = n - 1
            self._show_current()

    def _interval_sec(self) -> float:
        try:
            v = float(self.spin_interval.get().strip().replace(",", "."))
            return max(0.5, min(120.0, v))
        except ValueError:
            return 2.0

    def _play_tts(self) -> None:
        if not self._entries:
            return
        e = self._entries[self._index]
        text = reading_for_tts(e.reading)
        if not text:
            return
        voice = self.combo_voice.get() or DEFAULT_VOICE

        def run() -> None:
            if not self._tts_busy.acquire(blocking=False):
                return
            try:
                self._run_tts_blocking(text, voice)
            except Exception as ex:  # noqa: BLE001
                self.after(0, lambda: self._tts_error(str(ex)))
            finally:
                self._tts_busy.release()

        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    async def _edge_save(text: str, voice: str, out_path: Path) -> None:
        comm = edge_tts.Communicate(text, voice)
        await comm.save(str(out_path))

    @staticmethod
    def _release_music_file() -> None:
        """再生中の MP3 を解放し、同じパスへの上書きや削除で WinError 5/32 を避ける。"""
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        unload = getattr(pygame.mixer.music, "unload", None)
        if callable(unload):
            try:
                unload()
            except Exception:
                pass

    def _run_tts_blocking(self, text: str, voice: str) -> None:
        self._release_music_file()
        fd, name = tempfile.mkstemp(suffix=".mp3", prefix="vocab_tts_")
        os.close(fd)
        path = Path(name)
        try:
            asyncio.run(self._edge_save(text, voice, path))
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            ev = threading.Event()
            while pygame.mixer.music.get_busy():
                if self._auto_stop.is_set():
                    pygame.mixer.music.stop()
                    break
                ev.wait(0.06)
        finally:
            self._release_music_file()
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _tts_error(self, msg: str) -> None:
        self.txt_def.configure(state="normal")
        self.txt_def.insert("end", f"\n\n[TTS 错误] {msg}")
        try:
            self.txt_def.configure(text_color=self._resolved_content_text_color())
        except Exception:
            pass
        self.txt_def.configure(state="disabled")

    def _stop_auto(self) -> None:
        self._auto_stop.set()
        if self._auto_thread and self._auto_thread.is_alive():
            self._auto_thread.join(timeout=2.0)
        self._auto_stop.clear()
        self._auto_thread = None

    def _toggle_auto(self) -> None:
        if self.var_auto.get():
            self._start_auto()
        else:
            self._stop_auto()

    def _start_auto(self) -> None:
        if not self._entries:
            self.var_auto.set(False)
            return
        self._stop_auto()
        self._auto_stop.clear()

        def loop() -> None:
            while not self._auto_stop.is_set() and self.var_auto.get():
                if not self._entries:
                    break
                voice = self.combo_voice.get() or DEFAULT_VOICE
                e = self._entries[self._index]
                text = reading_for_tts(e.reading)
                with self._tts_busy:
                    if self._auto_stop.is_set():
                        break
                    try:
                        if text:
                            self._run_tts_blocking(text, voice)
                    except Exception as ex:  # noqa: BLE001
                        self.after(0, lambda e=str(ex): self._tts_error(e))
                if self._auto_stop.is_set():
                    break
                ev = threading.Event()
                end = time.monotonic() + self._interval_sec()
                while not self._auto_stop.is_set():
                    if time.monotonic() >= end:
                        break
                    ev.wait(0.08)
                if self._auto_stop.is_set():
                    break
                self.after(0, self._next)
                time.sleep(0.05)

        self._auto_thread = threading.Thread(target=loop, daemon=True)
        self._auto_thread.start()

    def _on_close(self) -> None:
        self._stop_auto()
        if self._save_settings_after_id is not None:
            try:
                self.after_cancel(self._save_settings_after_id)
            except Exception:
                pass
        self._flush_settings()
        pygame.mixer.quit()
        self.destroy()


def main() -> None:
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    app = VocabPlayerApp()
    app.mainloop()


if __name__ == "__main__":
    main()

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
from tkinter import colorchooser, filedialog, messagebox
from typing import Any, List, Optional

import customtkinter as ctk
import edge_tts
import pygame

import storage
from parser_vocab import VocabEntry, load_file, load_folder

DEFAULT_VOICE = "ja-JP-NanamiNeural"
VOICE_OPTIONS = [DEFAULT_VOICE, "ja-JP-KeitaNeural"]
WINDOW_TITLE = "词条播放器 MOJi PDF文本"

# 词汇区右侧「已记住」按钮尺寸（参照常见红框区域）
REMEMBER_BTN_WIDTH = 200
REMEMBER_BTN_HEIGHT = 92


def reading_for_tts(reading: str) -> str:
    """アクセント記号などを除き、読み上げ用の文字列にする。"""
    s = reading.strip()
    s = re.sub(r"\s*[⓪①②③④⑤⑥⑦⑧⑨]+\s*$", "", s)
    s = re.sub(r"\s+\d+\s*$", "", s)
    return s.strip() or reading.strip()


def _section_label(parent: ctk.CTkFrame, text: str) -> None:
    ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(weight="bold")).pack(
        anchor="w", pady=(10, 4)
    )


class SettingsWindow(ctk.CTkToplevel):
    """外観・語彙ソース・TTS・復習オプションをまとめた設定ウィンドウ。"""

    def __init__(self, app: "VocabPlayerApp") -> None:
        super().__init__(app)
        self.app = app
        self.title("设置")
        self.geometry("540x680")
        self.minsize(480, 520)
        self.transient(app)

        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        _section_label(body, "复习与列表")
        row_rev = ctk.CTkFrame(body, fg_color="transparent")
        row_rev.pack(fill="x")
        ctk.CTkCheckBox(
            row_rev,
            text="隐藏已记住",
            variable=app.var_hide_remembered,
            command=app._on_hide_toggle,
        ).pack(side="left", padx=(0, 12))
        ctk.CTkCheckBox(
            row_rev,
            text="乱序模式",
            variable=app.var_shuffle,
            command=app._on_shuffle_toggle,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row_rev, text="重新打乱", width=90, command=app._reshuffle_visible).pack(
            side="left", padx=(0, 12)
        )
        ctk.CTkButton(row_rev, text="管理已记住…", width=110, command=app._open_remembered_manager).pack(
            side="left"
        )

        _section_label(body, "文字与背景")
        row_tc = ctk.CTkFrame(body, fg_color="transparent")
        row_tc.pack(fill="x")
        ctk.CTkLabel(row_tc, text="词汇/释义文字色").pack(side="left", padx=(0, 6))
        ctk.CTkButton(row_tc, text="选色…", width=70, command=app._pick_content_text_color).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkButton(row_tc, text="恢复主题", width=72, command=app._reset_content_text_color).pack(
            side="left", padx=(0, 6)
        )
        self.lbl_content_text_val = ctk.CTkLabel(row_tc, text="主题默认", width=100, anchor="w")
        self.lbl_content_text_val.pack(side="left", padx=(0, 8))

        row_alpha = ctk.CTkFrame(body, fg_color="transparent")
        row_alpha.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(row_alpha, text="窗口透明度").pack(side="left", padx=(0, 8))
        self.slider_alpha = ctk.CTkSlider(
            row_alpha,
            from_=0.25,
            to=1.0,
            number_of_steps=75,
            width=200,
            command=app._on_alpha_slider,
        )
        self.slider_alpha.set(float(app._settings.get("alpha", 1.0)))
        self.slider_alpha.pack(side="left", padx=(0, 8))
        self.lbl_alpha = ctk.CTkLabel(row_alpha, text="100%", width=44)
        self.lbl_alpha.pack(side="left")
        pct = int(round(float(app._settings.get("alpha", 1.0)) * 100))
        self.lbl_alpha.configure(text=f"{pct}%")

        row_bg = ctk.CTkFrame(body, fg_color="transparent")
        row_bg.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(row_bg, text="词汇区背景").pack(side="left", padx=(0, 4))
        ctk.CTkButton(row_bg, text="选色…", width=56, command=app._pick_bg_head).pack(
            side="left", padx=(0, 6)
        )
        self.lbl_bg_head_val = ctk.CTkLabel(row_bg, text="跟随主题", width=96, anchor="w")
        self.lbl_bg_head_val.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row_bg, text="释义区背景").pack(side="left", padx=(0, 4))
        ctk.CTkButton(row_bg, text="选色…", width=56, command=app._pick_bg_def).pack(
            side="left", padx=(0, 6)
        )
        self.lbl_bg_def_val = ctk.CTkLabel(row_bg, text="跟随主题", width=96, anchor="w")
        self.lbl_bg_def_val.pack(side="left", padx=(0, 12))
        ctk.CTkButton(row_bg, text="背景恢复默认", width=100, command=app._reset_area_bgs).pack(
            side="left"
        )

        _section_label(body, "字体大小")
        row_fh = ctk.CTkFrame(body, fg_color="transparent")
        row_fh.pack(fill="x")
        ctk.CTkLabel(row_fh, text="词汇区字号").pack(side="left", padx=(0, 8))
        self.slider_font_head = ctk.CTkSlider(
            row_fh,
            from_=10,
            to=48,
            number_of_steps=38,
            width=220,
            command=self._on_font_head_slider,
        )
        self.slider_font_head.set(int(app._settings.get("font_head_pt", 20)))
        self.slider_font_head.pack(side="left", padx=(0, 8))
        self.lbl_font_head_pt = ctk.CTkLabel(row_fh, text="", width=56, anchor="w")
        self.lbl_font_head_pt.pack(side="left")
        self._on_font_head_slider(self.slider_font_head.get())

        row_fd = ctk.CTkFrame(body, fg_color="transparent")
        row_fd.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(row_fd, text="释义区字号").pack(side="left", padx=(0, 8))
        self.slider_font_def = ctk.CTkSlider(
            row_fd,
            from_=9,
            to=40,
            number_of_steps=31,
            width=220,
            command=self._on_font_def_slider,
        )
        self.slider_font_def.set(int(app._settings.get("font_def_pt", 15)))
        self.slider_font_def.pack(side="left", padx=(0, 8))
        self.lbl_font_def_pt = ctk.CTkLabel(row_fd, text="", width=56, anchor="w")
        self.lbl_font_def_pt.pack(side="left")
        self._on_font_def_slider(self.slider_font_def.get())

        _section_label(body, "朗读语音")
        row_tts = ctk.CTkFrame(body, fg_color="transparent")
        row_tts.pack(fill="x")
        self.combo_voice = ctk.CTkComboBox(
            row_tts,
            values=list(VOICE_OPTIONS),
            width=220,
            command=lambda _v: app._schedule_save_settings(),
        )
        self.combo_voice.set(str(app._settings.get("tts_voice", DEFAULT_VOICE)))
        self.combo_voice.pack(side="left")

        _section_label(body, "收藏")
        row_fav = ctk.CTkFrame(body, fg_color="transparent")
        row_fav.pack(fill="x")
        ctk.CTkButton(
            row_fav,
            text="导出收藏为 TXT…",
            width=180,
            command=app._export_favorites,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            row_fav,
            text="主窗口可点击「收藏」添加当前词条。",
            text_color=("gray30", "gray70"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        foot = ctk.CTkFrame(self)
        foot.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(foot, text="关闭", width=100, command=self._on_close).pack(side="right")

        self.sync_labels_from_app()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_font_head_slider(self, value: float | str) -> None:
        pt = int(round(float(value)))
        pt = max(10, min(48, pt))
        self.lbl_font_head_pt.configure(text=f"{pt} pt")
        self.app._settings["font_head_pt"] = pt
        self.app._apply_font_sizes()
        self.app._schedule_save_settings()

    def _on_font_def_slider(self, value: float | str) -> None:
        pt = int(round(float(value)))
        pt = max(9, min(40, pt))
        self.lbl_font_def_pt.configure(text=f"{pt} pt")
        self.app._settings["font_def_pt"] = pt
        self.app._apply_font_sizes()
        self.app._schedule_save_settings()

    def sync_labels_from_app(self) -> None:
        hx = str(self.app._settings.get("text_color_hex", "") or "").strip()
        if hx:
            self.lbl_content_text_val.configure(text=hx)
        else:
            self.lbl_content_text_val.configure(text="主题默认")
        if str(self.app._settings.get("bg_head_mode", "default")) == "custom":
            self.lbl_bg_head_val.configure(text=str(self.app._settings.get("bg_head_hex", "")))
        else:
            self.lbl_bg_head_val.configure(text="跟随主题")
        if str(self.app._settings.get("bg_def_mode", "default")) == "custom":
            self.lbl_bg_def_val.configure(text=str(self.app._settings.get("bg_def_hex", "")))
        else:
            self.lbl_bg_def_val.configure(text="跟随主题")
        a = float(self.app._settings.get("alpha", 1.0))
        self.lbl_alpha.configure(text=f"{int(round(a * 100))}%")
        try:
            self.slider_alpha.set(a)
        except Exception:
            pass

    def _on_close(self) -> None:
        self.app._flush_settings_from_settings_ui()
        self.app._settings_win = None
        self.destroy()


class VocabPlayerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("920x760")
        self.minsize(720, 620)

        self._settings: dict[str, Any] = storage.load_settings()
        self._remembered: dict[str, dict[str, str]] = storage.load_remembered()
        self._favorites: dict[str, dict[str, str]] = storage.load_favorites()

        self._pool: List[VocabEntry] = []
        self._entries: List[VocabEntry] = []
        self._index = 0
        self._folder: Optional[Path] = None
        self._auto_thread: Optional[threading.Thread] = None
        self._auto_stop = threading.Event()
        self._auto_nav_event = threading.Event()
        self._auto_after_advance_id: Optional[str] = None
        self._tts_busy = threading.Lock()
        self._save_settings_after_id: Optional[str] = None
        self._settings_win: Optional[SettingsWindow] = None

        pygame.mixer.init()

        self.var_hide_remembered = ctk.BooleanVar(
            value=bool(self._settings.get("hide_remembered", True))
        )
        self.var_shuffle = ctk.BooleanVar(
            value=bool(self._settings.get("shuffle_mode", False))
        )
        self.var_auto = ctk.BooleanVar(value=bool(self._settings.get("auto_advance", False)))

        self._build_ui()
        self._apply_alpha(self._settings.get("alpha", 1.0))
        self._apply_chrome_text_colors()
        self._apply_text_color()
        self._apply_font_sizes()
        self._apply_area_backgrounds()
        self._update_favorite_button()
        self.after(80, self._try_restore_last_source)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=12, pady=(12, 4))

        ctk.CTkButton(top, text="设置…", width=88, command=self._open_settings).pack(
            side="left", padx=(0, 8)
        )
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

        mid = ctk.CTkFrame(self)
        mid.pack(fill="both", expand=True, padx=12, pady=6)

        self.frm_vocab = ctk.CTkFrame(mid, corner_radius=8)
        self.frm_vocab.pack(fill="x", pady=(0, 10))

        fh = int(self._settings.get("font_head_pt", 20))
        self.txt_head = ctk.CTkTextbox(self.frm_vocab, height=80, font=ctk.CTkFont(size=fh))
        self.txt_head.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)

        right_col = ctk.CTkFrame(self.frm_vocab, fg_color="transparent")
        right_col.pack(side="right", padx=(10, 12), pady=10, fill="y")

        self.btn_remember = ctk.CTkButton(
            right_col,
            text="已记住",
            width=REMEMBER_BTN_WIDTH,
            height=REMEMBER_BTN_HEIGHT,
            command=self._mark_current_remembered,
        )
        self.btn_remember.pack(anchor="ne")

        self.btn_favorite = ctk.CTkButton(
            right_col,
            text="收藏",
            width=REMEMBER_BTN_WIDTH,
            height=44,
            command=self._toggle_favorite,
        )
        self.btn_favorite.pack(anchor="ne", pady=(10, 0))

        self.frm_def = ctk.CTkFrame(mid, corner_radius=8)
        self.frm_def.pack(fill="both", expand=True)

        fd = int(self._settings.get("font_def_pt", 15))
        self.txt_def = ctk.CTkTextbox(self.frm_def, font=ctk.CTkFont(size=fd))
        self.txt_def.pack(fill="both", expand=True, padx=10, pady=10)

        nav = ctk.CTkFrame(self)
        nav.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkButton(nav, text="上一条", width=100, command=self._prev).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkButton(nav, text="下一条", width=100, command=self._next).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkButton(nav, text="播放读音", width=110, command=self._play_tts).pack(
            side="left", padx=(0, 6)
        )

        auto_nav = ctk.CTkFrame(nav, fg_color="transparent")
        auto_nav.pack(side="left", padx=(14, 0))
        ctk.CTkCheckBox(
            auto_nav,
            text="自动下一条",
            variable=self.var_auto,
            command=self._toggle_auto,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(auto_nav, text="间隔(秒)").pack(side="left", padx=(0, 4))
        self.entry_interval = ctk.CTkEntry(auto_nav, width=50)
        self.entry_interval.pack(side="left", padx=(0, 0))
        iv = float(self._settings.get("auto_interval_sec", 2.0))
        if iv == int(iv):
            self.entry_interval.insert(0, str(int(iv)))
        else:
            self.entry_interval.insert(0, str(iv))
        self.entry_interval.bind("<FocusOut>", lambda _e: self._schedule_save_settings())
        self.entry_interval.bind("<Return>", lambda _e: self._schedule_save_settings())

    def _open_settings(self) -> None:
        if self._settings_win is not None:
            try:
                if self._settings_win.winfo_exists():
                    self._settings_win.lift()
                    self._settings_win.focus()
                    self._settings_win.sync_labels_from_app()
                    return
            except Exception:
                pass
        self._settings_win = SettingsWindow(self)

    def _flush_settings_from_settings_ui(self) -> None:
        sw = self._settings_win
        if sw is None:
            return
        try:
            if not sw.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            self._settings["tts_voice"] = sw.combo_voice.get() or DEFAULT_VOICE
        except (AttributeError, tk.TclError):
            pass

    def _flush_interval_from_main_entry(self) -> None:
        try:
            raw = self.entry_interval.get().strip().replace(",", ".")
            v = float(raw)
            self._settings["auto_interval_sec"] = max(0.5, min(120.0, v))
        except (ValueError, tk.TclError):
            pass

    def _apply_font_sizes(self) -> None:
        h = int(self._settings.get("font_head_pt", 20))
        d = int(self._settings.get("font_def_pt", 15))
        h = max(10, min(48, h))
        d = max(9, min(40, d))
        try:
            self.txt_head.configure(font=ctk.CTkFont(size=h))
        except Exception:
            pass
        try:
            self.txt_def.configure(font=ctk.CTkFont(size=d))
        except Exception:
            pass

    def _toggle_favorite(self) -> None:
        if not self._entries:
            return
        e = self._entries[self._index]
        eid = storage.entry_id(e)
        if eid in self._favorites:
            self._favorites.pop(eid, None)
        else:
            self._favorites[eid] = storage.favorite_meta_for_entry(e)
        storage.save_favorites(self._favorites)
        self._update_favorite_button()

    def _update_favorite_button(self) -> None:
        if not self._entries:
            try:
                self.btn_favorite.configure(state="disabled", text="收藏")
            except Exception:
                pass
            return
        try:
            self.btn_favorite.configure(state="normal")
        except Exception:
            pass
        eid = storage.entry_id(self._entries[self._index])
        if eid in self._favorites:
            self.btn_favorite.configure(text="已收藏")
        else:
            self.btn_favorite.configure(text="收藏")

    def _export_favorites(self) -> None:
        if not self._favorites:
            messagebox.showinfo("导出收藏", "当前没有收藏词条。")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本", "*.txt"), ("全部", "*.*")],
            title="导出收藏为 TXT",
        )
        if not path:
            return
        lines: List[str] = []
        for _eid, meta in sorted(
            self._favorites.items(),
            key=lambda x: (x[1].get("source", ""), x[1].get("headline", "")),
        ):
            head = meta.get("headline", "")
            defs = (meta.get("definitions") or "").strip()
            lines.append(head)
            if defs:
                lines.append(defs)
            lines.append("")
        Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        messagebox.showinfo("导出收藏", f"已写入：\n{path}")

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

    def _apply_chrome_text_colors(self) -> None:
        c = self._default_text_fg()
        for w in (self.lbl_folder, self.lbl_count, self.entry_interval):
            try:
                w.configure(text_color=c)
            except Exception:
                pass
        sw = self._settings_win
        if sw is not None:
            try:
                if sw.winfo_exists():
                    for w in (
                        sw.lbl_content_text_val,
                        sw.lbl_alpha,
                        sw.lbl_bg_head_val,
                        sw.lbl_bg_def_val,
                        sw.lbl_font_head_pt,
                        sw.lbl_font_def_pt,
                    ):
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
        self._apply_text_color()
        self._schedule_save_settings()
        if self._settings_win:
            try:
                self._settings_win.sync_labels_from_app()
            except Exception:
                pass

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
        self._apply_text_color()
        self._schedule_save_settings()
        if self._settings_win:
            try:
                self._settings_win.sync_labels_from_app()
            except Exception:
                pass

    def _reset_area_bgs(self) -> None:
        self._settings["bg_head_mode"] = "default"
        self._settings["bg_def_mode"] = "default"
        self._apply_area_backgrounds()
        self._apply_text_color()
        self._schedule_save_settings()
        if self._settings_win:
            try:
                self._settings_win.sync_labels_from_app()
            except Exception:
                pass

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
        self._apply_text_color()
        self._apply_chrome_text_colors()
        self._schedule_save_settings()
        if self._settings_win:
            try:
                self._settings_win.sync_labels_from_app()
            except Exception:
                pass

    def _reset_content_text_color(self) -> None:
        self._settings["text_color_hex"] = ""
        self._apply_text_color()
        self._apply_chrome_text_colors()
        self._schedule_save_settings()
        if self._settings_win:
            try:
                self._settings_win.sync_labels_from_app()
            except Exception:
                pass

    def _on_alpha_slider(self, value: float | str) -> None:
        a = float(value)
        self._apply_alpha(a)
        pct = int(round(a * 100))
        if self._settings_win:
            try:
                self._settings_win.lbl_alpha.configure(text=f"{pct}%")
            except Exception:
                pass
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
        self._flush_settings_from_settings_ui()
        self._flush_interval_from_main_entry()
        self._settings["hide_remembered"] = self.var_hide_remembered.get()
        self._settings["shuffle_mode"] = self.var_shuffle.get()
        self._settings["auto_advance"] = self.var_auto.get()
        storage.save_settings(self._settings)

    def _set_text_widgets(self, head: str, body: str) -> None:
        content_c = self._resolved_content_text_color()
        for w, content in ((self.txt_head, head), (self.txt_def, body)):
            w.configure(state="normal")
            w.delete("1.0", "end")
            w.insert("1.0", content)
            try:
                w.configure(text_color=content_c)
            except Exception:
                pass
            w.configure(state="disabled")
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
                msg += "\n可关闭「隐藏已记住」或在设置中打开「管理已记住…」移除部分条目。"
            else:
                msg += "\n请点击上方「选择文件夹」或「单个文件…」加载 PDF / TXT。"
            self._set_text_widgets("", msg)
            self.lbl_count.configure(text=f"0 条（词库 {total_pool}，已记住 {rem}）")
            self._update_favorite_button()
            return

        e = self._entries[self._index]
        vis_n = len(self._entries)
        head = f"{e.word}  |  {e.reading}"
        self._set_text_widgets(head, e.definitions or "（无释义行）")
        self.lbl_count.configure(text=f"{vis_n} 条显示（词库 {total_pool}，已记住 {rem}）")
        self._update_favorite_button()

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

    def _try_restore_last_source(self) -> None:
        """启动时若存在上次成功打开的文件夹或文件，则自动加载。"""
        kind = str(self._settings.get("last_source_kind", "") or "")
        if kind == "folder":
            raw = str(self._settings.get("last_folder_path", "") or "").strip()
            if not raw:
                return
            p = Path(raw)
            if not p.is_dir():
                return
            entries = load_folder(p)
            self._load_entries(entries, p)
            if not entries:
                self._set_text_widgets(
                    "",
                    "上次打开的文件夹中未解析到词条。\n支持：.pdf / .txt",
                )
        elif kind == "file":
            raw = str(self._settings.get("last_file_path", "") or "").strip()
            if not raw:
                return
            p = Path(raw)
            if not p.is_file():
                return
            entries = load_file(p)
            self._load_entries(entries, p.parent)
            self.lbl_folder.configure(text=str(p))
            if not entries:
                self._set_text_widgets("", "未能从上次打开的文件解析到词条。")

    def _initial_dir_for_dialog(self) -> str:
        d = str(self._settings.get("last_folder_path", "") or "").strip()
        if d and Path(d).is_dir():
            return d
        f = str(self._settings.get("last_file_path", "") or "").strip()
        if f:
            parent = Path(f).parent
            if parent.is_dir():
                return str(parent)
        return ""

    def _persist_last_folder(self, p: Path) -> None:
        self._settings["last_source_kind"] = "folder"
        self._settings["last_folder_path"] = str(p.resolve())
        self._settings["last_file_path"] = ""
        self._schedule_save_settings()

    def _persist_last_file(self, p: Path) -> None:
        self._settings["last_source_kind"] = "file"
        self._settings["last_file_path"] = str(p.resolve())
        self._settings["last_folder_path"] = str(p.parent.resolve())
        self._schedule_save_settings()

    def _load_entries(self, entries: List[VocabEntry], folder_hint: Optional[Path]) -> None:
        self._stop_auto()
        self._pool = list(entries)
        self._folder = folder_hint
        if folder_hint:
            self.lbl_folder.configure(text=str(folder_hint))
        self._rebuild_visible(reset_index=True)
        if self.var_auto.get() and self._entries:
            self.after(120, self._start_auto)

    def _mark_current_remembered(self) -> None:
        if not self._entries:
            return
        e = self._entries[self._index]
        eid = storage.entry_id(e)
        if eid in self._remembered:
            return

        was_auto = self.var_auto.get()
        hide = self.var_hide_remembered.get()
        # 隐藏并从列表移除后，自动线程仍处在「刚播完上一词、接下来要间隔再 _next」的旧阶段，会与
        # 新列表/索引错位，出现下一条几乎不显示、不朗读就再跳。隐藏移除时必须停掉并稍后重开自动。
        if was_auto and hide:
            self._stop_auto()
        elif was_auto:
            self._cancel_auto_pending_advance()

        self._remembered[eid] = storage.meta_for_entry(e)
        storage.save_remembered(self._remembered)
        if hide:
            self._entries.pop(self._index)
            if self._index >= len(self._entries):
                self._index = max(0, len(self._entries) - 1)
        self._show_current()

        if was_auto and hide and self._entries:
            self.after(120, self._start_auto)
        elif was_auto and hide and not self._entries:
            self.var_auto.set(False)

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
        init = self._initial_dir_for_dialog()
        d = filedialog.askdirectory(
            title="选择词条文件夹",
            **({"initialdir": init} if init else {}),
        )
        if not d:
            return
        p = Path(d)
        self._persist_last_folder(p)
        entries = load_folder(p)
        self._load_entries(entries, p)
        if not entries:
            self._set_text_widgets(
                "",
                "该文件夹内未解析到词条。\n支持：.pdf / .txt\n格式示例：\n呆気ない | あっけない ④\n[形] 释义…",
            )

    def _pick_file(self) -> None:
        init = self._initial_dir_for_dialog()
        f = filedialog.askopenfilename(
            title="选择 PDF 或 TXT",
            filetypes=[("PDF / 文本", "*.pdf *.txt"), ("全部", "*.*")],
            **({"initialdir": init} if init else {}),
        )
        if not f:
            return
        p = Path(f)
        self._persist_last_file(p)
        entries = load_file(p)
        self._load_entries(entries, p.parent)
        self.lbl_folder.configure(text=str(p))
        if not entries:
            self._set_text_widgets("", "未能从该文件解析到词条。")

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

    def _interval_sec(self) -> float:
        try:
            raw = self.entry_interval.get().strip().replace(",", ".")
            v = float(raw)
            return max(0.5, min(120.0, v))
        except (ValueError, tk.TclError, AttributeError):
            pass
        try:
            v = float(self._settings.get("auto_interval_sec", 2.0))
            return max(0.5, min(120.0, v))
        except (TypeError, ValueError):
            return 2.0

    def _current_voice(self) -> str:
        if self._settings_win is not None:
            try:
                if self._settings_win.winfo_exists():
                    return self._settings_win.combo_voice.get() or DEFAULT_VOICE
            except (tk.TclError, AttributeError):
                pass
        return str(self._settings.get("tts_voice", DEFAULT_VOICE) or DEFAULT_VOICE)

    def _play_tts(self) -> None:
        if not self._entries:
            return
        e = self._entries[self._index]
        text = reading_for_tts(e.reading)
        if not text:
            return
        voice = self._current_voice()

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

    def _cancel_auto_pending_advance(self) -> None:
        """取消尚未执行的自动「下一条」after 回调，并唤醒自动线程上的 wait。"""
        aid = self._auto_after_advance_id
        if aid is not None:
            try:
                self.after_cancel(aid)
            except Exception:
                pass
            self._auto_after_advance_id = None
        self._auto_nav_event.set()

    def _auto_main_thread_advance(self) -> None:
        """仅由自动播放后台线程通过 after 调度：前进一条并通知后台可继续。"""
        self._auto_after_advance_id = None
        try:
            if self._auto_stop.is_set() or not self.var_auto.get():
                return
            if not self._entries:
                return
            self._index = (self._index + 1) % len(self._entries)
            self._show_current()
        finally:
            self._auto_nav_event.set()

    def _stop_auto(self) -> None:
        self._auto_stop.set()
        self._cancel_auto_pending_advance()
        if self._auto_thread and self._auto_thread.is_alive():
            self._auto_thread.join(timeout=2.0)
        self._auto_stop.clear()
        self._auto_thread = None

    def _toggle_auto(self) -> None:
        if self.var_auto.get():
            self._start_auto()
        else:
            self._stop_auto()
        self._schedule_save_settings()

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
                voice = self._current_voice()
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
                # 须等主线程完成本次「下一条」后再进入下一轮；原 after(0,_next)+短 sleep 会堆积多次 _next 导致连跳
                self._auto_nav_event.clear()
                self._auto_after_advance_id = self.after(0, self._auto_main_thread_advance)
                self._auto_nav_event.wait(timeout=120.0)

        self._auto_thread = threading.Thread(target=loop, daemon=True)
        self._auto_thread.start()

    def _on_close(self) -> None:
        self._stop_auto()
        if self._settings_win is not None:
            try:
                if self._settings_win.winfo_exists():
                    self._flush_settings_from_settings_ui()
            except Exception:
                pass
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

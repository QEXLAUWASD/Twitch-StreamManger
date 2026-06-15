"""Tkinter GUI for Twitch Stream Auto-Title."""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable, Sequence

import psutil
import requests

from app_state import (
    APP_VERSION,
    GITHUB_REPO,
    I18N,
    LANGUAGE_LABEL_TO_CODE,
    PROCESS_LIST_REFRESH_INTERVAL_MS,
    UI_REFRESH_INTERVAL_MS,
    AppState,
)
from config_store import (
    add_custom_game,
    apply_config_to_state,
    load_config,
    load_excluded_processes,
    save_config,
    save_excluded_processes,
)
from process_monitor import get_current_game, is_excluded_process
from twitch_client import TwitchClient, format_title

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "SystemButtonFace",
        "fg": "SystemWindowText",
        "entry_bg": "SystemWindow",
        "entry_fg": "SystemWindowText",
        "listbox_bg": "SystemWindow",
        "listbox_fg": "SystemWindowText",
        "button_bg": "SystemButtonFace",
        "button_fg": "SystemButtonText",
        "button_active_bg": "SystemHighlight",
        "button_active_fg": "SystemHighlightText",
        "select_bg": "SystemHighlight",
        "select_fg": "SystemHighlightText",
        "check_select": "SystemWindow",
        "highlight_bg": "SystemButtonFace",
        "highlight_color": "SystemHighlight",
        "frame_border": "SystemButtonFace",
        "scrollbar_bg": "SystemScrollbar",
        "scrollbar_trough": "SystemButtonFace",
    },
    "dark": {
        "bg": "#1e1e1e",
        "fg": "#d4d4d4",
        "entry_bg": "#2d2d2d",
        "entry_fg": "#d4d4d4",
        "listbox_bg": "#2d2d2d",
        "listbox_fg": "#d4d4d4",
        "button_bg": "#3c3c3c",
        "button_fg": "#d4d4d4",
        "button_active_bg": "#505050",
        "button_active_fg": "#ffffff",
        "select_bg": "#264f78",
        "select_fg": "#ffffff",
        "check_select": "#2d2d2d",
        "highlight_bg": "#1e1e1e",
        "highlight_color": "#264f78",
        "frame_border": "#3c3c3c",
        "scrollbar_bg": "#4a4a4a",
        "scrollbar_trough": "#1e1e1e",
    },
}

# Widget-type → (common_options, extra_options_mapping, extra_kwargs)
# extra_kwargs are applied directly (not looked up in theme dict)
_WIDGET_THEME_OPTIONS: dict[type, tuple[Sequence[str], dict[str, str], dict[str, Any]]] = {
    tk.OptionMenu: (
        ("bg", "fg"),
        {"activebackground": "select_bg", "activeforeground": "select_fg"},
        {"highlightthickness": 0},
    ),
    tk.Checkbutton: (
        ("bg", "fg"),
        {"activebackground": "bg", "activeforeground": "fg", "selectcolor": "check_select"},
        {"highlightthickness": 0},
    ),
    tk.Button: (
        ("bg", "fg"),
        {"activebackground": "button_active_bg", "activeforeground": "button_active_fg"},
        {"highlightthickness": 0, "relief": "flat", "borderwidth": 1},
    ),
    tk.Entry: (
        ("bg", "fg"),
        {
            "insertbackground": "fg",
            "highlightbackground": "highlight_bg",
            "highlightcolor": "highlight_color",
            "selectbackground": "select_bg",
            "selectforeground": "select_fg",
        },
        {"highlightthickness": 1, "relief": "flat"},
    ),
    tk.Listbox: (
        ("bg", "fg", "selectbackground", "selectforeground"),
        {"highlightbackground": "entry_bg", "highlightcolor": "select_bg"},
        {"highlightthickness": 1, "relief": "flat"},
    ),
    tk.Label: (
        ("bg", "fg"),
        {},
        {},
    ),
    tk.Frame: (
        ("bg",),
        {"highlightbackground": "bg"},
        {"highlightthickness": 0},
    ),
    tk.LabelFrame: (
        ("bg", "fg"),
        {"highlightbackground": "frame_border"},
        {"highlightthickness": 1},
    ),
    tk.Toplevel: (
        ("bg",),
        {"highlightbackground": "bg"},
        {"highlightthickness": 0},
    ),
    tk.Scrollbar: (
        ("bg", "troughcolor", "activebackground"),
        {},
        {"highlightthickness": 0, "relief": "flat"},
    ),
    tk.Menu: (
        ("bg", "fg"),
        {
            "activebackground": "select_bg",
            "activeforeground": "select_fg",
            "selectcolor": "select_bg",
        },
        {"tearoff": 0, "relief": "flat", "borderwidth": 1},
    ),
}


def _theme_options(widget: tk.Widget, t: dict[str, str]) -> dict[str, Any]:
    """Build ``{option: value}`` dict for *widget* based on THEMES dict.

    Only sets options whose theme values are non-empty to avoid
    Tkinter falling back to system-default white.
    """
    info = _WIDGET_THEME_OPTIONS.get(type(widget))
    if info is None:
        return {}
    common_keys, extra_map, hardcoded = info
    opts: dict[str, Any] = dict(hardcoded)
    for key in common_keys:
        if key not in opts:
            val = t.get(key, "")
            if val:
                opts[key] = val
    for tk_option, theme_key in extra_map.items():
        val = t.get(theme_key, "")
        if val:
            opts[tk_option] = val
    # Special: Scrollbar trough / active colors
    if isinstance(widget, tk.Scrollbar):
        opts.setdefault("troughcolor", t.get("scrollbar_trough", _darken(t.get("bg", "#1e1e1e"), 0.7)))
        opts.setdefault("activebackground", t.get("scrollbar_bg", _darken(t.get("button_bg", "#3c3c3c"), 1.3)))
    return opts


def _darken(hex_color: str, factor: float) -> str:
    """Darken a hex color by *factor* (0–1).  Returns a new hex string."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, int(c * factor)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _list_running_process_names(state: AppState) -> list[str]:
    """Return a sorted list of non-excluded process names."""
    names: set[str] = set()
    for proc in psutil.process_iter(["name"]):
        try:
            name: str = proc.info["name"] or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if name and not is_excluded_process(name, state):
            names.add(name)
    return sorted(names, key=str.lower)


# ---------------------------------------------------------------------------
# Main Application GUI
# ---------------------------------------------------------------------------


class AppGUI:
    """Primary Tkinter window for the Twitch Auto-Title application."""

    def __init__(
        self,
        root: tk.Tk,
        base_dir: str,
        state: AppState,
        twitch_client: TwitchClient,
        on_close_callback: Callable[[], None],
    ) -> None:
        self.root = root
        self.base_dir = base_dir
        self.state = state
        self.twitch_client = twitch_client
        self.on_close_callback = on_close_callback

        self._exclusion_window: tk.Toplevel | None = None

        root.title(I18N[self.state.language]["app_title"])
        root.geometry("1280x720")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_ui()
        self.refresh_mappings()
        self.refresh_process_list()
        self.apply_theme()

        # Periodic tasks
        self.root.after(PROCESS_LIST_REFRESH_INTERVAL_MS, self._periodic_process_refresh)
        self.root.after(UI_REFRESH_INTERVAL_MS, self._update_loop)
        self.root.after(3000, self._start_update_check)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """One-shot construction of all widgets."""
        tr = I18N[self.state.language]

        # -- Top bar: language + dark mode --
        lang_frame = tk.Frame(self.root)
        lang_frame.pack(anchor="e", padx=10, pady=(8, 0))
        self.lang_label = tk.Label(lang_frame, text=tr["language"], font=("Segoe UI", 9, "bold"))
        self.lang_label.pack(side="left", padx=(0, 6))
        self.lang_var = tk.StringVar(value="English" if self.state.language == "en" else "中文")
        self.lang_menu = tk.OptionMenu(
            lang_frame, self.lang_var, *LANGUAGE_LABEL_TO_CODE.keys(), command=self.change_language
        )
        self.lang_menu.pack(side="left")
        self.dark_mode_var = tk.BooleanVar(value=self.state.dark_mode)
        self.dark_mode_check = tk.Checkbutton(
            lang_frame,
            text=tr["dark_mode"],
            variable=self.dark_mode_var,
            command=self.toggle_dark_mode,
        )
        self.dark_mode_check.pack(side="left", padx=(10, 0))

        # -- Current detected game --
        self.current_detected_label = tk.Label(
            self.root, text=tr["current_detected_game"], font=("Segoe UI", 10, "bold")
        )
        self.current_detected_label.pack(anchor="w", padx=10, pady=(10, 0))
        self.current_label = tk.Label(self.root, text=self.state.current_game, font=("Segoe UI", 12))
        self.current_label.pack(anchor="w", padx=10)

        # -- Configured mappings list --
        self.configured_mappings_label = tk.Label(
            self.root, text=tr["configured_mappings"], font=("Segoe UI", 10, "bold")
        )
        self.configured_mappings_label.pack(anchor="w", padx=10, pady=(10, 0))
        self.listbox = tk.Listbox(self.root, height=8, width=72)
        self.listbox.pack(padx=10, pady=(0, 6))

        # -- Action buttons --
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10)
        self.reload_btn = tk.Button(btn_frame, text=tr["reload_config"], command=self.reload_config)
        self.reload_btn.pack(side="left")
        self.remove_btn = tk.Button(btn_frame, text=tr["remove_selected"], command=self.remove_selected)
        self.remove_btn.pack(side="left", padx=6)
        self.edit_exclusions_btn = tk.Button(
            btn_frame, text=tr["edit_exclusions"], command=self.open_exclusions_editor
        )
        self.edit_exclusions_btn.pack(side="left", padx=6)

        # -- Add/Update form --
        frm = tk.Frame(self.root)
        frm.pack(fill="x", padx=10, pady=(10, 0))
        self.game_name_label = tk.Label(frm, text=tr["game_name"])
        self.game_name_label.grid(row=0, column=0, sticky="e")
        self.process_select_label = tk.Label(frm, text=tr["process_select"])
        self.process_select_label.grid(row=1, column=0, sticky="ne")
        self.twitch_category_label = tk.Label(frm, text=tr["twitch_category"])
        self.twitch_category_label.grid(row=2, column=0, sticky="e")

        self.entry_game = tk.Entry(frm, width=40)
        self.proc_listbox = tk.Listbox(frm, height=6, width=40, exportselection=False)
        self.entry_cat = tk.Entry(frm, width=40)
        self.entry_game.grid(row=0, column=1, padx=6, pady=2)
        self.proc_listbox.grid(row=1, column=1, padx=6, pady=2)
        self.entry_cat.grid(row=2, column=1, padx=6, pady=2)

        proc_btn_frame = tk.Frame(frm)
        proc_btn_frame.grid(row=1, column=2, padx=(4, 0), sticky="n")
        self.proc_refresh_btn = tk.Button(proc_btn_frame, text=tr["refresh"], command=self.refresh_process_list)
        self.proc_refresh_btn.pack(pady=(0, 2))
        self.proc_auto_btn = tk.Button(proc_btn_frame, text=tr["auto_select_match"], command=self.auto_select_process)
        self.proc_auto_btn.pack()

        # -- Custom suffix --
        self.custom_text_label = tk.Label(
            self.root, text=tr["custom_text_hint"], font=("Segoe UI", 10, "bold")
        )
        self.custom_text_label.pack(anchor="w", padx=10, pady=(10, 0))
        self.custom_text_entry = tk.Entry(self.root, width=80)
        self.custom_text_entry.pack(padx=10, pady=(0, 10))

        # -- Keep-last checkbox --
        self.keep_last_var = tk.BooleanVar(value=self.state.keep_last_when_no_game)
        self.keep_last_checkbox = tk.Checkbutton(
            self.root,
            text=tr["keep_last_when_none"],
            variable=self.keep_last_var,
            onvalue=True,
            offvalue=False,
            command=self._save_ui_settings,
        )
        self.keep_last_checkbox.pack(anchor="w", padx=10, pady=(0, 10))

        # -- Bottom buttons --
        self.add_update_btn = tk.Button(self.root, text=tr["add_update"], command=self.add_mapping)
        self.add_update_btn.pack(pady=8)
        self.manual_update_btn = tk.Button(self.root, text=tr["manual_update"], command=self.manual_update)
        self.manual_update_btn.pack(pady=4)
        self.status_label = tk.Label(self.root, text="", fg="green")
        self.status_label.pack()

    # ------------------------------------------------------------------
    # Language & theme
    # ------------------------------------------------------------------

    def change_language(self, language_label: str) -> None:
        code = LANGUAGE_LABEL_TO_CODE.get(language_label, "en")
        if code not in I18N:
            code = "en"
        self.state.language = code
        self._apply_language_texts()
        save_config(self.base_dir, self.state)

    def _apply_language_texts(self) -> None:
        tr = I18N.get(self.state.language, I18N["en"])
        self.root.title(tr["app_title"])
        widgets: list[tuple[tk.Widget, str]] = [
            (self.lang_label, "language"),
            (self.current_detected_label, "current_detected_game"),
            (self.configured_mappings_label, "configured_mappings"),
            (self.reload_btn, "reload_config"),
            (self.remove_btn, "remove_selected"),
            (self.edit_exclusions_btn, "edit_exclusions"),
            (self.game_name_label, "game_name"),
            (self.process_select_label, "process_select"),
            (self.twitch_category_label, "twitch_category"),
            (self.proc_refresh_btn, "refresh"),
            (self.proc_auto_btn, "auto_select_match"),
            (self.custom_text_label, "custom_text_hint"),
            (self.keep_last_checkbox, "keep_last_when_none"),
            (self.add_update_btn, "add_update"),
            (self.manual_update_btn, "manual_update"),
            (self.dark_mode_check, "dark_mode"),
        ]
        for widget, key in widgets:
            widget.config(text=tr.get(key, key))

    def toggle_dark_mode(self) -> None:
        self.state.dark_mode = bool(self.dark_mode_var.get())
        self.apply_theme()
        save_config(self.base_dir, self.state)

    def apply_theme(self) -> None:
        """Apply current theme to root window and all open Toplevels."""
        theme = THEMES["dark" if self.state.dark_mode else "light"]
        self.root.config(bg=theme["bg"])
        # Root + all descendant widgets inside it
        self._apply_theme_to_widget(self.root, theme)
        # Toplevel windows are NOT children of root — theme them separately
        for child in self.root.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.config(bg=theme["bg"])
                self._apply_theme_to_widget(child, theme)

    def _apply_theme_to_widget(self, parent: tk.Widget, t: dict[str, str]) -> None:
        """Apply theme to *parent* and all descendants (iterative DFS).

        Also handles tk.Menu children (OptionMenu dropdowns) explicitly,
        since menus are not returned by ``winfo_children()``.
        """
        stack: list[tk.Widget] = [parent]
        while stack:
            widget = stack.pop()
            stack.extend(widget.winfo_children())

            # Theme the widget itself
            self._config_widget(widget, t)

            # Theme OptionMenu's associated dropdown menu
            if isinstance(widget, tk.OptionMenu):
                menu = widget["menu"]
                if menu:
                    self._config_widget(menu, t)

    @staticmethod
    def _config_widget(widget: tk.Widget, t: dict[str, str]) -> None:
        """Safely apply theme options to a single widget."""
        try:
            opts = _theme_options(widget, t)
            if opts:
                widget.config(**opts)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Mappings list
    # ------------------------------------------------------------------

    def refresh_mappings(self) -> None:
        self.listbox.delete(0, tk.END)
        for game, proc in sorted(self.state.process_names.items()):
            cat = self.state.twitch_categories.get(game, "")
            self.listbox.insert(tk.END, f"{game} -> {proc}   [Category: {cat}]")

    def add_mapping(self) -> None:
        game = self.entry_game.get().strip()
        sel = self.proc_listbox.curselection()
        if not game:
            messagebox.showwarning("Missing", "Please provide a Game Name.")
            return
        if not sel:
            messagebox.showwarning("Missing", "Please select a Process from the list.")
            return
        proc = self.proc_listbox.get(sel[0]).strip()
        cat = self.entry_cat.get().strip()
        ok = add_custom_game(self.base_dir, self.state, game, proc, cat if cat else None)
        if ok:
            self.entry_game.delete(0, tk.END)
            self.entry_cat.delete(0, tk.END)
            self.refresh_mappings()
            self.status_label.config(text=f"Added/Updated: {game} -> {proc}", fg="green")
        else:
            self.status_label.config(text="Failed to add mapping", fg="red")

    def remove_selected(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose a mapping to remove.")
            return
        item = self.listbox.get(sel[0])
        game = item.split("->")[0].strip()
        if not messagebox.askyesno("Confirm", f"Remove mapping for '{game}'?"):
            return
        try:
            cfg = dict(self.state.app_config)
            for section in ("process_name", "TwitchCategoryName"):
                if section in cfg and game in cfg[section]:
                    del cfg[section][game]
            self.state.app_config = cfg
            self.state.process_names = cfg.get("process_name", {})
            self.state.twitch_categories = cfg.get("TwitchCategoryName", {})
            save_config(self.base_dir, self.state)
            self.refresh_mappings()
            messagebox.showinfo("Removed", f"Removed mapping for '{game}'.")
        except Exception:
            logger.exception("remove_selected failed")
            messagebox.showerror("Error", "Failed to remove mapping.")

    def reload_config(self) -> None:
        cfg = load_config(self.base_dir)
        apply_config_to_state(self.state, cfg)
        self.refresh_mappings()
        messagebox.showinfo("Reloaded", "config.json reloaded.")

    # ------------------------------------------------------------------
    # Process list (add/update panel)
    # ------------------------------------------------------------------

    def refresh_process_list(self) -> None:
        try:
            procs = _list_running_process_names(self.state)
            self.proc_listbox.delete(0, tk.END)
            for proc in procs:
                self.proc_listbox.insert(tk.END, proc)
        except Exception:
            logger.exception("refresh_process_list failed")

    def _periodic_process_refresh(self) -> None:
        self.refresh_process_list()
        self.root.after(PROCESS_LIST_REFRESH_INTERVAL_MS, self._periodic_process_refresh)

    def auto_select_process(self) -> None:
        """Auto-select the first process that matches a configured mapping."""
        configured = {v.lower() for v in self.state.process_names.values()}
        for i in range(self.proc_listbox.size()):
            item = self.proc_listbox.get(i).lower()
            if any(cfg in item or item in cfg for cfg in configured):
                self.proc_listbox.selection_clear(0, tk.END)
                self.proc_listbox.selection_set(i)
                self.proc_listbox.see(i)
                messagebox.showinfo("Auto-select", f"Selected: {self.proc_listbox.get(i)}")
                return
        messagebox.showinfo("Auto-select", "No likely match found.")

    # ------------------------------------------------------------------
    # Manual update
    # ------------------------------------------------------------------

    def manual_update(self) -> None:
        detected = get_current_game(self.state)
        if detected is None and self.keep_last_var.get():
            self.status_label.config(text="No game detected; kept last title.", fg="blue")
            return
        current = detected if detected is not None else "Just Chatting"
        custom = (self.custom_text_entry.get() or "").strip()
        new_title = format_title(self.state.base_template, current)
        if custom:
            new_title = f"{new_title} {custom}"
        self.twitch_client.update_stream_title(new_title)
        category = self.state.twitch_categories.get(current, "Just Chatting")
        self.twitch_client.update_stream_category(category)
        self.status_label.config(text=f"Manual update sent: {new_title}", fg="blue")

    # ------------------------------------------------------------------
    # Update checker
    # ------------------------------------------------------------------

    def _start_update_check(self) -> None:
        threading.Thread(target=self._check_for_update, daemon=True).start()

    def _check_for_update(self) -> None:
        tr = I18N.get(self.state.language, I18N["en"])
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                timeout=8,
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            tag = resp.json().get("tag_name", "")
            latest = self._parse_version(tag)
            current = self._parse_version(APP_VERSION)
            if latest > current:
                latest_str = ".".join(str(x) for x in latest)
                msg = tr["update_available_msg"].format(latest=latest_str, current=APP_VERSION)
                self.root.after(0, lambda: messagebox.showinfo(tr["update_available"], msg))
        except Exception:
            logger.debug("Update check failed", exc_info=True)

    @staticmethod
    def _parse_version(tag: str) -> tuple[int, ...]:
        m = re.search(r"(\d+\.\d+\.\d+)", tag)
        if m:
            return tuple(int(x) for x in m.group(1).split("."))
        return (0, 0, 0)

    # ------------------------------------------------------------------
    # Periodic UI refresh
    # ------------------------------------------------------------------

    def _update_loop(self) -> None:
        self.state.custom_suffix = (self.custom_text_entry.get() or "").strip()
        self.state.keep_last_when_no_game = bool(self.keep_last_var.get())
        self.current_label.config(text=self.state.current_game)
        self.root.after(UI_REFRESH_INTERVAL_MS, self._update_loop)

    def _save_ui_settings(self) -> None:
        self.state.keep_last_when_no_game = bool(self.keep_last_var.get())
        save_config(self.base_dir, self.state)

    # ------------------------------------------------------------------
    # Exclusions editor
    # ------------------------------------------------------------------

    def open_exclusions_editor(self) -> None:
        tr = I18N.get(self.state.language, I18N["en"])
        win = tk.Toplevel(self.root)
        win.title(tr["excluded_window"])
        win.geometry("960x420")
        win.transient(self.root)
        self._exclusion_window = win

        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        # --- Left: excluded names ---
        left = tk.Frame(frame)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        tk.Label(left, text=tr["excluded_names"]).pack(anchor="w")
        self.exc_names_lb = tk.Listbox(left, height=14, width=36, exportselection=False, selectmode=tk.EXTENDED)
        self.exc_names_lb.pack(fill="both", expand=True, padx=2, pady=4)
        en_frame = tk.Frame(left)
        en_frame.pack(fill="x")
        self.exc_name_entry = tk.Entry(en_frame)
        self.exc_name_entry.pack(side="left", fill="x", expand=True)
        tk.Button(en_frame, text=tr["add"], command=self._add_excluded_name).pack(side="left", padx=6)
        tk.Button(left, text=tr["remove_selected"], command=self._remove_selected_excluded_name).pack(pady=(6, 0))

        # --- Middle: running processes ---
        middle = tk.Frame(frame)
        middle.pack(side="left", fill="both", expand=True, padx=(6, 6))
        tk.Label(middle, text=tr["running_processes"]).pack(anchor="w")
        self.running_procs_lb = tk.Listbox(middle, height=14, width=36, exportselection=False, selectmode=tk.EXTENDED)
        self.running_procs_lb.pack(fill="both", expand=True, padx=2, pady=4)
        rp_btns = tk.Frame(middle)
        rp_btns.pack(fill="x")
        tk.Button(rp_btns, text=tr["refresh"], command=self._refresh_running_procs).pack(side="left")
        tk.Button(rp_btns, text=tr["add_to_names"], command=self._add_selected_to_names).pack(side="left", padx=6)
        tk.Button(rp_btns, text=tr["add_to_prefixes"], command=self._add_selected_to_prefixes).pack(side="left", padx=6)

        # --- Right: excluded prefixes ---
        right = tk.Frame(frame)
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))
        tk.Label(right, text=tr["excluded_prefixes"]).pack(anchor="w")
        self.exc_prefix_lb = tk.Listbox(right, height=14, width=36, exportselection=False, selectmode=tk.EXTENDED)
        self.exc_prefix_lb.pack(fill="both", expand=True, padx=2, pady=4)
        pre_frame = tk.Frame(right)
        pre_frame.pack(fill="x")
        self.exc_prefix_entry = tk.Entry(pre_frame)
        self.exc_prefix_entry.pack(side="left", fill="x", expand=True)
        tk.Button(pre_frame, text=tr["add"], command=self._add_excluded_prefix).pack(side="left", padx=6)
        tk.Button(right, text=tr["remove_selected"], command=self._remove_selected_excluded_prefix).pack(pady=(6, 0))

        # --- Bottom bar ---
        btns = tk.Frame(win)
        btns.pack(fill="x", pady=(6, 8), padx=8)
        tk.Button(btns, text=tr["save"], command=self._save_exclusions_and_close).pack(side="right", padx=6)
        tk.Button(btns, text=tr["close"], command=win.destroy).pack(side="right")

        self._refresh_exclusions_lists()
        self._refresh_running_procs()
        self.apply_theme()

    # --- Exclusion helpers ---

    def _refresh_running_procs(self) -> None:
        try:
            procs = _list_running_process_names(self.state)
            self.running_procs_lb.delete(0, tk.END)
            for proc in procs:
                self.running_procs_lb.insert(tk.END, proc)
        except Exception:
            logger.exception("_refresh_running_procs failed")

    def _refresh_exclusions_lists(self) -> None:
        self.exc_names_lb.delete(0, tk.END)
        for name in sorted(self.state.excluded_names):
            self.exc_names_lb.insert(tk.END, name)
        self.exc_prefix_lb.delete(0, tk.END)
        for p in self.state.excluded_prefixes:
            self.exc_prefix_lb.insert(tk.END, p)

    def _add_excluded_name(self) -> None:
        val = (self.exc_name_entry.get() or "").strip()
        if not val:
            messagebox.showwarning("Missing", "Enter a process name to exclude.")
            return
        self.state.excluded_names.add(val.lower())
        self.exc_name_entry.delete(0, tk.END)
        self._refresh_exclusions_lists()

    def _remove_selected_excluded_name(self) -> None:
        self._remove_selected_from_listbox(self.exc_names_lb, self.state.excluded_names)

    def _add_excluded_prefix(self) -> None:
        val = (self.exc_prefix_entry.get() or "").strip()
        if not val:
            messagebox.showwarning("Missing", "Enter a prefix to exclude.")
            return
        p = val.lower()
        if p not in self.state.excluded_prefixes:
            self.state.excluded_prefixes.append(p)
        self.exc_prefix_entry.delete(0, tk.END)
        self._refresh_exclusions_lists()

    def _remove_selected_excluded_prefix(self) -> None:
        sel = self.exc_prefix_lb.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose one or more prefixes to remove.")
            return
        for i in reversed(sel):
            p = self.exc_prefix_lb.get(i)
            try:
                self.state.excluded_prefixes.remove(p)
            except ValueError:
                pass
        self._refresh_exclusions_lists()

    @staticmethod
    def _remove_selected_from_listbox(lb: tk.Listbox, store: set[str]) -> None:
        sel = lb.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose one or more items to remove.")
            return
        for i in reversed(sel):
            store.discard(lb.get(i).lower())

    def _save_exclusions_and_close(self) -> None:
        try:
            save_excluded_processes(self.base_dir, self.state)
            load_excluded_processes(self.base_dir, self.state)
            logger.info("Saved exclusions: %d names, %d prefixes",
                        len(self.state.excluded_names), len(self.state.excluded_prefixes))
            messagebox.showinfo("Saved", "excluded_processes.json updated.")
        except Exception:
            logger.exception("save_exclusions_and_close failed")
            messagebox.showerror("Error", "Failed to save excluded_processes.json.")
        try:
            self.refresh_process_list()
        except Exception:
            pass
        if self._exclusion_window is not None:
            self._exclusion_window.destroy()
            self._exclusion_window = None

    def _add_selected_to_names(self) -> None:
        added = self._collect_selected_running()
        for name in added:
            self.state.excluded_names.add(name.lower())
        self._refresh_exclusions_lists()
        self._refresh_running_procs()
        messagebox.showinfo("Added", f"Added to excluded names:\n{', '.join(added)}" if added else "No valid names were added.")

    def _add_selected_to_prefixes(self) -> None:
        added: list[str] = []
        for name in self._collect_selected_running():
            prefix = name.split(".", 1)[0].lower()
            if prefix and prefix not in self.state.excluded_prefixes:
                self.state.excluded_prefixes.append(prefix)
                added.append(prefix)
        self._refresh_exclusions_lists()
        self._refresh_running_procs()
        messagebox.showinfo("Added", f"Added prefixes:\n{', '.join(added)}" if added else "No new prefixes were added.")

    def _collect_selected_running(self) -> list[str]:
        sel = self.running_procs_lb.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose one or more running processes.")
            return []
        return [self.running_procs_lb.get(i).strip() for i in sel]

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def on_close(self) -> None:
        try:
            self.on_close_callback()
        except Exception:
            logger.debug("on_close_callback raised (ignored)", exc_info=True)
        self.root.destroy()

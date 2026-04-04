import os
import re
import threading
import tkinter as tk
from tkinter import messagebox

import psutil
import requests

from app_state import APP_VERSION, GITHUB_REPO, I18N, LANGUAGE_LABEL_TO_CODE, AppState
from config_store import add_custom_game, apply_config_to_state, load_config, load_excluded_processes, save_config, save_excluded_processes
from process_monitor import get_current_game, is_excluded_process
from twitch_client import TwitchClient, format_title


THEMES = {
    "light": {
        "bg": "SystemButtonFace",
        "fg": "SystemWindowText",
        "entry_bg": "SystemWindow",
        "entry_fg": "SystemWindowText",
        "listbox_bg": "SystemWindow",
        "listbox_fg": "SystemWindowText",
        "button_bg": "SystemButtonFace",
        "button_fg": "SystemButtonText",
        "select_bg": "SystemHighlight",
        "select_fg": "SystemHighlightText",
        "check_select": "SystemWindow",
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
        "select_bg": "#264f78",
        "select_fg": "#d4d4d4",
        "check_select": "#2d2d2d",
    },
}


class AppGUI:
    def __init__(self, root: tk.Tk, base_dir: str, state: AppState, twitch_client: TwitchClient, on_close_callback):
        self.root = root
        self.base_dir = base_dir
        self.state = state
        self.twitch_client = twitch_client
        self.on_close_callback = on_close_callback

        root.title(I18N[self.state.language]["app_title"])
        root.geometry("1280x720")
        root.resizable(False, False)

        lang_frame = tk.Frame(root)
        lang_frame.pack(anchor="e", padx=10, pady=(8, 0))
        self.lang_label = tk.Label(lang_frame, text=I18N[self.state.language]["language"], font=("Segoe UI", 9, "bold"))
        self.lang_label.pack(side="left", padx=(0, 6))
        self.lang_var = tk.StringVar(value="English" if self.state.language == "en" else "中文")
        self.lang_menu = tk.OptionMenu(lang_frame, self.lang_var, *LANGUAGE_LABEL_TO_CODE.keys(), command=self.change_language)
        self.lang_menu.pack(side="left")
        self.dark_mode_var = tk.BooleanVar(value=self.state.dark_mode)
        self.dark_mode_check = tk.Checkbutton(
            lang_frame,
            text=I18N[self.state.language]["dark_mode"],
            variable=self.dark_mode_var,
            command=self.toggle_dark_mode,
        )
        self.dark_mode_check.pack(side="left", padx=(10, 0))

        self.current_detected_label = tk.Label(root, text=I18N[self.state.language]["current_detected_game"], font=("Segoe UI", 10, "bold"))
        self.current_detected_label.pack(anchor="w", padx=10, pady=(10, 0))
        self.current_label = tk.Label(root, text=self.state.current_game, font=("Segoe UI", 12))
        self.current_label.pack(anchor="w", padx=10)

        self.configured_mappings_label = tk.Label(root, text=I18N[self.state.language]["configured_mappings"], font=("Segoe UI", 10, "bold"))
        self.configured_mappings_label.pack(anchor="w", padx=10, pady=(10, 0))
        self.listbox = tk.Listbox(root, height=8, width=72)
        self.listbox.pack(padx=10, pady=(0, 6))

        btn_frame = tk.Frame(root)
        btn_frame.pack(fill="x", padx=10)
        self.reload_btn = tk.Button(btn_frame, text=I18N[self.state.language]["reload_config"], command=self.reload_config)
        self.reload_btn.pack(side="left")
        self.remove_btn = tk.Button(btn_frame, text=I18N[self.state.language]["remove_selected"], command=self.remove_selected)
        self.remove_btn.pack(side="left", padx=6)
        self.edit_exclusions_btn = tk.Button(
            btn_frame,
            text=I18N[self.state.language]["edit_exclusions"],
            command=self.open_exclusions_editor,
        )
        self.edit_exclusions_btn.pack(side="left", padx=6)

        frm = tk.Frame(root)
        frm.pack(fill="x", padx=10, pady=(10, 0))
        self.game_name_label = tk.Label(frm, text=I18N[self.state.language]["game_name"])
        self.game_name_label.grid(row=0, column=0, sticky="e")
        self.process_select_label = tk.Label(frm, text=I18N[self.state.language]["process_select"])
        self.process_select_label.grid(row=1, column=0, sticky="ne")
        self.twitch_category_label = tk.Label(frm, text=I18N[self.state.language]["twitch_category"])
        self.twitch_category_label.grid(row=2, column=0, sticky="e")

        self.entry_game = tk.Entry(frm, width=40)
        self.proc_listbox = tk.Listbox(frm, height=6, width=40, exportselection=False)
        self.entry_cat = tk.Entry(frm, width=40)
        self.entry_game.grid(row=0, column=1, padx=6, pady=2)
        self.proc_listbox.grid(row=1, column=1, padx=6, pady=2)
        self.entry_cat.grid(row=2, column=1, padx=6, pady=2)

        proc_btn_frame = tk.Frame(frm)
        proc_btn_frame.grid(row=1, column=2, padx=(4, 0), sticky="n")
        self.proc_refresh_btn = tk.Button(proc_btn_frame, text=I18N[self.state.language]["refresh"], command=self.refresh_process_list)
        self.proc_refresh_btn.pack(pady=(0, 2))
        self.proc_auto_btn = tk.Button(proc_btn_frame, text=I18N[self.state.language]["auto_select_match"], command=self.auto_select_process)
        self.proc_auto_btn.pack()

        self.custom_text_label = tk.Label(root, text=I18N[self.state.language]["custom_text_hint"], font=("Segoe UI", 10, "bold"))
        self.custom_text_label.pack(anchor="w", padx=10, pady=(10, 0))
        self.custom_text_entry = tk.Entry(root, width=80)
        self.custom_text_entry.pack(padx=10, pady=(0, 10))

        self.keep_last_var = tk.BooleanVar(value=self.state.keep_last_when_no_game)
        self.keep_last_checkbox = tk.Checkbutton(
            root,
            text=I18N[self.state.language]["keep_last_when_none"],
            variable=self.keep_last_var,
            onvalue=True,
            offvalue=False,
            command=self._save_ui_settings,
        )
        self.keep_last_checkbox.pack(anchor="w", padx=10, pady=(0, 10))

        self.add_update_btn = tk.Button(root, text=I18N[self.state.language]["add_update"], command=self.add_mapping)
        self.add_update_btn.pack(pady=8)
        self.manual_update_btn = tk.Button(root, text=I18N[self.state.language]["manual_update"], command=self.manual_update)
        self.manual_update_btn.pack(pady=4)
        self.status_label = tk.Label(root, text="", fg="green")
        self.status_label.pack()

        self.refresh_mappings()
        self.refresh_process_list()
        self.root.after(60000, self._periodic_process_refresh)
        self._update_loop()
        self.apply_theme()
        self.root.after(3000, self._start_update_check)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def change_language(self, language_label):
        code = LANGUAGE_LABEL_TO_CODE.get(language_label, "en")
        if code not in I18N:
            code = "en"
        self.state.language = code
        self.apply_language()
        save_config(self.base_dir, self.state)

    def apply_language(self):
        tr = I18N.get(self.state.language, I18N["en"])
        self.root.title(tr["app_title"])
        self.lang_label.config(text=tr["language"])
        self.current_detected_label.config(text=tr["current_detected_game"])
        self.configured_mappings_label.config(text=tr["configured_mappings"])
        self.reload_btn.config(text=tr["reload_config"])
        self.remove_btn.config(text=tr["remove_selected"])
        self.edit_exclusions_btn.config(text=tr["edit_exclusions"])
        self.game_name_label.config(text=tr["game_name"])
        self.process_select_label.config(text=tr["process_select"])
        self.twitch_category_label.config(text=tr["twitch_category"])
        self.proc_refresh_btn.config(text=tr["refresh"])
        self.proc_auto_btn.config(text=tr["auto_select_match"])
        self.custom_text_label.config(text=tr["custom_text_hint"])
        self.keep_last_checkbox.config(text=tr["keep_last_when_none"])
        self.add_update_btn.config(text=tr["add_update"])
        self.manual_update_btn.config(text=tr["manual_update"])
        self.dark_mode_check.config(text=tr["dark_mode"])

    def toggle_dark_mode(self):
        self.state.dark_mode = bool(self.dark_mode_var.get())
        self.apply_theme()
        save_config(self.base_dir, self.state)

    def _start_update_check(self):
        threading.Thread(target=self._check_for_update, daemon=True).start()

    def _check_for_update(self):
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
            pass

    @staticmethod
    def _parse_version(tag: str) -> tuple:
        m = re.search(r'(\d+\.\d+\.\d+)', tag)
        if m:
            return tuple(int(x) for x in m.group(1).split("."))
        return (0, 0, 0)

    def apply_theme(self):
        t = THEMES["dark" if self.state.dark_mode else "light"]
        self.root.config(bg=t["bg"])
        for child in self.root.winfo_children():
            self._apply_theme_to_widget(child, t)

    def _apply_theme_to_widget(self, widget, t):
        try:
            if isinstance(widget, tk.OptionMenu):
                widget.config(
                    bg=t["button_bg"], fg=t["button_fg"],
                    activebackground=t["select_bg"], activeforeground=t["select_fg"],
                )
                widget["menu"].config(
                    bg=t["button_bg"], fg=t["button_fg"],
                    activebackground=t["select_bg"], activeforeground=t["select_fg"],
                )
            elif isinstance(widget, tk.Checkbutton):
                widget.config(
                    bg=t["bg"], fg=t["fg"],
                    activebackground=t["bg"], activeforeground=t["fg"],
                    selectcolor=t["check_select"],
                )
            elif isinstance(widget, tk.Button):
                widget.config(
                    bg=t["button_bg"], fg=t["button_fg"],
                    activebackground=t["select_bg"], activeforeground=t["select_fg"],
                )
            elif isinstance(widget, tk.Entry):
                widget.config(
                    bg=t["entry_bg"], fg=t["entry_fg"],
                    insertbackground=t["fg"],
                )
            elif isinstance(widget, tk.Listbox):
                widget.config(
                    bg=t["listbox_bg"], fg=t["listbox_fg"],
                    selectbackground=t["select_bg"], selectforeground=t["select_fg"],
                )
            elif isinstance(widget, tk.Label):
                widget.config(bg=t["bg"], fg=t["fg"])
            elif isinstance(widget, (tk.Frame, tk.LabelFrame)):
                widget.config(bg=t["bg"])
            elif isinstance(widget, tk.Toplevel):
                widget.config(bg=t["bg"])
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._apply_theme_to_widget(child, t)

    def refresh_mappings(self):
        self.listbox.delete(0, tk.END)
        for game, proc in sorted(self.state.process_names.items()):
            cat = self.state.twitch_categories.get(game, "")
            self.listbox.insert(tk.END, f"{game} -> {proc}   [Category: {cat}]")

    def refresh_process_list(self):
        try:
            procs = []
            for p in psutil.process_iter(["name"]):
                try:
                    name = p.info["name"]
                    if not name or is_excluded_process(name, self.state):
                        continue
                    procs.append(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            procs = sorted(set(procs), key=str.lower)
            self.proc_listbox.delete(0, tk.END)
            for proc in procs:
                self.proc_listbox.insert(tk.END, proc)
        except Exception as e:
            print(f"Failed to refresh process list: {e}")

    def _periodic_process_refresh(self):
        self.refresh_process_list()
        self.root.after(60000, self._periodic_process_refresh)

    def auto_select_process(self):
        best_match_index = None
        configured = [v.lower() for v in self.state.process_names.values()]
        for i in range(self.proc_listbox.size()):
            item = self.proc_listbox.get(i)
            for cfg in configured:
                if cfg in item.lower() or item.lower() in cfg:
                    best_match_index = i
                    break
            if best_match_index is not None:
                break
        if best_match_index is not None:
            self.proc_listbox.selection_clear(0, tk.END)
            self.proc_listbox.selection_set(best_match_index)
            self.proc_listbox.see(best_match_index)
            messagebox.showinfo("Auto-select", f"Selected: {self.proc_listbox.get(best_match_index)}")
        else:
            messagebox.showinfo("Auto-select", "No likely match found.")

    def reload_config(self):
        cfg = load_config(self.base_dir)
        apply_config_to_state(self.state, cfg)
        self.refresh_mappings()
        messagebox.showinfo("Reloaded", "config.json reloaded.")

    def add_mapping(self):
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

    def remove_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose a mapping to remove.")
            return
        idx = sel[0]
        item = self.listbox.get(idx)
        game = item.split("->")[0].strip()
        if messagebox.askyesno("Confirm", f"Remove mapping for '{game}'?"):
            try:
                if "process_name" in self.state.app_config and game in self.state.app_config["process_name"]:
                    del self.state.app_config["process_name"][game]
                if "TwitchCategoryName" in self.state.app_config and game in self.state.app_config["TwitchCategoryName"]:
                    del self.state.app_config["TwitchCategoryName"][game]
                save_config(self.base_dir, self.state)
                self.state.process_names = self.state.app_config.get("process_name", {})
                self.state.twitch_categories = self.state.app_config.get("TwitchCategoryName", {})
                self.refresh_mappings()
                messagebox.showinfo("Removed", f"Removed mapping for '{game}'.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to remove: {e}")

    def _update_loop(self):
        self.state.custom_suffix = (self.custom_text_entry.get() or "").strip()
        self.state.keep_last_when_no_game = bool(self.keep_last_var.get())
        self.current_label.config(text=self.state.current_game)
        self.root.after(1000, self._update_loop)

    def _save_ui_settings(self):
        self.state.keep_last_when_no_game = bool(self.keep_last_var.get())
        save_config(self.base_dir, self.state)

    def on_close(self):
        try:
            self.on_close_callback()
        except Exception:
            pass
        self.root.destroy()
        os._exit(0)

    def open_exclusions_editor(self):
        tr = I18N.get(self.state.language, I18N["en"])
        win = tk.Toplevel(self.root)
        win.title(tr["excluded_window"])
        win.geometry("960x420")
        win.transient(self.root)

        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        left = tk.Frame(frame)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        tk.Label(left, text=tr["excluded_names"]).pack(anchor="w")
        self.exc_names_lb = tk.Listbox(left, height=14, width=36, exportselection=False, selectmode=tk.EXTENDED)
        self.exc_names_lb.pack(fill="both", expand=True, padx=2, pady=4)
        en_frame = tk.Frame(left)
        en_frame.pack(fill="x")
        self.exc_name_entry = tk.Entry(en_frame)
        self.exc_name_entry.pack(side="left", fill="x", expand=True)
        tk.Button(en_frame, text=tr["add"], command=self.add_excluded_name).pack(side="left", padx=6)
        tk.Button(left, text=tr["remove_selected"], command=self.remove_selected_excluded_name).pack(pady=(6, 0))

        middle = tk.Frame(frame)
        middle.pack(side="left", fill="both", expand=True, padx=(6, 6))
        tk.Label(middle, text=tr["running_processes"]).pack(anchor="w")
        self.running_procs_lb = tk.Listbox(middle, height=14, width=36, exportselection=False, selectmode=tk.EXTENDED)
        self.running_procs_lb.pack(fill="both", expand=True, padx=2, pady=4)
        rp_btns = tk.Frame(middle)
        rp_btns.pack(fill="x")
        tk.Button(rp_btns, text=tr["refresh"], command=self.refresh_running_processes_list).pack(side="left")
        tk.Button(rp_btns, text=tr["add_to_names"], command=self.add_selected_running_to_excluded_name).pack(side="left", padx=6)
        tk.Button(rp_btns, text=tr["add_to_prefixes"], command=self.add_selected_running_to_excluded_prefix).pack(side="left", padx=6)

        right = tk.Frame(frame)
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))
        tk.Label(right, text=tr["excluded_prefixes"]).pack(anchor="w")
        self.exc_prefix_lb = tk.Listbox(right, height=14, width=36, exportselection=False, selectmode=tk.EXTENDED)
        self.exc_prefix_lb.pack(fill="both", expand=True, padx=2, pady=4)
        pre_frame = tk.Frame(right)
        pre_frame.pack(fill="x")
        self.exc_prefix_entry = tk.Entry(pre_frame)
        self.exc_prefix_entry.pack(side="left", fill="x", expand=True)
        tk.Button(pre_frame, text=tr["add"], command=self.add_excluded_prefix).pack(side="left", padx=6)
        tk.Button(right, text=tr["remove_selected"], command=self.remove_selected_excluded_prefix).pack(pady=(6, 0))

        btns = tk.Frame(win)
        btns.pack(fill="x", pady=(6, 8), padx=8)
        tk.Button(btns, text=tr["save"], command=self.save_exclusions_and_close).pack(side="right", padx=6)
        tk.Button(btns, text=tr["close"], command=win.destroy).pack(side="right")

        self.refresh_exclusions_lists()
        self.refresh_running_processes_list()
        self.apply_theme()

    def refresh_running_processes_list(self):
        try:
            procs = []
            for p in psutil.process_iter(["name"]):
                try:
                    name = p.info["name"]
                    if not name or is_excluded_process(name, self.state):
                        continue
                    procs.append(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            procs = sorted(set(procs), key=str.lower)
            self.running_procs_lb.delete(0, tk.END)
            for proc in procs:
                self.running_procs_lb.insert(tk.END, proc)
        except Exception as e:
            print(f"Failed to refresh running processes list: {e}")

    def refresh_exclusions_lists(self):
        self.exc_names_lb.delete(0, tk.END)
        for name in sorted(self.state.excluded_names):
            self.exc_names_lb.insert(tk.END, name)
        self.exc_prefix_lb.delete(0, tk.END)
        for p in self.state.excluded_prefixes:
            self.exc_prefix_lb.insert(tk.END, p)

    def add_excluded_name(self):
        val = (self.exc_name_entry.get() or "").strip()
        if not val:
            messagebox.showwarning("Missing", "Enter a process name to exclude.")
            return
        self.state.excluded_names.add(val.lower())
        self.exc_name_entry.delete(0, tk.END)
        self.refresh_exclusions_lists()

    def remove_selected_excluded_name(self):
        sel = self.exc_names_lb.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose one or more names to remove.")
            return
        for i in reversed(sel):
            name = self.exc_names_lb.get(i)
            self.state.excluded_names.discard(name.lower())
        self.refresh_exclusions_lists()

    def add_excluded_prefix(self):
        val = (self.exc_prefix_entry.get() or "").strip()
        if not val:
            messagebox.showwarning("Missing", "Enter a prefix to exclude.")
            return
        p = val.lower()
        if p not in self.state.excluded_prefixes:
            self.state.excluded_prefixes.append(p)
        self.exc_prefix_entry.delete(0, tk.END)
        self.refresh_exclusions_lists()

    def remove_selected_excluded_prefix(self):
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
        self.refresh_exclusions_lists()

    def save_exclusions_and_close(self):
        try:
            save_excluded_processes(self.base_dir, self.state)
            load_excluded_processes(self.base_dir, self.state)
            print(f"Saved exclusions: {len(self.state.excluded_names)} names, {len(self.state.excluded_prefixes)} prefixes")
            messagebox.showinfo("Saved", "excluded_processes.json updated.")
        except Exception as e:
            print(f"Failed to save excluded_processes.json: {e}")
            messagebox.showerror("Error", "Failed to save excluded_processes.json.")
        try:
            self.refresh_process_list()
        except Exception:
            pass
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel) and w.title() in ("Edit Excluded Processes", "編輯排除程序"):
                w.destroy()

    def add_selected_running_to_excluded_name(self):
        sel = self.running_procs_lb.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose one or more running processes to add to excluded names.")
            return
        added = []
        for i in sel:
            name = self.running_procs_lb.get(i).strip()
            if not name:
                continue
            self.state.excluded_names.add(name.lower())
            added.append(name)
        self.refresh_exclusions_lists()
        self.refresh_running_processes_list()
        messagebox.showinfo("Added", f"Added to excluded names:\n{', '.join(added)}" if added else "No valid names were added.")

    def add_selected_running_to_excluded_prefix(self):
        sel = self.running_procs_lb.curselection()
        if not sel:
            messagebox.showinfo("Select", "Choose one or more running processes to add as prefix exclusions.")
            return
        added = []
        for i in sel:
            name = self.running_procs_lb.get(i).strip()
            if not name:
                continue
            prefix = name.split(".", 1)[0].lower()
            if prefix not in self.state.excluded_prefixes:
                self.state.excluded_prefixes.append(prefix)
                added.append(prefix)
        self.refresh_exclusions_lists()
        self.refresh_running_processes_list()
        messagebox.showinfo("Added", f"Added prefixes:\n{', '.join(added)}" if added else "No new prefixes were added.")

    def manual_update(self):
        detected_game = get_current_game(self.state)
        if detected_game is None and self.keep_last_var.get():
            self.status_label.config(text="No game detected; kept last title.", fg="blue")
            return
        current_game = detected_game if detected_game is not None else "Just Chatting"
        custom_text = (self.custom_text_entry.get() or "").strip()
        new_title = format_title(self.state.base_template, current_game)
        if custom_text:
            new_title = f"{new_title} {custom_text}"
        self.twitch_client.update_stream_title(new_title)
        category_name = self.state.twitch_categories.get(current_game, "Just Chatting")
        self.twitch_client.update_stream_category(category_name)
        self.status_label.config(text=f"Manual update sent: {new_title}", fg="blue")

import configparser
import json
import os
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog

import requests


def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def ensure_required_files(base_dir: str) -> None:
    config_ini = os.path.join(base_dir, "config.ini")
    config_json = os.path.join(base_dir, "config.json")
    excluded_json = os.path.join(base_dir, "excluded_processes.json")

    if not os.path.exists(config_ini):
        print("config.ini not found. Creating a template...")
        root_tmp = tk.Tk()
        root_tmp.withdraw()
        client_id = simpledialog.askstring("Twitch Credentials", "Enter your Twitch client_id:", parent=root_tmp)
        access_token = simpledialog.askstring(
            "Twitch Credentials",
            "Enter your Twitch access_token:",
            parent=root_tmp,
            show="*",
        )
        streamer_id = simpledialog.askstring("Twitch Credentials", "Enter your Twitch streamer_id (user ID):", parent=root_tmp)
        root_tmp.destroy()

        if not client_id or not access_token or not streamer_id:
            messagebox.showerror("Missing", "Credentials not provided. Exiting.")
            raise SystemExit(0)

        with open(config_ini, "w", encoding="utf-8") as f:
            f.write("[Twitch]\n")
            f.write(f"client_id = {client_id}\n")
            f.write(f"access_token = {access_token}\n")
            f.write(f"streamer_id = {streamer_id}\n")
        messagebox.showinfo("Template Created", "Template config.ini created. Please restart the application.")
        raise SystemExit(0)

    if not os.path.exists(config_json):
        print("config.json not found. Downloading a default template...")
        default_url = "https://raw.githubusercontent.com/QEXLAUWASD/Twitch-StreamManger/refs/heads/main/Default_config.json"
        try:
            response = requests.get(default_url, timeout=10)
            if response.status_code == 200:
                with open(config_json, "w", encoding="utf-8") as f:
                    f.write(response.text)
                print("Default config.json downloaded.")
            else:
                print(f"Failed to download default config.json: {response.status_code}")
                raise SystemExit(1)
        except Exception as e:
            print(f"Error downloading config.json: {e}")
            raise SystemExit(1)

    if not os.path.exists(excluded_json):
        print("excluded_processes.json not found. Creating an empty template...")
        with open(excluded_json, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "exclude_process_names": [
                        "System",
                        "System Idle Process",
                        "svchost.exe",
                        "explorer.exe",
                        "cmd.exe",
                        "python.exe",
                        "pythonw.exe",
                    ],
                    "exclude_prefixes": ["MicrosoftEdge", "Google Chrome", "Brave Browser"],
                },
                f,
                indent=4,
            )


def load_credentials(base_dir: str) -> dict:
    auth_config = configparser.ConfigParser()
    auth_config.read(os.path.join(base_dir, "config.ini"))
    return {
        "client_id": auth_config.get("Twitch", "client_id"),
        "access_token": auth_config.get("Twitch", "access_token"),
        "streamer_id": auth_config.get("Twitch", "streamer_id"),
    }

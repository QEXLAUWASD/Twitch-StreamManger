"""First-run bootstrapping: ensure required files exist, load credentials."""

from __future__ import annotations

import configparser
import json
import logging
import os
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_URL: str = (
    "https://raw.githubusercontent.com/QEXLAUWASD/Twitch-StreamManger"
    "/refs/heads/main/Default_config.json"
)
REQUEST_TIMEOUT: int = 10

DEFAULT_EXCLUSIONS: dict[str, list[str]] = {
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
}


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def get_base_dir() -> str:
    """Return the directory containing the executable (frozen) or this script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# File bootstrapping
# ---------------------------------------------------------------------------

def ensure_required_files(base_dir: str) -> None:
    """Create config.ini / config.json / excluded_processes.json if missing."""
    _ensure_config_ini(base_dir)
    _ensure_config_json(base_dir)
    _ensure_excluded_json(base_dir)


def _ensure_config_ini(base_dir: str) -> None:
    path = os.path.join(base_dir, "config.ini")
    if os.path.exists(path):
        return

    logger.info("config.ini not found – prompting for credentials…")
    root_tmp = tk.Tk()
    root_tmp.withdraw()
    try:
        client_id = simpledialog.askstring(
            "Twitch Credentials", "Enter your Twitch client_id:", parent=root_tmp
        )
        access_token = simpledialog.askstring(
            "Twitch Credentials",
            "Enter your Twitch access_token:",
            parent=root_tmp,
            show="*",
        )
        streamer_id = simpledialog.askstring(
            "Twitch Credentials", "Enter your Twitch streamer_id (user ID):", parent=root_tmp
        )
    finally:
        root_tmp.destroy()

    if not client_id or not access_token or not streamer_id:
        messagebox.showerror("Missing", "Credentials not provided. Exiting.")
        sys.exit(0)

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("[Twitch]\n")
        fh.write(f"client_id = {client_id}\n")
        fh.write(f"access_token = {access_token}\n")
        fh.write(f"streamer_id = {streamer_id}\n")
    messagebox.showinfo(
        "Template Created", "Template config.ini created. Please restart the application."
    )
    sys.exit(0)


def _ensure_config_json(base_dir: str) -> None:
    path = os.path.join(base_dir, "config.json")
    if os.path.exists(path):
        return

    logger.info("config.json not found – downloading default…")
    try:
        resp = requests.get(DEFAULT_CONFIG_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(resp.text)
        logger.info("Default config.json downloaded.")
    except Exception:
        logger.exception("Failed to download default config.json")
        sys.exit(1)


def _ensure_excluded_json(base_dir: str) -> None:
    path = os.path.join(base_dir, "excluded_processes.json")
    if os.path.exists(path):
        return

    logger.info("excluded_processes.json not found – creating default…")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(DEFAULT_EXCLUSIONS, fh, indent=4)


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def load_credentials(base_dir: str) -> dict[str, str]:
    """Read Twitch credentials from config.ini."""
    auth = configparser.ConfigParser()
    auth.read(os.path.join(base_dir, "config.ini"))
    return {
        "client_id": auth.get("Twitch", "client_id"),
        "access_token": auth.get("Twitch", "access_token"),
        "streamer_id": auth.get("Twitch", "streamer_id"),
    }

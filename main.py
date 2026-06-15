"""Twitch Stream Auto-Title – entry point.

Monitors running processes, detects games, and updates a Twitch stream's
title and category automatically.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app_state import AppState
from bootstrap import ensure_required_files, get_base_dir, load_credentials
from config_store import apply_config_to_state, load_config, load_excluded_processes
from process_monitor import monitor_game_and_update_title
from twitch_client import TwitchClient
from ui import AppGUI

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config file hot-reload watcher
# ---------------------------------------------------------------------------


class ConfigFileEventHandler(FileSystemEventHandler):
    """Watchdog handler that reloads config.json on modification."""

    def __init__(self, base_dir: str, state: AppState) -> None:
        super().__init__()
        self._base_dir = base_dir
        self._state = state

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.src_path.endswith("config.json"):
            cfg = load_config(self._base_dir)
            apply_config_to_state(self._state, cfg)
            logger.info("config.json reloaded (%d games)", len(self._state.process_names))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _stop_observer(observer: Observer) -> None:
    """Safely stop a Watchdog observer."""
    try:
        observer.stop()
        observer.join(timeout=1)
    except Exception:
        logger.debug("Observer stop raised (ignored)", exc_info=True)


def main() -> None:
    base_dir = get_base_dir()
    ensure_required_files(base_dir)

    # --- Credentials & API client ---
    creds = load_credentials(base_dir)
    twitch_client = TwitchClient(
        client_id=creds["client_id"],
        access_token=creds["access_token"],
        streamer_id=creds["streamer_id"],
    )

    # --- Application state ---
    state = AppState()
    apply_config_to_state(state, load_config(base_dir))
    load_excluded_processes(base_dir, state)

    logger.info("Twitch Stream Auto-Title Started!")
    logger.info("Monitoring for games: %s", list(state.process_names.keys()))

    # --- File watcher for hot-reload ---
    event_handler = ConfigFileEventHandler(base_dir, state)
    observer = Observer()
    observer.schedule(event_handler, path=base_dir, recursive=False)
    observer.start()

    # --- Background monitor thread ---
    monitor_thread = threading.Thread(
        target=monitor_game_and_update_title,
        args=(state, twitch_client),
        daemon=True,
    )
    monitor_thread.start()

    # --- Tkinter GUI ---
    root = tk.Tk()
    AppGUI(root, base_dir, state, twitch_client, lambda: _stop_observer(observer))

    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt – shutting down…")
    finally:
        _stop_observer(observer)


if __name__ == "__main__":
    main()

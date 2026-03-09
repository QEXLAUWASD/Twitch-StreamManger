import os
import threading

import tkinter as tk
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app_state import AppState
from bootstrap import ensure_required_files, get_base_dir, load_credentials
from config_store import apply_config_to_state, load_config, load_excluded_processes
from process_monitor import monitor_game_and_update_title
from twitch_client import TwitchClient
from ui import AppGUI


class ConfigFileEventHandler(FileSystemEventHandler):
    def __init__(self, base_dir: str, state: AppState):
        self.base_dir = base_dir
        self.state = state

    def on_modified(self, event):
        if event.src_path.endswith("config.json"):
            cfg = load_config(self.base_dir)
            apply_config_to_state(self.state, cfg)
            print("Configuration reloaded.")
            print(f"Now monitoring {len(self.state.process_names)} games")


def main() -> None:
    base_dir = get_base_dir()
    ensure_required_files(base_dir)

    creds = load_credentials(base_dir)
    twitch_client = TwitchClient(
        client_id=creds["client_id"],
        access_token=creds["access_token"],
        streamer_id=creds["streamer_id"],
    )

    state = AppState()
    apply_config_to_state(state, load_config(base_dir))
    load_excluded_processes(base_dir, state)

    print("Twitch Stream Auto-Title Started!")
    print(f"Monitoring for games: {list(state.process_names.keys())}")

    event_handler = ConfigFileEventHandler(base_dir, state)
    observer = Observer()
    observer.schedule(event_handler, path=base_dir, recursive=False)
    observer.start()

    monitor_thread = threading.Thread(target=monitor_game_and_update_title, args=(state, twitch_client), daemon=True)
    monitor_thread.start()

    def stop_observer() -> None:
        try:
            observer.stop()
            observer.join(timeout=1)
        except Exception:
            pass

    root = tk.Tk()
    AppGUI(root, base_dir, state, twitch_client, stop_observer)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Stopping monitor...")
        stop_observer()
        os._exit(0)


if __name__ == "__main__":
    main()

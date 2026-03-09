import time

import psutil

from app_state import AppState
from twitch_client import TwitchClient, format_title


def is_excluded_process(proc_name: str, state: AppState) -> bool:
    if not proc_name:
        return True
    name_l = proc_name.lower()
    if name_l in state.excluded_names:
        return True
    for prefix in state.excluded_prefixes:
        if name_l.startswith(prefix):
            return True
    return False


def get_current_game(state: AppState) -> str | None:
    detected_processes = []

    for proc in psutil.process_iter(["name", "pid"]):
        try:
            process_name = proc.info["name"]
            if is_excluded_process(process_name, state):
                continue
            detected_processes.append(process_name)

            for game, expected_proc in state.process_names.items():
                if (
                    process_name == expected_proc
                    or (process_name and process_name.lower() == expected_proc.lower())
                    or (expected_proc and expected_proc.lower() in process_name.lower())
                ):
                    print(f"FOUND GAME: {game} (Process: {process_name})")
                    return game

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    print(f"Looking for: {list(state.process_names.values())}")
    print("Recent (non-excluded) processes detected:")
    for proc in detected_processes[-10:]:
        print(f"  - {proc}")

    return None


def debug_all_processes(state: AppState) -> None:
    print("\n=== DEBUG: All Running Processes (Full Scan) ===")
    all_processes = []
    excluded_count = 0

    for proc in psutil.process_iter(["name", "pid"]):
        try:
            name = proc.info["name"]
            if is_excluded_process(name, state):
                excluded_count += 1
                continue
            all_processes.append(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    unique_processes = sorted(set(all_processes))
    print(f"Total unique (non-excluded) processes: {len(unique_processes)} - excluded skipped: {excluded_count}")
    print("\nLooking for these game processes:")
    for game, proc_name in state.process_names.items():
        print(f"  - {game}: '{proc_name}'")

    print("\nAll running processes (non-excluded):")
    for i, proc in enumerate(unique_processes):
        for expected_proc in state.process_names.values():
            if expected_proc and expected_proc.lower() in proc.lower():
                print(f"  {i:3d}. {proc}  <-- POTENTIAL MATCH")
                break
        else:
            print(f"  {i:3d}. {proc}")
    print("=== END DEBUG ===\n")


def monitor_game_and_update_title(state: AppState, twitch_client: TwitchClient) -> None:
    last_game = None
    debug_count = 0

    print("Starting game monitoring...")
    print(f"Monitoring for {len(state.process_names)} games")
    debug_all_processes(state)

    while True:
        detected_game = get_current_game(state)

        if detected_game is None:
            state.current_game = "No game detected"
            if state.keep_last_when_no_game:
                time.sleep(30)
                continue
            current_game = "Just Chatting"
        else:
            current_game = detected_game
            state.current_game = current_game

        if current_game != last_game:
            last_game = current_game
            print(f"Game changed to: {current_game}")
            new_title = format_title(state.base_template, current_game)
            if state.custom_suffix:
                new_title = f"{new_title} {state.custom_suffix}"
            twitch_client.update_stream_title(new_title)

            category_name = state.twitch_categories.get(current_game, "Just Chatting")
            twitch_client.update_stream_category(category_name)

        debug_count += 1
        if debug_count >= 10:
            print("\n--- Periodic Process Check ---")
            get_current_game(state)
            debug_count = 0

        time.sleep(30)

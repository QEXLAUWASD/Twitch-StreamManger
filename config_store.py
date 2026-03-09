import json
import os

from app_state import AppState


def load_config(base_dir: str) -> dict:
    try:
        path = os.path.join(base_dir, "config.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config.json: {e}")
        return {}


def apply_config_to_state(state: AppState, config: dict) -> None:
    state.app_config = config
    state.base_template = config.get("base", " %game% %date%")
    state.process_names = config.get("process_name", {})
    state.twitch_categories = config.get("TwitchCategoryName", {})


def save_config(base_dir: str, state: AppState) -> None:
    if "process_name" not in state.app_config:
        state.app_config["process_name"] = {}
    if "TwitchCategoryName" not in state.app_config:
        state.app_config["TwitchCategoryName"] = {}
    if "base" not in state.app_config:
        state.app_config["base"] = state.base_template

    with open(os.path.join(base_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(state.app_config, f, ensure_ascii=False, indent=4)


def add_custom_game(base_dir: str, state: AppState, game_name: str, process_name_str: str, twitch_category: str | None = None) -> bool:
    try:
        if not game_name or not process_name_str:
            raise ValueError("game_name and process_name are required")

        if "process_name" not in state.app_config:
            state.app_config["process_name"] = {}
        state.app_config["process_name"][game_name] = process_name_str

        if twitch_category:
            if "TwitchCategoryName" not in state.app_config:
                state.app_config["TwitchCategoryName"] = {}
            state.app_config["TwitchCategoryName"][game_name] = twitch_category

        save_config(base_dir, state)
        state.process_names = state.app_config.get("process_name", {})
        state.twitch_categories = state.app_config.get("TwitchCategoryName", {})
        print(f"Added/updated custom game: {game_name} -> {process_name_str} (Category: {twitch_category})")
        return True
    except Exception as e:
        print(f"Error adding custom game: {e}")
        return False


def load_excluded_processes(base_dir: str, state: AppState) -> None:
    path = os.path.join(base_dir, "excluded_processes.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        state.excluded_names = {n.lower() for n in data.get("exclude_process_names", []) if n}
        state.excluded_prefixes = [p.lower() for p in data.get("exclude_prefixes", []) if p]
        print(f"Loaded exclusions: {len(state.excluded_names)} names, {len(state.excluded_prefixes)} prefixes")
    except FileNotFoundError:
        print("excluded_processes.json not found - no exclusions loaded.")
    except Exception as e:
        print(f"Error loading excluded_processes.json: {e}")


def save_excluded_processes(base_dir: str, state: AppState) -> None:
    path = os.path.join(base_dir, "excluded_processes.json")
    data = {
        "exclude_process_names": sorted(list(state.excluded_names)),
        "exclude_prefixes": state.excluded_prefixes,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

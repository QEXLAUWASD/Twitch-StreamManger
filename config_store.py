"""Configuration persistence layer – JSON read/write with atomic writes."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

from app_state import AppState

logger = logging.getLogger(__name__)

CONFIG_FILENAME: str = "config.json"
EXCLUSIONS_FILENAME: str = "excluded_processes.json"


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _read_json(path: str) -> dict[str, Any]:
    """Return parsed JSON dict, or an empty dict on any error."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        logger.debug("File not found: %s", path)
    except Exception:
        logger.exception("Failed to read %s", path)
    return {}


def _write_json(path: str, data: dict[str, Any]) -> None:
    """Atomically write *data* as JSON via a temp-file + rename."""
    try:
        dir_name = os.path.dirname(path) or "."
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=dir_name, delete=False, suffix=".tmp"
        ) as tf:
            json.dump(data, tf, ensure_ascii=False, indent=4)
            tf.flush()
            os.fsync(tf.fileno())
        os.replace(tf.name, path)
    except Exception:
        logger.exception("Failed to write %s", path)


# ---------------------------------------------------------------------------
# config.json
# ---------------------------------------------------------------------------

def load_config(base_dir: str) -> dict[str, Any]:
    """Load the main configuration dictionary from *base_dir*."""
    return _read_json(os.path.join(base_dir, CONFIG_FILENAME))


def apply_config_to_state(state: AppState, config: dict[str, Any]) -> None:
    """Populate *state* fields from a raw config dictionary."""
    state.app_config = config
    state.base_template = config.get("base", state.base_template)
    state.process_names = config.get("process_name", {})
    state.twitch_categories = config.get("TwitchCategoryName", {})
    state.language = config.get("language", state.language)
    state.keep_last_when_no_game = config.get("keep_last_when_none", state.keep_last_when_no_game)
    state.dark_mode = config.get("dark_mode", state.dark_mode)


def save_config(base_dir: str, state: AppState) -> None:
    """Persist current *state* settings into config.json.

    Builds a fresh dictionary rather than mutating ``state.app_config`` in-place.
    """
    cfg: dict[str, Any] = dict(state.app_config)
    cfg.setdefault("process_name", {})
    cfg.setdefault("TwitchCategoryName", {})
    cfg["base"] = state.base_template
    cfg["language"] = state.language
    cfg["keep_last_when_none"] = state.keep_last_when_no_game
    cfg["dark_mode"] = state.dark_mode
    _write_json(os.path.join(base_dir, CONFIG_FILENAME), cfg)


def add_custom_game(
    base_dir: str,
    state: AppState,
    game_name: str,
    process_name_str: str,
    twitch_category: str | None = None,
) -> bool:
    """Add or update a game→process mapping and optionally a Twitch category."""
    if not game_name or not process_name_str:
        logger.warning("add_custom_game: empty game_name or process_name")
        return False

    try:
        cfg: dict[str, Any] = dict(state.app_config)
        cfg.setdefault("process_name", {})[game_name] = process_name_str
        if twitch_category:
            cfg.setdefault("TwitchCategoryName", {})[game_name] = twitch_category

        _write_json(os.path.join(base_dir, CONFIG_FILENAME), cfg)

        # Sync state
        state.app_config = cfg
        state.process_names = cfg.get("process_name", {})
        state.twitch_categories = cfg.get("TwitchCategoryName", {})

        logger.info("Added/updated game: %s → %s (category: %s)", game_name, process_name_str, twitch_category)
        return True
    except Exception:
        logger.exception("add_custom_game failed")
        return False


# ---------------------------------------------------------------------------
# excluded_processes.json
# ---------------------------------------------------------------------------

def load_excluded_processes(base_dir: str, state: AppState) -> None:
    """Load process exclusion lists into *state*."""
    data = _read_json(os.path.join(base_dir, EXCLUSIONS_FILENAME))
    state.excluded_names = {n.lower() for n in data.get("exclude_process_names", []) if n}
    state.excluded_prefixes = [p.lower() for p in data.get("exclude_prefixes", []) if p]
    logger.info("Loaded exclusions: %d names, %d prefixes", len(state.excluded_names), len(state.excluded_prefixes))


def save_excluded_processes(base_dir: str, state: AppState) -> None:
    """Persist current exclusion lists."""
    _write_json(
        os.path.join(base_dir, EXCLUSIONS_FILENAME),
        {
            "exclude_process_names": sorted(state.excluded_names),
            "exclude_prefixes": state.excluded_prefixes,
        },
    )

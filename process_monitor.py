"""Process-detection engine: maps running processes → game names."""

from __future__ import annotations

import logging
import time
from typing import Sequence

import psutil

from app_state import (
    FALLBACK_CATEGORY,
    NO_GAME_LABEL,
    PERIODIC_DEBUG_CYCLES,
    POLL_INTERVAL_SEC,
    AppState,
)
from twitch_client import TwitchClient, format_title

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exclusion helpers
# ---------------------------------------------------------------------------

def is_excluded_process(proc_name: str, state: AppState) -> bool:
    """Return ``True`` if *proc_name* should be ignored."""
    if not proc_name:
        return True
    name_l = proc_name.lower()
    if name_l in state.excluded_names:
        return True
    for prefix in state.excluded_prefixes:
        if name_l.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# Process iteration (cached for one scan)
# ---------------------------------------------------------------------------

def _iter_non_excluded(state: AppState) -> list[str]:
    """Return a deduplicated, sorted list of non-excluded process names."""
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
# Game detection
# ---------------------------------------------------------------------------

def get_current_game(state: AppState) -> str | None:
    """Scan running processes and return the first matching game name.

    The algorithm:
    1. Collect all non-excluded process names in one pass.
    2. For each configured ``(game, expected_proc)`` mapping, try exact
       and fuzzy matches.  The first hit wins.
    """
    detected: list[str] = []
    for proc_name in _iter_non_excluded(state):
        detected.append(proc_name)

        for game, expected_proc in state.process_names.items():
            if _proc_matches(proc_name, expected_proc):
                logger.info("FOUND GAME: %s (process: %s)", game, proc_name)
                return game

    # Diagnostics
    logger.debug(
        "Looking for: %s – recent processes (non-excluded): %s",
        list(state.process_names.values()),
        detected[-10:],
    )
    return None


def _proc_matches(actual: str, expected: str) -> bool:
    """Fuzzy-match a process name against the configured expected name."""
    if not expected:
        return False
    a = actual.lower()
    e = expected.lower()
    return a == e or e in a


# ---------------------------------------------------------------------------
# Debugging
# ---------------------------------------------------------------------------

def debug_all_processes(state: AppState) -> None:
    """Print a full snapshot of running processes (for troubleshooting)."""
    all_names = _iter_non_excluded(state)
    expected_vals = {v.lower() for v in state.process_names.values() if v}

    logger.debug("=== DEBUG: Running Processes ===")
    logger.debug("Total unique (non-excluded): %d", len(all_names))
    for game, proc_name in state.process_names.items():
        logger.debug("  Configured: %s → '%s'", game, proc_name)

    for i, name in enumerate(all_names):
        marker = "  <-- POTENTIAL MATCH" if any(
            ev and ev in name.lower() for ev in expected_vals
        ) else ""
        logger.debug("  %3d. %s%s", i, name, marker)
    logger.debug("=== END DEBUG ===")


# ---------------------------------------------------------------------------
# Monitoring loop
# ---------------------------------------------------------------------------

def monitor_game_and_update_title(state: AppState, twitch_client: TwitchClient) -> None:
    """Main loop: detect game → update Twitch title & category."""
    last_game: str | None = None
    cycle_count: int = 0

    logger.info("Starting game monitoring for %d games", len(state.process_names))
    debug_all_processes(state)

    while True:
        detected_game = get_current_game(state)

        if detected_game is None:
            state.current_game = NO_GAME_LABEL
            if state.keep_last_when_no_game:
                time.sleep(POLL_INTERVAL_SEC)
                continue
            current_game = FALLBACK_CATEGORY
        else:
            current_game = detected_game
            state.current_game = current_game

        if current_game != last_game:
            last_game = current_game
            logger.info("Game changed → %s", current_game)
            _push_update(state, twitch_client, current_game)

        cycle_count += 1
        if cycle_count >= PERIODIC_DEBUG_CYCLES:
            logger.debug("--- Periodic process check ---")
            get_current_game(state)  # re-scan for logging
            cycle_count = 0

        time.sleep(POLL_INTERVAL_SEC)


def _push_update(state: AppState, twitch_client: TwitchClient, game: str) -> None:
    """Build the formatted title and push it + the category to Twitch."""
    new_title = format_title(state.base_template, game)
    if state.custom_suffix:
        new_title = f"{new_title} {state.custom_suffix}"
    twitch_client.update_stream_title(new_title)

    category = state.twitch_categories.get(game, FALLBACK_CATEGORY)
    twitch_client.update_stream_category(category)

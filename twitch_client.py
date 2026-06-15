"""Twitch Helix API client with retry logic and title/category formatting."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app_state import API_MAX_RETRIES, API_TIMEOUT_SEC, FALLBACK_CATEGORY

logger = logging.getLogger(__name__)

TWITCH_API_BASE: str = "https://api.twitch.tv/helix"


def _build_session() -> requests.Session:
    """Create a requests Session with retry logic for transient failures."""
    retry = Retry(
        total=API_MAX_RETRIES,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"GET", "PATCH"},
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    return session


class TwitchClient:
    """Minimal Twitch Helix API wrapper for updating stream info."""

    def __init__(self, client_id: str, access_token: str, streamer_id: str) -> None:
        self.streamer_id: str = streamer_id
        self._session: requests.Session = _build_session()
        self._headers: dict[str, str] = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_stream_category(self, category: str) -> None:
        """Resolve *category* name to a Twitch game_id and set it on the channel.

        Falls back to ``FALLBACK_CATEGORY`` exactly once to avoid infinite
        recursion when the fallback itself cannot be resolved.
        """
        game_id, game_name = self._resolve_game(category)
        if game_id is None:
            if category != FALLBACK_CATEGORY:
                logger.warning("Category '%s' not found – falling back to '%s'", category, FALLBACK_CATEGORY)
                self.update_stream_category(FALLBACK_CATEGORY)
            return

        if not self._patch_channel({"game_id": game_id}):
            logger.error("Failed to update category to '%s'", game_name)
        else:
            logger.info("Stream category updated → %s", game_name)

    def update_stream_title(self, title: str) -> None:
        """Set the stream title via Twitch Helix."""
        if self._patch_channel({"title": title}):
            logger.info("Stream title updated → %s", title)
        else:
            logger.error("Failed to update stream title")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_game(self, name: str) -> tuple[str | None, str | None]:
        """Return ``(game_id, game_name)`` for a category name, or ``(None, None)``."""
        try:
            resp = self._session.get(
                f"{TWITCH_API_BASE}/games",
                headers=self._headers,
                params={"name": name},
                timeout=API_TIMEOUT_SEC,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            items: list[dict[str, Any]] = data.get("data", [])
            if items:
                return items[0]["id"], items[0]["name"]
        except Exception:
            logger.exception("Failed to resolve game '%s'", name)
        return None, None

    def _patch_channel(self, payload: dict[str, Any]) -> bool:
        """PATCH the broadcaster's channel.  Returns ``True`` on success."""
        try:
            url = f"{TWITCH_API_BASE}/channels?broadcaster_id={self.streamer_id}"
            resp = self._session.patch(
                url,
                headers=self._headers,
                json=payload,
                timeout=API_TIMEOUT_SEC,
            )
            if resp.status_code == 204:
                return True
            logger.error("PATCH failed (%d): %s", resp.status_code, resp.text)
        except Exception:
            logger.exception("PATCH exception for payload %s", payload)
        return False


def format_title(template: str, game: str) -> str:
    """Replace ``%date%`` and ``%game%`` placeholders in *template*."""
    current_date: str = time.strftime("%Y-%m-%d")
    return template.replace("%date%", current_date).replace("%game%", game)

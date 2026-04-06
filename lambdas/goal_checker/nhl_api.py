"""NHL API client for checking Bryan Rust's goal-scoring performance.

Uses the public NHL API (api-web.nhle.com). No API key required.
"""

import json
import logging
import urllib.request
import urllib.error
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

NHL_API_BASE = "https://api-web.nhle.com/v1"

# Game type constants
REGULAR_SEASON = 2
PLAYOFFS = 3


def get_current_season() -> str:
    """Determine the current NHL season string (e.g., '20252026').

    NHL season runs roughly October → June.
      - Oct–Dec 2025 → '20252026'
      - Jan–Sep 2026 → '20252026'
    """
    today = date.today()
    if today.month >= 10:
        return f"{today.year}{today.year + 1}"
    else:
        return f"{today.year - 1}{today.year}"


def _api_get(url: str) -> dict:
    """Make a GET request to the NHL API and return parsed JSON."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "RustyShakeAlert/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.error(f"NHL API HTTP error {e.code} for {url}")
        raise
    except urllib.error.URLError as e:
        logger.error(f"NHL API connection error for {url}: {e.reason}")
        raise


def fetch_game_log(
    player_id: str,
    season: str,
    game_type: int = REGULAR_SEASON,
) -> list[dict]:
    """Fetch a player's game log for the given season and game type.

    Args:
        player_id: NHL player ID (e.g., '8475825' for Bryan Rust)
        season: Season string (e.g., '20252026')
        game_type: 2 = regular season, 3 = playoffs

    Returns:
        List of game log entries. Each entry contains:
          - gameDate (str): 'YYYY-MM-DD'
          - goals (int)
          - assists (int)
          - gameId (int)
          - teamAbbrev (dict): {"default": "PIT"}
          - opponentAbbrev (dict): {"default": "WSH"}
    """
    url = f"{NHL_API_BASE}/player/{player_id}/game-log/{season}/{game_type}"
    logger.info(f"Fetching game log: {url}")

    data = _api_get(url)
    return data.get("gameLog", [])


def _extract_abbrev(field) -> str:
    """Extract abbreviation from NHL API field (handles both str and dict)."""
    if isinstance(field, dict):
        return field.get("default", "UNK")
    if isinstance(field, str):
        return field
    return "UNK"


def check_goals_for_date(
    player_id: str,
    target_date: date,
    include_playoffs: bool = False,
) -> Optional[dict]:
    """Check if the player scored any goals on the given date.

    Args:
        player_id: NHL player ID
        target_date: The date to check
        include_playoffs: Whether to also check playoff games

    Returns:
        Dict with game details if a game was played, None if no game.
        Example:
            {
                'game_date': '2026-04-05',
                'goals': 2,
                'assists': 1,
                'game_id': 2025020001,
                'opponent': 'WSH',
                'game_type': 'regular_season',
            }
    """
    season = get_current_season()
    target_str = target_date.isoformat()

    game_types = [REGULAR_SEASON]
    if include_playoffs:
        game_types.append(PLAYOFFS)

    for game_type in game_types:
        try:
            game_log = fetch_game_log(player_id, season, game_type)
        except Exception:
            logger.exception(f"Failed to fetch game log (type={game_type})")
            continue

        for entry in game_log:
            if entry.get("gameDate") == target_str:
                game_type_name = (
                    "playoffs" if game_type == PLAYOFFS else "regular_season"
                )
                return {
                    "game_date": target_str,
                    "goals": entry.get("goals", 0),
                    "assists": entry.get("assists", 0),
                    "game_id": entry.get("gameId"),
                    "opponent": _extract_abbrev(entry.get("opponentAbbrev")),
                    "game_type": game_type_name,
                }

    return None  # No game found for that date

"""Unit tests for NHL API client."""

import json
import sys
import os
from datetime import date
from unittest.mock import patch, MagicMock

import pytest

# Add Lambda source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambdas", "goal_checker"))

from nhl_api import (
    get_current_season,
    check_goals_for_date,
    fetch_game_log,
    _extract_abbrev,
    REGULAR_SEASON,
    PLAYOFFS,
)


# ── Sample API Responses ──────────────────────────────────────────────

SAMPLE_GAME_LOG_WITH_GOALS = {
    "gameLog": [
        {
            "gameId": 2025020950,
            "teamAbbrev": {"default": "PIT"},
            "homeRoadFlag": "H",
            "gameDate": "2026-04-05",
            "goals": 2,
            "assists": 1,
            "points": 3,
            "opponentAbbrev": {"default": "WSH"},
            "opponentCommonName": {"default": "Capitals"},
        },
        {
            "gameId": 2025020940,
            "teamAbbrev": {"default": "PIT"},
            "homeRoadFlag": "R",
            "gameDate": "2026-04-03",
            "goals": 0,
            "assists": 1,
            "points": 1,
            "opponentAbbrev": {"default": "NYR"},
            "opponentCommonName": {"default": "Rangers"},
        },
    ]
}

SAMPLE_GAME_LOG_NO_GOALS = {
    "gameLog": [
        {
            "gameId": 2025020940,
            "teamAbbrev": {"default": "PIT"},
            "gameDate": "2026-04-05",
            "goals": 0,
            "assists": 0,
            "opponentAbbrev": {"default": "NYR"},
        },
    ]
}

SAMPLE_GAME_LOG_EMPTY = {"gameLog": []}


# ── Tests: get_current_season ─────────────────────────────────────────


class TestGetCurrentSeason:
    @patch("nhl_api.date")
    def test_october_starts_new_season(self, mock_date):
        mock_date.today.return_value = date(2025, 10, 15)
        assert get_current_season() == "20252026"

    @patch("nhl_api.date")
    def test_december_same_season(self, mock_date):
        mock_date.today.return_value = date(2025, 12, 31)
        assert get_current_season() == "20252026"

    @patch("nhl_api.date")
    def test_january_previous_season_start(self, mock_date):
        mock_date.today.return_value = date(2026, 1, 5)
        assert get_current_season() == "20252026"

    @patch("nhl_api.date")
    def test_april_previous_season_start(self, mock_date):
        mock_date.today.return_value = date(2026, 4, 6)
        assert get_current_season() == "20252026"

    @patch("nhl_api.date")
    def test_july_offseason(self, mock_date):
        mock_date.today.return_value = date(2026, 7, 15)
        assert get_current_season() == "20252026"


# ── Tests: _extract_abbrev ────────────────────────────────────────────


class TestExtractAbbrev:
    def test_dict_format(self):
        assert _extract_abbrev({"default": "WSH"}) == "WSH"

    def test_string_format(self):
        assert _extract_abbrev("WSH") == "WSH"

    def test_none_returns_unk(self):
        assert _extract_abbrev(None) == "UNK"

    def test_empty_dict_returns_unk(self):
        assert _extract_abbrev({}) == "UNK"


# ── Tests: check_goals_for_date ───────────────────────────────────────


class TestCheckGoalsForDate:
    @patch("nhl_api.fetch_game_log")
    def test_goal_scored_yesterday(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_GAME_LOG_WITH_GOALS["gameLog"]

        result = check_goals_for_date("8475825", date(2026, 4, 5))

        assert result is not None
        assert result["goals"] == 2
        assert result["opponent"] == "WSH"
        assert result["game_date"] == "2026-04-05"
        assert result["game_type"] == "regular_season"

    @patch("nhl_api.fetch_game_log")
    def test_no_goals_yesterday(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_GAME_LOG_NO_GOALS["gameLog"]

        result = check_goals_for_date("8475825", date(2026, 4, 5))

        assert result is not None
        assert result["goals"] == 0
        assert result["opponent"] == "NYR"

    @patch("nhl_api.fetch_game_log")
    def test_no_game_yesterday(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_GAME_LOG_WITH_GOALS["gameLog"]

        # Check a date when no game was played
        result = check_goals_for_date("8475825", date(2026, 4, 4))

        assert result is None

    @patch("nhl_api.fetch_game_log")
    def test_empty_game_log(self, mock_fetch):
        mock_fetch.return_value = []

        result = check_goals_for_date("8475825", date(2026, 4, 5))

        assert result is None

    @patch("nhl_api.fetch_game_log")
    def test_api_failure_returns_none(self, mock_fetch):
        mock_fetch.side_effect = Exception("API Down")

        result = check_goals_for_date("8475825", date(2026, 4, 5))

        assert result is None

    @patch("nhl_api.fetch_game_log")
    def test_playoffs_checked_when_enabled(self, mock_fetch):
        # Regular season returns nothing, playoffs return a goal
        def side_effect(player_id, season, game_type):
            if game_type == PLAYOFFS:
                return [
                    {
                        "gameId": 2025030101,
                        "gameDate": "2026-04-20",
                        "goals": 1,
                        "assists": 0,
                        "opponentAbbrev": {"default": "NYI"},
                    }
                ]
            return []

        mock_fetch.side_effect = side_effect

        # Without playoffs — should find nothing
        result = check_goals_for_date(
            "8475825", date(2026, 4, 20), include_playoffs=False
        )
        assert result is None

        # With playoffs — should find the goal
        result = check_goals_for_date(
            "8475825", date(2026, 4, 20), include_playoffs=True
        )
        assert result is not None
        assert result["goals"] == 1
        assert result["game_type"] == "playoffs"

    @patch("nhl_api.fetch_game_log")
    def test_regular_season_checked_first(self, mock_fetch):
        """When both regular season and playoff games exist, regular season wins."""

        def side_effect(player_id, season, game_type):
            return [
                {
                    "gameId": 2025020950 if game_type == REGULAR_SEASON else 2025030101,
                    "gameDate": "2026-04-05",
                    "goals": 2 if game_type == REGULAR_SEASON else 1,
                    "assists": 0,
                    "opponentAbbrev": {"default": "WSH"},
                }
            ]

        mock_fetch.side_effect = side_effect

        result = check_goals_for_date(
            "8475825", date(2026, 4, 5), include_playoffs=True
        )
        # Should return regular season result first
        assert result["goals"] == 2
        assert result["game_type"] == "regular_season"

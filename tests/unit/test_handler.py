"""Unit tests for the Goal Checker Lambda handler."""

import json
import sys
import os
from datetime import date
from unittest.mock import patch, MagicMock

import pytest

# Add Lambda source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambdas", "goal_checker"))

# Must set env vars BEFORE importing handler (boto3 clients init at import time)
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["PLAYER_ID"] = "8475825"
os.environ["PLAYER_NAME"] = "Bryan Rust"
os.environ["SUBSCRIBERS_TABLE"] = "test-subscribers"
os.environ["GOAL_HISTORY_TABLE"] = "test-goal-history"
os.environ["SENDER_EMAIL"] = "test@example.com"
os.environ["INCLUDE_PLAYOFFS"] = "false"


SAMPLE_GAME_INFO = {
    "game_date": "2026-04-05",
    "goals": 2,
    "assists": 1,
    "game_id": 2025020950,
    "opponent": "WSH",
    "game_type": "regular_season",
}

SAMPLE_GAME_NO_GOALS = {
    "game_date": "2026-04-05",
    "goals": 0,
    "assists": 0,
    "game_id": 2025020950,
    "opponent": "WSH",
    "game_type": "regular_season",
}

SAMPLE_SUBSCRIBER = {
    "email": "fan@example.com",
    "name": "Test Fan",
    "status": "active",
    "confirmed": True,
    "confirmation_token": "abc123",
}


class TestLambdaHandler:
    @patch("handler._log_goal_event")
    @patch("handler._get_active_subscribers")
    @patch("handler._already_sent")
    @patch("handler._send_goal_emails")
    @patch("handler.check_goals_for_date")
    @patch("handler._get_yesterday_et")
    def test_no_game_yesterday(
        self, mock_yesterday, mock_check, mock_send, mock_sent, mock_subs, mock_log
    ):
        from handler import lambda_handler

        mock_yesterday.return_value = date(2026, 4, 5)
        mock_check.return_value = None  # No game

        result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "No game" in result["body"]
        mock_send.assert_not_called()

    @patch("handler._log_goal_event")
    @patch("handler._get_active_subscribers")
    @patch("handler._already_sent")
    @patch("handler._send_goal_emails")
    @patch("handler.check_goals_for_date")
    @patch("handler._get_yesterday_et")
    def test_game_but_no_goals(
        self, mock_yesterday, mock_check, mock_send, mock_sent, mock_subs, mock_log
    ):
        from handler import lambda_handler

        mock_yesterday.return_value = date(2026, 4, 5)
        mock_check.return_value = SAMPLE_GAME_NO_GOALS

        result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        mock_log.assert_called_once()
        mock_send.assert_not_called()

    @patch("handler._log_goal_event")
    @patch("handler._get_active_subscribers")
    @patch("handler._already_sent")
    @patch("handler._send_goal_emails")
    @patch("handler.check_goals_for_date")
    @patch("handler._get_yesterday_et")
    def test_goals_scored_sends_emails(
        self, mock_yesterday, mock_check, mock_send, mock_sent, mock_subs, mock_log
    ):
        from handler import lambda_handler

        mock_yesterday.return_value = date(2026, 4, 5)
        mock_check.return_value = SAMPLE_GAME_INFO
        mock_sent.return_value = False
        mock_subs.return_value = [SAMPLE_SUBSCRIBER]
        mock_send.return_value = 1

        result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["goals"] == 2
        assert body["emails_sent"] == 1
        mock_send.assert_called_once()
        mock_log.assert_called_once()

    @patch("handler._log_goal_event")
    @patch("handler._get_active_subscribers")
    @patch("handler._already_sent")
    @patch("handler._send_goal_emails")
    @patch("handler.check_goals_for_date")
    @patch("handler._get_yesterday_et")
    def test_idempotency_prevents_duplicate_sends(
        self, mock_yesterday, mock_check, mock_send, mock_sent, mock_subs, mock_log
    ):
        from handler import lambda_handler

        mock_yesterday.return_value = date(2026, 4, 5)
        mock_check.return_value = SAMPLE_GAME_INFO
        mock_sent.return_value = True  # Already sent!

        result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "Already processed" in result["body"]
        mock_send.assert_not_called()

    @patch("handler._log_goal_event")
    @patch("handler._get_active_subscribers")
    @patch("handler._already_sent")
    @patch("handler._send_goal_emails")
    @patch("handler.check_goals_for_date")
    @patch("handler._get_yesterday_et")
    def test_no_subscribers_skips_email(
        self, mock_yesterday, mock_check, mock_send, mock_sent, mock_subs, mock_log
    ):
        from handler import lambda_handler

        mock_yesterday.return_value = date(2026, 4, 5)
        mock_check.return_value = SAMPLE_GAME_INFO
        mock_sent.return_value = False
        mock_subs.return_value = []  # No subscribers

        result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        mock_send.assert_not_called()
        mock_log.assert_called_once()

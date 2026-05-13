"""Goal Checker Lambda — runs daily at 9 AM ET.

Checks if Bryan Rust scored a goal yesterday. If he did, sends a
promotional email to all active subscribers about The Milkshake
Factory's half-price "Rusty's Shake" deal.
"""

import json
import os
import logging
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

import boto3
from boto3.dynamodb.conditions import Key

from nhl_api import check_goals_for_date

# ── Logging ───────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Environment Variables ─────────────────────────────────────────────
PLAYER_ID = os.environ.get("PLAYER_ID", "8475825")
PLAYER_NAME = os.environ.get("PLAYER_NAME", "Bryan Rust")
SUBSCRIBERS_TABLE = os.environ.get("SUBSCRIBERS_TABLE", "rusty-subscribers")
GOAL_HISTORY_TABLE = os.environ.get("GOAL_HISTORY_TABLE", "rusty-goal-history")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
INCLUDE_PLAYOFFS = os.environ.get("INCLUDE_PLAYOFFS", "false").lower() == "true"
SES_CONFIG_SET = os.environ.get("SES_CONFIG_SET", "")
API_BASE_URL = os.environ.get("API_BASE_URL", "")

# ── AWS Clients ───────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb")
ses_client = boto3.client("ses")

# ── Template Cache ────────────────────────────────────────────────────
_GOAL_EMAIL_TEMPLATE = None


def _load_email_template() -> str:
    """Load the goal email HTML template (cached after first call)."""
    global _GOAL_EMAIL_TEMPLATE
    if _GOAL_EMAIL_TEMPLATE is None:
        template_path = os.path.join(
            os.path.dirname(__file__), "templates", "goal_email.html"
        )
        with open(template_path, "r", encoding="utf-8") as f:
            _GOAL_EMAIL_TEMPLATE = f.read()
    return _GOAL_EMAIL_TEMPLATE


def _mask_email(email: str) -> str:
    """Mask email for safe logging: 'test@example.com' → 'tes***@example.com'."""
    if "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    masked_local = local[:3] + "***" if len(local) > 3 else local[0] + "***"
    return f"{masked_local}@{domain}"


# ═══════════════════════════════════════════════════════════════════════
# HANDLER
# ═══════════════════════════════════════════════════════════════════════


def lambda_handler(event, context):
    """Main entry point — triggered by EventBridge daily."""
    logger.info(f"Goal Checker invoked. Source: {event.get('source', 'manual')}")

    # ── TEST-MODE OVERRIDE ────────────────────────────────────────────
    # If the invoke event contains "mock_game", skip the NHL API call
    # and use the provided data instead. Optional "bypass_idempotency"
    # flag also allows re-sending for a game_date we've processed before.
    # Required keys in mock_game: game_date (YYYY-MM-DD), goals, opponent.
    # Optional: game_id, assists, game_type.
    mock_game = event.get("mock_game")
    if mock_game:
        logger.warning(f"TEST MODE: using mock game data: {mock_game}")
        game_info = {
            "game_date": mock_game["game_date"],
            "game_id": mock_game.get("game_id", 0),
            "goals": int(mock_game.get("goals", 0)),
            "assists": int(mock_game.get("assists", 0)),
            "opponent": mock_game.get("opponent", "TEST"),
            "game_type": mock_game.get("game_type", "regular_season"),
        }
        bypass_idempotency = bool(event.get("bypass_idempotency", False))
    else:
        bypass_idempotency = False
        yesterday = _get_yesterday_et()
        logger.info(f"Checking for goals on: {yesterday.isoformat()}")

        # 1. Check if Rust played and scored yesterday
        game_info = check_goals_for_date(
            player_id=PLAYER_ID,
            target_date=yesterday,
            include_playoffs=INCLUDE_PLAYOFFS,
        )

    if game_info is None:
        logger.info("No game found yesterday. Nothing to do.")
        return {"statusCode": 200, "body": "No game yesterday."}

    goals = game_info["goals"]
    opponent = game_info["opponent"]
    logger.info(
        f"Game found vs {opponent}: {goals} goal(s) on {game_info['game_date']}"
    )

    if goals == 0:
        logger.info("Rust played but didn't score. Logging and exiting.")
        _log_goal_event(game_info, emails_sent=0)
        return {"statusCode": 200, "body": f"No goals vs {opponent}."}

    # 2. Idempotency check — did we already send for this game?
    if not bypass_idempotency and _already_sent(game_info["game_date"]):
        logger.warning(
            f"Emails already sent for {game_info['game_date']}. Skipping."
        )
        return {"statusCode": 200, "body": "Already processed."}

    # 3. Get active subscribers
    subscribers = _get_active_subscribers()
    logger.info(f"Found {len(subscribers)} active subscriber(s)")

    if not subscribers:
        logger.info("No active subscribers. Logging goal, skipping email.")
        _log_goal_event(game_info, emails_sent=0)
        return {"statusCode": 200, "body": "No subscribers to email."}

    # 4. Send emails
    sent_count = _send_goal_emails(subscribers, game_info)
    logger.info(f"Sent {sent_count}/{len(subscribers)} email(s)")

    # 5. Log the event
    _log_goal_event(game_info, emails_sent=sent_count)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "goals": goals,
                "opponent": opponent,
                "emails_sent": sent_count,
            }
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════


def _get_yesterday_et() -> date:
    """Get yesterday's date in Eastern Time (handles DST)."""
    now_et = datetime.now(ZoneInfo("America/New_York"))
    return (now_et - timedelta(days=1)).date()


def _already_sent(game_date_str: str) -> bool:
    """Check if we already sent emails for this game date (idempotency)."""
    table = dynamodb.Table(GOAL_HISTORY_TABLE)
    response = table.get_item(Key={"game_date": game_date_str})
    item = response.get("Item")
    return bool(item and item.get("emails_sent", 0) > 0)


def _log_goal_event(game_info: dict, emails_sent: int = 0) -> None:
    """Record the goal event (or lack thereof) in DynamoDB."""
    table = dynamodb.Table(GOAL_HISTORY_TABLE)
    table.put_item(
        Item={
            "game_date": game_info["game_date"],
            "game_id": game_info.get("game_id", 0),
            "goals": game_info.get("goals", 0),
            "assists": game_info.get("assists", 0),
            "opponent": game_info.get("opponent", "UNK"),
            "game_type": game_info.get("game_type", "regular_season"),
            "emails_sent": emails_sent,
            "sent_at": datetime.utcnow().isoformat() + "Z",
        }
    )


def _get_active_subscribers() -> list[dict]:
    """Retrieve all active, confirmed subscribers from DynamoDB."""
    table = dynamodb.Table(SUBSCRIBERS_TABLE)

    results = []
    response = table.query(
        IndexName="status-index",
        KeyConditionExpression=Key("status").eq("active"),
    )
    results.extend(response.get("Items", []))

    # Handle pagination
    while "LastEvaluatedKey" in response:
        response = table.query(
            IndexName="status-index",
            KeyConditionExpression=Key("status").eq("active"),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        results.extend(response.get("Items", []))

    # Only include confirmed subscribers
    return [s for s in results if s.get("confirmed", False)]


def _send_goal_emails(subscribers: list[dict], game_info: dict) -> int:
    """Send goal alert emails to all subscribers. Returns count sent."""
    if not SENDER_EMAIL:
        logger.error(
            "SENDER_EMAIL not configured. Set it in Lambda env vars "
            "after verifying an email address in SES."
        )
        return 0

    goals = game_info["goals"]
    opponent = game_info.get("opponent", "opponent")
    game_date = game_info["game_date"]
    goal_word = "goal" if goals == 1 else "goals"

    subject = (
        f"\U0001f3d2 {PLAYER_NAME} scored {goals} {goal_word}! "
        f"Half-price Rusty's Shake today!"
    )

    sent_count = 0
    for subscriber in subscribers:
        name = subscriber.get("name", "Fan")
        email = subscriber["email"]
        token = subscriber.get("confirmation_token", "")

        unsubscribe_url = _build_unsubscribe_url(token)

        body_html = _build_email_html(
            name=name,
            goals=goals,
            goal_word=goal_word,
            opponent=opponent,
            game_date=game_date,
            unsubscribe_url=unsubscribe_url,
        )
        body_text = (
            f"Hi {name}!\n\n"
            f"Great news! {PLAYER_NAME} scored {goals} {goal_word} "
            f"against {opponent} on {game_date}!\n\n"
            f"Head to The Milkshake Factory today for a half-price "
            f"Rusty's Shake!\n\n"
            f"Go Pens! \U0001f427\n\n"
            f"Unsubscribe: {unsubscribe_url}"
        )

        try:
            send_kwargs = {
                "Source": SENDER_EMAIL,
                "Destination": {"ToAddresses": [email]},
                "Message": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": body_html, "Charset": "UTF-8"},
                        "Text": {"Data": body_text, "Charset": "UTF-8"},
                    },
                },
            }

            # Attach SES configuration set for bounce/complaint tracking
            if SES_CONFIG_SET:
                send_kwargs["ConfigurationSetName"] = SES_CONFIG_SET

            ses_client.send_email(**send_kwargs)
            sent_count += 1
        except Exception:
            logger.exception(f"Failed to send email to {_mask_email(email)}")

    return sent_count


def _build_unsubscribe_url(token: str) -> str:
    """Build the unsubscribe URL for a subscriber."""
    if API_BASE_URL:
        base = API_BASE_URL.rstrip("/")
        return f"{base}/unsubscribe?token={token}"
    return f"#unsubscribe?token={token}"


def _build_email_html(
    name: str,
    goals: int,
    goal_word: str,
    opponent: str,
    game_date: str,
    unsubscribe_url: str,
) -> str:
    """Build the HTML email body from the external template.

    Falls back to a minimal inline template if the file can't be loaded.
    """
    try:
        template = _load_email_template()
        return template.format(
            name=name,
            player_name=PLAYER_NAME,
            goals=goals,
            goal_word=goal_word,
            opponent=opponent,
            game_date=game_date,
            unsubscribe_url=unsubscribe_url,
        )
    except Exception:
        logger.exception("Failed to load email template, using fallback")
        # Minimal fallback — ensures emails still go out even if
        # the template file is missing or malformed
        return (
            f"<h1>{PLAYER_NAME} scored {goals} {goal_word}!</h1>"
            f"<p>Hi {name}! Head to The Milkshake Factory for a "
            f"half-price Rusty's Shake!</p>"
            f"<p><a href=\"{unsubscribe_url}\">Unsubscribe</a></p>"
        )

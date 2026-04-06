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

# ── AWS Clients ───────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb")
ses_client = boto3.client("ses")


# ═══════════════════════════════════════════════════════════════════════
# HANDLER
# ═══════════════════════════════════════════════════════════════════════


def lambda_handler(event, context):
    """Main entry point — triggered by EventBridge daily."""
    logger.info(f"Goal Checker invoked. Event: {json.dumps(event)}")

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
    if _already_sent(game_info["game_date"]):
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

        body_html = _build_email_html(
            name=name,
            goals=goals,
            goal_word=goal_word,
            opponent=opponent,
            game_date=game_date,
            unsubscribe_token=token,
        )
        body_text = (
            f"Hi {name}!\n\n"
            f"Great news! {PLAYER_NAME} scored {goals} {goal_word} "
            f"against {opponent} on {game_date}!\n\n"
            f"Head to The Milkshake Factory today for a half-price "
            f"Rusty's Shake!\n\n"
            f"Go Pens! \U0001f427"
        )

        try:
            ses_client.send_email(
                Source=SENDER_EMAIL,
                Destination={"ToAddresses": [email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": body_html, "Charset": "UTF-8"},
                        "Text": {"Data": body_text, "Charset": "UTF-8"},
                    },
                },
            )
            sent_count += 1
        except Exception:
            logger.exception(f"Failed to send email to {email}")

    return sent_count


def _build_email_html(
    name: str,
    goals: int,
    goal_word: str,
    opponent: str,
    game_date: str,
    unsubscribe_token: str,
) -> str:
    """Build the HTML email body for a goal alert.

    Uses Penguins gold (#FCB514) + dark theme for on-brand styling.
    The email is inline-styled for maximum email client compatibility.
    """
    # TODO Phase 2: Load from templates/goal_email.html instead
    unsubscribe_url = f"#unsubscribe?token={unsubscribe_token}"

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rusty's Shake Alert</title>
</head>
<body style="margin:0; padding:0; background-color:#1a1a2e; font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background-color:#1a1a2e; padding:20px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0"
               style="background-color:#16213e; border-radius:12px; overflow:hidden; max-width:600px; width:100%;">
          <!-- HEADER -->
          <tr>
            <td style="background:linear-gradient(135deg,#FCB514,#CDA347); padding:32px 24px; text-align:center;">
              <h1 style="margin:0; color:#000; font-size:28px; line-height:1.2;">
                \U0001f3d2 GOAL ALERT!
              </h1>
              <p style="margin:10px 0 0; color:#000; font-size:17px; font-weight:bold;">
                {PLAYER_NAME} scored {goals} {goal_word}!
              </p>
            </td>
          </tr>
          <!-- BODY -->
          <tr>
            <td style="padding:32px 28px; color:#e0e0e0;">
              <p style="font-size:18px; margin:0 0 16px;">Hi {name}! \U0001f44b</p>
              <p style="font-size:16px; margin:0 0 16px; line-height:1.6;">
                Great news! <strong>{PLAYER_NAME}</strong> lit the lamp with
                <strong style="color:#FCB514;">{goals} {goal_word}</strong>
                against <strong>{opponent}</strong> on {game_date}!
              </p>
              <p style="font-size:16px; margin:0 0 28px; line-height:1.6;">
                That means today is <strong style="color:#FCB514;">Rusty&rsquo;s Shake Day</strong>
                at The Milkshake Factory! \U0001f389
              </p>
              <!-- CTA -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center">
                    <a href="https://themilkshakefactory.com" target="_blank"
                       style="display:inline-block; background:#FCB514; color:#000;
                              padding:16px 44px; text-decoration:none; font-size:18px;
                              font-weight:bold; border-radius:8px; letter-spacing:0.3px;">
                      \U0001f964 Get Half-Price Rusty&rsquo;s Shake!
                    </a>
                  </td>
                </tr>
              </table>
              <p style="font-size:14px; margin:28px 0 0; color:#888; text-align:center;">
                Let&rsquo;s Go Pens! \U0001f427
              </p>
            </td>
          </tr>
          <!-- FOOTER -->
          <tr>
            <td style="padding:20px 28px; background-color:#0f1629; text-align:center;
                        border-top:1px solid #2a2a4a;">
              <p style="margin:0; color:#666; font-size:12px; line-height:1.5;">
                You&rsquo;re receiving this because you subscribed to Rusty&rsquo;s Shake goal alerts.
              </p>
              <p style="margin:8px 0 0; font-size:12px;">
                <a href="{unsubscribe_url}" style="color:#FCB514; text-decoration:underline;">
                  Unsubscribe
                </a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

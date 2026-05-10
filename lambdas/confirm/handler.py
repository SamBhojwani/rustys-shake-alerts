"""Confirm Lambda — handles GET /confirm?token={token}.

Activates a subscriber's account after they click the confirmation
link in their double opt-in email. Validates token format and expiry.
"""

import os
import re
import logging
from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Key

# ── Logging ───────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Environment Variables ─────────────────────────────────────────────
SUBSCRIBERS_TABLE = os.environ.get("SUBSCRIBERS_TABLE", "rusty-subscribers")

# ── AWS Clients ───────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb")

# UUID format: 8-4-4-4-12 hex characters
_TOKEN_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _mask_email(email: str) -> str:
    """Mask email for safe logging."""
    if "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    masked_local = local[:3] + "***" if len(local) > 3 else local[0] + "***"
    return f"{masked_local}@{domain}"


# ── Template Cache ────────────────────────────────────────────────────
_SUBSCRIBED_HTML = None


def _load_subscribed_page() -> str:
    """Load the subscribed.html template (cached)."""
    global _SUBSCRIBED_HTML
    if _SUBSCRIBED_HTML is None:
        template_path = os.path.join(
            os.path.dirname(__file__), "templates", "subscribed.html"
        )
        with open(template_path, "r", encoding="utf-8") as f:
            _SUBSCRIBED_HTML = f.read()
    return _SUBSCRIBED_HTML


def _html_response(status_code: int, body: str) -> dict:
    """Return an API Gateway-compatible HTML response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store",
        },
        "body": body,
    }


def _error_page(message: str) -> str:
    """Simple error page HTML."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Error</title></head>
<body style="background:#1a1a2e; color:#e0e0e0; font-family:Arial,sans-serif;
             display:flex; justify-content:center; align-items:center;
             min-height:100vh; margin:0;">
  <div style="text-align:center; padding:40px;">
    <h1 style="color:#FCB514;">Oops!</h1>
    <p>{message}</p>
  </div>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════
# HANDLER
# ═══════════════════════════════════════════════════════════════════════


def lambda_handler(event, context):
    """Handle GET /confirm?token={token}."""
    logger.info("Confirm request received")

    # ── Extract and validate token ────────────────────────────────────
    params = event.get("queryStringParameters") or {}
    token = params.get("token", "").strip()

    if not token:
        logger.warning("No token provided")
        return _html_response(400, _error_page("Missing confirmation token."))

    if not _TOKEN_PATTERN.match(token):
        logger.warning("Invalid token format")
        return _html_response(400, _error_page("Invalid confirmation token."))

    # ── Look up subscriber by token ───────────────────────────────────
    table = dynamodb.Table(SUBSCRIBERS_TABLE)

    try:
        response = table.query(
            IndexName="token-index",
            KeyConditionExpression=Key("confirmation_token").eq(token),
        )
    except Exception:
        logger.exception("Failed to query subscribers table")
        return _html_response(
            500, _error_page("Something went wrong. Please try again later.")
        )

    items = response.get("Items", [])

    if not items:
        logger.warning(f"No subscriber found for token: {token[:8]}...")
        return _html_response(
            404,
            _error_page(
                "This confirmation link is invalid or has expired. "
                "Please subscribe again."
            ),
        )

    subscriber = items[0]
    email = subscriber["email"]

    # ── Check if already confirmed ────────────────────────────────────
    if subscriber.get("status") == "active" and subscriber.get("confirmed"):
        logger.info(f"Already confirmed: {_mask_email(email)}")
        return _html_response(200, _load_subscribed_page())

    # ── Check token expiry ────────────────────────────────────────────
    expires_at_str = subscriber.get("token_expires_at", "")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.rstrip("Z"))
            if datetime.utcnow() > expires_at:
                logger.warning(f"Expired token for: {_mask_email(email)}")
                return _html_response(
                    410,
                    _error_page(
                        "This confirmation link has expired. "
                        "Please subscribe again to get a new link."
                    ),
                )
        except (ValueError, TypeError):
            logger.warning("Could not parse token_expires_at, allowing confirmation")

    # ── Activate subscriber ───────────────────────────────────────────
    try:
        now_iso = datetime.utcnow().isoformat() + "Z"
        table.update_item(
            Key={"email": email},
            UpdateExpression=(
                "SET #s = :status, confirmed = :confirmed, "
                "confirmed_at = :now"
            ),
            ConditionExpression="#s = :pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": "active",
                ":confirmed": True,
                ":now": now_iso,
                ":pending": "pending",
            },
        )
        logger.info(f"Confirmed subscriber: {_mask_email(email)}")
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        # Subscriber is no longer pending — might have been unsubscribed
        # or already confirmed by another request
        logger.warning(f"Condition check failed for: {_mask_email(email)}")
        return _html_response(200, _load_subscribed_page())
    except Exception:
        logger.exception(f"Failed to confirm subscriber: {_mask_email(email)}")
        return _html_response(
            500, _error_page("Something went wrong. Please try again later.")
        )

    return _html_response(200, _load_subscribed_page())

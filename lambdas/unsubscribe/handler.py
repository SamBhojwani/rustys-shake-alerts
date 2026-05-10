"""Unsubscribe Lambda — handles GET /unsubscribe?token={token}.

Looks up the subscriber by their confirmation token, sets their status
to 'unsubscribed', and returns a styled confirmation page.
"""

import os
import re
import logging

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
    """Mask email for safe logging: 'test@example.com' → 'tes***@example.com'."""
    if "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    masked_local = local[:3] + "***" if len(local) > 3 else local[0] + "***"
    return f"{masked_local}@{domain}"

# ── Load unsubscribed confirmation page ───────────────────────────────
_UNSUBSCRIBED_HTML = None


def _load_unsubscribed_page() -> str:
    """Load the unsubscribed.html template (cached after first call)."""
    global _UNSUBSCRIBED_HTML
    if _UNSUBSCRIBED_HTML is None:
        template_path = os.path.join(
            os.path.dirname(__file__), "templates", "unsubscribed.html"
        )
        with open(template_path, "r", encoding="utf-8") as f:
            _UNSUBSCRIBED_HTML = f.read()
    return _UNSUBSCRIBED_HTML


def _html_response(status_code: int, body: str) -> dict:
    """Return an API Gateway-compatible HTML response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
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
    """Handle GET /unsubscribe?token={token}."""
    logger.info(f"Unsubscribe request received")

    # Extract token from query string
    params = event.get("queryStringParameters") or {}
    token = params.get("token", "").strip()

    if not token:
        logger.warning("No token provided in request")
        return _html_response(400, _error_page("Missing unsubscribe token."))

    # Validate token format (must be UUID)
    if not _TOKEN_PATTERN.match(token):
        logger.warning("Invalid token format received")
        return _html_response(400, _error_page("Invalid unsubscribe token."))

    # Look up subscriber by confirmation_token (via GSI)
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
                "We couldn&rsquo;t find your subscription. "
                "You may have already unsubscribed."
            ),
        )

    # Update subscriber status
    subscriber = items[0]
    email = subscriber["email"]

    try:
        table.update_item(
            Key={"email": email},
            UpdateExpression="SET #s = :status, confirmed = :confirmed",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": "unsubscribed",
                ":confirmed": False,
            },
        )
        logger.info(f"Successfully unsubscribed: {_mask_email(email)}")
    except Exception:
        logger.exception(f"Failed to update subscriber: {_mask_email(email)}")
        return _html_response(
            500, _error_page("Something went wrong. Please try again later.")
        )

    # Return the styled confirmation page
    return _html_response(200, _load_unsubscribed_page())

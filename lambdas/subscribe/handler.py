"""Subscribe Lambda — handles POST /subscribe.

Creates a pending subscriber with a confirmation token and sends
a double opt-in confirmation email. Designed with anti-enumeration
and input validation security measures.
"""

import json
import html
import os
import re
import uuid
import logging
from datetime import datetime, timedelta

import boto3
from boto3.dynamodb.conditions import Key

# ── Logging ───────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Environment Variables ─────────────────────────────────────────────
SUBSCRIBERS_TABLE = os.environ.get("SUBSCRIBERS_TABLE", "rusty-subscribers")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SES_CONFIG_SET = os.environ.get("SES_CONFIG_SET", "")
API_BASE_URL = os.environ.get("API_BASE_URL", "")
TOKEN_EXPIRY_HOURS = int(os.environ.get("TOKEN_EXPIRY_HOURS", "24"))

# ── AWS Clients ───────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb")
ses_client = boto3.client("ses")

# ── Validation Constants ──────────────────────────────────────────────
# Simplified RFC 5322 email pattern — permissive but catches garbage
_EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)
_MAX_NAME_LENGTH = 100
_MAX_EMAIL_LENGTH = 254  # RFC 5321

# Rate limit: minimum seconds between re-sending confirmation
_RESEND_COOLDOWN_SECONDS = 300  # 5 minutes

# ── Template Cache ────────────────────────────────────────────────────
_CONFIRM_EMAIL_TEMPLATE = None


def _load_confirm_template() -> str:
    """Load the confirmation email HTML template (cached)."""
    global _CONFIRM_EMAIL_TEMPLATE
    if _CONFIRM_EMAIL_TEMPLATE is None:
        template_path = os.path.join(
            os.path.dirname(__file__), "templates", "confirm_email.html"
        )
        with open(template_path, "r", encoding="utf-8") as f:
            _CONFIRM_EMAIL_TEMPLATE = f.read()
    return _CONFIRM_EMAIL_TEMPLATE


def _mask_email(email: str) -> str:
    """Mask email for safe logging."""
    if "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    masked_local = local[:3] + "***" if len(local) > 3 else local[0] + "***"
    return f"{masked_local}@{domain}"


def _json_response(status_code: int, body: dict) -> dict:
    """Return an API Gateway-compatible JSON response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(body),
    }


# Generic success message — same for new, existing, or invalid emails
# to prevent email enumeration attacks
_GENERIC_SUCCESS = {
    "message": "If this email is valid, you'll receive a confirmation link shortly."
}


# ═══════════════════════════════════════════════════════════════════════
# HANDLER
# ═══════════════════════════════════════════════════════════════════════


def lambda_handler(event, context):
    """Handle POST /subscribe."""
    logger.info("Subscribe request received")

    # ── Parse and validate input ──────────────────────────────────────
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _json_response(400, {"error": "Invalid JSON body."})

    raw_email = body.get("email", "")
    raw_name = body.get("name", "")

    # Validate email
    if not isinstance(raw_email, str):
        return _json_response(400, {"error": "Email must be a string."})

    email = raw_email.strip().lower()

    if not email or len(email) > _MAX_EMAIL_LENGTH:
        return _json_response(400, {"error": "Invalid email address."})

    if not _EMAIL_PATTERN.match(email):
        return _json_response(400, {"error": "Invalid email address."})

    # Validate and sanitize name
    if not isinstance(raw_name, str):
        return _json_response(400, {"error": "Name must be a string."})

    name = raw_name.strip()

    if not name or len(name) > _MAX_NAME_LENGTH:
        return _json_response(
            400,
            {"error": f"Name is required and must be under {_MAX_NAME_LENGTH} characters."},
        )

    # HTML-escape to prevent XSS when name is rendered in emails
    name = html.escape(name, quote=True)

    # ── Check for existing subscriber ─────────────────────────────────
    table = dynamodb.Table(SUBSCRIBERS_TABLE)

    try:
        response = table.get_item(Key={"email": email})
    except Exception:
        logger.exception("Failed to query subscribers table")
        return _json_response(500, {"error": "Internal server error."})

    existing = response.get("Item")

    if existing:
        return _handle_existing_subscriber(table, existing, name)

    # ── Create new subscriber ─────────────────────────────────────────
    token = str(uuid.uuid4())
    now = datetime.utcnow()
    expires_at = now + timedelta(hours=TOKEN_EXPIRY_HOURS)

    try:
        table.put_item(
            Item={
                "email": email,
                "name": name,
                "status": "pending",
                "confirmed": False,
                "confirmation_token": token,
                "token_expires_at": expires_at.isoformat() + "Z",
                "subscribed_at": now.isoformat() + "Z",
            },
            ConditionExpression="attribute_not_exists(email)",
        )
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        # Race condition: another request created it between our read and write
        # Return generic success anyway (anti-enumeration)
        logger.info("Concurrent subscribe detected, returning success")
        return _json_response(200, _GENERIC_SUCCESS)
    except Exception:
        logger.exception("Failed to create subscriber")
        return _json_response(500, {"error": "Internal server error."})

    # ── Send confirmation email ───────────────────────────────────────
    _send_confirmation_email(email, name, token)

    logger.info(f"New subscriber created: {_mask_email(email)}")
    return _json_response(200, _GENERIC_SUCCESS)


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════


def _handle_existing_subscriber(table, subscriber: dict, name: str) -> dict:
    """Handle subscribe request for an existing email address.

    Returns the same generic response regardless of outcome to prevent
    email enumeration.
    """
    email = subscriber["email"]
    status = subscriber.get("status", "")
    confirmed = subscriber.get("confirmed", False)

    # Already active and confirmed — do nothing
    if status == "active" and confirmed:
        logger.info(f"Already subscribed: {_mask_email(email)}")
        return _json_response(200, _GENERIC_SUCCESS)

    # Pending — re-send confirmation (with rate limiting)
    if status == "pending":
        last_sent = subscriber.get("subscribed_at", "")
        if last_sent and _within_cooldown(last_sent):
            logger.info(f"Resend cooldown active for: {_mask_email(email)}")
            return _json_response(200, _GENERIC_SUCCESS)

        # Generate new token and re-send
        token = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=TOKEN_EXPIRY_HOURS)

        try:
            table.update_item(
                Key={"email": email},
                UpdateExpression=(
                    "SET confirmation_token = :token, "
                    "token_expires_at = :expires, "
                    "subscribed_at = :now, "
                    "#n = :name"
                ),
                ExpressionAttributeNames={"#n": "name"},
                ExpressionAttributeValues={
                    ":token": token,
                    ":expires": expires_at.isoformat() + "Z",
                    ":now": now.isoformat() + "Z",
                    ":name": name,
                },
            )
        except Exception:
            logger.exception(f"Failed to update pending subscriber: {_mask_email(email)}")
            return _json_response(200, _GENERIC_SUCCESS)

        _send_confirmation_email(email, name, token)
        logger.info(f"Re-sent confirmation to: {_mask_email(email)}")
        return _json_response(200, _GENERIC_SUCCESS)

    # Unsubscribed — allow re-subscription
    if status == "unsubscribed":
        token = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=TOKEN_EXPIRY_HOURS)

        try:
            table.update_item(
                Key={"email": email},
                UpdateExpression=(
                    "SET #s = :status, "
                    "confirmed = :confirmed, "
                    "confirmation_token = :token, "
                    "token_expires_at = :expires, "
                    "subscribed_at = :now, "
                    "#n = :name"
                ),
                ExpressionAttributeNames={"#s": "status", "#n": "name"},
                ExpressionAttributeValues={
                    ":status": "pending",
                    ":confirmed": False,
                    ":token": token,
                    ":expires": expires_at.isoformat() + "Z",
                    ":now": now.isoformat() + "Z",
                    ":name": name,
                },
            )
        except Exception:
            logger.exception(f"Failed to re-subscribe: {_mask_email(email)}")
            return _json_response(200, _GENERIC_SUCCESS)

        _send_confirmation_email(email, name, token)
        logger.info(f"Re-subscription initiated for: {_mask_email(email)}")
        return _json_response(200, _GENERIC_SUCCESS)

    # Bounced or unknown status — do nothing
    logger.info(f"Ignoring subscribe for status={status}: {_mask_email(email)}")
    return _json_response(200, _GENERIC_SUCCESS)


def _within_cooldown(last_sent_iso: str) -> bool:
    """Check if we're still within the resend cooldown window."""
    try:
        last_sent = datetime.fromisoformat(last_sent_iso.rstrip("Z"))
        elapsed = (datetime.utcnow() - last_sent).total_seconds()
        return elapsed < _RESEND_COOLDOWN_SECONDS
    except (ValueError, TypeError):
        return False


def _send_confirmation_email(email: str, name: str, token: str) -> None:
    """Send the double opt-in confirmation email."""
    if not SENDER_EMAIL:
        logger.error("SENDER_EMAIL not configured — cannot send confirmation")
        return

    confirm_url = _build_confirm_url(token)

    try:
        template = _load_confirm_template()
        body_html = template.format(name=name, confirm_url=confirm_url)
    except Exception:
        logger.exception("Failed to load confirm email template")
        body_html = (
            f"<p>Hi {name}!</p>"
            f"<p>Click to confirm: <a href=\"{confirm_url}\">{confirm_url}</a></p>"
        )

    body_text = (
        f"Hi {name}!\n\n"
        f"Thanks for signing up for Rusty's Shake goal alerts.\n"
        f"Click to confirm your subscription:\n\n"
        f"{confirm_url}\n\n"
        f"This link expires in {TOKEN_EXPIRY_HOURS} hours."
    )

    subject = "\U0001f3d2 Confirm your Rusty's Shake subscription"

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

        if SES_CONFIG_SET:
            send_kwargs["ConfigurationSetName"] = SES_CONFIG_SET

        ses_client.send_email(**send_kwargs)
    except Exception:
        logger.exception(f"Failed to send confirmation to {_mask_email(email)}")


def _build_confirm_url(token: str) -> str:
    """Build the confirmation URL."""
    if API_BASE_URL:
        base = API_BASE_URL.rstrip("/")
        return f"{base}/confirm?token={token}"
    return f"#confirm?token={token}"

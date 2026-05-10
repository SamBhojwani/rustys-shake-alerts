"""Admin API Lambda — handles all /admin/* routes.

Protected by Cognito JWT authorizer at the API Gateway level.
This Lambda handles subscriber management, goal history queries,
test emails, and manual goal check triggers.
"""

import json
import os
import re
import logging
import urllib.parse
from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Key, Attr

# ── Logging ───────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Environment Variables ─────────────────────────────────────────────
SUBSCRIBERS_TABLE = os.environ.get("SUBSCRIBERS_TABLE", "rusty-subscribers")
GOAL_HISTORY_TABLE = os.environ.get("GOAL_HISTORY_TABLE", "rusty-goal-history")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SES_CONFIG_SET = os.environ.get("SES_CONFIG_SET", "")
GOAL_CHECKER_FUNCTION = os.environ.get("GOAL_CHECKER_FUNCTION", "")

# ── AWS Clients ───────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb")
ses_client = boto3.client("ses")
lambda_client = boto3.client("lambda")

# ── Constants ─────────────────────────────────────────────────────────
_MAX_PAGE_SIZE = 100
_DEFAULT_PAGE_SIZE = 25
_VALID_STATUSES = {"active", "pending", "unsubscribed", "bounced"}

# ── Security Headers ─────────────────────────────────────────────────
_SECURITY_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def _mask_email(email: str) -> str:
    """Mask email for safe logging."""
    if "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    masked_local = local[:3] + "***" if len(local) > 3 else local[0] + "***"
    return f"{masked_local}@{domain}"


def _json_response(status_code: int, body: dict) -> dict:
    """Return an API Gateway-compatible JSON response with security headers."""
    return {
        "statusCode": status_code,
        "headers": {**_SECURITY_HEADERS},
        "body": json.dumps(body, default=str),
    }


def _get_admin_email(event: dict) -> str:
    """Extract admin email from Cognito JWT claims."""
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    return claims.get("email", "admin")


def _safe_int(value, default: int, min_val: int = 1, max_val: int = _MAX_PAGE_SIZE) -> int:
    """Safely parse an integer parameter, clamped to [min_val, max_val]."""
    try:
        return max(min_val, min(int(value), max_val))
    except (ValueError, TypeError):
        return default


# ═══════════════════════════════════════════════════════════════════════
# HANDLER (path-based router)
# ═══════════════════════════════════════════════════════════════════════


def lambda_handler(event, context):
    """Route requests to the appropriate handler based on path + method."""
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("rawPath", "")
    logger.info(f"Admin API: {method} {path}")

    # Route matching
    if method == "GET" and path == "/admin/subscribers":
        return _list_subscribers(event)

    if method == "GET" and path == "/admin/subscribers/stats":
        return _subscriber_stats(event)

    if method == "DELETE" and path.startswith("/admin/subscribers/"):
        email = _extract_email_from_path(path)
        if email:
            return _delete_subscriber(email)
        return _json_response(400, {"error": "Invalid email in path."})

    if method == "GET" and path == "/admin/goals":
        return _list_goals(event)

    if method == "POST" and path == "/admin/test-email":
        return _send_test_email(event)

    if method == "POST" and path == "/admin/trigger-check":
        return _trigger_goal_check(event)

    return _json_response(404, {"error": "Not found."})


# ═══════════════════════════════════════════════════════════════════════
# ROUTE HANDLERS
# ═══════════════════════════════════════════════════════════════════════


def _list_subscribers(event: dict) -> dict:
    """GET /admin/subscribers — paginated subscriber list."""
    params = event.get("queryStringParameters") or {}

    status_filter = params.get("status", "").strip().lower()
    limit = _safe_int(params.get("limit", _DEFAULT_PAGE_SIZE), _DEFAULT_PAGE_SIZE)
    start_key_raw = params.get("startKey", "")

    # Whitelist status filter values
    if status_filter and status_filter not in _VALID_STATUSES:
        return _json_response(400, {"error": f"Invalid status. Allowed: {', '.join(sorted(_VALID_STATUSES))}"})

    table = dynamodb.Table(SUBSCRIBERS_TABLE)

    try:
        if status_filter:
            # Use the status-index GSI
            scan_kwargs = {
                "IndexName": "status-index",
                "KeyConditionExpression": Key("status").eq(status_filter),
                "Limit": limit,
            }
            if start_key_raw:
                try:
                    scan_kwargs["ExclusiveStartKey"] = json.loads(
                        urllib.parse.unquote(start_key_raw)
                    )
                except (json.JSONDecodeError, TypeError):
                    return _json_response(400, {"error": "Invalid pagination key."})
            response = table.query(**scan_kwargs)
        else:
            # Full table scan (all subscribers)
            scan_kwargs = {"Limit": limit}
            if start_key_raw:
                try:
                    scan_kwargs["ExclusiveStartKey"] = json.loads(
                        urllib.parse.unquote(start_key_raw)
                    )
                except (json.JSONDecodeError, TypeError):
                    return _json_response(400, {"error": "Invalid pagination key."})
            response = table.scan(**scan_kwargs)

        items = response.get("Items", [])
        last_key = response.get("LastEvaluatedKey")

        return _json_response(200, {
            "subscribers": items,
            "count": len(items),
            "nextKey": (
                urllib.parse.quote(json.dumps(last_key, default=str))
                if last_key
                else None
            ),
        })

    except Exception:
        logger.exception("Failed to list subscribers")
        return _json_response(500, {"error": "Failed to retrieve subscribers."})


def _subscriber_stats(event: dict) -> dict:
    """GET /admin/subscribers/stats — subscriber counts by status."""
    table = dynamodb.Table(SUBSCRIBERS_TABLE)

    counts = {}

    try:
        for status in _VALID_STATUSES:
            response = table.query(
                IndexName="status-index",
                KeyConditionExpression=Key("status").eq(status),
                Select="COUNT",
            )
            counts[status] = response.get("Count", 0)

        counts["total"] = sum(counts.values())

        return _json_response(200, {"stats": counts})

    except Exception:
        logger.exception("Failed to get subscriber stats")
        return _json_response(500, {"error": "Failed to retrieve stats."})


def _delete_subscriber(email: str) -> dict:
    """DELETE /admin/subscribers/{email} — remove a subscriber."""
    table = dynamodb.Table(SUBSCRIBERS_TABLE)

    try:
        table.delete_item(Key={"email": email})
        logger.info(f"Deleted subscriber: {_mask_email(email)}")
        return _json_response(200, {"message": "Subscriber deleted."})
    except Exception:
        logger.exception(f"Failed to delete: {_mask_email(email)}")
        return _json_response(500, {"error": "Failed to delete subscriber."})


def _list_goals(event: dict) -> dict:
    """GET /admin/goals — goal history, most recent first."""
    params = event.get("queryStringParameters") or {}
    limit = _safe_int(params.get("limit", _DEFAULT_PAGE_SIZE), _DEFAULT_PAGE_SIZE)

    table = dynamodb.Table(GOAL_HISTORY_TABLE)

    try:
        response = table.scan(Limit=limit)
        items = response.get("Items", [])

        # Sort by game_date descending
        items.sort(key=lambda x: x.get("game_date", ""), reverse=True)

        return _json_response(200, {
            "goals": items,
            "count": len(items),
        })

    except Exception:
        logger.exception("Failed to list goals")
        return _json_response(500, {"error": "Failed to retrieve goal history."})


def _send_test_email(event: dict) -> dict:
    """POST /admin/test-email — send a test goal alert to the admin."""
    admin_email = _get_admin_email(event)

    if not SENDER_EMAIL:
        return _json_response(400, {"error": "SENDER_EMAIL not configured."})

    # Validate admin email format before sending
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", admin_email):
        return _json_response(400, {"error": "Invalid admin email in token."})

    subject = "\U0001f3d2 [TEST] Bryan Rust scored 2 goals! Half-price Rusty's Shake!"
    body_html = (
        "<h1>&#x1F3D2; TEST Goal Alert</h1>"
        "<p>This is a <strong>test email</strong> from the admin dashboard.</p>"
        "<p>Bryan Rust scored <strong style='color:#FCB514;'>2 goals</strong> "
        "against WSH on 2026-04-05!</p>"
        "<p>Head to The Milkshake Factory for a half-price Rusty's Shake!</p>"
        "<p style='color:#888;'>This is a test — no actual goal was scored.</p>"
    )
    body_text = (
        "[TEST] Bryan Rust scored 2 goals against WSH!\n"
        "Head to The Milkshake Factory for a half-price Rusty's Shake!\n"
        "This is a test — no actual goal was scored."
    )

    try:
        send_kwargs = {
            "Source": SENDER_EMAIL,
            "Destination": {"ToAddresses": [admin_email]},
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
        logger.info(f"Test email sent to admin: {_mask_email(admin_email)}")
        return _json_response(200, {"message": "Test email sent."})

    except Exception:
        logger.exception("Failed to send test email")
        return _json_response(500, {"error": "Failed to send test email."})


def _trigger_goal_check(event: dict) -> dict:
    """POST /admin/trigger-check — manually invoke the goal checker."""
    if not GOAL_CHECKER_FUNCTION:
        return _json_response(400, {"error": "Goal checker function not configured."})

    try:
        response = lambda_client.invoke(
            FunctionName=GOAL_CHECKER_FUNCTION,
            InvocationType="Event",  # Async — don't wait for completion
            Payload=json.dumps({"source": "admin-manual-trigger"}),
        )
        logger.info("Manual goal check triggered by admin")
        return _json_response(200, {
            "message": "Goal check triggered. Check CloudWatch logs for results.",
            "statusCode": response.get("StatusCode", 0),
        })

    except Exception:
        logger.exception("Failed to trigger goal check")
        return _json_response(500, {"error": "Failed to trigger goal check."})


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════


def _extract_email_from_path(path: str) -> str:
    """Extract and decode email from /admin/subscribers/{email} path."""
    # Path: /admin/subscribers/user%40example.com
    parts = path.split("/admin/subscribers/", 1)
    if len(parts) != 2 or not parts[1]:
        return ""

    email = urllib.parse.unquote(parts[1]).strip().lower()

    # Strict email validation — format + length
    if len(email) > 254:
        return ""
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return ""

    return email

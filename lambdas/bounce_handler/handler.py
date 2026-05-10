"""Bounce/Complaint Handler Lambda — processes SES notification events.

Triggered by SNS when SES reports a bounce or complaint. Automatically
updates subscriber status in DynamoDB:
  - Hard bounce  → status = 'bounced'
  - Complaint    → status = 'unsubscribed'
"""

import json
import os
import logging

import boto3

# ── Logging ───────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Environment Variables ─────────────────────────────────────────────
SUBSCRIBERS_TABLE = os.environ.get("SUBSCRIBERS_TABLE", "rusty-subscribers")

# ── AWS Clients ───────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb")


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
    """Process SES bounce/complaint notifications from SNS."""
    logger.info(f"Bounce handler invoked with {len(event.get('Records', []))} record(s)")

    table = dynamodb.Table(SUBSCRIBERS_TABLE)
    processed = 0

    for record in event.get("Records", []):
        try:
            sns_message = json.loads(record["Sns"]["Message"])
            notification_type = sns_message.get("notificationType", "")

            if notification_type == "Bounce":
                processed += _handle_bounce(table, sns_message)
            elif notification_type == "Complaint":
                processed += _handle_complaint(table, sns_message)
            else:
                logger.info(f"Ignoring notification type: {notification_type}")

        except Exception:
            logger.exception("Failed to process SNS record")

    logger.info(f"Processed {processed} subscriber update(s)")
    return {"statusCode": 200, "processed": processed}


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════


def _handle_bounce(table, message: dict) -> int:
    """Handle SES bounce notification.

    Only acts on permanent (hard) bounces. Transient bounces are logged
    but the subscriber status is not changed.
    """
    bounce = message.get("bounce", {})
    bounce_type = bounce.get("bounceType", "")

    if bounce_type != "Permanent":
        logger.info(f"Ignoring transient bounce (type={bounce_type})")
        return 0

    recipients = bounce.get("bouncedRecipients", [])
    updated = 0

    for recipient in recipients:
        email = recipient.get("emailAddress", "").lower().strip()
        if not email:
            continue

        try:
            table.update_item(
                Key={"email": email},
                UpdateExpression="SET #s = :status",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":status": "bounced"},
            )
            logger.info(f"Marked as bounced: {_mask_email(email)}")
            updated += 1
        except Exception:
            logger.exception(f"Failed to update bounced subscriber: {_mask_email(email)}")

    return updated


def _handle_complaint(table, message: dict) -> int:
    """Handle SES complaint notification.

    Complaints (user clicked 'Report Spam') result in immediate
    unsubscription — required by AWS SES guidelines.
    """
    complaint = message.get("complaint", {})
    recipients = complaint.get("complainedRecipients", [])
    updated = 0

    for recipient in recipients:
        email = recipient.get("emailAddress", "").lower().strip()
        if not email:
            continue

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
            logger.info(f"Unsubscribed due to complaint: {_mask_email(email)}")
            updated += 1
        except Exception:
            logger.exception(f"Failed to update complained subscriber: {_mask_email(email)}")

    return updated

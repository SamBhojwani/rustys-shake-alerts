"""Email Stack — SES identity verification + bounce/complaint handling."""

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_ses as ses,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_logs as logs,
    aws_kms as kms,
)
from constructs import Construct


class EmailStack(Stack):
    """Provisions SES email identity and bounce/complaint handling pipeline."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        subscribers_table: dynamodb.Table,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── SES Email Identity ────────────────────────────────────────
        # Verifies the sender email address. After deployment, check
        # the inbox for a verification email from AWS and click the link.
        self.email_identity = ses.EmailIdentity(
            self,
            "SenderEmailIdentity",
            identity=ses.Identity.email("bryanrusties@gmail.com"),
        )

        # ── SNS Topic for Bounce/Complaint Notifications ─────────────
        self.notification_topic = sns.Topic(
            self,
            "SESNotificationTopic",
            topic_name="rusty-ses-notifications",
            display_name="Rusty's Shake SES Notifications",
            master_key=kms.Alias.from_alias_name(
                self, "SnsKmsKey", "alias/aws/sns"
            ),
        )

        # Wire SES notifications to the SNS topic
        # Note: SES → SNS notification configuration requires a
        # configuration set. We create one and attach it.
        config_set = ses.ConfigurationSet(
            self,
            "SESConfigSet",
            configuration_set_name="rusty-config-set",
        )

        # Add event destination for bounces and complaints
        ses.ConfigurationSetEventDestination(
            self,
            "BounceComplaintDestination",
            configuration_set=config_set,
            destination=ses.EventDestination.sns_topic(self.notification_topic),
            events=[
                ses.EmailSendingEvent.BOUNCE,
                ses.EmailSendingEvent.COMPLAINT,
            ],
        )

        # ── Bounce/Complaint Handler Lambda ──────────────────────────
        bounce_handler = lambda_.Function(
            self,
            "BounceHandlerFunction",
            function_name="rusty-bounce-handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambdas/bounce_handler"),
            timeout=Duration.seconds(30),
            memory_size=128,
            environment={
                "SUBSCRIBERS_TABLE": subscribers_table.table_name,
            },
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        # Grant the bounce handler permission to update subscribers
        subscribers_table.grant_read_write_data(bounce_handler)

        # Subscribe the Lambda to the SNS topic
        self.notification_topic.add_subscription(
            subs.LambdaSubscription(bounce_handler)
        )

        # ── Exports ──────────────────────────────────────────────────
        self.sender_email = "bryanrusties@gmail.com"
        self.config_set_name = config_set.configuration_set_name

        CfnOutput(self, "SenderEmail", value=self.sender_email)
        CfnOutput(
            self,
            "ConfigSetName",
            value=config_set.configuration_set_name,
        )
        CfnOutput(
            self,
            "NotificationTopicArn",
            value=self.notification_topic.topic_arn,
        )

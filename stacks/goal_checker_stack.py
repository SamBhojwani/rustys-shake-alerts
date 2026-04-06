"""Goal Checker Stack — Lambda function + EventBridge daily trigger."""

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_sqs as sqs,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class GoalCheckerStack(Stack):
    """Lambda that checks if Bryan Rust scored yesterday, triggered daily."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        subscribers_table: dynamodb.Table,
        goal_history_table: dynamodb.Table,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Dead Letter Queue ─────────────────────────────────────────
        dlq = sqs.Queue(
            self,
            "GoalCheckerDLQ",
            queue_name="rusty-goal-checker-dlq",
            retention_period=Duration.days(14),
        )

        # ── Goal Checker Lambda ───────────────────────────────────────
        self.goal_checker_fn = lambda_.Function(
            self,
            "GoalCheckerFunction",
            function_name="rusty-goal-checker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambdas/goal_checker"),
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={
                "PLAYER_ID": "8475825",
                "PLAYER_NAME": "Bryan Rust",
                "TEAM_ABBREV": "PIT",
                "SUBSCRIBERS_TABLE": subscribers_table.table_name,
                "GOAL_HISTORY_TABLE": goal_history_table.table_name,
                "SENDER_EMAIL": "",  # Set after SES email verification
                "INCLUDE_PLAYOFFS": "false",
            },
            dead_letter_queue=dlq,
            retry_attempts=2,
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        # ── IAM Permissions ───────────────────────────────────────────
        subscribers_table.grant_read_data(self.goal_checker_fn)
        goal_history_table.grant_read_write_data(self.goal_checker_fn)

        # SES send permission
        self.goal_checker_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "ses:SendEmail",
                    "ses:SendRawEmail",
                ],
                resources=["*"],
            )
        )

        # ── EventBridge Rule: 9 AM ET daily (14:00 UTC) ──────────────
        rule = events.Rule(
            self,
            "DailyGoalCheckRule",
            rule_name="rusty-daily-goal-check",
            schedule=events.Schedule.cron(
                minute="0",
                hour="14",
                month="*",
                week_day="*",
                year="*",
            ),
            description="Checks if Bryan Rust scored yesterday — runs 9 AM ET daily",
        )
        rule.add_target(targets.LambdaFunction(self.goal_checker_fn))

        # ── Outputs ───────────────────────────────────────────────────
        CfnOutput(
            self,
            "GoalCheckerFunctionArn",
            value=self.goal_checker_fn.function_arn,
        )
        CfnOutput(
            self,
            "GoalCheckerFunctionName",
            value=self.goal_checker_fn.function_name,
        )

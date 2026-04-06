"""Data Stack — DynamoDB tables for subscribers and goal history."""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_dynamodb as dynamodb,
)
from constructs import Construct


class DataStack(Stack):
    """Creates DynamoDB tables for the Rusty's Shake alert system."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Subscribers Table ──────────────────────────────────────────
        self.subscribers_table = dynamodb.Table(
            self,
            "SubscribersTable",
            table_name="rusty-subscribers",
            partition_key=dynamodb.Attribute(
                name="email",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True,
            ),
        )

        # GSI: query active subscribers efficiently for email blasts
        self.subscribers_table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(
                name="status",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ── Goal History Table ─────────────────────────────────────────
        self.goal_history_table = dynamodb.Table(
            self,
            "GoalHistoryTable",
            table_name="rusty-goal-history",
            partition_key=dynamodb.Attribute(
                name="game_date",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── Outputs ───────────────────────────────────────────────────
        CfnOutput(self, "SubscribersTableName",
                  value=self.subscribers_table.table_name)
        CfnOutput(self, "GoalHistoryTableName",
                  value=self.goal_history_table.table_name)

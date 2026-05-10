"""Goal Checker Stack — Lambda + EventBridge + API Gateway + Admin API."""

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    Fn,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_sqs as sqs,
    aws_dynamodb as dynamodb,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_logs as logs,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as integrations,
    aws_apigatewayv2_authorizers as authorizers,
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
        sender_email: str = "",
        config_set_name: str = "",
        user_pool: cognito.UserPool = None,
        user_pool_client: cognito.UserPoolClient = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Dead Letter Queue (encrypted) ─────────────────────────────
        dlq = sqs.Queue(
            self,
            "GoalCheckerDLQ",
            queue_name="rusty-goal-checker-dlq",
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
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
                "SENDER_EMAIL": sender_email,
                "INCLUDE_PLAYOFFS": "false",
                "SES_CONFIG_SET": config_set_name,
            },
            dead_letter_queue=dlq,
            retry_attempts=2,
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        # ── IAM Permissions ───────────────────────────────────────────
        subscribers_table.grant_read_data(self.goal_checker_fn)
        goal_history_table.grant_read_write_data(self.goal_checker_fn)

        # SES send permission — scoped to the verified sender identity only
        ses_identity_arn = Fn.sub(
            "arn:aws:ses:${AWS::Region}:${AWS::AccountId}:identity/"
            + sender_email
        ) if sender_email else "*"

        self.goal_checker_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "ses:SendEmail",
                    "ses:SendRawEmail",
                ],
                resources=[ses_identity_arn],
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

        # ── Unsubscribe Lambda ────────────────────────────────────────
        unsubscribe_fn = lambda_.Function(
            self,
            "UnsubscribeFunction",
            function_name="rusty-unsubscribe",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambdas/unsubscribe"),
            timeout=Duration.seconds(15),
            memory_size=128,
            environment={
                "SUBSCRIBERS_TABLE": subscribers_table.table_name,
            },
            log_retention=logs.RetentionDays.ONE_MONTH,
            # reserved_concurrent_executions intentionally omitted: account
            # has only 10 total concurrency, AWS requires 10 unreserved.
            # Re-add per-function caps after a Service Quotas increase.
        )

        # Grant unsubscribe Lambda access to subscribers table
        subscribers_table.grant_read_write_data(unsubscribe_fn)

        # ── Subscribe Lambda ──────────────────────────────────────────
        subscribe_fn = lambda_.Function(
            self,
            "SubscribeFunction",
            function_name="rusty-subscribe",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambdas/subscribe"),
            timeout=Duration.seconds(15),
            memory_size=128,
            environment={
                "SUBSCRIBERS_TABLE": subscribers_table.table_name,
                "SENDER_EMAIL": sender_email,
                "SES_CONFIG_SET": config_set_name,
                # API_BASE_URL is wired below via add_environment, after
                # the HttpApi construct exists.
                "TOKEN_EXPIRY_HOURS": "24",
            },
            log_retention=logs.RetentionDays.ONE_MONTH,
            # See note on UnsubscribeFunction; re-add after quota increase.
        )

        subscribers_table.grant_read_write_data(subscribe_fn)

        # Scoped SES permission for subscribe Lambda
        if sender_email:
            subscribe_ses_arn = Fn.sub(
                "arn:aws:ses:${AWS::Region}:${AWS::AccountId}:identity/"
                + sender_email
            )
            subscribe_fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["ses:SendEmail"],
                    resources=[subscribe_ses_arn],
                )
            )

        # ── Confirm Lambda ────────────────────────────────────────────
        confirm_fn = lambda_.Function(
            self,
            "ConfirmFunction",
            function_name="rusty-confirm",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambdas/confirm"),
            timeout=Duration.seconds(15),
            memory_size=128,
            environment={
                "SUBSCRIBERS_TABLE": subscribers_table.table_name,
            },
            log_retention=logs.RetentionDays.ONE_MONTH,
            # See note on UnsubscribeFunction; re-add after quota increase.
        )

        subscribers_table.grant_read_write_data(confirm_fn)

        # ── Admin API Lambda ───────────────────────────────────────────
        admin_fn = lambda_.Function(
            self,
            "AdminApiFunction",
            function_name="rusty-admin-api",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambdas/admin_api"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "SUBSCRIBERS_TABLE": subscribers_table.table_name,
                "GOAL_HISTORY_TABLE": goal_history_table.table_name,
                "SENDER_EMAIL": sender_email,
                "SES_CONFIG_SET": config_set_name,
                "GOAL_CHECKER_FUNCTION": self.goal_checker_fn.function_name,
            },
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        # Admin Lambda IAM — scoped permissions
        subscribers_table.grant_read_write_data(admin_fn)
        goal_history_table.grant_read_data(admin_fn)

        # SES send permission (for test emails)
        if sender_email:
            admin_ses_arn = Fn.sub(
                "arn:aws:ses:${AWS::Region}:${AWS::AccountId}:identity/"
                + sender_email
            )
            admin_fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["ses:SendEmail"],
                    resources=[admin_ses_arn],
                )
            )

        # Allow admin to invoke the goal checker Lambda
        self.goal_checker_fn.grant_invoke(admin_fn)

        # ── HTTP API Gateway (with throttling + CORS) ─────────────────
        self.http_api = apigw.HttpApi(
            self,
            "RustyHttpApi",
            api_name="rusty-api",
            description="Rusty's Shake public + admin API",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_origins=[
                    "http://localhost:5173",
                    "http://localhost:3000",
                    "http://127.0.0.1:5173",
                    "http://127.0.0.1:3000",
                    "https://dysdanp2wbnf9.cloudfront.net",
                ],
                allow_methods=[
                    apigw.CorsHttpMethod.GET,
                    apigw.CorsHttpMethod.POST,
                    apigw.CorsHttpMethod.DELETE,
                ],
                allow_headers=["Content-Type", "Authorization"],
                max_age=Duration.hours(1),
            ),
        )

        # Rate limiting to prevent abuse and cost spikes
        cfn_stage = self.http_api.default_stage.node.default_child
        cfn_stage.add_property_override(
            "DefaultRouteSettings.ThrottlingBurstLimit", 100
        )
        cfn_stage.add_property_override(
            "DefaultRouteSettings.ThrottlingRateLimit", 50
        )

        # API Gateway access logging — audit trail for all requests
        access_log_group = logs.LogGroup(
            self,
            "ApiAccessLogGroup",
            log_group_name="/aws/apigateway/rusty-api-access",
            retention=logs.RetentionDays.THREE_MONTHS,
        )
        cfn_stage.add_property_override(
            "AccessLogSettings.DestinationArn",
            access_log_group.log_group_arn,
        )
        cfn_stage.add_property_override(
            "AccessLogSettings.Format",
            '{"requestId":"$context.requestId","ip":"$context.identity.sourceIp",'
            '"method":"$context.httpMethod","path":"$context.path",'
            '"status":"$context.status","latency":"$context.responseLatency",'
            '"userAgent":"$context.identity.userAgent"}',
        )

        # Wire the API URL into the Subscribe Lambda so confirmation
        # emails contain valid links. Resolved at deploy time.
        subscribe_fn.add_environment(
            "API_BASE_URL", self.http_api.url or ""
        )

        # ── Public Routes (no auth) ───────────────────────────────────

        # GET /unsubscribe
        self.http_api.add_routes(
            path="/unsubscribe",
            methods=[apigw.HttpMethod.GET],
            integration=integrations.HttpLambdaIntegration(
                "UnsubscribeIntegration",
                unsubscribe_fn,
            ),
        )

        # POST /subscribe
        self.http_api.add_routes(
            path="/subscribe",
            methods=[apigw.HttpMethod.POST],
            integration=integrations.HttpLambdaIntegration(
                "SubscribeIntegration",
                subscribe_fn,
            ),
        )

        # GET /confirm
        self.http_api.add_routes(
            path="/confirm",
            methods=[apigw.HttpMethod.GET],
            integration=integrations.HttpLambdaIntegration(
                "ConfirmIntegration",
                confirm_fn,
            ),
        )

        # ── Admin Routes (JWT-protected) ──────────────────────────────
        admin_integration = integrations.HttpLambdaIntegration(
            "AdminApiIntegration",
            admin_fn,
        )

        # JWT Authorizer — Cognito
        jwt_authorizer = None
        if user_pool and user_pool_client:
            jwt_authorizer = authorizers.HttpJwtAuthorizer(
                "CognitoAuthorizer",
                jwt_issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}",
                jwt_audience=[user_pool_client.user_pool_client_id],
            )

        admin_routes = [
            ("/admin/subscribers", [apigw.HttpMethod.GET]),
            ("/admin/subscribers/stats", [apigw.HttpMethod.GET]),
            ("/admin/subscribers/{email}", [apigw.HttpMethod.DELETE]),
            ("/admin/goals", [apigw.HttpMethod.GET]),
            ("/admin/test-email", [apigw.HttpMethod.POST]),
            ("/admin/trigger-check", [apigw.HttpMethod.POST]),
        ]

        for path, methods in admin_routes:
            route_kwargs = {
                "path": path,
                "methods": methods,
                "integration": admin_integration,
            }
            if jwt_authorizer:
                route_kwargs["authorizer"] = jwt_authorizer
            self.http_api.add_routes(**route_kwargs)

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
        CfnOutput(
            self,
            "ApiUrl",
            value=self.http_api.url or "",
            description="Base URL of the public + admin API",
        )

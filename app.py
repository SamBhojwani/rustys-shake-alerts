#!/usr/bin/env python3
"""CDK entry point for Rusty's Shake Goal Alert System."""

import aws_cdk as cdk

from stacks.data_stack import DataStack
from stacks.email_stack import EmailStack
from stacks.auth_stack import AuthStack
from stacks.goal_checker_stack import GoalCheckerStack
from stacks.frontend_stack import FrontendStack


app = cdk.App()

env = cdk.Environment(region="us-east-1")

# --- Phase 1: Data Layer ---
data = DataStack(app, "RustyDataStack", env=env)

# --- Phase 2: Email (SES) ---
email = EmailStack(
    app,
    "RustyEmailStack",
    subscribers_table=data.subscribers_table,
    env=env,
)

# --- Phase 4: Authentication ---
auth = AuthStack(app, "RustyAuthStack", env=env)

# --- Phase 1-4: Goal Detection + Email + Admin API ---
goal_checker = GoalCheckerStack(
    app,
    "RustyGoalCheckerStack",
    subscribers_table=data.subscribers_table,
    goal_history_table=data.goal_history_table,
    sender_email=email.sender_email,
    config_set_name=email.config_set_name,
    user_pool=auth.user_pool,
    user_pool_client=auth.app_client,
    env=env,
)

# --- Phase 4: Frontend (S3 + CloudFront) ---
frontend = FrontendStack(
    app,
    "RustyFrontendStack",
    env=env,
)

app.synth()

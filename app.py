#!/usr/bin/env python3
"""CDK entry point for Rusty's Shake Goal Alert System."""

import aws_cdk as cdk

from stacks.data_stack import DataStack
from stacks.goal_checker_stack import GoalCheckerStack


app = cdk.App()

env = cdk.Environment(region="us-east-1")

# --- Phase 1: Data Layer + Goal Detection ---
data = DataStack(app, "RustyDataStack", env=env)

goal_checker = GoalCheckerStack(
    app,
    "RustyGoalCheckerStack",
    subscribers_table=data.subscribers_table,
    goal_history_table=data.goal_history_table,
    env=env,
)

# --- Phase 2: Email (SES) ---
# from stacks.email_stack import EmailStack
# email = EmailStack(app, "RustyEmailStack", env=env)

# --- Phase 3-4: API + Auth + Frontend ---
# from stacks.api_stack import ApiStack
# from stacks.auth_stack import AuthStack
# from stacks.frontend_stack import FrontendStack

app.synth()

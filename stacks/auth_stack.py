"""Auth Stack — Cognito User Pool for admin authentication."""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    CfnOutput,
    aws_cognito as cognito,
)
from constructs import Construct


class AuthStack(Stack):
    """Provisions Cognito User Pool with a single admin user."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Cognito User Pool ─────────────────────────────────────────
        self.user_pool = cognito.UserPool(
            self,
            "AdminUserPool",
            user_pool_name="rusty-admin-pool",
            self_sign_up_enabled=False,  # Admin-only — no public signup
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,  # NIST recommendation
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN,
            # Advanced Security — brute-force protection, compromised
            # credential detection, adaptive authentication
            advanced_security_mode=cognito.AdvancedSecurityMode.ENFORCED,
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(
                    required=True,
                    mutable=False,
                ),
            ),
        )

        # ── App Client (SPA — no secret) ─────────────────────────────
        self.app_client = self.user_pool.add_client(
            "AdminAppClient",
            user_pool_client_name="rusty-admin-client",
            generate_secret=False,  # Required for browser-based SPA auth
            auth_flows=cognito.AuthFlow(
                user_srp=True,  # Secure Remote Password (recommended)
                user_password=False,  # Disabled — SRP is more secure
            ),
            id_token_validity=Duration.hours(1),
            access_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(7),
            prevent_user_existence_errors=True,  # Don't reveal if user exists
        )

        # ── Admin User ────────────────────────────────────────────────
        # Single admin user — receives temporary password via email
        cognito.CfnUserPoolUser(
            self,
            "AdminUser",
            user_pool_id=self.user_pool.user_pool_id,
            username="bryanrusties@gmail.com",
            user_attributes=[
                cognito.CfnUserPoolUser.AttributeTypeProperty(
                    name="email",
                    value="bryanrusties@gmail.com",
                ),
                cognito.CfnUserPoolUser.AttributeTypeProperty(
                    name="email_verified",
                    value="true",
                ),
            ],
            desired_delivery_mediums=["EMAIL"],
        )

        # ── Outputs ──────────────────────────────────────────────────
        CfnOutput(
            self,
            "UserPoolId",
            value=self.user_pool.user_pool_id,
            description="Cognito User Pool ID",
        )
        CfnOutput(
            self,
            "UserPoolClientId",
            value=self.app_client.user_pool_client_id,
            description="Cognito App Client ID",
        )
        CfnOutput(
            self,
            "UserPoolRegion",
            value=self.region,
            description="Cognito User Pool Region",
        )

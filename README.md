# Rusty's Shake — Goal Alert System 🏒🥤

A serverless app that watches Pittsburgh Penguins forward **Bryan Rust**. Every time he scores a goal in a game, the next morning everyone on the subscriber list gets an email letting them know they can grab a half-price **"Rusty's Shake"** at The Milkshake Factory that day.

**Live demo:** [admin dashboard](https://dysdanp2wbnf9.cloudfront.net) · subscribe form runs locally for now (see below)

---

## What it does, in plain English

1. Fans sign up by entering their name + email on the subscribe page.
2. They get a confirmation email and click a link to verify they own the address.
3. Once a day, a small program wakes up and asks the NHL's public API whether Bryan Rust played and scored yesterday.
4. If he did, every confirmed subscriber gets an email about the deal.
5. Subscribers can unsubscribe with one click from any email.
6. An admin dashboard (login required) shows the subscriber list, recent goals, and lets the admin send test emails or trigger a manual check.

Everything runs on AWS — no servers to manage, costs only fractions of a cent per email.

---

## Architecture

```
                                  ┌──────────────────┐
                                  │  Public NHL API  │
                                  └─────────▲────────┘
                                            │
   ┌──────────────────┐    ┌────────────────┴────────────┐    ┌───────────────┐
   │ Daily 9 AM ET    │───▶│      Goal Checker (Lambda)  │───▶│ DynamoDB      │
   │ EventBridge cron │    │  Did Rust score yesterday?  │    │ goal history  │
   └──────────────────┘    └────────────────┬────────────┘    └───────────────┘
                                            │ yes
                                            ▼
                                  ┌──────────────────┐
                                  │  Amazon SES      │───▶ subscribers' inboxes
                                  └─────────▲────────┘
                                            │
   ┌──────────────────┐    ┌────────────────┴────────────┐    ┌───────────────┐
   │ Subscribe form   │───▶│  Subscribe / Confirm /      │◀──▶│ DynamoDB      │
   │ (static HTML)    │    │  Unsubscribe (3 x Lambda)   │    │ subscribers   │
   └──────────────────┘    └─────────────────────────────┘    └───────────────┘

   ┌──────────────────┐    ┌─────────────────────────────┐
   │ Admin dashboard  │───▶│  Admin API (Lambda)         │  ◀── Cognito login (JWT)
   │ (React on        │    │  list / delete / stats /    │
   │  CloudFront)     │    │  send test / trigger check  │
   └──────────────────┘    └─────────────────────────────┘
```

All five pieces are defined in code as CDK stacks — one command deploys the whole system.

---

## Tech stack

| Layer | What I used |
|---|---|
| **Infrastructure** | AWS CDK (Python), CloudFormation |
| **Compute** | AWS Lambda (Python 3.12) — 6 functions total |
| **API** | API Gateway HTTP API with JWT auth + rate limiting |
| **Auth** | Amazon Cognito User Pool |
| **Storage** | DynamoDB (with a Global Secondary Index for subscriber status) |
| **Email** | Amazon SES with bounce/complaint handling via SNS → Lambda |
| **Frontend** | React + Vite (admin dashboard), vanilla HTML (subscribe form) |
| **Hosting** | S3 + CloudFront, with HTTPS + HSTS |
| **Encryption** | Customer-managed KMS key for SNS notifications |
| **Scheduling** | EventBridge cron rule |
| **CI-friendly** | pytest test suite for the goal-detection logic |

---

## Features worth pointing out

- **Email verification (double opt-in).** A subscriber isn't added to the active list until they click a one-time link in their inbox. Tokens expire after 24 hours.
- **Bounce + complaint handling.** If an email bounces or someone marks it as spam, an automated process flags that subscriber so we never email them again. Helps keep sender reputation healthy.
- **Idempotent.** If the daily job runs twice for the same game, it only sends one round of emails. Tracked in a dedicated history table.
- **Anti-abuse.** API Gateway is rate-limited to cap costs. The subscribe endpoint returns the same response whether the email is new, taken, or invalid — so it can't be used to probe whether someone is already on the list.
- **Cost-aware.** Everything is pay-per-use serverless. The whole system costs ~$0 when idle and pennies per thousand emails sent.
- **Test mode.** The goal checker accepts an optional "mock game" payload so I can verify the full pipeline end-to-end without waiting for a real Penguins game.
- **One-command deploy.** `cdk deploy --all` provisions every piece of infrastructure, IAM role, environment variable, and DNS-friendly URL from scratch.

---

## Project structure

```
.
├── app.py                          # CDK entry point — wires the 5 stacks
├── stacks/
│   ├── data_stack.py               # DynamoDB tables
│   ├── auth_stack.py               # Cognito user pool + app client
│   ├── email_stack.py              # SES identity + bounce pipeline + CMK
│   ├── goal_checker_stack.py       # Lambdas + HTTP API + EventBridge
│   └── frontend_stack.py           # S3 + CloudFront for admin dashboard
├── lambdas/
│   ├── subscribe/                  # POST /subscribe handler
│   ├── confirm/                    # GET /confirm?token=... handler
│   ├── unsubscribe/                # GET /unsubscribe?token=... handler
│   ├── goal_checker/               # Daily check + NHL API client
│   ├── admin_api/                  # Cognito-protected admin endpoints
│   └── bounce_handler/             # SES → SNS bounce/complaint processor
├── frontend/
│   ├── admin/                      # React + Vite admin dashboard
│   └── subscribe/                  # Public subscribe page (static HTML)
├── templates/                      # HTML email templates
└── tests/                          # pytest unit tests
```

---

## Running it locally

```bash
# 1. Set up Python env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Run the tests
pytest tests/ -v

# 3. Synthesize the CloudFormation templates (no AWS calls)
cdk synth

# 4. Serve the subscribe form locally
cd frontend/subscribe && python3 -m http.server 3000
# then open http://localhost:3000
```

## Deploying

```bash
# Assumes AWS credentials are configured for the target account
cdk bootstrap   # one-time per account/region
cdk deploy --all
```

After the first deploy, verify the sender email address in the SES console (one click on the link AWS sends). That's the only manual step.

---

## What I'd do next

If this were going to handle real volume:

- Move from a `@gmail.com` sender address to a verified domain (with SPF/DKIM/DMARC) so emails consistently land in inboxes instead of Spam.
- Apply for SES production access (currently in sandbox — limited to verified test addresses).
- Add per-Lambda reserved concurrency once the account's default Lambda quota is raised.
- Add structured CloudWatch dashboards + alarms for bounces/complaints over a threshold.
- Add a subscribe-page CDN host (currently the admin dashboard is on CloudFront, but the subscribe form is local-only).

---

## License

MIT — see [LICENSE](LICENSE).

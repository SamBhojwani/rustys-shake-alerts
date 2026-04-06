# Rusty's Shake — Goal Alert System 🏒🥤

A serverless AWS system that monitors Pittsburgh Penguins player **Bryan Rust's** game performance. The morning after he scores a goal, it sends a promotional email to subscribers about The Milkshake Factory's half-price **"Rusty's Shake"** deal.

## Architecture

- **AWS Lambda** (Python 3.12) — Goal detection + email sending
- **Amazon EventBridge** — Daily 9 AM ET trigger
- **Amazon DynamoDB** — Subscriber list + goal history
- **Amazon SES** — Transactional email
- **AWS CDK** — Infrastructure as Code

## Quick Start

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Synthesize CloudFormation
cdk synth

# 4. Deploy (requires configured AWS CLI)
cdk deploy --all
```

## Project Structure

```
├── app.py                  # CDK entry point
├── cdk.json                # CDK config
├── stacks/                 # CDK stack definitions
│   ├── data_stack.py       # DynamoDB tables
│   └── goal_checker_stack.py  # Lambda + EventBridge
├── lambdas/                # Lambda function code
│   └── goal_checker/
│       ├── handler.py      # Main handler
│       └── nhl_api.py      # NHL API client
└── tests/
    └── unit/               # pytest unit tests
```

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Configuration

Key settings are in Lambda environment variables (configured in `goal_checker_stack.py`):

| Variable | Default | Description |
|---|---|---|
| `PLAYER_ID` | `8475825` | Bryan Rust's NHL player ID |
| `SENDER_EMAIL` | _(empty)_ | Verified SES sender email |
| `INCLUDE_PLAYOFFS` | `false` | Set to `true` to also track playoff goals |

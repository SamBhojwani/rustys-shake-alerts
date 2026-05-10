# Software Requirements Specification (SRS)

## Rusty's Shake — Goal Alert System 🏒🥤

| Field | Value |
|---|---|
| **Project** | Rusty's Shake Goal Alert System |
| **Version** | 1.0 |
| **Date** | 2026-04-30 |
| **Status** | Phase 1 Complete (Data Layer + Goal Detection) |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Overall Description](#2-overall-description)
3. [System Architecture](#3-system-architecture)
4. [Functional Requirements](#4-functional-requirements)
5. [Data Requirements](#5-data-requirements)
6. [External Interface Requirements](#6-external-interface-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [Constraints & Assumptions](#8-constraints--assumptions)
9. [Future Phases](#9-future-phases)
10. [Appendices](#10-appendices)

---

## 1. Introduction

### 1.1 Purpose

This document defines the software requirements for **Rusty's Shake Goal Alert System** — a serverless AWS application that monitors Pittsburgh Penguins player **Bryan Rust's** game performance via the NHL API. When Rust scores a goal, the system sends a promotional email to subscribers advertising The Milkshake Factory's half-price **"Rusty's Shake"** deal.

### 1.2 Scope

The system encompasses:

- Automated daily goal detection via the NHL public API
- Subscriber management with double opt-in confirmation
- Transactional email delivery through Amazon SES
- Goal history tracking and idempotent processing
- Infrastructure-as-Code via AWS CDK (Python)

### 1.3 Definitions & Acronyms

| Term | Definition |
|---|---|
| CDK | AWS Cloud Development Kit |
| SES | Amazon Simple Email Service |
| DLQ | Dead Letter Queue |
| GSI | Global Secondary Index |
| ET | Eastern Time (America/New_York) |
| NHL API | Public API at `api-web.nhle.com/v1` |

### 1.4 References

- NHL Public API: `https://api-web.nhle.com/v1`
- Bryan Rust Player ID: `8475825`
- AWS CDK v2.180.0
- Python 3.12 Runtime

---

## 2. Overall Description

### 2.1 Product Perspective

The system runs entirely on AWS serverless infrastructure with no persistent servers. It is triggered on a daily schedule and interacts with external NHL APIs to determine game outcomes.

### 2.2 User Classes

| User Class | Description |
|---|---|
| **Subscriber** | End user who opts in to receive goal alert emails |
| **Administrator** | Manages subscriber lists, monitors system health (Phase 3+) |

### 2.3 Operating Environment

- **Cloud Provider**: AWS (us-east-1)
- **Runtime**: Python 3.12 on AWS Lambda
- **IaC**: AWS CDK v2.180.0
- **CI/CD**: Manual deployment via `cdk deploy --all`

### 2.4 Development Phases

| Phase | Scope | Status |
|---|---|---|
| **Phase 1** | Data Layer + Goal Detection | ✅ Complete |
| **Phase 2** | Email (SES integration) | 🔲 Planned |
| **Phase 3** | API + Auth + Admin Dashboard | 🔲 Planned |
| **Phase 4** | Frontend (subscriber signup) | 🔲 Planned |

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌──────────────────┐     ┌──────────────────────┐
│  Amazon           │────▶│  Lambda: rusty-       │
│  EventBridge      │     │  goal-checker         │
│  (Daily 9 AM ET)  │     │  (Python 3.12)        │
└──────────────────┘     └──────┬───────┬────────┘
                                │       │
                    ┌───────────┘       └────────────┐
                    ▼                                ▼
          ┌─────────────────┐              ┌─────────────────┐
          │ NHL Public API  │              │ Amazon SES      │
          │ (api-web.nhle)  │              │ (Email sending) │
          └─────────────────┘              └─────────────────┘
                                                    │
                    ┌───────────────────────────────┘
                    ▼
          ┌─────────────────┐    ┌─────────────────────┐
          │ DynamoDB:       │    │ DynamoDB:            │
          │ rusty-          │    │ rusty-goal-          │
          │ subscribers     │    │ history              │
          └─────────────────┘    └─────────────────────┘
```

### 3.2 CDK Stack Structure

| Stack | Resource | Purpose |
|---|---|---|
| `RustyDataStack` | DynamoDB Tables | Subscribers + Goal History |
| `RustyGoalCheckerStack` | Lambda, EventBridge, SQS DLQ | Goal detection + scheduling |

### 3.3 Project File Structure

```
├── app.py                        # CDK entry point
├── cdk.json                      # CDK config + player context
├── requirements.txt              # Python dependencies
├── stacks/
│   ├── data_stack.py             # DynamoDB table definitions
│   └── goal_checker_stack.py     # Lambda + EventBridge + DLQ
├── lambdas/
│   └── goal_checker/
│       ├── handler.py            # Main Lambda handler
│       └── nhl_api.py            # NHL API client
└── tests/
    └── unit/
        ├── test_handler.py       # Handler unit tests
        └── test_nhl_api.py       # NHL API client tests
```

---

## 4. Functional Requirements

### 4.1 Goal Detection (FR-100)

| ID | Requirement | Priority |
|---|---|---|
| FR-101 | The system SHALL check if Bryan Rust (Player ID `8475825`) played an NHL game on the previous day (Eastern Time). | High |
| FR-102 | The system SHALL query the NHL API game log endpoint (`/player/{id}/game-log/{season}/{gameType}`) to retrieve scoring data. | High |
| FR-103 | The system SHALL automatically determine the current NHL season string (e.g., `20252026`) based on the current date, using October as the season start boundary. | High |
| FR-104 | The system SHALL support both regular season (game type `2`) and playoff (game type `3`) game detection, controlled by the `INCLUDE_PLAYOFFS` configuration flag. | Medium |
| FR-105 | When playoff checking is enabled, the system SHALL check regular season games first, returning the first match found. | Medium |
| FR-106 | The system SHALL extract opponent abbreviation from the NHL API response, handling both string and dict (`{"default": "WSH"}`) formats. | High |
| FR-107 | The system SHALL return `None` when no game is found for the target date. | High |
| FR-108 | The system SHALL gracefully handle NHL API failures (HTTP errors, timeouts, connection errors) by logging the error and continuing to the next game type. | High |

### 4.2 Email Notification (FR-200)

| ID | Requirement | Priority |
|---|---|---|
| FR-201 | When Bryan Rust scores ≥1 goal, the system SHALL send an email to all active, confirmed subscribers. | High |
| FR-202 | The email SHALL contain: player name, number of goals scored, opponent team, game date, and a CTA link to The Milkshake Factory. | High |
| FR-203 | The email SHALL be sent in both HTML and plain-text formats. | High |
| FR-204 | The HTML email SHALL use Penguins-branded styling (gold `#FCB514`, dark theme `#1a1a2e`/`#16213e`). | Medium |
| FR-205 | Each email SHALL include an unsubscribe link with the subscriber's confirmation token. | High |
| FR-206 | The email subject SHALL include an emoji (🏒), the player name, goal count, and the deal announcement. | Low |
| FR-207 | If `SENDER_EMAIL` is not configured, the system SHALL log an error and skip email sending (returning 0 sent). | High |
| FR-208 | Individual email send failures SHALL be caught and logged without stopping the remaining sends. | High |

### 4.3 Idempotency & History (FR-300)

| ID | Requirement | Priority |
|---|---|---|
| FR-301 | Before sending emails, the system SHALL check the Goal History table to determine if emails were already sent for the given game date. | High |
| FR-302 | If emails have already been sent (`emails_sent > 0` for that `game_date`), the system SHALL skip re-sending and return "Already processed". | High |
| FR-303 | After processing a game (goal or no goal), the system SHALL log the event to the Goal History table with: `game_date`, `game_id`, `goals`, `assists`, `opponent`, `game_type`, `emails_sent`, `sent_at`. | High |
| FR-304 | If no game is found, the system SHALL NOT write any record to the Goal History table. | Medium |

### 4.4 Subscriber Management (FR-400)

| ID | Requirement | Priority |
|---|---|---|
| FR-401 | The system SHALL query subscribers using the `status-index` GSI, filtering for `status = "active"`. | High |
| FR-402 | Only subscribers with `confirmed = true` SHALL receive emails. | High |
| FR-403 | The subscriber query SHALL handle DynamoDB pagination (`LastEvaluatedKey`). | High |
| FR-404 | If no active/confirmed subscribers exist, the system SHALL log the goal event but skip email sending. | Medium |

### 4.5 Scheduling (FR-500)

| ID | Requirement | Priority |
|---|---|---|
| FR-501 | The system SHALL be triggered daily at 9:00 AM ET (14:00 UTC) via Amazon EventBridge. | High |
| FR-502 | The EventBridge rule SHALL run every day of the week, year-round. | High |

---

## 5. Data Requirements

### 5.1 Subscribers Table (`rusty-subscribers`)

| Attribute | Type | Key | Description |
|---|---|---|---|
| `email` | String | Partition Key | Subscriber's email address |
| `status` | String | GSI Partition Key (`status-index`) | `active`, `inactive`, `pending` |
| `name` | String | — | Subscriber display name |
| `confirmed` | Boolean | — | Double opt-in confirmation flag |
| `confirmation_token` | String | — | Token for unsubscribe links |

**Configuration:**
- Billing: Pay-per-request (on-demand)
- Removal Policy: RETAIN (data preserved on stack deletion)
- Point-in-Time Recovery: Enabled
- GSI `status-index`: Projects ALL attributes

### 5.2 Goal History Table (`rusty-goal-history`)

| Attribute | Type | Key | Description |
|---|---|---|---|
| `game_date` | String | Partition Key | ISO date `YYYY-MM-DD` |
| `game_id` | Number | — | NHL game ID |
| `goals` | Number | — | Goals scored (0 if none) |
| `assists` | Number | — | Assists recorded |
| `opponent` | String | — | Opponent team abbreviation |
| `game_type` | String | — | `regular_season` or `playoffs` |
| `emails_sent` | Number | — | Count of emails sent |
| `sent_at` | String | — | ISO timestamp of processing |

**Configuration:**
- Billing: Pay-per-request (on-demand)
- Removal Policy: RETAIN

---

## 6. External Interface Requirements

### 6.1 NHL API

| Property | Value |
|---|---|
| Base URL | `https://api-web.nhle.com/v1` |
| Auth | None (public API) |
| Endpoint | `/player/{playerId}/game-log/{season}/{gameType}` |
| User-Agent | `RustyShakeAlert/1.0` |
| Timeout | 15 seconds |
| Response Format | JSON |

**Response Structure (game log entry):**
```json
{
  "gameId": 2025020950,
  "teamAbbrev": {"default": "PIT"},
  "gameDate": "2026-04-05",
  "goals": 2,
  "assists": 1,
  "opponentAbbrev": {"default": "WSH"}
}
```

### 6.2 Amazon SES

| Property | Value |
|---|---|
| Action | `ses:SendEmail`, `ses:SendRawEmail` |
| Permission Scope | `*` (all SES resources) |
| Sender | Configured via `SENDER_EMAIL` env var (must be SES-verified) |

### 6.3 Amazon DynamoDB

| Property | Value |
|---|---|
| Access Pattern | Read subscribers (GSI query), Read/Write goal history |
| Permissions | `grant_read_data` (subscribers), `grant_read_write_data` (goal history) |

---

## 7. Non-Functional Requirements

### 7.1 Performance

| ID | Requirement |
|---|---|
| NFR-101 | Lambda execution SHALL complete within 60 seconds (configured timeout). |
| NFR-102 | Lambda memory allocation SHALL be 256 MB. |
| NFR-103 | NHL API requests SHALL timeout after 15 seconds. |

### 7.2 Reliability

| ID | Requirement |
|---|---|
| NFR-201 | Failed Lambda invocations SHALL be retried up to 2 times. |
| NFR-202 | After all retries are exhausted, the event SHALL be sent to the SQS Dead Letter Queue (`rusty-goal-checker-dlq`). |
| NFR-203 | DLQ messages SHALL be retained for 14 days. |
| NFR-204 | The system SHALL be idempotent — duplicate invocations for the same game date SHALL NOT produce duplicate emails. |

### 7.3 Observability

| ID | Requirement |
|---|---|
| NFR-301 | Lambda logs SHALL be retained in CloudWatch for 1 month (`ONE_MONTH`). |
| NFR-302 | The system SHALL log: invocation events, game check results, subscriber counts, and email send results. |
| NFR-303 | Email send failures SHALL be logged at `EXCEPTION` level with full traceback. |

### 7.4 Data Protection

| ID | Requirement |
|---|---|
| NFR-401 | Both DynamoDB tables SHALL use `RETAIN` removal policy to prevent accidental data loss. |
| NFR-402 | The Subscribers table SHALL have Point-in-Time Recovery enabled. |

### 7.5 Maintainability

| ID | Requirement |
|---|---|
| NFR-501 | All infrastructure SHALL be defined as code using AWS CDK (Python). |
| NFR-502 | The system SHALL have unit test coverage for the Lambda handler and NHL API client. |
| NFR-503 | Tests SHALL run via `pytest tests/ -v`. |

---

## 8. Constraints & Assumptions

### 8.1 Constraints

- The NHL public API requires no authentication but may be rate-limited or change without notice.
- Amazon SES requires sender email verification before emails can be sent.
- The system is deployed to `us-east-1` only.
- Lambda uses only Python standard library + boto3 (no additional pip packages in the Lambda bundle).

### 8.2 Assumptions

- The NHL season runs roughly October through June; the season string calculation assumes this schedule.
- Bryan Rust's NHL Player ID (`8475825`) remains stable across seasons.
- EventBridge cron at 14:00 UTC corresponds to 9:00 AM ET (EST) / 10:00 AM ET (EDT). DST is handled at the application level for date calculations.
- Subscribers are managed externally (direct DynamoDB writes) until Phase 3/4 APIs are built.

---

## 9. Future Phases

### Phase 2 — Email (SES)

- Dedicated `EmailStack` CDK construct
- HTML email templates loaded from file (replacing inline HTML)
- SES domain verification and production access

### Phase 3 — API + Auth

- `ApiStack` — API Gateway REST endpoints for subscriber management
- `AuthStack` — Cognito-based admin authentication
- Admin dashboard (React) for managing subscribers and viewing goal history

### Phase 4 — Frontend

- `FrontendStack` — S3 + CloudFront hosted subscriber signup page
- Double opt-in confirmation flow via API
- Public-facing unsubscribe endpoint

---

## 10. Appendices

### 10.1 Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `PLAYER_ID` | `8475825` | No | NHL player ID to monitor |
| `PLAYER_NAME` | `Bryan Rust` | No | Display name for emails |
| `TEAM_ABBREV` | `PIT` | No | Team abbreviation |
| `SUBSCRIBERS_TABLE` | `rusty-subscribers` | Yes | DynamoDB subscriber table name |
| `GOAL_HISTORY_TABLE` | `rusty-goal-history` | Yes | DynamoDB goal history table name |
| `SENDER_EMAIL` | _(empty)_ | Yes* | SES-verified sender email (*required for email sending) |
| `INCLUDE_PLAYOFFS` | `false` | No | Enable playoff goal detection |

### 10.2 Dependencies

| Package | Version | Purpose |
|---|---|---|
| `aws-cdk-lib` | 2.180.0 | Infrastructure as Code |
| `constructs` | ≥10.0.0, <11.0.0 | CDK construct library |
| `boto3` | ≥1.34 | AWS SDK (Lambda runtime) |
| `pytest` | ≥7.0 | Unit testing |
| `moto` | ≥5.0 | AWS service mocking for tests |

### 10.3 Test Coverage Summary

| Test Suite | Tests | Coverage |
|---|---|---|
| `test_handler.py` | 5 tests | Handler flow: no game, no goals, goals → email, idempotency, no subscribers |
| `test_nhl_api.py` | 11 tests | Season calc, abbreviation parsing, goal detection, API failures, playoff logic |

---

*End of Document*

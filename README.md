# ESET Alert Monitor

A local FastAPI operations portal for parsing ESET Microsoft 365 / Outlook email notifications, scoring endpoint risk, preserving historical alert context, and sending controlled Microsoft Teams escalations.

The project is designed for teams that receive ESET security notifications by email and need a lightweight way to turn those messages into searchable alert history, client-aware severity scoring, and low-noise Teams notifications.

**GitHub description:** FastAPI dashboard for parsing ESET Microsoft 365 alert emails, scoring endpoint risk, storing alert history, and sending throttled Microsoft Teams escalations.

## What It Does

ESET Alert Monitor connects to a Microsoft 365 mailbox through Microsoft Graph, reads matching ESET notification emails, extracts alert fields, stores historical events in SQLite, and evaluates each alert against configurable severity and escalation logic.

The application focuses on reducing Teams noise. Alerts are recorded historically, but Teams escalation is intentionally gated so the channel receives only meaningful Critical events, capped to the first Critical alert per client in a rolling 24-hour window.

## Key Features

- Microsoft Graph OAuth / app credential mailbox access
- No Outlook basic authentication or mailbox password storage
- Recursive folder scanning when no folder filter is configured
- Historical backfill with dashboard presets from Today through 5 years
- SQLite-backed alert, event, scan, and escalation history
- Configurable ESET sender and subject filters
- ESET alert body parsing for hostname, user, threat, severity, action, status, IP, OS, and raw email body
- Configurable severity scoring model with taxonomy weights and contextual adjustments
- Dashboard metric filters for total alerts, Critical clients, repeated threats, unresolved cases, and escalations
- Alert detail pages with parsed fields, raw email body, escalation context, and historical matches
- Teams webhook delivery with local preview mode
- Encrypted local storage for sensitive settings
- Background polling while the web app is running
- CLI scanner for scheduled or manual execution

## Architecture

```text
Microsoft 365 mailbox
        |
        v
Microsoft Graph API
        |
        v
ESET email parser
        |
        v
SQLite history store
        |
        v
Severity scoring + escalation policy
        |
        v
Microsoft Teams webhook
```

Main modules:

- `app/main.py` starts FastAPI, mounts routes/static assets, and runs the polling loop.
- `app/graph_client.py` authenticates with Microsoft Graph and reads mailbox messages.
- `app/parser.py` extracts structured ESET fields from email bodies.
- `app/scoring.py` computes configurable 0-100 severity scores.
- `app/rules.py` applies Teams escalation throttling.
- `app/storage.py` stores configuration, alerts, events, and state in SQLite.
- `app/security.py` encrypts stored secrets with a local Fernet key.
- `app/teams_notifier.py` posts Teams webhook payloads.
- `app/scanner.py` runs mailbox scans from the web app or CLI.

## Requirements

- Python 3.11 or newer recommended
- Microsoft 365 mailbox that receives ESET alert emails
- Azure App Registration with Microsoft Graph permissions
- Optional Microsoft Teams Incoming Webhook or Teams Workflow webhook

Python dependencies are listed in `requirements.txt`.

## Quick Start

```powershell
git clone <your-repo-url>
cd ESET_alert_script

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
uvicorn app.main:app --reload
```

Open:

```text
http://localhost:8000
```

For another local port:

```powershell
uvicorn app.main:app --host localhost --port 8010
```

If you change ports, add the matching redirect URI in Azure, for example:

```text
http://localhost:8010/auth/callback
```

## Azure App Registration

1. Open Azure Portal.
2. Go to **Microsoft Entra ID**.
3. Create or open an **App registration**.
4. Copy the **Tenant ID** and **Client ID**.
5. Add a web redirect URI:

```text
http://localhost:8000/auth/callback
```

6. Add Microsoft Graph delegated permissions:

```text
User.Read
Mail.Read
offline_access
```

7. For unattended app credential scanning, also configure:

```text
Application permission: Mail.Read
```

8. Grant admin consent if required by your tenant.

This application does not use basic Outlook username/password authentication.

## Mailbox Access Modes

### Microsoft Sign-In

Use this for local testing or when a user account has access to the notifications mailbox.

1. Open the dashboard.
2. Enter the Tenant ID and Client ID.
3. Optionally enter the notifications mailbox address.
4. Leave the folder blank to scan every folder Graph exposes.
5. Click **Save and sign in with Microsoft**.

After sign-in, the dashboard scans automatically.

### App Credentials

Use this for unattended production polling. Configure Tenant ID, Client ID, Client Secret, and mailbox address through the Configure page or `.env`.

For shared mailboxes, the app registration must be allowed to read that mailbox. In production environments, consider using an Exchange application access policy to scope Graph access to only the mailbox or mail-enabled security group required by this app.

## Environment Variables

Copy `.env.example` to `.env` and set values as needed:

```dotenv
APP_DATABASE_PATH=./data/eset_alerts.db
APP_SECRET_KEY_PATH=./data/secret.key
APP_LOG_PATH=./logs/app.log
APP_POLL_INTERVAL_SECONDS=60

GRAPH_TENANT_ID=
GRAPH_CLIENT_ID=
GRAPH_CLIENT_SECRET=
GRAPH_MAILBOX_ADDRESS=
GRAPH_MAIL_FOLDER=
TEAMS_WEBHOOK_URL=
```

Values in `.env` override saved UI settings where applicable.

## Teams Delivery

Create a Teams Incoming Webhook or Teams Workflow webhook for the target channel, then paste the webhook URL into **Configure**.

The app sends Teams messages only when escalation policy allows it. By default, Teams alert posting can remain in local preview mode while testing. When local preview is enabled, the app records the Teams payload locally but does not post to the channel.

Teams escalation policy:

- Only Critical severity alerts are eligible for Teams.
- Teams posts are capped to the first Critical alert per client in a rolling 24-hour window.
- Client identity uses ESET client name, then hostname, then computer name.
- Non-escalated alerts remain in SQLite for dashboard history and investigation.

## Severity Scoring

Severity is configurable from the **Configure** page.

The scoring model is:

```text
final score = taxonomy base score
            + repeat / spread / persistence / velocity adjustments
            + failure or unresolved adjustment
            - successful containment discount
```

## TODO

- Align the settings page command bar and card spacing exactly with the dashboard layout.
- Ensure the Configure page header, button placement, and card spacing match the Dashboard experience.
- Confirm unsaved settings warnings behave consistently before navigating away.

Scores are clamped from `0` to `100`, then mapped to severity buckets:

- Critical
- High
- Medium
- Low

Configurable scoring inputs include:

- ESET taxonomy keyword scores
- Unknown threat base score
- Critical / High / Medium thresholds
- Same-host repeat event adjustments
- Same-threat multi-endpoint spread adjustments
- Multi-day persistence adjustments
- Velocity spike adjustments
- Host alert volume adjustments
- Failed or unresolved remediation adjustment
- Successful containment discount

Saving Configure automatically re-scores historical alerts so dashboard metrics reflect the current model.

## Dashboard

The dashboard provides:

- Total parsed alerts
- Critical clients
- Repeated threats
- Unresolved cases
- 24-hour Critical escalations
- Recent alerts table
- Clickable escalation feed
- Alert detail pages with raw email body and historical matches
- Date presets: Today, 7d, 30d, 60d, 90d, 6mo, 1yr, 2yr, 5yr

Selecting a date range backfills missing historical coverage when needed, then filters the dashboard to that range.

## Running the Scanner

Run one scan from the CLI:

```powershell
python -m app.scanner
```

Run sample local data without Graph:

```powershell
python -m app.scanner --sample
```

The scanner processes each unique Graph `message_id` only once.

## Running 24/7

For simple Windows deployment, run the FastAPI app continuously. The app starts a background polling task on startup.

Production-style command:

```powershell
cd C:\path\to\ESET_alert_script
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Set the polling interval in `.env`:

```dotenv
APP_POLL_INTERVAL_SECONDS=60
```

On Windows, use Task Scheduler:

- Trigger: at startup or at log on
- Program: `C:\path\to\ESET_alert_script\.venv\Scripts\python.exe`
- Arguments: `-m uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Start in: `C:\path\to\ESET_alert_script`
- Enable restart-on-failure behavior where possible

For server deployment, run under a process supervisor such as NSSM, systemd, Docker, or a managed VM service.

## Customizing the Parser

Parser regex patterns live in `app/parser.py`.

Each field maps to one or more regex patterns. Add patterns that capture the value in group 1:

```python
"hostname": [
    r"Host(?:name)?:\s*(.+)",
    r"Device name:\s*(.+)",
]
```

Keep parser changes focused and test with representative ESET notification bodies before running a large backfill.

## Data Storage

SQLite stores:

- Non-sensitive settings
- Parsed alerts
- Raw email body
- Scanner state and coverage
- Event logs
- Teams message history
- Escalation fingerprints

Default database path:

```text
data/eset_alerts.db
```

Sensitive values are encrypted before storage using:

```text
data/secret.key
```

If the key is deleted, encrypted values in SQLite cannot be recovered.

## Security Notes

- Do not commit `.env`, `data/`, `logs/`, SQLite databases, or encryption keys.
- `.gitignore` already excludes local secrets, databases, logs, virtual environments, and runtime files.
- Do not use raw mailbox passwords.
- Prefer Microsoft Graph OAuth or app credentials.
- Teams webhook URLs are secrets and should be treated like credentials.
- Stored client secrets and Teams webhook URLs are encrypted locally.
- Secrets are masked in the UI.
- Avoid posting real customer or endpoint data in public issues or screenshots.

## Troubleshooting

### Microsoft sign-in does not start

Check Tenant ID, Client ID, and redirect URI. Azure web redirect URIs must use `http://localhost` for local HTTP redirects, not `http://127.0.0.1`.

### `Could not acquire Graph token`

Verify the Azure App Registration, tenant, client ID, client secret, redirect URI, permissions, and admin consent.

### `403 Forbidden`

Confirm `Mail.Read` permissions and that the account or app has access to the mailbox.

### No messages are found

Check:

- Mailbox address
- Folder filter
- Sender filter
- Subject filter
- Date range selected in the dashboard
- Whether ESET notifications are in hidden or nested folders

Leave folder blank to scan every folder Graph returns.

### Teams accepts webhook but no channel message appears

If the app receives a successful `202` response but no message appears, check the Teams Workflow run history. The webhook trigger may be firing, but the workflow may not be posting the payload to the desired channel.

### Dashboard numbers changed after saving Configure

This is expected. Saving Configure re-scores historical alerts using the current severity model.

## Project Structure

```text
README.md
requirements.txt
.env.example

app/
  main.py
  config.py
  logger.py
  models.py
  database.py
  graph_client.py
  parser.py
  scoring.py
  storage.py
  rules.py
  teams_notifier.py
  scanner.py
  security.py

app/routes/
  dashboard.py
  settings.py
  alerts.py
  actions.py
  auth.py

app/templates/
  base.html
  dashboard.html
  settings.html
  alert_detail.html

app/static/
  style.css
  app.js
```

## Publication Checklist

Before publishing to GitHub:

- Remove real `.env` files.
- Remove `data/`, `logs/`, `.uvicorn.pid`, and local SQLite files.
- Confirm no screenshots include customer names, usernames, hostnames, webhook URLs, tenant IDs, or client IDs.
- Add a license if you intend others to reuse the project.
- Consider adding sanitized screenshots under a dedicated `docs/` or `assets/` folder.

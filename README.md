# ESET & Acronis Alert Monitor

A local FastAPI operations portal that monitors both ESET endpoint security email notifications and Acronis Cyber Protect Cloud backup alerts from a shared Microsoft 365 mailbox. It scores endpoint risk, preserves historical alert context, and sends controlled Microsoft Teams escalations.

The project is designed for teams that receive ESET and Acronis notifications by email and need a lightweight way to turn those messages into searchable alert history, client-aware severity scoring, and low-noise Teams notifications.

---

## What It Does

The monitor connects to a Microsoft 365 mailbox through Microsoft Graph, reads matching notification emails, extracts alert fields, stores historical events in SQLite, and evaluates each ESET alert against a configurable severity and escalation model.

It focuses on reducing Teams noise. Alerts are recorded historically, but Teams escalation is intentionally gated so the channel receives only meaningful Critical events, capped to the first Critical alert per client in a rolling 24-hour window.

---

## Key Features

- Microsoft Graph OAuth / app credential mailbox access
- No Outlook basic authentication or mailbox password storage
- Recursive folder scanning when no folder filter is configured
- Historical backfill with dashboard presets from Today through 1 year
- SQLite-backed alert, event, scan, and escalation history
- Separate ESET and Acronis dashboards with a shared switcher
- Configurable ESET sender and subject filters
- Configurable Acronis sender and subject filters (stored independently)
- ESET alert body parsing for hostname, user, threat, severity, action, status, IP, OS, and raw email body
- Acronis alert parsing for device, plan, group, account, and severity
- Configurable severity scoring model with taxonomy base scores plus recurrence, spread, persistence, velocity, host volume, and remediation outcome
- JSON API endpoints for dashboard, alert detail, settings, and scoring preview
- Dashboard metric filters for total alerts, Critical clients, repeated threats, unresolved cases, and escalations
- Alert detail pages with parsed fields, raw email body, escalation context, and historical matches
- Teams webhook delivery with local preview mode
- Encrypted local storage for sensitive settings
- Background polling while the web app is running
- CLI scanner for scheduled or manual execution

---

## Architecture

```text
Microsoft 365 mailbox
        |
        v
Microsoft Graph API
        |
        v
  ESET parser       Acronis parser
        |                  |
        v                  v
      SQLite history store
              |
              v
   Severity scoring + escalation policy
              |
              v
   Microsoft Teams webhook
```

Main modules:

- `app/main.py` — starts FastAPI, mounts routes and static assets, runs the polling loop
- `app/graph_client.py` — authenticates with Microsoft Graph and reads mailbox messages
- `app/parser.py` — extracts structured ESET fields from email bodies
- `app/scoring.py` — computes configurable 0–100 severity scores
- `app/rules.py` — applies Teams escalation throttling
- `app/storage.py` — stores configuration, alerts, events, and state in SQLite
- `app/security.py` — encrypts stored secrets with a local Fernet key
- `app/teams_notifier.py` — posts Teams webhook payloads
- `app/scanner.py` — runs mailbox scans from the web app or CLI

---

## Severity Scoring — Full Algorithm

The scoring engine lives in `app/scoring.py`. Scores run from 0 to 100 and are bucketed into four severity labels. The algorithm has three distinct stages: base score, contextual adjustments, and the unresolved override.

### Stage 1 — Base Score

Every alert starts from a base score derived from its threat name.

**Mode A: Equal base score (default)**

When taxonomy weighting is off, every threat starts from the same configurable base score (`unknown_base_score`, default `30`). Contextual signals — not the threat name — drive the final score. This is the recommended mode when you want recurrence and containment failure to dominate severity.

**Mode B: Taxonomy weighting**

When taxonomy weighting is on, the engine compares the part of the threat name after the last `/` (case-insensitive) against a keyword table. Each row in the table is `keyword = score`. The engine searches for whole-word matches and returns the score for the first keyword that matches.

Matching is longest-keyword-first so a more specific compound term beats a broad term. For example `riskware` (score 25) would not accidentally match before `backdoor` (score 90) on a name like `Win32/Backdoor.Agent`.

If no keyword matches, the threat falls back to `unknown_base_score`.

Default taxonomy (all values configurable from the Configure page):

| Keyword | Score |
|---|---|
| ransomware | 97 |
| rootkit | 95 |
| backdoor | 90 |
| rat | 90 |
| keylogger | 85 |
| psw | 82 |
| spy | 80 |
| stealer / infostealer | 80 |
| exploit | 78 |
| worm | 76 |
| trojan | 74 |
| phishing | 72 |
| dropper | 70 |
| cryptominer | 60 |
| downloader | 55 |
| injector | 52 |
| obfuscated | 45 |
| packed | 40 |
| redirector | 38 |
| riskware | 25 |
| pua | 18 |
| adware | 15 |
| cookie | 8 |

---

### Stage 2 — Contextual Adjustments

The engine then queries the existing alert history in SQLite and adds or subtracts adjustment points based on six signals. All windows and point values are configurable from the Configure page. Adjustments stack additively.

#### 2a. Same-host, same-threat repetition

The engine counts how many prior alerts for the same threat name on the same host exist within the configured repeat window (default: 24 hours).

| Prior occurrences in window | Adjustment (default) |
|---|---|
| 1 (total of 2) | +20 |
| 2 (total of 3) | +40 |
| 3+ (total of 4+) | +60 |

This catches persistent infections that antivirus keeps seeing but has not fully resolved on a single machine.

#### 2b. Same-threat, multi-endpoint spread (campaign detection)

The engine counts how many distinct hostnames have seen the same threat name within the configured campaign window (default: 24 hours).

| Distinct endpoints in window | Adjustment (default) |
|---|---|
| 2 | +8 |
| 3–4 | +18 |
| 5+ | +30 |

This detects lateral movement or a propagating infection spreading across the environment.

#### 2c. Persistence across days

The engine counts how many distinct calendar days the same threat has appeared on the same host across all time (not just the repeat window).

| Distinct days seen | Adjustment (default) |
|---|---|
| 2–3 days | +10 |
| 4+ days | +20 |

A threat returning on separate days suggests the malware is surviving reboots or scheduled scans, indicating incomplete remediation.

#### 2d. Velocity spike

The engine compares two rates for the same threat name:

- **Recent rate** — alerts per hour within the velocity window (default: last 6 hours)
- **Baseline rate** — alerts per hour during the baseline period that precedes the campaign window (default: 7 days back, excluding the last 24 hours)

If `recent_rate > baseline_rate × velocity_multiplier` (default multiplier: 5×) **and** the raw count in the velocity window meets the minimum count threshold (default: 3 alerts), the velocity adjustment is added.

| Condition met | Adjustment (default) |
|---|---|
| Spike detected | +10 |

This catches sudden surges for a known threat that was previously quiet, which can indicate a new campaign or worm spread wave.

#### 2e. Host alert volume

The engine counts all alerts from the same hostname within the host alert window (default: 24 hours), regardless of threat type.

| Alerts on host in window | Adjustment (default) |
|---|---|
| ≥ threshold (default: 10) | +10 |

A machine generating an unusually high volume of diverse alerts may be heavily compromised or the target of an active attack.

#### 2f. Remediation outcome

The engine reads the combined action_taken, containment_status, and resolved_status fields.

**Failure/unresolved patterns** (any of the following in any field):
`failed`, `failure`, `unresolved`, `not resolved`, `not cleaned`, `unable to clean/remove/delete/quarantine/resolve`, `action required`, `remediation failed/required`

**Success patterns** (any of the following, only when no failure is present):
`cleaned`, `deleted`, `resolved`, `quarantined`, `removed`, `blocked`, `terminated`, `contained`

| Outcome | Adjustment (default) |
|---|---|
| Failed or unresolved | +20 |
| Successfully contained | −20 |

Successfully contained alerts get a score reduction because antivirus handled the threat. Failed or unresolved alerts get an increase because the machine is still exposed.

---

### Stage 3 — Unresolved Hard Override

After all adjustments are calculated, the engine applies a final check:

> If the remediation outcome is **failed or unresolved**, the final score is forced directly to **100**, bypassing the normal 0–100 clamp and overriding whatever the base + contextual sum would have been.

This means a low-category threat (e.g. adware with base score 15) that antivirus could not remove is treated as Critical, because an active unresolved infection is operationally critical regardless of threat type.

If the outcome is not failed, the score is clamped to the range `[0, 100]`.

---

### Stage 4 — Severity Bucket

The clamped score is mapped to a label using three configurable thresholds:

| Score | Label (default thresholds) |
|---|---|
| ≥ 95 | Critical |
| ≥ 70 | High |
| ≥ 45 | Medium |
| < 45 | Low |

Thresholds are validated so Critical > High > Medium. The Configure page prevents saving an invalid threshold order.

---

### Full Scoring Formula

```text
base_score              (taxonomy keyword match, or unknown_base_score)

+ same_host_repeat      (up to +60 if same threat seen 3+ times on same host in window)
+ campaign_spread       (up to +30 if same threat on 5+ endpoints in window)
+ persistence           (up to +20 if same threat on same host on 4+ separate days)
+ velocity_spike        (+10 if recent alert rate > 5× baseline and count ≥ 3)
+ host_volume           (+10 if host has ≥ 10 alerts in window)
+ failure_adjustment    (+20 if action failed or threat unresolved)
- success_adjustment    (−20 if threat was cleaned/quarantined/blocked)

= adjusted_score        (clamped to 0–100)

IF unresolved_override: final = 100
ELSE:                   final = adjusted_score

→ severity_label        (Critical / High / Medium / Low by thresholds)
```

---

### Worked Example

A threat `Win32/Backdoor.Agent` arrives on `HOST-01`.

1. **Base score (taxonomy mode on):** keyword `backdoor` matches → base = **90**
2. **Same host repeat:** same threat seen once on HOST-01 in the last 24h → +20
3. **Campaign spread:** only 1 endpoint so far → +0
4. **Persistence:** only seen today (1 distinct day) → +0
5. **Velocity:** 2 recent alerts, below minimum count of 3 → +0
6. **Host volume:** HOST-01 has 7 alerts in 24h, below threshold of 10 → +0
7. **Remediation:** action_taken = "Remediation failed" → **unresolved override**
8. **Override fires:** final score = **100** → **Critical**

Same scenario without the failed remediation (action_taken = "Quarantined"):
- Score = 90 + 20 − 20 = **90** → **High** (below the Critical threshold of 95)

---

### Re-scoring on Save

Every time settings are saved, the engine re-scores every alert stored in SQLite using the current configuration. This means changing any scoring parameter — including thresholds, taxonomy, or adjustment values — will immediately update all historical severity labels. Dashboard metric counts reflect the re-scored results.

---

## Escalation Policy

Escalation logic lives in `app/rules.py`.

After scoring, the escalation engine decides whether to send a Teams notification:

1. **Unresolved/failed override** — if the remediation outcome is failed or unresolved, escalate regardless of score.
2. **Critical severity** — if the scored severity label is Critical, escalate.
3. **Everything else** — no escalation.

For eligible alerts, escalation is further gated by a **cooldown fingerprint**:

- Each alert generates a fingerprint based on client identity (client name, then hostname, then computer name) and the configured cooldown window.
- If a Teams notification was already sent for the same client within the cooldown period (default: 24 hours), the alert is suppressed from Teams.
- This prevents the Teams channel from being flooded when a single machine generates many Critical alerts in quick succession.

Non-escalated alerts are still stored in SQLite and visible on the dashboard. They are not silently dropped.

---

## Acronis Monitor

The Acronis dashboard (`/acronis`) connects to the same Microsoft 365 mailbox and displays Acronis Cyber Protect Cloud backup alerts parsed from email notifications. It has its own configuration page (`/acronis/settings`) with independent sender/subject filters and a separate taxonomy textarea. Azure credentials, the mailbox address, and the Teams webhook are shared between both monitors.

Acronis alert severity categories (Critical, Error, Warning, Information) come directly from Acronis notification content rather than the ESET scoring engine.

---

## Requirements

- Python 3.11 or newer recommended
- Microsoft 365 mailbox that receives ESET and/or Acronis alert emails
- Azure App Registration with Microsoft Graph permissions
- Optional Microsoft Teams Incoming Webhook or Teams Workflow webhook

Python dependencies are listed in `requirements.txt`.

---

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

If you change ports, add the matching redirect URI in Azure:

```text
http://localhost:8010/auth/callback
```

---

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

---

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

---

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

---

## Teams Delivery

Create a Teams Incoming Webhook or Teams Workflow webhook for the target channel, then paste the webhook URL into **Configure**.

The app sends Teams messages only when escalation policy allows it. By default, Teams alert posting remains in local preview mode while testing. When local preview is enabled, the app records the Teams payload locally but does not post to the channel.

Teams escalation policy:

- Critical severity alerts are eligible for Teams.
- Failed or unresolved remediation forces Critical severity and is eligible for Teams.
- Teams posts are capped per client during the configured escalation cooldown.
- Client identity uses ESET client name, then hostname, then computer name.
- Non-escalated alerts remain in SQLite for dashboard history and investigation.

---

## Dashboard

The ESET dashboard provides:

- Total parsed alerts
- Critical clients
- Repeated threats
- Unresolved cases
- 24-hour Critical escalations
- Recent alerts table
- Clickable escalation feed
- Alert detail pages with raw email body and historical matches
- Date presets: Today, 7d, 30d, 60d, 90d, 6mo, 1yr

The Acronis dashboard provides:

- Critical / Error / Warning / Information counts
- Backup alert table with device, plan, group, account, and severity

Switch between dashboards using the dropdown in the top-left nav.

---

## Frontend / Backend API

The UI is served by FastAPI/Jinja templates. The backend also exposes JSON endpoints:

```text
GET  /api/dashboard
GET  /api/alerts/{alert_id}
GET  /api/settings
POST /api/scoring-preview
```

---

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

---

## Running 24/7

For simple Windows deployment:

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

---

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

---

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

---

## Security Notes

- Do not commit `.env`, `data/`, `logs/`, SQLite databases, or encryption keys.
- `.gitignore` already excludes local secrets, databases, logs, virtual environments, and runtime files.
- Do not use raw mailbox passwords.
- Prefer Microsoft Graph OAuth or app credentials.
- Teams webhook URLs are secrets and should be treated like credentials.
- Stored client secrets and Teams webhook URLs are encrypted locally.
- Secrets are masked in the UI.
- Avoid posting real customer or endpoint data in public issues or screenshots.

---

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
- Whether notifications are in hidden or nested folders

Leave folder blank to scan every folder Graph returns.

### Teams accepts webhook but no channel message appears

If the app receives a successful `202` response but no message appears, check the Teams Workflow run history. The webhook trigger may be firing, but the workflow may not be posting the payload to the desired channel.

### Dashboard numbers changed after saving Configure

This is expected. Saving Configure re-scores historical alerts using the current severity model.

---

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
  api.py
  settings.py
  acronis.py
  acronis_settings.py
  alerts.py
  actions.py
  auth.py

app/templates/
  base.html
  dashboard.html
  settings.html
  acronis_dashboard.html
  acronis_settings.html
  alert_detail.html

app/static/
  style.css
  app.js
```

---

## Publication Checklist

Before publishing to GitHub:

- Remove real `.env` files.
- Remove `data/`, `logs/`, `.uvicorn.pid`, and local SQLite files.
- Confirm no screenshots include customer names, usernames, hostnames, webhook URLs, tenant IDs, or client IDs.
- Add a license if you intend others to reuse the project. MIT is a practical default for permissive internal tooling; keep it private or use a proprietary notice if you do not want reuse.
- Consider adding sanitized screenshots under a dedicated `docs/` or `assets/` folder.

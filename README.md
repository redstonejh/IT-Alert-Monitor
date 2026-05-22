# IT Alert Monitor

A local FastAPI operations portal that monitors ESET endpoint security email notifications, Acronis Cyber Protect Cloud backup alerts, and Xymon infrastructure notifications from Microsoft 365 mailboxes. It scores endpoint risk, preserves historical alert context, and sends controlled Microsoft Teams escalations.

The project is designed for teams that receive operational notifications by email and need a lightweight way to turn those messages into searchable alert history, client-aware severity scoring, and low-noise Teams notifications.

---

## What It Does

The monitor connects to Microsoft 365 mailboxes through Microsoft Graph, reads matching notification emails, stores historical events in SQLite, and evaluates ESET and Acronis alerts against configurable severity and escalation models.

It focuses on reducing Teams noise. Alerts are recorded historically, but Teams escalation is intentionally gated so the channel receives only meaningful Critical events, capped to the first Critical alert per client in a rolling 24-hour window.

Acronis parsing is enabled for daily status report and active-alert notification emails. Xymon still provides the shared mailbox connection, range backfill, sync status, and Alerts/Escalations layout, but Xymon parsing remains disabled until production notification samples are finalized.

---

## Key Features

- Microsoft Graph OAuth / app credential mailbox access
- No Outlook basic authentication or mailbox password storage
- Recursive folder scanning when no folder filter is configured
- Historical backfill with dashboard presets from Today through 1 year
- SQLite-backed alert, event, scan, and escalation history
- Separate ESET, Acronis, and Xymon dashboards with a shared switcher
- Configurable ESET sender and subject filters
- Configurable Acronis sender and subject filters (stored independently)
- Configurable Xymon sender and subject filters (stored independently)
- ESET alert body parsing for hostname, user, threat, severity, action, status, IP, OS, and raw email body
- Acronis alert parsing for report date, company/group/account, machine/device, backup outcome, reason, and vendor status
- Company abbreviation lookup from `app/company_abbreviations.csv`, shared by dashboards and Teams payloads
- Xymon mailbox sync shell with parsing disabled until sample emails are available
- Configurable severity scoring model with taxonomy base scores plus recurrence, spread, persistence, velocity, host volume, and remediation outcome
- Acronis derived severity model that down-weights stale/offline noise and transient restarts while prioritizing storage, repository, capacity, auth/license, agent/service, and spread evidence
- JSON API endpoints for dashboard, alert detail, settings, and scoring preview
- Dashboard metric filters for total alerts, Critical clients, repeated threats, unresolved cases, and escalations
- Global dashboard search across visible alert fields, date presets, and compact custom range control
- Collapsible Analytics, Alerts, and Escalations panels with shared visual behavior
- Dark mode with screenshot-stable rendering, explicit scrollbars, and higher contrast panel hierarchy
- Alert detail pages with parsed fields, raw email body, escalation context, and historical matches
- Teams webhook delivery with local preview mode
- Encrypted local storage for sensitive settings
- Background polling while the web app is running
- CLI scanner for scheduled or manual execution

---

## Recent Dashboard UX Updates

The dashboard now includes a shared widget and panel layout system across ESET, Acronis, and Xymon views:

- Live `+` panel and widget creation without refreshing the page or resetting the current layout
- Movable, resizable, pinnable, renameable, recolorable, and deletable dashboard widgets
- Movable, resizable, pinnable, renameable, recolorable, and deletable dashboard panels
- Smooth resize and drag interactions, with widgets and panels snapping back to equal 12-column spacing intervals when released
- Layout save/load slots for preserving different dashboard arrangements
- A Default control that resets only the current dashboard and active layout profile
- Draft-only layout edits until Save is clicked, with Undo support for recent layout changes
- Small pinned-state indicator dots on locked panels and widgets
- Time filters are now a full-width widget with the same layout tools and no-refresh filtering behavior
- Metric widget clicks update dashboard filters in place without a full browser refresh
- Dashboard-wide keyword search that behaves like a panel-aware Control-F, filtering visible rows/cards across panels and expanding matching panels
- Collapsible Analytics, Alerts, and Escalations panels with consistent header controls and count behavior
- Polished top-bar controls for mailbox status, sync health, theme mode, configuration, disconnect, layout slots, and custom panel/widget actions
- Mailbox and sync popovers that show connection health, Graph credential checks, Teams webhook status, sync cadence, and last sync time
- Light/dark mode styling refinements, including improved contrast, panel/widget layering, theme-aware menu styling, z-index handling, and screenshot-stable UI rendering
- Company acronym hover titles and global overflow tooltips for truncated values

These changes preserve the existing dashboard visual system while making the dashboards more configurable for daily operations.

---

## Architecture

```text
Microsoft 365 mailbox
        |
        v
Microsoft Graph API
        |
        v
  ESET parser       Acronis parser           Xymon sync shell
        |                  |                       |
        v                  v                       v
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
- `app/acronis_parser.py` — extracts Acronis alert rows from daily status and active-alert emails
- `app/acronis_scanner.py` — scans the Acronis mailbox, stores parsed alerts, tracks coverage, and applies Acronis Teams gating
- `app/xymon_scanner.py` — scans the Xymon mailbox, tracks coverage, and currently skips parsing
- `app/xymon_parser.py` — parser scaffold for future Xymon notification samples
- `app/scoring.py` — computes configurable 0–100 severity scores
- `app/rules.py` — applies Teams escalation throttling
- `app/storage.py` — stores configuration, alerts, events, and state in SQLite
- `app/company_abbreviations.py` — resolves client/company display acronyms from CSV
- `app/security.py` — encrypts stored secrets with a local Fernet key
- `app/teams_notifier.py` — posts Teams webhook payloads
- `app/scanner.py` — runs ESET mailbox scans from the web app or CLI

---

## ESET Severity Scoring — Full Algorithm

The scoring engine lives in `app/scoring.py`. Scores run from 0 to 100 and are bucketed into four severity labels. The algorithm has three distinct stages: base score, contextual adjustments, and hard overrides for unresolved or persistent repeat patterns.

### Stage 1 — Base Score

Every alert starts from a base score derived from its threat name.

**Mode A: Equal base score**

When taxonomy weighting is off, every threat starts from the same configurable base score (`unknown_base_score`, default `30`). Contextual signals — not the threat name — drive the final score. This is the recommended mode when you want recurrence and containment failure to dominate severity.

**Mode B: Taxonomy weighting (default)**

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

### Stage 3 — Hard Overrides

After all adjustments are calculated, the engine applies final checks that can force Critical severity:

1. If the remediation outcome is **failed or unresolved**, the final score is forced directly to **100**, bypassing the normal 0–100 clamp and overriding whatever the base + contextual sum would have been.
2. If the same threat reaches the repeat threshold on the same host across multiple days within a 7-day cluster, the final score is also forced to **100**.

This means a low-category threat that antivirus could not remove is treated as Critical, because an active unresolved infection is operationally critical regardless of threat type. It also means clustered repeat activity, such as the same packed script appearing on the same endpoint across multiple days in a week, is treated as Critical even if individual detections were terminated.

The repeat override is intentionally clustered to a 7-day window. Older, spaced-out detections can still raise the score through persistence, but they do not automatically become Critical just because the same user or machine has historical phishing noise.

If no override fires, the score is clamped to the range `[0, 100]`.

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

IF unresolved_override:        final = 100
ELSE IF repeat_cluster_override: final = 100
ELSE:                          final = adjusted_score

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
2. **Persistent repeat override** — if the same threat crosses the repeat threshold on the same host across multiple days within 7 days, escalate as Critical.
3. **Critical severity** — if the scored severity label is Critical, escalate.
4. **Everything else** — no escalation.

For eligible alerts, escalation is further gated by a **cooldown fingerprint**:

- Each alert generates a fingerprint based on client identity (client name, then hostname, then computer name) and the configured cooldown window.
- If a Teams notification was already sent for the same client within the cooldown period (default: 24 hours), the alert is suppressed from Teams.
- This prevents the Teams channel from being flooded when a single machine generates many Critical alerts in quick succession.

Non-escalated alerts are still stored in SQLite and visible on the dashboard. They are not silently dropped.

---

## Acronis Monitor

The Acronis dashboard (`/acronis`) connects to a Microsoft 365 mailbox and uses the same date preset/backfill behavior as ESET. It has its own configuration page (`/acronis/settings`) with independent mailbox, folder, sender, and subject filters.

The parser reads Acronis daily status report and active-alert email content into dashboard rows with:

- Received (PT)
- Company
- Machine
- Backup (`Fail` / `Pass`)
- Reason
- Derived Severity

The vendor labels (Critical, Error, Warning, Information) are preserved as input evidence, but the visible dashboard severity is derived from a separate Acronis triage model. That model is intentionally designed to reduce noise:

- Storage, disk health, repository, capacity, auth/license, agent/service, server-like assets, new patterns, and spread across machines increase severity.
- Operating system restarts, closed backup windows, stale workstation offline alerts, repeated unchanged patterns, successful/info cases, and long-running offline endpoints reduce severity.
- Critical Acronis cases are eligible for Teams only when the push gate passes.
- Teams messages are capped to one message per company/machine in a 24-hour period.

This is separate from the ESET malware scoring model. Acronis status is operational evidence, not a direct Teams trigger.

---

## Xymon Monitor

The Xymon dashboard (`/xymon`) connects to a Microsoft 365 mailbox and uses the same date preset/backfill behavior as ESET. It has its own configuration page (`/xymon/settings`) with independent mailbox, folder, sender, subject, host, test, and status filters.

The dashboard currently shows the same shared Alerts and Escalations panel structure, but Xymon parsing is disabled until notification output and routing are finalized. The sync layer still validates mailbox access, scans configured ranges, records last-scan state, and polls in the background.

`app/xymon_parser.py` is present as a scaffold for future Xymon email parsing once sample messages are available.

---

## Requirements

- Python 3.11 or newer recommended
- Microsoft 365 mailbox that receives ESET, Acronis, and/or Xymon alert emails
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

Use this for local testing or when a user account has access to the notifications mailbox. ESET, Acronis, and Xymon can all use the same signed-in Microsoft token cache when their monitor-specific auth mode is delegated.

1. Open the dashboard.
2. Enter the Tenant ID and Client ID.
3. Optionally enter the notifications mailbox address.
4. Leave the folder blank to scan every folder Graph exposes.
5. Click **Save and sign in with Microsoft**.

After sign-in, the dashboard scans automatically.

If the app shows a mailbox as connected but Acronis or Xymon reports that Microsoft sign-in is needed, open ESET Configure (`/settings`) and use **Sign in with Microsoft** in the Microsoft Graph section to recreate the local OAuth token cache.

### App Credentials

Use this for unattended production polling. Configure Tenant ID, Client ID, Client Secret, and mailbox address through the Configure page or `.env`.

For shared mailboxes, the app registration must be allowed to read that mailbox. In production environments, consider using an Exchange application access policy to scope Graph access to only the mailbox or mail-enabled security group required by this app.

If Acronis or Xymon is switched to app-credential access and Graph returns `403 Forbidden` while reading `/users/<mailbox>/mailFolders`, the saved IDs and secret may be valid but the Azure app identity is not authorized to read that mailbox. Add Microsoft Graph application permission `Mail.Read`, grant admin consent, and check any Exchange Application Access Policy.

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
- Clustered same-host, same-threat ESET repeats can force Critical when they cross the threshold across multiple days within 7 days.
- Acronis Critical derived severity can post to Teams only after the Acronis push gate passes.
- Teams posts are capped per client during the configured escalation cooldown.
- Acronis Teams posts are capped per company/machine for 24 hours.
- Client identity uses ESET client name, then hostname, then computer name.
- Non-escalated alerts remain in SQLite for dashboard history and investigation.

---

## Dashboard

All dashboards share the same visual system:

- Large dashboard switcher in the top toolbar with hover-open menu
- Connected mailbox and sync status panels
- Light/dark theme toggle with screenshot-stable rendering
- Date presets, compact custom date-range picker, and global search
- Tactile hover states on toolbar panels, stat cards, headers, and rows
- Collapsible Analytics, Alerts, and Escalations sections with matching chevron/count styling
- Truncated values expose the full value on hover via native titles

Design choices are deliberately conservative: the dashboards reuse one panel, table, badge, filter, and toolbar language instead of inventing alert-type-specific UI. Each tab changes labels and data mapping, not the visual grammar.

The ESET dashboard provides:

- Total parsed alerts
- Critical clients
- Repeated threats
- Unresolved cases
- 24-hour Critical escalations
- Collapsible analytics for severity mix, trend, top methods, and top companies
- Recent alerts table
- Clickable escalation feed
- Alert detail pages with raw email body and historical matches
- Table layout: Received (PT), Company, User, Machine, Method, Status, Severity
- Method is a short readable label such as Phishing, Redirect, Packed, or Downloader; hovering reveals the full threat name
- Date presets: Today, 7d, 30d, 60d, 90d, 6mo, 1yr

The Acronis dashboard provides:

- Critical / Error / Warning / Information vendor status counts on the stat cards
- Acronis-derived severity in the Alerts table
- Parsed daily status report rows with company abbreviations, machine, backup result, and reason
- Clickable severity badges that show score calculation details
- Acronis severity help popover and full scoring controls on Configure
- Push Review / Escalations panel for Teams-eligible Critical Acronis cases
- Date presets: Today, 7d, 30d, 60d, 90d, 6mo, 1yr
- Mailbox sync status and scan coverage tracking

The Xymon dashboard provides:

- Red / Yellow / Purple / Green status counts
- Date presets: Today, 7d, 30d, 60d, 90d, 6mo, 1yr
- Mailbox sync status and scan coverage tracking
- Shared Alerts and Escalations panels while parsing remains disabled

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

Acronis and Xymon run their own background scanners while the web app is running. Acronis parses and stores supported backup alert emails. Xymon currently validates mailbox access and updates scan state, but parsing/storage remains disabled until notification samples and routing are finalized.

All three monitors poll every `APP_POLL_INTERVAL_SECONDS` seconds while the FastAPI app is running. The default is 60 seconds.

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
  acronis_parser.py
  scoring.py
  storage.py
  rules.py
  teams_notifier.py
  scanner.py
  security.py
  company_abbreviations.py
  company_abbreviations.csv

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
  acronis_alert_detail.html
  xymon_dashboard.html

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

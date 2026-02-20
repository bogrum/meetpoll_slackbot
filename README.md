# MeetPoll - Slack Meeting Poll Bot

A self-hosted Slack bot for meeting scheduling polls, event management with RSVPs, and automated new member onboarding. Uses Socket Mode (no public URL required) and SQLite for storage. Perfect for Raspberry Pi deployment.

## Features

### Polls
- `/meetpoll` slash command to create polls
- Support for 5-25 time slot options
- Checkbox-based multi-select voting
- Real-time vote counting with transparency (shows who voted)
- Manual or automatic poll closing
- Detailed results view

### Events
- `/event create` to create events with a modal form
- `/event list` to see upcoming events
- Going / Maybe / Not Going RSVP buttons
- Optional max attendee limit (rejects Going when full)
- Automatic 24h and 1h reminders via DM to RSVPed users
- Auto-close events after their scheduled time

### New Member Onboarding
- Periodically checks a Google Sheet registration form for new entries
- Sends bilingual (Turkish/English) welcome emails with Slack invite link
- On `team_join`, auto-adds members to their selected committee channels
- Sends welcome DM with committee info
- `/onboard` command for managing the system (status, mappings, manual runs)
- First-run safety: `/onboard seed` to import existing members without emailing them

### Outreach Emails
- `/outreach academics` — compose personalized emails to academic contacts from a Google Sheet
- `/outreach clubs` — compose personalized emails to student clubs from a Google Sheet
- Auto-prepended greetings: "Sayın {Ad Soyad} Hocam," for academics, "Sevgili {Kulüp Adı}," for clubs
- Preview with 3 sample emails before confirming send
- Rate-limited background sending (2.5s between emails, Pi-friendly)
- Resumable campaigns — each recipient tracked individually
- `/outreach status` — aggregate statistics
- `/outreach history` — recent campaigns with expandable details

### Google Groups Auto-Add
- When a new member is onboarded, automatically adds them to a Google Group via Admin SDK
- Requires domain-wide delegation (DWD) configured in Google Workspace Admin Console
- Idempotent — members already in the group are silently skipped
- Retry logic: members who missed group-add (e.g. during downtime) are retried on next registration check
- If `GOOGLE_GROUP_EMAIL` is not set, this feature is silently skipped

### Bioinformatics RSS Opportunity Feed
- Fetches [jobrxiv.org](https://jobrxiv.org) and [opportunitydesk.org](https://opportunitydesk.org) twice daily (10:00 and 22:00)
- Filters entries by bioinformatics-related keywords (genomics, sequencing, omics, ML, etc.)
- New items are queued and posted at random times within the 10:00–22:00 window
- Maximum 5 posts per calendar day, preventing channel spam
- Each posted item is tracked by GUID — never posted twice
- Posts to the channel configured via `JOBS_CHANNEL_ID`

## Prerequisites

- Python 3.8+
- A Slack workspace where you have admin permissions
- A Google Cloud project with Sheets API enabled (free, no billing required)
- A Gmail account with 2-Step Verification and an App Password

---

## Part 1: Create the Slack App

### Step 1: Create a New App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"**
3. Choose **"From scratch"**
4. Enter app name: `MeetPoll`
5. Select your workspace
6. Click **"Create App"**

### Step 2: Enable Socket Mode

Socket Mode allows your bot to connect without a public URL.

1. In the left sidebar, click **"Socket Mode"**
2. Toggle **"Enable Socket Mode"** to ON
3. When prompted, create an App-Level Token:
   - Token Name: `meetpoll-socket`
   - Scope: `connections:write`
4. Click **"Generate"**
5. **Copy and save the token** (starts with `xapp-`) - you'll need this later

### Step 3: Add Bot Scopes

1. In the left sidebar, click **"OAuth & Permissions"**
2. Scroll to **"Scopes"** section
3. Under **"Bot Token Scopes"**, add these scopes:
   - `commands` - For slash commands
   - `chat:write` - To post messages
   - `chat:write.public` - To post in channels the bot hasn't joined
   - `users:read` - To read user profiles
   - `users:read.email` - To match new members by email
   - `channels:manage` - To invite users to public channels
   - `groups:write` - To invite users to private channels
   - `im:write` - To send welcome DMs

### Step 4: Create Slash Commands

1. In the left sidebar, click **"Slash Commands"**
2. Create three commands:

| Command | Short Description | Usage Hint |
|---|---|---|
| `/meetpoll` | Create a meeting scheduling poll | (opens poll creation dialog) |
| `/event` | Create and manage events | `create` or `list` |
| `/onboard` | Manage member onboarding | `status`, `list`, `map`, `unmap`, `run`, `seed` |
| `/outreach` | Send personalized outreach emails | `academics`, `clubs`, `status`, `history` |

### Step 5: Enable Interactivity

1. In the left sidebar, click **"Interactivity & Shortcuts"**
2. Toggle **"Interactivity"** to ON
3. You don't need a Request URL with Socket Mode - leave it blank or enter a placeholder
4. Click **"Save Changes"**

### Step 6: Subscribe to Events

1. In the left sidebar, click **"Event Subscriptions"**
2. Toggle **"Enable Events"** to ON
3. Under **"Subscribe to bot events"**, add:
   - `team_join` - Triggers when a new member joins the workspace
4. Click **"Save Changes"**

### Step 7: Install the App

1. In the left sidebar, click **"Install App"**
2. Click **"Install to Workspace"**
3. Review the permissions and click **"Allow"**
4. **Copy the "Bot User OAuth Token"** (starts with `xoxb-`)

> **Note:** You must reinstall the app every time you add new scopes or event subscriptions.

### Step 8: Add the Bot to Channels

The bot must be a member of any channel it needs to invite users to. For each committee channel:

1. Open the channel in Slack
2. Click the channel name at the top
3. Go to the **Integrations** tab
4. Click **Add apps** and add **MeetPoll**

---

## Part 2: Set Up Google Sheets API

The bot reads new member registrations from a Google Sheet (linked to a Google Form).

### Step 1: Create a Google Cloud Project

1. Go to [https://console.cloud.google.com](https://console.cloud.google.com)
2. Click **"Select a project"** at the top, then **"New Project"**
3. Name it (e.g., `meetpoll-bot`) and click **"Create"**
4. No billing is required for this setup

### Step 2: Enable the Google Sheets API

1. Go to **APIs & Services** > **Library**
2. Search for **"Google Sheets API"**
3. Click it and click **"Enable"**

### Step 3: Create a Service Account

1. Go to **APIs & Services** > **Credentials**
2. Click **"Create Credentials"** > **"Service Account"**
3. Name it (e.g., `meetpoll-sheets`) and click **"Create and Continue"**
4. Skip the optional role/access steps and click **"Done"**

### Step 4: Generate a JSON Key

1. Click on the service account you just created
2. Go to the **Keys** tab
3. Click **"Add Key"** > **"Create new key"** > **JSON** > **"Create"**
4. A `.json` file will download — save it as `service_account.json` in your project directory

### Step 5: Share the Google Sheet

1. Open your Google Sheet (the one linked to your registration form)
2. Click **Share** in the top right
3. Paste the service account email address (looks like `meetpoll-sheets@your-project.iam.gserviceaccount.com` — find it under IAM & Admin > Service Accounts)
4. Set role to **Viewer** and click **Send**

### Step 6: Get the Sheet ID and Name

- **Sheet ID**: From the Google Sheet URL — the long string between `/d/` and `/edit`:
  ```
  https://docs.google.com/spreadsheets/d/THIS_IS_THE_SHEET_ID/edit#gid=0
  ```
- **Sheet Name**: The tab name at the bottom of the sheet (e.g., `Form Responses 1` or `Form Yanıtları 1`)

---

## Part 2b: Google Groups Auto-Add (Optional)

This feature requires a **Google Workspace** account (not a personal `@gmail.com`). If you only have a personal Gmail account, skip this section and leave `GOOGLE_GROUP_EMAIL` empty.

### Step 1: Enable Admin SDK

1. Go to [https://console.cloud.google.com](https://console.cloud.google.com) → your project
2. Go to **APIs & Services** > **Library**
3. Search for **"Admin SDK API"** and enable it

### Step 2: Configure Domain-Wide Delegation

1. Go to **Google Workspace Admin Console** → [admin.google.com](https://admin.google.com)
2. Navigate to **Security** → **API Controls** → **Domain-wide Delegation**
3. Click **Add new**
4. Enter your service account's **Client ID** (found in the service account JSON under `client_id`)
5. Add scope: `https://www.googleapis.com/auth/admin.directory.group.member`
6. Click **Authorize**

### Step 3: Set Environment Variables

```bash
GOOGLE_GROUP_EMAIL=members@yourdomain.org   # The Google Group to add members to
GOOGLE_ADMIN_EMAIL=admin@yourdomain.org     # A Workspace admin email to impersonate
```

---

## Part 3: Set Up Gmail for Welcome Emails

The bot sends welcome emails via Gmail SMTP using an App Password.

### Step 1: Enable 2-Step Verification

1. Go to [https://myaccount.google.com/signinoptions/two-step-verification](https://myaccount.google.com/signinoptions/two-step-verification)
2. Turn on **2-Step Verification** and set up a verification method (phone, authenticator app, etc.)

> **Note:** If you're using a Google Workspace account and can't enable 2-Step Verification (admin restriction), create a free personal `@gmail.com` account for the bot instead.

### Step 2: Create an App Password

1. Go to [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Enter an app name (e.g., `MeetPoll Bot`)
3. Click **"Create"**
4. Copy the 16-character password that appears

---

## Part 4: Deploy the Bot

### Local Development Setup

```bash
# Clone or copy files to your machine
cd /path/to/meetpoll

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment file
cp .env.template .env
```

Edit `.env` with all your credentials (see [Configuring .env](#configuring-env) below).

Run the bot:
```bash
python bot.py
```

### Configuring .env

Copy the template and fill in all values:

```bash
cp .env.template .env
```

```bash
# Slack Bot Tokens (from Part 1)
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here

# Database path (defaults to ./meetpoll.db)
DATABASE_PATH=./meetpoll.db

# Google Sheets (from Part 2)
GOOGLE_SERVICE_ACCOUNT_PATH=./service_account.json
GOOGLE_SHEET_ID=your-google-sheet-id-here
GOOGLE_SHEET_NAME=Form Responses 1

# Gmail SMTP (from Part 3)
GMAIL_SENDER_ADDRESS=your-email@gmail.com
GMAIL_APP_PASSWORD=abcd efgh ijkl mnop

# Onboarding
SLACK_INVITE_LINK=https://join.slack.com/t/your-workspace/shared_invite/xxx
WELCOME_METHOD=email
ONBOARD_AFTER_DATE=
```

| Variable | Description |
|---|---|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token from Slack app settings (starts with `xoxb-`) |
| `SLACK_APP_TOKEN` | App-Level Token for Socket Mode (starts with `xapp-`) |
| `DATABASE_PATH` | Path to SQLite database file (created automatically) |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | Path to the service account JSON key file |
| `GOOGLE_SHEET_ID` | The ID from your Google Sheet URL |
| `GOOGLE_SHEET_NAME` | The sheet tab name (e.g., `Form Responses 1`) |
| `GMAIL_SENDER_ADDRESS` | Gmail address used to send welcome emails |
| `GMAIL_APP_PASSWORD` | 16-character Gmail App Password |
| `SLACK_INVITE_LINK` | Workspace invite link (get it from Slack: workspace menu > Invite people) |
| `CALENDAR_LINK` | Optional Google Calendar link for event calendar integration (leave empty to skip) |
| `WELCOME_METHOD` | `email` (send email only), `slack_dm` (DM only), or `both` |
| `ONBOARD_AFTER_DATE` | Optional cutoff date (e.g., `2026-02-01`). Entries before this date are ignored. Leave empty to process all. |
| `ONBOARD_SUPER_ADMIN` | Your Slack Member ID (get it from your Slack profile > "..." > Copy member ID). This user can manage onboard admins and cannot be removed. |
| `OUTREACH_ACADEMICS_SHEET_ID` | Google Sheet ID for academic contacts |
| `OUTREACH_ACADEMICS_SHEET_NAME` | Sheet tab name (default: `Sheet1`) |
| `OUTREACH_CLUBS_SHEET_ID` | Google Sheet ID for student club contacts |
| `OUTREACH_CLUBS_SHEET_NAME` | Sheet tab name (default: `Sheet1`) |
| `GOOGLE_GROUP_EMAIL` | Google Group email to auto-add new members to (e.g. `members@yourdomain.org`). Requires DWD. Leave empty to disable. |
| `GOOGLE_ADMIN_EMAIL` | A Google Workspace admin email to impersonate for domain-wide delegation |
| `JOBS_CHANNEL_ID` | Slack channel ID where bioinformatics RSS opportunities are posted (e.g. `CQ14TLAGK`) |

### Raspberry Pi Deployment

#### Initial Setup

```bash
# SSH into your Raspberry Pi
ssh pi@raspberrypi.local

# Install Python 3 and pip if needed
sudo apt update
sudo apt install python3 python3-pip python3-venv -y

# Create project directory
mkdir -p ~/meetpoll
cd ~/meetpoll

# Copy project files (from your local machine)
# scp bot.py database.py blocks.py sheets.py mailer.py requirements.txt .env service_account.json pi@raspberrypi.local:~/meetpoll/

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### Set Up as System Service

```bash
# Copy service file
sudo cp meetpoll.service /etc/systemd/system/slackbot.service

# Adjust the service file if your username isn't 'pi'
sudo nano /etc/systemd/system/slackbot.service

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable slackbot
sudo systemctl start slackbot

# Check status
sudo systemctl status slackbot

# View logs
sudo journalctl -u slackbot -f
```

#### Deploying Updates

From your local machine:
```bash
scp bot.py database.py blocks.py sheets.py mailer.py google_groups.py rss_feed.py requirements.txt pi@raspberrypi.local:~/meetpoll/
```

Then on the Pi (use the restart-bot script to avoid duplicate processes):
```bash
sudo restart-bot
```

To create the restart-bot helper (one-time setup):
```bash
sudo nano /usr/local/bin/restart-bot
# Contents:
#   #!/bin/bash
#   systemctl stop slackbot
#   pkill -9 -f "python bot.py" 2>/dev/null
#   sleep 2
#   systemctl start slackbot
sudo chmod +x /usr/local/bin/restart-bot
```

#### Service Management Commands

```bash
sudo restart-bot                    # Cleanly restart the bot (recommended)
sudo systemctl stop slackbot        # Stop the bot
sudo journalctl -u slackbot -n 50   # View recent logs
sudo journalctl -u slackbot -f      # View live logs
```

---

## Part 5: First Run

### 1. Start the Bot

```bash
python bot.py
```

You should see:
```
Scheduler started (polls, registrations, events)
MeetPoll bot starting in Socket Mode...
Bolt app is running!
```

### 2. Seed Existing Members

If your Google Sheet already has registrations, run this in Slack **before anything else** to prevent sending welcome emails to existing members:

```
/onboard seed
```

This imports all current entries as already-onboarded. No emails will be sent to them.

### 3. Set Up Committee Mappings

Map committee names to Slack channels. In Slack:

```
/onboard map "Journal Club" #journal-club
/onboard map "Webinar" #webinar
/onboard map "Website" #website
```

Repeat for each committee. Verify with:
```
/onboard list
```

### 4. Verify the Setup

```
/onboard status
```

Should show your seeded member count as `fully_onboarded`.

### 5. Test with a New Entry

1. Add a test entry to your Google Form with your own email
2. Run `/onboard run` in Slack (or wait up to 1 hour for automatic check)
3. Check your email for the welcome message
4. Join the workspace with the link and verify you're added to the correct channels

---

## Usage

### Polls

1. In any Slack channel, type `/meetpoll`
2. A modal dialog will open with these fields:
   - **Poll Question**: e.g., "When should we have our weekly sync?"
   - **Time Options**: Enter one time slot per line (5-25 options required)
   - **Close Date/Time**: Optional auto-close deadline
3. Click **"Create Poll"**

Voting:
- Click the checkboxes next to times that work for you
- You can select multiple options
- Votes are updated in real-time with full transparency

### Events

- `/event create` — Opens a modal to create an event (title, date, time, location, description, max attendees)
- `/event list` — Shows upcoming events

RSVP buttons appear on the event message: **Going**, **Maybe**, **Not Going**. If a max attendee limit is set, Going is blocked when full. Reminders are sent via DM 24 hours and 1 hour before the event.

### Onboarding Management

> **Access Control:** `/onboard` and `/outreach` commands are restricted to authorized admins only. Set `ONBOARD_SUPER_ADMIN` in `.env` with your Slack Member ID, then use `/onboard admin add @user` to grant access to others.

| Command | Description |
|---|---|
| `/onboard status` | Show onboarding statistics |
| `/onboard list` | Show committee-to-channel mappings |
| `/onboard map "Committee" #channel` | Add or update a mapping |
| `/onboard unmap "Committee"` | Remove a mapping |
| `/onboard run` | Manually check Google Sheet for new registrations |
| `/onboard seed` | Import all existing entries as already-onboarded (first-run safety) |
| `/onboard resend-since 2025-11-01` | Re-send welcome emails to seeded members registered after a date |
| `/onboard user@example.com` | Send a welcome email to a specific address |
| `/onboard admin list` | Show all onboard admins |
| `/onboard admin add @user` | Add an onboard admin (super admin only) |
| `/onboard admin remove @user` | Remove an onboard admin (super admin only) |

### Outreach

| Command | Description |
|---|---|
| `/outreach academics` | Compose and send personalized emails to academic contacts |
| `/outreach clubs` | Compose and send personalized emails to student clubs |
| `/outreach status` | Show aggregate outreach statistics |
| `/outreach history` | Show recent campaigns with expandable details |
| `/outreach send <id> email1, email2` | Resend a campaign to specific email addresses |

**Outreach flow:**
1. Run `/outreach academics` (or `clubs`) — a compose modal opens
2. Enter subject and body — the greeting is auto-prepended per recipient
3. Click **Preview** — see 3 sample emails with personalized greetings
4. Click **Confirm Send** — emails are sent in the background with 2.5s rate limiting
5. Progress updates are posted to the channel every 10 emails

**Manual resend:** Use `/outreach send <campaign_id> email1@x.com, email2@x.com` to resend a past campaign to specific addresses. Accepts comma-separated or space-separated emails. Greetings are looked up from the Google Sheet automatically.

**Google Sheets setup:**

- **Academics sheet** columns: `Ünvan`, `Ad Soyad` (or separate `Ad`/`Soyad`), `E-posta`, `Üniversite`
- **Clubs sheet** columns: `Üniversite`, `Kulüp Adı`, `İletişim E-postası`, `Instagram / Sosyal Medya`, `Alan`, `Notlar`

Share each sheet with the service account email as Viewer. Sheets must be native Google Sheets (not uploaded `.xlsx` files).

### Automatic Background Jobs

| Job | Schedule | Description |
|---|---|---|
| Registration check | Every 1 hour | Checks Google Sheet for new entries, sends welcome emails, retries Google Group adds |
| Event reminders | Every 5 minutes | Sends 24h/1h reminder DMs to RSVPed users |
| Past event closer | Every 10 minutes | Auto-closes events after their scheduled time |
| Poll closer | Every 1 minute | Auto-closes polls past their deadline |
| RSS queue refresh | 10:00 and 22:00 daily | Fetches bioinformatics opportunity feeds, queues new items |
| RSS opportunity post | Random, 10:00–22:00 | Posts one queued item at a time, max 5 per day |

---

## File Structure

```
meetpoll/
├── bot.py                # Main bot application (commands, handlers, scheduler)
├── database.py           # SQLite database operations
├── blocks.py             # Slack Block Kit UI builders
├── sheets.py             # Google Sheets API client
├── mailer.py             # Gmail SMTP email sender
├── google_groups.py      # Google Groups auto-add via Admin SDK DWD
├── rss_feed.py           # RSS feed fetcher and bioinformatics keyword filter
├── requirements.txt      # Python dependencies
├── .env.template         # Environment variables template
├── .env                  # Your actual environment file (do not commit)
├── service_account.json  # Google service account key (do not commit)
├── meetpoll.service      # Systemd service file for Raspberry Pi
├── meetpoll.db           # SQLite database (created automatically)
└── README.md             # This file
```

---

## Troubleshooting

### Bot doesn't respond to commands

1. Check the bot is running: `sudo systemctl status meetpoll`
2. Verify tokens in `.env` are correct
3. Make sure the app is installed/reinstalled after adding scopes
4. Check Socket Mode is enabled in app settings

### "channel_not_found" when onboarding

The bot must be a member of each committee channel before it can invite users. Add the bot to the channel via Slack: Channel settings > Integrations > Add apps.

### "not_in_channel" error

Invite the bot to the channel: `/invite @MeetPoll`

### Google Sheets returns 0 registrations

1. Verify `GOOGLE_SHEET_ID` and `GOOGLE_SHEET_NAME` in `.env`
2. Make sure you shared the Google Sheet with the service account email (Viewer access)
3. Check the service account JSON path is correct

### Welcome emails not sending

1. Verify `GMAIL_SENDER_ADDRESS` and `GMAIL_APP_PASSWORD` in `.env`
2. Make sure 2-Step Verification is enabled on the Gmail account
3. Check that `SLACK_INVITE_LINK` is set
4. Check logs: `sudo journalctl -u meetpoll --since "1 hour ago"`

### Votes/RSVPs not saving

1. Check database permissions: `ls -la meetpoll.db`
2. View logs: `sudo journalctl -u meetpoll -n 100`

---

## Security Notes

- Never commit `.env` or `service_account.json` — both are in `.gitignore`
- The Gmail App Password grants email-sending access — keep it secret
- The service account only has read-only access to the Google Sheet
- Database file contains user IDs and emails but no authentication credentials

---

## License

MIT License - Use freely for your team!

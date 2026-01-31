# MeetPoll - Slack Meeting Poll Bot

A simple, self-hosted Slack bot for creating meeting scheduling polls. Uses Socket Mode (no public URL required) and SQLite for storage. Perfect for Raspberry Pi deployment.

## Features

- `/meetpoll` slash command to create polls
- Support for 5-25 time slot options
- Checkbox-based multi-select voting
- Real-time vote counting with transparency (shows who voted)
- Manual or automatic poll closing
- Detailed results view
- Auto-close at scheduled deadline

## Prerequisites

- Python 3.8+
- A Slack workspace where you have admin permissions

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
   - `commands` - For the /meetpoll slash command
   - `chat:write` - To post poll messages
   - `users:read` - To display user names (optional but recommended)

### Step 4: Create the Slash Command

1. In the left sidebar, click **"Slash Commands"**
2. Click **"Create New Command"**
3. Fill in:
   - Command: `/meetpoll`
   - Short Description: `Create a meeting scheduling poll`
   - Usage Hint: `(opens poll creation dialog)`
4. Click **"Save"**

### Step 5: Enable Interactivity

1. In the left sidebar, click **"Interactivity & Shortcuts"**
2. Toggle **"Interactivity"** to ON
3. You don't need a Request URL with Socket Mode - leave it blank or enter a placeholder
4. Click **"Save Changes"**

### Step 6: Install the App

1. In the left sidebar, click **"Install App"**
2. Click **"Install to Workspace"**
3. Review the permissions and click **"Allow"**
4. **Copy the "Bot User OAuth Token"** (starts with `xoxb-`)

---

## Part 2: Deploy the Bot

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

Edit `.env` with your tokens:
```
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
```

Run the bot:
```bash
python bot.py
```

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
# scp -r ./* pi@raspberrypi.local:~/meetpoll/

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.template .env
nano .env  # Add your tokens
```

#### Set Up as System Service

```bash
# Copy service file
sudo cp meetpoll.service /etc/systemd/system/

# Adjust the service file if your username isn't 'pi'
sudo nano /etc/systemd/system/meetpoll.service

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable meetpoll
sudo systemctl start meetpoll

# Check status
sudo systemctl status meetpoll

# View logs
sudo journalctl -u meetpoll -f
```

#### Service Management Commands

```bash
# Stop the bot
sudo systemctl stop meetpoll

# Restart the bot
sudo systemctl restart meetpoll

# View recent logs
sudo journalctl -u meetpoll -n 50

# View live logs
sudo journalctl -u meetpoll -f
```

---

## Usage

### Creating a Poll

1. In any Slack channel, type `/meetpoll`
2. A modal dialog will open with these fields:
   - **Poll Question**: e.g., "When should we have our weekly sync?"
   - **Time Options**: Enter one time slot per line (5-25 options required)
   - **Close Date/Time**: Optional auto-close deadline

Example time options:
```
Monday 9:00 AM
Monday 2:00 PM
Tuesday 10:00 AM
Tuesday 3:00 PM
Wednesday 11:00 AM
```

3. Click **"Create Poll"**

### Voting

- Click the checkboxes next to times that work for you
- You can select multiple options
- Your votes are updated in real-time
- Everyone can see who voted for what (transparency for scheduling)

### Managing Polls

- **View Results**: Click to see a detailed breakdown in a modal
- **Close Poll**: Only the poll creator can manually close a poll
- Polls auto-close at the scheduled deadline if set

---

## File Structure

```
meetpoll/
├── bot.py              # Main bot application
├── database.py         # SQLite database operations
├── blocks.py           # Slack Block Kit UI builders
├── requirements.txt    # Python dependencies
├── .env.template       # Environment variables template
├── .env                # Your actual environment file (don't commit!)
├── meetpoll.service    # Systemd service file
├── meetpoll.db         # SQLite database (created automatically)
└── README.md           # This file
```

---

## Database Schema

The bot uses SQLite with three tables:

**polls**
- `id`: Primary key
- `question`: Poll question text
- `creator_id`: Slack user ID of creator
- `channel_id`: Channel where poll was posted
- `message_ts`: Slack message timestamp (for updates)
- `created_at`: Creation timestamp
- `closes_at`: Optional close deadline
- `status`: 'open' or 'closed'

**options**
- `id`: Primary key
- `poll_id`: Foreign key to polls
- `option_text`: The time slot text
- `option_order`: Display order

**votes**
- `id`: Primary key
- `poll_id`: Foreign key to polls
- `option_id`: Foreign key to options
- `user_id`: Slack user ID
- `voted_at`: Vote timestamp

---

## Troubleshooting

### Bot doesn't respond to /meetpoll

1. Check the bot is running: `sudo systemctl status meetpoll`
2. Verify tokens in `.env` are correct
3. Make sure the app is installed to your workspace
4. Check Socket Mode is enabled in app settings

### "not_in_channel" error

The bot needs to be in the channel to post. Either:
- Invite the bot: `/invite @MeetPoll`
- Or have the bot DM the poll to the creator

### Votes not saving

1. Check database permissions: `ls -la meetpoll.db`
2. View logs: `sudo journalctl -u meetpoll -n 100`

### Modal doesn't open

1. Verify "Interactivity" is enabled in app settings
2. Check that the bot has the `commands` scope

---

## Security Notes

- Never commit your `.env` file
- The `.env.template` file is safe to commit
- Database file contains user IDs but no sensitive data
- Consider adding `.env` and `*.db` to `.gitignore`

---

## License

MIT License - Use freely for your team!

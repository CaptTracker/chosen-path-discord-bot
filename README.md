[SETUP.md](https://github.com/user-attachments/files/29115876/SETUP.md)
# Chosen Path Bot — Setup Guide

#Invite Link: https://discord.com/oauth2/authorize?client_id=1516882229425606868

## Requirements
- Python 3.10+
- Discord bot with these privileged intents enabled in the Developer Portal:
  - **Server Members Intent**
  - **Message Content Intent**

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` → `.env` and fill in your values:

```env
DISCORD_TOKEN=your_token_here

# Comma-separated role IDs — members with these roles can use mod commands
MOD_ROLE_IDS=111111111111111111,222222222222222222

# Comma-separated role IDs — members with these can use admin commands
ADMIN_ROLE_IDS=333333333333333333,444444444444444444
```

**Getting a role ID:** Enable Developer Mode in Discord settings → right-click a role → Copy Role ID.

## Running

```bash
python bot.py
```

---

## Moderation Commands
Requires a role listed in `MOD_ROLE_IDS`, the **Moderate Members** Discord permission, or server Administrator.

| Command | Description |
|---|---|
| `/kick` | Kick a member |
| `/ban` | Ban a member |
| `/unban` | Unban a user by ID |
| `/timeout` | Timeout a member (minutes) |
| `/untimeout` | Remove a timeout |
| `/warn` | Warn a member (sends them a DM) |
| `/purge` | Delete up to 100 messages |
| `/slowmode` | Set channel slowmode delay |
| `/lock` / `/unlock` | Lock or unlock a channel |
| `/userinfo` | View info about a member |

## Stat Voice Channels
Requires a role in `ADMIN_ROLE_IDS` or server Administrator.

```
/stats add     — attach a voice channel to a stat template
/stats remove  — detach a channel
/stats list    — show all configured stat channels
/stats presets — show available template variables
```

**Template variables:** `{total}` `{humans}` `{bots}` `{online}`

Example: `/stats add channel:#stats-channel template:🦕 Members: {total}`

Channels update every 5 minutes due to Discord rate limits on channel name edits.

## Mod Logging
```
/setlogchannel #channel  — set the channel for mod action logs
/logchannel              — show the current log channel
```

All moderation actions are automatically logged with the moderator, target, and reason.

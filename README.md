# JobBot
Vibe coded bot to fw kunal and maybe post jobs

## Structure

- `bot.py`: Discord client startup and event wiring
- `config.py`: environment loading, constants, and config parsing
- `stickers.py`: sticker moderation helpers
- `monitor.py`: URL polling and apartment change notifications

To test locally:
1. `cp .env_example .env`
2. `make bot`
> Note: Multiple people cant test changes locally since there's only one tester bot

## URL monitor

The bot can also poll a URL on an interval and post in a Discord channel when the filtered apartment list changes.

Set these in `.env`:

- `URL_MONITOR_URL`: URL to request
- `URL_MONITOR_CHANNEL_ID`: Discord channel ID to notify
- `URL_MONITOR_INTERVAL_SECONDS`: poll interval, default `300`
- `URL_MONITOR_TIMEOUT_SECONDS`: request timeout, default `30`
- `URL_MONITOR_STATE_FILE`: file used to persist the last seen response hash
- `URL_MONITOR_MENTION`: optional role/user mention prefix
- `URL_MONITOR_BEDROOM_FILTER`: only include units whose `Beds` value matches this, default `2`

Behavior:

- On first successful poll, the bot stores the current response as the baseline and does not notify.
- On later polls, if the filtered list changes, the bot sends the new filtered list to the configured channel.

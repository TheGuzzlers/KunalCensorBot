import discord

from config import (
    ALLOWED_CHANNEL_IDS,
    BANNED_STICKER_IDS,
    MONITOR_CONFIG,
    REPLACEMENT_STICKER_ID,
    TARGET_USER_IDS,
    TOKEN,
)
from monitor import UrlMonitor
from stickers import get_message_sticker_ids, send_sticker

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
client = discord.Client(intents=intents)
url_monitor = UrlMonitor(client, MONITOR_CONFIG)


@client.event
async def on_ready() -> None:
    print(f"Logged in as {client.user} (id={client.user.id})")
    await url_monitor.start()


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or message.guild is None:
        return

    if ALLOWED_CHANNEL_IDS and message.channel.id not in ALLOWED_CHANNEL_IDS:
        return

    if message.author.id not in TARGET_USER_IDS:
        return

    sticker_ids = get_message_sticker_ids(message)
    if not sticker_ids or sticker_ids.isdisjoint(BANNED_STICKER_IDS):
        return

    try:
        await message.delete()
    except discord.Forbidden:
        print("Missing permissions to delete messages here.")
        return

    try:
        await send_sticker(message.channel, REPLACEMENT_STICKER_ID, TOKEN)
    except Exception as exc:
        print("Failed to send replacement sticker:", exc)


@client.event
async def on_disconnect() -> None:
    await url_monitor.close()


client.run(TOKEN)

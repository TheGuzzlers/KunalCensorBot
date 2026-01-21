import os
import aiohttp
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from typing import Set

# Load standard .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# --- CONFIG ---
def _parse_target_user_ids(raw: str) -> Set[int]:
    ids: Set[int] = set()
    if not raw:
        return ids
    for part in raw.replace(",", " ").split():
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


TARGET_USER_IDS = _parse_target_user_ids(os.getenv("TARGET_USER_IDS", ""))

BANNED_STICKER_IDS = {
    1461152152243142756,
    1461253269824471141,
}

REPLACEMENT_STICKER_ID = 1461235460943642656

# Optional: restrict to certain channels
ALLOWED_CHANNEL_IDS = set()  # e.g. {123, 456}; leave empty for all channels

# Periodic sticker sender (set both to enable)
PERIODIC_CHANNEL_ID = int(os.getenv("PERIODIC_CHANNEL_ID", "0") or "0")
PERIODIC_STICKER_ID = int(os.getenv("PERIODIC_STICKER_ID", "0") or "0")
PERIODIC_EVERY_HOURS = float(os.getenv("PERIODIC_EVERY_HOURS", "2") or "2")
# --------------

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
client = discord.Client(intents=intents)


def get_message_sticker_ids(message: discord.Message) -> Set[int]:
    ids: Set[int] = set()

    # Newer discord.py commonly exposes sticker_items
    sticker_items = getattr(message, "sticker_items", None)
    if sticker_items:
        for s in sticker_items:
            if getattr(s, "id", None) is not None:
                ids.add(int(s.id))

    # Some versions/forks expose stickers
    stickers = getattr(message, "stickers", None)
    if stickers:
        for s in stickers:
            if getattr(s, "id", None) is not None:
                ids.add(int(s.id))

    return ids


async def send_sticker(channel: discord.abc.Messageable, sticker_id: int) -> None:
    """
    Most reliable: call Discord REST Create Message with sticker_ids.
    Note: sticker_ids must be stickers in the server. :contentReference[oaicite:2]{index=2}
    """
    if not hasattr(channel, "id"):
        raise RuntimeError("Channel has no id")

    url = f"https://discord.com/api/v10/channels/{channel.id}/messages"
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    payload = {"sticker_ids": [sticker_id]}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"Failed to send sticker ({resp.status}): {text}")


async def get_channel_or_fetch(channel_id: int):
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except discord.DiscordException as e:
            print("Failed to fetch periodic channel:", e)
            return None
    return channel


@client.event
async def on_ready():
    print(f"Logged in as {client.user} (id={client.user.id})")
    if PERIODIC_CHANNEL_ID and PERIODIC_STICKER_ID:
        if not periodic_sticker_sender.is_running():
            periodic_sticker_sender.change_interval(hours=PERIODIC_EVERY_HOURS)
            periodic_sticker_sender.start()


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.guild is None:
        return

    if ALLOWED_CHANNEL_IDS and message.channel.id not in ALLOWED_CHANNEL_IDS:
        return

    if message.author.id not in TARGET_USER_IDS:
        return

    sticker_ids = get_message_sticker_ids(message)
    if not sticker_ids:
        return

    # Any banned sticker?
    if sticker_ids.isdisjoint(BANNED_STICKER_IDS):
        return

    # Delete the message (requires Manage Messages). :contentReference[oaicite:3]{index=3}
    try:
        await message.delete()
    except discord.Forbidden:
        print("Missing permissions to delete messages here.")
        return

    # Send replacement sticker
    try:
        await send_sticker(message.channel, REPLACEMENT_STICKER_ID)
    except Exception as e:
        print("Failed to send replacement sticker:", e)


@tasks.loop(hours=2)
async def periodic_sticker_sender():
    if not PERIODIC_CHANNEL_ID or not PERIODIC_STICKER_ID:
        return
    channel = await get_channel_or_fetch(PERIODIC_CHANNEL_ID)
    if channel is None:
        return
    try:
        await send_sticker(channel, PERIODIC_STICKER_ID)
    except Exception as e:
        print("Failed to send periodic sticker:", e)


@periodic_sticker_sender.before_loop
async def _periodic_sticker_sender_ready():
    await client.wait_until_ready()


client.run(TOKEN)

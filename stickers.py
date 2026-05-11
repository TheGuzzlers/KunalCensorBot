from typing import Set

import aiohttp
import discord


def get_message_sticker_ids(message: discord.Message) -> Set[int]:
    ids: Set[int] = set()

    for attr_name in ("sticker_items", "stickers"):
        stickers = getattr(message, attr_name, None)
        if not stickers:
            continue

        for sticker in stickers:
            sticker_id = getattr(sticker, "id", None)
            if sticker_id is not None:
                ids.add(int(sticker_id))

    return ids


async def send_sticker(
    channel: discord.abc.Messageable,
    sticker_id: int,
    token: str,
) -> None:
    if not hasattr(channel, "id"):
        raise RuntimeError("Channel has no id")

    url = f"https://discord.com/api/v10/channels/{channel.id}/messages"
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    payload = {"sticker_ids": [sticker_id]}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"Failed to send sticker ({resp.status}): {text}")

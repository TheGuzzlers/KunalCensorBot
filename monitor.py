import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urlsplit, urlunsplit

import aiohttp
import discord
from discord.ext import tasks

from config import LOCAL_TIMEZONE, MonitorConfig


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _format_human_date(value: datetime) -> str:
    return f"{_ordinal(value.day)} {value.strftime('%B %Y')}"


def _normalize_url(value: str) -> str:
    if not value:
        return ""

    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value

    normalized_path = quote(parts.path, safe="/")
    normalized_query = quote(parts.query, safe="=&%")
    return urlunsplit(
        (parts.scheme, parts.netloc, normalized_path, normalized_query, parts.fragment)
    )


@dataclass(frozen=True)
class MonitorPayload:
    status: int
    content_type: str
    body: str


@dataclass(frozen=True)
class Floorplan:
    floorplan_id: str
    name: str
    beds: str
    baths: str
    minimum_sqft: str
    maximum_sqft: str
    minimum_rent: str
    maximum_rent: str
    available_units: str
    availability_url: str
    image_url: str

    @classmethod
    def from_api_item(cls, item: dict) -> "Floorplan":
        return cls(
            floorplan_id=str(item.get("FloorplanId", "")),
            name=str(item.get("FloorplanName", "Unknown")),
            beds=str(item.get("Beds", "?")).strip(),
            baths=str(item.get("Baths", "?")),
            minimum_sqft=str(item.get("MinimumSQFT", "?")),
            maximum_sqft=str(item.get("MaximumSQFT", "?")),
            minimum_rent=str(item.get("MinimumRent", "?")),
            maximum_rent=str(item.get("MaximumRent", "?")),
            available_units=str(item.get("AvailableUnitsCount", "0")),
            availability_url=_normalize_url(str(item.get("AvailabilityURL", "")).strip()),
            image_url=_normalize_url(str(item.get("FloorplanImageURL", "")).strip()),
        )

    @property
    def sqft(self) -> str:
        if self.minimum_sqft == self.maximum_sqft:
            return self.minimum_sqft
        return f"{self.minimum_sqft}-{self.maximum_sqft}"

    @property
    def rent(self) -> str:
        if self.minimum_rent == self.maximum_rent:
            return self.minimum_rent
        return f"{self.minimum_rent}-{self.maximum_rent}"

    def summary_line(self) -> str:
        return (
            f"- {self.name}: {self.beds} bed / {self.baths} bath, "
            f"{self.sqft} sqft, ${self.rent}, {self.available_units} unit(s)"
        )

    def to_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=self.name,
            description=(
                f"{self.beds} bed / {self.baths} bath\n"
                f"{self.sqft} sqft\n"
                f"${self.rent}\n"
                f"{self.available_units} unit(s) available"
            ),
        )
        if self.availability_url:
            embed.url = self.availability_url
        if self.image_url:
            embed.set_image(url=self.image_url)
        return embed

    def signature_payload(self) -> dict[str, str]:
        return {
            "floorplan_id": self.floorplan_id,
            "name": self.name,
            "beds": self.beds,
            "baths": self.baths,
            "minimum_sqft": self.minimum_sqft,
            "maximum_sqft": self.maximum_sqft,
            "minimum_rent": self.minimum_rent,
            "maximum_rent": self.maximum_rent,
            "available_units": self.available_units,
            "availability_url": self.availability_url,
            "image_url": self.image_url,
        }


class UrlMonitor:
    def __init__(self, client: discord.Client, config: MonitorConfig):
        self.client = client
        self.config = config
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.last_signature: Optional[str] = None
        self.sent_startup_snapshot = False
        self.loop = tasks.loop(seconds=self.config.interval_seconds)(self.run_once)
        self.loop.before_loop(self.before_loop)

    async def start(self) -> None:
        if not self.config.enabled:
            return

        await self.send_startup_snapshot()

        if not self.loop.is_running():
            self.loop.start()

    async def close(self) -> None:
        if self.http_session is not None and not self.http_session.closed:
            await self.http_session.close()
            self.http_session = None

    async def before_loop(self) -> None:
        await self.client.wait_until_ready()
        self.last_signature = self._load_state()

    async def send_startup_snapshot(self) -> None:
        if self.sent_startup_snapshot:
            return

        channel = await self._get_channel()
        if channel is None:
            return

        try:
            payload = await self._fetch_payload()
            floorplans = self._extract_floorplans(payload)
            current_signature = self._build_signature(payload, floorplans)
        except Exception as exc:
            print(f"Failed to send startup monitor snapshot: {exc}")
            return

        if not await self._send_monitor_message(
            channel,
            self._build_embeds(payload, floorplans, "Current"),
            startup=True,
        ):
            return

        self.sent_startup_snapshot = True
        self.last_signature = current_signature
        self._save_state(current_signature)
        print("URL monitor sent startup snapshot.")

    async def run_once(self) -> None:
        channel = await self._get_channel()
        if channel is None:
            return

        try:
            payload = await self._fetch_payload()
            floorplans = self._extract_floorplans(payload)
            current_signature = self._build_signature(payload, floorplans)
        except Exception as exc:
            print(f"URL monitor request failed: {exc}")
            return

        if not self.sent_startup_snapshot:
            self.sent_startup_snapshot = True
            self.last_signature = current_signature
            self._save_state(current_signature)
            return

        if self.last_signature is None:
            self.last_signature = current_signature
            self._save_state(current_signature)
            print("URL monitor baseline stored.")
            return

        if current_signature == self.last_signature:
            return

        if not await self._send_monitor_message(
            channel,
            self._build_embeds(payload, floorplans, "Updated"),
            startup=False,
        ):
            return

        self.last_signature = current_signature
        self._save_state(current_signature)
        print("URL monitor detected a change and sent a notification.")

    def _load_state(self) -> Optional[str]:
        if not self.config.state_file.exists():
            return None

        try:
            with self.config.state_file.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

        signature = payload.get("signature")
        if isinstance(signature, str) and signature:
            return signature
        return None

    def _save_state(self, signature: str) -> None:
        with self.config.state_file.open("w", encoding="utf-8") as fh:
            json.dump({"signature": signature}, fh)

    async def _get_channel(self) -> Optional[discord.abc.Messageable]:
        if self.config.channel_id is None:
            print("URL monitor is enabled but URL_MONITOR_CHANNEL_ID is missing.")
            return None

        channel = self.client.get_channel(self.config.channel_id)
        if channel is not None:
            return channel

        try:
            return await self.client.fetch_channel(self.config.channel_id)
        except discord.DiscordException as exc:
            print(f"Failed to load monitor channel: {exc}")
            return None

    async def _fetch_payload(self) -> MonitorPayload:
        if not self.config.url:
            raise RuntimeError("URL monitor is not configured")

        if self.http_session is None or self.http_session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            self.http_session = aiohttp.ClientSession(timeout=timeout)

        async with self.http_session.get(self.config.url) as response:
            body = await response.text()
            return MonitorPayload(
                status=response.status,
                content_type=response.headers.get("Content-Type", ""),
                body=body,
            )

    def _extract_floorplans(self, payload: MonitorPayload) -> list[Floorplan]:
        try:
            data = json.loads(payload.body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"URL monitor response was not valid JSON: {exc}") from exc

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "URL monitor response JSON string did not contain a valid list"
                ) from exc

        if not isinstance(data, list):
            raise RuntimeError("URL monitor response JSON must be a list")

        floorplans: list[Floorplan] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            floorplan = Floorplan.from_api_item(item)
            if floorplan.beds != self.config.bedroom_filter:
                continue
            floorplans.append(floorplan)

        floorplans.sort(key=lambda item: item.floorplan_id)
        return floorplans

    def _build_signature(self, payload: MonitorPayload, floorplans: list[Floorplan]) -> str:
        normalized = json.dumps(
            {
                "status": payload.status,
                "content_type": payload.content_type,
                "floorplans": [floorplan.signature_payload() for floorplan in floorplans],
            },
            sort_keys=True,
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _build_embeds(
        self,
        payload: MonitorPayload,
        floorplans: list[Floorplan],
        prefix_label: str,
    ) -> list[discord.Embed]:
        formatted_date = _format_human_date(datetime.now(LOCAL_TIMEZONE))
        footer_text = f"{formatted_date} • Status {payload.status}"

        if not floorplans:
            embed = discord.Embed(
                title=f"{prefix_label} {self.config.bedroom_filter}-bedroom apartments",
                description="No matching floorplans are currently available.",
            )
            embed.set_footer(text=footer_text)
            if self.config.url:
                embed.url = self.config.url
            return [embed]

        embeds: list[discord.Embed] = []
        for index, floorplan in enumerate(floorplans[:10]):
            embed = floorplan.to_embed()
            if index == 0:
                embed.title = f"{prefix_label}: {embed.title}"
            embed.set_footer(text=footer_text)
            embeds.append(embed)

        return embeds

    async def _send_monitor_message(
        self,
        channel: discord.abc.Messageable,
        embeds: list[discord.Embed],
        *,
        startup: bool,
    ) -> bool:
        try:
            await channel.send(embeds=embeds)
            return True
        except discord.DiscordException as exc:
            label = "startup monitor snapshot" if startup else "monitor notification"
            print(f"Failed to send {label} with embeds: {exc}")
            return False

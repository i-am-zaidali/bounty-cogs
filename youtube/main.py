import dateparser
from datetime import datetime, timezone
import functools
import logging
import re
from typing import Optional

import aiohttp
import discord
import feedparser
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf, bounded_gather

from .errors import APIError, InvalidYoutubeCredentials, YoutubeQuotaExceeded

YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
YOUTUBE_BASE_URL = "https://www.googleapis.com/youtube/v3"
YOUTUBE_CHANNELS_ENDPOINT = YOUTUBE_BASE_URL + "/channels"
YOUTUBE_VIDEOS_ENDPOINT = YOUTUBE_BASE_URL + "/videos"
YOUTUBE_DURATION_REGEX = r"P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"

log = logging.getLogger("red.craycogs.youtube")


class Youtube(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(self, identifier=1234567890)

        default_guild = {
            "subscribed_channels": [],
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "posted_vids": [],
            "post_channels": {},  # would be like {"shorts": channel_id, "videos": channel_id, "live": channel_id}
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(checking_interval=300)

        self.session = aiohttp.ClientSession()
        self.check_task = self.checking.start()

    async def cog_unload(self):
        self.check_task.cancel()
        await self.session.close()

    @tasks.loop(seconds=1)
    async def checking(self):
        for guild_id, data in (await self.config.all_guilds()).items():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue

            subscribed_channels = data["subscribed_channels"]
            last_checked = datetime.fromisoformat(data["last_checked"])
            post_channels = data["post_channels"]
            posted_vids = data["posted_vids"]

            if len(subscribed_channels) == 0 or all(
                (val is None for val in post_channels.values())
            ):
                continue

            ids = set()
            msgs = []
            latest_videos = set()
            for channel_id in subscribed_channels:
                async with self.session.get(
                    YOUTUBE_FEED_URL.format(channel_id=channel_id)
                ) as resp:
                    if resp.status != 200:
                        log.error(
                            f"Failed to fetch feed for channel {channel_id}, error code: {resp.status} ({resp.reason})",
                        )
                        continue

                    feed = feedparser.parse(await resp.text())
                    videos = feed["entries"]
                    log.debug(f"Got {len(videos)} videos from channel {channel_id}")
                    latest_videos_cc = set(
                        sorted(
                            filter(
                                lambda x: dateparser.parse(x["published"])
                                >= last_checked
                                and x["yt_videoid"] not in posted_vids,
                                videos,
                            ),
                            key=lambda x: dateparser.parse(x["published"]),
                        )
                    )
                    latest_videos |= latest_videos_cc

                    if len(latest_videos_cc) == 0:
                        log.info(f"No new videos found from channel {channel_id}")
                        continue

                    ids |= set([vid.yt_videoid for vid in latest_videos_cc])

                    log.info(
                        f"Found {len(latest_videos_cc)} new videos from channel {channel_id}"
                    )

            try:
                data = await self.get_video_data_from_id(ids)

            except Exception as e:
                log.error("Error fetching video data", exc_info=e)
                continue

            for ytvid in data:
                reelvid = next(
                    vid for vid in latest_videos if vid.yt_videoid == ytvid["id"]
                )
                # reelvid would always be present since we requested based on it
                log.debug(ytvid, reelvid)
                published = dateparser.parse(ytvid["snippet"]["publishedAt"])

                message_to_send = f"<t:{int(published.timestamp())}:F> :\n**{ytvid['snippet']['title']}**\n\n{reelvid.link}"

                if (
                    ytvid["snippet"]["liveBroadcastContent"].lower()
                    not in ["none", None]
                    or ytvid.get("liveStreamingDetails") is not None
                ):
                    chan = post_channels.get("live")
                    if chan is None:
                        continue
                    channel = guild.get_channel(chan)
                    if channel is None:
                        log.info("No channel for live streams found.")
                        continue
                    msgs.append(channel.send(f"New live started at {message_to_send}"))

                elif (
                    duration := self.parse_duration(ytvid["contentDetails"]["duration"])
                ) > 600:
                    chan = post_channels.get("videos")
                    if chan is None:
                        continue
                    channel = guild.get_channel(chan)
                    if channel is None:
                        log.info("No channel for main videos found.")
                        continue
                    msgs.append(
                        channel.send(f"New video uploaded at {message_to_send}")
                    )

                # check if it's a short
                elif duration <= 60:
                    chan = post_channels.get("shorts")
                    if chan is None:
                        continue
                    channel = guild.get_channel(chan)
                    if channel is None:
                        log.info("No channel for shorts found.")
                        continue
                    msgs.append(
                        channel.send(f"New short uploaded at {message_to_send}")
                    )

            await bounded_gather(*msgs)

            now = datetime.now(timezone.utc)
            log.info(
                f"Checked for new videos at human readabale time: {now.strftime('%c')}"
            )
            await self.config.guild(guild).last_checked.set(
                datetime.now(timezone.utc).isoformat()
            )
            async with self.config.guild(guild).posted_vids() as posted_vids:
                posted_vids.extend(ids)

    @checking.before_loop
    async def before_checking(self):
        await self.bot.wait_until_red_ready()
        if not self.bot.get_cog("Youtube"):
            self.check_task.cancel()
            return
        self.checking.change_interval(seconds=await self.config.checking_interval())

    @checking.error
    async def checking_error(self, error):
        log.exception("There was an error in the youtube checking loop", exc_info=error)

    def parse_duration(self, duration: str) -> int:
        if not (match := re.match(YOUTUBE_DURATION_REGEX, duration)):
            raise ValueError("Invalid duration string")

        times = match.groups()

        multi = [86400, 3600, 60, 1]
        seconds = sum(
            int(time) * multi[i] for i, time in enumerate(times) if time is not None
        )

        return seconds

    async def get_video_data_from_id(self, video_ids: list[int]):
        params = {
            "part": "snippet,liveStreamingDetails,contentDetails",
            "id": ",".join(video_ids),
            "key": self.api_key,
        }
        async with self.session.get(YOUTUBE_VIDEOS_ENDPOINT, params=params) as resp:
            data = await resp.json()
            self.check_resp_for_errors(data)
            return data["items"]

    async def get_id_from_channel_name(self, channel_name: str, api_key: str):
        params = {
            "part": "id",
            "forUsername": channel_name,
            "key": api_key,
        }

        async with self.session.get(YOUTUBE_CHANNELS_ENDPOINT, params=params) as resp:
            data = await resp.json()
            self.check_resp_for_errors(data)
            return data["items"][0]["id"]

    def check_resp_for_errors(self, data: dict):
        if "error" in data:
            error_code = data["error"]["code"]
            if (
                error_code == 400
                and data["error"]["errors"][0]["reason"] == "keyInvalid"
            ):
                raise InvalidYoutubeCredentials()
            elif error_code == 403 and data["error"]["errors"][0]["reason"] in (
                "dailyLimitExceeded",
                "quotaExceeded",
                "rateLimitExceeded",
            ):
                raise YoutubeQuotaExceeded()
            raise APIError(error_code, data)

    @commands.group(name="youtube", aliases=["yt"])
    async def youtube(self, ctx: commands.Context):
        """Youtube commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @youtube.command(name="subscribe", aliases=["sub"])
    async def subscribe(self, ctx: commands.Context, channel_id: str):
        """
        Subscribe to a channel.

        You can use either the channel name or the channel ID.

        This would subscribe to the channel and start listening for new videos.
        """
        async with self.config.guild(ctx.guild).subscribed_channels() as channels:
            if channel_id in channels:
                await ctx.send("Channel already subscribed.")
                return

            channels.append(channel_id)

        await ctx.send("Channel subscribed.")

    @youtube.command(name="unsubscribe", aliases=["unsub"])
    async def unsubscribe(self, ctx: commands.Context, channel_id: str):
        """
        Unsubscribe from a channel.

        You can use either the channel name or the channel ID.

        This would unsubscribe from the channel and stop listening for new videos."""
        async with self.config.guild(ctx.guild).subscribed_channels() as channels:
            if channel_id not in channels:
                await ctx.send("Channel not subscribed.")
                return

            channels.remove(channel_id)

        await ctx.send("Channel unsubscribed.")

    @youtube.command(name="list")
    async def list(self, ctx: commands.Context):
        """
        List all subscribed channels."""
        channels = await self.config.guild(ctx.guild).subscribed_channels()
        if len(channels) == 0:
            await ctx.send("No channels subscribed.")
            return

        await ctx.send(
            f"Subscribed channels: {cf.humanize_list(channels) or 'No channels subscribed.'}"
        )

    @youtube.group(name="post")
    async def post(self, ctx: commands.Context):
        """Set the channels to post to."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @post.command(name="shorts")
    async def post_shorts(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """
        Set the channel to post shorts to."""
        async with self.config.guild(ctx.guild).post_channels() as channels:
            channels["shorts"] = getattr(channel, "id", None)

        await ctx.send(f"Shorts channel set to {getattr(channel, 'mention', None)}")

    @post.command(name="videos")
    async def post_videos(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """
        Set the channel to post videos to."""
        async with self.config.guild(ctx.guild).post_channels() as channels:
            channels["videos"] = getattr(channel, "id", None)

        await ctx.send(f"Videos channel set to {getattr(channel, 'mention', None)}")

    @post.command(name="live")
    async def post_live(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """
        Set the channel to post live streams to."""
        async with self.config.guild(ctx.guild).post_channels() as channels:
            channels["live"] = getattr(channel, "id", None)

        await ctx.send(f"Live channel set to {getattr(channel, 'mention', None)}")

    @youtube.command(name="setinterval")
    async def set_interval(self, ctx: commands.Context, interval: int):
        """
        Set the interval to check for new videos."""
        if interval < 60:
            await ctx.send("Interval must be at least 60 seconds.")
            return

        await self.config.checking_interval.set(interval)
        await ctx.send(f"Interval set to {interval} seconds.")

    @youtube.command(name="forcecheck")
    @commands.is_owner()
    async def force_check(self, ctx: commands.Context):
        """
        Force check for new videos.

        This will check for new videos and post them to the channels set.
        """
        await ctx.send("Checking for new videos...")
        await self.checking()
        await ctx.send("Done.")

    @youtube.command(name="setlasttimechecked", aliases=["sltc"])
    @commands.is_owner()
    async def sltc(
        self,
        ctx: commands.Context,
        *,
        date: functools.partial(
            dateparser.parse,
            settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True},
        ),
    ):
        if date >= discord.utils.utcnow():
            return await ctx.send("Cant have laSt checked date in the future")
        await self.config.guild(ctx.guild).last_checked.set(date.isoformat())
        await ctx.send(
            f"Last checked date has been set to <t:{int(date.timestamp())}:F>"
        )

    @youtube.command(name="showsettings", aliases=["settings", "ss"])
    async def show_settings(self, ctx: commands.Context):
        """
        Show the current settings for the cog."""
        data = await self.config.guild(ctx.guild).all()
        subscribed_channels = data["subscribed_channels"]
        last_checked = data["last_checked"]
        post_channels = data["post_channels"]
        interval = await self.config.checking_interval()

        message = (
            f"Subscribed channels: {cf.humanize_list(subscribed_channels) or 'No channels subscribed.'}\n"
            f"Last checked: <t:{int(datetime.fromisoformat(last_checked).timestamp())}:R>\n"
            f"Interval: {cf.humanize_timedelta(seconds=interval)}\n"
            f"Shorts channel: {getattr(ctx.guild.get_channel(post_channels.get('shorts')), 'mention', 'None')}\n"
            f"Videos channel: {getattr(ctx.guild.get_channel(post_channels.get('videos')), 'mention', 'None')}\n"
            f"Live channel: {getattr(ctx.guild.get_channel(post_channels.get('live')), 'mention', 'None')}\n"
        )

        await ctx.send(message)

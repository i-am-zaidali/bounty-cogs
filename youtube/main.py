from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
import discord
from discord.ext import tasks
from datetime import datetime, timezone
import asyncio
import feedparser
import aiohttp
import re
from .errors import InvalidYoutubeCredentials, YoutubeQuotaExceeded, APIError
from typing import Optional

YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
YOUTUBE_BASE_URL = "https://www.googleapis.com/youtube/v3"
YOUTUBE_CHANNELS_ENDPOINT = YOUTUBE_BASE_URL + "/channels"
YOUTUBE_VIDEOS_ENDPOINT = YOUTUBE_BASE_URL + "/videos"

class Youtube(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        
        self.config = Config.get_conf(self, identifier=1234567890)
        
        default_guild = {
            "subscribed_channels": [],
            "last_checked": datetime(2023, 4, 30, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
            "post_channels": {}, # would be like {"shorts": channel_id, "videos": channel_id, "live": channel_id}
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
        # get all guilds
        # for each guild, get the subscribed channels
        # for each channel, get the last checked time
        # for each channel, get the latest video
        # for each channel, check if the latest video is newer than the last checked time
        # if it is, post the video
        # update the last checked time
        # save the last checked time
        # repeat for each channel
        # repeat for each guild
        # repeat every 5 minutes
        for guild_id, data in (await self.config.all_guilds()).items():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            
            subscribed_channels = data["subscribed_channels"]
            last_checked = data["last_checked"]
            last_checked = datetime.fromisoformat(last_checked)
            post_channels = data["post_channels"]
            
            if len(subscribed_channels) == 0 or all((val is None for val in post_channels.values())):
                continue
            
            for channel_id in subscribed_channels:
                async with self.session.get(YOUTUBE_FEED_URL.format(channel_id=channel_id)) as resp:
                    if resp.status != 200:
                        continue
                    
                    feed = feedparser.parse(await resp.text())
                    videos = feed["entries"]
                    latest_videos = sorted(filter(lambda x: datetime.strptime(x['published'], '%Y-%m-%dT%H:%M:%S%z') > last_checked, videos), key=lambda x: x['published']) 
                    for vid in latest_videos:
                        data = await self.get_video_data_from_id(vid.yt_videoid)
                        published = datetime.strptime(data['snippet']['publishedAt'], '%Y-%m-%dT%H:%M:%S%z')
                        
                        message_to_send = f"<t:{int(published.timestamp())}:F> :\n**{data['snippet']['title']}**\n\n{vid.link}"
                        
                        if data['snippet']['liveBroadcastContent'] not in ["None", "none", None]:
                            chan = post_channels.get("live")
                            if chan is None:
                                continue
                            channel = guild.get_channel(chan)
                            if channel is None:
                                continue
                            await channel.send(f"New live started at {message_to_send}")
                        
                        # check if it's a short
                        elif self.parse_duration(data["contentDetails"]["duration"]) <= 60:
                            chan = post_channels.get("shorts")
                            if chan is None:
                                continue
                            channel = guild.get_channel(chan)
                            if channel is None:
                                continue
                            await channel.send(f"New short uploaded at {message_to_send}")
                        
                        else:
                            chan = post_channels.get("videos")
                            if chan is None:
                                continue
                            channel = guild.get_channel(chan)
                            if channel is None:
                                continue
                            await channel.send(f"New video uploaded at {message_to_send}")
                            
            await self.config.guild(guild).last_checked.set(datetime.now(timezone.utc).isoformat())
                                 
    @checking.before_loop
    async def before_checking(self):
        await self.bot.wait_until_red_ready()
        if not self.bot.get_cog("Youtube"):
            self.check_task.cancel()
            return
        self.checking.change_interval(seconds=await self.config.checking_interval())
        
    def parse_duration(self, duration: str) -> int:
        if not duration.startswith("PT"):
            raise ValueError("Invalid duration {}".format(duration))
        
        duration = duration[2:]
        seconds = 0
        # duration looks like this: xHxMxS
        
        # get the hours
        if "H" in duration:
            hours, duration = duration.split("H")
            seconds += int(hours) * 3600
            
        # get the minutes
        if "M" in duration:
            minutes, duration = duration.split("M")
            seconds += int(minutes) * 60
            
        # get the seconds
        if "S" in duration:
            seconds += int(duration[:-1])
            
        return seconds
                        
    async def get_video_data_from_id(self, video_id):
        params = {
            "part": "snippet,liveStreamingDetails,contentDetails",
            "id": video_id,
            "key": self.api_key,
        }
        async with self.session.get(YOUTUBE_VIDEOS_ENDPOINT, params=params) as resp:
            data = await resp.json()
            self.check_resp_for_errors(data)
            return data["items"][0]
        
    async def get_id_from_channel_name(self, channel_name: str, api_key: str):
        params = {
            "part": "id",
            "forUsername": channel_name,
            "key": api_key,
        }
        
        async with self.session.get(YOUTUBE_CHANNELS_ENDPOINT, params=params) as resp:
            data = await resp.json()
            self.check_resp_for_errors(data)
            print(data)
            return data["items"][0]["id"]
        
    def check_resp_for_errors(self, data: dict):
        if "error" in data:
            error_code = data["error"]["code"]
            if error_code == 400 and data["error"]["errors"][0]["reason"] == "keyInvalid":
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
        
        await ctx.send(f"Subscribed channels: {cf.humanize_list(channels) or 'No channels subscribed.'}")
        
    @youtube.group(name="post")
    async def post(self, ctx: commands.Context):
        """Set the channels to post to."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()
            
    @post.command(name="shorts")
    async def post_shorts(self, ctx: commands.Context, channel: Optional[discord.TextChannel]=None):
        """
        Set the channel to post shorts to."""
        async with self.config.guild(ctx.guild).post_channels() as channels:
            channels["shorts"] = getattr(channel, "id", None)
            
        await ctx.send(f"Shorts channel set to {getattr(channel, 'mention', None)}")
        
    @post.command(name="videos")
    async def post_videos(self, ctx: commands.Context, channel: Optional[discord.TextChannel]=None):
        """
        Set the channel to post videos to."""
        async with self.config.guild(ctx.guild).post_channels() as channels:
            channels["videos"] = getattr(channel, "id", None)
            
        await ctx.send(f"Videos channel set to {getattr(channel, 'mention', None)}")
        
    @post.command(name="live")
    async def post_live(self, ctx: commands.Context, channel: Optional[discord.TextChannel]=None):
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
    async def force_check(self, ctx: commands.Context):
        """
        Force check for new videos.
        
        This will check for new videos and post them to the channels set.
        """
        await ctx.send("Checking for new videos...")
        await self.checking()
        await ctx.send("Done.")
        
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
            f"Interval: {cf.humanize_timedelta(seconds=interval)}"
            f"Shorts channel: {getattr(ctx.guild.get_channel(post_channels.get('shorts')), 'mention', 'None')}\n"
            f"Videos channel: {getattr(ctx.guild.get_channel(post_channels.get('videos')), 'mention', 'None')}\n"
            f"Live channel: {getattr(ctx.guild.get_channel(post_channels.get('live')), 'mention', 'None')}\n"
        )
        
        await ctx.send(message)
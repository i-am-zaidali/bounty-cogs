import datetime
import logging
from redbot.core.bot import Red
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import pagify, humanize_timedelta
import discord
import typing
from bs4 import BeautifulSoup
from semver import Version
from redbot.core.utils import bounded_gather
from redbot.core.commands.converter import get_timedelta_converter
from discord.ext import tasks
from .scrapers import StreamlabsScraper, TwitchScraper, BaseScraper
from pathlib import Path

GuildMessageable = typing.Union[
    discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread
]
TimeDelta = get_timedelta_converter(
    default_unit="seconds",
    minimum=0.5 * 24 * 60 * 60,
)

log = logging.getLogger("red.bounty.patchnotes")


class PatchNotes(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        guild_default = {
            "streamlabs": {"channel": None, "pingrole": None},
            "twitch": {"channel": None, "pingrole": None},
            "obs": {"channel": None, "pingrole": None},
        }

        self.config.register_guild(**guild_default)
        self.config.register_global(
            obs_feed_name=None,
            last_posted_version={
                "obs": "0.0.0",
                "streamlabs": "0.0.0",
                "twitch": "25.0.0",
            },
            delay=1 * 24 * 60 * 60,
            chrome_path=None,
        )

        self._task = self.check_for_new_patchnotes.start()

    @tasks.loop(seconds=1)
    async def check_for_new_patchnotes(self):
        for feed_name in ["streamlabs", "twitch"]:
            all_guilds = await self.config.all_guilds()
            channels_to_send_to: list[
                tuple[GuildMessageable, typing.Optional[discord.Role]]
            ] = []

            for gid, data in all_guilds.items():
                log.debug(f"{gid=} {data=}")
                if not data[feed_name]["channel"]:
                    continue

                guild = self.bot.get_guild(gid)
                if guild is None:
                    continue

                channel = guild.get_channel(data.get(feed_name, {}).get("channel"))
                if channel is None:
                    continue

                if not (role := data.get(feed_name, {}).get("pingrole")):
                    role = None
                else:
                    role = guild.get_role(role)

                channels_to_send_to.append((channel, role))

            log.debug(f"{channels_to_send_to=}")
            if not channels_to_send_to:
                continue

            last_version = Version.parse(
                await self.config.last_posted_version.get_attr(feed_name)()
            )
            if feed_name == "streamlabs":
                scraper = StreamlabsScraper(chrome_path=await self.config.chrome_path())

            else:
                scraper = TwitchScraper(
                    last_version=last_version,
                    chrome_path=await self.config.chrome_path(),
                )

            version, md = await scraper.get_patch_notes()
            log.debug(f"{version=} {last_version=}")
            if version <= last_version:
                return
            log.info(
                f"New {feed_name} version detected: {version} (old: {last_version})"
            )

            await self._handle_sending_patchnotes(md, channels_to_send_to)

            await self.config.last_posted_version.get_attr(feed_name).set(str(version))

    @check_for_new_patchnotes.before_loop
    async def before_check_for_new_patchnotes(self):
        log.debug("WTF")
        await self.bot.wait_until_red_ready()
        delay = await self.config.delay()
        self.check_for_new_patchnotes.change_interval(seconds=delay)
        log.info(
            f"Starting check_for_new_patchnotes task, interval: {humanize_timedelta(seconds=delay)}",
        )

    @check_for_new_patchnotes.error
    async def check_for_new_patchnotes_error(self, error):
        log.error(f"Error in check_for_new_patchnotes task: {error}", exc_info=error)

    @commands.Cog.listener(name="on_aikaternacogs_rss_message")
    async def obs_patchnotes(
        self,
        channel: discord.TextChannel,
        feed_data: dict,
        feedparser_dict: dict,
        force: bool,
        **kwargs,
    ):
        if feed_data["name"] != await self.config.obs_feed_name():
            return

        log.info(f"OBS patch notes detected: {feedparser_dict['links'][0]['href']}")
        log.debug(f"{feed_data=}")

        new_version = Version.parse(feedparser_dict["links"][0]["href"].split("/")[-1])
        old_version = Version.parse(await self.config.last_posted_version.obs())
        log.debug(f"{new_version=} {old_version=}")
        if new_version <= old_version and not force:
            return

        log.info(f"New OBS version detected: {new_version} (old: {old_version})")

        channels_to_send = [
            (chan, guild.get_role(data.get("obs", {}).get("pingrole")))
            for gid, data in (await self.config.all_guilds()).items()
            if (guild := self.bot.get_guild(gid))
            and (
                chan := guild.get_channel_or_thread(data.get("obs", {}).get("channel"))
            )
        ]

        log.debug(f"{len(channels_to_send)=}")

        md = BaseScraper().convert_element_to_md(
            BeautifulSoup(feedparser_dict["content"][0]["value"], "html.parser")
        )

        await self._handle_sending_patchnotes(
            f"# __OBS PATCH NOTES__ (VER: {new_version}) {datetime.datetime.strptime(feedparser_dict['updated'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d')}\n"
            + md,
            channels_to_send,
        )

        await self.config.last_posted_version.obs.set(str(new_version))

    async def _handle_sending_patchnotes(
        self,
        markdown: str,
        channels_to_send_to: list[
            tuple[GuildMessageable, typing.Optional[discord.Role]]
        ],
    ):
        for ind, page in enumerate(
            pagify(
                markdown,
                delims=["```", "\n"],
                priority=True,
                page_length=2000,
            )
        ):
            await bounded_gather(
                *map(
                    lambda cr: cr[0].send(
                        (getattr(cr[1], "mention", "") if not ind else "") + page
                    ),
                    channels_to_send_to,
                )
            )

        log.debug(f"Total pages sent: {ind+1}")

    async def cog_unload(self):
        self._task.cancel()

    @commands.group(name="patchnotes", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def patchnotes(self, ctx: commands.Context):
        """Manage patch notes settings"""
        await ctx.send_help()

    @patchnotes.group(name="streamlabs", invoke_without_command=True)
    async def patchnotes_streamlabs(self, ctx: commands.Context):
        """Manage Streamlabs patch notes settings"""
        return await ctx.send_help()

    @patchnotes_streamlabs.command(name="channel")
    async def patchnotes_streamlabs_channel(
        self, ctx: commands.Context, channel: GuildMessageable
    ):
        """Set the channel to post Streamlabs patch notes"""
        if not await self.config.chrome_path():
            return await ctx.send(
                f"Please contact the owner to setup chrome path using the command `{ctx.clean_prefix}patchnotes chromepath`"
            )
        await self.config.guild(ctx.guild).streamlabs.channel.set(channel.id)
        await ctx.send(f"Streamlabs patch notes will be posted in {channel.mention}")

    @patchnotes_streamlabs.command(name="pingrole")
    async def patchnotes_streamlabs_pingrole(
        self, ctx: commands.Context, role: discord.Role
    ):
        """Set the role to ping for Streamlabs patch notes"""
        if not await self.config.chrome_path():
            return await ctx.send(
                f"Please contact the owner to setup chrome path using the command `{ctx.clean_prefix}patchnotes chromepath`"
            )
        await self.config.guild(ctx.guild).streamlabs.pingrole.set(role)
        await ctx.send(f"{role.mention} will be pinged for Streamlabs patch notes")

    @patchnotes.group(name="twitch", invoke_without_command=True)
    async def patchnotes_twitch(self, ctx: commands.Context):
        """Manage Twitch patch notes settings"""
        return await ctx.send_help()

    @patchnotes_twitch.command(name="channel")
    async def patchnotes_twitch_channel(
        self, ctx: commands.Context, channel: GuildMessageable
    ):
        """Set the channel to post Twitch patch notes"""
        if not await self.config.chrome_path():
            return await ctx.send(
                f"Please contact the owner to setup chrome path using the command `{ctx.clean_prefix}patchnotes chromepath`"
            )
        await self.config.guild(ctx.guild).twitch.channel.set(channel.id)
        await ctx.send(f"Twitch patch notes will be posted in {channel.mention}")

    @patchnotes_twitch.command(name="pingrole")
    async def patchnotes_twitch_pingrole(
        self, ctx: commands.Context, role: discord.Role
    ):
        """Set the role to ping for Twitch patch notes"""
        if not await self.config.chrome_path():
            return await ctx.send(
                f"Please contact the owner to setup chrome path using the command `{ctx.clean_prefix}patchnotes chromepath`"
            )
        await self.config.guild(ctx.guild).twitch.pingrole.set(role)
        await ctx.send(f"{role.mention} will be pinged for Twitch patch notes")

    @patchnotes.group(name="obs", invoke_without_command=True)
    async def patchnotes_obs(self, ctx: commands.Context):
        """Manage OBS patch notes settings"""
        return await ctx.send_help()

    @patchnotes_obs.command(name="channel")
    async def patchnotes_obs_channel(
        self, ctx: commands.Context, channel: GuildMessageable
    ):
        """Set the channel to post OBS patch notes"""
        if not await self.config.obs_feed_name():
            return await ctx.send(
                f"Please contact the owner to setup obs patch notes feed using the command `{ctx.clean_prefix}patchnotes obs feedname`"
            )

        await self.config.guild(ctx.guild).obs.channel.set(channel.id)
        await ctx.send(f"OBS patch notes will be posted in {channel.mention}")

    @patchnotes_obs.command(name="pingrole")
    async def patchnotes_obs_pingrole(self, ctx: commands.Context, role: discord.Role):
        """Set the role to ping for OBS patch notes"""
        await self.config.guild(ctx.guild).obs.pingrole.set(role)
        await ctx.send(f"{role.mention} will be pinged for OBS patch notes")

    @patchnotes_obs.command(name="feedname")
    @commands.is_owner()
    async def patchnotes_obs_feedname(
        self, ctx: commands.Context, feed_name: str, feed_channel: GuildMessageable
    ):
        """Set the feed name for OBS patch notes"""
        rsscog = self.bot.get_cog("RSS")
        if rsscog is None:
            return await ctx.send(
                "RSS cog is not loaded. The RSS cog needs to be loaded to publish OBS patch notes."
            )

        if not await rsscog._check_feed_existing(ctx, feed_name, feed_channel):
            return await ctx.send(
                f"{feed_name} doesn't exist in {feed_channel.mention}. Please check the feed name and channel. Use `{ctx.clean_prefix}rss listall` to see the available feeds."
            )

        await self.config.obs_feed_name.set(feed_name)
        await ctx.send(f"OBS patch notes feed name set to {feed_name}")

    @patchnotes.command(name="delay")
    @commands.is_owner()
    async def patchnotes_delay(self, ctx: commands.Context, delay: TimeDelta):
        """Set the delay between checking for new patch notes"""
        await self.config.delay.set(delay.total_seconds())
        await ctx.send(f"Delay set to {humanize_timedelta(timedelta=delay)}")

    @patchnotes.command(name="chromepath")
    @commands.is_owner()
    async def patchnotes_chromepath(self, ctx: commands.Context, path: Path):
        """Set the path to chrome executable"""
        if not BaseScraper.is_executable(path):
            return await ctx.send("The path provided is not an executable")
        await self.config.chrome_path.set(str(path))
        await ctx.send(f"Chrome path set to {path}")

    @patchnotes.command(name="force")
    @commands.is_owner()
    async def patchnotes_force(self, ctx: commands.Context):
        """Force check for new patch notes"""
        await self.check_for_new_patchnotes()
        await ctx.send("Forced check for new patch notes")

    @patchnotes.command(name="info")
    async def patchnotes_info(self, ctx: commands.Context):
        """Get the current patch notes settings"""
        curent_guild = await self.config.guild(ctx.guild).all()
        global_data = await self.config.all()

        msg = ""
        for feed_name in ["streamlabs", "twitch", "obs"]:
            msg += f"__{feed_name.upper()}__\n"
            msg += f"Channel: {getattr(ctx.guild.get_channel(curent_guild[feed_name]['channel']), 'mention', 'Channel not set')}\n"
            msg += f"Ping Role: {getattr(ctx.guild.get_role(curent_guild[feed_name]['pingrole']), 'mention', 'Role not set')}\n"
            msg += f"Last posted version: {global_data['last_posted_version'][feed_name]}\n\n"

        msg += f"Delay: {humanize_timedelta(seconds=global_data['delay'])}\n"
        msg += f"Chrome path: {global_data['chrome_path']}\n"

        await ctx.send(msg)

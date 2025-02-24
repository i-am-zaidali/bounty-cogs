import asyncio
import logging
import re
import typing
from collections import defaultdict

import discord
import redbot.core.utils.chat_formatting as cf
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.vendored.discord.ext import menus

from .views import Paginator

WEBHOOK_RE = re.compile(
    r"discord(?:app)?.com/api/webhooks/(?P<id>[0-9]{17,21})/(?P<token>[A-Za-z0-9\.\-\_]{60,68})"
)


class WebhookConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Webhook:
        try:
            return get_webhook_from_link(ctx.bot, argument)
        except ValueError as e:
            raise commands.BadArgument(str(e))


def get_webhook_from_link(bot: Red, link: str) -> discord.Webhook:
    match = WEBHOOK_RE.search(link)
    if not match:
        raise ValueError("That doesn't look like a webhook link.")
    webhook = discord.Webhook.from_url(
        match.group(0), session=bot.http._HTTPClient__session
    )
    return webhook


log = logging.getLogger("red.craycogs.wiretap")


class WireTap(commands.Cog):
    """A cog that listens for trigger words in channels and sends a message to a spy channel when it spots one"""

    __author__ = "crayyy_zee"
    __version__ = "0.0.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)

        self.config.register_guild(webhook=None)

        self.config.register_channel(
            triggers={}  # {word: channel id}
        )

        self.cooldown = commands.CooldownMapping.from_cooldown(
            4, 60, commands.BucketType.member
        )

    # region red cog methods

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        # Requester can be "discord_deleted_user", "owner", "user", or "user_strict"
        return

    async def red_get_data_for_user(self, *, requester: str, user_id: int):
        # Requester can be "discord_deleted_user", "owner", "user", or "user_strict"
        return

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        pass

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()

    # endregion

    # region Listeners

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if not isinstance(message.channel, discord.TextChannel):
            return

        if (
            message.author.bot
            or await self.bot.cog_disabled_in_guild(self, message.guild)
            or not await self.bot.allowed_by_whitelist_blacklist(message.author)
        ):
            return

        triggers: dict[str, int] = await self.config.channel(message.channel).triggers()
        if not triggers:
            return

        all_triggers = set[str](triggers.keys())
        triggered = all_triggers.intersection(
            word for word in message.content.casefold().split()
        )

        if not triggered:
            return

        bucket = self.cooldown.get_bucket(message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            return

        channel_triggers = defaultdict[int, list[str]](list)
        for trigger in triggered:
            channel_triggers[triggers[trigger]].append(trigger)

        for spy_channel_id, trigger_words in channel_triggers.items():
            spy_channel = message.guild.get_channel(spy_channel_id)
            if not spy_channel:
                continue

            spy_channel = typing.cast(discord.TextChannel, spy_channel)
            webhook = await self.config.guild(message.guild).webhook()
            if not webhook:
                return await spy_channel.send(
                    f"WireTap bug triggered in {message.channel.mention} for the word(s): {', '.join(trigger_words)}\n{message.jump_url}",
                    embed=discord.Embed(
                        description=cf.quote(message.content),
                    ).set_author(
                        name=message.author.display_name,
                        icon_url=message.author.display_avatar.url,
                    ),
                )

            webhook = discord.Webhook.from_url(
                webhook, session=self.bot.http._HTTPClient__session
            )
            await webhook.send(
                content=message.content,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
            )

    # endregion

    # region Commands
    @commands.group(name="wiretap")
    @commands.guild_only()
    @commands.admin()
    async def wiretap(self, ctx: commands.Context):
        """Wiretap commands"""

    @wiretap.command(name="addbug")
    async def addbug(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel = commands.parameter(
            displayed_name="bugged channel",
        ),
        to_channel: discord.TextChannel = commands.parameter(
            displayed_name="spy channel",
        ),
        trigger_word: str = commands.parameter(
            displayed_name="trigger word",
            description="The word that will trigger the wiretap",
            converter=str.casefold,
        ),
    ):
        """Add a channel to be wiretapped

        The bot will listen for the trigger word in the bugged channel and send a message to the spy channel when it spots it."""
        async with self.config.channel(channel).triggers() as triggers:
            triggers[trigger_word] = to_channel.id
        await ctx.send(
            f"Added {channel.mention} to be wiretapped for the word: `{trigger_word}`"
        )

    @wiretap.command(name="removebug")
    async def removebug(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel = commands.parameter(
            displayed_name="bugged channel",
        ),
        trigger_word: str = commands.parameter(
            displayed_name="trigger word",
            description="The word that will trigger the wiretap",
            converter=str.casefold,
        ),
    ):
        """Remove a channel from being wiretapped"""
        async with self.config.channel(channel).triggers() as triggers:
            if trigger_word in triggers:
                del triggers[trigger_word]
                await ctx.send(
                    f"Removed {channel.mention} from being wiretapped for the word: `{trigger_word}`"
                )

            else:
                await ctx.send(
                    f"{channel.mention} is not being wiretapped for the word: `{trigger_word}`"
                )

    @wiretap.command(name="listbugs")
    async def listbugs(self, ctx: commands.Context):
        """List all wiretaps"""
        triggers = await self.config.all_channels()
        if not triggers:
            return await ctx.send("No channels are being wiretapped")

        class Source(menus.ListPageSource):
            def __init__(self, data: dict[int, dict[str, int]]):
                items = [(k, vk, vv) for k, v in data.items() for vk, vv in v.items()]
                super().__init__(items, per_page=10)

            async def format_page(
                self, menu: Paginator, entries: list[tuple[int, str, int]]
            ):
                offset = menu.current_page * self.per_page
                embed = discord.Embed(
                    title="Wiretap List",
                    description="List of all wiretaps",
                    color=await ctx.embed_color(),
                )
                for index, (trigger, bugged, spy) in enumerate(entries, offset + 1):
                    embed.add_field(
                        name=f"{index}. <#{bugged}> -> <#{spy}>",
                        value=f"Trigger: `{trigger}`",
                    )

                embed.set_footer(
                    text=f"Page {menu.current_page + 1}/{self.get_max_pages()}"
                )
                return embed

        source = Source(triggers)
        paginator = Paginator(source)
        await paginator.start(ctx)

    @wiretap.command(name="webhook")
    async def webhook(
        self,
        ctx: commands.Context,
        webhook: discord.Webhook = commands.parameter(
            displayed_name="webhook link",
            description="The webhook link to send messages through",
            converter=WebhookConverter,
        ),
    ):
        """Set the webhook to send the messages to"""
        await self.config.guild(ctx.guild).webhook.set(webhook.url)
        await ctx.send(f"Set the webhook to {webhook.url}")

    # endregion

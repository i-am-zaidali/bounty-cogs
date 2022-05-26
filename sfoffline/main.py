import asyncio
import time
import typing
from datetime import datetime

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list, pagify


class SFOffline(commands.Cog):
    """
    Check when a user was last seen online.

    This also tracks their typing + reactions + messages incase they are on invisible mode."""

    online_statuses = [discord.Status.online, discord.Status.idle, discord.Status.dnd]
    offline_status = discord.Status.offline

    __version__ = "1.0.1"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot: Red):
        self.bot = bot
        self.cache: typing.Dict[int, typing.Optional[float]] = {}

        self._task = self.save_to_config_every_5.start()

        self.config = Config.get_conf(self, 2784481001, force_registration=True)
        self.config.register_user(seen=None)

        self.config.register_global(schema_version=1)  # just future proofing lmao

    async def build_cache(self):
        await self.bot.wait_until_red_ready()
        user_data = await self.config.all_users()
        for user_id, data in user_data.items():
            self.cache[user_id] = data["seen"]

        for guild in self.bot.guilds:
            for member in guild.members:
                if member.status is self.offline_status:
                    self.cache.update({member.id: time.time()})


    async def to_config(self):
        for user_id, seen in self.cache.copy().items():
            await self.config.user_from_id(user_id).seen.set(seen)

    def cog_unload(self):
        self._task.cancel()
        asyncio.create_task(self.to_config())

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    @tasks.loop(minutes=5)
    async def save_to_config_every_5(self):
        await self.to_config()
        self.cache.clear()
        await self.build_cache()

    @commands.Cog.listener()
    async def on_typing(
        self,
        channel: discord.abc.Messageable,
        user: typing.Union[discord.User, discord.Member],
        when: datetime,
    ):
        if isinstance(user, discord.Member):
            if user.bot:
                return

            status = user.status

            if status in self.online_statuses:
                # if they are online, don't update their last seen time
                # it will be updated in on_member_update
                return

            self.cache.update({user.id: time.time()})

    @commands.Cog.listener()
    async def on_reaction_add(
        self, reaction: discord.Reaction, user: typing.Union[discord.User, discord.Member]
    ):
        if isinstance(user, discord.Member):
            if user.bot:
                return

            status = user.status

            if status in self.online_statuses:
                # if they are online, don't update their last seen time
                # it will be updated in on_member_update
                return

            self.cache.update({user.id: time.time()})

    @commands.Cog.listener()
    async def on_reaction_remove(
        self, reaction: discord.Reaction, user: typing.Union[discord.User, discord.Member]
    ):
        if isinstance(user, discord.Member):
            if user.bot:
                return

            status = user.status

            if status in self.online_statuses:
                # if they are online, don't update their last seen time
                # it will be updated in on_member_update
                return

            self.cache.update({user.id: time.time()})

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if isinstance(message.author, discord.Member):
            if message.author.bot:
                return

            if message.author.status in self.online_statuses:
                # if they are online, don't update their last seen time
                # it will be updated in on_member_update
                return

            self.cache.update({message.author.id: time.time()})

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.bot:
            return

        if before.status != after.status:
            if after.status is self.offline_status or before.status is self.offline_status:
                self.cache.update({after.id: time.time()})

    @staticmethod
    def get_formatted_timestamps(time: float):
        time = int(time)
        return f"<t:{time}:F> - <t:{time}:R>"

    @commands.group(name="lastonline", aliases=["lastseen", "seen"], invoke_without_command=True)
    @commands.guild_only()
    async def lastonline(self, ctx: commands.Context, user: discord.Member):
        """
        See when the given user was last online."""
        if user.bot:
            return await ctx.maybe_send_embed("Sorry, I don't track bots.")

        last_online = self.cache.get(user.id, None)
        if not last_online:
            statement = f"I have never seen {user.mention} offline before."

        else:
            statement = (
                f"{user.mention} was last seen at {self.get_formatted_timestamps(last_online)}"
            )

        if user.status in self.online_statuses:
            statement = f"{user.mention} is currently online."

        return await ctx.maybe_send_embed(statement)

    @lastonline.command(name="top")
    @commands.guild_only()
    async def lastonline_top(self, ctx: commands.Context, x: int):
        """See a top x leaderboard of most offline users.

        If you wanna see all offline users right now, use `[p]lastonline all` instead."""

        if not self.cache:
            return await ctx.maybe_send_embed("I haven't tracked any offline users yet.")

        offline_users = dict(
            sorted(
                filter(
                    lambda x: (user := ctx.guild.get_member(x[0]))
                    and user.status is self.offline_status,
                    self.cache.copy().items(),
                ),
                key=lambda x: x[1],
            )
        )

        final = ""

        for ind, (user_id, lastseen) in enumerate(offline_users.items(), 1):
            final += f"{ind}. <@{user_id}> - {self.get_formatted_timestamps(lastseen)}\n"

            if ind == x:
                break

        for page in pagify(final):
            embed = discord.Embed(
                title="Top {} Offline Users".format(x), description=page, color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @lastonline.command(name="offline", aliases=["all"])
    @commands.guild_only()
    async def lastonline_offline(self, ctx: commands.Context):
        """
        Show a list of all offline users right now."""
        if not self.cache:
            return await ctx.maybe_send_embed(
                "I haven't tracked any users going offline or coming online yet."
            )

        final = ""

        sorted_dict = dict(
            sorted(
                filter(
                    lambda x: (user := ctx.guild.get_member(x[0]))
                    and user.status is self.offline_status,
                    self.cache.copy().items(),
                ),
                key=lambda x: x[1],
            )
        )

        for ind, (user_id, last_seen) in enumerate(sorted_dict.items(), 1):
            final += (
                f"{ind}. <@{user_id}> ({user_id}) - {self.get_formatted_timestamps(last_seen)}\n"
            )

        for page in pagify(final):
            embed = discord.Embed(
                title="All Offline Users", description=page, color=discord.Color.dark_purple()
            )
            await ctx.send(embed=embed)

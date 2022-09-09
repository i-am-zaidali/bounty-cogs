import asyncio
import typing

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf


def is_staff():
    async def predicate(ctx: commands.Context):
        if await ctx.bot.is_owner(ctx.author):
            return True

        if (await ctx.cog.config.guild(ctx.guild).staff_role()) in ctx.author._roles:
            return True

    return commands.check(predicate)


class RepManager(commands.Cog):
    """
    Manage a user's reputation in your server."""

    ADD = "added"
    REMOVE = "removed"
    RESET = "resetted"

    __version__ = "1.0.1"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(self, 2784481001, force_registration=True)
        self.config.register_guild(staff_role=None, log_channel=None)
        self.config.register_member(rep=0)

        self.cache: typing.Dict[int, typing.Dict[int, int]] = {}

        self._task = self.save_to_config_every_5.start()

    async def build_cache(self):
        data = await self.config.all_members()
        self.cache = {
            guild_id: {
                member_id: member_data["rep"] for member_id, member_data in guild_data.items()
            }
            for guild_id, guild_data in data.items()
        }

    async def to_config(self):
        for guild_id, data in self.cache.copy().items():
            for member_id, rep in data.items():
                await self.config.member_from_ids(guild_id, member_id).rep.set(rep)

    @tasks.loop(minutes=5)
    async def save_to_config_every_5(self):
        await self.to_config()
        self.cache.clear()
        await self.build_cache()

    def cog_unload(self):
        asyncio.create_task(self.to_config())

        self._task.cancel()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {cf.humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    async def send_logging_embed(
        self,
        ctx: commands.Context,
        members: typing.List[discord.Member],
        amount: int,
        action: str,
        reason: str = None,
    ):
        message = (
            (
                f"**{cf.humanize_number(amount)}** {'point' if amount == 1 else 'points'} rep "
                f"was {action} to {cf.humanize_list([member.mention for member in members])} by {ctx.author.mention}"
            )
            if action in [self.ADD, self.REMOVE]
            else (
                f"{cf.humanize_list([member.mention for member in members])}'s rep was {action} by {ctx.author.mention}."
            )
        )
        embed = discord.Embed(
            title=f"Reputation updated for {len(members)} member(s).",
            description=message,
            timestamp=ctx.message.created_at,
        )
        embed.add_field(name="**REASON: **", value=cf.box(reason))

        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
        embed.set_footer(text=f"{ctx.guild.name} ({ctx.guild.id})")

        log_channel = await self.config.guild(ctx.guild).log_channel()
        if log_channel is not None:
            log_channel = ctx.guild.get_channel(log_channel)

        log_channel = log_channel or ctx

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    @commands.group(name="rep", aliases=["reputation"], invoke_without_command=True)
    async def rep(self, ctx: commands.Context, member: discord.Member = None):
        """
        Check a user's reputation in your server.

        If no user is specified, the user who invoked the command will be used.
        """
        member = member or ctx.author

        rep = self.cache.get(ctx.guild.id, {}).get(member.id, 0)
        await ctx.maybe_send_embed(f"{member.mention} has {rep} reputation.")

    @rep.command(name="add")
    @is_staff()
    async def rep_add(
        self,
        ctx: commands.Context,
        amount: float,
        members_or_voice: typing.Union[discord.VoiceChannel, commands.Greedy[discord.Member]],
        *,
        reason: str,
    ):
        """
        Add a certain amount of reputation to a user.
        """

        members: typing.List[discord.Member] = members_or_voice.members if isinstance(members_or_voice, discord.VoiceChannel) else members_or_voice

        if not members:
            return await ctx.send_help()

        for member in members:
            rep = self.cache.setdefault(ctx.guild.id, {}).setdefault(member.id, 0)
            rep += amount
            self.cache[ctx.guild.id][member.id] = rep

        await ctx.maybe_send_embed(
            f"{cf.humanize_list([member.mention for member in members])} now have {rep} reputation."
        )

        await self.send_logging_embed(ctx, members, amount, self.ADD, reason)

    @rep.command(name="remove")
    @is_staff()
    async def rep_remove(
        self,
        ctx: commands.Context,
        amount: float,
        members: commands.Greedy[discord.Member],
        *,
        reason: str,
    ):
        """
        Remove a certain amount of reputation from a user."""

        members: typing.List[discord.Member] = [member for member in members]

        failed = []
        success = []

        for member in members:
            rep = self.cache.setdefault(ctx.guild.id, {}).setdefault(member.id, 0)

            if rep == 0 or rep < amount:
                failed.append(member)

            else:
                rep -= amount

                self.cache[ctx.guild.id][member.id] = rep

                success.append(member)

        if members == failed:
            return await ctx.maybe_send_embed(
                "All of the given members either had 0 reputation or had less rep than the amount given to remove."
            )

        await self.send_logging_embed(ctx, members, amount, self.REMOVE, reason)

        return await ctx.maybe_send_embed(
            f"Removed {amount} rep from {cf.humanize_list([member.mention for member in success])}.\nThey now have {rep} reputation.\n\n"
            + (
                f"{cf.humanize_list([member.mention for member in failed])} had 0 reputation or had less rep than the amount given to remove."
                if failed
                else ""
            )
        )

    @rep.command(name="reset")
    @is_staff()
    async def rep_reset(
        self, ctx: commands.Context, members: commands.Greedy[discord.Member], *, reason: str
    ):
        """
        Reset a user's reputation to 0.

        If no user is specified, the user who invoked the command will be used.
        """

        members: typing.List[discord.Member] = [member for member in members]

        failed = []
        success = []

        for member in members:
            rep = self.cache.setdefault(ctx.guild.id, {}).setdefault(member.id, 0)

            if rep == 0:
                failed.append(member)

            else:
                self.cache[ctx.guild.id][member.id] = 0

                success.append(member)

        if members == failed:
            return await ctx.maybe_send_embed(
                "All of the given members already had 0 reputation so I couldn't reset any of them."
            )

        await self.send_logging_embed(ctx, members, 0, self.RESET, reason)

        return await ctx.maybe_send_embed(
            f"Reset {cf.humanize_list([member.mention for member in success])}'s reputation to 0.\n\n"
            + (
                f"{cf.humanize_list([member.mention for member in failed])} had 0 reputation so I couldn't reset them."
                if failed
                else ""
            )
        )

    @rep.command(name="leaderboard", aliases=["lb"])
    async def rep_lb(
        self, ctx: commands.Context, amount: typing.Optional[int] = None, reversed=True
    ):
        """
        See a ranked list of users with the most/least reputation.

        The amount if the number of users to show on the leaderboard. (defaults to 10)

        If the reversed argument is not used, it defaults to True
        which shows the leaderboard from highest to lowest.
        Pass False/0 to show the leaderboard from lowest to highest instead.
        """

        amount = amount or 10
        if amount < 1:
            return await ctx.maybe_send_embed("You must specify an amount greater than 0.")

        members = sorted(
            filter(
                lambda x: ctx.guild.get_member(x[0]) and x[1],
                self.cache.get(ctx.guild.id, {}).items(),
            ),
            key=lambda x: x[1],
            reverse=reversed,
        )[:amount]

        if not members:
            return await ctx.maybe_send_embed("There are no users with reputation in this server.")

        members = [
            f"**{ind}**. <@{member[0]}>:\t**{cf.humanize_number(member[1])}**"
            for ind, member in enumerate(members, 1)
        ]

        h_or_l = "highest" if reversed else "lowest"

        await ctx.maybe_send_embed(
            f"***Top {amount} users with {h_or_l} rep***\n\n" + "\n".join(members)
        )

    @commands.group(name="repset", invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def repset(self, ctx: commands.Context):
        """
        Set the settings for the reputation system.
        """

    @repset.command(name="staffrole")
    async def repset_staffrole(self, ctx: commands.Context, role: discord.Role):
        """
        Set the staff role for the reputation system.

        This role will be able to use the reputation commands.
        """
        await ctx.tick()
        await self.config.guild(ctx.guild).staff_role.set(role.id)
        await ctx.maybe_send_embed(f"Staff role set to {role.mention}.")

    @repset.command(name="logchannel")
    async def repset_logchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Set the log channel for the reputation system.

        This channel will be used to log all reputation changes.
        """
        await ctx.tick()
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.maybe_send_embed(f"Log channel set to {channel.mention}.")

    @repset.command(name="showsettings", aliases=["show", "ss"])
    async def repset_showsettings(self, ctx: commands.Context):
        """
        Show the current settings for the reputation system.
        """
        staff_role = await self.config.guild(ctx.guild).staff_role()
        log_channel = await self.config.guild(ctx.guild).log_channel()

        if staff_role is None:
            staff_role = "Not set."
        else:
            staff_role = ctx.guild.get_role(int(staff_role))
            staff_role = getattr(
                staff_role, "mention", "Couldn't find set role. ID: {}".format(staff_role)
            )

        if log_channel is None:
            log_channel = "Not set."
        else:
            log_channel = ctx.guild.get_channel(int(log_channel))
            log_channel = getattr(
                log_channel, "mention", "Couldn't find set channel. ID: {}".format(log_channel)
            )

        embed = discord.Embed(
            title="Reputation Settings",
            description=f"Current Cog Version: **{self.__version__}**\n\nStaff role: {staff_role}\nLog channel: {log_channel}",
            colour=discord.Colour.blurple(),
        )

        await ctx.send(embed=embed)

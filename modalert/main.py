import asyncio
import datetime
import logging
import typing

import discord
import redbot.core.utils.chat_formatting as cf
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.antispam import AntiSpam

log = logging.getLogger("red.modalert")

timedelta_converter = commands.get_timedelta_converter(
    allowed_units=["days", "hours", "minutes", "seconds"],
    minimum=datetime.timedelta(seconds=30),
)


class ModAlert(commands.Cog):
    """A cog that auto deletes messages that are replied to with a mod ping a specific threshold number of times.

    It also optionally timeouts the user who sent the original message."""

    __author__ = "crayyy_zee"
    __version__ = "0.0.2"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_guild(
            mod_roles=[],
            mod_users=[],
            log_channel=None,
            alert_threshold=3,
            timeout_duration=None,
            timeframe_seconds=300,
        )
        # a dict mapping message ids to a tuple of (AntiSpam instance, list of user ids who alerted)
        self.reports: dict[int, tuple[AntiSpam, list[int]]] = {}

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(
            self.__version__, self.__author__
        )
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not message.reference:
            return

        if not message.mentions and not message.role_mentions:
            return

        msg_reference = message.reference.resolved

        if msg_reference.is_system():
            return

        if msg_reference.author == message.author:
            return

        guild_config = self.config.guild(message.guild)
        mod_role_ids: set[int] = set(await guild_config.mod_roles())
        mod_user_ids: set[int] = set(await guild_config.mod_users())
        log_channel_id = await guild_config.log_channel()
        alert_threshold = await guild_config.alert_threshold()
        timeout_duration = await guild_config.timeout_duration()
        timeframe_seconds = await guild_config.timeframe_seconds()

        message_mentions = {user.id for user in message.mentions} | {
            role.id for role in message.role_mentions
        }

        mod_pinged = (
            len(message_mentions.intersection(mod_user_ids, mod_role_ids)) > 0
        )
        if not mod_pinged:
            return

        msg_id = msg_reference.id
        if msg_id not in self.reports:
            self.reports[msg_id] = (
                AntiSpam(
                    [
                        (
                            datetime.timedelta(seconds=timeframe_seconds),
                            alert_threshold - 1,
                        )
                    ]
                ),
                [],
            )
        antispam, alerted_user_ids = self.reports[msg_id]
        if message.author.id in alerted_user_ids:
            return
        antispam.stamp()
        alerted_user_ids.append(message.author.id)

        if antispam.spammy:
            message_deleted = False
            user_timed_out = False

            original_message = message.reference.resolved
            if original_message and isinstance(
                original_message, discord.Message
            ):
                try:
                    await original_message.delete()
                    message_deleted = True
                except discord.Forbidden:
                    log.warning(
                        f"ModAlert: Missing permissions to delete message {original_message.id} in guild {message.guild.id}"
                    )
            else:
                log.warning(
                    f"ModAlert: Could not resolve original message {msg_id} in guild {message.guild.id}"
                )
            if timeout_duration:
                try:
                    await message.author.timeout(
                        datetime.timedelta(seconds=timeout_duration),
                        reason=f"Mod Alert: Message reported by {alert_threshold} users within {cf.humanize_timedelta(seconds=timeframe_seconds)}",
                    )
                    user_timed_out = True
                except discord.Forbidden:
                    log.warning(
                        f"ModAlert: Missing permissions to timeout user {message.author.id} in guild {message.guild.id}"
                    )
            if log_channel_id:
                log_channel = message.guild.get_channel(log_channel_id)
                if log_channel:
                    alerted_users = [
                        message.guild.get_member(user_id)
                        for user_id in set(alerted_user_ids)
                    ]
                    user_mentions = ", ".join(
                        user.mention
                        for user in alerted_users
                        if user is not None
                    )
                    await log_channel.send(
                        f"Message {message.reference.jump_url} was flagged because it was reported by {alert_threshold} users ({user_mentions}). "
                        f"{'The message was deleted' if message_deleted else 'Failed to delete the message'}"
                        f"{f'and the user was timed out for {cf.humanize_timedelta(seconds=timeout_duration)}' if user_timed_out else ''}."
                    )

            self.reports.pop(msg_id, None)

    @commands.group(name="modalert")
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def modalert_group(self, ctx: commands.Context):
        """Mod Alert configuration commands."""
        pass

    @modalert_group.group(name="modrole")
    async def modrole_group(self, ctx: commands.Context):
        """Commands to manage mod roles for Mod Alert."""
        pass

    @modrole_group.command(name="add")
    async def modrole_add(self, ctx: commands.Context, role: discord.Role):
        """Add a mod role for Mod Alert."""
        current_roles = await self.config.guild(ctx.guild).mod_roles()
        if role.id in current_roles:
            await ctx.send(f"The role {role.mention} is already a mod role.")
            return
        current_roles.append(role.id)
        await self.config.guild(ctx.guild).mod_roles.set(current_roles)
        await ctx.send(f"Added {role.mention} as a mod role.")

    @modrole_group.command(name="remove")
    async def modrole_remove(self, ctx: commands.Context, role: discord.Role):
        """Remove a mod role for Mod Alert."""
        current_roles = await self.config.guild(ctx.guild).mod_roles()
        if role.id not in current_roles:
            await ctx.send(f"The role {role.mention} is not a mod role.")
            return
        current_roles.remove(role.id)
        await self.config.guild(ctx.guild).mod_roles.set(current_roles)
        await ctx.send(
            f"Removed {role.mention} from mod roles.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @modrole_group.command(name="list")
    async def modrole_list(self, ctx: commands.Context):
        """List all mod roles for Mod Alert."""
        current_roles = await self.config.guild(ctx.guild).mod_roles()
        if not current_roles:
            await ctx.send("No mod roles have been set.")
            return
        roles = [ctx.guild.get_role(role_id) for role_id in current_roles]
        role_mentions = ", ".join(
            role.mention for role in roles if role is not None
        )
        await ctx.send(
            f"Mod roles: {role_mentions}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @modalert_group.group(name="moduser")
    async def moduser_group(self, ctx: commands.Context):
        """Commands to manage mod users for Mod Alert."""
        pass

    @moduser_group.command(name="add")
    async def moduser_add(self, ctx: commands.Context, user: discord.Member):
        """Add a mod user for Mod Alert."""
        current_users = await self.config.guild(ctx.guild).mod_users()
        if user.id in current_users:
            await ctx.send(f"The user {user.mention} is already a mod user.")
            return
        current_users.append(user.id)
        await self.config.guild(ctx.guild).mod_users.set(current_users)
        await ctx.send(
            f"Added {user.mention} as a mod user.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @moduser_group.command(name="remove")
    async def moduser_remove(self, ctx: commands.Context, user: discord.Member):
        """Remove a mod user for Mod Alert."""
        current_users = await self.config.guild(ctx.guild).mod_users()
        if user.id not in current_users:
            await ctx.send(f"The user {user.mention} is not a mod user.")
            return
        current_users.remove(user.id)
        await self.config.guild(ctx.guild).mod_users.set(current_users)
        await ctx.send(
            f"Removed {user.mention} from mod users.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @moduser_group.command(name="list")
    async def moduser_list(self, ctx: commands.Context):
        """List all mod users for Mod Alert."""
        current_users = await self.config.guild(ctx.guild).mod_users()
        if not current_users:
            await ctx.send("No mod users have been set.")
            return
        users = [ctx.guild.get_member(user_id) for user_id in current_users]
        user_mentions = ", ".join(
            user.mention for user in users if user is not None
        )
        await ctx.send(
            f"Mod users: {user_mentions}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @modalert_group.command(name="logchannel", aliases=["logchan"])
    async def logchannel_set(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel] = None,
    ):
        """Set the log channel for Mod Alert. Use no channel to unset."""
        await self.config.guild(ctx.guild).log_channel.set(
            channel.id if channel else None
        )
        if channel:
            await ctx.send(
                f"Set the log channel to {channel.mention}.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await ctx.send("Unset the log channel.")

    @modalert_group.command(name="threshold")
    async def threshold_set(self, ctx: commands.Context, threshold: int):
        """Set the alert threshold for Mod Alert."""
        if threshold < 1:
            await ctx.send("Threshold must be at least 1.")
            return
        await self.config.guild(ctx.guild).alert_threshold.set(threshold)
        await ctx.send(
            f"Set the alert threshold to {threshold}. "
            f"Now if there are {threshold} mod pings on a message in "
            f"{cf.humanize_timedelta(seconds=await self.config.guild(ctx.guild).timeframe_seconds())}, "
            "the message will be deleted and the user may be timed out."
        )

    @modalert_group.command(name="timeout")
    async def timeout_set(
        self,
        ctx: commands.Context,
        duration: typing.Optional[datetime.timedelta] = commands.param(
            converter=timedelta_converter, default=None
        ),
    ):
        """Set the timeout duration for Mod Alert. Use no duration to disable timeouts.

        Duration format examples: 10m, 1h, 1d
        """
        if duration is not None and duration.total_seconds() < 60:
            await ctx.send("Timeout duration must be at least 1 minute.")
            return
        await self.config.guild(ctx.guild).timeout_duration.set(
            int(duration.total_seconds()) if duration else None
        )
        if duration:
            await ctx.send(
                f"Set the timeout duration to {cf.humanize_timedelta(seconds=duration.total_seconds())}."
            )
        else:
            await ctx.send("Disabled timeouts for Mod Alert.")

    @modalert_group.command(name="timeframe")
    async def timeframe_set(
        self,
        ctx: commands.Context,
        timeframe: datetime.timedelta = commands.param(
            converter=timedelta_converter, default=datetime.timedelta(minutes=5)
        ),
    ):
        """Set the timeframe for Mod Alert.

        This is the time period in which mod pings are counted towards the alert threshold.
        """
        if timeframe.total_seconds() < 30:
            await ctx.send("Timeframe must be at least 30 seconds.")
            return
        await self.config.guild(ctx.guild).timeframe_seconds.set(
            int(timeframe.total_seconds())
        )
        await ctx.send(
            f"Set the timeframe to {cf.humanize_timedelta(seconds=timeframe.total_seconds())} "
            f"i.e if there are {await self.config.guild(ctx.guild).alert_threshold()} "
            "mod pings within this period, the message will be deleted and the user may be timed out."
        )

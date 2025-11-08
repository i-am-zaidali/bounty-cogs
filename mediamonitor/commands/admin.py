import datetime
import typing

import discord
import discord.ui
from redbot.core import commands
from redbot.core.utils import chat_formatting as cf
from redbot.core.utils.views import ConfirmView

from mediamonitor.views.monitoringchannelselect import MonitoringChannelSelect

from ..abc import MixinMeta
from ..common.converters import (
    MemoryUnits,
    ReadableMemoryToBytes,
    TimeConverter,
    ValidRegex,
    bytes_to_readable_memory,
)
from ..common.models import ActionTypes
from ..views.whitelistedusers import WhitelistedUsersSelect


class Admin(MixinMeta):
    @commands.group(name="mediamonitor", aliases=["medmon"])
    @commands.bot_has_guild_permissions(
        ban_members=True, kick_members=True, mute_members=True, moderate_members=True
    )
    async def mediamonitor(self, ctx: commands.Context):
        """The base command for MediaMonitor cog commands."""

    @mediamonitor.command(name="filenameregex", aliases=["fnregex", "fnr", "regex"])
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_filenameregex(
        self,
        ctx: commands.Context,
        *,
        regex: typing.Optional[str] = commands.param(
            converter=typing.Optional[ValidRegex], default=None
        ),
    ):
        """Set the filename regex pattern to monitor media files.

        This regex will be used to match against the filenames of media attachments in messages.
        If a filename matches the regex, it will be considered a violation.

        Example:
        ```
        ^.*(explicit|nsfw).*\\.(jpg|png|gif)$
        ```
        This regex will match any filename that contains "explicit" or "nsfw" and ends with .jpg, .png, or .gif.
        """
        if regex is None:
            confirm_view = ConfirmView(timeout=30)
            await ctx.send(
                "You are about to clear the filename regex. This will stop monitoring based on filename patterns.",
                view=confirm_view,
            )
            await confirm_view.wait()
            if not confirm_view.result:
                await ctx.send("Operation cancelled. Filename regex remains unchanged.")
                return
            regex = ""

        async with self.db.get_conf(ctx.guild) as guild_settings:
            guild_settings.filename_regex = regex
        await ctx.tick()

    @mediamonitor.command(name="filesizelimit", alias=["sizelim", "fslimit"])
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_filesizelimit(
        self,
        ctx: commands.Context,
        size: int = commands.param(
            converter=ReadableMemoryToBytes(
                MemoryUnits.B | MemoryUnits.KB | MemoryUnits.MB
            ),
            default=None,
        ),
    ):
        """Set the file size limit that media attachments must be less than.

        If a media attachment has a size greater than this limit, a violation will be logged.
        The size must be in human readable format.
        i.e 2mb, 200kb, etc."""

        if not size:
            confirm_view = ConfirmView(timeout=30)
            await ctx.send(
                "You are about to clear the file size limit. This will stop monitoring based on file size.",
                view=confirm_view,
            )
            await confirm_view.wait()
            if not confirm_view.result:
                await ctx.send(
                    "Operation cancelled. File size limit remains unchanged."
                )
                return
            size = 0

        async with self.db.get_conf(ctx.guild) as guild_settings:
            guild_settings.file_size_limit_bytes = size
        await ctx.tick()

    @mediamonitor.command(name="blacklistedfiletypes", aliases=["blft", "bft"])
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_blacklistedfiletypes(
        self, ctx: commands.Context, *filetypes: str
    ):
        """Set the blacklisted file types (extensions) to monitor.

        If a media attachment has a file type that is in this list, a violation will be logged.
        File types should be provided without a leading dot. i.e exe, bat, cmd

        To clear the blacklisted file types, run the command without any arguments.
        """
        if len(filetypes) == 0:
            confirm_view = ConfirmView(timeout=30)
            await ctx.send(
                "You are about to clear the blacklisted file types. This will stop monitoring based on file types.",
                view=confirm_view,
            )
            await confirm_view.wait()
            if not confirm_view.result:
                await ctx.send(
                    "Operation cancelled. Blacklisted file types remain unchanged."
                )
                return
            filetypes = []

        async with self.db.get_conf(ctx.guild) as guild_settings:
            guild_settings.blacklisted_file_types = [*filetypes]
        await ctx.tick()

    @mediamonitor.command(
        name="deleteonviolation", aliases=["delonviolation", "delonvio", "dov"]
    )
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_deleteonviolation(
        self,
        ctx: commands.Context,
        toggle: bool,
    ):
        """Set whether to delete messages with media attachments that violate the monitoring rules.

        If set to True, messages with violating media attachments will be deleted.
        If set to False, messages will not be deleted, but violations will still be logged.

        Note: The bot requires the "Manage Messages" permission to delete messages.
        Without this permission, this setting cannot be enabled.
        """
        if toggle is True and not ctx.guild.me.guild_permissions.manage_messages:
            await ctx.send(
                "I lack the 'Manage Messages' permission in this server. "
                "Please grant me this permission to enable message deletion on violation."
            )
            return
        async with self.db.get_conf(ctx.guild) as guild_settings:
            guild_settings.delete_on_violation = toggle
        await ctx.tick()

    @mediamonitor.command(name="threshold")
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_threshold(
        self,
        ctx: commands.Context,
        action: typing.Literal["kick", "ban", "mute"],
        threshold: int,
    ):
        """Set the threshold for a specific action type.

        When a user reaches this number of violations, the specified action will be taken.
        Setting the threshold to 0 will disable the action.
        """
        action_type = ActionTypes(action)
        async with self.db.get_conf(ctx.guild) as guild_settings:
            guild_settings.thresholds[action_type] = threshold
        await ctx.tick()

    @mediamonitor.command(name="violationexpiration", aliases=["vioexp"])
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_violationexpiration(
        self,
        ctx: commands.Context,
        time: datetime.timedelta = commands.param(
            converter=TimeConverter, default=datetime.timedelta(seconds=0)
        ),
    ):
        """Set the duration (in seconds) after which violations expire.

        After this duration, violations will be removed from a user's record.
        Setting this to 0 will disable violation expiration.
        """
        if time.total_seconds() == 0:
            confirm_view = ConfirmView(timeout=30)
            await ctx.send(
                "You are about to disable violation expiration. Violations will remain indefinitely.",
                view=confirm_view,
            )
            await confirm_view.wait()
            if not confirm_view.result:
                await ctx.send(
                    "Operation cancelled. Violation expiration remains unchanged."
                )
                return
        async with self.db.get_conf(ctx.guild) as guild_settings:
            guild_settings.violation_expiration_seconds = time.total_seconds()
        await ctx.tick()

    @mediamonitor.command(name="removeviolation", aliases=["rmvio", "remvio", "delvio"])
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_removeviolation(
        self,
        ctx: commands.Context,
        member: discord.Member,
        violation_id: str,
    ):
        """Remove a specific violation from a user's record."""
        async with self.db.get_conf(ctx.guild) as guild_settings:
            user_data = guild_settings.members.get(member.id)
            if not user_data or violation_id not in user_data.violations:
                await ctx.send(
                    f"No violation with ID `{violation_id}` found for {member}."
                )
                return
            del user_data.violations[violation_id]
        await ctx.tick()

    @mediamonitor.command(
        name="monitoringchannels",
        aliases=["monitoredchannels", "monchannels", "monchans", "monchan"],
    )
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_monitoringchannels(self, ctx: commands.Context):
        """View and manage the list of channels being monitored for media violations."""
        view = MonitoringChannelSelect(self, ctx.guild)
        if self.db.get_conf(ctx.guild).monitoring_channels:
            content = "Current monitoring channels:\n"
            content += "\n".join(
                f"{ind}. <#{cid}>"
                for ind, cid in enumerate(
                    self.db.get_conf(ctx.guild).monitoring_channels, 1
                )
            )
        else:
            content = "No monitoring channels are currently set."
        view.message = await ctx.send(content, view=view)

    @mediamonitor.command(
        name="whitelistedusers", aliases=["whitelistedmembers", "whitelistusers"]
    )
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_whitelistedusers(self, ctx: commands.Context):
        """View and manage the list of users who are whitelisted from media monitoring."""
        view = WhitelistedUsersSelect(self, ctx.guild)
        if self.db.get_conf(ctx.guild).whitelisted_members:
            content = "Current whitelisted users:\n"
            content += "\n".join(
                f"{ind}. <@{uid}>"
                for ind, uid in enumerate(
                    self.db.get_conf(ctx.guild).whitelisted_members, 1
                )
            )
        else:
            content = "No whitelisted users are currently set."
        view.message = await ctx.send(content, view=view)

    @mediamonitor.command(name="muteduration", aliases=["mutedur"])
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_muteduration(
        self,
        ctx: commands.Context,
        duration: datetime.timedelta = commands.param(converter=TimeConverter),
    ):
        """Set the duration for which a user will be muted when the mute action is taken.

        The duration should be provided in a human-readable format (e.g., 10m for 10 minutes, 1h for 1 hour).
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.thresholds.get(ActionTypes.MUTE, 0) == 0:
            await ctx.send(
                "The mute action is currently disabled (threshold set to 0). "
                "Please set a threshold for muting before configuring the mute duration."
            )
            return

        if duration.total_seconds() < 60:
            await ctx.send("The mute duration must be at least 1 minute.")
            return

        async with self.db.get_conf(ctx.guild) as guild_settings:
            guild_settings.mute_duration_seconds = int(duration.total_seconds())
        await ctx.tick()

    @mediamonitor.command(name="logchannel", aliases=["logchan"])
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_logchannel(
        self,
        ctx: commands.Context,
        channel: typing.Union[discord.TextChannel, discord.Thread],
    ):
        """Set the log channel where media violation logs will be sent."""
        if not channel.permissions_for(ctx.guild.me).send_messages:
            await ctx.send(
                "I do not have permission to send messages in that channel. Please choose a different channel."
            )
            return
        async with self.db.get_conf(ctx.guild) as guild_settings:
            guild_settings.log_channel = channel.id
        await ctx.tick()

    @mediamonitor.command(name="clearviolations", aliases=["clearvios", "clrviols"])
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_clearviolations(
        self, ctx: commands.Context, member: discord.Member
    ):
        """Clear all violations for a specific member."""
        confirm_view = ConfirmView(timeout=30)
        await ctx.send(
            f"Are you sure you want to clear all violations for {member}?",
            view=confirm_view,
        )
        await confirm_view.wait()
        if not confirm_view.result:
            await ctx.send("Operation cancelled. Violations remain unchanged.")
            return

        async with self.db.get_conf(ctx.guild) as guild_settings:
            user_data = guild_settings.members.get(member.id)
            if not user_data or not user_data.violations:
                await ctx.send(f"{member} has no violations to clear.")
                return
            user_data.violations.clear()
        await ctx.tick()

    @mediamonitor.command(name="showsettings", aliases=["ss", "settings"])
    @commands.admin_or_permissions(administrator=True)
    async def mediamonitor_viewsettings(self, ctx: commands.Context):
        """View the current MediaMonitor settings for this guild."""
        guild_settings = self.db.get_conf(ctx.guild)
        embed = discord.Embed(
            title=f"MediaMonitor Settings for {ctx.guild.name}",
            color=await self.bot.get_embed_color(ctx),
        )
        embed.add_field(
            name="Filename Regex",
            value=(
                f"`{guild_settings.filename_regex}`"
                if guild_settings.filename_regex
                else "Not Set"
            ),
            inline=False,
        )
        embed.add_field(
            name="File Size Limit",
            value=bytes_to_readable_memory(guild_settings.file_size_limit_bytes)
            if guild_settings.file_size_limit_bytes > 0
            else "Not Set",
            inline=False,
        )
        embed.add_field(
            name="Blacklisted File Types",
            value=(
                ", ".join(guild_settings.blacklisted_file_types)
                if guild_settings.blacklisted_file_types
                else "Not Set"
            ),
            inline=False,
        )
        embed.add_field(
            name="Delete on Violation",
            value=str(guild_settings.delete_on_violation),
            inline=False,
        )
        thresholds = "\n".join(
            f"*__{action.value.capitalize()}__*: {f'{threshold} violations required' if threshold > 0 else 'Disabled'}"
            + (
                f"\n- Duration: {cf.humanize_timedelta(seconds=guild_settings.mute_duration_seconds)}"
                if action == ActionTypes.MUTE and threshold > 0
                else ""
            )
            for action, threshold in guild_settings.thresholds.items()
        )
        embed.add_field(
            name="Action Thresholds",
            value=thresholds,
            inline=False,
        )
        embed.add_field(
            name="Violation Expiration",
            value=(
                f"{cf.humanize_timedelta(seconds=guild_settings.violation_expiration_seconds)}"
                if guild_settings.violation_expiration_seconds > 0
                else "Never"
            ),
            inline=False,
        )
        embed.add_field(
            name="Log Channel",
            value=(
                f"<#{guild_settings.log_channel}>"
                if guild_settings.log_channel
                else "Not Set"
            ),
            inline=False,
        )
        embed.add_field(
            name="Monitoring Channels",
            value=(
                ", ".join(f"<#{cid}>" for cid in guild_settings.monitoring_channels)
                if guild_settings.monitoring_channels
                else "Not Set"
            ),
            inline=False,
        )
        embed.add_field(
            name="Whitelisted Users",
            value=(
                ", ".join(f"<@{uid}>" for uid in guild_settings.whitelisted_members)
                if guild_settings.whitelisted_members
                else "Not Set"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

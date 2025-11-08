import asyncio
import datetime
import functools
import importlib.util
import logging
import multiprocessing as mp
import typing

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..common.models import ActionTypes, GuildSettings, Violation

if not importlib.util.find_spec("regex"):
    import re

else:
    import regex as re


log = logging.getLogger("red.mediamonitor.listeners")


class MessageListeners(MixinMeta):
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = message.guild
        if not guild:
            log.debug(f"Message {message.id} not in a guild, ignoring.")
            return

        conf = self.db.get_conf(guild.id)
        if not conf.is_enabled():
            log.debug(
                f"MediaMonitor is disabled in guild {guild.id}, ignoring message."
            )
            return

        if message.channel.id not in conf.monitoring_channels:
            log.debug(f"Message {message.id} not in monitoring channels, ignoring.")
            return

        if not message.attachments:
            log.debug(f"Message {message.id} has no attachments, ignoring.")
            return

        if message.author.id in conf.whitelisted_members:
            log.debug(
                f"Author {message.author.id} of message {message.id} is whitelisted, ignoring."
            )
            return

        log.debug(
            f"Message {message.id} in guild {guild.id} by {message.author.id} has passed all pre processing checks. Processing attachments."
        )

        attachments = message.attachments
        for attachment in attachments:
            violated, violation_type = await self.attachment_violates_rules(
                message.guild, message.author, conf, attachment
            )
            if violated is True:
                self.bot.dispatch(
                    "mediamonitor_violation", message, attachment, violation_type
                )

        else:
            log.debug(
                f"Message {message.id} in guild {guild.id} by {message.author.id} has no violating attachments."
            )

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        await self.on_message(after)

    @commands.Cog.listener()
    async def on_mediamonitor_violation(
        self,
        message: discord.Message,
        attachment: discord.Attachment,
        violation_type: str,
    ) -> None:
        log.debug(
            f"Media violation detected in message {message.id} in guild {message.guild.id} by {message.author.id} for {violation_type}."
        )
        guild = message.guild
        if not guild:
            return

        conf = self.db.get_conf(guild.id)

        message_deleted = False

        if conf.delete_on_violation:
            try:
                log.debug(
                    f"Deleting message {message.id} in guild {guild.id} due to media violation."
                )
                await message.delete()
                message_deleted = True
            except discord.Forbidden:
                log.warning(
                    "Lacking permissions to delete message in guild %s (%s)",
                    guild.name,
                    guild.id,
                )
            except discord.HTTPException as e:
                log.error(
                    "Failed to delete message in guild %s (%s): %s",
                    guild.name,
                    guild.id,
                    e,
                )

        all_violations = conf.get_member(message.author.id).violations

        thresholds = conf.thresholds
        action_to_take = next(
            (
                k
                for k, v in thresholds.items()
                if v > 0 and v == (len(all_violations) + 1)
            ),
            None,
        )
        action_taken: typing.Optional[ActionTypes] = action_to_take

        logchan = guild.get_channel_or_thread(conf.log_channel)
        if not logchan:
            return

        if action_to_take is not None:
            if action_to_take == ActionTypes.MUTE:
                success = await self.take_action_on_member(
                    logchan,
                    guild,
                    message.author,
                    action_to_take,
                    f"Media Monitor Violation Threshold reached: {thresholds[action_to_take]} violations.",
                    mute_duration=conf.mute_duration_seconds,
                )
            else:
                success = await self.take_action_on_member(
                    logchan,
                    guild,
                    message.author,
                    action_to_take,
                    f"Media Monitor Violation Threshold reached: {thresholds[action_to_take]} violations.",
                )

            if not success:
                action_to_take = None

        await self.log_violation(
            logchan,
            message,
            message_deleted=message_deleted,
            attachment=attachment,
            violation_type=violation_type,
            conf=conf,
            action_taken=action_taken,
        )

    async def attachment_violates_rules(
        self,
        guild: discord.Guild,
        author: discord.Member,
        conf: GuildSettings,
        attachment: discord.Attachment,
    ) -> typing.Union[
        typing.Tuple[bool, typing.Literal["", "filesize", "filetype", "filename"]],
    ]:
        """Check if an attachment violates the guild's media monitoring rules.

        Returns True if the attachment violates any of the rules, False otherwise.
        """
        if (
            conf.file_size_limit_bytes > 0
            and attachment.size > conf.file_size_limit_bytes
        ):
            log.debug(
                f"Attachment {attachment.id} in guild {guild.id} by {author.id} violates file size limit. {attachment.size=} > {conf.file_size_limit_bytes=}"
            )
            return True, "filesize"

        if conf.blacklisted_file_types:
            filetype = attachment.filename.split(".")[-1].lower()
            if filetype in conf.blacklisted_file_types:
                log.debug(
                    f"Attachment {attachment.id} in guild {guild.id} by {author.id} violates file type blacklist. {filetype=} in {conf.blacklisted_file_types=}"
                )
                return True, "filetype"

        if conf.filename_regex:
            pattern = re.compile(conf.filename_regex)
            safe, matches = await self.safe_regex_search(
                guild, author, pattern, attachment.filename
            )
            if safe and matches:
                log.debug(
                    f"Attachment {attachment.id} in guild {guild.id} by {author.id} violates filename regex. {attachment.filename=} matches {conf.filename_regex=}"
                )
                return True, "filename"

            elif not safe:
                async with conf:
                    conf.filename_regex = ""

        return False, ""

    # shamelessly stolen from TrustyJaid's ReTrigger cog
    async def safe_regex_search(
        self,
        guild: discord.Guild,
        author: discord.Member,
        regex: re.Pattern,
        filename: str,
    ) -> typing.Tuple[bool, list]:
        """
        Mostly safe regex search to prevent reDOS from user defined regex patterns

        This works by running the regex pattern inside a process pool defined at the
        cog level and then checking that process in the default executor to keep
        things asynchronous. If the process takes too long to complete we log a
        warning and remove the trigger from trying to run again.
        """
        try:
            process = self.re_pool.apply_async(regex.findall, (filename,))
            task = functools.partial(process.get, timeout=self.regex_timeout)
            loop = asyncio.get_running_loop()
            new_task = loop.run_in_executor(None, task)
            search = await asyncio.wait_for(new_task, timeout=self.regex_timeout + 5)
        except mp.TimeoutError:
            log.warning(
                "Filename Regex process timeout in guild %s (%s) Author %s Removing the regex",
                guild.name,
                guild.id,
                author.id,
            )
            return (False, [])
            # we certainly don't want to be performing multiple triggers if this happens
        except asyncio.TimeoutError:
            log.warning(
                "Filename Regex asyncio timeout in guild %s (%s) Author %s Removing the regex",
                guild.name,
                guild.id,
                author.id,
            )
            return (False, [])
        except ValueError:
            return (False, [])
        except Exception as exc:
            log.error(
                "Filename Regex unknown error in guild %s (%s) Author %s",
                guild.name,
                guild.id,
                author.id,
                exc_info=exc,
            )
            return (True, [])
        else:
            return (True, search)

    async def log_violation(
        self,
        log_channel: typing.Union[discord.TextChannel, discord.Thread],
        message: discord.Message,
        message_deleted: bool,
        attachment: discord.Attachment,
        violation_type: str,
        conf: GuildSettings,
        action_taken: typing.Optional[ActionTypes] = None,
    ) -> None:
        """Log a media violation to the specified log channel."""
        embed = await self.create_violation_embed(
            conf,
            message.guild,
            message.author,
            attachment,
            violation_type,
            message.jump_url,
            message_deleted,
            action_taken,
        )
        logmsg = None
        try:
            logmsg = await log_channel.send(embed=embed)
        except discord.Forbidden:
            log.warning(
                "Lacking permissions to send messages in log channel %s in guild %s (%s)",
                log_channel.id,
                message.guild.name,
                message.guild.id,
            )
        except discord.HTTPException as e:
            log.error(
                "Failed to send log message in guild %s (%s): %s",
                message.guild.name,
                message.guild.id,
                e,
            )

        async with self.db.get_conf(message.guild) as conf:
            vio = Violation(
                timestamp=discord.utils.utcnow().timestamp(),
                channel=message.channel.id,
                message=message.id if not message_deleted else None,
                violation_type=violation_type,
                action_taken=action_taken,
                log_message_url=logmsg.jump_url if logmsg else None,
            )
            conf.get_member(message.author.id).violations[vio.id] = vio

    async def create_violation_embed(
        self,
        conf: GuildSettings,
        guild: discord.Guild,
        member: discord.Member,
        attachment: discord.Attachment,
        violation_type: str,
        jump_url: str,
        message_deleted: bool = False,
        action_taken: typing.Optional[ActionTypes] = None,
    ) -> discord.Embed:
        """Create an embed for a media violation log."""
        embed = discord.Embed(
            title="Media Violation Detected",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        embed.add_field(
            name="Violation Type", value=violation_type.capitalize(), inline=False
        )
        embed.add_field(
            name="Attachment",
            value=f"[{attachment.filename}]({attachment.url}) ({attachment.size / 1024:.2f} KB)",
            inline=False,
        )
        if not message_deleted:
            embed.add_field(name="Message Link", value=f"[Jump to Message]({jump_url})")

        if action_taken is not None:
            embed.add_field(
                name="Action Taken",
                value=action_taken.name.capitalize()
                + (
                    f" for {conf.mute_duration_seconds} seconds"
                    if action_taken == ActionTypes.MUTE
                    else ""
                ),
                inline=False,
            )
        embed.add_field(
            name="Message Deleted",
            value="Yes" if message_deleted else "No",
            inline=False,
        )
        embed.set_footer(text=f"Guild: {guild.name} ({guild.id})")
        return embed

    @typing.overload
    async def take_action_on_member(
        self,
        guild: discord.Guild,
        member: discord.Member,
        action: typing.Literal[ActionTypes.MUTE],
        reason: str,
        mute_duration: int,
    ) -> None: ...

    @typing.overload
    async def take_action_on_member(
        self,
        guild: discord.Guild,
        member: discord.Member,
        action: typing.Union[
            typing.Literal[ActionTypes.KICK], typing.Literal[ActionTypes.BAN]
        ],
        reason: str,
    ) -> None: ...

    async def take_action_on_member(
        self,
        log_chan: typing.Union[discord.TextChannel, discord.Thread],
        guild: discord.Guild,
        member: discord.Member,
        action: ActionTypes,
        reason: str,
        mute_duration: int | None = None,
    ) -> bool:
        """Take the specified action on the member."""
        try:
            if action == ActionTypes.MUTE:
                log.debug(
                    f"Muting member {member.id} in guild {guild.id} for {mute_duration} seconds."
                )
                await member.timeout(
                    until=discord.utils.utcnow()
                    + datetime.timedelta(seconds=mute_duration),
                    reason=reason,
                )
            elif action == ActionTypes.KICK:
                log.debug(f"Kicking member {member.id} from guild {guild.id}.")
                await member.kick(reason=reason)
            elif action == ActionTypes.BAN:
                log.debug(f"Banning member {member.id} from guild {guild.id}.")
                await guild.ban(member, reason=reason)

            return True

        except discord.Forbidden:
            log.warning(
                "Lacking permissions to %s member %s in guild %s (%s)",
                action.name.lower(),
                member.id,
                guild.name,
                guild.id,
            )
        except discord.HTTPException as e:
            log.error(
                "Failed to %s member %s in guild %s (%s): %s",
                action.name.lower(),
                member.id,
                guild.name,
                guild.id,
                e,
            )

        await self.log_action_failure(log_chan, guild, member, action)

        return False

    async def log_action_failure(
        self,
        log_channel: typing.Union[discord.TextChannel, discord.Thread],
        guild: discord.Guild,
        member: discord.Member,
        action: ActionTypes,
    ) -> None:
        """Log a failure to take action on a member."""
        log.debug(
            f"Logging action failure for {action.name} on member {member.id} in guild {guild.id}."
        )
        embed = discord.Embed(
            title="Action Failure",
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        embed.add_field(
            name="Action",
            value=action.name.capitalize(),
            inline=False,
        )
        embed.set_footer(text=f"Guild: {guild.name} ({guild.id})")

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            log.warning(
                "Lacking permissions to send messages in log channel %s in guild %s (%s)",
                log_channel.id,
                guild.name,
                guild.id,
            )
        except discord.HTTPException as e:
            log.error(
                "Failed to send action failure log in guild %s (%s): %s",
                guild.name,
                guild.id,
                e,
            )

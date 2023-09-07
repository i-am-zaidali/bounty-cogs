from datetime import datetime, timedelta, timezone
from typing import TypedDict

import discord
from redbot.cogs.mutes.converters import MuteTime
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.modlog import create_case
from redbot.core.utils import chat_formatting as cf
import logging


class RTDict(TypedDict):
    duration: timedelta
    reason: str


class Timeout(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot

    @commands.command(name="timeout")
    @commands.guild_only()
    @commands.mod_or_permissions(moderate_members=True, mute_members=True)
    async def timeout(
        self,
        ctx: commands.Context,
        user: discord.Member,
        *,
        time_and_reason: RTDict = commands.param(converter=MuteTime, default={}),
    ):
        """
        Timeout a user.

        `<user>` is a username, ID, or mention.
        `[time_and_reason]` is the time to mute for and reason. Time is
        any valid time length such as `30 minutes` or `2 days`.

        Examples:
        `[p]mute @member1 spam 5 hours`
        `[p]mute @member1 3 days`"""
        if not time_and_reason:
            return await ctx.send_help()
        if not time_and_reason.get("duration"):
            return await ctx.send("You must specify a time to timeout the user.")
        if user == ctx.me:
            return await ctx.send("I can't timeout myself.")
        if user == ctx.author:
            return await ctx.send("You can't timeout yourself.")
        if user.timed_out_until:
            return await ctx.send("That user is already timed out.")
        duration = time_and_reason.get("duration")
        reason = time_and_reason.get("reason", None)
        until = datetime.now(timezone.utc) + duration
        time = " for {duration}".format(duration=cf.humanize_timedelta(timedelta=duration))
        try:
            await user.timeout(until, reason=reason)
        except Exception:
            logging.exception("Error while timing out user", exc_info=True)
            return await ctx.send(
                "Something went wrong while timing out that user. Check your logs."
            )

        await create_case(
            self.bot,
            ctx.guild,
            ctx.message.created_at,
            "smute",
            user,
            ctx.author,
            reason,
            until=until,
            channel=None,
        )

        await ctx.send(f"{user} has been muted in this server{time}.")


async def setup(bot):
    bot.add_cog(Timeout(bot))

import asyncio
import typing

import discord
from redbot.core import commands
from redbot.core.utils.views import ConfirmView

from ..abc import MixinMeta
from ..common.models import DAYS
from ..common.timeslotgen import TimeSlotsGenerator
from ..views.updatemytimes import UpdateMyTimes


class Admin(MixinMeta):
    """Admin commands for the timeslots cog"""

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def timeslots(self, ctx: commands.Context):
        """Admin commands for the timeslots cog"""

    @timeslots.command()
    async def endofweek(
        self,
        ctx: commands.Context,
        day: typing.Literal[
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
        ],
    ):
        """Set the end of the week for the guild"""
        self.db.get_conf(ctx.guild).end_of_the_week = DAYS[day]
        self.save()
        await ctx.send(f"End of the week set to {day}")

    @timeslots.group(name="selection")
    async def selection(self, ctx: commands.Context):
        """Commands for the slot selection message"""

    @selection.command(name="channel")
    async def selection_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the channel for the slot selection message"""
        conf = self.db.get_conf(ctx.guild)
        confchan = ctx.guild.get_channel(conf.slot_selection_channel)
        if conf.slot_selection_message and confchan:
            confmessage = confchan.get_partial_message(conf.slot_selection_message)
            await ctx.send(
                f"A slot selection menu already exists at {confmessage.jump_url}. "
                f"Are you sure you want to create a new one in {channel.mention} and delete the old one?",
                view=(view := ConfirmView(author=ctx.author, disable_buttons=True)),
            )
            if await view.wait():
                return await ctx.send("Keeping the old message.")
            if not view.result:
                return await ctx.send("Keeping the old message.")

        async with ctx.typing():
            confmessage = channel.get_partial_message(conf.slot_selection_message)
            try:
                await confmessage.delete()

            except discord.NotFound:
                conf.started_on = discord.utils.utcnow().date()

            except discord.Forbidden:
                await ctx.send(
                    "It seems I have insufficient permissions to delete the slot selection menu."
                    f"I have updated it in my memory but you will have to manually delete it {confmessage.jump_url}."
                )
            conf.started_on = conf.started_on or discord.utils.utcnow().date()
            chart = await asyncio.to_thread(
                TimeSlotsGenerator(self, ctx.guild).get_colored_organized_chart,
                {uid: data.reserved_times for uid, data in conf.users.items()},
            )
            msg = await channel.send(
                content=f"## Time Slot Selection for the week {conf.started_on.strftime('%A %m/%d/%Y')} to {conf.next_chart_reset.strftime('%A %m/%d/%Y')}",
                file=discord.File(chart, "timeslots.png"),
                view=discord.ui.View().add_item(UpdateMyTimes()),
            )
            conf.slot_selection_channel = channel.id
            conf.slot_selection_message = msg.id
            await msg.pin(reason="Slot selection message")

        await ctx.send(
            f"Slot selection channel set to {channel.mention}: {msg.jump_url}"
        )
        self.save()

    @selection.command(name="remove", aliases=["delete", "del", "rem"])
    async def selection_remove(
        self,
        ctx: commands.Context,
        ARE_YOU_SURE: bool = commands.param(displayed_name="", default=False),
    ):
        conf = self.db.get_conf(ctx.guild.id)
        channel = ctx.guild.get_channel(conf.slot_selection_channel)
        if not ARE_YOU_SURE and channel:
            confmessage = channel.get_partial_message(conf.slot_selection_message)
            return await ctx.send(
                f"This will delete the message at {confmessage.jump_url}. "
                "If you're sure about this, rerun the command with `True` appended at the end.\n"
                f"`{ctx.clean_prefix}timeslots selection remove True`"
            )

        elif not channel:
            return await ctx.send("There is no slot selection menu set right now.")

        else:
            confmessage = channel.get_partial_message(conf.slot_selection_message)
            try:
                await confmessage.delete()
            except discord.NotFound:
                conf.slot_selection_channel = conf.slot_selection_message = None
                return await ctx.send("The slot selection menu does not exist anymore.")

            except discord.Forbidden:
                conf.slot_selection_channel = conf.slot_selection_message = None
                return await ctx.send(
                    "It seems I have insufficient permissions to delete the slot selection menu."
                    f"I have removed it from my memory but you will have to manually delete it {confmessage.jump_url}."
                )
            finally:
                self.save()

    @selection.command(name="forceupdate")
    async def selection_update(self, ctx: commands.Context):
        """Force update the slot selection message"""
        conf = self.db.get_conf(ctx.guild)
        channel = ctx.guild.get_channel(conf.slot_selection_channel)
        if not channel:
            return await ctx.send("There is no slot selection menu set right now.")

        confmessage = channel.get_partial_message(conf.slot_selection_message)
        await ctx.send("Updating the slot selection message...")
        async with ctx.typing():
            try:
                await confmessage.edit(content="Updating...", attachments=[])
            except discord.Forbidden:
                return await ctx.send(
                    "It seems I have insufficient permissions to edit the slot selection menu."
                )

            except discord.NotFound:
                return await ctx.send(
                    "The slot selection message does not exist anymore."
                )

            chart = await asyncio.to_thread(
                TimeSlotsGenerator(self, ctx.guild).get_colored_organized_chart,
                {uid: data.reserved_times for uid, data in conf.users.items()},
            )
            await confmessage.edit(
                content=f"## Time Slot Selection for the week {conf.started_on.strftime('%A %m/%d/%Y')} to {conf.next_chart_reset.strftime('%A %m/%d/%Y')}",
                attachments=[discord.File(chart, "timeslots.png")],
                view=discord.ui.View().add_item(UpdateMyTimes()),
            )

            await ctx.send("Slot selection message updated")

    @selection.command(name="reset")
    async def reset(
        self,
        ctx: commands.Context,
        ARE_YOU_SURE: bool = commands.param(default=False, displayed_name=""),
    ):
        """Reset the timeslots data for all users"""
        conf = self.db.get_conf(ctx.guild.id)
        if not ARE_YOU_SURE:
            return await ctx.send(
                "If you are sure you want to reset the timeslots data for all users, "
                f"rerun the command with `{ctx.clean_prefix}timeslots selection reset True`."
            )

        conf.reset_timeslots()

        await ctx.send("All user slots have been cleared")
        self.save()

    @timeslots.command(name="utcoffset")
    async def utcoffset(self, ctx: commands.Context, utcoffset: int):
        """Set the timezone for the guild"""
        conf = self.db.get_conf(ctx.guild)
        conf.utcoffset = utcoffset
        self.save()
        await ctx.send(f"Timezone set to UTC{utcoffset:+}")

    @timeslots.command(name="showsettings", aliases=["settings", "ss"])
    async def showsettings(self, ctx: commands.Context):
        """Show the current settings for the guild"""
        conf = self.db.get_conf(ctx.guild)
        await ctx.send(
            f"End of the week: **{conf.end_of_the_week.name}**\n"
            f"Slot selection channel: {getattr(chan:=ctx.guild.get_channel(conf.slot_selection_channel), 'mention', 'None set')}\n"
            f"Slot selection message: {chan.get_partial_message(conf.slot_selection_message).jump_url if chan else 'Channel not set yet'}\n"
            f"Timezone: UTC{conf.utcoffset:+}"
        )

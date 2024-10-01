from redbot.core import commands
import typing
from .group import MCMGroup
import discord
from ..abc import MixinMeta

mcm_channel = typing.cast(commands.Gorup, MCMGroup.mcm_channel)
mcm_channel_courses = typing.cast(commands.Group, MCMGroup.mcm_channel_courses)


class MCMChannels(MixinMeta):
    @mcm_channel.command(name="track")
    async def mcm_channel_track(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the channel to track stats in"""
        async with self.db.get_conf(ctx.guild) as conf:
            conf.trackchannel = channel.id
            await ctx.tick()

    @mcm_channel.command(name="alert")
    async def mcm_channel_alert(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the channel to alert in"""
        async with self.db.get_conf(ctx.guild) as conf:
            conf.alertchannel = channel.id
            await ctx.tick()

    @mcm_channel.command(name="log")
    async def mcm_channel_log(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the channel to log in"""
        async with self.db.get_conf(ctx.guild) as conf:
            conf.logchannel = channel.id
            await ctx.tick()

    @mcm_channel.command(name="course")
    async def mcm_channel_courses(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the channel to announce courses in"""
        async with self.db.get_conf(ctx.guild) as conf:
            conf.coursechannel = channel.id
            await ctx.tick()

    @mcm_channel.command(name="show")
    async def mcm_channel_show(self, ctx: commands.Context):
        """Show the current channels"""
        conf = self.db.get_conf(ctx.guild)
        data = {
            "Track": conf.trackchannel,
            "Alert": conf.alertchannel,
            "Log": conf.logchannel,
            "Course": conf.coursechannel,
        }
        embed = discord.Embed(title="Channels")
        for name, channel_id in data.items():
            embed.add_field(
                name=name + " Channel",
                value=f"<#{channel_id}>" if channel_id else "Not set",
            )
        await ctx.send(embed=embed)

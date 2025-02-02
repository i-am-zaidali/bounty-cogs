import discord
import redbot.vendored.discord.ext.menus as menus
from redbot.core import commands

from ..abc import MixinMeta
from ..views.paginator import Paginator


class Admin(MixinMeta):
    @commands.group(name="firstwords")
    @commands.admin()
    async def firstwords(self, ctx: commands.Context):
        """First Words cog settings"""

    @firstwords.command(name="alertchannel")
    async def alertchannel(
        self, ctx: commands.Context, channel: discord.TextChannel | None = None
    ):
        """Set the channel for first words alerts"""
        async with self.db.get_conf(ctx.guild.id) as conf:
            conf.alert_channel = channel.id
        await ctx.send(
            f"Alert channel set to {channel.mention}"
            if channel
            else "Alert channel removed"
        )

    @firstwords.command(name="alertmessages")
    async def alertmessages(self, ctx: commands.Context, amount: int):
        """Set the amount of messages sent to alert on"""
        async with self.db.get_conf(ctx.guild.id) as conf:
            conf.alert_x_messages = amount
        await ctx.send(f"Alerting on {amount} messages")

    @firstwords.command(name="stillsilent")
    async def stillsilent(self, ctx: commands.Context):
        """Shows a paginated list of users that have been silent since they joined the server."""

        class StillSilentSource(menus.ListPageSource):
            async def format_page(self, menu: Paginator, items: list[discord.Member]):
                return discord.Embed(
                    title="Silent Users",
                    description="\n".join(
                        [
                            f"{ind}. {m.mention} ({m.id})\n"
                            f"  - Joined at: {discord.utils.format_dt(m.joined_at, 'F')}\n"
                            f"  - Messages sent: {menu.ctx.cog.db.get_conf(menu.ctx.guild.id).recently_joined_msgs.get(m.id, 0)}\n"
                            for ind, m in enumerate(items)
                        ]
                    ),
                    timestamp=menu.ctx.message.created_at,
                )

        conf = self.db.get_conf(ctx.guild.id)

        silent_members = [
            member
            for m in conf.recently_joined_msgs
            if (member := ctx.guild.get_member(m)) is not None
        ]
        if not silent_members:
            await ctx.send("No silent users yet.")
            return

        paginator = Paginator(StillSilentSource(silent_members, per_page=6))
        await paginator.start(ctx)

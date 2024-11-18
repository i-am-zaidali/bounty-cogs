import typing

from redbot.core import commands
from redbot.core.utils import chat_formatting as cf

from ..abc import MixinMeta
from ..common.models import GuildSettings
from ..views import Paginator, TotalStatsSource
from .group import MCMGroup

mcm = typing.cast(commands.Group, MCMGroup.mcm)


class MCMTopLevel(MixinMeta):
    @mcm.command(name="totalstats", aliases=["ts"])
    async def mcm_totalstats(self, ctx: commands.Context):
        """Show the total stats of all users"""
        conf = self.db.get_conf(ctx.guild)
        data = conf.members
        vehicles = conf.vehicles
        categories = conf.vehicle_categories
        if not vehicles:
            return await ctx.send("No vehicles have been added yet.")
        total_stats = dict.fromkeys(vehicles, 0)
        for member_data in data.values():
            for vehicle, amount in member_data.stats.items():
                if vehicle not in total_stats:
                    continue
                total_stats[vehicle] += amount
        total_stats = dict(
            sorted(
                total_stats.items(),
                key=lambda x: x[1],
                reverse=True,
            )
        )
        category_counts = [
            *{
                category: sum(total_stats.get(vehicle, 0) for vehicle in cat_vc)
                for category, cat_vc in categories.items()
            }.items()
        ]

        items = list(total_stats.items()) + list(category_counts)
        source = TotalStatsSource(items, vehicles)
        await Paginator(source, 0, use_select=True).start(ctx)

    @mcm.command(name="export")
    @commands.is_owner()
    async def mcm_export(self, ctx: commands.Context):
        """Export all stats to a csv file"""
        conf = self.db.get_conf(ctx.guild)
        data = conf.members
        vehicles = conf.vehicles
        if not vehicles:
            return await ctx.send("No vehicles have been added yet.")
        total_stats = dict.fromkeys(vehicles, 0)
        for member_data in data.values():
            for vehicle, amount in member_data.stats.items():
                if vehicle not in total_stats:
                    continue
                total_stats[vehicle] += amount

        csv = "\n".join(
            [f"{vehicle},{amount}" for vehicle, amount in total_stats.items()]
        )
        await ctx.send(file=cf.text_to_file(csv, filename="stats.csv"))

    @mcm.command(name="purge", aliases=["clearall"], usage="")
    @commands.is_owner()
    async def mcm_purge(
        self, ctx: commands.Context, ARE_YOU_SURE: bool = False
    ):
        """Purge EVERYTHING.

        This will delete all settings. from set channels, to allowed vehicles, to stats. EVERYTHING.
        """
        if not ARE_YOU_SURE:
            return await ctx.send(
                "Are you sure you want to purge all stats? If so, run the command again with `True` as the first argument."
            )
        self.db.configs[ctx.guild.id] = GuildSettings()
        await ctx.tick()
        await self.save()

    @mcm.command(name="showsettings", aliases=["ss"])
    @commands.mod()
    async def mcm_showsettings(self, ctx: commands.Context):
        """Show the current settings"""
        conf = self.db.get_conf(ctx.guild)
        message = f"Settings for **__{ctx.guild.name}__**\n"
        message += (
            "**__Log channel: __**"
            + getattr(
                ctx.guild.get_channel(conf.logchannel), "mention", "None set"
            )
            + "\n"
        )
        message += (
            "**__Alert channel: __**"
            + getattr(
                ctx.guild.get_channel(conf.alertchannel), "mention", "None set"
            )
            + "\n"
        )
        message += (
            "**__Track channel: __**"
            + getattr(
                ctx.guild.get_channel(conf.trackchannel), "mention", "None set"
            )
            + "\n"
        )
        message += (
            "**__Course channel: __**"
            + getattr(
                ctx.guild.get_channel(conf.coursechannel), "mention", "None set"
            )
            + "\n"
        )
        message += (
            "**__Course role: __**"
            + getattr(
                ctx.guild.get_role(conf.course_role), "mention", "None set"
            )
            + "\n"
        )
        message += (
            "**__Course teacher role: __**"
            + getattr(
                ctx.guild.get_role(conf.course_teacher_role),
                "mention",
                "None set",
            )
            + "\n"
        )
        message += (
            "**__Vehicles:__**"
            f" *Use `{ctx.clean_prefix}mcm vehicles list` to view these\n"
        )
        message += (
            "**__Vehicle categories:__**"
            f" *Use `{ctx.clean_prefix}mcm vehicle category list` to view these\n"
        )
        message += (
            "**__Course shorthands:__**"
            f" *Use `{ctx.clean_prefix}mcm courses shorthand list` to view these\n"
        )
        message += (
            "**__State roles:__**"
            f" *Use `{ctx.clean_prefix}mcm staterole list` to view these\n"
        )
        await ctx.send(message)

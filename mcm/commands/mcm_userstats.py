import collections
import operator
import typing

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..common.utils import parse_vehicles
from ..views import Paginator, UserStatsSource
from .group import MCMGroup

mcm_userstats = typing.cast(commands.Group, MCMGroup.mcm_userstats)


class MCMUserStats(MixinMeta):
    @mcm_userstats.command(name="show", usage="[users... or role = YOU]")
    async def mcm_userstats_show(
        self,
        ctx: commands.GuildContext,
        user_or_role: typing.Union[
            discord.Member,
            discord.Role,
            discord.User,  # User to allow viewing stats of someone who left the server
        ] = commands.param(
            default=operator.attrgetter("author"), displayed_default="<You>"
        ),
        *userlist: discord.Member,
    ):
        """Show the stats of a user"""
        if isinstance(user_or_role, discord.Role) and len(userlist):
            raise commands.BadArgument(
                "You cannot specify a role and users at the same time."
            )

        users = (
            user_or_role.members
            if isinstance(user_or_role, discord.Role)
            else [user_or_role, *userlist]
        )
        conf = self.db.get_conf(ctx.guild)
        vehicles = conf.vehicles
        categories = conf.vehicle_categories

        all_users: list[tuple[discord.Member | None, dict[str, int]]] = [
            (user, conf.get_member(user).stats) for user in users
        ]

        if len(users) > 1:
            # combined stats of all users:
            all_users.insert(
                0,
                (
                    None,
                    dict(
                        sum(
                            (
                                collections.Counter(user[1])
                                for user in all_users
                            ),
                            collections.Counter(),
                        )
                    ),
                ),
            )

        source = UserStatsSource(all_users, user_or_role, vehicles, categories)
        await Paginator(source, 0, use_select=True).start(ctx)

    @mcm_userstats.command(name="clear", usage="<user = YOU>")
    @commands.admin()
    async def mcm_userstats_clear(
        self,
        ctx: commands.Context,
        user: discord.Member = commands.param(
            converter=typing.Optional[typing.Union[discord.User, int]],
            default=operator.attrgetter("author"),
            displayed_default="<You>",
        ),
        ARE_YOU_SURE: bool = False,
    ):
        """Clear the stats of a user"""
        if not ARE_YOU_SURE:
            return await ctx.send(
                f"Are you sure you want to clear the stats of {user.mention}? If so, run the command again with `True` as the second argument."
            )

        async with self.db.get_conf(ctx.guild) as conf:
            userid = user.id if isinstance(user, discord.User) else user
            conf.members.pop(userid, None)
            await ctx.tick()

    @mcm_userstats.command(name="update")
    @commands.admin()
    async def mcm_userstats_update(
        self,
        ctx: commands.Context,
        user: discord.Member = commands.param(
            converter=typing.Optional[discord.Member],
            default=operator.attrgetter("author"),
            displayed_default="<You>",
        ),
        *,
        vehicles: str,
    ):
        """Update the stats of a user

        Be aware, this does not replace the user's existing stats, it only updates them
        """
        try:
            vehicle_amount = parse_vehicles(vehicles)
        except ValueError as e:
            return await ctx.send(e.args[0])

        conf = self.db.get_conf(ctx.guild)

        async with conf.get_member(user) as member:
            await self.log_new_stats(user, member.stats, vehicle_amount)
            member.stats = vehicle_amount
            await ctx.tick()

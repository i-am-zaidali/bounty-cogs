import typing

import discord
from redbot.core import commands
from redbot.core.utils.mod import is_mod_or_superior

from ..abc import MixinMeta
from ..common.models import UserData
from ..views.pagesources.violations_source import ViolationsSource
from ..views.paginator import Paginator
from .admin import Admin

mediamonitor = typing.cast("commands.Group", Admin.mediamonitor)


class User(MixinMeta):
    @mediamonitor.command(name="violations", aliases=["vios", "viols"], usage="")
    async def mediamonitor_violations(
        self,
        ctx: "commands.Context",
        member: typing.Optional[typing.Union[discord.Member, discord.User]] = None,
    ):
        """Check the number of media violations for a user in this server.

        If no user is specified, it will check your violations.
        """
        member = member or ctx.author
        if (
            not await is_mod_or_superior(self.bot, ctx.author)
            and member is not ctx.author
        ):
            member = ctx.author

        violations = (
            self.db.get_conf(ctx.guild).members.get(member.id, UserData()).violations
        )

        paginator = Paginator(
            ViolationsSource(violations, member, ctx.guild), use_select=True
        )

        await paginator.start(ctx)

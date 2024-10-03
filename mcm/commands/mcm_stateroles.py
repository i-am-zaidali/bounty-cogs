import typing

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..common.models import StateShorthands
from .group import MCMGroup

mcm_sr = typing.cast(commands.Group, MCMGroup.mcm_stateroles)


class MCMStateRoles(MixinMeta):
    @mcm_sr.command(name="set")
    async def mcm_sr_set(
        self,
        ctx: commands.Context,
        state: typing.Literal[
            "NSW", "QLD", "SA", "TAS", "VIC", "WA", "ACT", "NT"
        ],
        role: discord.Role,
    ):
        """Add a state role"""
        async with self.db.get_conf(ctx.guild) as conf:
            sr = conf.state_roles
            sr.update({state: role.id})
            await ctx.tick()

    @mcm_sr.command(name="list")
    async def mcm_sr_list(self, ctx: commands.Context):
        """List the state roles"""
        roles = self.db.get_conf(ctx.guild).state_roles
        if not roles:
            return await ctx.send("No state roles have been added yet.")
        await ctx.send(
            "- "
            + "\n- ".join(
                (
                    f"**{StateShorthands.__members__[x[0]]}**: {getattr(ctx.guild.get_role(x[1]),'mention', 'Not set')}"
                    for x in roles.items()
                )
            )
        )

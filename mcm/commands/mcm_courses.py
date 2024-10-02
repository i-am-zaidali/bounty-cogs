import typing

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..common.utils import lower_str_param, teacher_check
from .group import MCMGroup

mcm_courses = typing.cast(commands.Group, MCMGroup.mcm_courses)
mcm_courses_shorthand = typing.cast(
    commands.Group, MCMGroup.mcm_courses_shorthand
)


class MCMCourses(MixinMeta):
    @mcm_courses.command(name="announce", aliases=["ann", "a"])
    @teacher_check()
    async def mcm_courses_announce(
        self,
        ctx: commands.Context,
        shorthand: str,
        days: int,
        cost: int,
        *,
        location: str,
    ):
        """Ping for a course announcement"""
        conf = self.db.get_conf(ctx.guild)
        if not (role := ctx.guild.get_role(conf.course_role)):
            return await ctx.send("The course ping role has not been set yet.")

        if not (course := (conf.course_shorthands).get(shorthand.lower())):
            return await ctx.send("That course shorthand does not exist.")

        channel = ctx.guild.get_channel(conf.coursechannel)
        embed = discord.Embed(
            title="NEW COURSE!",
            description=f"New course started!\n\n"
            f"**TYPE:** {course}\n"
            f"**LOCATION:** {location}\n"
            f"**Start Time**: {days} days\n"
            f"**Cost per person per day**: {cost}\n",
            color=0x202026,
        )

        await (channel or ctx).send(
            role.mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )

    @mcm_courses_shorthand.command(name="add")
    async def mcm_courses_shorthand_add(
        self,
        ctx: commands.Context,
        shorthand: str = lower_str_param,
        *,
        course: str,
    ):
        """Add a course shorthand"""
        async with self.db.get_conf(ctx.guild) as conf:
            shorthands = conf.course_shorthands
            shorthands[shorthand] = course
            await ctx.tick()

    @mcm_courses_shorthand.command(name="remove")
    async def mcm_courses_shorthand_remove(
        self, ctx: commands.Context, shorthand: str = lower_str_param
    ):
        """Remove a course shorthand"""
        async with self.db.get_conf(ctx.guild) as conf:
            shorthands = conf.course_shorthands
            if shorthand not in shorthands:
                return await ctx.send("That shorthand does not exist.")
            shorthands.pop(shorthand)
            await ctx.tick()

    @mcm_courses_shorthand.command(name="list")
    async def mcm_courses_shorthand_list(self, ctx: commands.Context):
        """List the course shorthands"""
        shorthands = self.db.get_conf(ctx.guild).course_shorthands
        if not shorthands:
            return await ctx.send("No course shorthands have been added yet.")
        message = ""
        for shorthand, course in shorthands.items():
            message += f"{shorthand}: {course}\n"
        await ctx.send(message)

    @mcm_courses.command(name="pingrole", aliases=["pr"])
    async def mcm_courses_role(
        self, ctx: commands.Context, role: typing.Optional[discord.Role] = None
    ):
        """Set the role to ping for courses"""
        async with self.db.get_conf(ctx.guild) as conf:
            if role is None:
                return await ctx.send(
                    f"The course ping role is {getattr(ctx.guild.get_role(conf.course_role), 'mention', '`NOT SET`')}"
                )
            conf.course_role = role.id
            await ctx.tick()

    @mcm_courses.command(name="teacherrole", aliases=["tr"])
    async def mcm_courses_teacherrole(
        self, ctx: commands.Context, role: typing.Optional[discord.Role] = None
    ):
        """Set the role that can ping for courses"""
        async with self.db.get_conf(ctx.guild) as conf:
            if role is None:
                return await ctx.send(
                    f"The course teacher role is {getattr(ctx.guild.get_role(conf.course_teacher_role), 'mention', '`NOT SET`')}"
                )
            conf.course_teacher_role = role.id
            await ctx.tick()

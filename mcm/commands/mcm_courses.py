import typing

import discord
from redbot.core import commands
from tabulate import tabulate

from ..abc import MixinMeta
from ..common.utils import lower_str_param
from .group import MCMGroup

mcm_courses = typing.cast(commands.Group, MCMGroup.mcm_courses)
mcm_courses_shorthand = typing.cast(
    commands.Group, MCMGroup.mcm_courses_shorthand
)


class MCMCourses(MixinMeta):
    @mcm_courses_shorthand.command(name="add")
    async def mcm_courses_shorthand_add(
        self,
        ctx: commands.Context,
        shorthand: str = lower_str_param,
        *,
        course: str = commands.param(displayed_name="Full Course Name"),
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

    @mcm_courses.group(name="pingrole", aliases=["pr"])
    async def mcm_courses_role(
        self, ctx: commands.Context, role: typing.Optional[discord.Role] = None
    ):
        """Set the role to ping for courses"""

    @mcm_courses_role.command(name="set")
    async def mcm_courses_role_set(
        self, ctx: commands.Context, role: discord.Role
    ):
        """Set the role to ping for courses"""
        async with self.db.get_conf(ctx.guild) as conf:
            conf.course_role = role.id
            await ctx.tick()

    @mcm_courses_role.command(name="show")
    async def mcm_courses_role_show(self, ctx: commands.Context):
        """Show the role to ping for courses"""
        conf = self.db.get_conf(ctx.guild)
        role = ctx.guild.get_role(conf.course_role)
        await ctx.send(
            f"The course ping role is {getattr(role, 'mention', '`NOT SET`')}"
        )

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

    @mcm_courses.command(name="stats", aliases=["count"])
    async def mcm_courses_stats(self, ctx: commands.Context):
        """Get the course stats"""
        stats = self.db.get_conf(ctx.guild).course_count
        if not stats:
            return await ctx.send("No courses have been announced yet.")
        tabbed = tabulate(
            stats.items(),
            headers=["Course", "Count"],
            tablefmt="fancy_grid",
            maxcolwidths=[14, 4],
        )
        await ctx.send(
            embed=discord.Embed(
                title="Course Announcement Stats",
                description=f"```{tabbed}```",
            )
        )

import discord
from redbot.core import commands

from ..abc import CompositeMetaClass, MixinMeta
from ..common.utils import teacher_check


class MCMGroup(MixinMeta, metaclass=CompositeMetaClass):
    """Just the group commands for MCM"""

    @commands.group(name="missionchiefmetrics", aliases=["mcm"])
    @commands.guild_only()
    async def mcm(self, ctx: commands.Context):
        """The top level command for MCM management."""

    @mcm.group(name="vehicles", aliases=["vehicle", "vhc"])
    @commands.admin()
    async def mcm_vehicles(self, ctx: commands.Context):
        """Commands for managing vehicles."""

    @mcm_vehicles.group(name="categories", aliases=["category", "cat"])
    @commands.admin()
    async def mcm_vehicle_categories(self, ctx: commands.Context):
        """Commands for managing vehicle categories."""

    @mcm.group(name="stateroles", aliases=["staterole", "sr"])
    @commands.admin()
    async def mcm_stateroles(self, ctx: commands.Context):
        """Commands for managing stateroles"""

    @mcm.group(name="channel", aliases=["channels", "ch"])
    @commands.admin()
    async def mcm_channel(self, ctx: commands.Context):
        """Commands for managing channels"""

    @mcm.group(name="userstats", aliases=["us"])
    @commands.guild_only()
    async def mcm_userstats(self, ctx: commands.Context):
        """User stats"""

    @mcm.group(
        name="courses", aliases=["c", "course"], invoke_without_command=True
    )
    @teacher_check()
    async def mcm_courses(
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

        if not (course := conf.course_shorthands.get(shorthand.lower())):
            return await ctx.send("That course shorthand does not exist.")

        async with conf:
            conf.course_count.setdefault(course, 0)
            conf.course_count[course] += 1

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

    @mcm_courses.group(name="shorthand", aliases=["shorthands", "sh"])
    async def mcm_courses_shorthand(self, ctx: commands.Context):
        """Course shorthand management"""


# that's it

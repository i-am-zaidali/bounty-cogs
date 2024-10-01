from redbot.core import commands
from ..common.utils import teacher_check


class MCMGroup(commands.Cog):
    """Just the group commands for MCM"""

    @commands.group(name="missionchiefmetrics", aliases=["mcm"])
    async def mcm(self, ctx: commands.Context):
        """The top level command for MCM management."""

    @mcm.group(name="vehicles", aliases=["vehicle", "vhc"])
    async def mcm_vehicles(self, ctx: commands.Context):
        """Commands for managing vehicles."""

    @mcm_vehicles.group(name="categories", aliases=["category", "cat"])
    async def mcm_vehicle_categories(self, ctx: commands.Context):
        """Commands for managing vehicle categories."""

    @mcm.group(name="stateroles", aliases=["staterole", "sr"])
    async def mcm_stateroles(self, ctx: commands.Context):
        """Commands for managing stateroles"""

    @mcm.group(name="channel", aliases=["channels", "ch"])
    async def mcm_channel(self, ctx: commands.Context):
        """Commands for managing channels"""

    @mcm.group(name="userstats", aliases=["us"])
    @commands.guild_only()
    async def mcm_userstats(self, ctx: commands.Context):
        """User stats"""

    @mcm.group(name="courses", aliases=["c", "course"])
    @teacher_check()
    async def mcm_courses(self, ctx: commands.Context):
        """Commands for managing courses"""

    @mcm_courses.group(name="shorthand", aliases=["shorthands", "sh"])
    async def mcm_courses_shorthand(self, ctx: commands.Context):
        """Course shorthand management"""


# that's it

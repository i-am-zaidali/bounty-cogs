import typing

import discord
from redbot.core import app_commands, commands

from ..abc import CompositeMetaClass, MixinMeta
from ..common.utils import teacher_check
from ..views import RegistrationModal


class MCMGroup(MixinMeta, metaclass=CompositeMetaClass):
    """Just the group commands for MCM"""

    @commands.group(name="missionchiefmetrics", aliases=["mcm"])
    @commands.guild_only()
    async def mcm(self, ctx: commands.Context):
        """The top level command for MCM management."""

    @mcm.group(name="registration")
    @commands.admin()
    async def mcm_registration(self, ctx: commands.Context):
        """Commands for managing registrations"""

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

    # slash command just for register

    mcm_slash = app_commands.Group(
        name="missionchiefmetrics",
        description="MCM slash command, specifically for the registration system.",
    )

    @mcm_slash.command(name="register")
    @app_commands.guild_only()
    async def mcm_register(self, interaction: discord.Interaction):
        """Register for the MCM system"""
        ctx = typing.cast(
            commands.GuildContext, await self.bot.get_context(interaction)
        )
        conf = self.db.get_conf(ctx.guild)
        if not ctx.guild.get_channel(conf.modalertchannel):
            return await ctx.send(
                "Mods are unable to receive your registration request. Please contact an admin and ask them to setup a mod alerts channel.",
                ephemeral=True,
            )
        member = conf.get_member(ctx.author)
        if member.username is not None:
            return await ctx.send(
                "You are already registered",
                ephemeral=True,
            )

        elif member.registration_date is not None:
            return await ctx.send(
                "You have already registered and it's pending approval.",
                ephemeral=True,
            )

        if ctx.author.id in conf.registration.bans:
            duration = conf.registration.bans[ctx.author.id]
            if duration is None:
                return await ctx.send(
                    "You are banned from registering permanently.",
                    ephemeral=True,
                )

            elif duration > discord.utils.utcnow():
                return await ctx.send(
                    f"You are banned from registering until <t:{int(duration.timestamp())}:F>",
                    ephemeral=True,
                )

            async with conf:
                del conf.registration.bans[ctx.author.id]

        await interaction.response.send_modal(RegistrationModal(conf))


# that's it

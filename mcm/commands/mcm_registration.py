import typing

import discord
from redbot.core import commands

from ..abc import CompositeMetaClass, MixinMeta
from ..views import Paginator, RegisteredUsersSource
from .group import MCMGroup

mcm = typing.cast(commands.Group, MCMGroup.mcm)
mcm_registration = typing.cast(commands.Group, MCMGroup.mcm_registration)


class MCMRegistration(MixinMeta, metaclass=CompositeMetaClass):
    """Just the registration related commands for MCM"""

    @mcm.command(name="bind")
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    @commands.guild_only()
    async def mcm_bind(
        self, ctx: commands.Context, member: discord.Member, username: str
    ):
        """Register a user manually"""
        conf = self.db.get_conf(ctx.guild)
        memdata = conf.get_member(member.id)
        if memdata.username:
            return await ctx.send(
                f"This member is already registered as ***{memdata.username}***."
            )

        async with memdata:
            memdata.username = username
            memdata.registration_date = ctx.message.created_at
        try:
            await member.edit(nick=username)

        except discord.HTTPException:
            await ctx.send(
                "I was unable to change this user's nickname in the server. Please do so manually."
            )

        await ctx.tick()

    @mcm.command(name="unbind")
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    @commands.guild_only()
    async def mcm_unbind(
        self, ctx: commands.Context, member: discord.Member | str
    ):
        """De-register a user manually"""
        conf = self.db.get_conf(ctx.guild.id)
        if isinstance(member, str):
            memberid = next(
                (
                    mid
                    for mid, data in conf.members.items()
                    if data.username.lower() == member.lower()
                ),
                None,
            )
            if memberid is None:
                return await ctx.send("No member found with that username.")

            member = ctx.guild.get_member(memberid)

            if not member:
                return await ctx.send(
                    f"That username belong to a user with the id {memberid}, but they are not in the server anymore."
                )

        memdata = conf.get_member(member.id)
        if not memdata.username:
            return await ctx.send("This member is not registered.")

        async with memdata:
            memdata.username = None
            memdata.registration_date = None

        try:
            await member.edit(nick=member.nick.replace(memdata.username, ""))
        except discord.HTTPException:
            await ctx.send(
                "I was unable to change this user's nickname in the server. Please do so manually."
            )

        await ctx.tick()

    @mcm.command(name="registered", aliases=["listregistered", "lr"])
    @commands.guild_only()
    @commands.mod()
    async def mcm_registered(self, ctx: commands.Context):
        """List all registered members"""
        conf = self.db.get_conf(ctx.guild)
        members = conf.members
        registered = {
            ctx.guild.get_member(mid) or mid: data
            for mid, data in filter(
                lambda x: x[1].username and x[1].registration_date,
                members.items(),
            )
        }
        if not registered:
            return await ctx.send("No members have registered yet.")

        await Paginator(
            RegisteredUsersSource(registered, per_page=6), use_select=True
        ).start(ctx)

    @mcm_registration.group(name="questions", aliases=["question", "q"])
    async def mcm_registration_questions(self, ctx: commands.Context):
        """Registration question management"""

    @mcm_registration_questions.command(name="add")
    async def mcm_registration_questions_add(
        self, ctx: commands.Context, *, question: str
    ):
        """Add a registration question"""
        conf = self.db.get_conf(ctx.guild)
        if len(conf.registration.questions) >= 5:
            return await ctx.send("You can only have 5 questions at one time.")
        async with conf:
            conf.registration.questions[question] = True
        await ctx.tick()

    @mcm_registration_questions.command(name="remove", aliases=["delete", "rm"])
    async def mcm_registration_questions_remove(
        self, ctx: commands.Context, index: commands.Range[int, 0, 5]
    ):
        """Remove a registration question"""
        conf = self.db.get_conf(ctx.guild)
        if len(conf.registration.questions) > index:
            return await ctx.send("That question does not exist.")
        async with conf:
            question = list(conf.registration.questions.keys())[index - 1]
            del conf.registration.questions[question]
        await ctx.send(f"Removed question: {question}")
        await ctx.tick()

    @mcm_registration_questions.command(
        name="toggle", aliases=["enable", "disable"]
    )
    async def mcm_registration_questions_toggle(
        self, ctx: commands.Context, index: commands.Range[int, 0, 5]
    ):
        """Toggle a registration question"""
        conf = self.db.get_conf(ctx.guild)
        if len(conf.registration.questions) > index:
            return await ctx.send("That question does not exist.")

        val = (
            True
            if ctx.invoked_with == "enable"
            else False
            if ctx.invoked_with == "disable"
            else None
        )

        async with conf:
            question = list(conf.registration.questions.keys())[index - 1]
            conf.registration.questions[question] = val = (
                val
                if val is not None
                else not conf.registration.questions[question]
            )

        await ctx.send(
            f"Question `{question}` is now {'enabled' if val else 'disabled'}"
        )

    @mcm_registration_questions.command(name="show", aliases=["list"])
    async def mcm_registration_questions_show(self, ctx: commands.Context):
        """Show all registration questions"""
        conf = self.db.get_conf(ctx.guild)
        questions = conf.registration.questions
        if not questions:
            return await ctx.send("No questions have been set yet.")

        embed = discord.Embed(
            title="Registration Questions", color=await ctx.embed_color()
        )
        embed.description = "\n".join(
            f"{i+1}. {q}\n"
            f"  - {'enabled' if toggle else 'disabled' if i != 1 else 'Always enabled'}"
            for i, (q, toggle) in enumerate(questions.items())
        )
        await ctx.send(embed=embed)

    @mcm_registration.group(
        name="rejectionreasons", aliases=["rejectionreason", "rr"]
    )
    async def mcm_registration_reasons(self, ctx: commands.Context):
        """Registration rejection reasons"""

    @mcm_registration_reasons.command(name="add")
    async def mcm_registration_reasons_add(
        self, ctx: commands.Context, *, reason: str
    ):
        """Add a registration rejection reason"""
        conf = self.db.get_conf(ctx.guild)
        if len(conf.registration.rejection_reasons) >= 5:
            return await ctx.send("You can only have 5 reasons at one time.")
        async with conf:
            conf.registration.rejection_reasons.append(reason)
        await ctx.tick()

    @mcm_registration_reasons.command(name="remove", aliases=["delete", "rm"])
    async def mcm_registration_reasons_remove(
        self, ctx: commands.Context, index: commands.Range[int, 0, 5]
    ):
        """Remove a registration rejection reason"""
        conf = self.db.get_conf(ctx.guild)
        if len(conf.registration.rejection_reasons) > index:
            return await ctx.send("That reason does not exist.")
        async with conf:
            reason = conf.registration.rejection_reasons.pop(index - 1)
        await ctx.send(f"Removed reason: {reason}")
        await ctx.tick()

    @mcm_registration_reasons.command(name="show", aliases=["list"])
    async def mcm_registration_reasons_show(self, ctx: commands.Context):
        """Show all registration rejection reasons"""
        conf = self.db.get_conf(ctx.guild)
        reasons = conf.registration.rejection_reasons
        if not reasons:
            return await ctx.send("No reasons have been set yet.")

        embed = discord.Embed(
            title="Registration Rejection Reasons",
            color=await ctx.embed_color(),
        )
        embed.description = "\n".join(
            f"{i+1}. {reason}" for i, reason in enumerate(reasons)
        )
        await ctx.send(embed=embed)

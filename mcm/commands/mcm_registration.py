import datetime
import fnmatch
import typing

import discord
from redbot.core import commands

from ..abc import CompositeMetaClass, MixinMeta
from ..common.utils import DateInPast, MCMUsernameToDiscordUser
from ..views import AutoDebindView, Paginator, RegisteredUsersSource
from .group import MCMGroup

mcm = typing.cast(commands.Group, MCMGroup.mcm)
mcm_registration = typing.cast(commands.Group, MCMGroup.mcm_registration)


class MCMRegistration(MixinMeta, metaclass=CompositeMetaClass):
    """Just the registration related commands for MCM"""

    @mcm.command(name="bind")
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    @commands.guild_only()
    @commands.mod()
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
            memdata.registered_by = ctx.author.id

        roles = member.roles

        if (
            conf.registration.registered_role
            and (role := ctx.guild.get_role(conf.registration.registered_role))
            and not member.get_role(role.id)
        ):
            roles.append(role)

        try:
            await member.edit(nick=username, roles=roles)

        except discord.HTTPException:
            await ctx.send(
                "I was unable to change this user's nickname in the server. Please do so manually."
            )

        await ctx.tick()

    @mcm.command(name="unbind", aliases=["debind"])
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    @commands.mod()
    @commands.guild_only()
    async def mcm_unbind(
        self,
        ctx: commands.Context,
        member: discord.Member | discord.User = commands.param(
            converter=MCMUsernameToDiscordUser
        ),
    ):
        """De-register a user manually

        Also accepts an MCM username to de-register"""
        conf = self.db.get_conf(ctx.guild.id)

        memdata = conf.get_member(member.id)
        if not memdata.username:
            return await ctx.send(
                "This member is registered but is not found in the server."
            )

        username = memdata.username

        async with memdata:
            memdata.username = None
            memdata.registration_date = None

        if isinstance(member, discord.User):
            await ctx.tick()
            return

        roles = member.roles

        if (
            conf.registration.registered_role
            and (role := ctx.guild.get_role(conf.registration.registered_role))
            and member.get_role(role.id)
        ):
            roles.remove(role)

        try:
            await member.edit(
                nick=(member.nick or "").replace(username, ""), roles=roles
            )
        except discord.HTTPException:
            await ctx.send(
                "I was unable to change this user's nickname in the server. Please do so manually."
            )

        await ctx.tick()

    @mcm.command(name="bound")
    @commands.guild_only()
    @commands.mod()
    async def mcm_bound(
        self,
        ctx: commands.Context,
        member: discord.Member | discord.User = commands.param(
            converter=MCMUsernameToDiscordUser
        ),
    ):
        """A command to check what username a user is registered with

        This command can also work vice versa if you give it an MCM username and it will tell you which user is registered to that username"""
        conf = self.db.get_conf(ctx.guild)
        memdata = conf.get_member(member.id)
        if not memdata.username:
            return await ctx.send("This member is not registered.")

        await ctx.send(
            f"{member.mention} ({member.id}) was registered as ***{memdata.username}*** {f'by <@{mid}> ({mid})' if (mid := memdata.registered_by) else ''}on <t:{int(memdata.registration_date.timestamp())}:F>"
        )

    @mcm.command(name="autodebind")
    @commands.guild_only()
    @commands.mod()
    async def mcm_autodebind(
        self,
        ctx: commands.Context,
        *,
        date: datetime.datetime = commands.param(converter=DateInPast),
    ):
        """Automatically de-register members who registered after a certain date and have since left the server"""
        conf = self.db.get_conf(ctx.guild)
        members = conf.members
        members_to_debind = [
            memberid
            for memberid, member in members.items()
            if member.registration_date
            and member.username
            and member.registration_date > date
            # and not ctx.guild.get_member(memberid)
        ]
        if not members_to_debind:
            return await ctx.send("No members to de-register.")

        view = AutoDebindView(ctx, members_to_debind)
        embed = discord.Embed(
            color=await ctx.embed_color(),
            title="De-register Members",
            description=f"The following users registered after <t:{int(date.timestamp())}:F> and have since left the server. Would you like to de-register them?\n\n"
            + "\n".join(
                f"- <@{memberid}> ({memberid})\n  - {members[memberid].username}\n"
                for memberid in members_to_debind
            ),
        )
        await ctx.send(embed=embed, view=view)

    @mcm.command(name="search", aliases=["find"])
    @commands.guild_only()
    @commands.mod()
    async def mcm_search(self, ctx: commands.Context, *, searchpattern: str):
        """
        Search for members by their MCM username

        This command accepts glob pattern matching.
        `*` matches anything where it is placed between one and infinite times
        `?` matches any single character 0 or 1 times

        for example, if the registered usernames are: zay, zeh, zee, and grape
        The following pattern `z*` will match: zay, zeh and zee
        and `*e*` will match: zee and zeh.

        You can use [this tool](https://www.digitalocean.com/community/tools/glob) to test out patterns"""
        # `[seq]` matches any character in sequence
        # `[!seq]` matches any character not in sequence
        # `{a,b,c}` matches any of the sequences
        conf = self.db.get_conf(ctx.guild)
        members = conf.members
        all_usernames = [
            (ctx.guild.get_member(mid) or mid, data)
            for mid, data in members.items()
            if data.username
            and data.registration_date
            and fnmatch.fnmatch(data.username, searchpattern)
        ]
        if not all_usernames:
            return await ctx.send("No members found with that search pattern.")

        embed = discord.Embed(
            color=await ctx.embed_color(),
            title="Search Results",
            description=f"Search pattern: `{searchpattern}`\n\n"
            + "\n".join(
                f"- {getattr(member, 'mention', 'User not found in server')} ({getattr(member, 'id', member)})\n"
                f"  - {data.username}\n  - Registered: <t:{int(data.registration_date.timestamp())}:F>"
                for member, data in all_usernames
            ),
        )
        await ctx.send(embed=embed)

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
            RegisteredUsersSource([*registered.items()], per_page=6),
            use_select=True,
        ).start(ctx)

    @commands.admin()
    @mcm_registration.command(name="role")
    async def mcm_registration_role(self, ctx: commands.Context, role: discord.Role):
        """Set the role to be given to registered members"""
        conf = self.db.get_conf(ctx.guild)
        async with conf:
            conf.registration.registered_role = role.id
        await ctx.tick()

    @commands.admin()
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

    @mcm_registration_questions.command(name="toggle", aliases=["enable", "disable"])
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
                val if val is not None else not conf.registration.questions[question]
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
            f"{i + 1}. {q}\n"
            f"  - {'enabled' if toggle else 'disabled' if i != 1 else 'Always enabled'}"
            for i, (q, toggle) in enumerate(questions.items())
        )
        await ctx.send(embed=embed)

    @mcm_registration.group(name="rejectionreasons", aliases=["rejectionreason", "rr"])
    @commands.admin()
    async def mcm_registration_reasons(self, ctx: commands.Context):
        """Registration rejection reasons"""

    @mcm_registration_reasons.command(name="add")
    async def mcm_registration_reasons_add(
        self, ctx: commands.Context, *, reason: commands.Range[str, 1, 100]
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
            f"{i + 1}. {reason}" for i, reason in enumerate(reasons)
        )
        await ctx.send(embed=embed)

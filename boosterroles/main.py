import asyncio
from redbot.core.bot import Red
from redbot.core import commands, Config
import discord
from redbot.core.utils import chat_formatting as cf
import typing

import logging
from emoji import emoji_list
from redbot.vendored.discord.ext.menus import ListPageSource
from .views import Paginator

log = logging.getLogger("red.bounty.boosterroles")


class EmojiAttachmentConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        if argument.lower() == "attachment":
            att = ctx.message.attachments[0]
            if att.filename.endswith((".png", ".jpeg")):
                if att.size > 2048000:
                    raise commands.BadArgument("Attachment size exceeds 2048KB")
                return ctx.message.attachments[0]
            raise commands.BadArgument("Invalid attachment provided")
        if emoji := emoji_list(argument):
            return emoji[0]["emoji"]
        else:
            try:
                return str(await commands.EmojiConverter().convert(ctx, argument))

            except discord.HTTPException:
                raise commands.BadArgument("Invalid emoji provided")

            except discord.InvalidData:
                raise commands.BadArgument("Invalid emoji provided")


class UserRoleConfigFlags(commands.FlagConverter):
    name: typing.Optional[str]
    color: typing.Optional[typing.Union[discord.Color, typing.Literal["random"]]]
    hoist: typing.Optional[bool]
    mentionable: typing.Optional[bool]
    icon: typing.Optional[typing.Union[discord.Attachment, discord.Emoji]] = (
        commands.flag(
            name="display_icon",
            converter=typing.Optional[EmojiAttachmentConverter],
            aliases=["icon"],
        )
    )

    def to_json(self):
        return dict(
            filter(
                lambda x: x[1] is not None,
                {
                    "name": self.name,
                    "color": (
                        self.color.value
                        if isinstance(self.color, discord.Color)
                        else (
                            discord.Color.random().value
                            if self.color == "random"
                            else None
                        )
                    ),
                    "hoist": self.hoist,
                    "mentionable": self.mentionable,
                    "display_icon": self.icon,
                }.items(),
            )
        )


class RoleConfigFlags(UserRoleConfigFlags):
    above: typing.Optional[discord.Role]

    def to_json(self):
        json = super().to_json()
        json.pop("icon", None)
        if self.above:
            json["above"] = self.above.id

        return json


class BoosterRoles(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "booster_role": {
                "name": "Booster Role",
                "above": None,
                "color": discord.Color.random().value,
                "hoist": False,
                "mentionable": False,
            },
            "disallowed_properties": [],
            "threshold": 1,
            "role_limit": 10,
        }
        default_member = {"booster_role": {}, "boosts": 0}
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

    @commands.Cog.listener()
    async def on_member_boost(
        self,
        member: discord.Member,
        _type: typing.Literal["system", "premium_subscriber_role"],
    ):
        if not _type == "system":
            log.debug(
                "Boost event ignored because it was triggered by premium role addition."
            )
        boosts = await self.config.member(member).boosts()
        boosts += 1
        await self.config.member(member).boosts.set(boosts)

    @commands.Cog.listener()
    async def on_member_unboost(
        self, member: discord.Member, _type: typing.Literal["premium_subscriber_role"]
    ):
        # event will only be triggered when the user unboosts the server completely
        boosts = await self.config.member(member).boosts()
        if boosts == 0:
            return
        log.debug(
            f"{member.display_name} has unboosted the server, removing booster role."
        )
        role_id = await self.config.member(member).booster_role.id()
        role = member.guild.get_role(role_id)
        if role:
            log.debug(f"Deleting role {role.name}")
            await role.delete(reason="Booster role unassignment")
            log.debug(f"Role {role.name} deleted.")

        await self.config.member(member).boosts.set(0)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        role_id = await self.config.member(member).booster_role.id()
        role = member.guild.get_role(role_id)
        if role:
            log.debug(
                f"{member.display_name} has left the server, removing booster role."
            )
            log.debug(f"Deleting role {role.name}")
            await role.delete(reason="User left the server")
            log.debug(f"Role {role.name} deleted.")

        await self.config.member(member).boosts.set(0)

    @commands.group(aliases=["boosterroles"])
    @commands.guild_only()
    async def boosterrole(self, ctx: commands.Context):
        """Manage booster roles"""

    @boosterrole.command()
    @commands.admin()
    async def setconfig(self, ctx: commands.Context, *, flags: RoleConfigFlags):
        """
        Set the configuration for the booster role

        This command uses flags to set the configuration for the booster role.
        The syntax of a flag is:
        `flagname: value`

        The available flags are:
        - `above`: The role above which the booster role should be placed
        - `name`: The name of the booster role
        - `color`: The color of the booster role
        - `hoist`: Whether the booster role should be hoisted
        - `mentionable`: Whether the booster role should be mentionable"""
        if not flags.to_json():
            return await ctx.send("No flags provided.")

        async with self.config.guild(ctx.guild).booster_role() as booster_role:
            booster_role.update(flags.to_json())

        await ctx.tick()

    @boosterrole.command()
    @commands.admin()
    async def getconfig(self, ctx: commands.Context):
        """
        Get the configuration for the booster role
        """
        config = await self.config.guild(ctx.guild).booster_role()
        embed = discord.Embed(
            title="Booster Role Configuration", color=discord.Color(config["color"])
        )
        for key, value in config.items():
            embed.add_field(name=key, value=value)

        await ctx.send(embed=embed)

    @boosterrole.command()
    @commands.max_concurrency(2, per=commands.BucketType.guild)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.cooldown(1, 180)
    async def assign(self, ctx: commands.Context):
        """
        Assign the booster role to yourself"""
        member = ctx.author
        config = await self.config.guild(ctx.guild).booster_role()
        threshold = await self.config.guild(ctx.guild).threshold()
        roleid = await self.config.member(member).booster_role.id()
        if roleid:
            role = ctx.guild.get_role(roleid)
            if role:
                return await ctx.send(
                    f"{member.display_name} already has the booster role {role.mention}."
                )

        if await self.config.guild(ctx.guild).role_limit() <= len(
            [
                *filter(
                    lambda x: ctx.guild.get_role(x["booster_role"].get("id")),
                    (await self.config.all_members(ctx.guild)).values(),
                )
            ]
        ):
            return await ctx.send("Role limit reached. Cannot assign more roles.")
        boosts = await self.config.member(member).boosts()
        above_role = ctx.guild.get_role(config.pop("above"))
        if not above_role:
            above_role = ctx.guild.default_role
            await ctx.send("Above role not found. Assigning role to default position.")

        if boosts < threshold:
            return await ctx.send(
                f"{member.display_name} has not boosted enough times to receive the booster role."
            )

        try:
            role = await ctx.guild.create_role(
                **config,
                reason="Booster role assignment",
            )

        except discord.Forbidden:
            return await ctx.send(
                "I do not have the necessary permissions to create roles"
            )

        except discord.HTTPException as e:
            log.exception("Role creation failed", exc_info=e)
            return await ctx.send("Role creation failed. Check logs.")

        else:

            try:
                roles = [*ctx.guild.roles[1:]]
                try:
                    roles.remove(role)
                except ValueError:
                    pass
                try:
                    position = roles.index(above_role)
                except ValueError:
                    position = -1
                roles.insert(position + 1, role)
                payload = {role: ind for ind, role in enumerate(roles, 1)}
                await ctx.guild.edit_role_positions(payload)
            except discord.Forbidden:
                log.warning("Failed to edit role position")
            except discord.HTTPException as e:
                log.exception("Role position edit failed", exc_info=e)
                await ctx.send("Role position edit failed. Check logs.")
            try:
                await member.add_roles(role, reason="Booster role assignment")

            except discord.Forbidden:
                return await ctx.send(
                    "I do not have the necessary permissions to assign roles"
                )

            except discord.HTTPException as e:
                log.exception("Role assignment failed", exc_info=e)
                return await ctx.send("Role assignment failed. Check logs.")

        async with self.config.member(member).booster_role() as booster_role:
            booster_role.update(
                dict(
                    id=role.id,
                    color=role.color.value,
                    hoist=role.hoist,
                    mentionable=role.mentionable,
                )
            )

        await ctx.send(
            f"{member.display_name} has been assigned the booster role {role.mention}."
        )

    @boosterrole.command(name="unassign", usage="")
    @commands.max_concurrency(1, per=commands.BucketType.guild)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @commands.cooldown(1, 180)
    async def unassign(
        self, ctx: commands.Context, member: discord.Member = commands.Author
    ):
        """
        Unassign the booster role from yourself"""
        if member != ctx.author and not await self.bot.is_admin(ctx.author):
            member = ctx.author

        role_id = await self.config.member(ctx.author).booster_role.id()
        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.send("Booster role not found.")

        try:
            await role.delete(reason="Booster role unassignment")
        except discord.Forbidden:
            return await ctx.send(
                "I do not have the necessary permissions to remove roles"
            )

        except discord.HTTPException as e:
            log.exception("Role removal failed", exc_info=e)
            return await ctx.send("Role removal failed. Check logs.")

        await ctx.send(f"{member.display_name} has been unassigned the booster role.")
        await self.config.member(member).clear()

    @boosterrole.command(name="setthreshold", aliases=["setboostreq", "threshold"])
    @commands.admin()
    async def setthreshold(
        self, ctx: commands.Context, threshold: commands.positive_int
    ):
        """
        Set the number of boosts required to receive the booster role"""
        await self.config.guild(ctx.guild).threshold.set(threshold)
        await ctx.tick()

    @boosterrole.command(name="showsettings", aliases=["settings", "ss"])
    async def showsettings(self, ctx: commands.Context):
        """
        Show the current booster role settings"""
        config = await self.config.guild(ctx.guild).booster_role()
        threshold = await self.config.guild(ctx.guild).threshold()
        disallowed = await self.config.guild(ctx.guild).disallowed_properties()
        embed = discord.Embed(
            title="Booster Role Settings", color=await ctx.embed_color()
        )
        embed.add_field(name="Threshold", value=threshold)
        for key, value in config.items():
            embed.add_field(name=key, value=value)

        embed.add_field(
            name="Disallowed Properties", value=cf.humanize_list(disallowed) or "None"
        )

        embed.add_field(
            name="Role Limit",
            value=await self.config.guild(ctx.guild).role_limit(),
        )

        await ctx.send(embed=embed)

    @boosterrole.command(name="setboosts", aliases=["setboostcount"])
    @commands.admin()
    async def setboosts(
        self, ctx: commands.Context, member: discord.Member, count: int
    ):
        """
        Set the number of boosts for a member incase they are wrongly shown in `[p]showboosts`
        """
        await self.config.member(member).boosts.set(count)
        await ctx.tick()

    @boosterrole.command(name="showboosts", aliases=["boosts"])
    async def showboosts(self, ctx: commands.Context, member: discord.Member):
        """
        Show the number of boosts a member has"""
        boosts = await self.config.member(member).boosts()
        await ctx.send(f"{member.display_name} has {boosts} boosts.")

    @boosterrole.group(name="myrole", aliases=["mine"], invoke_without_command=True)
    async def myrole(self, ctx: commands.Context):
        """
        View your booster role settings"""
        config = await self.config.member(ctx.author).booster_role()
        if not config:
            return await ctx.send("You do not have a booster role.")
        role = ctx.guild.get_role(config["id"])
        if not role:
            return await ctx.send("Booster role not found.")
        self.myrole.reset_cooldown(ctx)
        embed = discord.Embed(
            title="Booster Role Configuration", color=discord.Color(config["color"])
        )
        for key, value in config.items():
            embed.add_field(name=key, value=value)

        return await ctx.send(embed=embed)

    @myrole.command(name="edit", cooldown_after_parsing=True)
    @commands.cooldown(1, 180, commands.BucketType.member)
    async def myroleedit(self, ctx: commands.Context, *, flags: UserRoleConfigFlags):
        """
        Edit your booster role

        This command uses flags to configure or view your booster role.
        The syntax of a flag is:
        `flagname: value`

        The available flags are:

        - `name`: The name of the booster role
        - `color`: The color of the booster role
        - `hoist`: Whether the booster role should be hoisted
        - `mentionable`: Whether the booster role should be mentionable
        - `icon`: The icon of the booster role. valid values for this are: `attachment` or  an emoji

            (If `attachment` is used the bot will read the image from the first attachment)

        For example:
        `[p]boosterrole myrole edit color: red icon: 🎉`
        `[p]boosterrole myrole edit icon: attachment`
        `[p]boosterrole myrole edit hoist: true`

        If no flags are provided, the current configuration will be displayed.
        """
        config = await self.config.member(ctx.author).booster_role()
        disallowed = await self.config.guild(ctx.guild).disallowed_properties()
        if not config:
            return await ctx.send("You do not have a booster role.")
        role = ctx.guild.get_role(config["id"])
        if not role:
            return await ctx.send("Booster role not found.")

        flags_json = flags.to_json()

        if not flags_json:
            return await ctx.send("No flags provided.")

        if any(prop in disallowed for prop in flags_json):
            return await ctx.send("You are not allowed to edit this property.")

        flags_json.update(
            {
                "display_icon": await getattr(
                    di := flags_json.pop("display_icon"),
                    "read",
                    lambda: asyncio.sleep(0, di),
                )()
            }
        )

        try:
            await role.edit(**flags_json, reason="Booster role configuration")
        except discord.Forbidden:
            log.warning("Failed to edit role")
            return await ctx.send(
                "I do not have the necessary permissions to edit roles"
            )

        except discord.HTTPException as e:
            log.exception("Role edit failed", exc_info=e)
            return await ctx.send("Role edit failed. Check logs.")

        async with self.config.member(ctx.author).booster_role() as booster_role:
            booster_role.update(flags.to_json())

        await ctx.send("Booster role configuration updated.")

    @boosterrole.command(
        name="disallowproperties", aliases=["disallow"], require_var_positional=True
    )
    async def disallowproperties(
        self,
        ctx: commands.Context,
        *properties: typing.Literal["name", "color", "hoist", "mentionable", "icon"],
    ):
        """
        Disallow certain properties from being edited by users"""
        await self.config.guild(ctx.guild).disallowed_properties.set(properties)
        await ctx.tick()

    @boosterrole.command(name="list")
    async def listroles(self, ctx: commands.Context):
        """
        List all booster roles in the server"""
        members = await self.config.all_members(ctx.guild)
        if not members:
            return await ctx.send("No booster roles found.")

        async def format_page(menu, page: list[tuple[int, dict]]):
            embed = discord.Embed(title="Booster Roles", color=await ctx.embed_color())
            for member_id, data in page:
                member = ctx.guild.get_member(member_id)
                role = ctx.guild.get_role(data["booster_role"]["id"])
                embed.add_field(
                    name=getattr(member, "display_name", f"User not found")
                    + f" ({member_id})",
                    value="Role: "
                    + getattr(
                        role,
                        "mention",
                        f"Role not found ({data['booster_role']['id']})",
                    )
                    + "\nBoosts: "
                    + str(data["boosts"]),
                    inline=False,
                )
            return embed

        source = ListPageSource(
            [
                *filter(
                    lambda x: ctx.guild.get_role(x[1]["booster_role"].get("id")),
                    members.items(),
                )
            ],
            per_page=10,
        )
        source.format_page = format_page

        await Paginator(source, use_select=True).start(ctx)

    @boosterrole.command(name="listboosters", aliases=["boosters"])
    async def listboosters(self, ctx: commands.Context):
        """
        List all boosters in the server"""
        members = await self.config.all_members(ctx.guild)
        if not members:
            return await ctx.send("No boosters found.")

        async def format_page(menu, page: list[tuple[int, dict]]):
            embed = discord.Embed(title="Boosters", color=await ctx.embed_color())
            for member_id, data in page:
                member = ctx.guild.get_member(member_id)
                embed.add_field(
                    name=getattr(member, "display_name", "User not found")
                    + f" ({member_id})",
                    value="Boosts: " + str(data["boosts"]),
                    inline=False,
                )
            return embed

        source = ListPageSource(list(members.items()), per_page=10)
        source.format_page = format_page

        await Paginator(source, use_select=True).start(ctx)

    @boosterrole.command(name="rolelimit")
    @commands.admin()
    async def rolelimit(self, ctx: commands.Context, limit: commands.positive_int):
        """
        Set the maximum number of booster roles allowed in the server"""
        await self.config.guild(ctx.guild).role_limit.set(limit)
        await ctx.tick()

    @boosterrole.command(name="purgeroles")
    @commands.admin()
    async def purgeroles(self, ctx: commands.Context):
        """
        Purge all booster roles in the server"""
        members = await self.config.all_members(ctx.guild)
        if not members:
            return await ctx.send("No booster roles found.")

        await ctx.send("Purging booster roles...")
        async with ctx.typing():
            for member_id, data in members.items():
                role = ctx.guild.get_role(data["booster_role"].get("id"))
                if role:
                    await role.delete(reason="Booster role purge")

                await self.config.member_from_ids(ctx.guild.id, member_id).clear()

        await ctx.send("Booster roles purged.")

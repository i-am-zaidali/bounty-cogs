import logging
from typing import Dict, List, Optional, Set, TypedDict

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter, bounded_gather
from redbot.core.utils import chat_formatting as cf

from .conv import FuzzyMember, FuzzyRole

log = logging.getLogger("red.misanthropist.RoleDetector")


class GuildSettings(TypedDict):
    channel: Optional[int]
    role: Optional[int]
    floorwarden: Optional[int]
    last_output: Optional[str]


class RoleDetector(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(self, 2784481001, force_registration=True)
        self.config.register_guild(channel=None, role=None, floorwarden=None)

        self.cache: Dict[int, GuildSettings] = {}

    async def _build_cache(self):
        for guild, data in (await self.config.all_guilds()).items():
            data.update({"last_output": None, "floorwarden": None})
            self.cache.update({guild: data})

    async def get_member_and_roles(
        self,
        guild: discord.Guild,
        string: str,
        ctx: commands.Context,
        present: List[discord.Member],
    ):
        username, roles = string.split(",", 1)
        r = roles.split(",")

        try:
            rank, cls = r

        except Exception:
            rank, cls = r[0], ""

        check = lambda x: x.name.lower() == rank.lower()
        check2 = lambda x: x.name.lower() == cls.lower()
        check3 = lambda x: x.display_name.casefold() == username.casefold()

        user = guild.get_member_named(username)  # or discord.utils.find(
        # check3, guild.members
        # )  # or await FuzzyMember().convert(ctx, username)

        return (
            user if user not in present else None,
            discord.utils.find(check, guild.roles) or await FuzzyRole().convert(ctx, rank),
            (discord.utils.find(check2, guild.roles) or await FuzzyRole().convert(ctx, cls))
            if cls
            else None,
        )

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        data = self.cache.get(message.guild.id)

        if not data:
            return

        if message.channel.id != data["channel"]:
            return

        if message.attachments:
            attachment = message.attachments[0]
            text = str(await attachment.read(), "utf-8")
            message.content += f"\n{text}"

        guild_role = message.guild.get_role(data["role"])
        floorwarden = message.guild.get_role(data["floorwarden"])

        output_success = ""
        not_found = []
        failed = []

        roles_added: Set[discord.Member] = set()

        fake_ctx = await self.bot.get_context(message)

        await message.channel.send(
            "Batch job received - Processing guild roster. This may take a while..."
        )

        async with message.channel.typing():
            remove = "--no-remove" not in message.content.lower()
            message.content = message.content.replace("--no-remove", "")
            _iter = AsyncIter(message.content.splitlines(), 5, 100)
            async for line in _iter.filter(lambda x: bool(x)):
                user, rank, cls = await self.get_member_and_roles(
                    message.guild, line, fake_ctx, roles_added
                )
                if not user:
                    not_found.append(line.split(",", 1)[0])
                    continue

                to_add = list(
                    filter(
                        lambda x: isinstance(x, discord.Role),
                        [guild_role, rank, cls],
                    )
                )
                if to_add == user.roles:
                    log.debug(f"{user} already has all roles ({cf.humanize_list(to_add)}).")
                    to_add = []

                elif set.issubset(set(to_add), set(user.roles)):
                    log.debug(
                        f"{user} has some extra roles apart from the required ones. Removing extra."
                    )
                    to_remove = set(user.roles).difference(to_add)
                    to_remove.remove(message.guild.default_role)
                    try:
                        await user.remove_roles(*to_remove, reason="RoleDetector")

                    except Exception as e:
                        log.exception(f"Failed to remove roles from {user}.", exc_info=e)
                        failed.append(user.display_name)
                        continue

                else:
                    log.debug(
                        f"{user} has no roles or some roles are missing. Adding roles ({cf.humanize_list(to_add)})."
                    )
                    try:
                        await user.edit(roles=to_add, reason="RoleDetector")

                    except Exception as e:
                        log.exception("AAAAAAAAAAAA", exc_info=e)
                        failed.append(user.display_name)
                        continue

                roles_added.add(user)
                output_success += (
                    f"{user.display_name} ({cf.humanize_list(to_add) or 'No roles added.'})\n"
                )

            if remove:
                users_to_remove = filter(lambda x: x not in roles_added, message.guild.members)

                bounded_gather(
                    *map(
                        lambda x: x.remove_roles(
                            *filter(lambda y: not y.is_default(), x.roles), reason="RoleDetector"
                        ),
                        users_to_remove,
                    ),
                    limit=5,
                )

        output = "Detected following users in the server:\n" f"{output_success}\n\n" + (
            f"These users were not found so were ignored: \n{cf.humanize_list(not_found)}\n\n"
            if not_found
            else ""
        ) + (
            f"The following users failed to have their roles added to them due to permissions issues:\n{cf.humanize_list(failed)}\n\n"
            if failed
            else ""
        ) + (
            f"The remaining users are getting their roles removed from them." if remove else ""
        )

        self.cache[message.guild.id]["last_output"] = output

        for p in cf.pagify(output, delims=", ", page_length=2000):  # istg discord
            await message.channel.send(p)

        shitter = discord.utils.find(lambda x: x.name.lower() == "shitter", message.guild.roles)
        shitters = "\n".join(
            map(
                lambda x: f"**{x.display_name}**: {x.mention} ({x.id})",
                sorted(
                    filter(lambda x: shitter in x.roles, message.guild.members),
                    key=lambda x: x.display_name,
                ),
            )
        )

        if shitters:
            await message.channel.send(
                embed=discord.Embed(
                    title="Shitters",
                    description=shitters,
                    color=discord.Color.red(),
                )
            )

    @commands.group(name="roledetector", aliases=["rd"], invoke_without_command=True)
    async def rd(self, ctx: commands.Context):
        """
        Base command to set up roledetector"""
        return await ctx.send_help()

    @rd.command(name="channel", aliases=["c"])
    async def rd_c(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Set the channel to track for roledetector"""
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await ctx.send(cf.success(f"Channel set to {channel.mention}"))
        await self._build_cache()

    @rd.command(name="role", aliases=["r"])
    async def rd_r(self, ctx: commands.Context, role: discord.Role):
        """
        Set the role to assign to users."""
        await self.config.guild(ctx.guild).role.set(role.id)
        await ctx.send(cf.success(f"Role set to {role.mention}"))
        await self._build_cache()

    @rd.command(name="floorwarden", aliases=["fw"])
    async def rd_fw(self, ctx: commands.Context, role: discord.Role):
        """
        Set the floorwarden role."""
        await self.config.guild(ctx.guild).floorwarden.set(role.id)
        await ctx.send(cf.success(f"FloorWarden role set to {role.mention}"))
        await self._build_cache()

    @rd.command(name="last", aliases=["lastoutput", "lo"])
    async def rd_lo(self, ctx: commands.Context):
        output = self.cache.get(ctx.guild.id)

        if not output or not output["last_output"]:
            return await ctx.send("There has been no last role detection.")

        return await ctx.send(output)

    @rd.command(name="listshitters", aliases=["ls", "shitters"])
    async def rd_ls(self, ctx: commands.Context, prefix: str = "/gpromote", suffix: str = "-Whitemane"):
        """
        See a list of shitters in the server.

        The prefix and suffix arguments are optional.
        The former is used to add a prefix to the list of names.
        and the latter is used to add a suffix to each individual name without space.
        If you don't want a prefix or suffix, you can pass None, or False to disable it.
        It is /gpromote and -Whitemane by default."""
        if prefix.lower() in ("false", "None"):
            prefix = ""

        else:
            prefix += " "
            
        if suffix.lower() in ("false", "None"):
            suffix = ""

        shitter = discord.utils.find(lambda x: x.name.lower() == "shitter", ctx.guild.roles)
        shitters = "\n".join(
            map(
                lambda x: f"{prefix}{x.display_name}{suffix}",
                sorted(
                    filter(lambda x: shitter in x.roles, ctx.guild.members),
                    key=lambda x: x.display_name,
                ),
            )
        )

        if shitters:
            embed = discord.Embed(
                title="Shitters of the server.",
                color=discord.Color.red(),
            )
            for page in cf.pagify(shitters, page_length=255):
                embed.add_field(name="\u200b", value=page, inline=False)
                
            return await ctx.send(
                embed=embed
            )

        await ctx.send("No shitters found.")

    @rd.command(name="show", aliases=["ss", "showsettings"])
    async def rd_ss(self, ctx: commands.Context):
        """
        See the settings for roledetector in your server."""
        data = self.cache.get(ctx.guild.id)
        if not data:
            return await ctx.send("RoleDetector is not setup in your server.")

        embed = discord.Embed(title=f"RoleDetector settings in __**{ctx.guild.name}**__")

        embed.description = f"Channel: <#{data['channel']}>\n\n" f"Role: <@&{data['role']}>"

        return await ctx.send(embed=embed)

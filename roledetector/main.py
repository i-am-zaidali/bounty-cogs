import logging
from typing import Dict, Optional, TypedDict

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
    last_output: Optional[str]


class RoleDetector(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(self, 2784481001, force_registration=True)
        self.config.register_guild(channel=None, role=None)

        self.cache: Dict[int, GuildSettings] = {}

    async def _build_cache(self):
        for guild, data in (await self.config.all_guilds()).items():
            data.update({"last_output": None})
            self.cache.update({guild: data})

    async def get_member_and_roles(self, guild: discord.Guild, string: str, ctx: commands.Context):
        username, roles = string.split(",", 1)
        r = roles.split(",")

        try:
            rank, cls = r

        except Exception:
            rank, cls = r[0], ""

        check = lambda x: x.name.lower() == rank.lower()
        check2 = lambda x: x.name.lower() == cls.lower()

        return (
            guild.get_member_named(username) or await FuzzyMember().convert(ctx, username),
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

        output_success = ""
        output_not_found = ""
        output_failed = ""

        roles_added: set[discord.Member] = set()

        role_member: dict[discord.Role, list[discord.Member]] = {}

        fake_ctx = await self.bot.get_context(message)

        await message.channel.send(
            "Batch job received - Processing guild roster. This may take a while..."
        )

        async with message.channel.typing():
            _iter = AsyncIter(message.content.splitlines(), 5, 100)
            async for line in _iter.filter(lambda x: bool(x)):
                user, rank, cls = await self.get_member_and_roles(message.guild, line, fake_ctx)
                if not user:
                    output_not_found += f"{line.split(',', 1)[0]}\n"
                    continue

                to_add = list(
                    filter(
                        lambda x: isinstance(x, discord.Role) and x not in user.roles,
                        [guild_role, rank, cls],
                    )
                )

                log.info(f"{user} has {to_add}")

                if to_add:
                    try:
                        await user.add_roles(*to_add, reason="RoleDetector")

                    except Exception as e:
                        log.exception("AAAAAAAAAAAA", exc_info=e)
                        output_failed += f"{user.display_name}\n"

                    else:
                        roles_added.add(user)
                        role_member.setdefault(rank, []).append(user)
                        output_success += f"{user.display_name} ({cf.humanize_list(to_add)})\n"

            users_to_remove = set(message.guild.members).difference(roles_added)

            bounded_gather(
                *map(lambda x: x.remove_roles(guild_role, reason="RoleDetector"), users_to_remove),
                limit=5,
            )

        output = (
            "Successfully added roles to the following users:\n"
            f"{output_success}\n\n"
            + (
                f"These users were not found so were ignored: \n{output_not_found}\n\n"
                if output_not_found
                else ""
            )
            + (
                f"The following users failed to have their roles added to them due to permissions issues:\n{output_failed}\n\n"
                if output_failed
                else ""
            )
            + f"The remaining users are getting the `@{guild_role.name}` role removed from them."
        )

        self.cache[message.guild.id]["last_output"] = output

        for p in cf.pagify(output):
            await message.channel.send(p)

        embed = discord.Embed(
            title="Roles and Members",
            color=discord.Color.blue(),
        )

        for role, members in role_member.items():
            member_list = "\n".join(map(lambda x: f"{x.display_name}", members))
            for p in cf.pagify(member_list, page_length=1500):
                embed.add_field(name=role.name, value=p)

        await message.channel.send(embed=embed)

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

    @rd.command(name="last", aliases=["lastoutput", "lo"])
    async def rd_lo(self, ctx: commands.Context):
        output = self.cache.get(ctx.guild.id)

        if not output or not output["last_output"]:
            return await ctx.send("There has been no last role detection.")

        return await ctx.send(output)

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

import asyncio
import typing
from datetime import datetime

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list, pagify


class Verifier(commands.Cog):
    """
    Verify other users by mentioning gthem in a set channel."""

    __version__ = "1.0.1"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(self, 563189763, True)
        self.config.register_member(has_verified=[], has_been_verified=False)
        self.config.register_guild(channel=None, role=None)
        self.config.register_global(schema=0)

        self.cache: typing.Dict[int, typing.Dict[str, int]] = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    async def schema_0_to_1(self):
        if await self.config.schema() != 0:
            return

        users = await self.config.all_members()
        for guild_id, user_data in users.items():
            for member_id, data in user_data.items():

                if data["has_been_verified"]:
                    data["has_been_verified"] = (
                        data["has_been_verified"],
                        datetime.now().isoformat(),
                    )
                    await self.config.member_from_ids(guild_id, member_id).has_been_verified.set(
                        data["has_been_verified"]
                    )

                if data["has_verified"]:
                    data["has_verified"] = [
                        (uid, datetime.now().isoformat()) for uid in data["has_verified"]
                    ]
                    await self.config.member_from_ids(guild_id, member_id).has_verified.set(
                        data["has_verified"]
                    )

        await self.config.set_raw("schema", value=1)

    async def build_cache(self):
        await self.schema_0_to_1()
        self.cache = await self.config.all_guilds()

    async def to_config(self):
        for guild_id, data in self.cache.items():
            await self.config.guild_from_id(guild_id).set(data)

    def cog_unload(self):
        asyncio.create_task(self.to_config())

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if message.author.bot:
            return

        if message.guild is None:
            return

        if not (data := self.cache.get(message.guild.id)):
            return

        channel_id = data.get("channel")

        if not channel_id:
            return

        if not message.channel.id == channel_id:
            return

        if not message.mentions:
            await message.delete()
            return

        if not (await self.config.member(message.author).has_been_verified()):
            await message.delete()
            return await message.channel.send(
                "You have not been verified yet so you cannot verify others.", delete_after=25
            )

        if message.author in message.mentions:
            await message.delete()
            return await message.channel.send("You cannot verify yourself.", delete_after=25)

        await message.delete()

        role_id = data.get("role")
        role = message.guild.get_role(role_id)

        failed = []
        verified = []

        for member in message.mentions:
            if member.bot:
                continue
            if await self.config.member(member).has_been_verified():
                failed.append(member)

            else:
                if role:
                    await member.add_roles(role, reason="Verification.")
                await self.config.member(member).has_been_verified.set(
                    (message.author.id, datetime.now().isoformat())
                )
                verified.append(member)

        if not verified:
            return await message.channel.send(
                embed=discord.Embed(
                    description=f"No users were verified by {message.author.mention}.\n"
                    f"{humanize_list([member.mention for member in  failed])} "
                    f"{'was' if len(failed) == 1 else 'were'} already verified.",
                    color=discord.Color.random(),
                )
            )

        async with self.config.member(message.author).has_verified() as has_verified:
            has_verified.extend([(i.id, datetime.now().isoformat()) for i in verified])

        await message.channel.send(
            embed=discord.Embed(
                description=f"The following users were verified by {message.author.mention}:\n"
                + f"{humanize_list([member.mention for member in verified])}"
                + (
                    "Following users were already verified:\n"
                    + f"{humanize_list([member.mention for member in failed])}"
                    if failed
                    else ""
                ),
                color=discord.Color.random(),
            )
        )
        
    @commands.Cog.listener()
    async def on_guild_remove(self, member: discord.Member):
        if not member.guild.id in self.cache:
            return
        
        if not (tup:=await self.config.member(member).has_been_verified()):
            return
        
        user_id = tup[0]
        
        async with self.config.member_from_ids(member.guild.id, user_id).has_verified() as has_verified:
            for (member_id, dt) in has_verified.copy():
                if member_id == user_id:
                    has_verified.remove((member_id, dt))
                    return

    @commands.command(name="verified", aliases=["v"])
    @commands.mod_or_permissions(manage_guild=True)
    async def verified(self, ctx: commands.Context, user: discord.Member):
        """
        Check how many users have been verifeid by the given user.
        """
        await ctx.message.delete()
        has_verified = await self.config.member(user).has_verified()
        if not has_verified:
            return await ctx.maybe_send_embed(f"{user.mention} has not verified anyone.")

        string = "\n".join(
            f"<@{id}> - <t:{int(datetime.fromisoformat(dt).timestamp())}:F>"
            for id, dt in has_verified
        )

        for page in pagify(string, delims=["\n"], page_length=2000):
            embed = discord.Embed(
                description=f"{user.mention} has verified {len(has_verified)} people.\n"
                "They are mentioned below.\n" + page,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)

    @commands.command(name="verifiedby", aliases=["vb"])
    @commands.mod_or_permissions(manage_guild=True)
    async def verifiedby(self, ctx: commands.Context, user: discord.Member = None):
        """
        Check who the given user has been verified by

        If user is omitted, then the author of the command is used.
        """
        await ctx.message.delete()
        user = user or ctx.author
        has_been_verified = await self.config.member(user).has_been_verified()

        if not has_been_verified:
            return await ctx.maybe_send_embed(f"{user.mention} has not been verified by anyone.")

        uid, dt = has_been_verified

        return await ctx.maybe_send_embed(
            f"{user.mention} has been verified by <@{uid}> <t:{int(datetime.fromisoformat(dt).timestamp())}:F>.\n"
        )

    @commands.command(name="verifychannel", aliases=["vc"])
    @commands.admin_or_permissions(administrator=True)
    async def verifychannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """
        Set the channel for verification.

        If channel is omitted, then the current channel is used.
        """
        await ctx.message.delete()
        if not channel:
            channel = ctx.channel

        await self.config.guild(ctx.guild).channel.set(channel.id)
        await self.build_cache()
        return await ctx.maybe_send_embed(f"Verification channel set to {channel.mention}.")

    @commands.command(name="verifyrole", aliases=["vr"])
    @commands.admin_or_permissions(administrator=True)
    async def verifyrole(self, ctx: commands.Context, role: discord.Role):
        """
        Set the role for verification.
        """
        await self.config.guild(ctx.guild).role.set(role.id)
        await self.build_cache()
        return await ctx.maybe_send_embed(f"Verification role set to {role.mention}.")

    @commands.command(name="verifysettings", aliases=["verifyset", "vs"])
    @commands.admin_or_permissions(administrator=True)
    async def verifysettings(self, ctx: commands.Context):
        """
        See your configured settings for verification."""
        await ctx.message.delete()
        data = self.cache.get(ctx.guild.id)

        if not data:
            return await ctx.maybe_send_embed(
                "There are no verification settings for this server."
            )

        channel = f"<#{data['channel']}>" if data["channel"] else "None"
        role = f"<@&{data['role']}>" if data["role"] else "None"

        embed = discord.Embed(
            title=f"Verification Settings for {ctx.guild.name}",
            description=f"Channel: {channel}\n\nRole: {role}",
            color=discord.Color.green(),
        )

        await ctx.maybe_send_embed(embed=embed)

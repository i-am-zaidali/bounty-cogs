from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from typing import Dict, Optional, TypedDict

import discord
import asyncio

from .conv import FuzzyMember, FuzzyRole

class GuildSettings(TypedDict):
    channel: Optional[int]
    role: Optional[int]

class RoleDetector(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = Red
        
        self.config = Config.get_conf(self, 2784481001, force_registration=True)
        self.config.register_guild(channel=None, role=None)
        
        self.cache: Dict[int, GuildSettings] = {}
        
    async def _build_cache(self):
        for guild, data in (await self.config.all_guilds()).items():
            self.cache.update({guild: data})
        
    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if not message.guild:
            return
        
        data = self.cache.get(message.guild.id)
        
        if not data:
            return
        
        if message.channel.id != data['channel']:
            return
        
        guild_role = message.guild.get_role(data["role"])
        
        not_guild_members: list[str] = []
        
        m = list(filter(None, message.content.splitlines()))
        
        member_role = dict(map(lambda x: x.split(";"), m))
        
        fuzzyrole, fuzzymember = FuzzyRole(), FuzzyMember()
        
        partial_ctx = await self.bot.get_context(message)
        
        for mem, role_id in member_role.copy().items():
            try:
                member = await fuzzymember.convert(partial_ctx, mem)
                role = await fuzzyrole.convert(partial_ctx, role_id)
            
            except commands.BadArgument:
                not_guild_members.append(mem)
            
            else:
                member_role[member] = None
                await member.add_roles(*[guild_role, role])

            del member_role[mem]
                            
        asyncio.gather(*map(lambda x: x.remove_roles(guild_role), set(message.guild.members).difference(member_role.keys())))
        
        await message.channel.send(
            (
                "Successfully added roles to the following users:\n"
                f"{cf.humanize_list(member_role)}\n\n"
                + (
                    "These users were not found so were ignored: \n\n"
                    f"{cf.humanize_list(not_guild_members)}" if not_guild_members else ""
                ) + f"The remaining users had the `@{guild_role.name}` role removed from them."
            ), delete_after=10
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
        await ctx.send(cf.success("Channel set to {channel.mention}"))
        await self._build_cache()
        
    @rd.command(name="role", aliases=["r"])
    async def rd_r(self, ctx: commands.Context, role: discord.Role):
        """
        Set the role to assign to users."""
        await self.config.guild(ctx.guild).role.set(role.id)
        await ctx.send(cf.success("Role set to {role.mention}"))
        await self._build_cache()
        
    @rd.command(name="show", aliases=["ss", "showsettings"])
    async def rd_ss(self, ctx: commands.Context):
        """
        See the settings for roledetector in your server."""
        data = self.cache.get(ctx.guild.id)
        if not data:
            return await ctx.send("RoleDetector is not setup in your server.")
        
        embed = discord.Embed(title=f"RoleDetector settings in __**{ctx.guild.name}**__")
        
        embed.description = (
            f"Channel: <#{data['channel']}>\n\n"
            f"Role: <@&{data['role']}>"
        )
        
        return await ctx.send(embed=embed)
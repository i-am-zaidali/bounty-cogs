import typing
from logging import getLogger

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

humanize_bool = lambda b: "enabled" if b else "disabled"

log = getLogger("red.bounty-cogs.banonleave")


class BanOnLeave(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, 1234567890, force_registration=True)
        self.config.register_guild(ban_on_leave=False, log=None)

    @commands.group(aliases=["bol"])
    async def banonleave(self, ctx: commands.Context):
        """Ban On Leave"""
        return await ctx.send_help()

    @banonleave.command(name="toggle")
    @commands.mod_or_permissions(ban_members=True)
    async def banonleave_toggle(self, ctx: commands.Context):
        """Toggle ban on leave"""
        guild = ctx.guild
        current = await self.config.guild(guild).ban_on_leave()
        await self.config.guild(guild).ban_on_leave.set(not current)
        await ctx.send(f"Ban on leave is now {humanize_bool(not current)}")

    @banonleave.command(name="log")
    @commands.mod_or_permissions(manage_guild=True)
    async def banonleave_log(
        self, ctx: commands.Context, channel: typing.Optional[discord.TextChannel]
    ):
        """Set the log channel where ban on leave messages will be sent"""
        guild = ctx.guild
        await self.config.guild(guild).log.set(getattr(channel, "id", None))
        await ctx.send(f"Log channel is now {getattr(channel, 'mention', 'removed')}")

    @banonleave.command(name="showsettings", aliases=["show", "ss"])
    @commands.mod_or_permissions(manage_guild=True)
    async def banonleave_info(self, ctx: commands.Context):
        """Show current settings"""
        guild = ctx.guild
        current = await self.config.guild(guild).ban_on_leave()
        log = await self.config.guild(guild).log()
        log = f"<#{log}>" if log else "not set"
        await ctx.send(f"Ban on leave is {humanize_bool(current)}\nLog channel is {log}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        ban_on_leave = await self.config.guild(guild).ban_on_leave()
        if ban_on_leave:
            try:
                await guild.fetch_ban(member)
            except discord.NotFound:
                if not guild.me.guild_permissions.ban_members:
                    log.error(
                        "Missing permissions to ban members. Unable to ban %s for leaving the guild %s",
                        member,
                        guild,
                    )
                    return
                await guild.ban(member, reason="Ban on leave", delete_message_days=0)
                # send an embed to log channel
                log_channel_id = await self.config.guild(guild).log()
                if log_channel_id:
                    log_channel = guild.get_channel(log_channel_id)
                    if log_channel:
                        embed = discord.Embed(
                            title="Ban on Leave",
                            description=f"{member.mention} was banned because they left the server.",
                            color=discord.Color.red(),
                        )
                        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                        embed.set_footer(text=f"User ID: {member.id}")
                        await log_channel.send(embed=embed)

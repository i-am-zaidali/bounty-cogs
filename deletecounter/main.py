import datetime
from redbot.core.bot import Red
from redbot.core import commands, Config, modlog
from redbot.core.utils import chat_formatting as cf
import discord
from collections import deque
from logging import getLogger
from tabulate import tabulate

log = getLogger("red.bounty.deletecounter")


class DeleteCounter(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=1234567890, force_registration=True
        )
        default_guild = {
            "mute_duration": 15,
            "duration": 300,
            "threshold": 5,
            "exempt_roles": [],
            "leaderboard": {},
        }

        self.config.register_guild(**default_guild)

        self.guild_cache: dict[int, dict[int, deque[discord.Message]]] = {}

    @commands.group(name="deletecounter", aliases=["delc"], invoke_without_command=True)
    async def dc(self, ctx: commands.Context):
        """Manage the delete counter settings."""
        return await ctx.send_help()

    @dc.command(name="duration")
    async def dc_duration(self, ctx: commands.Context, duration: datetime.timedelta = commands.param(converter=commands.get_timedelta_converter(allowed_units=["seconds", "minutes"]))):  # type: ignore
        """Set the duration in seconds for the delete counter."""
        await self.config.guild(ctx.guild).duration.set(duration.total_seconds())
        await ctx.send(
            f"The duration has been set to {cf.humanize_timedelta(timedelta=duration)}."
        )

    @dc.command(name="threshold")
    async def dc_threshold(self, ctx: commands.Context, threshold: int):
        """Set the threshold for the delete counter."""
        await self.config.guild(ctx.guild).threshold.set(threshold)
        await ctx.send(f"The threshold has been set to {threshold}.")

    @dc.command(name="muteduration")
    async def dc_mute_duration(
        self,
        ctx: commands.Context,
        duration: datetime.timedelta = commands.param(
            converter=commands.get_timedelta_converter(
                allowed_units=["seconds", "minutes", "hours"]
            )
        ),
    ):
        """Set the duration in seconds for the mute."""
        await self.config.guild(ctx.guild).mute_duration.set(duration.total_seconds())
        await ctx.send(
            f"The mute duration has been set to {cf.humanize_timedelta(timedelta=duration)}."
        )

    @dc.group(name="exemptroles")
    async def dc_exempt_roles(self, ctx: commands.Context):
        """Manage the exempt roles for the delete counter."""
        pass

    @dc_exempt_roles.command(name="add")
    async def dc_exempt_roles_add(self, ctx: commands.Context, *roles: discord.Role):
        """Add a role to the exempt roles list."""
        if not roles:
            return await ctx.send_help()
        role_ids = [r.id for r in roles]
        async with self.config.guild(ctx.guild).exempt_roles() as exempt_roles:
            exempt_roles.extend(set(exempt_roles) | set(role_ids))
            await ctx.send(
                f"{cf.humanize_list(set(exempt_roles) | set(role_ids))} have been added to the exempt roles list."
            )

    @dc_exempt_roles.command(name="remove")
    async def dc_exempt_roles_remove(self, ctx: commands.Context, *roles: discord.Role):
        """Remove a role from the exempt roles list."""
        if not roles:
            return await ctx.send_help()

        role_ids = [r.id for r in roles]

        async with self.config.guild(ctx.guild).exempt_roles() as exempt_roles:
            er = set(exempt_roles) - set(role_ids)
            exempt_roles.clear()
            exempt_roles.extend(er)
            await ctx.send(
                f"{cf.humanize_list(roles)} have been removed from the exempt roles list."
            )

    @dc.command(name="leaderboard")
    async def dc_lb(self, ctx: commands.Context):
        lb = await self.config.guild(ctx.guild).leaderboard()
        if not lb:
            return await ctx.send("The leaderboard is empty.")

        # sort by both messages_deleted and mutes
        sorted_lb = list(
            map(
                lambda x: (ctx.guild.get_member(int(x[0])).name, *x[1].values()),
                sorted(
                    filter(lambda x: ctx.guild.get_member(int(x[0])), lb.items()),
                    key=lambda x: (x[1]["messages_deleted"], x[1]["mutes"]),
                    reverse=True,
                ),
            )
        )
        tabbed = tabulate(
            sorted_lb,
            headers=["User", "Messages Deleted", "Mutes"],
            tablefmt="rounded_outline",
            maxcolwidths=[15, None, None],
            maxheadercolwidths=[None, 8, None],
        )

        await ctx.send(f"```\n{tabbed}```")

    @dc.command(name="showsettings", aliases=["settings"])
    async def dc_show_settings(self, ctx: commands.Context):
        """Show the current delete counter settings."""
        cdata = await self.config.guild(ctx.guild).all()
        exempt_roles = [
            ctx.guild.get_role(r).name for r in cdata.get("exempt_roles", [])
        ]
        embed = discord.Embed(
            title="Delete Counter Settings", color=await ctx.embed_color()
        )
        embed.add_field(
            name="Duration",
            value=cf.humanize_timedelta(seconds=cdata.get("duration")),
            inline=False,
        )
        embed.add_field(name="Threshold", value=cdata.get("threshold"), inline=False)
        embed.add_field(
            name="Mute Duration",
            value=cf.humanize_timedelta(seconds=cdata.get("mute_duration")),
            inline=False,
        )
        embed.add_field(
            name="Exempt Roles",
            value=cf.humanize_list(exempt_roles) or "None set",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot:
            return
        guild = message.guild
        if guild is None:
            return

        cdata = await self.config.guild(guild).all()

        if any(
            message.author.get_role(r) for r in cdata.get("exempt_roles", [])
        ):  # or await self.bot.is_mod(message.author):
            return

        threshold = cdata.get("threshold")
        gdata = self.guild_cache.setdefault(guild.id, {})
        udata = gdata.setdefault(message.author.id, deque(maxlen=threshold))
        udata.append(message)
        duration = cdata.setdefault("duration")
        leaderboard = cdata.setdefault("leaderboard", {}).setdefault(
            str(message.author.id), {"messages_deleted": 0, "mutes": 0}
        )
        leaderboard["messages_deleted"] += 1
        if len(udata) == threshold and self.within_range(udata, duration):
            udata.clear()
            until = discord.utils.utcnow() + datetime.timedelta(
                seconds=cdata.get("mute_duration")
            )
            reason = f"Muted for {cf.humanize_timedelta(seconds=cdata.get('mute_duration'))} for deleting {cdata.get('threshold',0):,} messages in a {cf.humanize_timedelta(seconds=duration)} span."
            try:
                await message.author.timeout(until, reason=reason)
                leaderboard["mutes"] += 1
            except Exception:
                log.exception("Error while timing out user", exc_info=True)
                return

            await modlog.create_case(
                self.bot,
                guild,
                message.created_at,
                "smute",
                message.author,
                guild.me,
                reason,
                until=until,
                channel=message.channel,
            )

        await self.config.guild(guild).leaderboard.set_raw(
            str(message.author.id), value=leaderboard
        )

    def within_range(self, messages: deque[discord.Message], duration: int):
        return (
            messages[-1].created_at - messages[0].created_at
        ).total_seconds() <= duration

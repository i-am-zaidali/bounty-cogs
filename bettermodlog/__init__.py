from datetime import datetime, timezone
from typing import List, Optional, TypeVar, Union

import discord
from redbot.cogs.modlog import ModLog
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.modlog import Case, get_cases_for_member, get_casetype
from redbot.core.utils import chat_formatting as cf
from redbot.core.utils.menus import menu

_T = TypeVar("_T")


def chunks(l: List[_T], n: int):
    for i in range(0, len(l), n):
        yield l[i : i + n]


class BetterModlog(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self._command = self.bot.remove_command("listcases")

    async def cog_unload(self) -> None:
        if self._command:
            await self.bot.add_command(self._command, "listcases")

    @commands.command()
    @commands.guild_only()
    async def listcases(
        self,
        ctx: commands.Context,
        per_embed: Optional[commands.Range[int, 1, 19]] = 6,
        *,
        member: Union[discord.Member, int],
    ):
        """List cases for the specified member."""
        async with ctx.typing():
            try:
                if isinstance(member, int):
                    cases = await get_cases_for_member(
                        bot=ctx.bot, guild=ctx.guild, member_id=member
                    )
                else:
                    cases = await get_cases_for_member(bot=ctx.bot, guild=ctx.guild, member=member)
            except discord.NotFound:
                return await ctx.send("That user does not exist.")
            except discord.HTTPException:
                return await ctx.send(
                    "Something unexpected went wrong while fetching that user by ID."
                )
            if not cases:
                return await ctx.send("That user does not have any cases.")

            rendered_cases = []
            for page, ccases in enumerate(chunks(cases, per_embed), 1):
                embed = discord.Embed(
                    title=f"Cases for `{getattr(member, 'display_name', member)}` (Page {page} / {len(cases) // per_embed + 1})",
                )
                for case in ccases:
                    if case.moderator is None:
                        moderator = "Unknown"
                    elif isinstance(case.moderator, int):
                        # can't use _() inside f-string expressions, see bpo-36310 and red#3818
                        if case.moderator == 0xDE1:
                            moderator = "Deleted User."
                        else:
                            translated = "Unknown or Deleted User"
                            moderator = f"[{translated}] ({case.moderator})"
                    else:
                        moderator = f"{case.moderator} ({case.moderator.id})"

                    length = ""
                    if case.until:
                        start = datetime.fromtimestamp(case.created_at, tz=timezone.utc)
                        end = datetime.fromtimestamp(case.until, tz=timezone.utc)
                        end_fmt = discord.utils.format_dt(end)
                        duration = end - start
                        dur_fmt = cf.humanize_timedelta(timedelta=duration)
                        until = f"Until: {end_fmt}\n"
                        duration = f"Length: {dur_fmt}\n"
                        length = until + duration

                    created_at = datetime.fromtimestamp(case.created_at, tz=timezone.utc)
                    embed.add_field(
                        name=f"Case #{case.case_number} | {(await get_casetype(case.action_type, getattr(member, 'guild', ctx.guild))).case_str}",
                        value=f"{cf.bold('Moderator:')} {moderator}\n"
                        f"{cf.bold('Reason:')} {case.reason}\n"
                        f"{length}"
                        f"{cf.bold('Timestamp:')} {discord.utils.format_dt(created_at)}\n\n",
                        inline=False,
                    )
                rendered_cases.append(embed)

        await menu(ctx, rendered_cases)


org_listcases = None


async def setup(bot: Red):
    modlog = bot.get_cog("ModLog")
    if not modlog:
        raise RuntimeError("ModLog cog must be loaded to use this cog.")
    await bot.add_cog(BetterModlog(bot))

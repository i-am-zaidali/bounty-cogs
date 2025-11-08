import datetime
import typing

import discord
from redbot.vendored.discord.ext.menus import ListPageSource

from ...common.models import Violation
from ..paginator import Paginator


class ViolationsSource(ListPageSource):
    def __init__(
        self,
        violations: dict[str, Violation],
        violator: typing.Union[discord.User, discord.Member],
        guild: discord.Guild,
    ):
        super().__init__([*violations.values()], per_page=3)
        self.all_violations = violations
        self.violator = violator
        self.guild = guild

    async def format_page(self, menu: Paginator, violations: list[Violation]):
        embed = discord.Embed(
            title=f"Violations of {self.violator.display_name}",
            timestamp=discord.utils.utcnow(),
        )

        if not violations:
            embed.description = f"{self.violator.display_name} has been a good member of society. No violations by them!"
            return embed

        embed.description = f"Total Violations: {len(self.all_violations)}"

        for violation in violations:
            dt = datetime.datetime.fromtimestamp(violation.timestamp)
            expiration_td = datetime.timedelta(
                seconds=menu.ctx.cog.db.get_conf(
                    self.guild.id
                ).violation_expiration_seconds
            )

            embed.add_field(
                name=f"Violation {violation.id}",
                value=f"*__Channel__*: <#{violation.channel}>\n"
                f"*__Time__*: {discord.utils.format_dt(dt)}\n"
                + (
                    f"*__Expires at__*: {discord.utils.format_dt(dt + expiration_td)}\n"
                    if expiration_td.total_seconds() > 0
                    else "*__Expires__*: Never\n"
                )
                + (
                    f"*__Log Message__*: [Jump to log message]({violation.log_message_url})\n"
                    if violation.log_message_url
                    else ""
                )
                + (
                    f"*__Jump URL__*: https://discord.com/channels/{self.violator.guild.id}/{violation.channel}/{violation.message}\n"
                    if violation.message
                    else ""
                )
                + f"*__Violation Type__*: {violation.violation_type.upper()}\n"
                + (
                    f"*__Action taken__*: {violation.action_taken}\n"
                    if violation.action_taken
                    else ""
                ),
                inline=False,
            )

        embed.set_footer(text=f"Page {menu.current_page + 1} / {self.get_max_pages()}")

        return embed

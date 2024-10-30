import collections
import itertools
import typing

import discord
from redbot.core.utils import chat_formatting as cf
from redbot.vendored.discord.ext import menus
from tabulate import tabulate

from . import Paginator

if typing.TYPE_CHECKING:
    from ..common.models import MemberData

__all__ = ["TotalStatsSource", "UserStatsSource", "RegisteredUsersSource"]

GroupByEntry = collections.namedtuple("GroupByEntry", ["key", "items"])


class TotalStatsSource(menus.GroupByPageSource):
    def __init__(self, items: list[tuple[str, int]], vehicles: list[str]):
        super().__init__(
            items, key=lambda x: x[0] in vehicles, per_page=20, sort=False
        )

    async def format_page(self, menu: Paginator, entry: GroupByEntry):
        embed = discord.Embed(
            title="Total Stats",
            description=cf.box(
                tabulate(
                    entry[1],
                    headers=[
                        "Vehicle" if entry.key is True else "Category",
                        "Amount",
                    ],
                    tablefmt="fancy_grid",
                    colalign=("left", "center"),
                )
            ),
        ).set_footer(
            text=f"Page {menu.current_page + 1}/{self.get_max_pages()}"
        )
        return embed


class UserStatsSource(menus.ListPageSource):
    def __init__(
        self,
        all_users: list[tuple[discord.Member | None, dict[str, int]]],
        user_or_role: discord.Member | discord.Role,
        vehicles: list[str],
        categories: dict[str, list[str]],
    ):
        self.all_users = all_users
        self.user_or_role = user_or_role
        self.categories = categories
        self.vehicles = vehicles
        super().__init__(all_users, per_page=1)

    async def format_page(
        self,
        menu: Paginator,
        entry: tuple[discord.Member | None, dict[str, int]],
    ):
        user_or_role = self.user_or_role
        vehicles = self.vehicles
        categories = self.categories
        categoried_vehicles = [
            *itertools.chain.from_iterable(categories.values())
        ]
        all_users = self.all_users

        if not entry[1]:
            return discord.Embed(
                title=(
                    f"{entry[0]}'s stats"
                    if entry[0]
                    else (
                        f"Combined stats of all members of **{user_or_role.name}**"
                        if isinstance(user_or_role, discord.Role)
                        else "Combined stats of all users"
                    )
                ),
                description="No stats available",
            )
        category_totals = {
            category: sum(entry[1].get(vehicle, 0) for vehicle in cat_vc)
            for category, cat_vc in categories.items()
        }
        category_individuals = {
            category: dict(
                sorted(
                    {
                        vehicle: entry[1].get(vehicle, 0)
                        for vehicle in cat_vc
                        if entry[1].get(vehicle, 0) > 0
                    }.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
            )
            for category, cat_vc in categories.items()
        }
        category_individuals.update(
            {
                "uncategorised": dict(
                    sorted(
                        {
                            vehicle: entry[1].get(vehicle, 0)
                            for vehicle in vehicles
                            if vehicle not in categoried_vehicles
                            and entry[1].get(vehicle, 0) > 0
                        }.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    ),
                )
            }
        )
        category_totals.update(
            {
                "uncategorised": sum(
                    category_individuals["uncategorised"].values()
                )
            }
        )

        description = (
            cf.box(
                tabulate(
                    ci.items(),
                    headers=["Vehicle", "Amount"],
                    tablefmt="simple",
                    colalign=("left", "center"),
                )
            )
            if (ci := category_individuals.pop("uncategorised"))
            else "No stats available for this category."
        )

        not_available = [user[0].mention for user in all_users if not user[1]]
        desc = (
            f"{cf.humanize_list(not_available)} {'have' if len(not_available) > 1 else 'has'} no stats available.\n\n"
            if not entry[0] and not_available
            else ""
        )

        embed = discord.Embed(
            title=(
                f"{entry[0]}'s stats"
                if entry[0]
                else (
                    f"Combined stats of all members of **{user_or_role.name}**"
                    if isinstance(user_or_role, discord.Role)
                    else "Combined stats of all users"
                )
            ),
            description=f"{desc}**Uncategorised**\nTotal: {category_totals.pop('uncategorised')}\n{description}",
        )
        for cat, s in category_totals.items():
            embed.add_field(
                name=f"**{cat}**\nTotal: {s}",
                value=(
                    cf.box(
                        tabulate(
                            category_individuals[cat].items(),
                            headers=["Vehicle", "Amount"],
                            tablefmt="simple",
                            colalign=("left", "center"),
                        )
                    )
                    if category_individuals[cat]
                    else "No stats available for this category."
                ),
                inline=False,
            )

        return embed


class RegisteredUsersSource(menus.ListPageSource):
    entries: list[tuple[typing.Union[int, discord.Member], "MemberData"]]

    async def format_page(
        self,
        menu: Paginator,
        entries: list[tuple[typing.Union[int, discord.Member], "MemberData"]],
    ):
        embed = discord.Embed(
            title="Registered Users",
            description=cf.box(
                tabulate(
                    [
                        (
                            f"{member.display_name if isinstance(member, int) else f'User Not found\n{member}'}",
                            f"{data.username}",
                            data.registration_date.strftime("%d-%m-%Y")
                            if data.registration_date
                            # should never happen since filtering is done before creating the Source object but just in case
                            else "Not Registered",
                        )
                        for member, data in entries
                    ],
                    headers=["Server Member", "Username", "Registration Date"],
                    tablefmt="fancy_grid",
                    showindex=range(
                        (start := (menu.current_page * menu.per_page) + 1),
                        start + len(entries) + 1,
                    ),
                    colalign=("left", "center"),
                )
            ),
        ).set_footer(
            text=f"Page {menu.current_page + 1}/{self.get_max_pages()}"
        )
        return embed

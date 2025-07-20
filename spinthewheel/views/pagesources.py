import datetime
import operator
import random
import typing

import discord
import emoji
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from redbot.vendored.discord.ext import menus
from tabulate import tabulate

from . import Paginator

__all__ = [
    "WheelSource",
]


class WheelSource(menus.ListPageSource):
    def __init__(self, wheels: dict[str, dict[str, int]], rarity: dict[int, str]):
        self.rarity = rarity
        super().__init__(list(wheels.items()), per_page=1)

        self.custom_indices = [
            {"label": f"{wheel} wheel", "description": f"See the items for {wheel}"}
            for wheel in wheels
        ]

    async def format_page(
        self, menu: menus.MenuPages, entry: tuple[str, dict[str, int]]
    ):
        embed = discord.Embed(title="Wheel List", description=f"Wheel: {entry[0]}\n\n")
        embed.description += cf.box(
            tabulate(
                [
                    (k, self.rarity.get(v, v))
                    for k, v in sorted(
                        entry[1].items(), key=operator.itemgetter(1), reverse=True
                    )
                ],
                headers=["Prize", "Rarity"],
                tablefmt="rounded_grid",
            )
            if entry[1]
            else "No items found"
        )
        return embed

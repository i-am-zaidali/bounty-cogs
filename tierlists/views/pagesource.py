from redbot.vendored.discord.ext import menus
from typing import List

from ..common.models import Category


class CategoryPageSource(menus.ListPageSource):
    def __init__(self, categories: List[Category], percentiles: dict[str, int]):
        self.percentiles = percentiles
        super().__init__(categories, per_page=1)

    async def format_page(self, menu, entry: Category):
        return entry.get_voting_embed(self.percentiles)

import functools
import itertools

import discord
from redbot.core.bot import Red

from ..common.models import GuildSettings
from ..common.utils import chunks
from .viewdisableontimeout import ViewDisableOnTimeout

__all__ = ["CategoryEditor", "SaveOrBackView"]


class CategoryEditor(ViewDisableOnTimeout):
    def __init__(self, conf: GuildSettings, category_name: str):
        self.conf = conf
        self.category = category_name

        super().__init__(timeout=60)

        self.remaining = set(self.conf.vehicles).difference(
            itertools.chain.from_iterable(self.conf.vehicle_categories.values())
        )
        self.selected = set(
            self.conf.vehicle_categories.setdefault(category_name, [])
        )

        self.generate_selects()

    def generate_selects(self, inter: discord.Interaction[Red] | None = None):
        self.clear_items()
        for ind, chunk in enumerate(chunks(self.remaining, 25)):
            select = discord.ui.Select(
                placeholder="Select vehicles to add to the category",
                custom_id=f"_add_vehicles_{ind}",
                options=[
                    discord.SelectOption(label=vehicle, value=vehicle)
                    for vehicle in chunk
                ],
            )
            select.callback = functools.partial(self.select_cb, select)
            self.add_item(select)

        for ind, chunk in enumerate(chunks(self.selected, 25)):
            select = discord.ui.Select(
                placeholder="Select vehicles to remove from the category",
                custom_id=f"_remove_vehicles_{ind}",
                options=[
                    discord.SelectOption(label=vehicle, value=vehicle)
                    for vehicle in chunk
                ],
            )
            select.callback = functools.partial(self.select_cb, select)
            self.add_item(select)

        if inter:
            return inter.response.edit_message(view=self)

    async def select_cb(
        self, select: discord.ui.Select, inter: discord.Interaction[Red]
    ):
        if "add" in select.custom_id:
            self.selected.update(select.values)
            self.remaining.difference_update(select.values)

        else:
            self.selected.difference_update(select.values)
            self.remaining.update(select.values)
        await self.generate_selects(inter)


class SaveOrBackView(ViewDisableOnTimeout):
    def __init__(self, parent: CategoryEditor):
        self.parent = parent
        super().__init__(timeout=60)

    @discord.ui.button(
        label="Save Changes",
        custom_id="_save_changes",
        style=discord.ButtonStyle.green,
    )
    async def save_callback(
        self, inter: discord.Interaction, button: discord.ui.Button
    ):
        await inter.response.edit_message(content="Saving changes...")
        async with self.parent.conf as conf:
            conf.vehicle_categories[self.parent.category] = list(
                self.parent.selected
            )

        await inter.message.edit(content="Changes saved.", delete_after=10)

import itertools

import discord
from redbot.core.bot import Red

from mcm.views.utilviews import SelectView

from ..common.models import GuildSettings
from .paginator import CloseButton
from .viewdisableontimeout import ViewDisableOnTimeout

__all__ = ["NewCategory"]


class NewCategory(ViewDisableOnTimeout):
    def __init__(self, conf: GuildSettings):
        self.conf = conf

        super().__init__(timeout=60)

        self.add_item(CloseButton())

    @discord.ui.button(
        label="Add Category",
        custom_id="_add_category",
        style=discord.ButtonStyle.green,
    )
    async def ac_callback(
        self, inter: discord.Interaction, button: discord.ui.Button
    ):
        modal = CategoryNameModal(
            categories=self.conf.vehicle_categories,
            title="Enter the category name:",
            timeout=60,
        )
        await inter.response.send_modal(modal)
        if await modal.wait():
            message = await inter.followup.send("Cancelled.", wait=True)
            return await message.delete(delay=10)

        options = [
            discord.SelectOption(label=option, value=option)
            for option in set(self.conf.vehicles).difference(
                itertools.chain.from_iterable(
                    self.conf.vehicle_categories.values()
                )
            )
        ]

        selview = SelectView(
            "Select vehicles to add to the category", options=options
        )

        await inter.response.edit_message(view=selview)

        selview.message = inter.message

        if await selview.wait():
            return await inter.followup.send(
                "You took too long to respond. Operation Cancelled",
                wait=True,
                ephemeral=True,
            )

        async with self.conf:
            self.conf.vehicle_categories[modal.name.value] = [
                o.value for o in selview.selected
            ]


class CategoryNameModal(discord.ui.Modal):
    name = discord.ui.TextInput(
        label="Category Name",
        custom_id="_category_name",
        placeholder="Category Name",
    )

    def __init__(self, categories: list[str] = None, **kwargs):
        self.categories = categories or []
        super().__init__(**kwargs)

    async def on_submit(self, interaction: discord.Interaction[Red]) -> None:
        if not self.name.value.strip():
            await interaction.response.send_message(
                "You need to enter a category name."
            )
            return

        all_categories = self.categories
        if self.name.value.strip().lower() in all_categories:
            return await interaction.response.send_message(
                "That category already exists.", ephemeral=True
            )
        await interaction.response.defer()
        self.stop()
        # await self.further_handling(
        #     interaction, self.name.value.strip().lower()
        # )

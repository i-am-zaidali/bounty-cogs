import functools
import typing

import discord

from ..common.utils import chunks
from .viewdisableontimeout import ViewDisableOnTimeout, disable_items

if typing.TYPE_CHECKING:
    from redbot.core.bot import Red


class SelectView(ViewDisableOnTimeout):
    def __init__(
        self,
        select_placeholder: str,
        options: list[discord.SelectOption],
        deselect_placeholder: str = "Select items to deselect",
    ):
        super().__init__(timeout=300)
        self.options = set(options)
        self.selected = set[discord.SelectOption]()

    def generate_selects(self, inter: discord.Interaction["Red"] | None = None):
        self.clear_items()
        for ind, chunk in enumerate(chunks(self.options, 25)):
            select = discord.ui.Select(
                placeholder="Select vehicles to add to the category",
                custom_id=f"select_{ind}",
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
                custom_id=f"deselect_{ind}",
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
        self, select: discord.ui.Select, inter: discord.Interaction["Red"]
    ):
        if select.custom_id.startswith("select"):
            self.selected.update(select.values)
            self.options.difference_update(select.values)

        else:
            self.selected.difference_update(select.values)
            self.options.update(select.values)
        await self.generate_selects(inter)

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.primary, row=4)
    async def submit(
        self, interaction: discord.Interaction["Red"], button: discord.ui.Button
    ):
        disable_items(self)
        await interaction.response.edit_message(view=self)
        await self.stop()


class AskOneQuestion(discord.ui.Modal):
    """Literally just ask one question in a modal"""

    answer: str

    def __init__(
        self,
        question: str,
        *,
        title: str,
        timeout=None,
    ):
        super().__init__(title=title, timeout=timeout)
        self.question = question
        self.question_input = discord.ui.TextInput(
            label=question, required=True
        )
        self.add_item(self.question_input)

    async def on_submit(self, interaction: discord.Interaction["Red"]):
        self.answer = self.question_input.value
        await interaction.response.defer()
        self.stop()

import functools
import typing
from operator import attrgetter

import discord

from ..common.utils import chunks
from .viewdisableontimeout import ViewDisableOnTimeout, disable_items

if typing.TYPE_CHECKING:
    from redbot.core.bot import Red


class NumberedButtonsView(ViewDisableOnTimeout):
    def __init__(
        self,
        rng: range,
        allowed_to_interact: list[int] = [],
    ):
        super().__init__(timeout=300, allowed_to_interact=allowed_to_interact)
        self.rng = rng
        if len(rng) > 25:
            raise ValueError("Range must be less than 25")
        self.generate_buttons()

        self.result: int

    def generate_buttons(self):
        self.clear_items()
        for i in self.rng:
            button = discord.ui.Button(style=discord.ButtonStyle.primary, label=str(i))
            button.callback = functools.partial(self.num_callback, button)
            self.add_item(button)

    async def num_callback(
        self, button: discord.ui.Button, inter: discord.Interaction["Red"]
    ):
        self.result = int(button.label)
        await inter.response.defer()
        await inter.delete_original_response()
        self.stop()


class SelectView(ViewDisableOnTimeout):
    def __init__(
        self,
        select_placeholder: str,
        options: list[discord.SelectOption],
        deselect_placeholder: str = "Select items to deselect",
        *,
        max_selected: typing.Optional[int] = None,
        allowed_to_interact: list[int] = [],
    ):
        super().__init__(timeout=300, allowed_to_interact=allowed_to_interact)
        self.select_placeholder = select_placeholder
        self.deselect_placeholder = deselect_placeholder
        self.options = set(options)
        self.option_values = {option.value: option for option in options}
        self.selected = set[discord.SelectOption]()
        if max_selected is not None and max_selected < 1:
            raise ValueError("max_selected must be greater than 0")
        self.max_selected = max_selected
        self.generate_selects()

    def generate_selects(self, inter: discord.Interaction["Red"] | None = None):
        self.clear_items()
        for ind, chunk in enumerate(
            chunks(sorted(self.options, key=attrgetter("label")), 25)
        ):
            max_selected = (
                self.max_selected is not None
                and len(self.selected) >= self.max_selected
            )
            select = discord.ui.Select(
                placeholder=("(Disabled: Max selected) " if max_selected else "")
                + self.select_placeholder,
                custom_id=f"select_{ind}",
                options=chunk,
                disabled=max_selected,
            )
            select.callback = functools.partial(self.select_cb, select)
            self.add_item(select)

        for ind, chunk in enumerate(chunks(self.selected, 25)):
            select = discord.ui.Select(
                placeholder=self.deselect_placeholder,
                custom_id=f"deselect_{ind}",
                options=chunk,
            )
            select.callback = functools.partial(self.select_cb, select)
            self.add_item(select)

        self.add_item(self.submit)
        self.submit.disabled = not self.selected

        if inter:
            return inter.response.edit_message(view=self)

    async def select_cb(
        self, select: discord.ui.Select, inter: discord.Interaction["Red"]
    ):
        selected_options = [self.option_values[value] for value in select.values]
        if select.custom_id.startswith("select"):
            self.selected.update(selected_options)
            self.options.difference_update(selected_options)

        else:
            self.selected.difference_update(selected_options)
            self.options.update(selected_options)
        await self.generate_selects(inter)

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.primary, row=4)
    async def submit(
        self, interaction: discord.Interaction["Red"], button: discord.ui.Button
    ):
        disable_items(self)
        await interaction.response.defer()
        await interaction.delete_original_response()
        self.stop()


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
        self.question_input = discord.ui.TextInput(label=question, required=True)
        self.add_item(self.question_input)

    async def on_submit(self, interaction: discord.Interaction["Red"]):
        self.answer = self.question_input.value
        await interaction.response.defer()
        self.stop()

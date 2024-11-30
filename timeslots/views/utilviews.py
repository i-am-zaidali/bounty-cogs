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
        allowed_to_interact: list[int],
        select_placeholder: str,
        options: list[discord.SelectOption],
        preselected: list[str] = [],
        deselect_placeholder: str = "Select items to deselect",
        min_select: int = 1,
        max_select: typing.Optional[int] = None,
        chain_view: discord.ui.View | None = None,
        allow_empty_submit: bool = False,
    ):
        super().__init__(timeout=300, allowed_to_interact=allowed_to_interact)
        self.select_placeholder = select_placeholder
        self.deselect_placeholder = deselect_placeholder
        self.all_options = options.copy()
        print(self.all_options)
        self.selected = set[str](preselected)
        self.select_options = list(
            filter(lambda x: x.value not in self.selected, options.copy())
        )
        self.min_select = min_select or 1
        self.max_select = max_select or len(options) if len(options) < 25 else 25
        self.chain_view = chain_view
        "The view that this view will switch to once it receives a submit interaction."
        self.allow_empty_submit = allow_empty_submit
        self.generate_selects()
        if max_select == 1:
            self.remove_item(self.submit)

    def generate_selects(self):
        self.clear_items()
        self.add_item(self.submit)
        for ind, chunk in enumerate(chunks(self.select_options, 25)):
            select = discord.ui.Select(
                placeholder=self.select_placeholder,
                custom_id=f"select_{ind}",
                options=list(chunk),
                min_values=self.min_select,
                max_values=min(self.max_select, len(chunk)),
            )
            select.callback = functools.partial(self.select_cb, select)
            self.add_item(select)

        for ind, chunk in enumerate(chunks(self.selected, 25)):
            select = discord.ui.Select(
                placeholder=self.deselect_placeholder,
                custom_id=f"deselect_{ind}",
                options=[
                    option for option in self.all_options if option.value in chunk
                ],
                min_values=1,
                max_values=len(chunk),
            )
            select.callback = functools.partial(self.select_cb, select)
            self.add_item(select)

        if not self.selected and not self.allow_empty_submit:
            self.submit.disabled = True

        else:
            self.submit.disabled = False

    async def select_cb(
        self, select: discord.ui.Select, inter: discord.Interaction["Red"]
    ):
        if select.custom_id.startswith("select"):
            self.selected.update(select.values)

        else:
            self.selected.difference_update(select.values)
        self.select_options = [
            option for option in self.all_options if option.value not in self.selected
        ]

        if self.max_select == 1:
            self.add_item(self.submit)
            return await self.submit.callback(inter)
        self.generate_selects()
        await inter.response.edit_message(view=self)

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.primary, row=4)
    async def submit(
        self, interaction: discord.Interaction["Red"], button: discord.ui.Button
    ):
        self.final_interaction = interaction
        if self.chain_view:
            await interaction.response.edit_message(view=self.chain_view)
        else:
            disable_items(self)
            await interaction.response.edit_message(view=self)
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

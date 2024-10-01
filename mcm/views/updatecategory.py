import discord

from ..common.models import GuildSettings
from .categoryeditor import CategoryEditor, SaveOrBackView
from .paginator import CloseButton
from .viewdisableontimeout import ViewDisableOnTimeout

__all__ = ["UpdateCategory"]


class UpdateCategory(ViewDisableOnTimeout):
    def __init__(self, conf: GuildSettings):
        self.conf = conf

        super().__init__(timeout=60)

        self.add_item(CloseButton())
        self.category_select.options = [*self.conf.vehicle_categories]

    @discord.ui.select(
        placeholder="Select a category to update",
        custom_id="_update_category",
        options=[],
        max_values=1,
        min_values=1,
    )
    async def category_select(
        self, inter: discord.Interaction, select: discord.ui.Select
    ):
        category = select.values[0]
        editor = CategoryEditor(self.conf, category)
        await inter.response.edit_message(view=editor)
        save = SaveOrBackView(editor)
        await inter.followup.send("\u200b", view=save)

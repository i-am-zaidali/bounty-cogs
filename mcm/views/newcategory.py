import discord
from redbot.core.bot import Red

from ..common.models import GuildSettings
from .categoryeditor import CategoryEditor
from .paginator import CloseButton
from .viewdisableontimeout import ViewDisableOnTimeout

__all__ = ["NewCategory"]


class NewCategory(ViewDisableOnTimeout):
    def __init__(self, conf: GuildSettings):
        self.conf = conf

        super().__init__(timeout=60)

        self.add_item(CloseButton())

    @discord.ui.button(
        label="Add Category", custom_id="_add_category", style=discord.ButtonStyle.green
    )
    async def ac_callback(self, inter: discord.Interaction, button: discord.ui.Button):
        modal = CategoryNameModal(
            categories=self.conf.vehicle_categories, title="Enter the category name:"
        )
        await inter.response.send_modal(modal)
        if await modal.wait():
            message = await inter.followup.send("Cancelled.", wait=True)
            return await message.delete(delay=10)

        editor = CategoryEditor(self.conf, modal.name.value)
        await inter.response.edit_message(view=editor)


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

        all_categories = await self.config.guild(interaction.guild).vehicle_categories()
        if self.name.value.strip().lower() in all_categories:
            return await interaction.response.send_message(
                "That category already exists.", ephemeral=True
            )
        await interaction.response.defer()
        await self.stop()
        await self.further_handling(interaction, self.name.value.strip().lower())

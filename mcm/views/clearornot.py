import re
from typing import TYPE_CHECKING

import discord
from redbot.core.bot import Red

from .viewdisableontimeout import disable_items

if TYPE_CHECKING:
    from ..main import MissionChiefMetrics

__all__ = ["Clear", "Not", "ClearOrNot"]


async def interaction_check(
    interaction: discord.Interaction[Red], item: discord.ui.Item
) -> bool:
    cog = interaction.client.get_cog("MissionChiefMetrics")
    if not cog:
        await interaction.response.send_message(
            "The MissionChiefMetrics cog isn't loaded.",
            ephemeral=True,
        )
        return False

    if not await interaction.client.is_mod(
        interaction.user
    ) and interaction.user.id not in (
        interaction.guild.owner_id,
        *interaction.client.owner_ids,
    ):
        await interaction.response.send_message(
            "You aren't allowed to interact with this.", ephemeral=True
        )
        return False
    disable_items(item.view)
    item.disabled = True
    await interaction.response.edit_message(view=item.view)
    return True


class Clear(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"MCM_CLEAR_(?P<user>\d{17,20})",
):
    def __init__(self, userid: int):
        self.userid = userid
        item = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Clear",
            custom_id=f"MCM_CLEAR_{userid}",
        )
        super().__init__(item)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Red],
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        return cls(int(match.group("user")))

    async def callback(self, interaction: discord.Interaction[Red]):
        await interaction.response.send_message("Clearing...", ephemeral=True)
        cog: MissionChiefMetrics = interaction.client.get_cog(
            "MissionChiefMetrics"
        )

        conf = cog.db.get_conf(interaction.guild)
        if conf is None:
            return

        async with conf:
            conf.members.pop(self.userid, None)

        await interaction.edit_original_response(content="Cleared.")

    async def interaction_check(
        self, interaction: discord.Interaction[Red]
    ) -> bool:
        return await interaction_check(interaction, self.item)


class Not(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"MCM_NOT_(?P<user>\d{17,20})",
):
    def __init__(self, userid: int):
        self.userid = userid
        item = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Not",
            custom_id=f"MCM_NOT_{userid}",
        )
        super().__init__(item)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[Red],
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        return cls(int(match.group("user")))

    async def callback(self, interaction: discord.Interaction[Red]):
        await interaction.response.send_message(
            "Ok I won't clear their stats...", ephemeral=True
        )

    async def interaction_check(
        self, interaction: discord.Interaction[Red]
    ) -> bool:
        return await interaction_check(interaction, self.item)


class ClearOrNot(discord.ui.View):
    """
    A generic view subclass which \
        rids me of having to manually add the items \
            in places where they are requires."""

    def __init__(self, user: discord.Member):
        super().__init__(timeout=1)
        self.add_item(Clear(user.id))
        self.add_item(Not(user.id))

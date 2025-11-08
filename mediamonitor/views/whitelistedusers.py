from typing import TYPE_CHECKING

import discord

from . import ViewDisableOnTimeout

if TYPE_CHECKING:
    from ..main import MediaMonitor


class WhitelistedUsersSelect(ViewDisableOnTimeout):
    def __init__(self, cog: "MediaMonitor", guild: discord.Guild):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.user_select.default_values = [
            discord.Object(id=uid, type=discord.abc.User)
            for uid in cog.db.get_conf(guild.id).whitelisted_members
        ]

    @discord.ui.select(
        cls=discord.ui.UserSelect["WhitelistedUsersSelect"],
        placeholder="Select users to whitelist from media monitoring",
        min_values=0,
        max_values=25,
    )
    async def user_select(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ):
        if select.values:
            content = "Your whitelisted users have been updated to:\n"
            content += "\n".join(
                f"{ind}. {user.mention}" for ind, user in enumerate(select.values, 1)
            )

        else:
            content = "You have cleared all whitelisted users."

        content += "\n\nThese changes have not been saved yet. Click the `SAVE` button to do so."
        await interaction.response.edit_message(content=content)

    @discord.ui.button(
        label="Save",
        style=discord.ButtonStyle.green,
        custom_id="mediamonitor_save_whitelisted_users",
    )
    async def save_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        selected_user_ids = [user.id for user in self.user_select.values]
        async with self.cog.db.get_conf(self.guild.id) as conf:
            conf.whitelisted_members = selected_user_ids
        self.user_select.disabled = True
        button.disabled = True
        await interaction.response.edit_message(
            content="Whitelisted users have been updated to: \n"
            + "\n".join(
                f"{ind}. <@{uid}>" for ind, uid in enumerate(selected_user_ids, 1)
            ),
            view=self,
        )

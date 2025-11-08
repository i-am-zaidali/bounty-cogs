from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from ..main import MediaMonitor


class MonitoringChannelSelect(discord.ui.View):
    def __init__(self, cog: "MediaMonitor", guild: discord.Guild):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.channel_select.default_values = [
            discord.Object(id=cid, type=discord.abc.GuildChannel)
            for cid in cog.db.get_conf(guild.id).monitoring_channels
        ]

    @discord.ui.select(
        cls=discord.ui.ChannelSelect["MonitoringChannelSelect"],
        placeholder="Select channels to monitor for media attachments",
        min_values=0,
        max_values=25,
        channel_types=[
            discord.ChannelType.text,
            discord.ChannelType.public_thread,
            discord.ChannelType.voice,
        ],
        custom_id="mediamonitor_channel_select",
    )
    async def channel_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ):
        if select.values:
            content = "Your monitoring channels have been updated to:\n"
            content += "\n".join(
                f"{ind}. {channel.mention}"
                for ind, channel in enumerate(select.values, 1)
            )

        else:
            content = "You have cleared all monitoring channels."

        content += "\n\nThese changes have not been saved yet. Click the `SAVE` button to do so."
        await interaction.response.edit_message(content=content)

    @discord.ui.button(
        label="Save",
        style=discord.ButtonStyle.green,
        custom_id="mediamonitor_save_monitoring_channels",
    )
    async def save_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        selected_channel_ids = [channel.id for channel in self.channel_select.values]
        async with self.cog.db.get_conf(self.guild.id) as conf:
            conf.monitoring_channels = selected_channel_ids
        self.channel_select.disabled = True
        button.disabled = True
        await interaction.response.edit_message(
            content="Monitoring channels have been updated to: \n"
            + "\n".join(
                f"{ind}. <#{cid}>" for ind, cid in enumerate(selected_channel_ids, 1)
            ),
            view=self,
        )

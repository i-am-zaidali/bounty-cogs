import functools

import discord
import discord.ui

from risk.common.riskmodels import RiskState, Territory


class PlaceArmiesAmountView(discord.ui.View):
    def __init__(self, state: RiskState, selected: Territory):
        super().__init__()
        for i in range(1, min(26, state.turn_player.armies + 1)):
            item = discord.ui.Button(style=discord.ButtonStyle.primary, label=str(i))

            self.add_item(item)
            item.callback = functools.partial(self.num_callback, button=item)

        self.selected = selected

        self.state = state

    async def num_callback(
        self, interaction: discord.Interaction, *, button: discord.ui.Button
    ):
        amount = int(button.label)
        await interaction.response.defer()
        await interaction.delete_original_response()

        self.state.turn_player.armies -= amount
        self.state.turn_player.captured_territories.setdefault(self.selected, 0)
        self.state.turn_player.captured_territories[self.selected] += amount

        await interaction.followup.send(
            f"Successfully placed {amount} armies on {self.selected.name.replace('_', ' ').title()} by {interaction.user.mention}.",
        )
        self.stop()

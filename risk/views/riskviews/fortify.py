import functools

import discord

from risk.common.riskmodels import RiskState, Territory


class FortifyAmountView(discord.ui.View):
    def __init__(self, state: RiskState, _from: Territory, to: Territory):
        super().__init__(timeout=300)
        self.state = state
        self._from = _from
        self.to = to

        for i in range(1, min(26, state.turn_player.captured_territories[_from])):
            item = discord.ui.Button(style=discord.ButtonStyle.primary, label=str(i))

            self.add_item(item)
            item.callback = functools.partial(self.num_callback, button=item)

    async def num_callback(
        self, interaction: discord.Interaction, *, button: discord.ui.Button
    ):
        amount = int(button.label)
        await interaction.response.defer()
        await interaction.delete_original_message()

        self.state.turn_player.captured_territories[self._from] -= amount
        self.state.turn_player.captured_territories.setdefault(self.to, 0)
        self.state.turn_player.captured_territories[self.to] += amount

        await interaction.followup.send(
            f"Successfully moved {amount} armies from {self._from.name.replace('_', ' ').title()} to {self.to.name.replace('_', ' ').title()} by {interaction.user.mention}.",
        )
        self.stop()

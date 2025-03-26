import discord

from risk.common.riskmodels import RiskState


class CardSelect(discord.ui.Select[discord.ui.View]):
    def __init__(self, state: RiskState):
        assert state.turn is not None
        self.state = state
        options = [
            discord.SelectOption(
                label=getattr(card.territory, "name", "Wildcard"),
                value=str(i),
                description=getattr(card.name, "name", None),
            )
            for i, card in enumerate(state.players[state.turn].cards)
        ]
        super().__init__(
            placeholder="Select a card", options=options, min_values=3, max_values=3
        )

    async def callback(self, interaction: discord.Interaction):
        player = self.state.turn_player
        selected_cards = [player.cards[int(value)] for value in self.values]

        # check for combinations, either all the cards should have the same army denomination or all should have different
        if len({card.army for card in selected_cards}) not in (1, 3):
            return await interaction.response.send_message(
                "Invalid combination of cards. Either all cards should have the same army denomination or all should have different",
                ephemeral=True,
            )

        await interaction.response.defer()

        player.cards = [card for card in player.cards if card not in selected_cards]
        self.state.card_sets_traded += 1

        armies_rewarded = 0

        match self.state.card_sets_traded:
            case 1:
                armies_rewarded = 4

            case 2:
                armies_rewarded = 6

            case 3:
                armies_rewarded = 8

            case 4:
                armies_rewarded = 10

            case 5:
                armies_rewarded = 12

            case 6:
                armies_rewarded = 15

            case _:
                armies_rewarded = 15 + (self.state.card_sets_traded - 6) * 5

        if any(
            card.territory in player.captured_territories for card in selected_cards
        ):
            armies_rewarded += 2

        player.armies += armies_rewarded

        await interaction.delete_original_response()

        await interaction.followup.send(
            f"Traded cards for {armies_rewarded} armies", ephemeral=True
        )
        self.state.turn_phase_completed = len(self.state.turn_player.cards) <= 5

        self.view.stop()

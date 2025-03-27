import asyncio
import random
from typing import TYPE_CHECKING

import discord
from redbot.core import commands
from redbot.core.utils.views import ConfirmView

from risk.common.riskmodels import Player, RiskState, Territory, TurnPhase, color_names
from risk.views.riskviews.game import GameView
from risk.views.viewdisableontimeout import disable_items

if TYPE_CHECKING:
    from risk.main import Risk


class JoinGame(discord.ui.View):
    def __init__(self, host: discord.Member, ctx: commands.Context):
        super().__init__(timeout=None)
        self.state = RiskState(host=host.id)
        self.cog: "Risk" = ctx.cog
        self.ctx = ctx
        self.state.players.append(
            Player(id=host.id, turn=0, color=self.state.COLORS.pop())
        )

    @discord.ui.button(
        label="Join Game", style=discord.ButtonStyle.primary, custom_id="JOIN_GAME"
    )
    async def join_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        players = self.state.players

        if self.state.host == interaction.user.id:
            await interaction.response.send_message(
                "You are the host of the game and already a player.", ephemeral=True
            )
            return

        if len(players) == 6:
            await interaction.response.send_message(
                "Game is full. Not accepting any new players.", ephemeral=True
            )
            return

        for player in players:
            if player.id == interaction.user.id:
                await interaction.response.send_message(
                    "You are already a player in the game.", ephemeral=True
                )
                return

        else:
            color = random.choice(list(self.state.COLORS))
            self.state.COLORS.remove(color)
            players.append(Player(id=interaction.user.id, turn=0, color=color))

        await interaction.response.edit_message(embed=self.format_embed())

    @discord.ui.button(
        label="Leave Game", style=discord.ButtonStyle.danger, custom_id="LEAVE_GAME"
    )
    async def leave_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        players = self.state.players

        if self.state.host == interaction.user.id:
            await interaction.response.send_message(
                "You are the host of the game and cannot leave.", ephemeral=True
            )
            return

        for ind in range(len(players)):
            player = players[ind]
            if player.id == interaction.user.id:
                players.pop(ind)
                self.state.COLORS.add(player.color)
                break

        else:
            await interaction.response.send_message(
                "You are not in the game.", ephemeral=True
            )
            return

        await interaction.response.edit_message(embed=self.format_embed())

    @discord.ui.button(
        label="Start Game",
        style=discord.ButtonStyle.success,
        row=1,
        custom_id="START_GAME",
    )
    async def start_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        players = self.state.players

        if self.state.host != interaction.user.id:
            await interaction.response.send_message(
                "Only the host can start the game.", ephemeral=True
            )
            return

        if len(players) < 2:
            await interaction.response.send_message(
                "Need at least 2 players to start the game.", ephemeral=True
            )
            return

        await interaction.response.edit_message(view=None)

        view = ConfirmView(interaction.user)
        view.message = await interaction.followup.send(
            "Should users have randomized claimed territories?",
            view=view,
            ephemeral=True,
            wait=True,
        )
        if await view.wait():
            await interaction.followup.send(
                "You took too long to answer. Defaulting to manual claiming.",
                ephemeral=True,
            )
            randomize_territories = False

        else:
            assert view.result is not None
            randomize_territories = view.result

        await interaction.followup.send(
            f"The game has been started with {len(players)} players. I will be rolling dices for each individual player, the one with the highest dice number gets the first turn.",
        )

        await asyncio.sleep(1.5)
        await interaction.followup.send(
            "The rolls for each player are as follows:\n"
            + "\n".join(
                f"{player.mention} ({color_names[player.color]}): {player.initial_roll}"
                for player in players
            )
        )
        self.state.players.sort(key=lambda p: p.initial_roll, reverse=True)
        armies_per_player = 50 - 5 * len(players)
        for ind in range(len(players)):
            players[ind].turn = ind
            players[ind].armies = armies_per_player

        await interaction.followup.send(
            f"{players[0].mention} has the first turn. Each user has {armies_per_player} armies to place on the board."
        )

        if randomize_territories:
            territories = list(Territory)
            random.shuffle(territories)
            terr_per_player, remaining_terrs = divmod(len(territories), len(players))
            start_index = 0
            for ind, player in enumerate(players):
                armies_per_terr, remaining_armies = divmod(
                    armies_per_player, terr_per_player
                )
                end_index = start_index + terr_per_player
                if remaining_terrs > 0:
                    end_index += 1
                    remaining_terrs -= 1

                for t in territories[start_index:end_index]:
                    armies = armies_per_terr
                    if remaining_armies > 0:
                        armies += 1
                        remaining_armies -= 1
                    player.captured_territories[t] = armies
                    self.state.territories[t] = player.turn
                    player.armies -= armies

                start_index = end_index
            self.state.turn_phase = TurnPhase.ARMY_CALCULATION

        else:
            self.state.turn_phase = TurnPhase.INITIAL_ARMY_PLACEMENT

        self.state.turn = 0

        view = GameView(self.state, self.ctx)

        self.cog.cache[self.ctx.channel.id] = view

        if self.state.turn_phase is TurnPhase.ARMY_CALCULATION:
            await view.army_calculation_phase(interaction)

        view.update_acc_to_state()

        file = await self.state.format_embed(interaction)

        view.message = await interaction.followup.send(
            f"{players[0].mention} has the first turn.\n\nThey have {players[0].armies} armies remaining.",
            file=file,
            view=view,
            wait=True,
        )

    @discord.ui.button(
        label="Cancel Game",
        style=discord.ButtonStyle.danger,
        row=1,
        custom_id="CANCEL_GAME",
    )
    async def cancel_game(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.state.host != interaction.user.id:
            await interaction.response.send_message(
                "Only the host can cancel the game.", ephemeral=True
            )
            return

        disable_items(self)
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("Game has been cancelled.", ephemeral=True)
        self.stop()

    def format_embed(self):
        players = self.state.players
        return discord.Embed(
            title="Risk Game",
            description=f"Started by: <@{self.state.host}>",
        ).add_field(
            name="Players",
            value="\n".join(
                f"{ind}. {player.mention}" for ind, player in enumerate(players)
            ),
        )

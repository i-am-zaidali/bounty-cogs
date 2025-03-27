import asyncio
import random
import typing

import discord
from redbot.core import commands
from redbot.core.data_manager import bundled_data_path
from redbot.core.utils.views import ConfirmView

from risk.common.riskmodels import (
    Continent,
    RiskState,
    Territory,
    TurnPhase,
    territory_adjacency,
)
from risk.views.riskviews.trade_cards import CardSelect
from risk.views.utilviews import NumberedButtonsView, SelectView
from risk.views.viewdisableontimeout import disable_items

if typing.TYPE_CHECKING:
    from ...main import Risk

ALERT_MESSAGE_DELETE_DELAY = 15


class GameView(discord.ui.View):
    def __init__(self, state: RiskState, ctx: commands.Context):
        self.message: discord.Message
        self.state = state
        self.cog: "Risk" = ctx.cog
        self.ctx = ctx
        super().__init__(timeout=None)
        self.update_acc_to_state()
        self.current_sip_votes = 0
        self.edit_task: asyncio.Task[None] | None = None

    def disable_except_essentials(self):
        disable_items(self)
        self.force_skip.disabled = False
        self.end_game.disabled = False
        self.show_raw_map.disabled = False

    def update_acc_to_state(self):
        self.disable_except_essentials()
        if self.state.turn_phase is TurnPhase.INITIAL_ARMY_PLACEMENT:
            if not self.state.turn_phase_completed:
                self.place_armies.disabled = False

        else:
            phase_button: discord.ui.Button = None
            match self.state.turn_phase:
                case TurnPhase.CARD_TRADE | TurnPhase.FORCED_CARD_TRADE:
                    phase_button = self.trade_cards

                case TurnPhase.PLACE_ARMIES:
                    phase_button = self.place_armies

                case TurnPhase.ATTACK:
                    phase_button = self.attack

                case TurnPhase.FORTIFY:
                    phase_button = self.fortify

                case _:
                    phase_button = self.end_game

            phase_button.disabled = False

        if not self.state.turn_phase.required or self.state.turn_phase_completed:
            self.skip_phase.disabled = False

        match self.state.turn_phase:
            case TurnPhase.FORTIFY | TurnPhase.INITIAL_ARMY_PLACEMENT:
                self.skip_phase.label = "End Turn"
                self.skip_phase.custom_id = "end_turn"

            case (
                TurnPhase.CARD_TRADE
                | TurnPhase.FORCED_CARD_TRADE
                | TurnPhase.PLACE_ARMIES
            ):
                self.skip_phase.label = "Skip Phase"
                self.skip_phase.custom_id = "skip_phase"

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data["custom_id"] in ["show_raw_map", "force_skip"]:
            return True

        if interaction.data["custom_id"] == "end_game":
            if interaction.user.id == self.state.host:
                return True
            else:
                await interaction.response.send_message(
                    "Only the host can end the game", ephemeral=True
                )
                return False

        else:
            if interaction.user.id == self.state.players[self.state.turn].id:
                return True

            await interaction.response.send_message(
                "It's not your turn", ephemeral=True
            )
            return False

    @discord.ui.button(label="Trade cards", style=discord.ButtonStyle.primary, row=1)
    async def trade_cards(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        self.disable_except_essentials()
        await interaction.response.edit_message(view=self)
        if len(self.state.turn_player.cards) < 3:
            self.state.turn_phase_completed = True
            if self.edit_task is not None and self.edit_task.done() is False:
                self.edit_task.cancel()
            self.edit_task = asyncio.create_task(self.show_updated_board(interaction))
            return await interaction.followup.send(
                "You do not have enough cards to form a set to trade", ephemeral=True
            )

        select = CardSelect(self.state)
        view = discord.ui.View(timeout=None)
        view.add_item(select)
        await interaction.followup.send(
            "Select 3 cards to trade", view=view, epehemral=True
        )
        await view.wait()
        if self.edit_task is not None and self.edit_task.done() is False:
            self.edit_task.cancel()
        self.edit_task = asyncio.create_task(self.show_updated_board(interaction))

    @discord.ui.button(label="Place armies", style=discord.ButtonStyle.primary, row=1)
    async def place_armies(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        self.disable_except_essentials()
        await interaction.response.edit_message(view=self)
        if self.state.turn_player.armies == 0:
            self.state.turn_phase_completed = True
            if self.edit_task is not None and self.edit_task.done() is False:
                self.edit_task.cancel()
            self.edit_task = asyncio.create_task(self.show_updated_board(interaction))
            return await interaction.followup.send(
                "You have no armies to place", ephemeral=True
            )

        if (
            self.state.turn_phase is TurnPhase.INITIAL_ARMY_PLACEMENT
            and self.state.turn_phase_completed
        ):
            if self.edit_task is not None and self.edit_task.done() is False:
                self.edit_task.cancel()
            self.edit_task = asyncio.create_task(self.show_updated_board(interaction))
            return await interaction.followup.send(
                "You have already placed your armies for this turn.", ephemeral=True
            )

        options: list[discord.SelectOption] = []
        for t, turn in self.state.territories.items():
            #     filter(
            #     lambda x: x[1] == self.state.players[self.state.turn].id
            #     if self.state.turn_phase != TurnPhase.INITIAL_ARMY_PLACEMENT
            #     or self.state.turn_player.armies > 0
            #     else x[1] is None,
            #     self.state.territories.items(),
            # ):
            option = discord.SelectOption(
                label=f"{t.name.replace('_', ' ').title()} || {t.continent.name.replace('_', ' ').title()}",
                value=str(t.value),
                description=f"Armies: {self.state.turn_player.captured_territories.get(t, 0)}",
            )

            if (
                self.state.turn_phase is TurnPhase.INITIAL_ARMY_PLACEMENT
                and (
                    (
                        any(player.armies > 0 for player in self.state.players)
                        and all(
                            turn is not None for turn in self.state.territories.values()
                        )
                        and turn == self.state.turn
                    )
                    or turn is None
                )
            ) or turn == self.state.turn:
                options.append(option)

        view = SelectView(
            "Select a territory to place armies on",
            options=options,
            max_selected=1,
            allowed_to_interact=[self.state.turn_player.id],
        )
        result = await self.send_select(view, interaction)
        if not result:
            return

        territory = Territory._value2member_map_.get(int(result.pop().value))
        assert territory is not None

        self.state.territories[territory] = self.state.turn

        if self.state.turn_phase is TurnPhase.INITIAL_ARMY_PLACEMENT:
            armies = 1

        else:
            aview = NumberedButtonsView(
                range(1, min(26, self.state.turn_player.armies + 1))
            )
            await interaction.followup.send(
                f"Select the amount of armies to place on {territory.name}",
                view=aview,
                ephemeral=True,
            )
            if await aview.wait():
                if self.state.turn_player.captured_territories.get(territory) is None:
                    self.state.territories[territory] = None
                await interaction.followup.send(
                    "Why you take so long to respond bro?", ephemeral=True
                )
                if self.edit_task is not None and self.edit_task.done() is False:
                    self.edit_task.cancel()
                self.edit_task = asyncio.create_task(
                    self.show_updated_board(interaction)
                )
                return

            armies = aview.result

        self.state.turn_player.armies -= armies
        self.state.turn_player.captured_territories.setdefault(territory, 0)
        self.state.turn_player.captured_territories[territory] += armies

        msg = await interaction.followup.send(
            f"Successfully placed {armies} armies on {territory.name.replace('_', ' ').title()} by {interaction.user.mention}.",
            wait=True,
        )
        await msg.delete(delay=ALERT_MESSAGE_DELETE_DELAY)
        self.state.turn_phase_completed = True
        print(f"Updating board for {interaction.user.display_name}")
        if self.edit_task is not None and self.edit_task.done() is False:
            self.edit_task.cancel()
        self.edit_task = asyncio.create_task(self.show_updated_board(interaction))

    @discord.ui.button(label="Attack", style=discord.ButtonStyle.primary, row=1)
    async def attack(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        self.disable_except_essentials()
        await interaction.response.edit_message(view=self)

        await self.attack_logic(interaction)

        if self.edit_task is not None and self.edit_task.done() is False:
            self.edit_task.cancel()
        self.edit_task = asyncio.create_task(self.show_updated_board(interaction))

    @discord.ui.button(
        label="Fortify (Move armies)", style=discord.ButtonStyle.blurple, row=1
    )
    async def fortify(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        self.disable_except_essentials()
        await interaction.response.edit_message(view=self)
        if len(self.state.turn_player.captured_territories) < 2:
            return await interaction.followup.send(
                "You need to have at least 2 captured territories to fortify",
                ephemeral=True,
            )

        player = self.state.turn_player

        options: list[discord.SelectOption] = [
            discord.SelectOption(
                label=f"{territory.name.replace('_', ' ').title()} - {territory.continent.name.replace('_', ' ').title()}",
                value=str(territory.value),
                description=f"Armies: {armies}",
            )
            for territory, armies in player.captured_territories.items()
            if armies > 1
        ]
        view = SelectView(
            "Select the territory to move armies from",
            options=options,
            max_selected=1,
        )

        result = await self.send_select(view, interaction)
        if not result:
            return

        _from = result.pop()
        options.remove(_from)

        _from = Territory._value2member_map_[int(_from.value)]

        options = [
            discord.SelectOption(
                label=f"{territory.name.replace('_', ' ').title()} - {territory.continent.name.replace('_', ' ').title()}",
                value=str(territory.value),
                description=f"Captured by: {interaction.guild.get_member(player.id).display_name} "
                f"|| Armies: {player.captured_territories[territory]}",
            )
            for territory in territory_adjacency[_from]
            if self.state.territories[territory] == self.state.turn
        ]

        if not options:
            self.update_acc_to_state()
            await interaction.edit_original_response(view=self)
            return await interaction.followup.send(
                f"There are no territories accessible from {_from.name.replace('_', ' ').title()}",
                ephemeral=True,
            )

        view = SelectView(
            "Select the territory to move armies to",
            options=options,
            max_selected=2,
        )

        result = await self.send_select(view, interaction)
        if not result:
            return

        to = Territory._value2member_map_[int(result.pop().value)]

        view = NumberedButtonsView(
            range(1, self.state.turn_player.captured_territories[_from])
        )
        await interaction.followup.send(
            f"Select the amount of armies to move from {_from.name.replace('_', ' ').title()} to {to.name.replace('_', ' ').title()}",
            view=view,
            ephemeral=True,
        )
        if await view.wait():
            if self.edit_task is not None and self.edit_task.done() is False:
                self.edit_task.cancel()
            self.edit_task = asyncio.create_task(self.show_updated_board(interaction))
            await interaction.followup.send(
                "Why you take so long to respond bro?", ephemeral=True
            )
            return

        self.state.turn_player.captured_territories[_from] -= view.result
        self.state.turn_player.captured_territories[to] += view.result

        msg = await interaction.followup.send(
            f"Successfully moved {view.result} armies from {_from.name.replace('_', ' ').title()} to {to.name.replace('_', ' ').title()} by {interaction.user.mention}.",
            wait=True,
        )
        await msg.delete(delay=ALERT_MESSAGE_DELETE_DELAY)

        if self.edit_task is not None and self.edit_task.done() is False:
            self.edit_task.cancel()
        self.edit_task = asyncio.create_task(self.show_updated_board(interaction))

    @discord.ui.button(
        label="Skip Phase",
        style=discord.ButtonStyle.green,
        row=2,
        custom_id="skip_phase",
    )
    async def skip_phase(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.defer()

        if button.custom_id == "skip_phase":
            self.state.turn_phase = self.state.turn_phase.next()

        elif button.custom_id == "end_turn":
            await self.end_turn_logic(interaction)

        if self.state.turn_phase is TurnPhase.ARMY_CALCULATION:
            await self.army_calculation_phase(interaction)
        if self.edit_task is not None and self.edit_task.done() is False:
            self.edit_task.cancel()
        self.edit_task = asyncio.create_task(self.show_updated_board(interaction))

    async def end_turn_logic(self, interaction: discord.Interaction | None = None):
        if self.state.turn_phase is TurnPhase.INITIAL_ARMY_PLACEMENT:
            if all(player.armies == 0 for player in self.state.players) and all(
                turn is not None for turn in self.state.territories.values()
            ):
                self.state.turn_phase = TurnPhase.ARMY_CALCULATION

            else:
                self.state.turn_phase = TurnPhase.INITIAL_ARMY_PLACEMENT
            self.state.next_turn()

        else:
            if self.state.turn_territories_captured > 0:
                card = self.state.draw_pile.pop()
                self.state.turn_player.cards.append(card)
                if interaction:
                    msg = await interaction.followup.send(
                        f"{self.state.turn_player.mention} has received a card for capturing a territory.\n"
                        f"{card}",
                        wait=True,
                        file=discord.File(
                            bundled_data_path(self.cog)
                            / "cards"
                            / f"{card.territory.name.lower()}.png"
                        ),
                    )
                    await msg.delete(delay=ALERT_MESSAGE_DELETE_DELAY)

                else:
                    await self.ctx.send(
                        f"{self.state.turn_player.mention} has received a card for capturing a territory.\n"
                        f"{card}",
                        file=discord.File(
                            bundled_data_path(self.cog)
                            / "cards"
                            / f"{card.territory.name.lower()}.png"
                        ),
                    )
            self.state.next_turn()
            self.state.turn_phase = TurnPhase.ARMY_CALCULATION
            msg = await interaction.followup.send(
                f"{self.state.turn_player.mention} it's your turn now.",
                wait=True,
            )
            await msg.delete(delay=ALERT_MESSAGE_DELETE_DELAY)

    async def army_calculation_phase(
        self, interaction: discord.Interaction | None = None
    ):
        self.state.turn_player.armies += max(
            3, len(self.state.turn_player.captured_territories) // 3
        )
        alert = f"- {self.state.turn_player.mention} has received {self.state.turn_player.armies} armies\n"

        # check if any of the territories the user has captured form a continent

        ctx = (
            interaction.followup
            if isinstance(interaction, discord.Interaction)
            else self.ctx
        )
        kwargs = {"wait": True} if isinstance(interaction, discord.Interaction) else {}

        for continent in Continent:
            if all(
                territory in self.state.turn_player.captured_territories
                for territory in continent.territories
            ):
                self.state.turn_player.armies += continent
                alert += f"- {self.state.turn_player.mention} has received {continent.value} armies for capturing {continent.name}\n"

        if alert:
            msg = await ctx.send(alert, **kwargs)
            await msg.delete(delay=ALERT_MESSAGE_DELETE_DELAY)

        if len(self.state.turn_player.cards) >= 5:
            msg = await ctx.send(
                f"{self.state.turn_player.mention} has more than 5 cards, they must trade cards",
                **kwargs,
            )
            await msg.delete(delay=ALERT_MESSAGE_DELETE_DELAY)
            self.state.turn_phase = TurnPhase.FORCED_CARD_TRADE

        else:
            self.state.turn_phase = TurnPhase.CARD_TRADE

        self.state.turn_armies_received = True

    @discord.ui.button(
        label="End Game", style=discord.ButtonStyle.danger, row=2, custom_id="end_game"
    )
    async def end_game(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        self.disable_except_essentials()
        await interaction.response.edit_message(view=self)
        view = ConfirmView(interaction.user)
        view.message = await interaction.followup.send(
            "DO you want to save this game to continue later? This save will be linked to this channel",
            ephemeral=True,
            view=view,
            wait=True,
        )
        if await view.wait():
            await interaction.followup.send(
                "Game not saved, you took too long to answer", ephemeral=True
            )
            return

        if view.result:
            async with self.cog.db.get_conf(interaction.guild.id) as conf:
                if interaction.channel.id in conf.saves:
                    view = ConfirmView(interaction.user)
                    view.message = await interaction.followup.send(
                        "There is already a saved game in this channel, do you want to overwrite it?",
                        ephemeral=True,
                        view=view,
                        wait=True,
                    )
                    if await view.wait():
                        await interaction.followup.send(
                            "Game not saved, you took too long to answer",
                            ephemeral=True,
                        )
                        return

                    if not view.result:
                        return

                conf.saves[interaction.channel.id] = self.state

        self.cog.cache.pop(interaction.channel.id, None)

        self.stop()
        await interaction.followup.send("Game ended")

    @discord.ui.button(
        label="Show Raw Map",
        style=discord.ButtonStyle.gray,
        row=3,
        custom_id="show_raw_map",
    )
    async def show_raw_map(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_message(
            "Here is the raw map",
            file=discord.File(
                bundled_data_path(interaction.client.get_cog("Risk")) / "riskmap.png"
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Force Skip", style=discord.ButtonStyle.red, row=3)
    async def force_skip(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        self.current_sip_votes += 1
        if self.current_sip_votes >= len(self.state.players) / 2:
            await self.end_turn_logic(interaction)
            self.current_sip_votes = 0
            if self.state.turn_phase is TurnPhase.ARMY_CALCULATION:
                await self.army_calculation_phase(interaction)
            await interaction.response.edit_message(view=self)
            if self.edit_task is not None and self.edit_task.done() is False:
                self.edit_task.cancel()
            self.edit_task = asyncio.create_task(self.show_updated_board(interaction))

    async def send_select(self, view: SelectView, inter: discord.Interaction):
        view.message = await inter.followup.send(
            view.select_placeholder, view=view, wait=True, ephemeral=True
        )

        timed_out = await view.wait()
        if timed_out:
            if self.edit_task is not None and self.edit_task.done() is False:
                self.edit_task.cancel()
            self.edit_task = asyncio.create_task(self.show_updated_board(inter))
            await inter.followup.send(
                "You took too long to respond. Please try again.", ephemeral=True
            )

        return view.selected

    async def show_updated_board(self, inter: discord.Interaction | None = None):
        self.disable_except_essentials()
        await getattr(inter, "edit_original_response", self.message.edit)(
            content="Please wait while the updated board is being generated...",
            view=self,
            embed=None,
            attachments=[],
        )
        file = await self.state.format_embed(inter)
        self.update_acc_to_state()
        # for child in self.children:
        #     child = typing.cast("discord.ui.Button[GameView]", child)
        #     print(f"{child.label} -> {child.disabled = }")

        await getattr(inter, "edit_original_response", self.message.edit)(
            content=f"{self.state.turn_player.mention} it's your turn\n\nThey have {self.state.turn_player.armies} armies remaining.",
            attachments=[file],
            view=self,
        )

    async def attack_logic(self, inter: discord.Interaction):
        options = [
            discord.SelectOption(
                label=f"{territory.name.replace('_', ' ').title()} - {territory.continent.name.replace('_', ' ').title()}",
                value=str(territory.value),
                description=f"Armies: {armies}",
            )
            for territory, armies in self.state.turn_player.captured_territories.items()
            if armies > 1
        ]

        if not options:
            if self.edit_task is not None and self.edit_task.done() is False:
                self.edit_task.cancel()
            self.edit_task = asyncio.create_task(self.show_updated_board(inter))
            return await inter.followup.send(
                "You need to have at least 2 armies on a territory to attack",
                ephemeral=True,
            )

        view = SelectView(
            "Select a territory to attack from",
            options=options,
            max_selected=1,
        )

        result = await self.send_select(view, inter)
        if not result:
            return

        _from = Territory._value2member_map_[int(result.pop().value)]

        options = [
            discord.SelectOption(
                label=f"{territory.name.replace('_', ' ').title()} - {territory.continent.name.replace('_', ' ').title()}",
                value=str(territory.value),
                description=f"Captured by: {inter.guild.get_member(player.id).display_name} "
                f"|| Armies: {armies}",
            )
            for territory in territory_adjacency[_from]
            if (player_turn := self.state.territories[territory]) is not None
            and player_turn != self.state.turn
            and (player := self.state.players[player_turn])
            and (armies := player.captured_territories[territory])
        ]

        if not options:
            if self.edit_task is not None and self.edit_task.done() is False:
                self.edit_task.cancel()
            self.edit_task = asyncio.create_task(self.show_updated_board(inter))
            return await inter.followup.send(
                f"There are no attackable territories accessible from {_from.name.replace('_', ' ').title()}",
                ephemeral=True,
            )

        view = SelectView(
            "Select a territory to attack",
            options=options,
            max_selected=1,
        )

        result = await self.send_select(view, inter)
        if not result:
            return

        to = Territory._value2member_map_[int(result.pop().value)]

        defender_turn = self.state.territories[to]
        assert defender_turn is not None

        defender = self.state.players[defender_turn]
        attacker = self.state.turn_player

        arng = range(1, min(4, attacker.captured_territories[_from]))

        if len(arng) == 1:
            attacker_dice = 1

        else:
            view = NumberedButtonsView(arng, allowed_to_interact=[attacker.id])
            await inter.followup.send(
                f"Select the amount of dice to roll to attack {to.name.replace('_', ' ').title()} from {_from.name.replace('_', ' ').title()}",
                view=view,
                ephemeral=True,
            )
            if await view.wait():
                self.disable_except_essentials()
                await inter.edit_original_response(
                    content="Please wait while the updated board is being generated...",
                    view=self,
                    embed=None,
                    attachments=[],
                )
                self.update_acc_to_state()
                file = await self.state.format_embed(inter)
                await inter.edit_original_response(attachments=[file], view=self)
                return await inter.followup.send(
                    "Why you take so long to respond bro?", ephemeral=True
                )

            attacker_dice = view.result

        drng = range(1, min(3, defender.captured_territories[to] + 1))

        if len(drng) == 1:
            defender_dice = 1

        else:
            view = NumberedButtonsView(drng)
            await inter.followup.send(
                f"{defender.mention} Select the amount of dice to roll to defend {to.name.replace('_', ' ').title()} from {_from.name.replace('_', ' ').title()}",
                view=view,
            )
            if await view.wait():
                self.disable_except_essentials()
                await inter.edit_original_response(
                    content="Please wait while the updated board is being generated...",
                    view=self,
                    embed=None,
                    attachments=[],
                )
                self.update_acc_to_state()
                file = await self.state.format_embed(inter)
                await inter.edit_original_response(file=file, view=self)
                return await inter.followup.send(
                    "Why you take so long to respond bro?", ephemeral=True
                )

            defender_dice = view.result

        arolls = [random.randrange(1, 7) for _ in range(attacker_dice)]
        drolls = [random.randrange(1, 7) for _ in range(defender_dice)]

        attacker_rolls = sorted(arolls, reverse=True)
        defender_rolls = sorted(drolls, reverse=True)

        await asyncio.sleep(3)

        message = f"{attacker.mention} rolled {attacker_dice} dice and got {', '.join(map(str, arolls))}\n"
        message += f"{defender.mention} rolled {defender_dice} dice and got {', '.join(map(str, drolls))}\n\n"
        message += f"{attacker.mention}'s highest rolls are {', '.join(map(str, attacker_rolls[: len(defender_rolls)]))}\n"
        message += f"{defender.mention}'s highest rolls are {', '.join(map(str, defender_rolls))}\n\n"

        alost = 0
        dlost = 0

        captured = False

        for aroll, droll in zip(attacker_rolls, defender_rolls):
            if aroll > droll:
                defender.captured_territories[to] -= 1
                dlost += 1

            else:
                attacker.captured_territories[_from] -= 1
                alost += 1

        if alost == 0:
            message += f"{attacker.mention} lost no armies meanwhile {defender.mention} lost {dlost} armies\n"

        elif dlost == 0:
            message += f"{defender.mention} lost no armies meanwhile {attacker.mention} lost {alost} armies\n"

        else:
            message += f"{attacker.mention} lost {alost} armies meanwhile {defender.mention} lost {dlost} armies\n"

        if defender.captured_territories[to] == 0:
            captured = True
            self.state.territories[to] = self.state.turn
            defender.captured_territories.pop(to)
            attacker.captured_territories[to] = 0

            message += f"{defender.mention} has lost {to.name.replace('_', ' ').title()} to {attacker.mention}\n"

            if len(defender.captured_territories) == 0:
                self.state.players.pop(defender.turn)
                if defender.turn < self.state.turn:
                    self.state.turn -= 1
                    for player in self.state.players[attacker.turn :]:
                        player.turn -= 1
                attacker.cards.extend(defender.cards)
                message += f"{defender.mention} has been eliminated from the game because they lost all their captured territories.\n"

        msg = await inter.followup.send(message, wait=True)
        await msg.delete(delay=ALERT_MESSAGE_DELETE_DELAY)

        if len(self.state.players) == 1:
            await inter.followup.send(
                f"{self.state.players[0].mention} has won the game by eliminating all other players!",
                wait=True,
            )
            self.stop()
            self.cog.cache.pop(inter.channel.id, None)
            return

        if captured:
            rng = range(1, attacker.captured_territories[_from])
            if len(rng) == 1:
                move_armies = 1

            else:
                view = NumberedButtonsView(rng, allowed_to_interact=[attacker.id])
                await inter.followup.send(
                    f"Select the amount of armies to move from {_from.name.replace('_', ' ').title()} to {to.name.replace('_', ' ').title()}",
                    view=view,
                    ephemeral=True,
                )
                if await view.wait():
                    if self.edit_task is not None and self.edit_task.done() is False:
                        self.edit_task.cancel()
                    self.edit_task = asyncio.create_task(self.show_updated_board(inter))
                    return await inter.followup.send(
                        "Why you take so long to respond bro?", ephemeral=True
                    )

                move_armies = view.result

            attacker.captured_territories[_from] -= move_armies
            attacker.captured_territories.setdefault(to, 0)
            attacker.captured_territories[to] += move_armies

            msg = await inter.followup.send(
                f"{attacker.mention} placed {move_armies} armies on their newly captured territory {to.name.replace('_', ' ').title()}",
                wait=True,
            )
            await msg.delete(delay=ALERT_MESSAGE_DELETE_DELAY)

            self.state.turn_territories_captured += 1

        self.state.turn_phase_completed = True
        if self.edit_task is not None and self.edit_task.done() is False:
            self.edit_task.cancel()
        self.edit_task = asyncio.create_task(self.show_updated_board(inter))

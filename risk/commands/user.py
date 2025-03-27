import discord
from redbot.core import commands
from redbot.core.utils.views import ConfirmView

from risk.common.riskmodels import TurnPhase
from risk.views.riskviews.game import GameView
from risk.views.riskviews.joingame import JoinGame

from ..abc import MixinMeta


class User(MixinMeta):
    @commands.group(name="risk", invoke_without_command=True)
    async def risk(self, ctx: commands.Context):
        """Start a game of Risk."""
        if ctx.channel.id in self.cache:
            return await ctx.send(
                f"A game is already in progress in this channel. Please end it through the `End Game` button or the `{ctx.clean_prefix}risk endgame` command before starting another."
            )

        if ctx.channel.id in self.db.get_conf(ctx.guild).saves:
            view = ConfirmView(ctx.author)
            await ctx.send(
                "A game save is present for this channel already. Do you want to continue playing that?",
                view=view,
            )
            if await view.wait():
                return await ctx.send("You took too long to respond. Please try again.")

            if not view.result:
                return await ctx.send(
                    "Either agree to continuing the saved game or delete it first with `[p]risk deletesave`."
                )

            state = self.db.get_conf(ctx.guild).saves[ctx.channel.id]
            view = GameView(state, ctx)
            if (
                state.turn_phase is TurnPhase.ARMY_CALCULATION
                and not state.turn_armies_received
            ):
                await view.army_calculation_phase()

            view.update_acc_to_state()

            file = await state.format_embed(ctx)
            view.message = await ctx.send(
                content=f"{state.turn_player.mention} it's your turn",
                file=file,
                view=view,
            )
            self.cache[ctx.channel.id] = view
            return

        view = JoinGame(ctx.author, ctx)
        await ctx.send(embed=view.format_embed(), view=view)

    @risk.command(name="endgame")
    async def risk_endgame(self, ctx: commands.Context):
        """End the game."""
        if ctx.channel.id not in self.cache:
            await ctx.send("No game in progress.")
            return

        if (gameview := self.cache[ctx.channel.id]).state.host != ctx.author.id:
            await ctx.send("Only the host can end the game.")
            return

        view = ConfirmView(ctx.author)
        await ctx.send("Are you sure you want to end the game?", view=view)
        if await view.wait():
            return await ctx.send("You took too long to respond. Please try again.")

        if not view.result:
            return await ctx.send("Game not ended.")

        gameview.stop()

        view = ConfirmView(ctx.author)
        view.message = await ctx.send(
            "DO you want to save this game to continue later? This save will be linked to this channel",
            ephemeral=True,
            view=view,
        )
        if await view.wait():
            await ctx.send(
                "Game not saved, you took too long to answer", ephemeral=True
            )
            return

        if view.result:
            async with self.cog.db.get_conf(ctx.guild.id) as conf:
                if ctx.channel.id in conf.saves:
                    view = ConfirmView(ctx.author)
                    view.message = await ctx.send(
                        "There is already a saved game in this channel, do you want to overwrite it?",
                        ephemeral=True,
                        view=view,
                    )
                    if await view.wait():
                        await ctx.followup.send(
                            "Game not saved, you took too long to answer",
                            ephemeral=True,
                        )
                        return

                    if not view.result:
                        return

                conf.saves[ctx.channel.id] = self.state

        del self.cache[ctx.channel.id]
        await ctx.send("Game ended.")

    @risk.command(name="saves")
    async def risk_saves(self, ctx: commands.Context):
        """List all saved games."""
        saves = self.db.get_conf(ctx.guild).saves
        if not saves:
            await ctx.send("No saved games.")
            return

        msg = "Saved games:\n"
        for i, save in enumerate(saves, 1):
            msg += f"{i}. <#{save}>\n"

        await ctx.send(msg)

    @risk.command(name="deletesave")
    async def risk_deletesave(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel = commands.CurrentChannel,
    ):
        """Delete a saved game."""
        async with self.db.get_conf(ctx.guild) as conf:
            if channel.id not in conf.saves:
                await ctx.send("No save found for this channel.")
                return

            del conf.saves[channel.id]
            await ctx.send("Save deleted.")

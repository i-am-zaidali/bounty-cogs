import discord
from redbot.core import commands
from redbot.core.utils.views import ConfirmView
from redbot.vendored.discord.ext import menus

from risk.common.riskmodels import TurnPhase
from risk.views.paginator import Paginator
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

            file = await state.generate_risk_board_image(ctx)
            view.message = await ctx.send(
                content=f"{state.turn_player.mention} it's your turn",
                file=file,
                view=view,
            )
            self.cache[ctx.channel.id] = view
            return

        view = JoinGame(ctx.author, ctx)
        await ctx.send(embed=view.format_embed(), view=view)

    @risk.command(name="refresh")
    async def risk_refresh(self, ctx: commands.Context):
        """Refresh the game view."""
        if ctx.channel.id not in self.cache:
            await ctx.send("No game in progress.")
            return

        view = self.cache[ctx.channel.id]
        view.update_acc_to_state()
        if view.message:
            await view.message.edit(view=view)
            await ctx.send(f"Game view refreshed. {view.message.jump_url}")
        else:
            await ctx.send("No game in progress.")

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

    @risk.command(name="info")
    async def risk_info(self, ctx: commands.Context):
        """Get information about Risk."""
        embeds = self.get_risk_embeds()
        source = menus.ListPageSource(embeds, per_page=1)

        async def format_page(menu, page):
            return page

        source.format_page = format_page
        await Paginator(source=source).start(ctx)

    @staticmethod
    def get_risk_embeds():
        embeds: list[discord.Embed] = []

        # Page 1: Welcome to Risk!
        embed1 = discord.Embed(
            title="📜 Welcome to Risk!",
            description=(
                "Risk is a strategic board game where players battle for global domination! Each turn, you will:\n\n"
                "1️⃣ **Gain and place armies**\n"
                "2️⃣ **Attack territories**\n"
                "3️⃣ **Fortify your defenses**\n"
                "4️⃣ **Earn cards to trade for reinforcements**\n\n"
                "Conquer all territories to win!\n\n"
                "🛠 **Game Phases Explained** → *(Use the buttons below to navigate!)*"
            ),
            color=discord.Color.gold(),
        )
        embed1.set_thumbnail(
            url="https://cdn.discordapp.com/attachments/1340320280912072855/1354889393030041600/quj4ks6o.png?ex=67e6ee93&is=67e59d13&hm=97c924862c92bc11b56476f96d57f5a0da64907ccf0fdf9d00197abb8fc944ca&"
        )  # Replace with actual image URL
        embeds.append(embed1)

        # Page 2: Gaining and Placing Armies
        embed2 = discord.Embed(
            title="🎖️ Gaining and Placing Armies",
            description=(
                "At the start of your turn, you receive reinforcements based on:\n\n"
                "✅ The **territories** you control\n"
                "✅ Completed **continent bonuses**\n"
                "✅ Any **traded cards** (if applicable)\n\n"
                "📝 **Your Actions:**\n"
                "🔄 *Press* **'Trade Cards'** *to exchange sets for bonus armies.*\n"
                "📍 *Press* **'Place Armies'** *to deploy them on your territories.*\n\n"
                "🔹 **Tip:** Spread your troops wisely to prepare for battle!"
            ),
            color=discord.Color.blue(),
        )
        embed2.set_thumbnail(
            url="https://cdn.discordapp.com/attachments/1340320280912072855/1354890948315713856/dcuon1tv.png?ex=67e6f006&is=67e59e86&hm=262e101c13ab34668ba64c10a80c8d9243479cd492b784f0b1e85e1869f33b7c&"
        )
        embeds.append(embed2)

        # Page 3: Attacking Opponents
        embed3 = discord.Embed(
            title="⚔️ Attacking Opponents",
            description=(
                "Once your armies are placed, you can attack enemy territories!\n\n"
                "🛡 **Combat Basics:**\n"
                "🎲 Roll dice based on your attack size.\n"
                "🔥 Higher rolls win, eliminating enemy troops.\n"
                "🏆 If you wipe out all defenders, you take the territory!\n\n"
                "⚔ **Your Actions:**\n"
                "🔫 *Press* **'Attack'** *to launch an attack.*\n"
                "🚫 *Press* **'End Turn'** *if you don’t want to attack.*\n\n"
                "🔹 **Tip:** Weaken opponents strategically and aim for key territories!"
            ),
            color=discord.Color.red(),
        )
        embed3.set_thumbnail(
            url="https://cdn.discordapp.com/attachments/1340320280912072855/1354889659473461258/54VTEpIN.png?ex=67e6eed3&is=67e59d53&hm=e4c2c2a79f4fbf75f1275f1bf7e7e50078ef6c07aa601eba26ba81836cf09b08&"
        )
        embeds.append(embed3)

        # Page 4: Moving Armies (Fortify)
        embed4 = discord.Embed(
            title="🏰 Moving Armies (Fortify)",
            description=(
                "After attacking, you can fortify your position by moving troops.\n\n"
                "🔄 **Why Fortify?**\n"
                "🛡 Strengthen borders against enemy attacks.\n"
                "🔁 Shift troops to support future attacks.\n\n"
                "🚶 **Your Actions:**\n"
                "➡️ *Press* **'Move Armies (Fortify)'** *to transfer troops between connected territories.*\n"
                "⏳ *Press* **'End Turn'** *when you’re done.*\n\n"
                "🔹 **Tip:** Always leave enough defenses behind!"
            ),
            color=discord.Color.dark_blue(),
        )
        embed4.set_thumbnail(
            url="https://cdn.discordapp.com/attachments/1340320280912072855/1354890293320880138/0crtW521.png?ex=67e6ef6a&is=67e59dea&hm=f2e5c0a8339166697fbe174393eb9198005fb6882f7288d0a5aec553788f18f9&"
        )
        embeds.append(embed4)

        # Page 5: Earning and Trading Cards
        embed5 = discord.Embed(
            title="🃏 Earning and Trading Cards",
            description=(
                "After your turn, if you conquered a territory, you earn a **Risk card**!\n\n"
                "📜 **Card Rules:**\n"
                "🔹 Collect **sets (3 matching symbols)** to trade for bonus armies.\n"
                "🛠 *Press* **'Trade Cards'** *at the start of your turn to redeem them.*\n\n"
                "🔹 **Tip:** Save cards for big reinforcements, but don’t hoard too long!"
            ),
            color=discord.Color.purple(),
        )
        embed5.set_thumbnail(
            url="https://github.com/i-am-zaidali/bounty-cogs/blob/main/risk/data/cards/wildcard.png?raw=true"
        )
        embeds.append(embed5)

        # Page 6: Map and Strategy
        embed6 = discord.Embed(
            title="🗺️ Map and Strategy",
            description=(
                "Want a detailed view of the game?\n\n"
                "🌍 **Your Actions:**\n"
                "📊 *Press* **'Show Raw Map'** *to view the full map with territory names.*\n\n"
                "🔹 **Tip:** Keep an eye on strong opponents and plan ahead!"
            ),
            color=discord.Color.dark_green(),
        )
        embed6.set_image(
            url="https://cdn.discordapp.com/attachments/1340320280912072855/1352975857043509248/risk_board.png?ex=67e68ff5&is=67e53e75&hm=1c46d867a29ce9781862db4072c7938472a9425e9eaa005dbdcdf35421ab96e1&"
        )
        embeds.append(embed6)

        # Page 7: Victory and Winning the Game
        embed7 = discord.Embed(
            title="🏆 Victory and Winning the Game",
            description=(
                "To win, **eliminate all opponents** and take control of every territory!\n\n"
                "🎖 **Winning Tips:**\n"
                "✅ Expand steadily—don’t spread too thin!\n"
                "💰 Use card trades wisely for reinforcements.\n"
                "🤝 Alliances can help... but trust no one!\n\n"
                "📝 **Now, conquer the world!**"
            ),
            color=discord.Color.orange(),
        )
        embed7.set_thumbnail(
            url="https://cdn.discordapp.com/attachments/1340320280912072855/1354891213035143188/6kFEK6uy.png?ex=67e6f045&is=67e59ec5&hm=533d5e55786e7b29f224766ae7a473c6d126c5c34798ce9ebce5fea2de78c7ec&"
        )
        embeds.append(embed7)

        return embeds

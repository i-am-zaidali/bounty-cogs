import asyncio
import collections
from redbot.core.bot import Red
from redbot.core import commands, Config
from redbot.core.utils import chat_formatting as cf
import discord
from .games import GTN, Cups, FTR, CTW
from typing import Literal


class MiniGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=1234567890, force_registration=True
        )
        self.config.register_guild(ftr={"wins": {}, "lastwinner": None})
        self.channels: dict[int, asyncio.Lock] = collections.defaultdict(
            lambda: asyncio.Lock()
        )

    async def cog_before_invoke(self, ctx: commands.Context):
        if self.channels[ctx.channel.id].locked():
            raise commands.CheckFailure(
                "A game is already in progress in this channel."
            )

        await self.channels[ctx.channel.id].acquire()
        return True

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if ctx.cog is self:
            self.channels[ctx.channel.id].release()

    @commands.command(name="cups")
    @commands.guild_only()
    async def cups(
        self, ctx: commands.Context, mode: Literal["easy", "medium", "hard"] = "easy"
    ):
        """Play a game of cups."""
        await Cups().play(ctx)

    @commands.command(name="guessthenumber", aliases=["gtn"])
    @commands.guild_only()
    async def gtn(self, ctx: commands.Context):
        """Play a game of guess the number."""
        await GTN().play(ctx)

    @commands.command(name="reacttowin", aliases=["rtw"])
    @commands.guild_only()
    async def rtw(self, ctx: commands.Context):
        """Play a game of react to win."""
        data = await self.config.guild(ctx.guild).ftr()
        await FTR(self, ctx.guild.get_member(data["lastwinner"]), data["wins"]).play(
            ctx
        )

    @commands.command(name="calculatetowin", aliases=["ctw", "calctowin"])
    @commands.guild_only()
    async def ctw(
        self, ctx: commands.Context, mode: Literal["easy", "medium", "hard"] = "easy"
    ):
        """Play a game of calculate to win."""
        await CTW().play(ctx)
